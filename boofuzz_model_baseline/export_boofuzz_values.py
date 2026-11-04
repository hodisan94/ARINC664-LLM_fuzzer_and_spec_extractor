#!/usr/bin/env python3
"""Export the test values that the boofuzz library generates for our message fields.

Run once, in an environment where boofuzz is installed (it is not needed to run the baseline):

    python3 -m venv ~/boofuzz_venv && ~/boofuzz_venv/bin/pip install boofuzz==0.4.2
    ~/boofuzz_venv/bin/python boofuzz_model_baseline/export_boofuzz_values.py

Writes boofuzz_model_baseline/boofuzz_values.json. The values come from each primitive's own
mutations() generator, i.e. boofuzz's fuzz library, not from this project. The baseline reads
the JSON, so its run environment does not need boofuzz.

Two properties of boofuzz 0.4.2 found when this was written (2026-11-02):
  * BitField.mutations() yields the raw unsigned numbers also for signed=True fields; the sign
    is applied only when the value is rendered to bytes. This script renders each value and
    reads it back as a signed integer, so the JSON holds the values boofuzz actually sends.
  * The documented fuzz_values option is accepted but not used by BitField.mutations(), so
    tester-defined values (the AFDX limits) are added by model.py, not through boofuzz.
"""

import json
from pathlib import Path

from boofuzz import BitField, Byte, Group, Word
from importlib.metadata import version

OUT = Path(__file__).resolve().parent / "boofuzz_values.json"
# Timing offset field width. 16 bits since 2026-11-04 (RANDOM_MODEL_PLAN 3.2): an 8-bit field
# (-128..127 ms, used in the runs of 2026-11-02) cannot hold offsets the LLM fuzzer sent (+746 ms).
TIMING_WIDTH = 16
VL_CONFIG = Path(__file__).resolve().parents[1] / "examples/AFDX_V3/config/virtual_links.csv"


def max_frame_sizes(path=VL_CONFIG):
    """The distinct MaxFrame values of the network configuration (column 8 of virtual_links.csv)."""
    sizes = set()
    for line in path.read_text().splitlines():
        parts = line.strip().split(",")
        if line.strip() and not line.startswith("#") and len(parts) >= 9:
            sizes.add(int(parts[7]))
    return sorted(sizes)


def signed_values(field):
    """Values of a signed BitField as sent: render each mutation and read it back signed."""
    values = []
    for raw in field.mutations(field.original_value()):
        rendered = field.encode(raw, None)
        signed = int.from_bytes(rendered, byteorder="little" if field.endian == "<" else "big",
                                signed=True)
        half = 2 ** (8 * len(rendered) - 1)
        assert signed == (raw - 2 * half if raw >= half else raw), (raw, rendered)
        values.append(signed)
    return values


def main():
    frame = Word(name="frame_size", default_value=0)
    seq = Byte(name="sequence_number", default_value=0)
    timing = BitField(name="timing_offset_ms", default_value=0, width=TIMING_WIDTH, signed=True)
    src = Group(name="src_mac", default_value="none",
                values=["none", "spoof_src", "spoof_dst", "broadcast", "invalid_src", "zero_mac"])
    dst = Group(name="dst_mac", default_value="none",
                values=["none", "corrupt_prefix", "wrong_vl", "zero"])
    drop = Group(name="drop_probability", default_value="0", values=["0", "0.1", "0.5", "1.0"])

    def group_values(g):
        return [v.decode() if isinstance(v, bytes) else v for v in g.mutations(g.original_value())]

    report = {
        "boofuzz_version": version("boofuzz"),
        "fields": {
            "frame_size": {"primitive": "Word (16-bit unsigned)",
                           "values": list(frame.mutations(frame.original_value()))},
            "timing_offset_ms": {"primitive": f"BitField(width={TIMING_WIDTH}, signed=True)",
                                 "width": TIMING_WIDTH,
                                 "values": signed_values(timing)},
            "sequence_number": {"primitive": "Byte (8-bit unsigned)",
                                "values": list(seq.mutations(seq.original_value()))},
            "src_mac": {"primitive": "Group", "values": group_values(src)},
            "dst_mac": {"primitive": "Group", "values": group_values(dst)},
            "drop_probability": {"primitive": "Group",
                                 "values": [float(v) for v in group_values(drop)]},
        },
        # Configuration variant: the frame-size field of a VL is declared with that VL's maximum
        # (boofuzz's max_num = MaxFrame + 1, i.e. the field holds 0..MaxFrame). boofuzz then builds
        # its boundaries from that maximum; it never generates a value above it.
        "frame_size_by_max_frame": {
            str(m): {"primitive": f"Word(max_num={m + 1})",
                     "values": list(Word(name=f"frame_size_{m}", default_value=0,
                                         max_num=m + 1).mutations(0))}
            for m in max_frame_sizes()},
    }
    OUT.write_text(json.dumps(report, indent=1) + "\n")
    for name, f in list(report["fields"].items()) + [
            (f"frame_size max {m}", f) for m, f in report["frame_size_by_max_frame"].items()]:
        print(f"{name:18} {len(f['values']):4d} values  {f['values'][:6]} ... {f['values'][-3:]}")
    print(f"boofuzz {report['boofuzz_version']} -> {OUT}")


if __name__ == "__main__":
    main()
