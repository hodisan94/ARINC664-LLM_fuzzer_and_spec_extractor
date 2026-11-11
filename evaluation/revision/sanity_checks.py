#!/usr/bin/env python3
"""
End-to-end sanity checks of the simulator, run before the campaigns.

1. A run with no effective mutation drops and rejects nothing.
2. Each mutation changes the counter it is meant to change.
3. Each injected bug is detected (compute_bdr.bug_detected) by a targeted input.
4. The same input gives the same counters twice.

Usage:  python3 evaluation/revision/sanity_checks.py [--jobs 8]
Exit code 0 when every check passes.
"""

import argparse
import json
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evaluation"))

from llm_fuzzer.utils.simulator_runner import SimulatorRunner  # noqa: E402
from llm_fuzzer.utils.log_parser import SimulatorLogParser  # noqa: E402
from compute_bdr import BUGS, bug_detected  # noqa: E402

DROP_KEYS = ("frames_dropped_policing", "frames_dropped_frame_error",
             "frames_dropped_mac_error", "frames_dropped_invalid_vl", "es_frames_rejected")


def config(vl=1001, **metadata):
    """Simulator input as produced by SimulatorRunner._translate_to_cpp_format."""
    runner = SimulatorRunner(skip_ns3_check=True)
    return runner._translate_to_cpp_format({"vl_id": vl, "metadata": metadata})


# name -> (simulator input, check on the metrics, description)
MUTATION_CASES = {
    "noop":               (config(), lambda m: all(m[k] == 0 for k in DROP_KEYS),
                           "no drops and no rejections"),
    "bag_fast":           (config(bag_value=1), lambda m: m["frames_dropped_policing"] > 0,
                           "BAG 1 ms on a 4 ms VL is policed"),
    "jitter_fast":        (config(timing_jitter_ms=-2), lambda m: m["frames_dropped_policing"] > 0,
                           "-2 ms offset on a 4 ms VL is policed"),
    "jitter_slow":        (config(timing_jitter_ms=4), lambda m: all(m[k] == 0 for k in DROP_KEYS),
                           "+4 ms offset is legal (slower than BAG)"),
    "size_valid":         (config(frame_size=300), lambda m: all(m[k] == 0 for k in DROP_KEYS),
                           "300 B on a 64..512 B VL is accepted"),
    "size_above_vl_max":  (config(frame_size=600), lambda m: m["frames_dropped_frame_error"] > 0,
                           "600 B on a 512 B VL is a frame error"),
    "size_oversized":     (config(frame_size=2000), lambda m: m["frames_dropped_frame_error"] > 0,
                           "2000 B is a frame error"),
    "size_zero":          (config(frame_size=0), lambda m: m["frames_dropped_frame_error"] > 0,
                           "frame_size 0 (clamped to the 17 B header) is a frame error"),
    "mac_spoof_src":      (config(mac_mutation_type="spoof_src"), lambda m: m["frames_dropped_mac_error"] > 0,
                           "spoofed source MAC is dropped by the switch"),
    "dest_corrupt":       (config(dest_mac_mutation="corrupt_prefix"), lambda m: m["es_frames_rejected"] > 0,
                           "corrupted constant field is rejected by the end systems"),
    "seq_constant_255":   (config(sequence_number_override=255), lambda m: m["es_frames_rejected"] > 0,
                           "constant sequence number 255 fails integrity checking"),
    "seq_zero":           (config(sequence_number_override=0), lambda m: m["es_frames_rejected"] == 0,
                           "sequence number 0 is always accepted (ARINC 664 P7 3.2.6.2.1)"),
    "vl_impersonation":   (config(vl_id_override=3001), lambda m: m["frames_dropped_invalid_vl"] > 0,
                           "VL 1001 frames carrying VL 3001 arrive on ES1's port and are dropped"),
    "vl_same_es":         (config(vl_id_override=1002),
                           lambda m: m["frames_dropped_invalid_vl"] == 0 and m["frames_dropped_policing"] > 0,
                           "VL 1001 carrying VL 1002 (same port) passes the VL check; VL 1002 then exceeds its BAG"),
    "tx_drop":            (config(prob=0.5), lambda m: m["mutation_tx_prob_drops"] > 0,
                           "sender drops frames with probability 0.5"),
}

