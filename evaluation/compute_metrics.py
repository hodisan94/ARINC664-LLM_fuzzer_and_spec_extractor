#!/usr/bin/env python3
"""
Tier 1 Evaluation Metrics — compute_metrics.py

Computes all Tier 1 metrics from iteration_history.jsonl files and test_cases.json:
  1. Rule Coverage (cumulative)
  2. Time to Coverage (80% / 100%)
  3. Redundancy Ratio
  4. Violation Diversity (Shannon Entropy)
  5. Unique Findings (Venn Diagram)
  6. Reward Convergence (Moving Average)

Outputs:
  - Console summary
  - evaluation/results/metrics_report.json
  - evaluation/results/figures/*.png
"""

import sys
import json
import math
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Set
from collections import Counter

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).parent.parent))

FIGURES_DIR = Path("evaluation/results/figures")
RESULTS_DIR = Path("evaluation/results")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_jsonl(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return pd.DataFrame(records) if records else pd.DataFrame()


def get_rule_field(df: pd.DataFrame) -> pd.Series:
    """Return the column that identifies which rule was targeted, regardless of fuzzer format."""
    if "protocol_rule" in df.columns:
        return df["protocol_rule"].fillna("unknown")
    if "mutation_type" in df.columns:
        return df["mutation_type"].fillna("unknown")
    return pd.Series(["unknown"] * len(df), index=df.index)


def get_violation_field(df: pd.DataFrame) -> pd.Series:
    """Return the column that identifies the violation type."""
    if "violation_type" in df.columns:
        return df["violation_type"].fillna("unknown")
    if "strategy" in df.columns:
        return df["strategy"].fillna("unknown")
    return pd.Series(["unknown"] * len(df), index=df.index)


def load_all(
    llm_path: str,
    random_path: str,
    boofuzz_path: str,
) -> Dict[str, pd.DataFrame]:
    return {
        "LLM": load_jsonl(Path(llm_path)),
        "Random": load_jsonl(Path(random_path)),
        "Boofuzz": load_jsonl(Path(boofuzz_path)),
    }


# ---------------------------------------------------------------------------
# Metric 1 — Rule Coverage (cumulative)
# ---------------------------------------------------------------------------

def cumulative_rule_coverage(df: pd.DataFrame, total_rules: int) -> List[float]:
    """Return a list of cumulative coverage fractions, one per iteration."""
    rules = get_rule_field(df)
    seen: Set[str] = set()
    curve = []
    for r in rules:
        seen.add(r)
        curve.append(len(seen) / total_rules)
    return curve


def plot_rule_coverage(
    curves: Dict[str, List[float]],
    total_rules: int,
    out_path: Path,
):
    fig, ax = plt.subplots(figsize=(10, 6))
    colors = {"LLM": "#2563eb", "Random": "#f59e0b", "Boofuzz": "#10b981"}
    for name, curve in curves.items():
        if not curve:
            continue
        ax.plot(
            range(1, len(curve) + 1),
            [c * 100 for c in curve],
            label=name,
            linewidth=2.2,
            color=colors.get(name, None),
        )
    ax.set_xlabel("Iteration", fontsize=13)
    ax.set_ylabel("Cumulative Rule Coverage (%)", fontsize=13)
    ax.set_title(f"Rule Coverage Over Time (total rules = {total_rules})", fontsize=14)
    ax.legend(fontsize=12)
    ax.grid(True, alpha=0.3)
    ax.set_ylim(0, 105)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path}")


# ---------------------------------------------------------------------------
# Metric 2 — Time to Coverage (80% / 100%)
# ---------------------------------------------------------------------------

def time_to_coverage(curve: List[float], thresholds: List[float] = [0.8, 1.0]) -> Dict[str, Any]:
    result = {}
    for t in thresholds:
        label = f"{int(t*100)}%"
        hit = None
        for i, v in enumerate(curve):
            if v >= t:
                hit = i + 1
                break
        result[label] = hit
    result["max_coverage"] = curve[-1] if curve else 0.0
    return result


# ---------------------------------------------------------------------------
# Metric 3 — Redundancy Ratio
# ---------------------------------------------------------------------------

