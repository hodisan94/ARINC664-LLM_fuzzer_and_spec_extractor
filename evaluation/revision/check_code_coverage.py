#!/usr/bin/env python3
"""Checks of the code-coverage measurement (context/EVALUATION_METRICS.md, section 3.6).

Run before using code_coverage.py's numbers:
  1. parallel and one-at-a-time runs of the same inputs give identical coverage (gcov adds up
     the counts of processes that write the same files);
  2. measuring the same inputs again gives identical numbers;
  3. the instrumented simulator produces the same drop and rejection counters as the fixed one.
Also prints the coverage of the unmutated input (normal traffic).

Usage (from the repository root, in WSL):
  AFDX_NS3_PATH=/tmp/ns3_cov python3 evaluation/revision/check_code_coverage.py \
      --gcovr ~/cov_venv/bin/gcovr --fixed /tmp/ns3_fixtest
No LLM API is used.
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evaluation"))
sys.path.insert(0, str(ROOT / "evaluation" / "revision"))

import code_coverage as cc  # noqa: E402
from bdr_replay import config_key, logged_campaign  # noqa: E402
from compute_bdr import parse_metrics  # noqa: E402
from llm_fuzzer.utils.simulator_runner import SimulatorRunner  # noqa: E402

HISTORY = ROOT / "evaluation/results/revision/runs/stage7/llm_full_r1.jsonl"


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--gcovr", required=True)
    parser.add_argument("--fixed", required=True, help="the fixed (uninstrumented) ns-3 tree")
    parser.add_argument("--inputs", type=int, default=24)
    args = parser.parse_args()
    ns3 = os.environ["AFDX_NS3_PATH"]
    cfgs = list({config_key(c): c for _, c in logged_campaign(HISTORY, 10**9)}.values())[:args.inputs]

    base = cc.measure([cc.UNMUTATED], ns3, args.gcovr, 1)
    print(f"unmutated: {base['line_covered']}/{base['line_total']} lines, "
          f"{base['branch_covered']}/{base['branch_total']} branches")
    par = cc.measure(cfgs, ns3, args.gcovr, 8)
    seq = cc.measure(cfgs, ns3, args.gcovr, 1)
    again = cc.measure(cfgs, ns3, args.gcovr, 8)

    def key(r):
        return (r["line_covered"], r["branch_covered"],
                {f: (v["line_covered"], v["branch_covered"]) for f, v in r["files"].items()})

    print(f"{len(cfgs)} inputs: lines {par['line_covered']}, branches {par['branch_covered']}")
    print("check 1, parallel == one at a time:", key(par) == key(seq))
    print("check 2, repeat gives the same numbers:", key(par) == key(again))
    cov = SimulatorRunner(ns3_path=ns3, work_dir="/tmp/check_code_coverage/cov")
    fixed = SimulatorRunner(ns3_path=args.fixed, work_dir="/tmp/check_code_coverage/fixed")
    same = sum(parse_metrics(cov.run_simulation(sim_config=dict(c, inject_bug="none"), timeout=120))
               == parse_metrics(fixed.run_simulation(sim_config=dict(c, inject_bug="none"), timeout=120))
               for c in cfgs[:8])
    print(f"check 3, same counters as the fixed simulator: {same}/8")


if __name__ == "__main__":
    main()
