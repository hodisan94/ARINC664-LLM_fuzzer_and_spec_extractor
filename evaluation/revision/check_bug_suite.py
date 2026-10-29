"""Acceptance checks of the injected-bug suite (TAES revision, fix plan stage 5).

Every bug must (a) not be detected by an input without mutation and (b) be detected by at
least one input that the mutation parameters can express, unless it is listed as
unreachable. The inputs below are hand-written probes, one or more per check, on the VLs of
examples/AFDX_V3/config/virtual_links.csv (frame size = midpoint of the VL's range plus
payload_delta_bytes; VL 1001: range 64..512, midpoint 288, BAG 4 ms; VL 3001: range 64..1024,
midpoint 544, BAG 32 ms). The script prints which probes detect which bug and writes the
matrix to --out.

Usage (with AFDX_NS3_PATH pointing at the ns-3 build to check):
  python3 evaluation/revision/check_bug_suite.py --out evaluation/results/revision/bug_suite_checks.json
No LLM API is used.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "evaluation" / "revision"))
sys.path.insert(0, str(ROOT / "evaluation"))
sys.path.insert(0, str(ROOT))

import bdr_replay as br  # noqa: E402
from compute_bdr import BUGS, bug_detected  # noqa: E402

UNREACHABLE = {"skip_token_bucket", "skip_vl_check"}


def probe(vl, **mutation):
    cfg = {"vlId": vl, "prob": 0.0, "payload_delta_bytes": 0, "timing_jitter_ms": 0,
           "mac_mutation": "none", "is_extreme_test": True, "sequence_number_override": 0,
           "dest_mac_mutation": "none"}
    cfg.update(mutation)
    return cfg


PROBES = {
    "no mutation (VL 1001)": probe(1001),
    "no mutation (VL 3001)": probe(3001),
    "frame 1 byte below MinFrame (VL 1001, 63 B)": probe(1001, payload_delta_bytes=-225),
    "frame exactly MaxFrame (VL 1001, 512 B)": probe(1001, payload_delta_bytes=224),
    "frame 1 byte above MaxFrame (VL 1001, 513 B)": probe(1001, payload_delta_bytes=225),
    "frame 2 bytes above MaxFrame (VL 1001, 514 B)": probe(1001, payload_delta_bytes=226),
    "frame above 1518 B (VL 1001, 2000 B)": probe(1001, payload_delta_bytes=1712),
    "send every 3 ms on BAG 4 (VL 1001, jitter -1)": probe(1001, timing_jitter_ms=-1),
    "send every 31 ms on BAG 32 (VL 3001, jitter -1)": probe(3001, timing_jitter_ms=-1),
    "send every 29 ms on BAG 32 (VL 3001, jitter -3)": probe(3001, timing_jitter_ms=-3),
    "send every 28 ms on BAG 32 (VL 3001, jitter -4)": probe(3001, timing_jitter_ms=-4),
    "spoofed source MAC (VL 1001)": probe(1001, mac_mutation="spoof_src"),
    "corrupted MAC prefix (VL 1001)": probe(1001, dest_mac_mutation="corrupt_prefix"),
    "wrong VL bytes in dest MAC (VL 1001)": probe(1001, dest_mac_mutation="wrong_vl"),
    "constant sequence number 255 (VL 1001)": probe(1001, sequence_number_override=255),
    "sequence number 0 (VL 1001)": probe(1001, sequence_number_override=256),
    "512 B frames at BAG 4 (VL 1001, token-bucket stress)": probe(1001, payload_delta_bytes=224),
    "large frames sent fast (VL 1002, +212 B, jitter -5)": probe(1002, payload_delta_bytes=212,
                                                              timing_jitter_ms=-5),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--cache", default=str(br.RESULTS / "bug_suite_checks_cache.json"))
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    pool = br.Pool(args.workers, args.cache)
    keys = {name: br.config_key(cfg) for name, cfg in PROBES.items()}
    pool.run_all([(key, bug) for key in keys.values() for bug in ["none"] + [b["id"] for b in BUGS]])

    matrix, failures = {}, []
    for bug in BUGS:
        hits = {}
        for name, key in keys.items():
            ref, buggy = pool.metrics(key, "none"), pool.metrics(key, bug["id"])
            if br.FAILED in ref or br.FAILED in buggy:
                hits[name] = None
                failures.append((bug["id"], name))
            else:
                hits[name] = bug_detected(ref, buggy, bug)
        clean_detects = any(hits[n] for n in keys if n.startswith("no mutation"))
        some_detects = any(v for n, v in hits.items() if not n.startswith("no mutation"))
        expected_reachable = bug["id"] not in UNREACHABLE
        matrix[bug["id"]] = {
            "detected_by": [n for n, v in hits.items() if v],
            "check_a_not_detected_without_mutation": not clean_detects,
            "check_b_detected_by_some_input": some_detects,
            "listed_unreachable": not expected_reachable,
            "passes": (not clean_detects) and (some_detects == expected_reachable),
        }
        print(f"{bug['id']:22s} a={'ok' if not clean_detects else 'FAIL'} "
              f"b={'ok' if some_detects == expected_reachable else 'FAIL'} "
              f"detected by: {matrix[bug['id']]['detected_by']}")
    clean = {n: pool.metrics(k, "none") for n, k in keys.items()}
    Path(args.out).write_text(json.dumps({"probes": PROBES, "bugs": matrix,
                                          "reference_metrics": clean,
                                          "failed_runs": failures}, indent=2))
    print(f"failed runs: {failures}")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
