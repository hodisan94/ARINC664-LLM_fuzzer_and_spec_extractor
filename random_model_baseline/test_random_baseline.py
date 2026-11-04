#!/usr/bin/env python3
"""Checks for the model-based random baseline (context/RANDOM_MODEL_PLAN.md, step 3).

Usage (from the repository root): python3 -m unittest random_model_baseline/test_random_baseline.py
"""

import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from boofuzz_model_baseline.adapter import fields_to_sim_config, to_sim_config, unmutated  # noqa: E402
from boofuzz_model_baseline.model import FIELDS, load_vls  # noqa: E402
from random_model_baseline.generator import (DST_MAC, RANGES, SRC_MAC, build_test_list,  # noqa: E402
                                             draw_test)

VLS = load_vls()
MANY = build_test_list(seed=7, n=6000, vls=VLS)
FIELD_KEY = {"frame_size": "payload_delta_bytes", "timing_offset_ms": "timing_jitter_ms",
             "sequence_number": "sequence_number_override", "src_mac": "mac_mutation",
             "dst_mac": "dest_mac_mutation", "drop_probability": "prob"}


class TestGenerator(unittest.TestCase):
    def test_reproducible_and_seed_dependent(self):
        self.assertEqual(build_test_list(1, 50, VLS), build_test_list(1, 50, VLS))
        self.assertNotEqual(build_test_list(1, 50, VLS), build_test_list(2, 50, VLS))

    def test_test_i_does_not_depend_on_budget(self):
        # reseeded per test as in Peach, so a resume or a longer run repeats the same tests
        self.assertEqual(build_test_list(3, 200, VLS)[:20], build_test_list(3, 20, VLS))
        self.assertEqual(draw_test(3, 150, VLS), build_test_list(3, 200, VLS)[150])

    def test_values_in_range(self):
        for t in MANY:
            for f, v in t["values"].items():
                if f in RANGES:
                    lo, hi = RANGES[f]
                    self.assertTrue(lo <= v <= hi, (f, v))
                elif f == "src_mac":
                    self.assertIn(v, SRC_MAC)
                elif f == "dst_mac":
                    self.assertIn(v, DST_MAC)
                else:
                    self.assertTrue(0.0 < v <= 1.0, v)

    def test_only_the_drawn_fields_are_mutated(self):
        for t in MANY[:1000]:
            self.assertGreaterEqual(len(t["values"]), 1)
            base = unmutated(t["vl"])
            changed = {k for k in FIELD_KEY.values() if t["sim_config"][k] != base[k]}
            # a drawn field can land on its "no change" value (e.g. timing 0), never the reverse
            self.assertLessEqual(changed, {FIELD_KEY[f] for f in t["values"]}, t)

    def test_peach_rule_distribution(self):
        # number of fields uniform over 1..6; each field in about 7/12 of the tests
        counts = Counter(len(t["values"]) for t in MANY)
        self.assertEqual(sorted(counts), [1, 2, 3, 4, 5, 6])
        for k in range(1, 7):
            self.assertAlmostEqual(counts[k] / len(MANY), 1 / 6, delta=0.02)
        for f in FIELDS:
            share = sum(f in t["values"] for t in MANY) / len(MANY)
            self.assertAlmostEqual(share, 7 / 12, delta=0.03, msg=f)
        for vl in VLS:
            share = sum(t["vl"] == vl for t in MANY) / len(MANY)
            self.assertAlmostEqual(share, 1 / len(VLS), delta=0.02, msg=vl)

    def test_values_spread_over_the_whole_range(self):
        sizes = [t["values"]["frame_size"] for t in MANY if "frame_size" in t["values"]]
        self.assertAlmostEqual(sum(s > 32767 for s in sizes) / len(sizes), 0.5, delta=0.05)
        offsets = [t["values"]["timing_offset_ms"] for t in MANY if "timing_offset_ms" in t["values"]]
        self.assertAlmostEqual(sum(o < 0 for o in offsets) / len(offsets), 0.5, delta=0.05)

    def test_adapter_handles_several_fields_like_single_ones(self):
        values = {"frame_size": 1025, "timing_offset_ms": -1, "sequence_number": 0,
                  "dst_mac": "zero"}
        cfg = fields_to_sim_config(values, 3001, VLS)
        for f, v in values.items():
            single = to_sim_config({"field": f, "value": v}, 3001, VLS)
            self.assertEqual(cfg[FIELD_KEY[f]], single[FIELD_KEY[f]], f)
        self.assertEqual(cfg["payload_delta_bytes"], 481)
        self.assertEqual(cfg["sequence_number_override"], 256)

    def test_no_test_cases_or_rules(self):
        source = (Path(__file__).resolve().parent / "generator.py").read_text()
        self.assertNotIn("test_cases", source)
        self.assertNotIn("spec_rules", source)


if __name__ == "__main__":
    unittest.main()
