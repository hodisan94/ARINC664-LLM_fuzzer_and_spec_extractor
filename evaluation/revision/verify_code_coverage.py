#!/usr/bin/env python3
"""Two further checks that the code-coverage numbers count what really ran
(context/EVALUATION_METRICS.md, section 3.6b).

Check A, known answer. Three inputs on VL 1001, each measured alone:
  - normal traffic (no change);
  - frame size exactly MaxFrame (still allowed);
  - frame size MaxFrame + 1 (one byte over the limit).
The switch line that rejects a frame outside the VL's size range must run 0 times in the first
two and more than 0 times in the third. Its execution count is printed next to the simulator's
own frame-error drop counter.

Check B, a second tool. The counters of a 24-input run are read twice: by gcovr (the tool
code_coverage.py uses) and by GCC's own gcov command (gcov --json-format). Lines are merged per
source file across object files the way gcovr does (a line is covered if any object file ran
it). The covered and total line counts of the AFDX files must agree.

Usage (from the repository root, in WSL):
  AFDX_NS3_PATH=/tmp/ns3_cov python3 evaluation/revision/verify_code_coverage.py \
      --gcovr ~/cov_venv/bin/gcovr --out evaluation/results/revision/code_coverage_checks.json
No LLM API is used.
"""

import argparse
import gzip
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evaluation"))
sys.path.insert(0, str(ROOT / "evaluation" / "revision"))

import code_coverage as cc  # noqa: E402
from bdr_replay import config_key, logged_campaign  # noqa: E402
from boundary_coverage import load_vls  # noqa: E402
from compute_bdr import parse_metrics  # noqa: E402
from llm_fuzzer.utils.simulator_runner import SimulatorRunner  # noqa: E402

HISTORY = ROOT / "evaluation/results/revision/runs/stage7/llm_full_r1.jsonl"
SWITCH = "examples/AFDX_V3/model/afdx-switch.cc"
VL = 1001


def reject_line(ns3):
    """Line number of 'return false;' after the VL size-range warning in afdx-switch.cc."""
    lines = (Path(ns3) / SWITCH).read_text().splitlines()
    warn = next(i for i, l in enumerate(lines) if '" out of range ["' in l)
    return next(i for i in range(warn, len(lines)) if lines[i].strip() == "return false;") + 1


def gcovr_lines(ns3, gcovr):
    """{file: {line: count}} of the AFDX code from gcovr's detailed JSON."""
    out = subprocess.run([gcovr, "--root", str(ns3), "--filter", cc.FILTER, "--json", "-", str(ns3)],
                         capture_output=True, text=True, check=True)
    result = {}
    for f in json.loads(out.stdout)["files"]:
        counts = defaultdict(int)
        for ln in f["lines"]:
            counts[ln["line_number"]] += ln["count"]
        result[f["file"]] = dict(counts)
    return result


def gcov_lines(ns3):
    """{file: {line: count}} of the AFDX code read with GCC's gcov, merged over object files."""
    merged = defaultdict(lambda: defaultdict(int))
    for gcda in Path(ns3).rglob("*.gcda"):
        out = subprocess.run(["gcov", "--json-format", "--stdout", "-o", str(gcda.parent), str(gcda)],
                             capture_output=True, cwd=gcda.parent, check=True)
        text = out.stdout
        if text[:2] == b"\x1f\x8b":
            text = gzip.decompress(text)
        for doc in text.decode().splitlines():
            if not doc.strip():
                continue
            for f in json.loads(doc)["files"]:
                path = Path(f["file"])
                if not path.is_absolute():
                    path = (gcda.parent / path)
                rel = os.path.relpath(os.path.normpath(path), ns3).replace(os.sep, "/")
                if not rel.startswith("examples/AFDX_V3/"):
                    continue
                for ln in f["lines"]:
                    merged[rel][ln["line_number"]] += ln["count"]
    return {f: dict(v) for f, v in merged.items()}


def totals(lines):
    return (sum(1 for v in lines.values() for c in v.values() if c > 0),
            sum(len(v) for v in lines.values()))


