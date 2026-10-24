#!/usr/bin/env python3
"""Testing depth per covered rule category (TAES revision, R2-C4).

Rule Coverage counts a category after one executed test. This script reports,
per fuzzer, how many iterations targeted each covered category and how many
distinct mutation-parameter settings were used for it, using the same
label-to-category mapping as recompute_coverage_venn.py.

Usage: python3 evaluation/revision/coverage_depth.py
Output: evaluation/results/revision/coverage_depth.json
"""
import json
import statistics
from collections import defaultdict

from recompute_coverage_venn import HISTORIES, OUT, SPEC_RULES, build_matcher, rule_labels

PARAMS = ("mutation_type", "bag_value", "frame_size", "sequence_number",
          "sequence_number_override", "timing_jitter_ms", "payload_pattern",
          "mac_mutation_type", "dest_mac_mutation", "test_cases")


def main():
    categories_of = build_matcher(json.loads(SPEC_RULES.read_text()))
    report = {"parameters_defining_a_setting": PARAMS, "fuzzers": {}}
    for name, path in HISTORIES.items():
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        iterations, settings = defaultdict(int), defaultdict(set)
        for row, label in zip(rows, rule_labels(rows)):
            setting = json.dumps([row.get(p) for p in PARAMS], sort_keys=True, default=str)
            for cat in categories_of(label):
                iterations[cat] += 1
                settings[cat].add(setting)
        covered = len(iterations)
        multi_iter = sum(1 for c in iterations if iterations[c] >= 2)
        multi_setting = sum(1 for c in settings if len(settings[c]) >= 2)
        report["fuzzers"][name] = {
            "covered_categories": covered,
            "iterations_per_covered_category_mean": round(statistics.mean(iterations.values()), 2),
            "iterations_per_covered_category_median": statistics.median(iterations.values()),
            "iterations_per_covered_category_max": max(iterations.values()),
            "categories_with_2plus_iterations": multi_iter,
            "categories_with_2plus_distinct_settings": multi_setting,
            "pct_categories_with_2plus_distinct_settings": round(100 * multi_setting / covered, 1),
        }
        r = report["fuzzers"][name]
        print(f"{name:16s} covered {covered:3d} | iterations/category mean "
              f"{r['iterations_per_covered_category_mean']} median "
              f"{r['iterations_per_covered_category_median']} | >=2 distinct settings "
              f"{multi_setting} ({r['pct_categories_with_2plus_distinct_settings']}%)")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "coverage_depth.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
