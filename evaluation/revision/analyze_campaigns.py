#!/usr/bin/env python3
"""
Metrics of the revision campaigns (histories that log 'sim_config').

For every history: Rule Coverage as defined in the paper (categories reached
by the recorded protocol-rule labels), the same count restricted to
iterations whose simulator input contains at least one mutation, the
executed mutation settings, planner actions, LLM token use, and the Bug
Detection Rate from a bdr_replay.py report. Fuzzers with several runs are
summarized by mean, standard deviation and range, and compared pairwise with
an exact two-sided Mann-Whitney U test.

Usage:
  analyze_campaigns.py --campaign LLM=runs/llm_full_*.jsonl \
      --campaign Boofuzz=runs/boofuzz.jsonl --bdr bdr_replay_revision.json \
      --out campaign_metrics.json

The BDR report must name each history by its path (bdr_replay.py --history PATH=PATH).
Iterations whose input crashed the simulator in the replay count as not executed:
they add no coverage and are not valid.
No LLM API is used.
"""

import argparse
import glob
import json
import statistics
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "evaluation" / "revision"))

import audit_final_rules as audit  # noqa: E402
import executed_settings as es  # noqa: E402
import recompute_coverage_venn as rcv  # noqa: E402

# USD per million tokens (input, cached input, output); check against current list prices.
PRICES = {"gpt-5": (1.25, 0.125, 10.0)}
N_CATEGORIES = 185
COMPLETENESS = ROOT / "evaluation/results/revision/rule_completeness_validated.json"
CORRECTNESS = ROOT / "evaluation/results/revision/rule_correctness_filtered.json"


def rejected_only_categories(spec_rules):
    """Categories all of whose rules the correctness audit judged incorrect."""
    verdicts = {}
    for v in json.loads(CORRECTNESS.read_text())["verdicts"].values():
        verdicts.setdefault(v["category"], []).append(v["verdict"])
    return {c for c in spec_rules if verdicts.get(c) and set(verdicts[c]) == {"incorrect"}}


def checklist_categories(categories_of):
    """Normative statement of the specification checklist -> categories of the rule that covers it."""
    rules = {r["id"]: r for r in audit.load_rules("validated")}
    items = json.loads(COMPLETENESS.read_text())["items"]

    def rule_of(rid):
        # The audit model sometimes answered with the bare number ("167" for "rule_167").
        rid = str(rid or "")
        return rules.get(rid) or (rules.get(f"rule_{int(rid):03d}") if rid.isdigit() else None)

    return {sid: categories_of(rule_of(v["rule_id"]).get("category") or "")
            | categories_of(rule_of(v["rule_id"]).get("name") or "")
            for sid, v in items.items()
            if v["status"] == "covered" and rule_of(v.get("rule_id"))}, len(items)


