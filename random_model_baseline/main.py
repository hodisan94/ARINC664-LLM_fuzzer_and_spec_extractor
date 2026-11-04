#!/usr/bin/env python3
"""Model-based random baseline: run loop (context/RANDOM_MODEL_PLAN.md, step 2).

Runs the seeded tests of generator.py on the simulator, through the same SimulatorRunner as the
other fuzzers, and writes one JSON line per test in the same history format as the model-based
BOOFUZZ baseline (with 'sim_config'), so bdr_replay.py, boundary_coverage.py and
analyze_campaigns.py read it unchanged.

No rule labels ('protocol_rule' is None). Extra fields: 'seed' and 'random_values' (the field
values drawn, before the adapter's clamping).

Usage (from the repository root):
  python3 random_model_baseline/main.py --seed 1 --max-iterations 200 \
      --history-path <file> --work-dir <dir> [--force | --resume]
No LLM API is used.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from boofuzz_model_baseline.main import COUNTERS, MAX_CONSECUTIVE_FAILURES  # noqa: E402
from boofuzz_model_baseline.model import load_vls  # noqa: E402
from llm_fuzzer.utils.log_parser import SimulatorLogParser  # noqa: E402
from llm_fuzzer.utils.simulator_runner import SimulatorRunner  # noqa: E402
from random_model_baseline.generator import draw_test  # noqa: E402


def run(seed, max_iterations, history_path, work_dir, resume, force):
    history_path = Path(history_path)
    if history_path.exists() and history_path.stat().st_size > 0:
        if force:
            history_path.unlink()
        elif not resume:
            raise SystemExit(f"{history_path} exists; use --resume or --force")
    done = len(history_path.read_text().splitlines()) if history_path.exists() else 0
    history_path.parent.mkdir(parents=True, exist_ok=True)
    vls = load_vls()
    print(f"random baseline, seed {seed}: running {max_iterations - done} tests from #{done}")
    runner = SimulatorRunner(work_dir=work_dir)
    failures = 0
    for i in range(done, max_iterations):
        t = draw_test(seed, i, vls)
        start = datetime.now()
        result = runner.run_simulation(sim_config=t["sim_config"], run_id=f"random_model_{seed}_{i:03d}",
                                       timeout=120)
        record = {
            "iteration": i,
            "timestamp": start.isoformat(),
            "duration": (datetime.now() - start).total_seconds(),
            "fuzzer_type": "RANDOM_MODEL",
            "seed": seed,
            "target_vl": t["vl"],
            "protocol_rule": None,
            "random_values": t["values"],
            "sim_config": result.get("sim_config"),
            "simulation_success": result["success"],
            "error": result.get("error"),
        }
        if result["success"]:
            metrics = SimulatorLogParser(log_content=result.get("log_content", ""),
                                         csv_content=result.get("csv_content", "")).parse()
            record.update({k: metrics.get(k, 0) for k in COUNTERS})
        with open(history_path, "a") as f:
            f.write(json.dumps(record) + "\n")
        print(f"#{i:3d} VL {t['vl']}  {t['values']}  "
              f"{'ok' if result['success'] else 'FAILED: ' + str(result.get('error'))[:80]}")
        failures = 0 if result["success"] else failures + 1
        if failures >= MAX_CONSECUTIVE_FAILURES:
            print(f"Stopping: {failures} consecutive failures")
            break


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--max-iterations", type=int, default=200)
    parser.add_argument("--history-path", required=True)
    parser.add_argument("--work-dir", default=None,
                        help="isolated simulator working directory, for parallel campaigns")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--resume", action="store_true", help="continue an existing history")
    mode.add_argument("--force", action="store_true", help="delete an existing history first")
    args = parser.parse_args()
    run(args.seed, args.max_iterations, args.history_path, args.work_dir, args.resume, args.force)


if __name__ == "__main__":
    main()
