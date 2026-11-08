#!/usr/bin/env python3
"""Coverage of pairs of conditions in one test (Reviewer 2, comment 4; REMAINING_EXPERIMENTS 4).

Boundary-value coverage counts each input field on its own. This script counts combinations:
two range classes of different input fields (frame size, timing, sequence number, source MAC,
destination MAC), on the same virtual link, in the same executed test. The class list comes from
boundary_coverage.classify(); the universe is every such pair and is the same for all fuzzers.
A fuzzer that changes one field per test reaches no combination, by design.

Usage:
  combination_coverage.py --campaign LLM=runs/stage7/llm_full_r*.jsonl ... \
      --cache bdr_replay_cache_stage7.json --out combination_coverage.json
No LLM API and no simulator are used.
"""

import argparse
import glob
import json
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import boundary_coverage as bc  # noqa: E402
from analyze_campaigns import mann_whitney_exact, summary  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--campaign", action="append", required=True, metavar="NAME=GLOB")
    parser.add_argument("--cache", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    vls = bc.load_vls()
    universe = bc.combination_universe(vls)
    cache = json.loads(Path(args.cache).read_text())
    report = {"universe": len(universe), "per_run": {}, "per_fuzzer": {}}
    for spec in args.campaign:
        name, pattern = spec.split("=", 1)
        report["per_run"][name] = {}
        for path in sorted(Path(p).as_posix() for p in glob.glob(pattern)):
            seen = set()
            for _, cfg in bc.executed_inputs(path, cache):
                seen |= bc.combination_classes(cfg, vls)
            if not seen <= universe:
                raise SystemExit(f"{path}: combinations outside the universe: {sorted(seen - universe)[:3]}")
            report["per_run"][name][path] = len(seen)
        values = list(report["per_run"][name].values())
        report["per_fuzzer"][name] = summary(values)
        print(f"{name:14} of {len(universe)}: {values}", flush=True)
    report["mann_whitney_p"] = {
        f"{a} vs {b}": mann_whitney_exact(report["per_fuzzer"][a]["values"], report["per_fuzzer"][b]["values"])
        for a, b in combinations(report["per_fuzzer"], 2)
        if len(report["per_fuzzer"][a]["values"]) > 1 and len(report["per_fuzzer"][b]["values"]) > 1}
    for k, p in report["mann_whitney_p"].items():
        print(f"  p={p:.4f}  {k}")
    Path(args.out).write_text(json.dumps(report, indent=2))
    print("->", args.out)


if __name__ == "__main__":
    main()
