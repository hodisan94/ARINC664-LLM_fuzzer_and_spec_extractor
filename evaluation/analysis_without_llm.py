#!/usr/bin/env python3
"""
Analysis WITHOUT requiring LLM API - uses existing data only.
Generates paper-ready results from Phase 1 and Random fuzzer.
"""

import json
import pandas as pd
from pathlib import Path
from collections import Counter, defaultdict

class NoLLMAnalysis:
    """Analysis using only available data (no LLM API needed)."""
    
    def __init__(self):
        self.output_dir = Path("evaluation/results")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.spec_rules_path = Path("configs/spec_rules.json")
        self.test_cases_path = Path("configs/test_cases.json")
    
    def analyze_phase1(self):
        """Complete Phase 1 analysis."""
        print("\n" + "="*80)
        print("PHASE 1: SPECIFICATION KNOWLEDGE EXTRACTION - DETAILED ANALYSIS")
        print("="*80)
        
        # Load data
        with open(self.spec_rules_path) as f:
            spec_rules = json.load(f)
        
        with open(self.test_cases_path) as f:
            test_cases = json.load(f)
        
        # Analyze rules
        rules_list = [k for k in spec_rules.keys() if k not in ['bag', 'frame_structure']]
        rules_by_category = defaultdict(list)
        
        for rule_id in rules_list:
            category = rule_id.split('.')[0]
            rules_by_category[category].append(rule_id)
        
        # Analyze test cases
        total_test_cases = 0
        test_cases_per_rule = {}
        violation_types = Counter()
        test_case_examples = {}
        
        for rule_id, rule_data in test_cases.items():
            if 'test_cases' in rule_data:
                cases = rule_data['test_cases']
                total_test_cases += len(cases)
                test_cases_per_rule[rule_id] = len(cases)
                
                # Store first example
                if cases:
                    test_case_examples[rule_id] = cases[0]
                
                for case in cases:
                    vtype = case.get('violation_type', 'unknown')
                    violation_types[vtype] += 1
        
        # Print results
        print(f"\n{'─'*80}")
        print("PROTOCOL RULES EXTRACTED")
        print(f"{'─'*80}")
        print(f"\n✓ Total Rules: {len(rules_list)}")
        print(f"\nRules by Category:")
        for cat, rules in sorted(rules_by_category.items()):
            print(f"\n  [{cat.upper()}] ({len(rules)} rules):")
            for rule in rules:
                print(f"    • {rule}")
        
        print(f"\n{'─'*80}")
        print("TEST CASES GENERATED")
        print(f"{'─'*80}")
        print(f"\n✓ Total Test Cases: {total_test_cases}")
        print(f"✓ Average per Rule: {total_test_cases / len(test_cases_per_rule):.1f}")
        
        print(f"\nTest Cases per Rule:")
        for rule_id, count in sorted(test_cases_per_rule.items(), key=lambda x: x[1], reverse=True):
            print(f"  • {rule_id}: {count} test cases")
        
        print(f"\nViolation Type Distribution:")
        for vtype, count in violation_types.most_common():
            print(f"  • {vtype}: {count}")
        
        print(f"\n{'─'*80}")
        print("EXAMPLE TEST CASES (for paper)")
        print(f"{'─'*80}")
        
        # Show a few examples for the paper
        example_rules = ['bag', 'sequence_numbers', 'virtual_link.id_range']
        for rule_id in example_rules:
            if rule_id in test_case_examples:
                ex = test_case_examples[rule_id]
                print(f"\n[{rule_id}]")
                print(f"  Violation Type: {ex.get('violation_type')}")
                print(f"  Test Value: {ex.get('value')}")
                print(f"  Reason: {ex.get('reason', '')[:100]}...")
        
        return {
            'total_rules': len(rules_list),
            'rules_by_category': {k: len(v) for k, v in rules_by_category.items()},
            'total_test_cases': total_test_cases,
            'avg_per_rule': total_test_cases / len(test_cases_per_rule) if test_cases_per_rule else 0,
            'violation_types': dict(violation_types),
            'test_cases_per_rule': test_cases_per_rule
        }
    
    def analyze_random_fuzzer(self):
        """Analyze random fuzzer results."""
        print("\n" + "="*80)
        print("RANDOM FUZZER ANALYSIS (Baseline)")
        print("="*80)
        
        history_file = Path("random_baseline/data/iteration_history.jsonl")
        if not history_file.exists():
            print("No random fuzzer data found")
            return {}
        
        records = []
        with open(history_file) as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))
        
        df = pd.DataFrame(records)
        
        print(f"\n✓ Total Iterations: {len(df)}")
        print(f"✓ Successful: {df['simulation_success'].sum()}")
        
        # Coverage
        vls_tested = df['target_vl'].unique()
        rules_tested = df['protocol_rule'].unique()
        
        print(f"\nCoverage:")
        print(f"  • VLs tested: {len(vls_tested)} (out of 8)")
        print(f"    VL IDs: {sorted(vls_tested)}")
        print(f"  • Protocol rules tested: {len(rules_tested)}")
        for rule in sorted(rules_tested):
            print(f"    - {rule}")
        
        # Efficiency
        print(f"\nParameter Diversity:")
        
        # Count test mode usage
        predefined = (df['test_mode'] == 'predefined').sum()
        custom = (df['test_mode'] == 'custom').sum()
        print(f"  • Used predefined test cases: {predefined} times")
        print(f"  • Used custom mutations: {custom} times")
        
        # VL distribution
        vl_dist = df['target_vl'].value_counts()
        print(f"\nVL Testing Distribution:")
        for vl, count in vl_dist.items():
            print(f"  • VL {vl}: {count} times ({count/len(df)*100:.1f}%)")
        
        # Performance
        print(f"\nPerformance Metrics:")
        print(f"  • Average reward: {df['reward'].mean():.3f}")
        print(f"  • Max reward: {df['reward'].max():.3f}")
        print(f"  • Std deviation: {df['reward'].std():.3f}")
        
        return {
            'total_iterations': len(df),
            'vls_tested': len(vls_tested),
            'vls_list': list(vls_tested),
            'rules_tested': len(rules_tested),
            'rules_list': list(rules_tested),
            'predefined_used': int(predefined),
            'custom_used': int(custom),
            'avg_reward': float(df['reward'].mean()),
            'vl_distribution': vl_dist.to_dict()
        }
    
    def generate_paper_content(self, phase1_results, random_results):
        """Generate paper-ready content."""
        print("\n" + "="*80)
        print("GENERATING PAPER CONTENT")
        print("="*80)
        
        output = []
        output.append("\\section{Evaluation and Results}")
        output.append("\\label{sec:evaluation}\n")
        
        # Introduction
        output.append("We evaluate our approach in two stages: ")
        output.append("(1) specification knowledge extraction, and ")
        output.append("(2) fuzzing effectiveness. ")
        output.append("We compare against a random baseline that uniformly samples ")
        output.append("test parameters without adaptation or learning.\\n")
        
        # Phase 1
        output.append("\\subsection{Specification Knowledge Extraction}\\n")
        output.append(f"The automated extraction identified {phase1_results['total_rules']} ")
        output.append(f"protocol rules from ARINC~664 Part~7 and generated ")
        output.append(f"{phase1_results['total_test_cases']} violation test cases ")
        output.append(f"({phase1_results['avg_per_rule']:.1f} per rule on average). ")
        output.append("Table~\\ref{tab:phase1} shows the distribution. ")
        output.append("This demonstrates zero-shot extraction without manual annotation.\\n")
        
        # Table 1
        output.append("\\begin{table}[ht]")
        output.append("\\centering")
        output.append("\\caption{Specification Knowledge Extraction Results}")
        output.append("\\label{tab:phase1}")
        output.append("\\small")
        output.append("\\begin{tabular}{lc}")
        output.append("\\toprule")
        output.append("\\textbf{Component} & \\textbf{Count} \\\\")
        output.append("\\midrule")
        output.append(f"Protocol rules & {phase1_results['total_rules']} \\\\")
        output.append(f"Test cases & {phase1_results['total_test_cases']} \\\\")
        output.append(f"Avg. cases/rule & {phase1_results['avg_per_rule']:.1f} \\\\")
        output.append("\\midrule")
        output.append("\\multicolumn{2}{l}{\\textit{Rules by category:}} \\\\")
        for cat, count in sorted(phase1_results['rules_by_category'].items(), key=lambda x: x[1], reverse=True):
            output.append(f"\\quad {cat.replace('_', ' ')} & {count} \\\\")
        output.append("\\bottomrule")
        output.append("\\end{tabular}")
        output.append("\\end{table}\\n")
        
        # Random baseline results
        output.append("\\subsection{Random Baseline Characteristics}\\n")
        output.append(f"The random baseline executed {random_results['total_iterations']} iterations, ")
        output.append(f"testing {random_results['vls_tested']}/8 VLs and ")
        output.append(f"{random_results['rules_tested']} distinct protocol rules. ")
        output.append(f"It achieved an average reward of {random_results['avg_reward']:.3f}, ")
        output.append("providing a performance baseline for comparison. ")
        output.append("The uniform sampling explored the test space without adaptation.\\n")
        
        # Save
        output_file = self.output_dir / "evaluation_section.tex"
        with open(output_file, 'w') as f:
            f.write('\n'.join(output))
        
        print(f"\n✓ Paper content saved to: {output_file}")
        
        # Also save JSON
        import numpy as np
        
        def convert(obj):
            if isinstance(obj, (np.integer, np.int64)):
                return int(obj)
            elif isinstance(obj, (np.floating, np.float64)):
                return float(obj)
            return obj
        
        json_file = self.output_dir / "evaluation_data.json"
        with open(json_file, 'w') as f:
            json.dump({
                'phase1': phase1_results,
                'random_baseline': random_results
            }, f, indent=2, default=convert)
        
        print(f"✓ Data saved to: {json_file}")
    
    def run(self):
        """Run complete analysis."""
        print("\n" + "="*80)
        print("EVALUATION ANALYSIS (WITHOUT LLM API)")
        print("="*80)
        print("Analyzing available data for paper...")
        
        phase1 = self.analyze_phase1()
        random = self.analyze_random_fuzzer()
        self.generate_paper_content(phase1, random)
        
        print("\n" + "="*80)
        print("ANALYSIS COMPLETE")
        print("="*80)
        print("\n✓ Phase 1 analysis: DONE")
        print("✓ Random baseline analysis: DONE")
        print("✓ Paper content generated: DONE")
        print("\nNOTE: LLM fuzzer requires OpenAI API key to run.")
        print("      Once available, run with API key for complete comparison.")

if __name__ == "__main__":
    analyzer = NoLLMAnalysis()
    analyzer.run()

