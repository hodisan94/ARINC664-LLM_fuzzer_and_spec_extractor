#!/usr/bin/env python3
"""Turn one test case of the model into the simulator input (context/BOOFUZZ_MODEL_PLAN.md, step 5).

The simulator reads 9 keys (the format of SimulatorRunner._translate_to_cpp_format). One field
is mutated; every other key keeps the value that means "no change".

Three adaptations, each matching what the simulator does with the value anyway:
  * Frame size: the sender clamps a frame to 18..9000 bytes (afdx-demo.cc, fuzz mode), so the
    requested size is clamped here first. The logged input then shows the size actually sent,
    and requests that send the same frame are recognized as the same test.
  * Timing: the next frame is sent BAG - |offset| later, but at least 100 us later
    (afdx-traffic-generator.cc, FuzzedSendInterval), so every offset <= -BAG sends at 100 us;
    the offset is floored at -BAG here.
  * Sequence number 0: an override of 0 means "no change" in the simulator, which keeps only
    the low 8 bits of the override, so 0 is sent as 256 (REVISION_FINDINGS Bug 31; no
    simulator change, decision D4).
"""

SMALLEST_FRAME, LARGEST_FRAME = 18, 9000


def unmutated(vl):
    return {"vlId": vl, "prob": 0.0, "payload_delta_bytes": 0, "timing_jitter_ms": 0,
            "mac_mutation": "none", "is_extreme_test": True, "sequence_number_override": 0,
            "dest_mac_mutation": "none", "inject_bug": "none"}


def to_sim_config(case, vl, vls):
    """Simulator input of one test case (one mutated field) on VL vl."""
    return fields_to_sim_config({case["field"]: case["value"]}, vl, vls)


def fields_to_sim_config(values, vl, vls):
    """Simulator input with several fields mutated at once ({field: value}) on VL vl.

    Used by the model-based random baseline (random_model_baseline/), which mutates a random set
    of fields per test; each field is translated exactly as for a single mutation.
    """
    v = vls[vl]
    cfg = unmutated(vl)
    for field, value in values.items():
        if field == "frame_size":
            sent = min(max(int(value), SMALLEST_FRAME), LARGEST_FRAME)
            cfg["payload_delta_bytes"] = sent - (v["min"] + v["max"]) // 2
        elif field == "timing_offset_ms":
            cfg["timing_jitter_ms"] = max(int(value), -v["bag"])
        elif field == "sequence_number":
            cfg["sequence_number_override"] = 256 if int(value) == 0 else int(value)
        elif field == "src_mac":
            cfg["mac_mutation"] = value
        elif field == "dst_mac":
            cfg["dest_mac_mutation"] = value
        elif field == "drop_probability":
            cfg["prob"] = float(value)
        else:
            raise ValueError(f"unknown field {field}")
    return cfg
