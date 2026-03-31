#!/usr/bin/env python3
"""
Bug Detection Rate (BDR) Evaluation

Injects known bugs into the ns-3 AFDX simulator (via mutations.json) and
runs each fuzzer's historical test cases against each bug to measure
detection capability.

BDR = #bugs_detected / #bugs_injected
Mean Iterations to First Detection = avg(first iteration that detects each bug)

A bug is "detected" when the fuzzer's test case, replayed against a buggy
simulator, produces different observable behaviour from the non-buggy run —
specifically, frames that should have been dropped/rejected are now forwarded.
"""

import json
import os
import sys
import time
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from llm_fuzzer.utils.simulator_runner import SimulatorRunner
from llm_fuzzer.utils.log_parser import SimulatorLogParser

# ── Bug catalogue ─────────────────────────────────────────────────────
BUGS = [
    {
        "id": "skip_bag_policing",
        "description": "Switch skips BAG timing enforcement",
        "location": "afdx-switch.cc Step 3",
        "detection_signal": "policing_drop_decrease",
    },
    {
        "id": "skip_frame_validation",
        "description": "Switch skips frame size validation",
        "location": "afdx-switch.cc Step 1",
        "detection_signal": "frame_error_drop_decrease",
    },
    {
        "id": "skip_mac_validation",
        "description": "Switch skips source MAC check",
        "location": "afdx-switch.cc Step 2b",
        "detection_signal": "mac_error_drop_decrease",
    },
    {
        "id": "skip_token_bucket",
        "description": "Switch skips token-bucket policing",
        "location": "afdx-switch.cc Step 4",
        "detection_signal": "policing_drop_decrease",
    },
    {
        "id": "skip_vl_check",
        "description": "Switch skips VL authorization",
        "location": "afdx-switch.cc Step 2",
        "detection_signal": "forward_increase",
    },
    {
        "id": "skip_constant_field",
        "description": "End System skips constant-field MAC check",
        "location": "afdx-end-system.cc Step 2 + traffic-generator.cc Step 2",
        "detection_signal": "es_rejection_decrease",
    },
    {
        "id": "skip_sequence_check",
        "description": "End System skips sequence-number integrity check",
        "location": "afdx-end-system.cc Step 5 + traffic-generator.cc Step 3",
        "detection_signal": "es_rejection_decrease",
    },
    {
        "id": "accept_oversized",
        "description": "Switch accepts frames larger than 1518 bytes",
        "location": "afdx-switch.cc ValidateFrame",
        "detection_signal": "frame_error_drop_decrease",
    },
]


def run_single_iteration(runner: SimulatorRunner, history_record: dict,
                         inject_bug: str = "none") -> Dict[str, Any]:
    """Replay a single historical iteration with an optional injected bug."""
    test_inputs = {
        "vl_id": history_record.get("target_vl", 2001),
        "frames": [],
        "metadata": {
            "mutation_type": history_record.get("mutation_type", ""),
            "bag_value": history_record.get("bag_value"),
            "frame_size": history_record.get("frame_size"),
            "timing_jitter_ms": history_record.get("timing_jitter_ms"),
            "sequence_number_override": history_record.get("sequence_number_override"),
            "dest_mac_mutation": history_record.get("dest_mac_mutation"),
            "mac_mutation_type": history_record.get("mac_mutation_type"),
            "prob": history_record.get("prob", 0.5),
            "strategy_type": history_record.get("strategy", "edge-case"),
            "inject_bug": inject_bug,
        },
    }
    return runner.run_simulation(test_inputs=test_inputs, timeout=60)


def parse_metrics(sim_result: dict) -> Dict[str, float]:
    """Extract numeric metrics from a simulation result."""
    if not sim_result.get("success"):
        return {}
    parser = SimulatorLogParser(
        log_content=sim_result.get("log_content", ""),
        csv_content=sim_result.get("csv_content", ""),
    )
    m = parser.parse()
    return {
        "frames_forwarded": m.get("frames_forwarded", 0),
        "frames_dropped_policing": m.get("frames_dropped_policing", 0),
        "frames_dropped_frame_error": m.get("frames_dropped_frame_error", 0),
        "frames_dropped_mac_error": m.get("frames_dropped_mac_error", 0),
        "forward_rate": m.get("forward_rate", 0),
        "policing_rate": m.get("policing_rate", 0),
        "es_frames_rejected": m.get("es_frames_rejected", 0),
        "es_frames_received": m.get("es_frames_received", 0),
    }


def bug_detected(baseline_metrics: dict, buggy_metrics: dict, bug: dict) -> bool:
    """
    Determine whether the difference between baseline and buggy metrics
    indicates that the fuzzer's test case would reveal the bug.

    The core idea: when a validation is skipped, frames that WOULD have been
    dropped are now forwarded.  So we look for more forwarding / less dropping
    compared to the clean run.
    """
    if not baseline_metrics or not buggy_metrics:
        return False

    sig = bug["detection_signal"]
    THRESHOLD = 0.5  # at least one frame difference matters

    if sig == "policing_drop_decrease":
        bl = baseline_metrics.get("frames_dropped_policing", 0)
        bg = buggy_metrics.get("frames_dropped_policing", 0)
        return bl - bg > THRESHOLD

    if sig == "frame_error_drop_decrease":
        bl = baseline_metrics.get("frames_dropped_frame_error", 0)
        bg = buggy_metrics.get("frames_dropped_frame_error", 0)
        return bl - bg > THRESHOLD

    if sig == "mac_error_drop_decrease":
        bl = baseline_metrics.get("frames_dropped_mac_error", 0)
        bg = buggy_metrics.get("frames_dropped_mac_error", 0)
        return bl - bg > THRESHOLD

    if sig == "forward_increase":
        bl = baseline_metrics.get("frames_forwarded", 0)
        bg = buggy_metrics.get("frames_forwarded", 0)
        return bg - bl > THRESHOLD

    if sig == "es_rejection_decrease":
        bl = baseline_metrics.get("es_frames_rejected", 0)
        bg = buggy_metrics.get("es_frames_rejected", 0)
        return bl - bg > THRESHOLD

    return False


