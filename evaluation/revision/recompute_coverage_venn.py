#!/usr/bin/env python3
"""Recompute coverage and Unique Findings in one consistent unit (TAES revision, R1-M1 / R2-C5).

The submitted paper reported normalized coverage over the 185 rule categories
(Table IV), but drew the Venn diagram (Fig. 6) over normalized rule *labels*.
This script maps every iteration's ``protocol_rule`` label onto the 185
categories of ``configs/spec_rules_filtered.json`` with the same matching logic
that produced Table IV, and derives coverage, time-to-coverage and the Venn
regions from those category sets, so that every number shares one unit.

Mapping logic copied from evaluation/compute_metrics.py at commit 8bfd294
(``normalize_rule_name``, ``get_rule_field``, ``normalized_spec_coverage``).

Usage: python3 evaluation/revision/recompute_coverage_venn.py
Outputs: evaluation/results/revision/coverage_venn_categories.json
         evaluation/results/revision/unique_findings_venn_categories.png
"""
import json
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "evaluation" / "results" / "revision"
HISTORIES = {
    "LLM": ROOT / "llm_fuzzer/data/iteration_history.jsonl",
    "Boofuzz": ROOT / "boofuzz_baseline/data/iteration_history.jsonl",
    "Random": ROOT / "random_baseline/data/iteration_history.jsonl",
    "LLM No-Feedback": ROOT / "llm_fuzzer/data/iteration_history_no_feedback.jsonl",
}
SPEC_RULES = ROOT / "configs/spec_rules_filtered.json"
VENN_FUZZERS = ("LLM", "Boofuzz", "Random")


def normalize_rule_name(raw: str) -> str:
    s = raw.lower().replace(" ", "_").replace(".", "_").replace("-", "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")


def rule_labels(rows):
    """Targeted rule per iteration (protocol_rule, else mutation_type), as in get_rule_field."""
    out = []
    for r in rows:
        label = r.get("protocol_rule")
        if label is None:
            label = r.get("mutation_type")
        out.append("unknown" if label is None else str(label))
    return out


def build_matcher(spec_rules):
    sub_lookup = {}
    for cat, content in spec_rules.items():
        sub_lookup[normalize_rule_name(cat)] = cat
        if isinstance(content, dict):
            for sub in content:
                sub_lookup[normalize_rule_name(sub)] = cat
    norm_cats = {normalize_rule_name(c): c for c in spec_rules}

    def categories_of(raw_rule):
        cats = set()
        norm = normalize_rule_name(raw_rule)
        if norm in sub_lookup:
            cats.add(sub_lookup[norm])
        parts = raw_rule.split(".")
        if len(parts) > 1:
            sub = normalize_rule_name(parts[-1])
            if sub in sub_lookup:
                cats.add(sub_lookup[sub])
            prefix = normalize_rule_name(parts[0])
            if prefix in sub_lookup:
                cats.add(sub_lookup[prefix])
        for nc, original in norm_cats.items():
            if norm == nc or norm.startswith(nc + "_") or nc.startswith(norm + "_"):
                cats.add(original)
        return cats

    return categories_of


def build_loose_matcher(spec_rules, strict, threshold=0.5):
    """Sensitivity mapping: strict match first; otherwise the category of the
    best token-Jaccard match among category and rule names, if >= threshold."""
    entries = []
    for cat, content in spec_rules.items():
        entries.append((set(normalize_rule_name(cat).split("_")) - {""}, cat))
        if isinstance(content, dict):
            for sub in content:
                entries.append((set(normalize_rule_name(sub).split("_")) - {""}, cat))

    def jaccard(a, b):
        return len(a & b) / len(a | b) if a | b else 0.0

    def categories_of(raw_rule):
        cats = strict(raw_rule)
        if cats:
            return cats
        tokens = set(normalize_rule_name(raw_rule.split(".")[-1]).split("_")) - {""}
        scores = [(jaccard(tokens, e), c) for e, c in entries]
        best = max(s for s, _ in scores)
        return {c for s, c in scores if s == best} if best >= threshold else set()

    return categories_of


def venn_regions(sets):
    names = list(sets)
    regions = {}
    for k in range(1, len(names) + 1):
        for combo in combinations(names, k):
            inside = set.intersection(*(sets[n] for n in combo))
            outside = set().union(*(sets[n] for n in names if n not in combo))
            regions[" & ".join(combo)] = len(inside - outside)
    return regions


