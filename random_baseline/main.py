#!/usr/bin/env python3
"""
Random Baseline Fuzzer - Main Loop

This is a fair comparison baseline for the LLM-guided fuzzer.
It uses THE SAME infrastructure:
- FeedbackAnalyzer (same)
- TestGenerator (same)
- SimulatorRunner (same)
- Reward Calculator (same)

But replaces LLMStrategyPlanner with RandomStrategyGenerator.

This ensures the ONLY difference is: LLM intelligence vs. random selection.
"""

import sys
import json
import argparse
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from llm_fuzzer.core.feedback_analyzer import FeedbackAnalyzer
from llm_fuzzer.core.test_generator import TestGenerator
from llm_fuzzer.utils.simulator_runner import SimulatorRunner
from random_baseline.random_strategy_generator import RandomStrategyGenerator


class RandomFuzzer:
    """
    Random Baseline Fuzzer - uses same infrastructure as LLM fuzzer.
    
    Key difference: RandomStrategyGenerator instead of LLMStrategyPlanner.
    Everything else is IDENTICAL for fair comparison.
    """
    
    def __init__(
        self,
        spec_rules_path: str = "configs/spec_rules_filtered.json",
        test_cases_path: str = "configs/test_cases.json",
        seed_frames_path: str = "llm_fuzzer/data/seed_frames.json",
        history_path: str = "random_baseline/data/iteration_history.jsonl",
        output_dir: str = "random_baseline/output",
        max_iterations: int = 50,
        available_vls: Optional[List[int]] = None,
        random_seed: Optional[int] = None
    ):
        """
        Initialize Random Baseline Fuzzer.
        
        Args:
            spec_rules_path: Path to protocol specification rules
            test_cases_path: Path to violation test cases
            seed_frames_path: Path to seed frames
            history_path: Path to iteration history file (JSONL)
            output_dir: Directory for output files
            max_iterations: Maximum number of fuzzing iterations
            available_vls: List of available VL IDs
            random_seed: Random seed for reproducibility
        """
        self.spec_rules_path = spec_rules_path
        self.test_cases_path = test_cases_path
        self.seed_frames_path = seed_frames_path
        self.history_path = Path(history_path)
        self.output_dir = Path(output_dir)
        self.max_iterations = max_iterations
        self.available_vls = available_vls or [1001, 1002, 1003, 2001, 2002, 2003, 3001, 3002]
        self.random_seed = random_seed
        
        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize components (SAME as LLM fuzzer)
        print("Initializing components...")
        self.feedback_analyzer = FeedbackAnalyzer()
        
        # ONLY DIFFERENCE: RandomStrategyGenerator instead of LLMStrategyPlanner
        self.strategy_generator = RandomStrategyGenerator(
            spec_rules_path=spec_rules_path,
            test_cases_path=test_cases_path,
            seed=random_seed
        )
        
        self.test_generator = TestGenerator(
            seed_frames_path=seed_frames_path,
            test_cases_path=test_cases_path
        )
        self.simulator_runner = SimulatorRunner()
        
        print("All components initialized successfully!")
        print(f"Random seed: {random_seed if random_seed is not None else 'None (non-deterministic)'}")
    
    def load_history(self) -> pd.DataFrame:
        """Load iteration history from JSONL file."""
        if not self.history_path.exists():
            print("No previous history found. Starting fresh.")
            return pd.DataFrame()
        
        try:
            records = []
            with open(self.history_path, 'r') as f:
                for line in f:
                    if line.strip():
                        records.append(json.loads(line))
            
            if records:
                df = pd.DataFrame(records)
                print(f"Loaded {len(df)} previous iterations from history")
                return df
            else:
                return pd.DataFrame()
        
        except Exception as e:
            print(f"Warning: Could not load history: {e}")
            return pd.DataFrame()
    
    def save_iteration(self, iteration_data: Dict[str, Any]):
        """Save iteration data to history file (append to JSONL)."""
        with open(self.history_path, 'a') as f:
            f.write(json.dumps(iteration_data) + '\n')
    
    def run_iteration(
        self,
        iteration: int,
        history: pd.DataFrame
    ) -> Dict[str, Any]:
        """Run a single fuzzing iteration (SAME as LLM fuzzer)."""
        print(f"\n{'='*70}")
        print(f"ITERATION {iteration}")
        print(f"{'='*70}")
        
        iteration_start = datetime.now()
        
        try:
            # Step 1: Random Strategy Generator (ONLY DIFFERENCE!)
            print("\n[1/4] Generating Random Strategy...")
            strategy = self.strategy_generator.plan_next_iteration(
                history=history if not history.empty else None,
                iteration=iteration,
                system_config={'available_vls': self.available_vls}
            )
            
            print(f"  Target VL: {strategy['target_vl']}")
            print(f"  Protocol Rule: {strategy['protocol_rule']}")
            print(f"  Test Mode: {strategy['test_mode']}")
            print(f"  Strategy Type: {strategy['strategy']}")
            print(f"  Reasoning: Random selection (no learning)")
            
            # Step 2: Test Generator (SAME as LLM fuzzer)
            print("\n[2/4] Generating Test Inputs...")
            test_inputs = self.test_generator.generate_test_inputs(strategy)
            
            print(f"  Generated {test_inputs['metadata']['num_frames']} frames")
            print(f"  VL ID: {test_inputs['vl_id']}")
            
            # Save test inputs
            test_file = self.output_dir / f"iteration_{iteration:03d}_test.json"
            self.test_generator.save_to_file(test_inputs, str(test_file))
            print(f"  Saved to: {test_file}")
            
            # Step 3: Simulator Runner (SAME as LLM fuzzer)
            print("\n[3/4] Running Simulator...")
            sim_result = self.simulator_runner.run_simulation(
                test_inputs=test_inputs,
                run_id=f"random_iter_{iteration:03d}",
                timeout=120
            )
            
            if sim_result['success']:
                print(f"  Simulation completed in {sim_result['duration']:.2f}s")
            else:
                print(f"  Simulation failed: {sim_result['error']}")
            
            # Step 4: Feedback Analyzer (SAME as LLM fuzzer)
            print("\n[4/4] Analyzing Feedback...")
            # Use CSV content if available, otherwise fallback to log content
            analysis_content = sim_result.get('csv_content') or sim_result['log_content']
            feedback = self.feedback_analyzer.analyze(
                log_content=analysis_content,
                strategy=strategy,
                history=history
            )
            
            print(f"  Reward: {feedback.get('reward', 0.0):.3f}")
            policing_rate = feedback.get('metrics', {}).get('policing_rate', 0.0)
            print(f"  Policing Rate: {policing_rate:.1f}%")
            bugs_found = feedback.get('analysis', {}).get('bugs_found', False)
            print(f"  Bugs Found: {bugs_found}")
            
            # Compile iteration results
            iteration_data = {
                'iteration': iteration,
                'timestamp': datetime.now().isoformat(),
                'duration': (datetime.now() - iteration_start).total_seconds(),
                'fuzzer_type': 'RANDOM_BASELINE',
                'target_vl': strategy['target_vl'],
                'protocol_rule': strategy['protocol_rule'],
                'test_mode': strategy['test_mode'],
                'strategy': strategy['strategy'],
                'test_cases': strategy.get('test_cases'),
                'custom_mutation': strategy.get('custom_mutation'),
                'num_frames': test_inputs['metadata']['num_frames'],
                'simulation_success': sim_result['success'],
                'reward': feedback['reward'],
                'frames_received': feedback['metrics'].get('frames_received', 0),
                'frames_dropped_policing': feedback['metrics'].get('frames_dropped_policing', 0),
                'frames_forwarded': feedback['metrics'].get('frames_forwarded', 0),
                'policing_rate': feedback['metrics'].get('policing_rate', 0.0),
                'forward_rate': feedback['metrics'].get('forward_rate', 0.0),
                'bugs_found': bugs_found,
            }
            
            print(f"\nIteration {iteration} completed successfully!")
            return iteration_data
        
        except Exception as e:
            print(f"\nERROR in iteration {iteration}: {e}")
            import traceback
            traceback.print_exc()
            
            # Return error record with all required fields
            return {
                'iteration': iteration,
                'timestamp': datetime.now().isoformat(),
                'duration': (datetime.now() - iteration_start).total_seconds(),
                'fuzzer_type': 'RANDOM_BASELINE',
                'target_vl': strategy.get('target_vl', -1) if 'strategy' in locals() else -1,
                'protocol_rule': strategy.get('protocol_rule', 'unknown') if 'strategy' in locals() else 'unknown',
                'test_mode': strategy.get('test_mode', 'unknown') if 'strategy' in locals() else 'unknown',
                'strategy': strategy.get('strategy', 'unknown') if 'strategy' in locals() else 'unknown',
                'test_cases': None,
                'custom_mutation': None,
                'num_frames': 0,
                'simulation_success': False,
                'reward': 0.0,
                'frames_received': 0,
                'frames_dropped_policing': 0,
                'frames_forwarded': 0,
                'policing_rate': 0.0,
                'forward_rate': 0.0,
                'bugs_found': False,
                'error': str(e),
                'success': False
            }
    
    def should_stop(
        self,
        iteration: int,
        history: pd.DataFrame,
        consecutive_failures: int
    ) -> bool:
        """Determine if fuzzing should stop."""
        if iteration >= self.max_iterations:
            print(f"\nStopping: Reached max iterations ({self.max_iterations})")
            return True
        
        if consecutive_failures >= 5:
            print(f"\nStopping: {consecutive_failures} consecutive failures")
            return True
        
        return False
    
    def generate_report(self, history: pd.DataFrame) -> str:
        """Generate final fuzzing report (SAME format as LLM fuzzer)."""
        report_lines = []
        report_lines.append("=" * 70)
        report_lines.append("RANDOM BASELINE FUZZER - FINAL REPORT")
        report_lines.append("=" * 70)
        report_lines.append("")
        
        if history.empty:
            report_lines.append("No iterations completed.")
            return "\n".join(report_lines)
        
        # Basic stats
        total_iterations = len(history)
        if 'simulation_success' in history.columns:
            successful = history[history['simulation_success'] == True].copy()
        else:
            successful = history.copy()
        
        report_lines.append(f"Total Iterations: {total_iterations}")
        report_lines.append(f"Successful: {len(successful)}")
        report_lines.append(f"Failed: {total_iterations - len(successful)}")
        report_lines.append("")
        
        if not successful.empty:
            # Reward stats
            report_lines.append("Reward Statistics:")
            report_lines.append(f"  Mean: {successful['reward'].mean():.3f}")
            report_lines.append(f"  Max: {successful['reward'].max():.3f}")
            report_lines.append(f"  Min: {successful['reward'].min():.3f}")
            report_lines.append(f"  Std: {successful['reward'].std():.3f}")
            report_lines.append("")
            
            # Bugs found
            bugs_found = successful['bugs_found'].sum()
            report_lines.append(f"Bugs Found: {bugs_found}")
            report_lines.append("")
            
            # VL coverage
            vls_tested = successful['target_vl'].unique()
            report_lines.append(f"VLs Tested: {len(vls_tested)} / {len(self.available_vls)}")
            report_lines.append(f"  VL IDs: {sorted(vls_tested)}")
            report_lines.append("")
            
            # Rules tested
            rules_tested = successful['protocol_rule'].unique()
            report_lines.append(f"Protocol Rules Tested: {len(rules_tested)}")
            report_lines.append(f"  Rules: {sorted(rules_tested)}")
            report_lines.append("")
            
            # Strategy distribution
            report_lines.append("Strategy Distribution:")
            for strategy, count in successful['strategy'].value_counts().items():
                report_lines.append(f"  {strategy}: {count}")
            report_lines.append("")
            
            # Test mode distribution
            report_lines.append("Test Mode Distribution:")
            for mode, count in successful['test_mode'].value_counts().items():
                report_lines.append(f"  {mode}: {count}")
            report_lines.append("")
            
            # Top performers
            top_5 = successful.nlargest(5, 'reward')[['iteration', 'target_vl', 'protocol_rule', 'reward', 'bugs_found']]
            report_lines.append("Top 5 Iterations (by reward):")
            for idx, row in top_5.iterrows():
                bugs_str = " [BUG!]" if row['bugs_found'] else ""
                report_lines.append(f"  Iter {row['iteration']}: VL={row['target_vl']}, "
                                  f"rule={row['protocol_rule']}, reward={row['reward']:.3f}{bugs_str}")
        
        report_lines.append("")
        report_lines.append("=" * 70)
        report_lines.append("NOTE: This is a RANDOM baseline - no learning or adaptation")
        report_lines.append("=" * 70)
        
        return "\n".join(report_lines)
    
    def run(self):
        """Main fuzzing loop."""
        print("\n" + "=" * 70)
        print("RANDOM BASELINE AFDX FUZZER")
        print("=" * 70)
        print(f"\nConfiguration:")
        print(f"  Max Iterations: {self.max_iterations}")
        print(f"  Available VLs: {self.available_vls}")
        print(f"  History File: {self.history_path}")
        print(f"  Output Directory: {self.output_dir}")
        print(f"  Random Seed: {self.random_seed if self.random_seed is not None else 'None'}")
        print("")
        
        # Load history
        history = self.load_history()
        start_iteration = len(history) if not history.empty else 0
        
        if start_iteration > 0:
            print(f"\nResuming from iteration {start_iteration}")
        
        # Main loop
        consecutive_failures = 0
        
        for iteration in range(start_iteration, self.max_iterations):
            # Run iteration
            result = self.run_iteration(iteration, history)
            
            # Save result
            self.save_iteration(result)
            
            # Update history
            new_row = pd.DataFrame([result])
            history = pd.concat([history, new_row], ignore_index=True)
            
            # Track failures
            if not result.get('simulation_success', False):
                consecutive_failures += 1
            else:
                consecutive_failures = 0
            
            # Check stopping conditions
            if self.should_stop(iteration + 1, history, consecutive_failures):
                break
        
        # Generate and save final report
        print("\n\nGenerating final report...")
        report = self.generate_report(history)
        print("\n" + report)
        
        # Save report to file
        report_file = self.output_dir / f"random_fuzzing_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(report_file, 'w') as f:
            f.write(report)
        print(f"\nReport saved to: {report_file}")
        
        # Save full history as CSV
        if not history.empty:
            csv_file = self.output_dir / f"random_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            history.to_csv(csv_file, index=False)
            print(f"Full history saved to: {csv_file}")
        
        print("\nRandom baseline fuzzing completed!")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Random Baseline AFDX Fuzzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with defaults (50 iterations)
  python3 random_baseline/main.py
  
  # Run with custom iteration count
  python3 random_baseline/main.py --max-iterations 100
  
  # Run with random seed for reproducibility
  python3 random_baseline/main.py --seed 42
  
  # Specify custom VLs
  python3 random_baseline/main.py --vls 1001 1002 2001 2002
        """
    )
    
    parser.add_argument(
        '--max-iterations',
        type=int,
        default=50,
        help='Maximum number of fuzzing iterations (default: 50)'
    )
    
    parser.add_argument(
        '--seed',
        type=int,
        default=None,
        help='Random seed for reproducibility (default: None)'
    )
    
    parser.add_argument(
        '--vls',
        type=int,
        nargs='+',
        default=None,
        help='List of available VL IDs (default: 1001-3002)'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default='random_baseline/output',
        help='Output directory for results (default: random_baseline/output)'
    )
    
    args = parser.parse_args()
    
    # Create fuzzer
    fuzzer = RandomFuzzer(
        max_iterations=args.max_iterations,
        available_vls=args.vls,
        output_dir=args.output_dir,
        random_seed=args.seed
    )
    
    # Run
    try:
        fuzzer.run()
    except KeyboardInterrupt:
        print("\n\nFuzzing interrupted by user.")
        print("History saved. You can resume with same seed for deterministic results.")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

