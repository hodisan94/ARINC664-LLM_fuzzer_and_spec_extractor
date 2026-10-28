#!/usr/bin/env python3
"""Which simulator mutations can test which rule category? (TAES revision, bug 18)

Executed Rule Coverage counts a label's category when its iteration changed any of the
simulator parameters, even an unrelated one (e.g. a frame-size change under an
ip_header_checksum label). This module assigns each merged rule category
(recompute_coverage_venn.build_single_matcher) the mutation mechanisms of
executed_settings.mechanisms() that can plausibly exercise it, using keyword rules on the
category name. A category whose name matches no rule gets no mechanism: none of the seven
parameters can exercise it (IP/UDP fields, ports, configuration, initialization, ...).

This is an approximation from category names, meant as a reviewable sensitivity measure,
not a ground truth. The full table is written to
evaluation/results/revision/category_mechanisms.json for review.

Usage (from the repository root): python3 evaluation/revision/category_mechanisms.py
No LLM API and no simulator are used.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "evaluation" / "revision"))

import recompute_coverage_venn as rcv  # noqa: E402

OUT = ROOT / "evaluation/results/revision/category_mechanisms.json"

# Categories about fields or functions that no simulator parameter can change.
EXCLUDE = ("ip_", "ipv4", "udp", "transport", "port", "sap", "protocol", "data_encoding",
           "data_format", "data_representation", "data_alignment", "data_structure",
           "message_format", "configuration", "initialization", "operating_mode",
           "operational_mode", "switch_modes", "status", "physical", "interoperability")

# Keyword (substring of the normalized category name) -> mechanisms it can be tested by.
RULES = (
    (("frame_size", "frame_length", "frame_structure", "frame_construction", "frame_formatting",
      "frame_validation", "ethernet_frame", "data_size", "packet_length", "fragmentation",
      "reassembly", "segmentation"), ("frame_size",)),
    (("bag", "bandwidth", "policing", "shaping", "traffic_control", "jitter", "latency",
      "timing", "scheduling", "flow_control"), ("timing",)),
    (("sequence", "ordinal", "integrity", "message_ordering"), ("seq_override", "tx_drop")),
    (("redundancy",), ("seq_override",)),
    (("reliability", "fault"), ("tx_drop",)),
    (("mac", "address", "filtering", "frame_identification", "source_uniqueness",
      "segregation", "partition"), ("src_mac", "dest_mac")),
    (("broadcast",), ("dest_mac",)),
)


def mechanisms_for(category):
    """Mechanisms that can test a normalized category name, and the keywords that matched."""
    if any(x in category for x in EXCLUDE):
        return [], []
    mechs, hits = set(), []
    for keywords, rule_mechs in RULES:
        matched = [k for k in keywords if k in category]
        if matched:
            mechs.update(rule_mechs)
            hits += matched
    return sorted(mechs), hits


def build_table(spec_rules):
    single = rcv.build_single_matcher(spec_rules)
    return {c: dict(zip(("mechanisms", "keywords"), mechanisms_for(c))) for c in single.categories}


def main():
    spec_rules = json.loads((ROOT / "configs/spec_rules_filtered.json").read_text(encoding="utf-8"))
    table = build_table(spec_rules)
    OUT.write_text(json.dumps(table, indent=2))
    testable = sum(bool(v["mechanisms"]) for v in table.values())
    print(f"{len(table)} merged categories, {testable} testable by at least one mechanism "
          f"-> {OUT.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
