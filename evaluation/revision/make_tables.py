#!/usr/bin/env python3
"""
LaTeX table rows for the revised Experiment 2, ablation and Experiment 3
tables, printed from the output of analyze_campaigns.py so that no number is
copied by hand.

Usage:
  make_tables.py campaign_metrics.json [--llm LLM --boofuzz Boofuzz --random Random]

No LLM API and no simulator are used.
"""

import argparse
import json
import statistics

N_CATEGORIES = 185
BUG_ORDER = ["skip_bag_policing", "skip_frame_validation", "skip_mac_validation",
             "skip_token_bucket", "skip_vl_check", "skip_constant_field",
             "skip_sequence_check", "accept_oversized"]


def num(x, fmt):
    return f"{x:.0f}" if float(x).is_integer() else fmt.format(x)


def cell(s, fmt="{:.1f}", pct=False):
    """mean ± sd [min–max] for several runs, the value alone for one run."""
    scale = 100 / N_CATEGORIES if pct else 1
    if s["n"] == 1:
        return f"${fmt.format(s['mean'] * scale) if pct else num(s['mean'], fmt)}$"
    lo, hi = s["min"] * scale, s["max"] * scale
    rng = f"{fmt.format(lo)}--{fmt.format(hi)}" if pct else f"{num(lo, fmt)}--{num(hi, fmt)}"
    return f"${fmt.format(s['mean'] * scale)} \\pm {fmt.format(s['sd'] * scale)}$ [{rng}]"


def first_detection(runs, bug):
    """'k/n, median [min–max]' of the first detection iteration over runs."""
    firsts = [r["first_detection"][bug] for r in runs if r.get("first_detection")]
    hits = [f for f in firsts if f is not None]
    if len(firsts) == 1:
        return f"\\checkmark\\,({hits[0]})" if hits else "$\\times$"
    if not hits:
        return f"$0/{len(firsts)}$"
    spread = f"{min(hits)}--{max(hits)}" if len(hits) > 1 else f"{hits[0]}"
    return f"${len(hits)}/{len(firsts)}$, {statistics.median(hits):g} [{spread}]"


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("metrics")
    parser.add_argument("--llm", default="LLM")
    parser.add_argument("--boofuzz", default="Boofuzz")
    parser.add_argument("--random", default="Random")
    parser.add_argument("--ablation", default="A2,A1,A0")
    args = parser.parse_args()
    m = json.load(open(args.metrics))
    pf, runs, uf = m["per_fuzzer"], m["per_run"], m.get("unique_findings", {})
    cols = [args.llm, args.boofuzz, args.random]

    print("% Experiment 2")
    rows = [("Rule Coverage (\\%)", "rule_coverage", "{:.1f}", True),
            ("\\quad (categories)", "rule_coverage", "{:.1f}", False),
            ("Executed Rule Coverage (\\%)", "rule_coverage_executed", "{:.1f}", True),
            ("\\quad (categories)", "rule_coverage_executed", "{:.1f}", False),
            ("Distinct rule labels", "distinct_labels", "{:.1f}", False),
            ("Distinct simulator settings", "distinct_settings", "{:.1f}", False),
            ("Iterations without mutation", "iterations_without_mutation", "{:.1f}", False)]
    for label, key, fmt, pct in rows:
        print(f"{label} & " + " & ".join(cell(pf[c][key], fmt, pct) for c in cols) + " \\\\")
    t80 = [[r["time_to_80pct"] for r in runs[c].values()] for c in cols]
    print("Time to $80\\%$ Rule Coverage & " + " & ".join(
        "N/A" if all(v is None for v in t) else str(t) for t in t80) + " \\\\")
    valid = [pf[c]["valid_ratio"] for c in cols]
    print("Ratio of Valid Messages & " + " & ".join(
        f"${100 * v['mean']:.1f}\\%$" if v["n"] == 1 or v["sd"] == 0 else cell(v, "{:.3f}") for v in valid) + " \\\\")
    if uf:
        print("Unique Findings (categories) & " + " & ".join(cell(uf[c]) for c in cols) + " \\\\")

    print("\n% Ablation")
    variants = [args.llm] + args.ablation.split(",")
    for v in variants:
        p = pf[v]
        print(f"{v} & " + " & ".join([
            cell(p["distinct_labels"]), cell(p["rule_coverage"]), cell(p["rule_coverage_executed"]),
            cell(p["distinct_settings"]), cell(p["iterations_without_mutation"]),
            cell(p["bugs_detected"], "{:.0f}") if "bugs_detected" in p else "--"]) + " \\\\")

    print("\n% Experiment 3: bugs detected per run")
    for c in cols + args.ablation.split(","):
        if "bugs_detected" in pf[c]:
            print(f"{c}: {pf[c]['bugs_detected']['values']}")
    print("\n% Experiment 3: per-bug first detection (iterations counted from 0)")
    for bug in BUG_ORDER:
        print(f"\\texttt{{{bug.replace('_', chr(92) + '_')}}} & " + " & ".join(
            first_detection(list(runs[c].values()), bug) for c in cols) + " \\\\")
    print("\n% LLM cost and time per run")
    for c in [args.llm] + args.ablation.split(","):
        r = list(runs[c].values())
        print(c, "cost", [x["llm_cost_usd"] for x in r], "calls", [x["llm_calls"] for x in r],
              "median s/iter", [round(x["median_iteration_s"], 1) for x in r],
              "backends", [x["llm_backends"] for x in r])


if __name__ == "__main__":
    main()
