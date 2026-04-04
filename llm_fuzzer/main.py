#!/usr/bin/env python3
"""
LLM-Guided AFDX Fuzzer - Main Loop

This is the main entry point for the LLM-guided iterative fuzzing system.
It orchestrates all three components in an iterative loop:

1. Test Feedback Analyzer - analyzes simulator results and computes rewards
2. LLM-Based Strategy Planner - decides what to test next
3. Strategy-Driven Test Input Generator - creates and executes tests

The fuzzer runs iteratively, learning from each test and adapting its strategy.
"""

import sys
import json
import argparse
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(Path(__file__).parent.parent / ".env")

from llm_fuzzer.core.feedback_analyzer import FeedbackAnalyzer
from llm_fuzzer.core.strategy_planner import LLMStrategyPlanner
from llm_fuzzer.core.test_generator import TestGenerator
from llm_fuzzer.utils.simulator_runner import SimulatorRunner


class LLMFuzzer:
    """
    Main LLM-Guided Fuzzing orchestrator.
    
    Manages the iterative fuzzing loop, integrating all three components.
    """
    
    def __init__(
        self,
        spec_rules_path: str = "configs/spec_rules_filtered.json",
        test_cases_path: str = "configs/test_cases.json",
        seed_frames_path: str = "llm_fuzzer/data/seed_frames.json",
        history_path: str = "llm_fuzzer/data/iteration_history.jsonl",
        output_dir: str = "llm_fuzzer/output",
        max_iterations: int = 50,
        available_vls: Optional[List[int]] = None
    ):
        """
        Initialize the fuzzer.
        
        Args:
            spec_rules_path: Path to protocol specification rules
            test_cases_path: Path to violation test cases
            seed_frames_path: Path to seed frames
            history_path: Path to iteration history file (JSONL)
            output_dir: Directory for output files
            max_iterations: Maximum number of fuzzing iterations
            available_vls: List of available VL IDs
        """
        self.spec_rules_path = spec_rules_path
        self.test_cases_path = test_cases_path
        self.seed_frames_path = seed_frames_path
        self.history_path = Path(history_path)
        self.output_dir = Path(output_dir)
        self.max_iterations = max_iterations
        self.available_vls = available_vls or [1001, 1002, 1003, 2001, 2002, 2003, 3001, 3002]
        
        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        print("Initializing components...")
        self.feedback_analyzer = FeedbackAnalyzer()
        self.strategy_planner = LLMStrategyPlanner(
            spec_rules_path=spec_rules_path,
            test_cases_path=test_cases_path
        )
        self.test_generator = TestGenerator(
            seed_frames_path=seed_frames_path,
            test_cases_path=test_cases_path
        )
        self.simulator_runner = SimulatorRunner()
        
        print("All components initialized successfully!")
    
    def load_history(self) -> pd.DataFrame:
        """
        Load iteration history from JSONL file.
        
        Returns:
            DataFrame with history, or empty DataFrame if no history exists
        """
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
        """
        Save iteration data to history file (append to JSONL).
        
        Args:
            iteration_data: Dictionary with iteration results
        """
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.history_path, 'a') as f:
            f.write(json.dumps(iteration_data) + '\n')
    
    def run_iteration(
        self,
        iteration: int,
        history: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        Run a single fuzzing iteration.
        
        Args:
            iteration: Current iteration number
            history: DataFrame with previous iterations
            
        Returns:
            Dictionary with iteration results
        """
        print(f"\n{'='*70}")
        print(f"ITERATION {iteration}")
        print(f"{'='*70}")
        
        iteration_start = datetime.now()
        
        try:
            # Step 1: LLM Strategy Planner
            print("\n[1/4] LLM Planning Strategy...")
            strategy = self.strategy_planner.plan_next_iteration(
                history=history if not history.empty else None,
                iteration=iteration,
                system_config={'available_vls': self.available_vls}
            )
            
            print(f"  Target VL: {strategy['target_vl']}")
            print(f"  Mutation Type: {strategy['mutation_type']}")
            
            # Show what LLM chose (test cases, params, or both)
            has_tc = strategy.get('test_cases') and len(strategy.get('test_cases', [])) > 0
            has_params = any([strategy.get('bag_value'), strategy.get('frame_size'), strategy.get('sequence_number')])
            
            if has_tc:
                print(f"  Test Cases: {strategy.get('test_cases')}")
            if has_params:
                print(f"  Custom Values: BAG={strategy.get('bag_value')}, Size={strategy.get('frame_size')}, Seq={strategy.get('sequence_number')}")
            
            print(f"  Strategy Type: {strategy['strategy']}")
            print(f"  Reasoning: {strategy['reasoning'][:100]}...")
            
            # Step 2: Test Generator
            print("\n[2/4] Generating Test Inputs...")
            test_inputs = self.test_generator.generate_test_inputs(strategy)
            
            print(f"  Generated {test_inputs['metadata']['num_frames']} frames")
            print(f"  VL ID: {test_inputs['vl_id']}")
            
            # Save test inputs
            test_file = self.output_dir / f"iteration_{iteration:03d}_test.json"
            self.test_generator.save_to_file(test_inputs, str(test_file))
            print(f"  Saved to: {test_file}")
            
            # Step 3: Simulator Runner
            print("\n[3/4] Running Simulator...")
            sim_result = self.simulator_runner.run_simulation(
                test_inputs=test_inputs,
                run_id=f"iter_{iteration:03d}",
                timeout=120
            )
            
            if sim_result['success']:
                print(f"  Simulation completed in {sim_result['duration']:.2f}s")
            else:
                print(f"  Simulation failed: {sim_result['error']}")
            
            # Step 4: Feedback Analyzer
            print("\n[4/4] Analyzing Feedback...")
            cov_pct = self.strategy_planner.category_coverage_pct(history)
            feedback = self.feedback_analyzer.analyze(
                log_content=sim_result.get('log_content', ''),
                csv_content=sim_result.get('csv_content', ''),
                strategy=strategy,
                history=history,
                coverage_pct=cov_pct
            )
            
            print(f"  Reward: {feedback.get('reward', 0.0):.3f}")
            policing_rate = feedback.get('metrics', {}).get('policing_rate', 0.0)
            print(f"  Policing Rate: {policing_rate:.1f}%")
            bugs_found = feedback.get('analysis', {}).get('bugs_found', False)
            print(f"  Bugs Found: {bugs_found}")
            recommendation = feedback.get('analysis', {}).get('recommendation', 'No recommendation')
            print(f"  Recommendation: {recommendation[:80]}...")
            
            # Compile iteration results (HYBRID FORMAT - LLM full freedom)
            iteration_data = {
                'iteration': iteration,
                'timestamp': datetime.now().isoformat(),
                'duration': (datetime.now() - iteration_start).total_seconds(),
                'target_vl': strategy['target_vl'],
                'mutation_type': strategy['mutation_type'],
                'protocol_rule': strategy.get('protocol_rule', strategy['mutation_type']),
                'test_cases': strategy.get('test_cases'),
                'bag_value': strategy.get('bag_value'),
                'frame_size': strategy.get('frame_size'),
                'sequence_number': strategy.get('sequence_number'),
                'timing_jitter_ms': strategy.get('timing_jitter_ms'),
                'payload_pattern': strategy.get('payload_pattern'),
                'mac_mutation_type': strategy.get('mac_mutation_type'),
                'prob': strategy.get('prob'),
                'sequence_number_override': strategy.get('sequence_number_override'),
                'dest_mac_mutation': strategy.get('dest_mac_mutation'),
                'strategy': strategy['strategy'],
                'reasoning': strategy['reasoning'],
                'num_frames': test_inputs['metadata']['num_frames'],
                'simulation_success': sim_result['success'],
                'reward': feedback['reward'],
                'frames_received': feedback['metrics'].get('frames_received', 0),
                'frames_dropped_policing': feedback['metrics'].get('frames_dropped_policing', 0),
                'frames_forwarded': feedback['metrics'].get('frames_forwarded', 0),
                'policing_rate': feedback['metrics'].get('policing_rate', 0.0),
                'forward_rate': feedback['metrics'].get('forward_rate', 0.0),
                'frames_dropped_frame_error': feedback['metrics'].get('frames_dropped_frame_error', 0),
                'frames_dropped_mac_error': feedback['metrics'].get('frames_dropped_mac_error', 0),
                'es_frames_rejected': feedback['metrics'].get('es_frames_rejected', 0),
                'es_duplicates_discarded': feedback['metrics'].get('es_duplicates_discarded', 0),
                'es_rejection_rate': feedback['metrics'].get('es_rejection_rate', 0.0),
                'bugs_found': feedback.get('analysis', {}).get('bugs_found', False),
                'recommendation': feedback.get('analysis', {}).get('recommendation', 'No recommendation')
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
                'target_vl': strategy.get('target_vl', -1) if 'strategy' in locals() else -1,
                'mutation_type': strategy.get('mutation_type', 'unknown') if 'strategy' in locals() else 'unknown',
                'protocol_rule': strategy.get('protocol_rule', strategy.get('mutation_type', 'unknown')) if 'strategy' in locals() else 'unknown',
                'test_cases': None,
                'bag_value': None,
                'frame_size': None,
                'sequence_number': None,
                'timing_jitter_ms': None,
                'payload_pattern': None,
                'strategy': strategy.get('strategy', 'unknown') if 'strategy' in locals() else 'unknown',
                'reasoning': strategy.get('reasoning', 'Error occurred') if 'strategy' in locals() else 'Error occurred',
                'num_frames': 0,
                'simulation_success': False,
                'reward': 0.0,
                'frames_received': 0,
                'frames_dropped_policing': 0,
                'frames_forwarded': 0,
                'policing_rate': 0.0,
                'forward_rate': 0.0,
                'bugs_found': False,
                'recommendation': f'Error: {str(e)}',
                'error': str(e),
                'success': False
            }
    
    def should_stop(
        self,
        iteration: int,
        history: pd.DataFrame,
        consecutive_failures: int
    ) -> bool:
        """
        Determine if fuzzing should stop.
        
        Args:
            iteration: Current iteration
            history: Full history DataFrame
            consecutive_failures: Number of consecutive failed iterations
            
        Returns:
            True if should stop, False otherwise
        """
        # Max iterations reached
        if iteration >= self.max_iterations:
            print(f"\nStopping: Reached max iterations ({self.max_iterations})")
            return True
        
        # Too many consecutive failures
        if consecutive_failures >= 10:
            print(f"\nStopping: {consecutive_failures} consecutive failures")
            return True
        
        return False
    
    def generate_report(self, history: pd.DataFrame) -> str:
        """
        Generate final fuzzing report.
        
        Args:
            history: Complete iteration history
            
        Returns:
            Report text
        """
        report_lines = []
        report_lines.append("=" * 70)
        report_lines.append("LLM-GUIDED FUZZING - FINAL REPORT")
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
            
            # Mutation types tested
            mutation_types = successful['mutation_type'].unique()
            report_lines.append(f"Mutation Types Tested: {len(mutation_types)}")
            report_lines.append(f"  Types: {sorted(mutation_types)}")
            report_lines.append("")
            
            # Strategy distribution
            report_lines.append("Strategy Distribution:")
            for strategy, count in successful['strategy'].value_counts().items():
                report_lines.append(f"  {strategy}: {count}")
            report_lines.append("")
            
            # Top performers
            top_5 = successful.nlargest(5, 'reward')[['iteration', 'target_vl', 'mutation_type', 'reward', 'bugs_found']]
            report_lines.append("Top 5 Iterations (by reward):")
            for idx, row in top_5.iterrows():
                bugs_str = " [BUG!]" if row['bugs_found'] else ""
                report_lines.append(f"  Iter {row['iteration']}: VL={row['target_vl']}, "
                                  f"mutation={row['mutation_type']}, reward={row['reward']:.3f}{bugs_str}")
        
        report_lines.append("")
        report_lines.append("=" * 70)
        
        return "\n".join(report_lines)
    
    def run(self):
        """
        Main fuzzing loop.
        
        Runs the complete LLM-guided fuzzing process.
        """
        print("\n" + "=" * 70)
        print("LLM-GUIDED AFDX FUZZER")
        print("=" * 70)
        print(f"\nConfiguration:")
        print(f"  Max Iterations: {self.max_iterations}")
        print(f"  Available VLs: {self.available_vls}")
        print(f"  History File: {self.history_path}")
        print(f"  Output Directory: {self.output_dir}")
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
        report_file = self.output_dir / f"fuzzing_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(report_file, 'w') as f:
            f.write(report)
        print(f"\nReport saved to: {report_file}")
        
        # Save full history as CSV
        if not history.empty:
            csv_file = self.output_dir / f"history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            history.to_csv(csv_file, index=False)
            print(f"Full history saved to: {csv_file}")
        
        print("\nFuzzing completed!")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="LLM-Guided AFDX Fuzzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with defaults (50 iterations)
  python3 llm_fuzzer/main.py
  
  # Run with custom iteration count
  python3 llm_fuzzer/main.py --max-iterations 100
  
  # Resume from previous run
  python3 llm_fuzzer/main.py --resume
  
  # Specify custom VLs
  python3 llm_fuzzer/main.py --vls 1001 1002 2001 2002
        """
    )
    
    parser.add_argument(
        '--max-iterations',
        type=int,
        default=50,
        help='Maximum number of fuzzing iterations (default: 50)'
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
        default='llm_fuzzer/output',
        help='Output directory for results (default: llm_fuzzer/output)'
    )
    
    parser.add_argument(
        '--spec-rules',
        type=str,
        default='configs/spec_rules_filtered.json',
        help='Path to protocol rules JSON (default: configs/spec_rules_filtered.json)'
    )
    
    parser.add_argument(
        '--resume',
        action='store_true',
        help='Resume from previous run (load existing history)'
    )
    
    args = parser.parse_args()
    
    # Create fuzzer
    fuzzer = LLMFuzzer(
        spec_rules_path=args.spec_rules,
        max_iterations=args.max_iterations,
        available_vls=args.vls,
        output_dir=args.output_dir
    )
    
    # Run
    try:
        fuzzer.run()
    except KeyboardInterrupt:
        print("\n\nFuzzing interrupted by user.")
        print("History saved. You can resume with --resume flag.")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

