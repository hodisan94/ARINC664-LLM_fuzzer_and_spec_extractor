#!/usr/bin/env python3
"""
Figures of the revision campaigns (histories that log 'sim_config').

  rev_coverage_curves.png   cumulative Rule Coverage per iteration for the
                            LLM-guided fuzzer, the BOOFUZZ-style baseline and
                            the random baseline: (a) categories reached by the
                            recorded labels, as defined in the paper; (b) the
                            same count over iterations whose simulator input
                            contains at least one mutation. Lines are means
                            over runs, bands span the minimum and maximum.
  rev_ablation.png          the same two curves for the planner variants
                            (feedback x steering).
  rev_unique_findings_venn.png
                            categories reached by exactly one fuzzer, first run
                            of each fuzzer.

No LLM API and no simulator are used.
"""

import argparse
import glob
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "evaluation" / "revision"))

import executed_settings as es  # noqa: E402
import recompute_coverage_venn as rcv  # noqa: E402

RUNS = ROOT / "evaluation/results/revision/runs"
N_CATEGORIES = 185
BUDGET = 200


CRASHED = {}  # history path -> iterations whose input crashed the simulator (bdr_replay.py)


def curves(path, categories_of):
    """Cumulative label and executed-label category counts per iteration, and both final sets."""
    label, executed, label_curve, executed_curve = set(), set(), [], []
    crashed = CRASHED.get(str(Path(path).relative_to(ROOT)), ())
    for row in es.load(Path(path))[:BUDGET]:
        ran = row.get("simulation_success") and row.get("iteration") not in crashed
        cats = categories_of(row.get("protocol_rule") or "") if ran else set()
        label |= cats
        cfg = row.get("sim_config")
        if cfg and es.mechanisms(cfg):
            executed |= cats
        label_curve.append(len(label))
        executed_curve.append(len(executed))
    return np.array(label_curve), np.array(executed_curve), label, executed


def band(ax, paths, categories_of, which, name, color, style="-"):
    data = [curves(p, categories_of)[which] for p in paths]
    n = min(len(d) for d in data)
    data = np.array([d[:n] for d in data]) / N_CATEGORIES * 100
    x = np.arange(1, n + 1)
    label = f"{name} (n={len(paths)})" if len(paths) > 1 else name
    ax.plot(x, data.mean(axis=0), style, color=color, lw=1.6, label=label)
    if len(paths) > 1:
        ax.fill_between(x, data.min(axis=0), data.max(axis=0), color=color, alpha=0.2, lw=0)


def coverage_figure(groups, categories_of, out, title_suffix=""):
    fig, axes = plt.subplots(2, 1, figsize=(3.5, 4.6), sharex=True)
    for which, ax, title in ((0, axes[0], "(a) categories of recorded labels"),
                             (1, axes[1], "(b) labels of iterations with a mutation")):
        for name, (paths, color, style) in groups.items():
            band(ax, paths, categories_of, which, name, color, style)
        ax.set_title(title + title_suffix, fontsize=8)
        ax.set_ylabel("Rule Coverage (%)", fontsize=8)
        ax.set_ylim(0, 100)
        ax.axhline(80, color="grey", lw=0.6, ls=":")
        ax.tick_params(labelsize=7)
        ax.grid(alpha=0.3, lw=0.4)
    axes[1].set_xlabel("Iteration", fontsize=8)
    axes[0].legend(fontsize=6.5, loc="upper left", frameon=False)
    fig.tight_layout()
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)


def venn_figure(panels, out):
    from matplotlib_venn import venn3
    fig, axes = plt.subplots(len(panels), 1, figsize=(3.4, 2.7 * len(panels)))
    for ax, (title, sets) in zip(np.atleast_1d(axes), panels.items()):
        names = list(sets)
        v = venn3([sets[n] for n in names], set_labels=names, ax=ax,
                  set_colors=("tab:blue", "tab:orange", "tab:green"), alpha=0.45)
        for text in v.set_labels + v.subset_labels:
            if text:
                text.set_fontsize(8)
        union = set().union(*sets.values())
        ax.set_title(f"{title}\n{N_CATEGORIES - len(union)} of {N_CATEGORIES} categories reached by no fuzzer",
                     fontsize=7)
    fig.tight_layout()
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out-dir", default=str(ROOT / "evaluation/results/revision/figures"))
    parser.add_argument("--bdr", action="append", default=[],
                        help="bdr_replay.py report whose crashed iterations are excluded (repeatable)")
    args = parser.parse_args()
    for report in args.bdr:
        for name, r in json.loads(Path(report).read_text()).items():
            CRASHED[name] = set(r.get("crashed_iterations", ()))
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    categories_of = rcv.build_matcher(json.loads((ROOT / "configs/spec_rules_filtered.json").read_text()))

    llm = sorted(glob.glob(str(RUNS / "llm_full_r*.jsonl")))
    random = sorted(glob.glob(str(RUNS / "random_s*.jsonl")))
    boofuzz = [str(RUNS / "boofuzz.jsonl")]
    coverage_figure({"LLM-guided": (llm, "tab:blue", "-"),
                     "BOOFUZZ-style": (boofuzz, "tab:orange", "-"),
                     "Random": (random, "tab:green", "-")},
                    categories_of, out / "rev_coverage_curves.png")
    coverage_figure({"Full (feedback + steering)": (llm, "tab:blue", "-"),
                     "A2: feedback only": ([str(RUNS / "llm_A2.jsonl")], "tab:purple", "--"),
                     "A1: steering only": ([str(RUNS / "llm_A1.jsonl")], "tab:red", "-."),
                     "A0: neither": ([str(RUNS / "llm_A0.jsonl")], "tab:gray", ":")},
                    categories_of, out / "rev_ablation.png")
    first = {"LLM-guided": curves(llm[0], categories_of),
             "BOOFUZZ-style": curves(boofuzz[0], categories_of),
             "Random": curves(random[0], categories_of)}
    venn_figure({"(a) categories of recorded labels": {n: c[2] for n, c in first.items()},
                 "(b) labels of iterations with a mutation": {n: c[3] for n, c in first.items()}},
                out / "rev_unique_findings_venn.png")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
