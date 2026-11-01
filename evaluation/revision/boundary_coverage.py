#!/usr/bin/env python3
"""Boundary-value coverage of the executed simulator inputs (TAES revision, R2).

Rule Coverage shows which rule categories a fuzzer targeted, not how thoroughly it tested
them. This script measures testing depth with boundary-value analysis (exact points b-1, b,
b+1) and, as a coarser view, equivalence classes (ranges: below, inside, above). The
boundaries come from the configuration of each virtual link (virtual_links.csv: MinFrame,
MaxFrame, BAG) and from the standard (1518-byte Ethernet maximum, 8-bit sequence number), not
from the rule extraction. The class list is fixed in this file and is the same for every
fuzzer and run (context/PAPER_CHANGES.md, 4.8).

Every test of every fuzzer goes through the same function, classify(), which reads only the
logged simulator input ('sim_config'), never the fuzzer type or the rule label. The records
are the ones bdr_replay.py scores (successful iterations); iterations whose input crashed the
simulator in the replay count as not executed, as in analyze_campaigns.py.

For each injected bug, the script also lists which boundary classes the detecting inputs
hit, using the replay cache of bdr_replay.py.

Usage:
  boundary_coverage.py --campaign LLM=runs/stage7/llm_full_r*.jsonl \
      --campaign Random=runs/stage7/random_s*.jsonl ... \
      --cache bdr_replay_cache_stage7.json --out boundary_coverage_stage7.json
No LLM API and no simulator are used.
"""

import argparse
import glob
import json
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "evaluation"))
sys.path.insert(0, str(ROOT / "evaluation" / "revision"))

from compute_bdr import BUGS, bug_detected  # noqa: E402
from bdr_replay import FAILED, config_key, logged_campaign  # noqa: E402
from analyze_campaigns import mann_whitney_exact, summary  # noqa: E402

VL_CONFIG = ROOT / "examples/AFDX_V3/config/virtual_links.csv"
ETHERNET_MAX = 1518                     # IEEE 802.3 maximum frame size
SMALLEST_FRAME, LARGEST_FRAME = 18, 9000  # afdx-demo.cc clamp in fuzz mode (17-byte header + 1)
SEQ_POINTS = (0, 1, 254, 255)           # 8-bit field; 0 is reserved for reset
SRC_MAC = ("spoof_src", "spoof_dst", "broadcast", "invalid_src", "zero_mac")
DST_MAC = ("corrupt_prefix", "wrong_vl", "zero")


def load_vls(path=VL_CONFIG):
    """VL id -> BAG (ms), MinFrame, MaxFrame, parsed as SimulatorRunner._load_vl_configs does."""
    vls = {}
    for line in Path(path).read_text().splitlines():
        parts = line.strip().split(",")
        if not line.strip() or line.startswith("#") or len(parts) < 9:
            continue
        vls[int(parts[0])] = {"bag": int(parts[6]), "max": int(parts[7]), "min": int(parts[8])}
    return vls


def universe(vls):
    """The fixed class lists: (point classes, range classes)."""
    points, ranges = [], []
    for vl, v in sorted(vls.items()):
        for name in ("min", "max"):
            points += [f"size|{vl}|{name}-1", f"size|{vl}|{name}", f"size|{vl}|{name}+1"]
        points += [f"timing|{vl}|bag-1", f"timing|{vl}|bag+1"]
        ranges += [f"size|{vl}|below_min", f"size|{vl}|inside", f"size|{vl}|above_max",
                   f"timing|{vl}|faster", f"timing|{vl}|slower"]
    points += [f"size|eth|{ETHERNET_MAX + d}" for d in (-1, 0, 1)]
    ranges += ["size|eth|above"]
    points += [f"seq|{s}" for s in SEQ_POINTS]
    ranges += ["seq|reserved_0", "seq|1-255"]
    for kind, values in (("src", SRC_MAC), ("dst", DST_MAC)):
        points += [f"{kind}|{m}" for m in values]
        ranges += [f"{kind}|{m}" for m in values]
    return points, ranges


def sent_frame_size(cfg, v):
    """Frame size the generator sends for the target VL (afdx-demo.cc, fuzz mode)."""
    size = (v["min"] + v["max"]) // 2 + int(cfg.get("payload_delta_bytes") or 0)
    return min(max(size, SMALLEST_FRAME), LARGEST_FRAME)


