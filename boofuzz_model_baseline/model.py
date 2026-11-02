#!/usr/bin/env python3
"""The message model of the model-based BOOFUZZ baseline (context/BOOFUZZ_MODEL_PLAN.md, step 3).

One message whose fields are the inputs the simulator accepts. Each field has a boofuzz type and
a default meaning "no change". The test values of every field are boofuzz's own
(boofuzz_values.json, written by export_boofuzz_values.py from the boofuzz library). The tester's
own values are the AFDX limits of each VL (decision D1): boofuzz documents such additions
(fuzz_values) but 0.4.2 does not apply them to integer fields, so they are added here.

No test-case list and no rule list is used.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALUES = Path(__file__).resolve().parent / "boofuzz_values.json"
VL_CONFIG = ROOT / "examples/AFDX_V3/config/virtual_links.csv"
ETHERNET_MAX = 1518

# Rotation order of the fields (step 4)
FIELDS = ("frame_size", "timing_offset_ms", "sequence_number", "src_mac", "dst_mac",
          "drop_probability")


def load_vls(path=VL_CONFIG):
    """VL id -> BAG (ms), MinFrame, MaxFrame, parsed as SimulatorRunner._load_vl_configs does."""
    vls = {}
    for line in Path(path).read_text().splitlines():
        parts = line.strip().split(",")
        if not line.strip() or line.startswith("#") or len(parts) < 9:
            continue
        vls[int(parts[0])] = {"bag": int(parts[6]), "max": int(parts[7]), "min": int(parts[8])}
    return vls


def load_boofuzz_values(path=VALUES):
    data = json.loads(Path(path).read_text())
    return data["boofuzz_version"], {f: v["values"] for f, v in data["fields"].items()}


def windows(values, modulus=None):
    """Split boofuzz's value list into its boundary windows: runs of consecutive values.

    boofuzz builds each integer list from boundaries (0, max, max/2, max/3, ...) and the values
    around each one, in ascending order, so a window is a run of consecutive numbers. For a
    signed field the list follows the raw unsigned order (127 is followed by -128), hence
    the modulus.
    """
    def consecutive(a, b):
        return (b - a) % modulus == 1 if modulus else b - a == 1

    groups, current = [], []
    for v in values:
        if current and not consecutive(current[-1], v):
            groups.append(current)
            current = []
        current.append(v)
    if current:
        groups.append(current)
    return groups


def case(field, value, source, group, vl=None):
    """One test case: one mutated field. vl=None means the next VL in the rotation."""
    return {"field": field, "value": value, "source": source, "group": group, "vl": vl}


def field_groups(boofuzz_values, vls, afdx=True):
    """Field -> list of value groups (each a list of cases), boofuzz's first, then the AFDX ones.

    afdx=False leaves out the tester's AFDX values: boofuzz's own values only.
    """
    groups = {}
    frame = [[case("frame_size", v, "boofuzz", f"boofuzz {w[0]}..{w[-1]}") for v in w]
             for w in windows(boofuzz_values["frame_size"])]
    if afdx:
        for vl, v in sorted(vls.items()):
            for name in ("min", "max"):
                b = v[name]
                frame.append([case("frame_size", b + d, "afdx", f"VL {vl} {name.capitalize()}Frame", vl)
                              for d in (-1, 0, 1)])
        frame.append([case("frame_size", ETHERNET_MAX + d, "afdx", "Ethernet maximum")
                      for d in (-1, 0, 1)])
    groups["frame_size"] = frame

    timing = [[case("timing_offset_ms", v, "boofuzz", f"boofuzz {w[0]}..{w[-1]}") for v in w]
              for w in windows(boofuzz_values["timing_offset_ms"], modulus=256)]
    if afdx:
        for vl, v in sorted(vls.items()):
            timing.append([case("timing_offset_ms", d, "afdx", f"VL {vl} BAG", vl) for d in (-1, 1)])
    groups["timing_offset_ms"] = timing

    groups["sequence_number"] = [
        [case("sequence_number", v, "boofuzz", f"boofuzz {w[0]}..{w[-1]}") for v in w]
        for w in windows(boofuzz_values["sequence_number"])]
    for field in ("src_mac", "dst_mac", "drop_probability"):
        groups[field] = [[case(field, v, "boofuzz", "boofuzz group") for v in boofuzz_values[field]]]
    return groups


def field_sequence(groups):
    """Order the cases of one field: one value from each group in turn, ascending inside a group."""
    queues = [list(g) for g in groups]
    ordered = []
    while any(queues):
        for q in queues:
            if q:
                ordered.append(q.pop(0))
    return ordered
