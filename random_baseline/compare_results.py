#!/usr/bin/env python3
"""
Compare LLM-Guided Fuzzer vs. Random Baseline

This script analyzes and compares the results from both fuzzers.

Usage:
    python3 random_baseline/compare_results.py \
        --llm llm_fuzzer/output/history_*.csv \
        --random random_baseline/output/random_history_*.csv
"""

import argparse
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Any


def load_results(llm_file: str, random_file: str) -> tuple:
    """Load results from both fuzzers."""
    llm_df = pd.read_csv(llm_file)
    random_df = pd.read_csv(random_file)
    
    return llm_df, random_df


def calculate_statistics(df: pd.DataFrame, name: str) -> Dict[str, Any]:
    """Calculate statistics for a fuzzer's results."""
    # Filter successful runs
    if 'simulation_success' in df.columns:
        successful = df[df['simulation_success'] == True].copy()
    else:
        successful = df.copy()
    
    if successful.empty:
        return {"name": name, "error": "No successful runs"}
    
    stats = {
        "name": name,
        "total_iterations": len(df),
        "successful_runs": len(successful),
        "success_rate": len(successful) / len(df) if len(df) > 0 else 0.0,
        
        # Reward stats
        "reward_mean": successful['reward'].mean(),
        "reward_median": successful['reward'].median(),
        "reward_std": successful['reward'].std(),
        "reward_min": successful['reward'].min(),
        "reward_max": successful['reward'].max(),
        
        # Bugs
        "bugs_found": successful['bugs_found'].sum() if 'bugs_found' in successful.columns else 0,
        
        # Coverage
        "vls_tested": len(successful['target_vl'].unique()) if 'target_vl' in successful.columns else 0,
        "rules_tested": len(successful['protocol_rule'].unique()) if 'protocol_rule' in successful.columns else 0,
        
        # Efficiency
        "avg_policing_rate": successful['policing_rate'].mean() if 'policing_rate' in successful.columns else 0.0,
        "avg_forward_rate": successful['forward_rate'].mean() if 'forward_rate' in successful.columns else 0.0,
    }
    
    return stats


