#!/usr/bin/env python3
"""What did each iteration actually send? (TAES revision: R1-M2, R2-C4).

Rule Coverage counts the rule label that each iteration records. This script replays
every recorded strategy through the shared TestGenerator (no simulator, no API calls)
and classifies the executed traffic:

  rule_test_case   predefined test-case frames of a rule were generated
  direct_params    only direct mutation parameters (BAG, frame size, sequence number,
                   jitter, payload) were applied
  mac_or_seq_only  only a MAC or sequence-number override was applied by the simulator
  generic          nothing specific was applied; a generic varied sequence was sent

For rule_test_case iterations it also records whether the test-case rule that the
generator resolved is the labeled rule itself.

Run from the repository root:  python3 evaluation/revision/executed_tests.py
Output: evaluation/results/revision/executed_tests.json
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from llm_fuzzer.core.test_generator import TestGenerator  # noqa: E402

HISTORIES = {
    "LLM": ROOT / "llm_fuzzer/data/iteration_history.jsonl",
    "Boofuzz": ROOT / "boofuzz_baseline/data/iteration_history.jsonl",
    "Random": ROOT / "random_baseline/data/iteration_history.jsonl",
}
OUT = ROOT / "evaluation/results/revision/executed_tests.json"
STRATEGY_FIELDS = ("target_vl", "mutation_type", "protocol_rule", "test_cases", "test_mode",
                   "bag_value", "frame_size", "sequence_number", "timing_jitter_ms",
                   "payload_pattern", "mac_mutation_type", "prob", "sequence_number_override",
                   "dest_mac_mutation", "custom_mutation", "strategy")
DIRECT = ("bag_value", "frame_size", "sequence_number", "timing_jitter_ms", "payload_pattern")
RULE_CANDIDATES = ("bag", "sequence_numbers", "sequence_number_field",
                   "virtual_link.id_range", "frame_structure.ethernet")


def resolved_rule(mutation_type):
    """Rule whose test cases TestGenerator._apply_test_cases looks up for a label."""
    for rule in RULE_CANDIDATES:
        if rule.lower() in mutation_type.lower():
            return rule
    return mutation_type.split("_")[0]


def classify(gen, row):
    strategy = {k: row.get(k) for k in STRATEGY_FIELDS}
    strategy["mutation_type"] = strategy["mutation_type"] or strategy["protocol_rule"] or "generic"
    seed = gen._load_seed_frame(strategy["target_vl"])
    tc_frames = gen._apply_test_cases(seed, strategy) if strategy.get("test_cases") else []
    if tc_frames:
        rule = resolved_rule(strategy["mutation_type"])
        return "rule_test_case", rule == row.get("protocol_rule")
    if any(strategy.get(k) is not None for k in DIRECT):
        return "direct_params", None
    if (strategy.get("mac_mutation_type") not in (None, "none")
            or strategy.get("dest_mac_mutation") not in (None, "none")
            or strategy.get("sequence_number_override")):
        return "mac_or_seq_only", None
    return "generic", None


def main():
    gen = TestGenerator(seed_frames_path=str(ROOT / "llm_fuzzer/data/seed_frames.json"),
                        test_cases_path=str(ROOT / "configs/test_cases.json"))
    report = {}
    for name, path in HISTORIES.items():
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        kinds, label_match = Counter(), Counter()
        for row in rows:
            kind, same_rule = classify(gen, row)
            kinds[kind] += 1
            if kind == "rule_test_case":
                label_match["labeled_rule" if same_rule else "other_rule"] += 1
        report[name] = {"iterations": len(rows), "executed": dict(kinds),
                        "rule_test_case_rule": dict(label_match)}
        print(f"{name:8s} {len(rows)} iterations: {dict(kinds)}; test-case rule: {dict(label_match)}")
    OUT.write_text(json.dumps(report, indent=2))
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
