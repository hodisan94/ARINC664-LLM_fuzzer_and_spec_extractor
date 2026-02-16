#!/usr/bin/env python3
"""
Generate LaTeX tables from evaluation results.
"""

import json
import sys
from pathlib import Path
from collections import Counter

def load_latest_results():
    """Load the most recent results file."""
    results_dir = Path("evaluation/results")
    if not results_dir.exists():
        print("No results directory found")
        return None
    
    # Find latest results file
    result_files = list(results_dir.glob("complete_results_*.json"))
    if not result_files:
        print("No results files found")
        return None
    
    latest = max(result_files, key=lambda p: p.stat().st_mtime)
    print(f"Loading: {latest}")
    
    with open(latest, 'r') as f:
        return json.load(f)

def generate_phase1_table(results):
    """Generate Phase 1 extraction results table."""
    p1 = results.get('phase1', {})
    
    latex = []
    latex.append("\\begin{table}[ht]")
    latex.append("\\centering")
    latex.append("\\caption{Specification Knowledge Extraction Results}")
    latex.append("\\label{tab:phase1-extraction}")
    latex.append("\\small")
    latex.append("\\begin{tabular}{lc}")
    latex.append("\\toprule")
    latex.append("\\textbf{Metric} & \\textbf{Count} \\\\")
    latex.append("\\midrule")
    latex.append(f"Protocol rules extracted & {p1.get('total_rules', 0)} \\\\")
    latex.append(f"Test cases generated & {p1.get('total_test_cases', 0)} \\\\")
    latex.append(f"Avg. test cases per rule & {p1.get('avg_test_cases_per_rule', 0):.1f} \\\\")
    latex.append("\\midrule")
    
    # Top categories
    rules_by_cat = p1.get('rules_by_category', {})
    if rules_by_cat:
        latex.append("\\multicolumn{2}{l}{\\textit{Rules by category:}} \\\\")
        for cat, count in sorted(rules_by_cat.items(), key=lambda x: x[1], reverse=True)[:5]:
            latex.append(f"\\quad {cat.replace('_', '\\_')} & {count} \\\\")
    
    latex.append("\\bottomrule")
    latex.append("\\end{tabular}")
    latex.append("\\end{table}")
    
    return "\n".join(latex)

def generate_comparison_table(results):
    """Generate fuzzer comparison table."""
    llm_cov = results.get('llm_coverage', {})
    rand_cov = results.get('random_coverage', {})
    comp = results.get('comparison', {})
    
    latex = []
    latex.append("\\begin{table}[ht]")
    latex.append("\\centering")
    latex.append("\\caption{Fuzzer Performance Comparison}")
    latex.append("\\label{tab:fuzzer-comparison}")
    latex.append("\\small")
    latex.append("\\begin{tabular}{lcc}")
    latex.append("\\toprule")
    latex.append("\\textbf{Metric} & \\textbf{LLM-Guided} & \\textbf{Random} \\\\")
    latex.append("\\midrule")
    
    # Coverage
    latex.append(f"VL coverage & {llm_cov.get('vls_tested', 0)}/8 & {rand_cov.get('vls_tested', 0)}/8 \\\\")
    latex.append(f"Mutation types & {llm_cov.get('mutation_types', 0)} & {rand_cov.get('mutation_types', 0)} \\\\")
    latex.append(f"Test cases used & {llm_cov.get('test_cases_used', 0)} & {rand_cov.get('test_cases_used', 0)} \\\\")
    latex.append(f"Custom mutations & {llm_cov.get('custom_used', 0)} & {rand_cov.get('custom_used', 0)} \\\\")
    
    latex.append("\\midrule")
    
    # Performance
    reward = comp.get('reward_comparison', {})
    latex.append(f"Avg. reward & {reward.get('llm_mean', 0):.3f} & {reward.get('random_mean', 0):.3f} \\\\")
    latex.append(f"Improvement & \\multicolumn{{2}}{{c}}{{{reward.get('improvement_pct', 0):+.1f}\\%}} \\\\")
    
    latex.append("\\bottomrule")
    latex.append("\\end{tabular}")
    latex.append("\\end{table}")
    
    return "\n".join(latex)

