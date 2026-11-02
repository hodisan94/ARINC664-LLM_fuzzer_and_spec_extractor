#!/usr/bin/env python3
"""The fixed test list of the model-based BOOFUZZ baseline (context/BOOFUZZ_MODEL_PLAN.md, step 4).

Kept from boofuzz: each test mutates exactly one field, the others keep their defaults; the
values are boofuzz's (plus the AFDX limits, decision D1); the order is fixed; nothing is
learned from results.

Adapted to the 200-test budget (boofuzz itself would exhaust the first field before moving on):
  1. the fields take turns: frame size, timing, sequence number, source MAC, destination MAC,
     drop probability, then frame size again; an exhausted field leaves the rotation;
  2. inside a field, one value from each boundary window in turn (ascending inside a window,
     as boofuzz orders them), so the budget reaches every boundary;
  3. an AFDX value is sent on its own VL; every other value on the next VL of the rotation
     1001 ... 3002 (the rotation moves on only when a test is kept);
  4. a test whose simulator input equals an earlier one, or the unmutated input, is skipped.
     The skipped tests are counted.
"""

import json

from boofuzz_model_baseline.adapter import to_sim_config, unmutated
from boofuzz_model_baseline.model import (FIELDS, field_groups, field_sequence, load_boofuzz_values,
                                          load_vls)


def config_key(cfg):
    return json.dumps({k: v for k, v in cfg.items() if k != "inject_bug"}, sort_keys=True)


def build_test_list(vls=None, boofuzz_values=None):
    """All tests in order, and the skipped ones with the reason."""
    vls = vls or load_vls()
    if boofuzz_values is None:
        _, boofuzz_values = load_boofuzz_values()
    groups = field_groups(boofuzz_values, vls)
    queues = {f: field_sequence(groups[f]) for f in FIELDS}
    vl_order = sorted(vls)
    next_vl = 0
    seen = {config_key(unmutated(vl)) for vl in vls}
    tests, skipped = [], []
    while any(queues.values()):
        for field in FIELDS:
            if not queues[field]:
                continue
            c = queues[field].pop(0)
            vl = c["vl"] if c["vl"] is not None else vl_order[next_vl % len(vl_order)]
            cfg = to_sim_config(c, vl, vls)
            key = config_key(cfg)
            if key in seen:
                reason = "no change" if cfg == unmutated(vl) else "same input as an earlier test"
                skipped.append({**c, "vl": vl, "reason": reason})
                continue
            seen.add(key)
            if c["vl"] is None:
                next_vl += 1
            tests.append({**c, "vl": vl, "sim_config": cfg})
    return tests, skipped


if __name__ == "__main__":
    from collections import Counter
    tests, skipped = build_test_list()
    print(f"{len(tests)} tests, {len(skipped)} skipped ({dict(Counter(s['reason'] for s in skipped))})")
    print("fields in the first 200:", dict(Counter(t["field"] for t in tests[:200])))
    print("AFDX values in the first 200:", sum(t["source"] == "afdx" for t in tests[:200]))
    for t in tests[:14]:
        print(f"  {t['field']:17} {str(t['value']):12} VL {t['vl']}  {t['group']}")
