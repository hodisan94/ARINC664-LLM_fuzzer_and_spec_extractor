#!/usr/bin/env python3
"""Checks for the model-based BOOFUZZ baseline (context/BOOFUZZ_MODEL_PLAN.md, step 6).

Usage (from the repository root): python3 -m unittest boofuzz_model_baseline/test_model_baseline.py
Run with an interpreter that has boofuzz installed to also compare against the library.
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from boofuzz_model_baseline.adapter import to_sim_config, unmutated  # noqa: E402
from boofuzz_model_baseline.generator import build_test_list, config_key  # noqa: E402
from boofuzz_model_baseline.model import load_boofuzz_values, load_vls  # noqa: E402

VLS = load_vls()
VERSION, VALUES = load_boofuzz_values()
TESTS, SKIPPED = build_test_list(VLS, VALUES)
MUTABLE = ("prob", "payload_delta_bytes", "timing_jitter_ms", "mac_mutation",
           "sequence_number_override", "dest_mac_mutation")


def independent_bitfield_values(width):
    """boofuzz 0.4.2 BitField rule, rewritten from its source (bit_field.py), not imported.

    Boundaries 0, max/2, max/3, max/4, max/8, max/16, max/32 and max (max = 2**width), sorted;
    around each, the values from 10 below to 9 above that lie strictly between the last value
    produced and max.
    """
    max_num = 2 ** width
    boundaries = sorted([0, max_num // 2, max_num // 3, max_num // 4, max_num // 8,
                         max_num // 16, max_num // 32, max_num])
    values, lower = [], -1
    for b in boundaries:
        for i in range(-10, 10):
            v = b + i
            if lower < v < max_num:
                values.append(v)
                lower = v
    return values


class TestValues(unittest.TestCase):
    def test_version(self):
        self.assertEqual(VERSION, "0.4.2")

    def test_values_follow_boofuzz_rule(self):
        self.assertEqual(VALUES["frame_size"], independent_bitfield_values(16))
        self.assertEqual(VALUES["sequence_number"], independent_bitfield_values(8))
        signed = [v - 256 if v >= 128 else v for v in independent_bitfield_values(8)]
        self.assertEqual(VALUES["timing_offset_ms"], signed)

    def test_values_equal_the_library(self):
        try:
            from boofuzz import BitField, Byte, Word
        except ImportError:
            self.skipTest("boofuzz not installed in this interpreter")
        self.assertEqual(VALUES["frame_size"], list(Word(name="f", default_value=0).mutations(0)))
        self.assertEqual(VALUES["sequence_number"], list(Byte(name="s", default_value=0).mutations(0)))
        raw = list(BitField(name="t", default_value=0, width=8, signed=True).mutations(0))
        self.assertEqual(VALUES["timing_offset_ms"], [v - 256 if v >= 128 else v for v in raw])


class TestAdapter(unittest.TestCase):
    def test_max_frame_plus_one(self):
        # VL 3001: MinFrame 64, MaxFrame 1024, normal frame (64 + 1024) // 2 = 544
        cfg = to_sim_config({"field": "frame_size", "value": 1025}, 3001, VLS)
        self.assertEqual(cfg, {**unmutated(3001), "payload_delta_bytes": 481})

    def test_frame_size_is_clamped_as_the_simulator_does(self):
        self.assertEqual(to_sim_config({"field": "frame_size", "value": 65535}, 3001, VLS)
                         ["payload_delta_bytes"], 9000 - 544)
        self.assertEqual(to_sim_config({"field": "frame_size", "value": 0}, 3001, VLS)
                         ["payload_delta_bytes"], 18 - 544)

    def test_timing_is_floored_at_minus_bag(self):
        self.assertEqual(to_sim_config({"field": "timing_offset_ms", "value": -128}, 1001, VLS)
                         ["timing_jitter_ms"], -4)
        self.assertEqual(to_sim_config({"field": "timing_offset_ms", "value": 127}, 1001, VLS)
                         ["timing_jitter_ms"], 127)

    def test_sequence_zero_is_sent_as_256(self):
        self.assertEqual(to_sim_config({"field": "sequence_number", "value": 0}, 1001, VLS)
                         ["sequence_number_override"], 256)
        self.assertEqual(to_sim_config({"field": "sequence_number", "value": 255}, 1001, VLS)
                         ["sequence_number_override"], 255)

    def test_groups(self):
        self.assertEqual(to_sim_config({"field": "src_mac", "value": "zero_mac"}, 2001, VLS)
                         ["mac_mutation"], "zero_mac")
        self.assertEqual(to_sim_config({"field": "drop_probability", "value": 0.5}, 2001, VLS)
                         ["prob"], 0.5)


class TestList(unittest.TestCase):
    def test_deterministic(self):
        self.assertEqual(build_test_list(VLS, VALUES), (TESTS, SKIPPED))

    def test_one_field_per_test(self):
        for t in TESTS:
            base = unmutated(t["vl"])
            changed = [k for k in MUTABLE if t["sim_config"][k] != base[k]]
            self.assertEqual(len(changed), 1, t)

    def test_no_repeated_or_empty_input(self):
        keys = [config_key(t["sim_config"]) for t in TESTS]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(all(t["sim_config"] != unmutated(t["vl"]) for t in TESTS))

    def test_skipped_tests_are_really_identical(self):
        kept = {config_key(t["sim_config"]) for t in TESTS}
        for s in SKIPPED:
            cfg = to_sim_config(s, s["vl"], VLS)
            self.assertTrue(cfg == unmutated(s["vl"]) or config_key(cfg) in kept, s)

    def test_every_value_is_used_or_skipped(self):
        for field, values in VALUES.items():
            seen = [c["value"] for c in TESTS + SKIPPED
                    if c["field"] == field and c["source"] == "boofuzz"]
            self.assertEqual(sorted(seen, key=str), sorted(values, key=str), field)

    def test_afdx_values_reach_their_own_vl(self):
        # An AFDX value is skipped when boofuzz's own list already sent the same input to that
        # VL (e.g. timing +1), so check the inputs, not where they came from.
        kept = {config_key(t["sim_config"]) for t in TESTS}
        for vl, v in VLS.items():
            for size in (v["min"] - 1, v["min"], v["min"] + 1, v["max"] - 1, v["max"], v["max"] + 1):
                cfg = to_sim_config({"field": "frame_size", "value": size}, vl, VLS)
                self.assertIn(config_key(cfg), kept, (vl, size))
            for offset in (-1, 1):
                cfg = to_sim_config({"field": "timing_offset_ms", "value": offset}, vl, VLS)
                self.assertIn(config_key(cfg), kept, (vl, offset))

    def test_no_rule_labels_or_test_cases(self):
        source = (Path(__file__).resolve().parent / "generator.py").read_text() + \
                 (Path(__file__).resolve().parent / "model.py").read_text()
        self.assertNotIn("test_cases", source)
        self.assertNotIn("spec_rules", source)


if __name__ == "__main__":
    unittest.main()