def compute_redundancy(test_cases_path: str) -> Dict[str, Any]:
    with open(test_cases_path) as f:
        tc = json.load(f)

    total = 0
    duplicates = 0
    param_stats = {}

    for param, data in tc.items():
        cases = data.get("test_cases", [])
        if not cases:
            continue

        signatures = []
        for c in cases:
            val = c.get("value")
            vtype = c.get("violation_type", "")
            sig = (str(val), vtype)
            signatures.append(sig)

        total += len(signatures)
        unique = set(signatures)
        param_dups = len(signatures) - len(unique)
        duplicates += param_dups

        if param_dups > 0:
            param_stats[param] = {
                "total": len(signatures),
                "unique": len(unique),
                "duplicates": param_dups,
            }

    ratio = duplicates / total if total > 0 else 0.0
    return {
        "total_test_cases": total,
        "duplicate_test_cases": duplicates,
        "redundancy_ratio": ratio,
        "redundancy_percent": f"{ratio * 100:.1f}%",
        "params_with_duplicates": len(param_stats),
        "top_redundant_params": dict(
            sorted(param_stats.items(), key=lambda x: -x[1]["duplicates"])[:10]
        ),
    }


# ---------------------------------------------------------------------------
# Metric 4 — Violation Diversity (Shannon Entropy)
# ---------------------------------------------------------------------------

def shannon_entropy(counts: Counter) -> float:
    total = sum(counts.values())
    if total == 0:
        return 0.0
    probs = [c / total for c in counts.values()]
    return -sum(p * math.log2(p) for p in probs if p > 0)


def violation_diversity(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {"entropy": 0.0, "max_entropy": 0.0, "normalized_entropy": 0.0, "n_types": 0, "top_5": []}

    rules = get_rule_field(df)
    counts = Counter(rules)
    h = shannon_entropy(counts)
    n = len(counts)
    h_max = math.log2(n) if n > 1 else 0.0
    normalized = h / h_max if h_max > 0 else 0.0

    return {
        "entropy": round(h, 4),
        "max_entropy": round(h_max, 4),
        "normalized_entropy": round(normalized, 4),
        "n_types": n,
        "top_5": counts.most_common(5),
    }


def plot_diversity(diversities: Dict[str, Dict], out_path: Path):
    names = [n for n in diversities if diversities[n]["n_types"] > 0]
    if not names:
        return
    norm = [diversities[n]["normalized_entropy"] for n in names]
    colors = {"LLM": "#2563eb", "Random": "#f59e0b", "Boofuzz": "#10b981"}

    fig, ax = plt.subplots(figsize=(7, 5))
    bars = ax.bar(names, norm, color=[colors.get(n, "#888") for n in names], width=0.5)
    for bar, val in zip(bars, norm):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02,
                f"{val:.2f}", ha="center", fontsize=12)
    ax.set_ylabel("Normalized Shannon Entropy", fontsize=13)
    ax.set_title("Violation Diversity (higher = more diverse)", fontsize=14)
    ax.set_ylim(0, 1.15)
    ax.grid(True, alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path}")


# ---------------------------------------------------------------------------
# Metric 5 — Unique Findings (Venn Diagram)
# ---------------------------------------------------------------------------

def normalize_rule_name(raw: str) -> str:
    """Normalize a rule name to a canonical form for cross-fuzzer comparison.

    Steps:
      1. Lowercase
      2. Replace spaces, dots, hyphens with underscores
      3. Collapse repeated underscores
      4. Strip leading/trailing underscores
    This maps 'Frame Filtering.destination_address_validity',
    'frame_filtering_destination_address_validity', and
    'Destination Address Validity' to comparable forms.
    """
    s = raw.lower().replace(" ", "_").replace(".", "_").replace("-", "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")


def build_finding_set(df: pd.DataFrame) -> Set[str]:
    """Build a set of normalized rule names from history (for overlap/Venn)."""
    if df.empty:
        return set()
    rules = get_rule_field(df)
    return {normalize_rule_name(r) for r in rules}


def build_detailed_finding_set(df: pd.DataFrame) -> Set[str]:
    """Build a set of (rule|violation_type) strings for per-fuzzer listing."""
    if df.empty:
        return set()
    rules = get_rule_field(df)
    violations = get_violation_field(df)
    return {f"{r}|{v}" for r, v in zip(rules, violations)}


