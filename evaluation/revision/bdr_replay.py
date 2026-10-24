#!/usr/bin/env python3
"""
Experiment 3 (Bug Detection Rate) replayed with the exact simulator input of
every iteration.

compute_bdr.py rebuilt each iteration from a subset of the logged fields, so
mutations that a fuzzer did not log were not replayed, and a missing 'prob'
field became a 50% sender drop. This script replays the simulator input
itself:

  * a history that logs 'sim_config' (campaigns run after the revision) is
    replayed as logged (--history NAME=PATH);
  * --original reconstructs the inputs of the submitted campaigns: the
    LLM-guided campaign from its logged fields (complete for that fuzzer) and
    the BOOFUZZ-style campaign by re-running its deterministic generator
    (executed_settings.py). The parameters of the submitted Random campaign
    were not logged and cannot be reconstructed;
  * --original-as-run rebuilds the inputs exactly as compute_bdr.py did, to
    check this script against the submitted Experiment 3 numbers.

Bug catalogue, metrics, detection signals and threshold are imported from
compute_bdr.py. The simulator is deterministic, so every distinct
(input, bug) pair is run once and shared between iterations and fuzzers;
results are cached in --cache.

No LLM API is used.
"""

import argparse
import json
import queue
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evaluation"))
sys.path.insert(0, str(ROOT / "evaluation" / "revision"))

from compute_bdr import BUGS, bug_detected, parse_metrics  # noqa: E402
from llm_fuzzer.utils.simulator_runner import SimulatorRunner  # noqa: E402
import executed_settings as es  # noqa: E402

RESULTS = ROOT / "evaluation/results/revision"
# Cache marker of a simulator run that exited with an error; such an iteration detects nothing.
FAILED = "_failed"


def config_key(cfg):
    return json.dumps({k: v for k, v in cfg.items() if k != "inject_bug"}, sort_keys=True)


def successful(rows, configs, max_iterations):
    """The records compute_bdr.py evaluated: successful iterations, first max_iterations."""
    kept = [(row, cfg) for row, cfg in zip(rows, configs) if row.get("simulation_success", False)]
    return kept[:max_iterations]


def logged_campaign(path, max_iterations):
    rows = es.load(Path(path))
    missing = [r.get("iteration") for r in rows if r.get("simulation_success") and not r.get("sim_config")]
    if missing:
        raise SystemExit(f"{path}: {len(missing)} successful iterations without sim_config")
    return successful(rows, [r.get("sim_config") for r in rows], max_iterations)


def original_campaigns(max_iterations, as_run):
    translate = es.Translator()
    rows = {name: es.load(path) for name, path in es.HISTORIES.items()}
    if as_run:
        return {name: successful(history, [translate(r.get("target_vl", 2001), es.bdr_metadata(r))
                                           for r in history], max_iterations)
                for name, history in rows.items()}
    llm = [translate(r["target_vl"], es.campaign_metadata(
        r, r.get("mutation_type") or r.get("protocol_rule") or "generic")) for r in rows["LLM"]]
    with tempfile.TemporaryDirectory() as tmp:
        strategies, matched, _ = es.replay_boofuzz(rows["Boofuzz"], Path(tmp))
    if matched != len(rows["Boofuzz"]):
        raise SystemExit(f"BOOFUZZ replay matched {matched}/{len(rows['Boofuzz'])} iterations")
    boofuzz = es.boofuzz_campaign_configs(rows["Boofuzz"], strategies, translate)
    return {"LLM": successful(rows["LLM"], llm, max_iterations),
            "Boofuzz": successful(rows["Boofuzz"], boofuzz, max_iterations)}


class Pool:
    """Simulator runs in parallel, one isolated working directory per worker."""

    def __init__(self, workers, cache_path):
        self.cache_path = Path(cache_path)
        self.cache = json.loads(self.cache_path.read_text()) if self.cache_path.exists() else {}
        self.lock = threading.Lock()
        self.tmp = tempfile.TemporaryDirectory(prefix="bdr_replay_")
        self.runners = queue.Queue()
        for i in range(workers):
            self.runners.put(SimulatorRunner(work_dir=f"{self.tmp.name}/w{i}"))
        self.workers = workers

    def _run(self, key, bug):
        runner = self.runners.get()
        try:
            cfg = dict(json.loads(key), inject_bug=bug)
            result = runner.run_simulation(sim_config=cfg, timeout=120)
        finally:
            self.runners.put(runner)
        if not result["success"]:
            return {FAILED: result["error"]}
        return parse_metrics(result)

    def run_all(self, jobs):
        todo = sorted({job for job in jobs if f"{job[1]}|{job[0]}" not in self.cache})
        print(f"{len(set(jobs))} distinct runs, {len(todo)} not cached, {self.workers} workers")
        with ThreadPoolExecutor(self.workers) as ex:
            futures = {ex.submit(self._run, key, bug): (key, bug) for key, bug in todo}
            for n, fut in enumerate(as_completed(futures), 1):
                key, bug = futures[fut]
                with self.lock:
                    self.cache[f"{bug}|{key}"] = fut.result()
                if n % 50 == 0 or n == len(todo):
                    print(f"  {n}/{len(todo)}", flush=True)
                    self.save()
        self.save()

    def save(self):
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self.cache))

    def metrics(self, key, bug):
        return self.cache[f"{bug}|{key}"]