# bug -> targeted input
BUG_INPUTS = {
    "skip_bag_policing": config(bag_value=1),
    "skip_frame_validation": config(frame_size=40),
    "skip_mac_validation": config(mac_mutation_type="spoof_src"),
    # Maximum-size frames (VL 1001: 512 B) sent as fast as possible: frames that the BAG
    # check lets through within its tolerance exceed the token bucket.
    "skip_token_bucket": config(frame_size=512, bag_value=0),
    "skip_vl_check": config(vl_id_override=3001),
    "skip_constant_field": config(dest_mac_mutation="corrupt_prefix"),
    "skip_sequence_check": config(sequence_number_override=255),
    "accept_oversized": config(frame_size=2000),
}


def metrics_of(result):
    if not result.get("success"):
        return None
    m = SimulatorLogParser(log_content=result["log_content"], csv_content=result.get("csv_content", "")).parse()
    m.setdefault("mutation_tx_prob_drops", 0)
    return m


def run_all(jobs):
    tasks = {}
    for name, (cfg, _, _) in MUTATION_CASES.items():
        tasks[("mut", name)] = cfg
    tasks[("mut", "noop_repeat")] = MUTATION_CASES["noop"][0]
    tasks[("mut", "bag_fast_repeat")] = MUTATION_CASES["bag_fast"][0]
    for bug, cfg in BUG_INPUTS.items():
        tasks[("ref", bug)] = cfg
        tasks[("bug", bug)] = dict(cfg, inject_bug=bug)

    tmp = Path(tempfile.mkdtemp(prefix="afdx_sanity_"))

    def run(item):
        (kind, name), cfg = item
        runner = SimulatorRunner(work_dir=str(tmp / f"{kind}_{name}"))
        return (kind, name), metrics_of(runner.run_simulation(sim_config=cfg, timeout=180))

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        return dict(pool.map(run, tasks.items()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--out", default=str(ROOT / "evaluation/revision/out/sanity_checks.json"))
    args = ap.parse_args()

    res = run_all(args.jobs)
    report, ok = {"mutations": {}, "bugs": {}, "determinism": {}}, True

    print("Mutations")
    for name, (cfg, check, desc) in MUTATION_CASES.items():
        m = res[("mut", name)]
        passed = m is not None and check(m)
        ok &= passed
        counters = {k: m[k] for k in ("frames_received", "frames_forwarded", *DROP_KEYS)} if m else None
        report["mutations"][name] = {"input": cfg, "expect": desc, "passed": passed, "counters": counters}
        print(f"  [{'PASS' if passed else 'FAIL'}] {name:18s} {desc}\n         {counters}")

    print("Bugs (targeted input, reference vs buggy)")
    for bug in BUGS:
        ref, buggy = res[("ref", bug["id"])], res[("bug", bug["id"])]
        detected = bool(ref and buggy and bug_detected(ref, buggy, bug))
        report["bugs"][bug["id"]] = {"input": BUG_INPUTS[bug["id"]], "signal": bug["detection_signal"],
                                     "detected": detected}
        ok &= detected
        print(f"  [{'DETECTED' if detected else 'NOT DETECTED'}] {bug['id']} ({bug['detection_signal']})")

    print("Determinism")
    for name in ("noop", "bag_fast"):
        a, b = res[("mut", name)], res[("mut", f"{name}_repeat")]
        same = a is not None and b is not None and all(a[k] == b[k] for k in ("frames_received", *DROP_KEYS))
        ok &= same
        report["determinism"][name] = same
        print(f"  [{'PASS' if same else 'FAIL'}] {name} twice gives the same counters")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(f"\n{'ALL CHECKS PASSED' if ok else 'SOME CHECKS FAILED'} -> {out}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