def history_metrics(path, categories_of, bdr, loose_categories_of, statements, rejected_only):
    rows = es.load(Path(path))
    configs = [r.get("sim_config") for r in rows]
    if any(c is None for c, r in zip(configs, rows) if r.get("simulation_success")):
        raise SystemExit(f"{path}: successful iterations without sim_config")
    # The harness that recorded the histories did not detect simulator crashes; the replay does.
    crashed = set(bdr[str(path)]["crashed_iterations"]) if bdr and str(path) in bdr else set()
    executed = [bool(r.get("simulation_success")) and r.get("iteration") not in crashed for r in rows]
    labels, executed_labels, curve = set(), set(), []
    for row, cfg, ran in zip(rows, configs, executed):
        cats = categories_of(row.get("protocol_rule") or "") if ran else set()
        labels |= cats
        if cfg and es.mechanisms(cfg):
            executed_labels |= cats
        curve.append(len(labels))
    run_labels = {r.get("protocol_rule") for r, ran in zip(rows, executed) if ran and r.get("protocol_rule")}
    threshold = 0.8 * N_CATEGORIES
    durations = sorted(r["duration"] for r in rows if isinstance(r.get("duration"), (int, float)))
    actions = Counter(a.get("type") for r in rows for a in (r.get("planner_actions") or []))
    usage = [u for r in rows for u in (r.get("llm_usage") or [])]
    cost = 0.0
    for u in usage:
        price_in, price_cached, price_out = PRICES.get(u["model"], (0.0, 0.0, 0.0))
        cached = u.get("cached_tokens") or 0
        cost += ((u["prompt_tokens"] - cached) * price_in + cached * price_cached
                 + u["completion_tokens"] * price_out) / 1e6
    report = {
        "iterations": len(rows),
        "simulation_failures": sum(not r.get("simulation_success") for r in rows),
        "rule_coverage": len(labels),
        "rule_coverage_executed": len(executed_labels),
        "categories": sorted(labels),
        "categories_executed": sorted(executed_labels),
        "distinct_labels": len(run_labels),
        "labels_not_mapped": len({lbl for lbl in run_labels if not categories_of(lbl)}),
        "rule_coverage_loose": len(set().union(*(loose_categories_of(lbl) for lbl in run_labels))),
        "rejected_only_covered": len(labels & rejected_only),
        "rule_coverage_pct_without_rejected": 100 * len(labels - rejected_only) / (N_CATEGORIES - len(rejected_only)),
        "checklist_statements": sum(bool(c & labels) for c in statements.values()),
        "checklist_statements_executed": sum(bool(c & executed_labels) for c in statements.values()),
        "crashed_iterations": sorted(crashed),
        "valid_ratio": sum(ran and (r.get("frames_received") or 0) > 0
                           for r, ran in zip(rows, executed)) / len(rows),
        "time_to_80pct": next((i + 1 for i, c in enumerate(curve) if c >= threshold), None),
        "median_iteration_s": statistics.median(durations) if durations else None,
        "executed": es.summarize([c for c, ran in zip(configs, executed) if c and ran]),
        "planner_actions": dict(actions),
        "llm_calls": len(usage),
        "llm_backends": dict(Counter(u.get("backend") for u in usage)),
        "llm_tokens": {k: sum(u.get(k) or 0 for u in usage)
                       for k in ("prompt_tokens", "cached_tokens", "completion_tokens",
                                 "reasoning_tokens")},
        "llm_cost_usd": round(cost, 2),
    }
    if bdr and str(path) in bdr:
        report["bugs_detected"] = bdr[str(path)]["bugs_detected"]
        report["bdr_per_bug"] = {b: v["detecting_iterations"]
                                 for b, v in bdr[str(path)]["per_bug"].items()}
        report["first_detection"] = {b: v["first_detection_iter"]
                                     for b, v in bdr[str(path)]["per_bug"].items()}
    return report


def unique_findings(per_run, names, key="categories"):
    """U_f per fuzzer for run triples paired by index; single-run fuzzers repeat their run."""
    runs = {n: list(per_run[n].values()) for n in names}
    k = max(len(r) for r in runs.values())
    if any(len(r) not in (1, k) for r in runs.values()):
        raise SystemExit("--unique needs fuzzers with one run or the same number of runs")
    counts = {n: [] for n in names}
    for i in range(k):
        sets = {n: set(runs[n][i if len(runs[n]) > 1 else 0][key]) for n in names}
        for n in names:
            others = set().union(*(sets[m] for m in names if m != n))
            counts[n].append(len(sets[n] - others))
    return {n: summary(v) for n, v in counts.items()}


def summary(values):
    return {"n": len(values), "mean": statistics.mean(values),
            "sd": statistics.stdev(values) if len(values) > 1 else 0.0,
            "min": min(values), "max": max(values), "values": values}


