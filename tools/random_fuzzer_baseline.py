#!/usr/bin/env python3
"""
Random Baseline Fuzzer - For Comparison with AI-Driven Fuzzer

Runs the same fuzzing experiments but with purely random parameter selection
instead of LLM-guided decisions. Used to demonstrate AI effectiveness.

Usage:
    python3 tools/random_fuzzer_baseline.py --iterations 50 --outdir experiments/random_baseline
"""

import argparse
import json
import random
import subprocess
import time
import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

# Project paths (same as AI fuzzer)
ROOT_DIR = Path.home() / "ns-3-reset" / "ns-3"
SIMULATOR_BIN = ROOT_DIR / "build" / "examples" / "AFDX_V3" / "ns3-dev-afdx-demo-debug"
MUTATIONS_JSON = ROOT_DIR / "examples" / "AFDX_V3" / "mutations.json"

# Same parameter ranges as AI fuzzer
VALID_VLS = [1001, 1002, 1003, 2001, 2002, 2003, 3001, 3002]
PROBABILITY_MIN = 0.10
PROBABILITY_MAX = 0.50
PAYLOAD_DELTAS = [-64, -32, -16, 0, 16, 32, 64]
TIMING_JITTERS = [0, 2, 4, 8, 12, 16]


def random_mutation_config() -> Dict[str, Any]:
    """Generate completely random mutation configuration."""
    return {
        "vlId": random.choice(VALID_VLS),
        "op": "bitflip",
        "prob": round(random.uniform(PROBABILITY_MIN, PROBABILITY_MAX), 2),
        "payload_delta_bytes": random.choice(PAYLOAD_DELTAS),
        "timing_jitter_ms": random.choice(TIMING_JITTERS)
    }


def parse_simulator_output(stdout: str, stderr: str) -> Dict[str, int]:
    """Parse simulator output to extract metrics."""
    metrics = {
        "frames_received": 0,
        "frames_forwarded": 0,
        "frames_dropped": 0,
        "frames_dropped_invalid_vl": 0
    }
    
    # Simple parsing - adjust based on your actual output format
    lines = (stdout + stderr).split('\n')
    for line in lines:
        if "frames received" in line.lower():
            try:
                metrics["frames_received"] = int(line.split(':')[-1].strip())
            except:
                pass
        elif "frames forwarded" in line.lower():
            try:
                metrics["frames_forwarded"] = int(line.split(':')[-1].strip())
            except:
                pass
        elif "frames dropped" in line.lower() and "invalid" not in line.lower():
            try:
                metrics["frames_dropped"] = int(line.split(':')[-1].strip())
            except:
                pass
        elif "invalid vl" in line.lower():
            try:
                metrics["frames_dropped_invalid_vl"] = int(line.split(':')[-1].strip())
            except:
                pass
    
    return metrics


def compute_reward(metrics: Dict[str, int]) -> float:
    """
    Compute reward using same formula as AI fuzzer.
    This allows direct comparison.
    """
    total = metrics["frames_received"]
    if total == 0:
        return 0.0
    
    forward_ratio = metrics["frames_forwarded"] / total
    policing_ratio = metrics["frames_dropped"] / total
    invalid_ratio = metrics["frames_dropped_invalid_vl"] / total
    
    # Same reward formula as ai_fuzzer_agent.py
    if invalid_ratio > 0:
        return -1.0 - 5.0 * invalid_ratio
    
    reward = (
        0.6 * policing_ratio +
        -0.2 * forward_ratio +
        0.0  # No novelty/repeat for random
    )
    
    return reward