def evaluate_fuzzer(
    fuzzer_name: str,
    history_path: str,
    runner: SimulatorRunner,
    max_iterations: int = 50,
) -> Dict[str, Any]:
    """Run BDR evaluation for a single fuzzer."""
    print(f"\n{'='*60}")
    print(f"  BDR EVALUATION: {fuzzer_name}")
    print(f"{'='*60}")

    records = []
    with open(history_path) as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                if d.get("simulation_success", False):
                    records.append(d)

    records = records[:max_iterations]
    print(f"  Loaded {len(records)} successful iterations")

    results_per_bug: Dict[str, Dict] = {}

    for bug in BUGS:
        bug_id = bug["id"]
        print(f"\n  Bug: {bug_id} — {bug['description']}")

        detected = False
        first_detection_iter = None

        for idx, rec in enumerate(records):
            iteration_num = rec.get("iteration", idx)

            # Run baseline (no bug)
            baseline_result = run_single_iteration(runner, rec, inject_bug="none")
            baseline_metrics = parse_metrics(baseline_result)

            # Run with bug
            buggy_result = run_single_iteration(runner, rec, inject_bug=bug_id)
            buggy_metrics = parse_metrics(buggy_result)

            if bug_detected(baseline_metrics, buggy_metrics, bug):
                detected = True
                first_detection_iter = iteration_num
                print(f"    DETECTED at iteration {iteration_num}")
                break

        if not detected:
            print(f"    NOT detected in {len(records)} iterations")

        results_per_bug[bug_id] = {
            "detected": detected,
            "first_detection_iter": first_detection_iter,
            "description": bug["description"],
        }

    bugs_detected = sum(1 for r in results_per_bug.values() if r["detected"])
    bdr = bugs_detected / len(BUGS) if BUGS else 0

    detection_iters = [
        r["first_detection_iter"]
        for r in results_per_bug.values()
        if r["detected"] and r["first_detection_iter"] is not None
    ]
    mean_iter = sum(detection_iters) / len(detection_iters) if detection_iters else None

    print(f"\n  SUMMARY: {bugs_detected}/{len(BUGS)} bugs detected  (BDR = {bdr:.1%})")
    if mean_iter is not None:
        print(f"  Mean iterations to first detection: {mean_iter:.1f}")

    return {
        "fuzzer": fuzzer_name,
        "bugs_detected": bugs_detected,
        "bugs_total": len(BUGS),
        "bdr": bdr,
        "mean_iterations_to_first_detection": mean_iter,
        "per_bug": results_per_bug,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="BDR Evaluation")
    parser.add_argument("--max-iterations", type=int, default=50,
                        help="Max iterations per fuzzer to evaluate")
    parser.add_argument("--fuzzers", nargs="*",
                        default=["LLM", "Boofuzz", "Random"],
                        help="Which fuzzers to evaluate")
    parser.add_argument("--output", type=str,
                        default="evaluation/results/bdr_report.json",
                        help="Output JSON file")
    args = parser.parse_args()

    runner = SimulatorRunner()

    fuzzer_paths = {
        "LLM": "llm_fuzzer/data/iteration_history.jsonl",
        "Boofuzz": "boofuzz_baseline/data/iteration_history.jsonl",
        "Random": "random_baseline/data/iteration_history.jsonl",
    }

    all_results = {}
    for name in args.fuzzers:
        path = fuzzer_paths.get(name)
        if not path or not Path(path).exists():
            print(f"Skipping {name}: history file not found")
            continue
        result = evaluate_fuzzer(name, path, runner, args.max_iterations)
        all_results[name] = result

    # Final comparison
    print(f"\n{'='*60}")
    print("  BDR COMPARISON")
    print(f"{'='*60}")
    for name, r in sorted(all_results.items(), key=lambda x: -x[1]["bdr"]):
        mi = r["mean_iterations_to_first_detection"]
        mi_str = f"{mi:.1f}" if mi is not None else "N/A"
        print(f"  {name:10s}: BDR={r['bdr']:.1%}  "
              f"({r['bugs_detected']}/{r['bugs_total']})  "
              f"Mean iter={mi_str}")
        for bug_id, br in r["per_bug"].items():
            status = "DETECTED" if br["detected"] else "missed"
            iter_str = f" @iter {br['first_detection_iter']}" if br["detected"] else ""
            print(f"    {bug_id:30s}: {status}{iter_str}")

    # Save report
    report = {
        "generated": datetime.now().isoformat(),
        "bugs": [{k: v for k, v in b.items()} for b in BUGS],
        "results": all_results,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nReport saved to: {output_path}")


if __name__ == "__main__":
    main()
