#!/usr/bin/env python3
"""Tests of the model-based random baseline (context/RANDOM_MODEL_PLAN.md, section 3).

The fields are those of the model-based BOOFUZZ baseline (boofuzz_model_baseline/model.py), and
each test is turned into the simulator input by the same adapter. No test-case list, no rule
list and no rule labels are used, and the VL table is used only to send each test to an
existing VL.

Each test, as Peach Fuzzer 2.x's RandomMutationStrategy (Peach/MutateStrategies/rand.py) does
for a data model with no more fields than maxFieldsToMutate (default 7):
  1. a VL, uniformly among the configured VLs;
  2. a number k uniformly from 1..min(7, number of fields), then k fields uniformly without
     replacement;
  3. for each chosen field, a value uniformly from the field's full range (RANGES).
As in Peach, the generator is reseeded for every test from the seed and the test number
(sha512), so test i is the same whatever the budget or a resume.
"""

import hashlib
import random

from boofuzz_model_baseline.adapter import fields_to_sim_config
from boofuzz_model_baseline.model import FIELDS, load_vls

MAX_FIELDS_TO_MUTATE = 7  # Peach's default maxFieldsToMutate
SRC_MAC = ("spoof_src", "spoof_dst", "broadcast", "invalid_src", "zero_mac")
DST_MAC = ("corrupt_prefix", "wrong_vl", "zero")
# Full range of each field (RANDOM_MODEL_PLAN 3.1): frame size as a 16-bit field, timing as a
# signed 16-bit field (3.2), sequence number as the protocol's 8-bit field.
RANGES = {
    "frame_size": (0, 65535),
    "timing_offset_ms": (-32768, 32767),
    "sequence_number": (0, 255),
}


def test_rng(seed, i):
    """The generator of test i, reseeded as Peach does: sha512 of the seed and the test number."""
    return random.Random(hashlib.sha512(f"{seed}{i}".encode()).digest())


def draw_value(rng, field):
    if field in RANGES:
        return rng.randint(*RANGES[field])
    if field == "src_mac":
        return rng.choice(SRC_MAC)
    if field == "dst_mac":
        return rng.choice(DST_MAC)
    if field == "drop_probability":
        return 1.0 - rng.random()  # uniform in (0, 1]
    raise ValueError(f"unknown field {field}")


def draw_test(seed, i, vls):
    rng = test_rng(seed, i)
    vl = rng.choice(sorted(vls))
    k = rng.randint(1, min(MAX_FIELDS_TO_MUTATE, len(FIELDS)))
    chosen = rng.sample(FIELDS, k)
    values = {f: draw_value(rng, f) for f in FIELDS if f in chosen}
    return {"vl": vl, "values": values, "sim_config": fields_to_sim_config(values, vl, vls)}


def build_test_list(seed, n, vls=None):
    vls = vls or load_vls()
    return [draw_test(seed, i, vls) for i in range(n)]


if __name__ == "__main__":
    from collections import Counter
    tests = build_test_list(1, 200)
    print("fields per test:", dict(sorted(Counter(len(t["values"]) for t in tests).items())))
    print("field shares:", {f: sum(f in t["values"] for t in tests) for f in FIELDS})
    for t in tests[:5]:
        print(f"  VL {t['vl']}  {t['values']}")