def main():
    spec_rules = json.loads(SPEC_RULES.read_text())
    total = len(spec_rules)
    categories_of = build_matcher(spec_rules)
    loose_categories_of = build_loose_matcher(spec_rules, categories_of)
    threshold = 0.8 * total

    report = {"denominator_categories": total, "fuzzers": {}}
    category_sets, label_sets = {}, {}
    for name, path in HISTORIES.items():
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        labels = rule_labels(rows)
        covered, curve, first80, unmatched = set(), [], None, set()
        for i, label in enumerate(labels, 1):
            cats = categories_of(label)
            if not cats:
                unmatched.add(label)
            covered |= cats
            curve.append(len(covered))
            if first80 is None and len(covered) >= threshold:
                first80 = i
        category_sets[name] = covered
        label_sets[name] = {normalize_rule_name(lbl) for lbl in labels}
        loose = set().union(*(loose_categories_of(lbl) for lbl in labels))
        report["fuzzers"][name] = {
            "iterations": len(rows),
            "covered_categories": len(covered),
            "normalized_coverage_pct": round(100 * len(covered) / total, 1),
            "first_iteration_at_80pct_categories": first80,
            "distinct_raw_labels": len(set(labels)),
            "distinct_normalized_labels": len(label_sets[name]),
            "labels_not_mapped_to_any_category": len(unmatched),
            "loose_jaccard_0.5_covered_categories": len(loose),
            "loose_jaccard_0.5_coverage_pct": round(100 * len(loose) / total, 1),
            "cumulative_categories_per_iteration": curve,
        }

    venn_sets = {n: category_sets[n] for n in VENN_FUZZERS}
    regions = venn_regions(venn_sets)
    for n in VENN_FUZZERS:
        total_n = sum(v for k, v in regions.items() if n in k.split(" & "))
        assert total_n == len(venn_sets[n]), (n, total_n, len(venn_sets[n]))
    union = set().union(*venn_sets.values())
    assert sum(regions.values()) == len(union) <= total
    unique = {n: regions[n] for n in VENN_FUZZERS}
    for n in VENN_FUZZERS:
        others = set().union(*(venn_sets[m] for m in VENN_FUZZERS if m != n))
        assert unique[n] == len(venn_sets[n] - others)
    report["venn_categories"] = {
        "regions": regions,
        "unique_findings_Uf": unique,
        "union": len(union),
        "covered_by_none": total - len(union),
    }
    label_regions = venn_regions({n: label_sets[n] for n in VENN_FUZZERS})
    report["venn_normalized_labels_as_in_submitted_fig6"] = {
        "regions": label_regions,
        "union": len(set().union(*(label_sets[n] for n in VENN_FUZZERS))),
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "coverage_venn_categories.json").write_text(json.dumps(report, indent=2))
    plot_venn(venn_sets, total, OUT / "unique_findings_venn_categories.png")

    for n, v in report["fuzzers"].items():
        print(f"{n:16s} categories {v['covered_categories']:3d}/{total} = {v['normalized_coverage_pct']:5.1f}%"
              f" | first iter >=80%: {v['first_iteration_at_80pct_categories']}"
              f" | raw labels {v['distinct_raw_labels']} | normalized labels {v['distinct_normalized_labels']}"
              f" | unmapped labels {v['labels_not_mapped_to_any_category']}"
              f" | loose mapping {v['loose_jaccard_0.5_covered_categories']}/{total}"
              f" = {v['loose_jaccard_0.5_coverage_pct']}%")
    print("Venn over categories:", regions, "| union", len(union), "| none", total - len(union))
    print("Venn over normalized labels (submitted Fig. 6 units):", label_regions)


def plot_venn(sets, total, out_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib_venn import venn3

    names = list(sets)
    labels = [f"{'BOOFUZZ' if n == 'Boofuzz' else n}\n({len(sets[n])} of {total})" for n in names]
    fig, ax = plt.subplots(figsize=(6.4, 4.8))
    v = venn3([sets[n] for n in names], set_labels=labels, ax=ax,
              set_colors=("#2563eb", "#10b981", "#f59e0b"), alpha=0.5)
    for t in v.subset_labels:
        if t is not None:
            t.set_fontsize(12)
    for t in v.set_labels:
        if t is not None:
            t.set_fontsize(11)
    fig.tight_layout()
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