def mann_whitney_exact(x, y):
    """Two-sided exact Mann-Whitney U test over all splits of the pooled runs (handles ties)."""
    pooled = list(x) + list(y)

    def u(a, b):
        return sum((ai > bi) + 0.5 * (ai == bi) for ai in a for bi in b)

    center = len(x) * len(y) / 2
    observed = abs(u(x, y) - center)
    splits = list(combinations(range(len(pooled)), len(x)))
    extreme = 0
    for idx in splits:
        a = [pooled[i] for i in idx]
        b = [pooled[i] for i in range(len(pooled)) if i not in idx]
        extreme += abs(u(a, b) - center) >= observed - 1e-9
    return extreme / len(splits)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--campaign", action="append", required=True, metavar="NAME=GLOB")
    parser.add_argument("--bdr", action="append", default=[], help="bdr_replay.py report (repeatable)")
    parser.add_argument("--unique", metavar="NAME,NAME,...",
                        help="campaigns compared by Unique Findings")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    spec_rules = json.loads((ROOT / "configs/spec_rules_filtered.json").read_text())
    categories_of = rcv.build_matcher(spec_rules)
    loose_categories_of = rcv.build_loose_matcher(spec_rules, categories_of)
    statements, n_statements = checklist_categories(categories_of)
    rejected_only = rejected_only_categories(spec_rules)
    print(f"categories with only rejected rules: {len(rejected_only)}")
    print(f"checklist: {n_statements} statements, {len(statements)} covered by a validated rule, "
          f"{sum(bool(c) for c in statements.values())} of them map to a category")
    bdr = {k: v for f in args.bdr for k, v in json.loads(Path(f).read_text()).items()}
    per_run, per_fuzzer = {}, {}
    for spec in args.campaign:
        name, pattern = spec.split("=", 1)
        paths = sorted(glob.glob(pattern))
        if not paths:
            raise SystemExit(f"no history matches {pattern}")
        per_run[name] = {p: history_metrics(p, categories_of, bdr, loose_categories_of, statements,
                                            rejected_only) for p in paths}

    metrics = ("rule_coverage", "rule_coverage_executed", "rule_coverage_loose",
               "rejected_only_covered", "rule_coverage_pct_without_rejected", "checklist_statements",
               "checklist_statements_executed", "distinct_labels", "labels_not_mapped", "valid_ratio",
               "bugs_detected", "llm_cost_usd")
    for name, runs in per_run.items():
        per_fuzzer[name] = {m: summary([r[m] for r in runs.values()])
                            for m in metrics if all(m in r for r in runs.values())}
        per_fuzzer[name]["distinct_settings"] = summary(
            [r["executed"]["distinct_settings"] for r in runs.values()])
        per_fuzzer[name]["iterations_without_mutation"] = summary(
            [r["executed"]["iterations_without_mutation"] for r in runs.values()])

    tests = {}
    for a, b in combinations(per_fuzzer, 2):
        for m in per_fuzzer[a]:
            if m in per_fuzzer[b] and m != "llm_cost_usd":
                x, y = per_fuzzer[a][m]["values"], per_fuzzer[b][m]["values"]
                if len(x) > 1 and len(y) > 1:
                    tests[f"{a} vs {b}: {m}"] = mann_whitney_exact(x, y)

    report = {"per_run": per_run, "per_fuzzer": per_fuzzer, "mann_whitney_p": tests}
    if args.unique:
        names = args.unique.split(",")
        report["unique_findings"] = unique_findings(per_run, names)
        report["unique_findings_executed"] = unique_findings(per_run, names, "categories_executed")
        # Categories exercised with a mutation by every run of the first fuzzer and by no run of the others.
        first, others = names[0], names[1:]
        always = set.intersection(*(set(r["categories_executed"]) for r in per_run[first].values()))
        reached = set().union(*(r["categories_executed"] for n in others for r in per_run[n].values()))
        report["executed_in_every_run_only"] = {first: sorted(always - reached)}
    Path(args.out).write_text(json.dumps(report, indent=2))
    for name, s in per_fuzzer.items():
        print(name, {m: (round(v["mean"], 2), round(v["sd"], 2)) for m, v in s.items()})
    for k, p in tests.items():
        print(f"  p={p:.4f}  {k}")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