def crashed(records, pool, bugs):
    """Iterations whose input makes the simulator exit with an error in any of the given variants."""
    return [row.get("iteration") for row, cfg in records
            if any(FAILED in pool.metrics(config_key(cfg), bug) for bug in bugs)]


def evaluate(records, pool):
    per_bug = {}
    for bug in BUGS:
        detecting = []
        for row, cfg in records:
            key = config_key(cfg)
            ref, buggy = pool.metrics(key, "none"), pool.metrics(key, bug["id"])
            if FAILED not in ref and FAILED not in buggy and bug_detected(ref, buggy, bug):
                detecting.append(row.get("iteration"))
        per_bug[bug["id"]] = {"detected": bool(detecting),
                              "first_detection_iter": detecting[0] if detecting else None,
                              "detecting_iterations": len(detecting)}
    firsts = [b["first_detection_iter"] for b in per_bug.values() if b["detected"]]
    found = sum(b["detected"] for b in per_bug.values())
    return {"iterations": len(records),
            "crashed_iterations": crashed(records, pool, ["none"] + [b["id"] for b in BUGS]),
            "distinct_inputs": len({config_key(cfg) for _, cfg in records}),
            "bugs_detected": found, "bugs_total": len(BUGS), "bdr": found / len(BUGS),
            "mean_iterations_to_first_detection": sum(firsts) / len(firsts) if firsts else None,
            "per_bug": per_bug}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--history", action="append", default=[], metavar="NAME=PATH",
                        help="history JSONL with sim_config per iteration (repeatable)")
    parser.add_argument("--original", action="store_true",
                        help="reconstructed inputs of the submitted LLM and BOOFUZZ campaigns")
    parser.add_argument("--original-as-run", action="store_true",
                        help="inputs as rebuilt by compute_bdr.py (check against the paper)")
    parser.add_argument("--max-iterations", type=int, default=200)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--cache", default=str(RESULTS / "bdr_replay_cache_v2.json"))
    parser.add_argument("--reference-only", action="store_true",
                        help="run only the bug-free SUT and report the iterations whose input crashes it")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    campaigns = {}
    if args.original:
        campaigns.update({f"original/{k}": v for k, v in
                          original_campaigns(args.max_iterations, as_run=False).items()})
    if args.original_as_run:
        campaigns.update({f"original_as_run/{k}": v for k, v in
                          original_campaigns(args.max_iterations, as_run=True).items()})
    for spec in args.history:
        name, path = spec.split("=", 1)
        campaigns[name] = logged_campaign(path, args.max_iterations)
    if not campaigns:
        parser.error("nothing to replay")

    pool = Pool(args.workers, args.cache)
    variants = ["none"] if args.reference_only else ["none"] + [b["id"] for b in BUGS]
    jobs = [(config_key(cfg), bug) for records in campaigns.values() for _, cfg in records
            for bug in variants]
    pool.run_all(jobs)

    if args.reference_only:
        report = {name: {"iterations": len(records), "crashed_iterations": crashed(records, pool, ["none"]),
                         "errors": sorted({pool.metrics(config_key(cfg), "none")[FAILED][:200]
                                           for _, cfg in records
                                           if FAILED in pool.metrics(config_key(cfg), "none")})}
                  for name, records in campaigns.items()}
        Path(args.out).write_text(json.dumps(report, indent=2))
        for name, r in report.items():
            print(f"{name:28s} crashed {len(r['crashed_iterations'])}/{r['iterations']}: {r['crashed_iterations']}")
        print(f"-> {args.out}")
        return

    report = {name: evaluate(records, pool) for name, records in campaigns.items()}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2))
    for name, r in report.items():
        hits = ", ".join(f"{b}({v['detecting_iterations']})" for b, v in r["per_bug"].items() if v["detected"])
        print(f"{name:28s} {r['bugs_detected']}/{r['bugs_total']}  inputs={r['distinct_inputs']:3d}  {hits}")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