def run_one(cfg, ns3, gcovr, line):
    cc.reset_counters(ns3)
    runner = SimulatorRunner(ns3_path=ns3, work_dir="/tmp/verify_code_coverage")
    result = runner.run_simulation(sim_config=dict(cfg, inject_bug="none"), timeout=120)
    counts = gcovr_lines(ns3, gcovr).get(SWITCH, {})
    m = parse_metrics(result)
    return {"reject_line_count": counts.get(line, 0),
            "frames_dropped_frame_error": m.get("frames_dropped_frame_error"),
            "frames_forwarded": m.get("frames_forwarded"), "success": result["success"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--gcovr", required=True)
    parser.add_argument("--inputs", type=int, default=24)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    ns3 = os.environ["AFDX_NS3_PATH"]
    report = {}

    v = load_vls()[VL]
    middle = (v["min"] + v["max"]) // 2
    line = reject_line(ns3)
    print(f"check A: {SWITCH}:{line}, VL {VL} MinFrame {v['min']} MaxFrame {v['max']}")
    report["check_A"] = {"file": SWITCH, "line": line, "vl": VL, "max_frame": v["max"], "inputs": {}}
    for name, delta in (("normal", 0), ("MaxFrame", v["max"] - middle),
                        ("MaxFrame+1", v["max"] - middle + 1)):
        cfg = dict(cc.UNMUTATED, vlId=VL, payload_delta_bytes=delta)
        r = run_one(cfg, ns3, args.gcovr, line)
        report["check_A"]["inputs"][name] = dict(r, payload_delta_bytes=delta)
        print(f"  {name:11} delta {delta:5}: reject line ran {r['reject_line_count']} times, "
              f"frame-error drops {r['frames_dropped_frame_error']}, forwarded {r['frames_forwarded']}")
    a = report["check_A"]["inputs"]
    report["check_A"]["passed"] = (a["normal"]["reject_line_count"] == 0
                                   and a["MaxFrame"]["reject_line_count"] == 0
                                   and a["MaxFrame+1"]["reject_line_count"] > 0)
    print("  passed:", report["check_A"]["passed"])

    cfgs = list({config_key(c): c for _, c in logged_campaign(HISTORY, 10**9)}.values())[:args.inputs]
    cc.reset_counters(ns3)
    cc.run_inputs(cfgs, 8)
    by_gcovr, by_gcov = gcovr_lines(ns3, args.gcovr), gcov_lines(ns3)
    files = sorted(set(by_gcovr) | set(by_gcov))
    per_file = {f: {"gcovr": totals({f: by_gcovr.get(f, {})}), "gcov": totals({f: by_gcov.get(f, {})})}
                for f in files}
    covered_differs = {f: sorted(l for l in set(by_gcovr.get(f, {})) | set(by_gcov.get(f, {}))
                                 if (by_gcovr.get(f, {}).get(l, 0) > 0) != (by_gcov.get(f, {}).get(l, 0) > 0))
                       for f in files}
    report["check_B"] = {"inputs": len(cfgs), "gcovr": totals(by_gcovr), "gcov": totals(by_gcov),
                         "per_file": per_file,
                         "lines_covered_by_one_tool_only": {f: l for f, l in covered_differs.items() if l}}
    report["check_B"]["passed"] = (report["check_B"]["gcovr"] == report["check_B"]["gcov"]
                                   and not report["check_B"]["lines_covered_by_one_tool_only"])
    print(f"check B: {len(cfgs)} inputs; gcovr covered/total {report['check_B']['gcovr']}, "
          f"gcov {report['check_B']['gcov']}")
    for f, t in per_file.items():
        print(f"  {f:52} gcovr {t['gcovr']}  gcov {t['gcov']}")
    print("  lines covered by one tool only:", report["check_B"]["lines_covered_by_one_tool_only"])
    print("  passed:", report["check_B"]["passed"])
    Path(args.out).write_text(json.dumps(report, indent=2))
    print("->", args.out)


if __name__ == "__main__":
    main()