def compute_venn_data(sets: Dict[str, Set[str]]) -> Dict[str, Any]:
    names = list(sets.keys())
    result = {}
    for n in names:
        others = set()
        for m in names:
            if m != n:
                others |= sets[m]
        only = sets[n] - others
        result[f"{n}_only"] = sorted(only)
        result[f"{n}_only_count"] = len(only)

    if len(names) >= 2:
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                shared = sets[names[i]] & sets[names[j]]
                key = f"{names[i]}_and_{names[j]}"
                result[key] = len(shared)

    if len(names) == 3:
        all_shared = sets[names[0]] & sets[names[1]] & sets[names[2]]
        result["all_three"] = len(all_shared)

    for n in names:
        result[f"{n}_total"] = len(sets[n])

    return result


def plot_venn(sets: Dict[str, Set[str]], out_path: Path):
    try:
        from matplotlib_venn import venn3, venn3_circles, venn2
    except ImportError:
        print("  [SKIP] matplotlib-venn not installed, skipping Venn diagram")
        return

    fig, ax = plt.subplots(figsize=(9, 7))

    active = {k: v for k, v in sets.items() if v}
    names = list(active.keys())

    if len(names) == 3:
        v = venn3(
            [active[n] for n in names],
            set_labels=names,
            ax=ax,
        )
        venn3_circles(
            [active[n] for n in names],
            linewidth=1.5,
            ax=ax,
        )
    elif len(names) == 2:
        v = venn2(
            [active[n] for n in names],
            set_labels=names,
            ax=ax,
        )
    else:
        plt.close(fig)
        return

    ax.set_title("Unique Rule-Violation Findings per Fuzzer", fontsize=14)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path}")


# ---------------------------------------------------------------------------
# Metric 6 — Reward Convergence (Moving Average)
# ---------------------------------------------------------------------------

def reward_moving_average(df: pd.DataFrame, window: int = 5) -> List[float]:
    if df.empty or "reward" not in df.columns:
        return []
    rewards = df["reward"].tolist()
    if len(rewards) < window:
        window = max(1, len(rewards))
    ma = pd.Series(rewards).rolling(window=window, min_periods=1).mean().tolist()
    return ma


def compute_base_reward(df: pd.DataFrame, new_rule_bonus: float = 1.0) -> List[float]:
    """Compute reward with exploration bonus removed.

    For each iteration, if the protocol_rule appears for the first time
    in history up to that point, subtract ``new_rule_bonus`` from the reward.
    This gives the "base" reward that reflects actual fuzzing impact only.
    """
    if df.empty or "reward" not in df.columns:
        return []
    rules = get_rule_field(df)
    rewards = df["reward"].tolist()

    seen: set = set()
    base = []
    for rule, reward in zip(rules, rewards):
        norm = normalize_rule_name(str(rule))
        if norm not in seen:
            seen.add(norm)
            base.append(reward - new_rule_bonus)
        else:
            base.append(reward)
    return base


def plot_reward_convergence(
    ma_curves: Dict[str, List[float]],
    out_path: Path,
    window: int = 5,
    base_ma_curves: Optional[Dict[str, List[float]]] = None,
):
    fig, ax = plt.subplots(figsize=(10, 6))
    colors = {"LLM": "#2563eb", "Random": "#f59e0b", "Boofuzz": "#10b981"}
    for name, ma in ma_curves.items():
        if not ma:
            continue
        ax.plot(
            range(1, len(ma) + 1),
            ma,
            label=f"{name} (total)",
            linewidth=2.2,
            color=colors.get(name, None),
        )
        if base_ma_curves and name in base_ma_curves and base_ma_curves[name]:
            bma = base_ma_curves[name]
            ax.plot(
                range(1, len(bma) + 1),
                bma,
                label=f"{name} (base, excl. exploration bonus)",
                linewidth=1.5,
                color=colors.get(name, None),
                linestyle="--",
                alpha=0.7,
            )
    ax.set_xlabel("Iteration", fontsize=13)
    ax.set_ylabel(f"Reward (rolling avg, window={window})", fontsize=13)
    ax.set_title("Reward Convergence — Learning Curve", fontsize=14)
    ax.legend(fontsize=10, loc="best")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path}")


# ---------------------------------------------------------------------------
# Metric 7 — Ratio of Valid Messages (proxy)
# ---------------------------------------------------------------------------

