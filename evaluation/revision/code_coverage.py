#!/usr/bin/env python3
"""Code coverage of the simulator per fuzzing run (TAES revision, PAPER_CHANGES 4.9).

Line and branch coverage of the AFDX simulator code (examples/AFDX_V3/, the switch, end-system
and traffic-generator models and the scenario) reached by the simulator inputs of each run. It
depends on nothing of our method: no rules, no labels, no table; only on what the simulator
executed. Every run of every fuzzer goes through the same steps:

  1. the run's successful records are read as bdr_replay.py reads them (logged_campaign), and
     its distinct simulator inputs are kept (an identical input executes identical code);
  2. the coverage counters (.gcda) of the instrumented build are deleted;
  3. every distinct input is run on the bug-free simulator (inject_bug "none"), in parallel,
     each worker in its own working directory; gcov adds up the counters of all runs;
  4. gcovr reports line and branch coverage restricted to examples/AFDX_V3/.

The simulator must be a copy built with the compiler's --coverage flag (build_coverage_simulator.sh; here
/tmp/ns3_cov), set with AFDX_NS3_PATH. --baseline adds the unmutated input alone, i.e. the code that normal traffic
already runs. No LLM API is used.

Usage:
  AFDX_NS3_PATH=/tmp/ns3_cov code_coverage.py --gcovr ~/cov_venv/bin/gcovr \
      --campaign LLM=runs/stage7/llm_full_r*.jsonl ... --baseline --out code_coverage_stage7.json
"""

import argparse
import glob
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evaluation"))
sys.path.insert(0, str(ROOT / "evaluation" / "revision"))

from bdr_replay import config_key, logged_campaign  # noqa: E402
from llm_fuzzer.utils.simulator_runner import SimulatorRunner  # noqa: E402
from analyze_campaigns import mann_whitney_exact, summary  # noqa: E402

FILTER = r".*examples/AFDX_V3/.*"
UNMUTATED = {"vlId": 1001, "prob": 0.0, "payload_delta_bytes": 0, "timing_jitter_ms": 0,
             "mac_mutation": "none", "is_extreme_test": True, "sequence_number_override": 0,
             "dest_mac_mutation": "none", "inject_bug": "none"}


def reset_counters(ns3):
    for f in Path(ns3).rglob("*.gcda"):
        f.unlink()


def run_inputs(configs, workers):
    """Run every simulator input once on the bug-free simulator; return the failed ones."""
    tmp = tempfile.TemporaryDirectory(prefix="code_coverage_")
    runners = [SimulatorRunner(work_dir=f"{tmp.name}/w{i}") for i in range(workers)]
    chunks = [configs[i::workers] for i in range(workers)]

    def work(i):
        failed = []
        for cfg in chunks[i]:
            result = runners[i].run_simulation(sim_config=dict(cfg, inject_bug="none"), timeout=120)
            if not result["success"]:
                failed.append(config_key(cfg))
        return failed

    with ThreadPoolExecutor(workers) as ex:
        failed = [k for f in ex.map(work, range(workers)) for k in f]
    tmp.cleanup()
    return failed


def coverage_report(ns3, gcovr):
    """Line and branch totals and per-file numbers of the AFDX code, from gcovr's JSON summary."""
    out = subprocess.run([gcovr, "--root", str(ns3), "--filter", FILTER,
                          "--exclude-throw-branches", "--exclude-unreachable-branches",
                          "--json-summary", "-", str(ns3)],
                         capture_output=True, text=True, check=True)
    data = json.loads(out.stdout)
    files = {f["filename"]: {k: f[k] for k in ("line_covered", "line_total",
                                                  "branch_covered", "branch_total")}
             for f in data["files"]}
    return {"line_covered": data["line_covered"], "line_total": data["line_total"],
            "line_percent": data["line_percent"], "branch_covered": data["branch_covered"],
            "branch_total": data["branch_total"], "branch_percent": data["branch_percent"],
            "files": files}


def measure(configs, ns3, gcovr, workers):
    reset_counters(ns3)
    failed = run_inputs(configs, workers)
    report = coverage_report(ns3, gcovr)
    report.update(distinct_inputs=len(configs), failed_inputs=failed)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--campaign", action="append", required=True, metavar="NAME=GLOB")
    parser.add_argument("--gcovr", required=True, help="path of the gcovr executable")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--baseline", action="store_true", help="also measure the unmutated input")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    ns3 = os.environ.get("AFDX_NS3_PATH")
    if not ns3 or not list(Path(ns3).rglob("*.gcno")):
        raise SystemExit("AFDX_NS3_PATH must point to a build built with --coverage (build_coverage_simulator.sh)")

    report = {"filter": FILTER, "per_run": {}, "per_fuzzer": {}}
    if args.baseline:
        report["unmutated"] = measure([UNMUTATED], ns3, args.gcovr, 1)
        print(f"unmutated: lines {report['unmutated']['line_percent']}%, "
              f"branches {report['unmutated']['branch_percent']}%", flush=True)
    for spec in args.campaign:
        name, pattern = spec.split("=", 1)
        paths = sorted(Path(p).as_posix() for p in glob.glob(pattern))
        if not paths:
            raise SystemExit(f"no history matches {pattern}")
        report["per_run"][name] = {}
        for path in paths:
            distinct = {config_key(cfg): cfg for _, cfg in logged_campaign(path, 10**9)}
            r = measure(list(distinct.values()), ns3, args.gcovr, args.workers)
            report["per_run"][name][path] = r
            print(f"{name:14} {Path(path).name:28} lines {r['line_covered']}/{r['line_total']} "
                  f"branches {r['branch_covered']}/{r['branch_total']} "
                  f"({r['distinct_inputs']} inputs, {len(r['failed_inputs'])} failed)", flush=True)
            Path(args.out).write_text(json.dumps(report, indent=2))
        runs = report["per_run"][name].values()
        report["per_fuzzer"][name] = {m: summary([r[m] for r in runs])
                                      for m in ("line_covered", "branch_covered")}
    names = list(report["per_fuzzer"])
    report["mann_whitney_p"] = {
        f"{a} vs {b}: {m}": mann_whitney_exact(report["per_fuzzer"][a][m]["values"],
                                               report["per_fuzzer"][b][m]["values"])
        for i, a in enumerate(names) for b in names[i + 1:] for m in ("line_covered", "branch_covered")
        if len(report["per_fuzzer"][a][m]["values"]) > 1 and len(report["per_fuzzer"][b][m]["values"]) > 1}
    Path(args.out).write_text(json.dumps(report, indent=2))
    for k, p in report["mann_whitney_p"].items():
        print(f"  p={p:.4f}  {k}")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