def compare_statistics(llm_stats: Dict, random_stats: Dict) -> str:
    """Generate comparison report."""
    lines = []
    lines.append("=" * 80)
    lines.append("FUZZER COMPARISON: LLM-GUIDED vs. RANDOM BASELINE")
    lines.append("=" * 80)
    lines.append("")
    
    # Success rates
    lines.append("## Success Rates")
    lines.append(f"  LLM:    {llm_stats['successful_runs']}/{llm_stats['total_iterations']} "
                f"({llm_stats['success_rate']:.1%})")
    lines.append(f"  Random: {random_stats['successful_runs']}/{random_stats['total_iterations']} "
                f"({random_stats['success_rate']:.1%})")
    lines.append("")
    
    # Reward comparison
    lines.append("## Reward Statistics")
    lines.append(f"  Metric          LLM         Random      Improvement")
    lines.append(f"  Mean:           {llm_stats['reward_mean']:6.3f}      {random_stats['reward_mean']:6.3f}      "
                f"{((llm_stats['reward_mean'] - random_stats['reward_mean']) / random_stats['reward_mean'] * 100):+.1f}%")
    lines.append(f"  Median:         {llm_stats['reward_median']:6.3f}      {random_stats['reward_median']:6.3f}      "
                f"{((llm_stats['reward_median'] - random_stats['reward_median']) / random_stats['reward_median'] * 100):+.1f}%")
    lines.append(f"  Std Dev:        {llm_stats['reward_std']:6.3f}      {random_stats['reward_std']:6.3f}")
    lines.append(f"  Max:            {llm_stats['reward_max']:6.3f}      {random_stats['reward_max']:6.3f}")
    lines.append("")
    
    # Bugs
    lines.append("## Bugs Found")
    lines.append(f"  LLM:    {llm_stats['bugs_found']}")
    lines.append(f"  Random: {random_stats['bugs_found']}")
    if llm_stats['bugs_found'] > random_stats['bugs_found']:
        lines.append(f"  Winner: LLM (+{llm_stats['bugs_found'] - random_stats['bugs_found']} bugs)")
    elif random_stats['bugs_found'] > llm_stats['bugs_found']:
        lines.append(f"  Winner: Random (+{random_stats['bugs_found'] - llm_stats['bugs_found']} bugs)")
    else:
        lines.append(f"  Tie")
    lines.append("")
    
    # Coverage
    lines.append("## Coverage")
    lines.append(f"  VLs Tested:")
    lines.append(f"    LLM:    {llm_stats['vls_tested']}")
    lines.append(f"    Random: {random_stats['vls_tested']}")
    lines.append(f"  Protocol Rules Tested:")
    lines.append(f"    LLM:    {llm_stats['rules_tested']}")
    lines.append(f"    Random: {random_stats['rules_tested']}")
    lines.append("")
    
    # Efficiency
    lines.append("## Efficiency")
    lines.append(f"  Avg Policing Rate:")
    lines.append(f"    LLM:    {llm_stats['avg_policing_rate']:.1f}%")
    lines.append(f"    Random: {random_stats['avg_policing_rate']:.1f}%")
    lines.append(f"  Avg Forward Rate:")
    lines.append(f"    LLM:    {llm_stats['avg_forward_rate']:.1f}%")
    lines.append(f"    Random: {random_stats['avg_forward_rate']:.1f}%")
    lines.append("")
    
    # Statistical significance (if scipy available)
    try:
        from scipy.stats import mannwhitneyu
        
        llm_rewards = llm_stats.get('rewards', [])
        random_rewards = random_stats.get('rewards', [])
        
        if len(llm_rewards) > 0 and len(random_rewards) > 0:
            statistic, p_value = mannwhitneyu(llm_rewards, random_rewards, alternative='greater')
            lines.append("## Statistical Significance (Mann-Whitney U Test)")
            lines.append(f"  H0: LLM rewards <= Random rewards")
            lines.append(f"  H1: LLM rewards > Random rewards")
            lines.append(f"  p-value: {p_value:.4f}")
            if p_value < 0.05:
                lines.append(f"  Result: SIGNIFICANT (p < 0.05) - LLM is better!")
            else:
                lines.append(f"  Result: Not significant (p >= 0.05)")
            lines.append("")
    except ImportError:
        lines.append("## Statistical Significance")
        lines.append("  (scipy not available - install with: pip install scipy)")
        lines.append("")
    
    # Summary
    lines.append("=" * 80)
    lines.append("SUMMARY")
    lines.append("=" * 80)
    
    llm_wins = 0
    random_wins = 0
    
    if llm_stats['reward_mean'] > random_stats['reward_mean']:
        llm_wins += 1
        lines.append("  Reward (mean): LLM WINS")
    else:
        random_wins += 1
        lines.append("  Reward (mean): Random wins")
    
    if llm_stats['bugs_found'] > random_stats['bugs_found']:
        llm_wins += 1
        lines.append("  Bugs found: LLM WINS")
    elif llm_stats['bugs_found'] < random_stats['bugs_found']:
        random_wins += 1
        lines.append("  Bugs found: Random wins")
    else:
        lines.append("  Bugs found: Tie")
    
    if llm_stats['vls_tested'] > random_stats['vls_tested']:
        llm_wins += 1
        lines.append("  VL coverage: LLM WINS")
    elif llm_stats['vls_tested'] < random_stats['vls_tested']:
        random_wins += 1
        lines.append("  VL coverage: Random wins")
    else:
        lines.append("  VL coverage: Tie")
    
    if llm_stats['rules_tested'] > random_stats['rules_tested']:
        llm_wins += 1
        lines.append("  Rule coverage: LLM WINS")
    elif llm_stats['rules_tested'] < random_stats['rules_tested']:
        random_wins += 1
        lines.append("  Rule coverage: Random wins")
    else:
        lines.append("  Rule coverage: Tie")
    
    lines.append("")
    lines.append(f"OVERALL: LLM wins {llm_wins}, Random wins {random_wins}")
    
    if llm_wins > random_wins:
        lines.append("VERDICT: LLM-GUIDED FUZZER IS BETTER")
    elif random_wins > llm_wins:
        lines.append("VERDICT: RANDOM BASELINE IS BETTER (unexpected!)")
    else:
        lines.append("VERDICT: TIE (need more iterations)")
    
    lines.append("=" * 80)
    
    return "\n".join(lines)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Compare LLM-Guided Fuzzer vs. Random Baseline"
    )
    
    parser.add_argument(
        '--llm',
        type=str,
        required=True,
        help='Path to LLM fuzzer history CSV file'
    )
    
    parser.add_argument(
        '--random',
        type=str,
        required=True,
        help='Path to Random baseline history CSV file'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Output file for comparison report (default: print to stdout)'
    )
    
    args = parser.parse_args()
    
    # Load results
    print("Loading results...")
    llm_df, random_df = load_results(args.llm, args.random)
    
    print(f"  LLM:    {len(llm_df)} iterations")
    print(f"  Random: {len(random_df)} iterations")
    print()
    
    # Calculate statistics
    print("Calculating statistics...")
    llm_stats = calculate_statistics(llm_df, "LLM-Guided")
    random_stats = calculate_statistics(random_df, "Random Baseline")
    
    # Store rewards for statistical test
    if 'simulation_success' in llm_df.columns:
        llm_successful = llm_df[llm_df['simulation_success'] == True]
    else:
        llm_successful = llm_df
    
    if 'simulation_success' in random_df.columns:
        random_successful = random_df[random_df['simulation_success'] == True]
    else:
        random_successful = random_df
    
    llm_stats['rewards'] = llm_successful['reward'].tolist()
    random_stats['rewards'] = random_successful['reward'].tolist()
    
    # Generate comparison
    report = compare_statistics(llm_stats, random_stats)
    
    # Output
    if args.output:
        Path(args.output).write_text(report)
        print(f"Comparison report saved to: {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()

