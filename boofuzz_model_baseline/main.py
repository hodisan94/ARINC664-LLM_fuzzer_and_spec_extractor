#!/usr/bin/env python3
"""Model-based BOOFUZZ baseline: run loop (context/BOOFUZZ_MODEL_PLAN.md, step 5).

Runs the fixed test list of generator.py on the simulator, through the same SimulatorRunner as
the other fuzzers, and writes one JSON line per test in the same history format (with
'sim_config'), so bdr_replay.py, boundary_coverage.py and analyze_campaigns.py read it unchanged.

The baseline has no rule labels ('protocol_rule' is None): like boofuzz, it mutates message
fields, not rules. Extra fields: 'boofuzz_field', 'boofuzz_value' (the value boofuzz chose,
before the adaptations of adapter.py), 'boofuzz_source' ('boofuzz' or 'afdx') and
'boofuzz_group'.

Usage (from the repository root):
  python3 boofuzz_model_baseline/main.py --max-iterations 200 \
      --history-path <file> --work-dir <dir> [--force | --resume]
No LLM API is used.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from boofuzz_model_baseline.generator import build_test_list  # noqa: E402
from boofuzz_model_baseline.model import load_boofuzz_values, load_vls  # noqa: E402
from llm_fuzzer.utils.log_parser import SimulatorLogParser  # noqa: E402
from llm_fuzzer.utils.simulator_runner import SimulatorRunner  # noqa: E402

COUNTERS = ("frames_received", "frames_forwarded", "frames_dropped_policing",
            "frames_dropped_frame_error", "frames_dropped_mac_error", "es_frames_rejected",
            "es_duplicates_discarded")
MAX_CONSECUTIVE_FAILURES = 5  # as in the other baselines


def run(max_iterations, history_path, work_dir, resume, force, afdx=True):
    history_path = Path(history_path)
    if history_path.exists() and history_path.stat().st_size > 0:
        if force:
            history_path.unlink()
        elif not resume:
            raise SystemExit(f"{history_path} exists; use --resume or --force")
    done = len(history_path.read_text().splitlines()) if history_path.exists() else 0
    history_path.parent.mkdir(parents=True, exist_ok=True)

    version, values = load_boofuzz_values()
    tests, skipped = build_test_list(load_vls(), values, afdx)
    print(f"boofuzz {version}, AFDX values {'on' if afdx else 'off'}: {len(tests)} tests in the list "
          f"({len(skipped)} skipped as identical inputs); running "
          f"{min(max_iterations, len(tests)) - done} from #{done}")
    runner = SimulatorRunner(work_dir=work_dir)
    failures = 0
    for i in range(done, min(max_iterations, len(tests))):
        t = tests[i]
        start = datetime.now()
        result = runner.run_simulation(sim_config=t["sim_config"], run_id=f"boofuzz_model_{i:03d}",
                                       timeout=120)
        record = {
            "iteration": i,
            "timestamp": start.isoformat(),
            "duration": (datetime.now() - start).total_seconds(),
            "fuzzer_type": "BOOFUZZ_MODEL",
            "boofuzz_version": version,
            "afdx_values": afdx,
            "target_vl": t["vl"],
            "protocol_rule": None,
            "boofuzz_field": t["field"],
            "boofuzz_value": t["value"],
            "boofuzz_source": t["source"],
            "boofuzz_group": t["group"],
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
        print(f"#{i:3d} {t['field']:17} {str(t['value']):14} VL {t['vl']}  "
              f"{'ok' if result['success'] else 'FAILED: ' + str(result.get('error'))[:80]}")
        failures = 0 if result["success"] else failures + 1
        if failures >= MAX_CONSECUTIVE_FAILURES:
            print(f"Stopping: {failures} consecutive failures")
            break


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--max-iterations", type=int, default=200)
    parser.add_argument("--history-path", required=True)
    parser.add_argument("--work-dir", default=None,
                        help="isolated simulator working directory, for parallel campaigns")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--resume", action="store_true", help="continue an existing history")
    mode.add_argument("--force", action="store_true", help="delete an existing history first")
    parser.add_argument("--no-afdx-values", action="store_true",
                        help="use boofuzz's own values only, without the tester-defined AFDX limits")
    args = parser.parse_args()
    run(args.max_iterations, args.history_path, args.work_dir, args.resume, args.force,
        afdx=not args.no_afdx_values)


if __name__ == "__main__":
    main()