def classify(cfg, vls):
    """Point and range classes hit by one executed simulator input."""
    points, ranges = set(), set()
    vl = cfg.get("vlId")
    v = vls.get(vl)
    if v and cfg.get("payload_delta_bytes"):
        size = sent_frame_size(cfg, v)
        for name in ("min", "max"):
            for off, suffix in ((-1, "-1"), (0, ""), (1, "+1")):
                if size == v[name] + off:
                    points.add(f"size|{vl}|{name}{suffix}")
        if ETHERNET_MAX - 1 <= size <= ETHERNET_MAX + 1:
            points.add(f"size|eth|{size}")
        ranges.add(f"size|{vl}|" + ("below_min" if size < v["min"]
                                    else "above_max" if size > v["max"] else "inside"))
        if size > ETHERNET_MAX:
            ranges.add("size|eth|above")
    # The generator sends the next frame BAG + offset later (at least 100 us).
    jitter = int(cfg.get("timing_jitter_ms") or 0)
    if v and jitter:
        if jitter in (-1, 1):
            points.add(f"timing|{vl}|bag{'+' if jitter > 0 else '-'}1")
        ranges.add(f"timing|{vl}|" + ("faster" if jitter < 0 else "slower"))
    # The simulator applies the override only when it is > 0, and keeps its low 8 bits.
    override = int(cfg.get("sequence_number_override") or 0)
    if override > 0:
        seq = override & 0xFF
        if seq in SEQ_POINTS:
            points.add(f"seq|{seq}")
        ranges.add("seq|reserved_0" if seq == 0 else "seq|1-255")
    for kind, field, values in (("src", "mac_mutation", SRC_MAC),
                                ("dst", "dest_mac_mutation", DST_MAC)):
        if cfg.get(field) in values:
            points.add(f"{kind}|{cfg[field]}")
            ranges.add(f"{kind}|{cfg[field]}")
    return points, ranges


def executed_inputs(path, cache):
    """(iteration, sim_config) of the successful iterations that did not crash in the replay."""
    variants = ["none"] + [b["id"] for b in BUGS]
    records = logged_campaign(path, max_iterations=10**9)
    return [(row.get("iteration"), cfg) for row, cfg in records
            if not any(FAILED in cache.get(f"{bug}|{config_key(cfg)}", {}) for bug in variants)]


def run_metrics(inputs, vls, all_points, all_ranges):
    points, ranges, first_point = set(), set(), {}
    for iteration, cfg in inputs:
        p, r = classify(cfg, vls)
        for c in p - points:
            first_point[c] = iteration
        points |= p
        ranges |= r
    return {"executed_inputs": len(inputs),
            "point_classes": len(points), "point_coverage": len(points) / len(all_points),
            "range_classes": len(ranges), "range_coverage": len(ranges) / len(all_ranges),
            "points": sorted(points), "ranges": sorted(ranges),
            "first_iteration_per_point": first_point}


def per_bug_classes(inputs_by_run, vls, cache):
    """For each bug: how many detecting inputs hit each point class (all runs pooled)."""
    report = {}
    for bug in BUGS:
        hits, detecting, without = Counter(), 0, 0
        for inputs in inputs_by_run.values():
            for _, cfg in inputs:
                key = config_key(cfg)
                ref, buggy = cache.get(f"none|{key}"), cache.get(f"{bug['id']}|{key}")
                if ref is None or buggy is None:
                    raise SystemExit(f"replay cache has no entry for {bug['id']} / {key}")
                if FAILED in ref or FAILED in buggy or not bug_detected(ref, buggy, bug):
                    continue
                detecting += 1
                p, _ = classify(cfg, vls)
                hits.update(p)
                without += not p
        report[bug["id"]] = {"detecting_inputs": detecting,
                             "detecting_inputs_without_point_class": without,
                             "point_classes_of_detecting_inputs": dict(hits.most_common())}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--campaign", action="append", required=True, metavar="NAME=GLOB")
    parser.add_argument("--cache", required=True, help="bdr_replay.py cache of these inputs")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    vls = load_vls()
    all_points, all_ranges = universe(vls)
    print(f"{len(all_points)} point classes, {len(all_ranges)} range classes")
    cache = json.loads(Path(args.cache).read_text())

    per_run, per_fuzzer, inputs_by_run = {}, {}, {}
    for spec in args.campaign:
        name, pattern = spec.split("=", 1)
        paths = sorted(Path(p).as_posix() for p in glob.glob(pattern))
        if not paths:
            raise SystemExit(f"no history matches {pattern}")
        per_run[name] = {}
        for path in paths:
            inputs_by_run[path] = executed_inputs(path, cache)
            per_run[name][path] = run_metrics(inputs_by_run[path], vls, all_points, all_ranges)
        per_fuzzer[name] = {m: summary([r[m] for r in per_run[name].values()])
                            for m in ("point_classes", "range_classes")}

    tests = {}
    for a, b in combinations(per_fuzzer, 2):
        for m in ("point_classes", "range_classes"):
            x, y = per_fuzzer[a][m]["values"], per_fuzzer[b][m]["values"]
            if len(x) > 1 and len(y) > 1:
                tests[f"{a} vs {b}: {m}"] = mann_whitney_exact(x, y)

    report = {"classes": {"points": all_points, "ranges": all_ranges},
              "per_run": per_run, "per_fuzzer": per_fuzzer, "mann_whitney_p": tests,
              "per_bug": per_bug_classes(inputs_by_run, vls, cache)}
    Path(args.out).write_text(json.dumps(report, indent=2))
    for name, s in per_fuzzer.items():
        print(f"{name:8} points {s['point_classes']['values']}  ranges {s['range_classes']['values']}")
    for k, p in tests.items():
        print(f"  p={p:.4f}  {k}")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
