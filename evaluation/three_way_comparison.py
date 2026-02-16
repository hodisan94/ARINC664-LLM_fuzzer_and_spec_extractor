#!/usr/bin/env python3
"""
Three-Way Fuzzer Comparison: LLM vs boofuzz vs Random

This script provides comprehensive comparison between all three fuzzers:
1. LLM-Guided Fuzzer - Intelligent, learning-based selection
2. boofuzz Baseline - Deterministic, exhaustive testing
3. Random Baseline - Pure random selection

The comparison uses the SAME metrics for fair evaluation.
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from collections import defaultdict
import pandas as pd
import numpy as np

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class ThreeWayComparison:
    """
    Comprehensive comparison of three fuzzing approaches.
    """
    
    def __init__(
        self,
        llm_history_path: str = "llm_fuzzer/data/iteration_history.jsonl",
        boofuzz_history_path: str = "boofuzz_baseline/data/iteration_history.jsonl",
        random_history_path: str = "random_baseline/data/iteration_history.jsonl",
        output_dir: str = "evaluation/results"
    ):
        """
        Initialize comparison.
        
        Args:
            llm_history_path: Path to LLM fuzzer history
            boofuzz_history_path: Path to boofuzz history
            random_history_path: Path to random fuzzer history
            output_dir: Output directory for reports
        """
        self.llm_history_path = Path(llm_history_path)
        self.boofuzz_history_path = Path(boofuzz_history_path)
        self.random_history_path = Path(random_history_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Load data
        self.llm_df = self._load_history(self.llm_history_path, "LLM")
        self.boofuzz_df = self._load_history(self.boofuzz_history_path, "boofuzz")
        self.random_df = self._load_history(self.random_history_path, "Random")
    
    def _load_history(self, path: Path, name: str) -> pd.DataFrame:
        """Load history from JSONL file."""
        if not path.exists():
            print(f"Warning: {name} history not found at {path}")
            return pd.DataFrame()
        
        records = []
        with open(path, 'r') as f:
            for line in f:
                if line.strip():
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        
        if records:
            df = pd.DataFrame(records)
            df['fuzzer'] = name
            return df
        
        return pd.DataFrame()
    
    def compare_all(self) -> Dict[str, Any]:
        """
        Run comprehensive comparison of all three fuzzers.
        
        Returns:
            Complete comparison results
        """
        print("=" * 70)
        print("THREE-WAY FUZZER COMPARISON")
        print("=" * 70)
        
        results = {}
        
        # 1. Basic statistics
        results['basic_stats'] = self._compare_basic_stats()
        
        # 2. Reward analysis
        results['reward_analysis'] = self._compare_rewards()
        
        # 3. Coverage analysis
        results['coverage_analysis'] = self._compare_coverage()
        
        # 4. Efficiency analysis
        results['efficiency_analysis'] = self._compare_efficiency()
        
        # 5. Learning curve (LLM only)
        results['learning_curve'] = self._analyze_learning_curve()
        
        # 6. Violation detection
        results['violation_detection'] = self._compare_violation_detection()
        
        # 7. Statistical significance
        results['statistical_tests'] = self._run_statistical_tests()
        
        # Generate reports
        self._generate_text_report(results)
        self._generate_json_report(results)
        self._generate_latex_table(results)
        
        return results
    
    def _compare_basic_stats(self) -> Dict[str, Any]:
        """Compare basic statistics."""
        print("\n## Basic Statistics")
        
        stats = {}
        
        for name, df in [('LLM', self.llm_df), 
                         ('boofuzz', self.boofuzz_df), 
                         ('Random', self.random_df)]:
            if df.empty:
                stats[name] = {'error': 'No data'}
                continue
            
            stats[name] = {
                'total_iterations': len(df),
                'successful_iterations': len(df[df.get('simulation_success', True) == True]) if 'simulation_success' in df.columns else len(df),
                'success_rate': 100.0,  # Will be calculated
            }
            
            if 'simulation_success' in df.columns:
                stats[name]['success_rate'] = (df['simulation_success'].sum() / len(df)) * 100
            
            print(f"  {name}: {stats[name]['total_iterations']} iterations")
        
        return stats
    
    def _compare_rewards(self) -> Dict[str, Any]:
        """Compare reward statistics."""
        print("\n## Reward Analysis")
        
        rewards = {}
        
        for name, df in [('LLM', self.llm_df), 
                         ('boofuzz', self.boofuzz_df), 
                         ('Random', self.random_df)]:
            if df.empty or 'reward' not in df.columns:
                rewards[name] = {'error': 'No reward data'}
                continue
            
            reward_col = df['reward'].dropna()
            
            rewards[name] = {
                'mean': float(reward_col.mean()),
                'median': float(reward_col.median()),
                'std': float(reward_col.std()),
                'min': float(reward_col.min()),
                'max': float(reward_col.max()),
                'q25': float(reward_col.quantile(0.25)),
                'q75': float(reward_col.quantile(0.75))
            }
            
            print(f"  {name}: mean={rewards[name]['mean']:.3f}, "
                  f"max={rewards[name]['max']:.3f}")
        
        # Calculate improvements
        if 'LLM' in rewards and 'Random' in rewards:
            if 'error' not in rewards['LLM'] and 'error' not in rewards['Random']:
                if rewards['Random']['mean'] != 0:
                    llm_vs_random = ((rewards['LLM']['mean'] - rewards['Random']['mean']) / 
                                    abs(rewards['Random']['mean'])) * 100
                    rewards['llm_vs_random_improvement'] = llm_vs_random
                    print(f"\n  LLM vs Random: {llm_vs_random:+.1f}%")
        
        if 'LLM' in rewards and 'boofuzz' in rewards:
            if 'error' not in rewards['LLM'] and 'error' not in rewards['boofuzz']:
                if rewards['boofuzz']['mean'] != 0:
                    llm_vs_boofuzz = ((rewards['LLM']['mean'] - rewards['boofuzz']['mean']) / 
                                     abs(rewards['boofuzz']['mean'])) * 100
                    rewards['llm_vs_boofuzz_improvement'] = llm_vs_boofuzz
                    print(f"  LLM vs boofuzz: {llm_vs_boofuzz:+.1f}%")
        
        return rewards
    
    def _compare_coverage(self) -> Dict[str, Any]:
        """Compare coverage metrics."""
        print("\n## Coverage Analysis")
        
        coverage = {}
        
        for name, df in [('LLM', self.llm_df), 
                         ('boofuzz', self.boofuzz_df), 
                         ('Random', self.random_df)]:
            if df.empty:
                coverage[name] = {'error': 'No data'}
                continue
            
            coverage[name] = {
                'unique_vls': df['target_vl'].nunique() if 'target_vl' in df.columns else 0,
                'unique_rules': df['protocol_rule'].nunique() if 'protocol_rule' in df.columns else 0,
                'unique_mutations': df['mutation_type'].nunique() if 'mutation_type' in df.columns else 0,
                'unique_violation_types': df['violation_type'].nunique() if 'violation_type' in df.columns else 0
            }
            
            print(f"  {name}: {coverage[name]['unique_rules']} rules, "
                  f"{coverage[name]['unique_vls']} VLs")
        
        return coverage
    
    def _compare_efficiency(self) -> Dict[str, Any]:
        """Compare fuzzing efficiency."""
        print("\n## Efficiency Analysis")
        
        efficiency = {}
        
        for name, df in [('LLM', self.llm_df), 
                         ('boofuzz', self.boofuzz_df), 
                         ('Random', self.random_df)]:
            if df.empty:
                efficiency[name] = {'error': 'No data'}
                continue
            
            # Policing rate (higher = better at finding violations)
            policing_rate = df['policing_rate'].mean() if 'policing_rate' in df.columns else 0
            
            # Forward rate (lower = better - fewer bad frames forwarded)
            forward_rate = df['forward_rate'].mean() if 'forward_rate' in df.columns else 0
            
            # Bugs found
            bugs_found = df['bugs_found'].sum() if 'bugs_found' in df.columns else 0
            
            # Time to first bug (if applicable)
            first_bug_iteration = None
            if 'bugs_found' in df.columns:
                bugs_df = df[df['bugs_found'] > 0]
                if not bugs_df.empty:
                    first_bug_iteration = bugs_df['iteration'].min() if 'iteration' in bugs_df.columns else 0
            
            efficiency[name] = {
                'avg_policing_rate': float(policing_rate),
                'avg_forward_rate': float(forward_rate),
                'total_bugs_found': int(bugs_found),
                'first_bug_iteration': first_bug_iteration,
                'bugs_per_iteration': float(bugs_found / len(df)) if len(df) > 0 else 0
            }
            
            print(f"  {name}: policing={policing_rate:.1f}%, bugs={bugs_found}")
        
        return efficiency
    
    def _analyze_learning_curve(self) -> Dict[str, Any]:
        """Analyze LLM learning curve (early vs late performance)."""
        print("\n## Learning Curve Analysis (LLM only)")
        
        if self.llm_df.empty or 'reward' not in self.llm_df.columns:
            return {'error': 'No LLM data'}
        
        df = self.llm_df
        n = len(df)
        
        if n < 4:
            return {'error': 'Not enough iterations'}
        
        # Split into quarters
        q1 = df.iloc[:n//4]['reward'].mean()
        q2 = df.iloc[n//4:n//2]['reward'].mean()
        q3 = df.iloc[n//2:3*n//4]['reward'].mean()
        q4 = df.iloc[3*n//4:]['reward'].mean()
        
        # Early vs late
        early = df.iloc[:n//2]['reward'].mean()
        late = df.iloc[n//2:]['reward'].mean()
        
        improvement = ((late - early) / abs(early)) * 100 if early != 0 else 0
        
        result = {
            'q1_reward': float(q1),
            'q2_reward': float(q2),
            'q3_reward': float(q3),
            'q4_reward': float(q4),
            'early_reward': float(early),
            'late_reward': float(late),
            'improvement_percent': float(improvement)
        }
        
        print(f"  Early (first half): {early:.3f}")
        print(f"  Late (second half): {late:.3f}")
        print(f"  Improvement: {improvement:+.1f}%")
        
        return result
    
    def _compare_violation_detection(self) -> Dict[str, Any]:
        """Compare which violations each fuzzer found."""
        print("\n## Violation Detection")
        
        detection = {}
        
        for name, df in [('LLM', self.llm_df), 
                         ('boofuzz', self.boofuzz_df), 
                         ('Random', self.random_df)]:
            if df.empty:
                detection[name] = {'error': 'No data'}
                continue
            
            # Count violations by type
            if 'violation_type' in df.columns:
                violation_counts = df['violation_type'].value_counts().to_dict()
            else:
                violation_counts = {}
            
            # High-reward iterations (successful violations)
            high_reward = df[df['reward'] > 0.5] if 'reward' in df.columns else pd.DataFrame()
            
            detection[name] = {
                'violation_type_counts': violation_counts,
                'high_reward_count': len(high_reward),
                'high_reward_percent': (len(high_reward) / len(df) * 100) if len(df) > 0 else 0
            }
            
            print(f"  {name}: {len(violation_counts)} violation types, "
                  f"{detection[name]['high_reward_percent']:.1f}% high-reward")
        
        return detection
    
    def _run_statistical_tests(self) -> Dict[str, Any]:
        """Run statistical significance tests."""
        print("\n## Statistical Significance Tests")
        
        results = {}
        
        try:
            from scipy.stats import mannwhitneyu, kruskal
            
            # Extract reward arrays
            llm_rewards = self.llm_df['reward'].dropna().values if not self.llm_df.empty and 'reward' in self.llm_df.columns else np.array([])
            boofuzz_rewards = self.boofuzz_df['reward'].dropna().values if not self.boofuzz_df.empty and 'reward' in self.boofuzz_df.columns else np.array([])
            random_rewards = self.random_df['reward'].dropna().values if not self.random_df.empty and 'reward' in self.random_df.columns else np.array([])
            
            # LLM vs Random (Mann-Whitney U)
            if len(llm_rewards) > 0 and len(random_rewards) > 0:
                stat, p_value = mannwhitneyu(llm_rewards, random_rewards, alternative='greater')
                results['llm_vs_random'] = {
                    'test': 'Mann-Whitney U',
                    'statistic': float(stat),
                    'p_value': float(p_value),
                    'significant': p_value < 0.05,
                    'interpretation': 'LLM significantly better' if p_value < 0.05 else 'No significant difference'
                }
                print(f"  LLM vs Random: p={p_value:.4f} ({'*' if p_value < 0.05 else 'ns'})")
            
            # LLM vs boofuzz (Mann-Whitney U)
            if len(llm_rewards) > 0 and len(boofuzz_rewards) > 0:
                stat, p_value = mannwhitneyu(llm_rewards, boofuzz_rewards, alternative='greater')
                results['llm_vs_boofuzz'] = {
                    'test': 'Mann-Whitney U',
                    'statistic': float(stat),
                    'p_value': float(p_value),
                    'significant': p_value < 0.05,
                    'interpretation': 'LLM significantly better' if p_value < 0.05 else 'No significant difference'
                }
                print(f"  LLM vs boofuzz: p={p_value:.4f} ({'*' if p_value < 0.05 else 'ns'})")
            
            # boofuzz vs Random (Mann-Whitney U)
            if len(boofuzz_rewards) > 0 and len(random_rewards) > 0:
                stat, p_value = mannwhitneyu(boofuzz_rewards, random_rewards, alternative='greater')
                results['boofuzz_vs_random'] = {
                    'test': 'Mann-Whitney U',
                    'statistic': float(stat),
                    'p_value': float(p_value),
                    'significant': p_value < 0.05,
                    'interpretation': 'boofuzz significantly better' if p_value < 0.05 else 'No significant difference'
                }
                print(f"  boofuzz vs Random: p={p_value:.4f} ({'*' if p_value < 0.05 else 'ns'})")
            
            # Kruskal-Wallis (all three)
            all_arrays = [arr for arr in [llm_rewards, boofuzz_rewards, random_rewards] if len(arr) > 0]
            if len(all_arrays) >= 2:
                stat, p_value = kruskal(*all_arrays)
                results['kruskal_wallis'] = {
                    'test': 'Kruskal-Wallis H',
                    'statistic': float(stat),
                    'p_value': float(p_value),
                    'significant': p_value < 0.05,
                    'interpretation': 'Significant difference between groups' if p_value < 0.05 else 'No significant difference'
                }
                print(f"  Kruskal-Wallis (all): p={p_value:.4f} ({'*' if p_value < 0.05 else 'ns'})")
        
        except ImportError:
            results['error'] = 'scipy not available'
            print("  (scipy not available - install with: pip install scipy)")
        
        return results
    
    def _generate_text_report(self, results: Dict[str, Any]):
        """Generate human-readable text report."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_path = self.output_dir / f"three_way_comparison_{timestamp}.txt"
        
        lines = []
        lines.append("=" * 80)
        lines.append("THREE-WAY FUZZER COMPARISON REPORT")
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 80)
        
        # Basic stats
        lines.append("\n## BASIC STATISTICS")
        for fuzzer, stats in results.get('basic_stats', {}).items():
            if 'error' in stats:
                lines.append(f"  {fuzzer}: {stats['error']}")
            else:
                lines.append(f"  {fuzzer}: {stats['total_iterations']} iterations")
        
        # Reward analysis
        lines.append("\n## REWARD ANALYSIS")
        lines.append(f"{'Fuzzer':<15} {'Mean':<10} {'Median':<10} {'Max':<10} {'Std':<10}")
        lines.append("-" * 55)
        
        for fuzzer, rewards in results.get('reward_analysis', {}).items():
            if fuzzer.startswith('llm_vs'):
                continue
            if 'error' in rewards:
                lines.append(f"{fuzzer:<15} {rewards['error']}")
            else:
                lines.append(f"{fuzzer:<15} {rewards['mean']:<10.3f} {rewards['median']:<10.3f} "
                           f"{rewards['max']:<10.3f} {rewards['std']:<10.3f}")
        
        if 'llm_vs_random_improvement' in results.get('reward_analysis', {}):
            lines.append(f"\nLLM vs Random: {results['reward_analysis']['llm_vs_random_improvement']:+.1f}%")
        if 'llm_vs_boofuzz_improvement' in results.get('reward_analysis', {}):
            lines.append(f"LLM vs boofuzz: {results['reward_analysis']['llm_vs_boofuzz_improvement']:+.1f}%")
        
        # Coverage
        lines.append("\n## COVERAGE ANALYSIS")
        lines.append(f"{'Fuzzer':<15} {'VLs':<10} {'Rules':<10} {'Mutations':<10}")
        lines.append("-" * 45)
        
        for fuzzer, coverage in results.get('coverage_analysis', {}).items():
            if 'error' in coverage:
                lines.append(f"{fuzzer:<15} {coverage['error']}")
            else:
                lines.append(f"{fuzzer:<15} {coverage['unique_vls']:<10} "
                           f"{coverage['unique_rules']:<10} {coverage['unique_mutations']:<10}")
        
        # Efficiency
        lines.append("\n## EFFICIENCY ANALYSIS")
        lines.append(f"{'Fuzzer':<15} {'Policing %':<12} {'Bugs':<10} {'Bugs/Iter':<10}")
        lines.append("-" * 47)
        
        for fuzzer, eff in results.get('efficiency_analysis', {}).items():
            if 'error' in eff:
                lines.append(f"{fuzzer:<15} {eff['error']}")
            else:
                lines.append(f"{fuzzer:<15} {eff['avg_policing_rate']:<12.1f} "
                           f"{eff['total_bugs_found']:<10} {eff['bugs_per_iteration']:<10.3f}")
        
        # Learning curve
        learning = results.get('learning_curve', {})
        if 'error' not in learning:
            lines.append("\n## LLM LEARNING CURVE")
            lines.append(f"  Early iterations: {learning['early_reward']:.3f}")
            lines.append(f"  Late iterations: {learning['late_reward']:.3f}")
            lines.append(f"  Improvement: {learning['improvement_percent']:+.1f}%")
        
        # Statistical tests
        lines.append("\n## STATISTICAL SIGNIFICANCE")
        for test_name, test_result in results.get('statistical_tests', {}).items():
            if test_name == 'error':
                lines.append(f"  {test_result}")
            else:
                sig = "*" if test_result.get('significant', False) else "ns"
                lines.append(f"  {test_name}: p={test_result['p_value']:.4f} ({sig}) - "
                           f"{test_result.get('interpretation', '')}")
        
        # Summary
        lines.append("\n" + "=" * 80)
        lines.append("SUMMARY")
        lines.append("=" * 80)
        
        # Determine winner
        reward_analysis = results.get('reward_analysis', {})
        if all(f in reward_analysis for f in ['LLM', 'boofuzz', 'Random']):
            means = {
                'LLM': reward_analysis['LLM'].get('mean', 0),
                'boofuzz': reward_analysis['boofuzz'].get('mean', 0),
                'Random': reward_analysis['Random'].get('mean', 0)
            }
            winner = max(means, key=means.get)
            lines.append(f"\nBest mean reward: {winner} ({means[winner]:.3f})")
        
        efficiency = results.get('efficiency_analysis', {})
        if all(f in efficiency for f in ['LLM', 'boofuzz', 'Random']):
            bugs = {
                'LLM': efficiency['LLM'].get('total_bugs_found', 0),
                'boofuzz': efficiency['boofuzz'].get('total_bugs_found', 0),
                'Random': efficiency['Random'].get('total_bugs_found', 0)
            }
            winner = max(bugs, key=bugs.get)
            lines.append(f"Most bugs found: {winner} ({bugs[winner]})")
        
        lines.append("\n" + "=" * 80)
        
        # Write report
        with open(report_path, 'w') as f:
            f.write('\n'.join(lines))
        
        print(f"\nText report saved to: {report_path}")
    
    def _generate_json_report(self, results: Dict[str, Any]):
        """Generate JSON report."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_path = self.output_dir / f"three_way_comparison_{timestamp}.json"
        
        def make_serializable(obj):
            """Recursively convert objects to JSON-serializable types."""
            if isinstance(obj, (np.bool_, bool)):
                return bool(obj)
            elif isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            elif isinstance(obj, pd.Timestamp):
                return obj.isoformat()
            elif isinstance(obj, dict):
                return {str(k): make_serializable(v) for k, v in obj.items()}
            elif isinstance(obj, (list, tuple)):
                return [make_serializable(item) for item in obj]
            elif isinstance(obj, (str, int, float, type(None))):
                return obj
            else:
                return str(obj)
        
        serializable_results = make_serializable(results)
        
        with open(report_path, 'w') as f:
            json.dump(serializable_results, f, indent=2)
        
        print(f"JSON report saved to: {report_path}")
    
    def _generate_latex_table(self, results: Dict[str, Any]):
        """Generate LaTeX table for paper."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_path = self.output_dir / f"three_way_comparison_{timestamp}.tex"
        
        lines = []
        lines.append("% Three-Way Fuzzer Comparison Table")
        lines.append(f"% Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append("\\begin{table}[htbp]")
        lines.append("\\centering")
        lines.append("\\caption{Comparison of Fuzzing Approaches}")
        lines.append("\\label{tab:fuzzer-comparison}")
        lines.append("\\begin{tabular}{lccc}")
        lines.append("\\toprule")
        lines.append("\\textbf{Metric} & \\textbf{LLM-Guided} & \\textbf{boofuzz} & \\textbf{Random} \\\\")
        lines.append("\\midrule")
        
        # Reward
        reward_analysis = results.get('reward_analysis', {})
        llm_mean = reward_analysis.get('LLM', {}).get('mean', 'N/A')
        boofuzz_mean = reward_analysis.get('boofuzz', {}).get('mean', 'N/A')
        random_mean = reward_analysis.get('Random', {}).get('mean', 'N/A')
        
        if isinstance(llm_mean, (int, float)):
            lines.append(f"Mean Reward & {llm_mean:.3f} & {boofuzz_mean:.3f} & {random_mean:.3f} \\\\")
        
        # Bugs
        efficiency = results.get('efficiency_analysis', {})
        llm_bugs = efficiency.get('LLM', {}).get('total_bugs_found', 'N/A')
        boofuzz_bugs = efficiency.get('boofuzz', {}).get('total_bugs_found', 'N/A')
        random_bugs = efficiency.get('Random', {}).get('total_bugs_found', 'N/A')
        
        lines.append(f"Bugs Found & {llm_bugs} & {boofuzz_bugs} & {random_bugs} \\\\")
        
        # Policing rate
        llm_pol = efficiency.get('LLM', {}).get('avg_policing_rate', 'N/A')
        boofuzz_pol = efficiency.get('boofuzz', {}).get('avg_policing_rate', 'N/A')
        random_pol = efficiency.get('Random', {}).get('avg_policing_rate', 'N/A')
        
        if isinstance(llm_pol, (int, float)):
            lines.append(f"Policing Rate (\\%) & {llm_pol:.1f} & {boofuzz_pol:.1f} & {random_pol:.1f} \\\\")
        
        # Coverage
        coverage = results.get('coverage_analysis', {})
        llm_rules = coverage.get('LLM', {}).get('unique_rules', 'N/A')
        boofuzz_rules = coverage.get('boofuzz', {}).get('unique_rules', 'N/A')
        random_rules = coverage.get('Random', {}).get('unique_rules', 'N/A')
        
        lines.append(f"Rules Tested & {llm_rules} & {boofuzz_rules} & {random_rules} \\\\")
        
        # Learning improvement (LLM only)
        learning = results.get('learning_curve', {})
        if 'improvement_percent' in learning:
            lines.append(f"Learning Improvement & {learning['improvement_percent']:+.1f}\\% & N/A & N/A \\\\")
        
        lines.append("\\bottomrule")
        lines.append("\\end{tabular}")
        lines.append("\\end{table}")
        
        with open(report_path, 'w') as f:
            f.write('\n'.join(lines))
        
        print(f"LaTeX table saved to: {report_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Three-way fuzzer comparison: LLM vs boofuzz vs Random"
    )
    
    parser.add_argument(
        '--llm-history',
        type=str,
        default="llm_fuzzer/data/iteration_history.jsonl",
        help='Path to LLM fuzzer history'
    )
    
    parser.add_argument(
        '--boofuzz-history',
        type=str,
        default="boofuzz_baseline/data/iteration_history.jsonl",
        help='Path to boofuzz history'
    )
    
    parser.add_argument(
        '--random-history',
        type=str,
        default="random_baseline/data/iteration_history.jsonl",
        help='Path to random fuzzer history'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default="evaluation/results",
        help='Output directory for reports'
    )
    
    args = parser.parse_args()
    
    comparison = ThreeWayComparison(
        llm_history_path=args.llm_history,
        boofuzz_history_path=args.boofuzz_history,
        random_history_path=args.random_history,
        output_dir=args.output_dir
    )
    
    comparison.compare_all()


if __name__ == "__main__":
    main()

