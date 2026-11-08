#!/usr/bin/env python3
"""Bugs found and boundary classes reached as a function of the test budget (TAES revision,
context/REVIEW_STATUS.md, Fig. 5 replacement).

For each run and each budget n (25, 50, ..., 200), counts what the first n tests of the run
reached, using only results that already exist:
  - bugs: a bug counts at budget n if its first detecting iteration (bug replay output,
    per_bug.first_detection_iter) is below n; reachable bugs only (8);
  - boundary points (of 79) and ranges (of 51): boundary_coverage.classify() on the executed
    inputs whose iteration is below n, the same inputs boundary_coverage.py uses.
No simulator run and no LLM API call.

Usage: python evaluation/revision/budget_curves.py --out evaluation/results/revision/budget_curves.json
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evaluation"))
sys.path.insert(0, str(ROOT / "evaluation" / "revision"))

from bdr_replay import BUGS  # noqa: E402
from boundary_coverage import classify, executed_inputs, load_vls, universe  # noqa: E402

RES = ROOT / "evaluation/results/revision"
RUNS = "evaluation/results/revision/runs/stage7/"
FUZZERS = {
    "LLM": [f"llm_full_r{i}" for i in range(1, 6)],
    "Random (Peach rule)": [f"random_model_s{i}" for i in range(1, 6)],
    "boofuzz as is": ["boofuzz_as_is"],
    "A2 feedback only": ["llm_A2"],
    "A1 steering only": ["llm_A1"],
    "A0 neither": ["llm_A0"],
}
BUDGETS = list(range(25, 201, 25))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    replay = {}
    for f in ("bdr_replay_stage7.json", "bdr_replay_model_baselines.json"):
        replay.update(json.loads((RES / f).read_text()))
    cache = json.loads((RES / "bdr_replay_cache_stage7.json").read_text())
    vls = load_vls()
    points_all, ranges_all = universe(vls)
    reachable = [b["id"] for b in BUGS if b.get("reachable", True)]
    report = {"budgets": BUDGETS, "bugs_reachable": len(reachable),
              "points_total": len(points_all), "ranges_total": len(ranges_all), "runs": {}}
    for fuzzer, runs in FUZZERS.items():
        report["runs"][fuzzer] = {}
        for run in runs:
            path = RUNS + run + ".jsonl"
            per_bug = replay[path]["per_bug"]
            inputs = executed_inputs(path, cache)
            curve = []
            for n in BUDGETS:
                bugs = sum(1 for b in reachable if per_bug[b]["first_detection_iter"] is not None
                           and per_bug[b]["first_detection_iter"] < n)
                pts, rng = set(), set()
                for it, cfg in inputs:
                    if it < n:
                        p, r = classify(cfg, vls)
                        pts |= p
                        rng |= r
                curve.append({"budget": n, "bugs": bugs, "points": len(pts), "ranges": len(rng)})
            report["runs"][fuzzer][run] = curve
    Path(args.out).write_text(json.dumps(report, indent=2))

    for metric in ("bugs", "points", "ranges"):
        print(f"\n{metric} by budget: " + " ".join(f"{n:>7}" for n in BUDGETS))
        for fuzzer, runs in report["runs"].items():
            cells = []
            for i in range(len(BUDGETS)):
                vals = [c[i][metric] for c in runs.values()]
                cells.append(f"{min(vals)}" if min(vals) == max(vals) else f"{min(vals)}-{max(vals)}")
            print(f"  {fuzzer:20}" + " ".join(f"{c:>7}" for c in cells))
    print("->", args.out)


if __name__ == "__main__":
    main()