def ratio_valid_messages(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Proxy for R_valid: use simulator data to estimate what fraction of
    fuzzer-generated frames were structurally valid enough to be processed.

    Two sub-metrics:
      - injection_success_rate: fraction of iterations where the simulator
        successfully processed the fuzzer's input (simulation_success=True
        and frames_received > 0).
      - avg_forward_rate: among successful iterations, what fraction of
        frames passed through without being dropped by policing. High values
        mean the frames were "too valid" (no violations detected); low values
        mean violations were triggered — which is the goal.
    """
    if df.empty:
        return {"error": "No data"}

    n = len(df)

    # Injection success: did the simulator accept and run the input?
    if "simulation_success" in df.columns:
        success_mask = df["simulation_success"].astype(bool)
    else:
        success_mask = pd.Series([True] * n, index=df.index)

    has_frames = pd.Series([True] * n, index=df.index)
    if "frames_received" in df.columns:
        has_frames = df["frames_received"].fillna(0) > 0

    valid_mask = success_mask & has_frames
    injection_success = valid_mask.sum() / n if n > 0 else 0.0

    # Among valid iterations: average forward rate
    valid_df = df[valid_mask]
    avg_forward = 0.0
    avg_policing = 0.0
    if not valid_df.empty:
        if "forward_rate" in valid_df.columns:
            avg_forward = float(valid_df["forward_rate"].mean())
        if "policing_rate" in valid_df.columns:
            avg_policing = float(valid_df["policing_rate"].mean())

    return {
        "total_iterations": n,
        "successful_injections": int(valid_mask.sum()),
        "injection_success_rate": round(injection_success, 4),
        "injection_success_percent": f"{injection_success * 100:.1f}%",
        "avg_forward_rate": round(avg_forward, 2),
        "avg_policing_rate": round(avg_policing, 2),
        "interpretation": (
            "High injection success = frames are structurally valid. "
            "High policing rate = frames trigger rule violations (good for fuzzer). "
            "High forward rate = frames pass unchallenged (fuzzer not finding violations)."
        ),
    }


# ---------------------------------------------------------------------------
# Metric 8 — Cost-Effectiveness
# ---------------------------------------------------------------------------

def cost_effectiveness(
    data: Dict[str, pd.DataFrame],
    finding_sets: Dict[str, Set[str]],
    cost_per_call: float,
) -> Dict[str, Any]:
    """
    Compare cost per unique finding across fuzzers.

    LLM fuzzer makes 1 API call per iteration (strategy planning).
    Random and Boofuzz make 0 API calls.
    """
    results = {}

    for name, df in data.items():
        if df.empty:
            results[name] = {"error": "No data"}
            continue

        n_iterations = len(df)
        findings = finding_sets.get(name, set())
        n_findings = len(findings)

        is_llm = name.lower() == "llm"
        api_calls = n_iterations if is_llm else 0
        total_cost = api_calls * cost_per_call

        cost_per_finding = total_cost / n_findings if n_findings > 0 else None
        cost_per_iteration = total_cost / n_iterations if n_iterations > 0 else 0.0
        findings_per_dollar = n_findings / total_cost if total_cost > 0 else float("inf")

        results[name] = {
            "iterations": n_iterations,
            "api_calls": api_calls,
            "cost_per_call_usd": cost_per_call if is_llm else 0.0,
            "total_cost_usd": round(total_cost, 4),
            "unique_findings": n_findings,
            "cost_per_finding_usd": round(cost_per_finding, 4) if cost_per_finding is not None else None,
            "findings_per_dollar": round(findings_per_dollar, 1) if findings_per_dollar != float("inf") else "inf (free)",
            "cost_per_iteration_usd": round(cost_per_iteration, 4),
        }

    return results


def plot_cost_effectiveness(ce_data: Dict[str, Dict], out_path: Path):
    names = [n for n in ce_data if "error" not in ce_data[n] and ce_data[n]["unique_findings"] > 0]
    if not names:
        return

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5))
    colors = {"LLM": "#2563eb", "Random": "#f59e0b", "Boofuzz": "#10b981"}

    # Left: unique findings
    findings = [ce_data[n]["unique_findings"] for n in names]
    bars1 = ax1.bar(names, findings, color=[colors.get(n, "#888") for n in names], width=0.5)
    for bar, val in zip(bars1, findings):
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                 str(val), ha="center", fontsize=12, fontweight="bold")
    ax1.set_ylabel("Unique Findings", fontsize=13)
    ax1.set_title("Unique Findings per Fuzzer", fontsize=14)
    ax1.grid(True, alpha=0.3, axis="y")

    # Right: total cost
    costs = [ce_data[n]["total_cost_usd"] for n in names]
    bars2 = ax2.bar(names, costs, color=[colors.get(n, "#888") for n in names], width=0.5)
    for bar, val in zip(bars2, costs):
        label = f"${val:.3f}" if val > 0 else "Free"
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.001,
                 label, ha="center", fontsize=12, fontweight="bold")
    ax2.set_ylabel("Total Cost (USD)", fontsize=13)
    ax2.set_title("API Cost per Fuzzer", fontsize=14)
    ax2.grid(True, alpha=0.3, axis="y")

    fig.suptitle("Cost-Effectiveness Comparison", fontsize=15, y=1.02)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Compute Tier 1 + Tier 2 evaluation metrics")
    parser.add_argument("--llm-history", default="llm_fuzzer/data/iteration_history.jsonl")
    parser.add_argument("--random-history", default="random_baseline/data/iteration_history.jsonl")
    parser.add_argument("--boofuzz-history", default="boofuzz_baseline/data/iteration_history.jsonl")
    parser.add_argument("--test-cases", default="configs/test_cases.json")
    parser.add_argument("--spec-rules", default="configs/spec_rules_filtered.json")
    parser.add_argument("--window", type=int, default=5, help="Moving average window size")
    parser.add_argument("--cost-per-call", type=float, default=0.015,
                        help="Estimated USD cost per LLM API call (default: $0.015 for GPT-4o)")
    args = parser.parse_args()

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Load spec rules to get total count
    with open(args.spec_rules) as f:
        spec_rules = json.load(f)
    total_rules = len(spec_rules)
    print(f"Total filtered rules: {total_rules}")

    # Load fuzzer histories
    data = load_all(args.llm_history, args.random_history, args.boofuzz_history)
    for name, df in data.items():
        print(f"{name}: {len(df)} iterations loaded")

    report: Dict[str, Any] = {
        "generated": datetime.now().isoformat(),
        "total_rules": total_rules,
        "iterations": {n: len(df) for n, df in data.items()},
    }

    # -----------------------------------------------------------------------
    # Metric 1 — Rule Coverage
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("METRIC 1: Rule Coverage (Cumulative)")
    print("=" * 60)

    coverage_curves = {}
    coverage_results = {}
    for name, df in data.items():
        if df.empty:
            continue
        curve = cumulative_rule_coverage(df, total_rules)
        coverage_curves[name] = curve
        final = curve[-1] if curve else 0
        n_unique = int(final * total_rules)
        print(f"  {name}: {n_unique} unique rules / {total_rules} = {final*100:.1f}%")
        coverage_results[name] = {
            "unique_rules_tested": n_unique,
            "coverage_percent": round(final * 100, 1),
        }

    if coverage_curves:
        plot_rule_coverage(coverage_curves, total_rules, FIGURES_DIR / "rule_coverage.png")
    report["rule_coverage"] = coverage_results

    # -----------------------------------------------------------------------
    # Metric 2 — Time to Coverage
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("METRIC 2: Time to Coverage")
    print("=" * 60)

    ttc_results = {}
    for name, curve in coverage_curves.items():
        ttc = time_to_coverage(curve)
        ttc_results[name] = ttc
        max_cov = ttc["max_coverage"]
        print(f"  {name}: max={max_cov*100:.1f}%, "
              f"iter@80%={ttc['80%'] or 'N/A'}, "
              f"iter@100%={ttc['100%'] or 'N/A'}")
    report["time_to_coverage"] = ttc_results

    # -----------------------------------------------------------------------
    # Metric 3 — Redundancy Ratio
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("METRIC 3: Redundancy Ratio (test_cases.json)")
    print("=" * 60)

    redundancy = compute_redundancy(args.test_cases)
    print(f"  Total test cases: {redundancy['total_test_cases']}")
    print(f"  Duplicates: {redundancy['duplicate_test_cases']}")
    print(f"  Redundancy: {redundancy['redundancy_percent']}")
    print(f"  Parameters with duplicates: {redundancy['params_with_duplicates']}")
    if redundancy["top_redundant_params"]:
        print("  Top redundant parameters:")
        for param, stats in list(redundancy["top_redundant_params"].items())[:5]:
            print(f"    {param}: {stats['duplicates']} duplicates / {stats['total']} cases")
    report["redundancy_ratio"] = redundancy

    # -----------------------------------------------------------------------
    # Metric 4 — Violation Diversity
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("METRIC 4: Violation Diversity (Shannon Entropy)")
    print("=" * 60)

    diversities = {}
    for name, df in data.items():
        div = violation_diversity(df)
        diversities[name] = div
        print(f"  {name}: H={div['entropy']:.3f}, "
              f"H_norm={div['normalized_entropy']:.3f}, "
              f"types={div['n_types']}")
        if div["top_5"]:
            for rule, cnt in div["top_5"]:
                print(f"    {rule}: {cnt}")

    if diversities:
        plot_diversity(diversities, FIGURES_DIR / "violation_diversity.png")

    serializable_div = {}
    for name, div in diversities.items():
        d = dict(div)
        d["top_5"] = [{"rule": r, "count": c} for r, c in div.get("top_5", [])]
        serializable_div[name] = d
    report["violation_diversity"] = serializable_div

    # -----------------------------------------------------------------------
    # Metric 5 — Unique Findings (Venn)
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("METRIC 5: Unique Findings (Venn Diagram)")
    print("=" * 60)

    finding_sets = {name: build_finding_set(df) for name, df in data.items()}
    detailed_sets = {name: build_detailed_finding_set(df) for name, df in data.items()}
    venn_data = compute_venn_data(finding_sets)

    for name in data:
        total_f = venn_data.get(f"{name}_total", 0)
        only_f = venn_data.get(f"{name}_only_count", 0)
        print(f"  {name}: {total_f} total findings, {only_f} unique to {name}")

    if "all_three" in venn_data:
        print(f"  Shared by all three: {venn_data['all_three']}")
    for i, ni in enumerate(list(data.keys())):
        for nj in list(data.keys())[i+1:]:
            key = f"{ni}_and_{nj}"
            if key in venn_data:
                print(f"  Shared {ni} & {nj}: {venn_data[key]}")

    if finding_sets:
        plot_venn(finding_sets, FIGURES_DIR / "unique_findings_venn.png")

    venn_serializable = {k: v for k, v in venn_data.items() if not k.endswith("_only") or k.endswith("_only_count")}
    for name in data:
        key = f"{name}_only"
        if key in venn_data:
            venn_serializable[key] = venn_data[key][:20]
        detail_key = f"{name}_detailed"
        venn_serializable[detail_key] = sorted(detailed_sets.get(name, set()))[:20]
    report["unique_findings"] = venn_serializable

    # -----------------------------------------------------------------------
    # Metric 6 — Reward Convergence
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("METRIC 6: Reward Convergence (Moving Average)")
    print("=" * 60)

    ma_curves = {}
    base_ma_curves = {}
    convergence_results = {}
    for name, df in data.items():
        ma = reward_moving_average(df, window=args.window)
        ma_curves[name] = ma

        base_rewards = compute_base_reward(df)
        if base_rewards:
            base_ma = pd.Series(base_rewards).rolling(
                window=min(args.window, max(1, len(base_rewards))),
                min_periods=1
            ).mean().tolist()
        else:
            base_ma = []
        base_ma_curves[name] = base_ma

        if ma:
            first_half = ma[: len(ma) // 2] if len(ma) >= 4 else ma
            second_half = ma[len(ma) // 2 :] if len(ma) >= 4 else ma
            early = np.mean(first_half)
            late = np.mean(second_half)
            improvement = ((late - early) / abs(early) * 100) if early != 0 else 0

            base_early = np.mean(base_ma[: len(base_ma) // 2]) if len(base_ma) >= 4 else (np.mean(base_ma) if base_ma else 0)
            base_late = np.mean(base_ma[len(base_ma) // 2 :]) if len(base_ma) >= 4 else (np.mean(base_ma) if base_ma else 0)
            base_improvement = ((base_late - base_early) / abs(base_early) * 100) if base_early != 0 else 0

            convergence_results[name] = {
                "early_mean_reward": round(float(early), 4),
                "late_mean_reward": round(float(late), 4),
                "improvement_percent": round(float(improvement), 1),
                "final_ma": round(ma[-1], 4),
                "base_early_mean": round(float(base_early), 4),
                "base_late_mean": round(float(base_late), 4),
                "base_improvement_percent": round(float(base_improvement), 1),
            }
            print(f"  {name}: early={early:.3f}, late={late:.3f}, "
                  f"improvement={improvement:+.1f}%, final_ma={ma[-1]:.3f}")
            print(f"    base (excl. exploration bonus): early={base_early:.3f}, "
                  f"late={base_late:.3f}, improvement={base_improvement:+.1f}%")

    if ma_curves:
        plot_reward_convergence(ma_curves, FIGURES_DIR / "reward_convergence.png",
                                args.window, base_ma_curves)
    report["reward_convergence"] = convergence_results

    # -----------------------------------------------------------------------
    # Metric 7 — Ratio of Valid Messages (proxy)
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("METRIC 7: Ratio of Valid Messages (proxy)")
    print("=" * 60)

    rvm_results = {}
    for name, df in data.items():
        rvm = ratio_valid_messages(df)
        rvm_results[name] = rvm
        if "error" not in rvm:
            print(f"  {name}: injection_success={rvm['injection_success_percent']}, "
                  f"avg_policing={rvm['avg_policing_rate']:.1f}%, "
                  f"avg_forward={rvm['avg_forward_rate']:.1f}%")
    report["ratio_valid_messages"] = rvm_results

    # -----------------------------------------------------------------------
    # Metric 8 — Cost-Effectiveness
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("METRIC 8: Cost-Effectiveness")
    print("=" * 60)

    ce_results = cost_effectiveness(data, finding_sets, args.cost_per_call)
    for name, ce in ce_results.items():
        if "error" in ce:
            continue
        cost_str = f"${ce['total_cost_usd']:.3f}" if ce['total_cost_usd'] > 0 else "Free"
        cpf = f"${ce['cost_per_finding_usd']:.4f}" if ce['cost_per_finding_usd'] is not None else "N/A"
        print(f"  {name}: {ce['unique_findings']} findings, "
              f"cost={cost_str}, per_finding={cpf}")

    if ce_results:
        plot_cost_effectiveness(ce_results, FIGURES_DIR / "cost_effectiveness.png")
    report["cost_effectiveness"] = ce_results

    # -----------------------------------------------------------------------
    # Metric 9 — Effective Mutation Rate (NEW)
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("METRIC 9: Effective Mutation Rate")
    print("=" * 60)
    print("  (Counts iterations where policing_rate differs from baseline ~74.5%)")

    BASELINE_POLICING = 74.53
    TOLERANCE = 0.5
    effective_results = {}
    for name, df in data.items():
        if df.empty or "policing_rate" not in df.columns:
            effective_results[name] = {"error": "No policing data"}
            continue
        rates = df["policing_rate"].dropna()
        total = len(rates)
        effective = int(((rates - BASELINE_POLICING).abs() > TOLERANCE).sum())
        zero_frame_count = int((df.get("num_frames", pd.Series([1]*total)) == 0).sum()) if "num_frames" in df.columns else 0
        effective_results[name] = {
            "total_iterations": total,
            "effective_mutations": effective,
            "effective_rate_percent": round(effective / total * 100, 1) if total > 0 else 0,
            "zero_frame_iterations": zero_frame_count,
            "baseline_policing": BASELINE_POLICING,
            "tolerance": TOLERANCE,
        }
        print(f"  {name}: {effective}/{total} effective ({effective_results[name]['effective_rate_percent']}%), "
              f"zero-frame iters: {zero_frame_count}")
    report["effective_mutation_rate"] = effective_results

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Rule Coverage:       see evaluation/results/figures/rule_coverage.png")
    print(f"  Time to Coverage:    see report JSON")
    print(f"  Redundancy Ratio:    {redundancy['redundancy_percent']}")
    for name in data:
        if name in diversities:
            print(f"  Diversity ({name}):   H_norm = {diversities[name]['normalized_entropy']:.3f}")
    print(f"  Unique Findings:     see evaluation/results/figures/unique_findings_venn.png")
    print(f"  Reward Convergence:  see evaluation/results/figures/reward_convergence.png")
    print(f"  Valid Messages:      see report JSON")
    print(f"  Cost-Effectiveness:  see evaluation/results/figures/cost_effectiveness.png")

    # Save JSON report
    report_path = RESULTS_DIR / "metrics_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n  Full report saved: {report_path}")


if __name__ == "__main__":
    main()