def generate_efficiency_table(results):
    """Generate efficiency analysis table."""
    llm_eff = results.get('llm_efficiency', {})
    rand_eff = results.get('random_efficiency', {})
    
    latex = []
    latex.append("\\begin{table}[ht]")
    latex.append("\\centering")
    latex.append("\\caption{Parameter Exploration Efficiency}")
    latex.append("\\label{tab:efficiency}")
    latex.append("\\small")
    latex.append("\\begin{tabular}{lcc}")
    latex.append("\\toprule")
    latex.append("\\textbf{Parameter} & \\textbf{LLM-Guided} & \\textbf{Random} \\\\")
    latex.append("\\midrule")
    latex.append(f"Unique BAG values & {llm_eff.get('unique_bag_values', 0)} & {rand_eff.get('unique_bag_values', 0)} \\\\")
    latex.append(f"Unique frame sizes & {llm_eff.get('unique_frame_sizes', 0)} & {rand_eff.get('unique_frame_sizes', 0)} \\\\")
    latex.append(f"Unique seq. numbers & {llm_eff.get('unique_seq_numbers', 0)} & {rand_eff.get('unique_seq_numbers', 0)} \\\\")
    latex.append("\\bottomrule")
    latex.append("\\end{tabular}")
    latex.append("\\end{table}")
    
    return "\n".join(latex)

def generate_reasoning_table(results):
    """Generate LLM reasoning distribution table."""
    reasoning = results.get('llm_reasoning', {})
    mode_dist = reasoning.get('mode_distribution', {})
    strategy_dist = reasoning.get('strategy_distribution', {})
    
    latex = []
    latex.append("\\begin{table}[ht]")
    latex.append("\\centering")
    latex.append("\\caption{LLM Decision-Making Analysis}")
    latex.append("\\label{tab:llm-reasoning}")
    latex.append("\\small")
    latex.append("\\begin{tabular}{lc}")
    latex.append("\\toprule")
    latex.append("\\textbf{Decision Mode} & \\textbf{Count (\\%)} \\\\")
    latex.append("\\midrule")
    
    total = sum(mode_dist.values())
    for mode, count in sorted(mode_dist.items(), key=lambda x: x[1], reverse=True):
        pct = (count / total * 100) if total > 0 else 0
        mode_name = mode.replace('_', ' ').title()
        latex.append(f"{mode_name} & {count} ({pct:.1f}\\%) \\\\")
    
    latex.append("\\midrule")
    latex.append("\\multicolumn{2}{l}{\\textit{Strategy distribution:}} \\\\")
    
    for strategy, count in sorted(strategy_dist.items(), key=lambda x: x[1], reverse=True):
        pct = (count / total * 100) if total > 0 else 0
        latex.append(f"\\quad {strategy.replace('_', '-')} & {count} ({pct:.1f}\\%) \\\\")
    
    latex.append("\\bottomrule")
    latex.append("\\end{tabular}")
    latex.append("\\end{table}")
    
    return "\n".join(latex)

def main():
    results = load_latest_results()
    if not results:
        print("No results to process")
        return
    
    output_dir = Path("evaluation/results")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate all tables
    tables = []
    tables.append(generate_phase1_table(results))
    tables.append("")
    tables.append(generate_comparison_table(results))
    tables.append("")
    tables.append(generate_efficiency_table(results))
    tables.append("")
    tables.append(generate_reasoning_table(results))
    
    # Save
    output_file = output_dir / "latex_tables.tex"
    with open(output_file, 'w') as f:
        f.write('\n'.join(tables))
    
    print(f"\n✓ LaTeX tables saved to: {output_file}")
    print("\nYou can now include these tables in your paper!")

if __name__ == "__main__":
    main()