def run_experiment(iteration: int, config: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
    """Run single fuzzing experiment with random config."""
    
    # Create mutations.json
    mutations_data = {
        "round": iteration,
        "timestamp": int(time.time()),
        "mutations": [config],
        "strategy": "RANDOM_BASELINE",
        "note": f"Random iteration {iteration}"
    }
    
    MUTATIONS_JSON.write_text(json.dumps(mutations_data, indent=2))
    
    # Run simulator
    run_id = f"random_{iteration:03d}_vl{config['vlId']}_p{config['prob']}"
    run_dir = output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"[{iteration:3d}] VL={config['vlId']}, prob={config['prob']:.2f}, "
          f"payload={config['payload_delta_bytes']:+3d}, jitter={config['timing_jitter_ms']}", 
          end=" ... ")
    
    try:
        start_time = time.time()
        result = subprocess.run(
            [str(SIMULATOR_BIN)],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            timeout=60
        )
        elapsed = time.time() - start_time
        
        # Save logs
        log_file = run_dir / "output.log"
        log_file.write_text(result.stdout + "\n\n=== STDERR ===\n\n" + result.stderr)
        
        # Parse metrics
        metrics = parse_simulator_output(result.stdout, result.stderr)
        reward = compute_reward(metrics)
        
        print(f"reward={reward:.3f}, recv={metrics['frames_received']}, "
              f"fwd={metrics['frames_forwarded']}, drop={metrics['frames_dropped']}")
        
        return {
            "iteration": iteration,
            "run_id": run_id,
            "vl": config['vlId'],
            "probability": config['prob'],
            "payload_delta": config['payload_delta_bytes'],
            "timing_jitter": config['timing_jitter_ms'],
            "success": result.returncode == 0,
            "runtime_seconds": elapsed,
            "reward": reward,
            **metrics
        }
    
    except subprocess.TimeoutExpired:
        print("TIMEOUT")
        return {
            "iteration": iteration,
            "run_id": run_id,
            "vl": config['vlId'],
            "probability": config['prob'],
            "payload_delta": config['payload_delta_bytes'],
            "timing_jitter": config['timing_jitter_ms'],
            "success": False,
            "error": "timeout"
        }
    except Exception as e:
        print(f"Error: {e}")
        return {
            "iteration": iteration,
            "run_id": run_id,
            "vl": config['vlId'],
            "probability": config['prob'],
            "payload_delta": config['payload_delta_bytes'],
            "timing_jitter": config['timing_jitter_ms'],
            "success": False,
            "error": str(e)
        }


def save_results_csv(results: List[Dict[str, Any]], output_file: Path):
    """Save results in CSV format compatible with analysis tools."""
    if not results:
        return
    
    fieldnames = [
        "iteration", "run_id", "vl", "probability", "payload_delta", "timing_jitter",
        "frames_received", "frames_forwarded", "frames_dropped", "frames_dropped_invalid_vl",
        "reward", "success", "runtime_seconds"
    ]
    
    with open(output_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(results)


def main():
    parser = argparse.ArgumentParser(description="Random Baseline Fuzzer")
    parser.add_argument("--iterations", type=int, default=50, 
                        help="Number of random tests")
    parser.add_argument("--outdir", type=Path, 
                        default=ROOT_DIR / "experiments" / "random_baseline",
                        help="Output directory")
    parser.add_argument("--seed", type=int, default=42, 
                        help="Random seed for reproducibility")
    args = parser.parse_args()
    
    # Set random seed
    random.seed(args.seed)
    
    # Setup output directory
    args.outdir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 80)
    print("RANDOM BASELINE FUZZER")
    print("=" * 80)
    print(f"Iterations: {args.iterations}")
    print(f"Output dir: {args.outdir}")
    print(f"Random seed: {args.seed}")
    print(f"Timestamp:  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print()
    
    # Run random experiments
    results = []
    start_time = time.time()
    
    for i in range(1, args.iterations + 1):
        config = random_mutation_config()
        result = run_experiment(i, config, args.outdir)
        results.append(result)
    
    elapsed = time.time() - start_time
    
    # Calculate statistics
    successful_runs = [r for r in results if r.get("success", False)]
    rewards = [r.get("reward", 0.0) for r in successful_runs if "reward" in r]
    
    avg_reward = sum(rewards) / len(rewards) if rewards else 0.0
    max_reward = max(rewards) if rewards else 0.0
    min_reward = min(rewards) if rewards else 0.0
    
    # Save summary
    summary = {
        "strategy": "RANDOM_BASELINE",
        "iterations": args.iterations,
        "seed": args.seed,
        "elapsed_seconds": elapsed,
        "successful_runs": len(successful_runs),
        "statistics": {
            "avg_reward": avg_reward,
            "max_reward": max_reward,
            "min_reward": min_reward
        },
        "timestamp": datetime.now().isoformat()
    }
    
    summary_file = args.outdir / "summary.json"
    summary_file.write_text(json.dumps(summary, indent=2))
    
    # Save CSV for analysis
    csv_file = args.outdir / "random_results.csv"
    save_results_csv(results, csv_file)
    
    print("\n" + "=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)
    print(f"Total runs:      {args.iterations}")
    print(f"Successful:      {len(successful_runs)}")
    print(f"Elapsed time:    {elapsed:.1f}s")
    print(f"Avg reward:      {avg_reward:.3f}")
    print(f"Max reward:      {max_reward:.3f}")
    print(f"Min reward:      {min_reward:.3f}")
    print()
    print(f"Results saved to:")
    print(f"   Summary:  {summary_file}")
    print(f"   CSV:      {csv_file}")
    print("=" * 80)


if __name__ == "__main__":
    main()

