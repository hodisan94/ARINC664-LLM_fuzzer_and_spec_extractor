#!/usr/bin/env python3
"""Hand-checked cases for boundary_coverage.classify().

VL 3001 in virtual_links.csv: BAG 32 ms, MinFrame 64, MaxFrame 1024, so the unmutated
frame is (64 + 1024) // 2 = 544 bytes.

Usage (from the repository root): python3 -m unittest evaluation/revision/test_boundary_coverage.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import boundary_coverage as bc  # noqa: E402

VLS = bc.load_vls()


def cfg(**fields):
    base = {"vlId": 3001, "prob": 0.0, "payload_delta_bytes": 0, "timing_jitter_ms": 0,
            "mac_mutation": "none", "is_extreme_test": True, "sequence_number_override": 0,
            "dest_mac_mutation": "none", "inject_bug": "none"}
    base.update(fields)
    return base


class TestClassify(unittest.TestCase):
    def test_vl_table(self):
        self.assertEqual(VLS[3001], {"bag": 32, "max": 1024, "min": 64})
        self.assertEqual(len(VLS), 8)

    def test_universe_sizes(self):
        points, ranges = bc.universe(VLS)
        self.assertEqual(len(points), 79)
        self.assertEqual(len(ranges), 51)
        self.assertEqual(len(set(points)), 79)

    def test_unmutated_input_hits_nothing(self):
        self.assertEqual(bc.classify(cfg(), VLS), (set(), set()))

    def test_frame_size_points(self):
        cases = {480: "size|3001|max", 481: "size|3001|max+1", 479: "size|3001|max-1",
                 -480: "size|3001|min", -481: "size|3001|min-1", -479: "size|3001|min+1"}
        for delta, expected in cases.items():
            points, _ = bc.classify(cfg(payload_delta_bytes=delta), VLS)
            self.assertEqual(points, {expected}, delta)

    def test_frame_size_ranges(self):
        self.assertEqual(bc.classify(cfg(payload_delta_bytes=100), VLS),
                         (set(), {"size|3001|inside"}))
        self.assertEqual(bc.classify(cfg(payload_delta_bytes=2000), VLS)[1],
                         {"size|3001|above_max", "size|eth|above"})
        # 544 - 1000 is clamped to the smallest frame, 18 bytes: below MinFrame
        self.assertEqual(bc.classify(cfg(payload_delta_bytes=-1000), VLS),
                         (set(), {"size|3001|below_min"}))

    def test_ethernet_points(self):
        points, ranges = bc.classify(cfg(payload_delta_bytes=1518 - 544), VLS)
        self.assertEqual(points, {"size|eth|1518"})
        self.assertEqual(ranges, {"size|3001|above_max"})
        points, ranges = bc.classify(cfg(payload_delta_bytes=1519 - 544), VLS)
        self.assertEqual(points, {"size|eth|1519"})
        self.assertIn("size|eth|above", ranges)

    def test_boundaries_follow_the_target_vl(self):
        # VL 2001: MaxFrame 256, base (64 + 256) // 2 = 160, so +97 sends 257 = MaxFrame+1
        points, _ = bc.classify(cfg(vlId=2001, payload_delta_bytes=97), VLS)
        self.assertEqual(points, {"size|2001|max+1"})

    def test_timing(self):
        self.assertEqual(bc.classify(cfg(timing_jitter_ms=-1), VLS),
                         ({"timing|3001|bag-1"}, {"timing|3001|faster"}))
        self.assertEqual(bc.classify(cfg(timing_jitter_ms=1), VLS),
                         ({"timing|3001|bag+1"}, {"timing|3001|slower"}))
        self.assertEqual(bc.classify(cfg(timing_jitter_ms=-15), VLS),
                         (set(), {"timing|3001|faster"}))

    def test_sequence_number(self):
        self.assertEqual(bc.classify(cfg(sequence_number_override=255), VLS),
                         ({"seq|255"}, {"seq|1-255"}))
        # 256 keeps its low 8 bits: the simulator sends 0
        self.assertEqual(bc.classify(cfg(sequence_number_override=256), VLS),
                         ({"seq|0"}, {"seq|reserved_0"}))
        # 0 means "no override" in the simulator
        self.assertEqual(bc.classify(cfg(sequence_number_override=0), VLS), (set(), set()))
        self.assertEqual(bc.classify(cfg(sequence_number_override=100), VLS),
                         (set(), {"seq|1-255"}))

    def test_addresses(self):
        points, ranges = bc.classify(cfg(mac_mutation="spoof_src", dest_mac_mutation="wrong_vl"), VLS)
        self.assertEqual(points, {"src|spoof_src", "dst|wrong_vl"})
        self.assertEqual(points, ranges)

    def test_ignores_everything_but_the_simulator_input(self):
        with_extra = cfg(timing_jitter_ms=-1)
        with_extra.update({"fuzzer_type": "random", "protocol_rule": "Frame Validation.x"})
        self.assertEqual(bc.classify(with_extra, VLS), bc.classify(cfg(timing_jitter_ms=-1), VLS))

    def test_combined_input(self):
        points, ranges = bc.classify(cfg(payload_delta_bytes=481, timing_jitter_ms=-1,
                                         sequence_number_override=1), VLS)
        self.assertEqual(points, {"size|3001|max+1", "timing|3001|bag-1", "seq|1"})
        self.assertEqual(ranges, {"size|3001|above_max", "timing|3001|faster", "seq|1-255"})


if __name__ == "__main__":
    unittest.main()
