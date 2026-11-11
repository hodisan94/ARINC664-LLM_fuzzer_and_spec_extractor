#!/usr/bin/env python3
"""
Experiment 1 statistics of a test-case file: groups, test cases, and the
Redundancy Ratio, i.e., the share of test cases that repeat the value and
violation type of another test case of the same rule group.

Usage: test_case_stats.py [test_cases.json ...]
Output: evaluation/revision/out/test_case_stats.json
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from llm_fuzzer.utils.test_case_mapping import classify_rule  # noqa: E402


def stats(path: Path) -> dict:
    tc = json.loads(path.read_text())
    seen, duplicates, total = set(), 0, 0
    for rule, group in tc.items():
        for case in group.get("test_cases", []):
            total += 1
            key = (rule, json.dumps(case.get("value"), sort_keys=True), case.get("violation_type"))
            duplicates += key in seen
            seen.add(key)
    no_parameter = sum(classify_rule(r) in ("ip_header", "priority") for r in tc)
    return {"file": str(path.relative_to(ROOT)), "groups": len(tc), "test_cases": total,
            "duplicates": duplicates, "redundancy_ratio": round(duplicates / total, 4) if total else 0.0,
            "groups_without_simulator_parameter": no_parameter}


def main():
    paths = [Path(p).resolve() for p in sys.argv[1:]] or [ROOT / "configs/test_cases.json"]
    report = [stats(p) for p in paths]
    out = ROOT / "evaluation/revision/out/test_case_stats.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    for r in report:
        print(r)
    print(f"-> {out}")


if __name__ == "__main__":
    main()
