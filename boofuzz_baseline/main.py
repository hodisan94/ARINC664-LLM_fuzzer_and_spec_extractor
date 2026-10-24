#!/usr/bin/env python3
"""
boofuzz Baseline Fuzzer - Main Entry Point

This is the main fuzzing loop for the boofuzz baseline, designed to be
directly comparable to the LLM fuzzer and Random fuzzer.

Key differences:
- LLM Fuzzer: Learns from results, intelligently selects tests
- Random Fuzzer: Randomly selects tests, no learning
- boofuzz Baseline: Systematically tests ALL violations in order, no learning

All three use:
- Same test cases (from test_cases.json)
- Same frame generator (TestGenerator)
- Same simulator runner (SimulatorRunner, real ns-3)
- Same feedback analyzer & reward calculator
- Same output format
"""

import sys
import json
import argparse
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(Path(__file__).parent.parent / ".env")

from boofuzz_baseline.boofuzz_strategy_generator import BoofuzzStrategyGenerator
from llm_fuzzer.core.test_generator import TestGenerator
from llm_fuzzer.core.feedback_analyzer import FeedbackAnalyzer
from llm_fuzzer.core.reward_calculator import RewardCalculator
from llm_fuzzer.utils.simulator_runner import SimulatorRunner


class BoofuzzFuzzer:
    """
    boofuzz Baseline Fuzzer - Systematic Protocol Testing

    Tests all violations in deterministic order using the SAME
    infrastructure as the LLM and Random fuzzers.
    """

    def __init__(
        self,
        spec_rules_path: str = "configs/spec_rules_filtered.json",
        test_cases_path: str = "configs/test_cases.json",
        seed_frames_path: str = "llm_fuzzer/data/seed_frames.json",
        history_path: str = "boofuzz_baseline/data/iteration_history.jsonl",
        output_dir: str = "boofuzz_baseline/output",
        max_iterations: int = 50,
        available_vls: Optional[List[int]] = None,
        work_dir: Optional[str] = None,
    ):
        self.max_iterations = max_iterations
        self.available_vls = available_vls or [1001, 1002, 1003, 2001, 2002, 2003, 3001, 3002]
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.history_path = Path(history_path)
        self.history_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize components (SAME as LLM / Random fuzzer)
        print("Initializing components...")
        self.strategy_generator = BoofuzzStrategyGenerator(
            test_cases_path=test_cases_path,
            spec_rules_path=spec_rules_path,
        )
        self.test_generator = TestGenerator(
            seed_frames_path=seed_frames_path,
            test_cases_path=test_cases_path,
        )
        self.feedback_analyzer = FeedbackAnalyzer()
        self.reward_calculator = RewardCalculator()
        self.simulator_runner = SimulatorRunner(work_dir=work_dir)

        self.iteration_history = []

        self.system_config = {
            'available_vls': self.available_vls,
            'fuzzer_type': 'boofuzz',
        }
        print("All components initialized successfully!")

    # ------------------------------------------------------------------
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
            return pd.DataFrame()
        except Exception as e:
            print(f"Warning: Could not load history: {e}")
            return pd.DataFrame()

    def save_iteration(self, iteration_data: Dict[str, Any]):
        with open(self.history_path, 'a') as f:
            f.write(json.dumps(iteration_data) + '\n')

    # ------------------------------------------------------------------
    def run_iteration(self, iteration: int, history: pd.DataFrame) -> Dict[str, Any]:
        """Run a single fuzzing iteration (same flow as Random / LLM)."""
        print(f"\n{'='*70}")
        print(f"ITERATION {iteration}")
        print(f"{'='*70}")

        iteration_start = datetime.now()

        try:
            # Step 1: Strategy (deterministic)
            print("\n[1/4] Generating Boofuzz Strategy...")
            strategy = self.strategy_generator.plan_next_iteration(
                history=None,
                iteration=iteration,
                system_config=self.system_config,
            )
            print(f"  Target VL: {strategy['target_vl']}")
            print(f"  Violation: {strategy['violation_id']}")
            print(f"  Rule: {strategy['protocol_rule']}")
            print(f"  Type: {strategy['violation_type']}")

            # Step 2: Test Generator (SAME as LLM / Random)
            print("\n[2/4] Generating Test Inputs...")
            test_inputs = self.test_generator.generate_test_inputs(strategy)

            # Fallback if predefined mode produced 0 frames
            if test_inputs['metadata']['num_frames'] == 0 and strategy.get('test_mode') == 'predefined':
                print("  [WARN] Predefined mode produced 0 frames, falling back to mutation params")
                strategy['test_cases'] = None
                strategy['test_mode'] = 'custom_fallback'
                rule = strategy.get('protocol_rule', '').lower()
                if 'bag' in rule:
                    strategy['bag_value'] = strategy.get('bag_value') or 0
                elif 'frame' in rule or 'ethernet' in rule:
                    strategy['frame_size'] = strategy.get('frame_size') or 63
                elif 'sequence' in rule:
                    strategy['sequence_number'] = strategy.get('sequence_number') or 0
                else:
                    strategy['bag_value'] = strategy.get('bag_value') or 1
                    strategy['frame_size'] = strategy.get('frame_size') or 63
                test_inputs = self.test_generator.generate_test_inputs(strategy)

            print(f"  Generated {test_inputs['metadata']['num_frames']} frames")
            print(f"  VL ID: {test_inputs['vl_id']}")

            # Save test inputs
            test_file = self.output_dir / f"iteration_{iteration:03d}_test.json"
            self.test_generator.save_to_file(test_inputs, str(test_file))
            print(f"  Saved to: {test_file}")

            # Step 3: Simulator Runner (SAME as LLM / Random)
            print("\n[3/4] Running Simulator...")
            history_df = pd.DataFrame(self.iteration_history) if self.iteration_history else None
            sim_result = self.simulator_runner.run_simulation(
                test_inputs=test_inputs,
                run_id=f"boofuzz_iter_{iteration:03d}",
                timeout=120,
            )

            if sim_result['success']:
                print(f"  Simulation completed in {sim_result['duration']:.2f}s")
            else:
                print(f"  Simulation failed: {sim_result.get('error', 'unknown')}")

            # Step 4: Feedback Analyzer (SAME as LLM / Random)
            print("\n[4/4] Analyzing Feedback...")
            feedback = self.feedback_analyzer.analyze(
                log_content=sim_result.get('log_content', ''),
                csv_content=sim_result.get('csv_content', ''),
                strategy=strategy,
                history=history_df,
            )

            policing_rate = feedback.get('metrics', {}).get('policing_rate', 0.0)
            forward_rate = feedback.get('metrics', {}).get('forward_rate', 0.0)
            bugs_found = feedback.get('analysis', {}).get('bugs_found', False)

            print(f"  Reward: {feedback.get('reward', 0.0):.3f}")
            print(f"  Policing Rate: {policing_rate:.1f}%")
            print(f"  Bugs Found: {bugs_found}")

            iteration_record = {
                'iteration': iteration,
                'timestamp': datetime.now().isoformat(),
                'duration': (datetime.now() - iteration_start).total_seconds(),
                'fuzzer_type': 'BOOFUZZ_BASELINE',
                'target_vl': strategy['target_vl'],
                'mutation_type': strategy['mutation_type'],
                'protocol_rule': strategy['protocol_rule'],
                'violation_id': strategy['violation_id'],
                'violation_type': strategy['violation_type'],
                'strategy': strategy['strategy'],
                'test_mode': strategy.get('test_mode', 'predefined'),
                'test_cases': strategy.get('test_cases'),
                'bag_value': strategy.get('bag_value'),
                'frame_size': strategy.get('frame_size'),
                'sequence_number': strategy.get('sequence_number'),
                'sim_config': sim_result.get('sim_config'),
                'mac_mutation_type': strategy.get('mac_mutation_type'),
                'dest_mac_mutation': strategy.get('dest_mac_mutation'),
                'sequence_number_override': strategy.get('sequence_number_override'),
                'timing_jitter_ms': strategy.get('timing_jitter_ms'),
                'prob': strategy.get('prob'),
                'reasoning': strategy['reasoning'],
                'num_frames': test_inputs['metadata']['num_frames'],
                'simulation_success': sim_result['success'],
                'reward': feedback['reward'],
                'frames_received': feedback['metrics'].get('frames_received', 0),
                'frames_dropped_policing': feedback['metrics'].get('frames_dropped_policing', 0),
                'frames_forwarded': feedback['metrics'].get('frames_forwarded', 0),
                'policing_rate': policing_rate,
                'forward_rate': forward_rate,
                'frames_dropped_frame_error': feedback['metrics'].get('frames_dropped_frame_error', 0),
                'frames_dropped_mac_error': feedback['metrics'].get('frames_dropped_mac_error', 0),
                'es_frames_rejected': feedback['metrics'].get('es_frames_rejected', 0),
                'es_duplicates_discarded': feedback['metrics'].get('es_duplicates_discarded', 0),
                'es_rejection_rate': feedback['metrics'].get('es_rejection_rate', 0.0),
                'bugs_found': bugs_found,
            }

            self.iteration_history.append(iteration_record)
            print(f"\nIteration {iteration} completed successfully!")
            return iteration_record

        except Exception as e:
            print(f"\nERROR in iteration {iteration}: {e}")
            import traceback
            traceback.print_exc()

            return {
                'iteration': iteration,
                'timestamp': datetime.now().isoformat(),
                'duration': (datetime.now() - iteration_start).total_seconds(),
                'fuzzer_type': 'BOOFUZZ_BASELINE',
                'target_vl': strategy.get('target_vl', -1) if 'strategy' in dir() else -1,
                'mutation_type': 'unknown',
                'protocol_rule': 'unknown',
                'violation_id': 'unknown',
                'violation_type': 'unknown',
                'strategy': 'unknown',
                'test_mode': 'unknown',
                'test_cases': None,
                'bag_value': None,
                'frame_size': None,
                'sequence_number': None,
                'reasoning': f'Error: {str(e)}',
                'num_frames': 0,
                'simulation_success': False,
                'reward': 0.0,
                'frames_received': 0,
                'frames_dropped_policing': 0,
                'frames_forwarded': 0,
                'policing_rate': 0.0,
                'forward_rate': 0.0,
                'frames_dropped_frame_error': 0,
                'frames_dropped_mac_error': 0,
                'es_frames_rejected': 0,
                'es_duplicates_discarded': 0,
                'es_rejection_rate': 0.0,
                'bugs_found': False,
                'error': str(e),
                'success': False,
            }

    # ------------------------------------------------------------------
    def should_stop(self, iteration: int, consecutive_failures: int) -> bool:
        if iteration >= self.max_iterations:
            print(f"\nStopping: Reached max iterations ({self.max_iterations})")
            return True
        if consecutive_failures >= 5:
            print(f"\nStopping: {consecutive_failures} consecutive failures")
            return True
        return False

    # ------------------------------------------------------------------
    def run(self) -> Dict[str, Any]:
        print("\n" + "=" * 70)
        print("BOOFUZZ BASELINE FUZZER")
        print("=" * 70)
        print(f"\nConfiguration:")
        print(f"  Max iterations: {self.max_iterations}")
        print(f"  Available VLs: {self.available_vls}")
        print(f"  Total test cases: {len(self.strategy_generator.all_violations)}")
        print(f"  Simulator: ns-3 (real)")
        print(f"  History File: {self.history_path}")
        print(f"  Output Directory: {self.output_dir}")
        print("=" * 70 + "\n")

        # Load history
        history = self.load_history()
        start_iteration = len(history) if not history.empty else 0
        if start_iteration > 0:
            print(f"\nResuming from iteration {start_iteration}")

        start_time = datetime.now()
        consecutive_failures = 0

        for iteration in range(start_iteration, self.max_iterations):
            result = self.run_iteration(iteration, history)

            self.save_iteration(result)

            new_row = pd.DataFrame([result])
            history = pd.concat([history, new_row], ignore_index=True)

            if not result.get('simulation_success', False):
                consecutive_failures += 1
            else:
                consecutive_failures = 0

            if self.should_stop(iteration + 1, consecutive_failures):
                break

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        summary = self._generate_summary(duration, history)
        self._save_report(summary)
        return summary

    # ------------------------------------------------------------------
    def _generate_summary(self, duration: float, history: pd.DataFrame) -> Dict[str, Any]:
        if history.empty:
            return {'error': 'No successful iterations'}

        df = history
        progress = self.strategy_generator.get_progress()

        successful = df[df.get('simulation_success', True) == True] if 'simulation_success' in df.columns else df

        summary = {
            'fuzzer_type': 'boofuzz',
            'total_iterations': len(df),
            'successful_iterations': len(successful),
            'duration_seconds': duration,
            'violations_tested': progress['tested_violations'],
            'total_violations': progress['total_violations'],
            'coverage_percent': progress['coverage_percent'],
        }

        if not successful.empty and 'reward' in successful.columns:
            summary.update({
                'reward_mean': float(successful['reward'].mean()),
                'reward_max': float(successful['reward'].max()),
                'reward_min': float(successful['reward'].min()),
                'reward_std': float(successful['reward'].std()) if len(successful) > 1 else 0.0,
                'avg_policing_rate': float(successful['policing_rate'].mean()),
                'vls_tested': int(successful['target_vl'].nunique()),
                'rules_tested': int(successful['protocol_rule'].nunique()) if 'protocol_rule' in successful.columns else 0,
            })

        return summary

    def _save_report(self, summary: Dict[str, Any]):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        summary_file = self.output_dir / f"boofuzz_summary_{timestamp}.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)

        if self.iteration_history:
            df = pd.DataFrame(self.iteration_history)
            csv_file = self.output_dir / f"boofuzz_history_{timestamp}.csv"
            df.to_csv(csv_file, index=False)

        print("\n" + "=" * 70)
        print("BOOFUZZ BASELINE SUMMARY")
        print("=" * 70)
        print(f"Total iterations: {summary.get('total_iterations', 0)}")
        print(f"Successful: {summary.get('successful_iterations', 0)}")
        print(f"Duration: {summary.get('duration_seconds', 0):.1f} seconds")
        print(f"Coverage: {summary.get('coverage_percent', 0):.1f}%")
        print(f"Mean reward: {summary.get('reward_mean', 0):.3f}")
        print(f"Avg policing rate: {summary.get('avg_policing_rate', 0):.1f}%")
        print("=" * 70)
        print(f"\nSummary saved to: {summary_file}")


def main():
    parser = argparse.ArgumentParser(
        description="boofuzz Baseline Fuzzer for AFDX",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with defaults (50 iterations, real ns-3 simulator)
  python3 boofuzz_baseline/main.py

  # Run with custom iteration count
  python3 boofuzz_baseline/main.py --max-iterations 100

  # Specify custom VLs
  python3 boofuzz_baseline/main.py --vls 1001 1002 2001 2002
        """,
    )

    parser.add_argument(
        '--max-iterations', type=int, default=50,
        help='Maximum iterations (default: 50)',
    )
    parser.add_argument(
        '--vls', type=int, nargs='+', default=None,
        help='VLs to test (default: 1001-3002, all 8)',
    )
    parser.add_argument(
        '--output-dir', type=str, default='boofuzz_baseline/output',
        help='Output directory for results',
    )

    parser.add_argument(
        '--history-path', type=str, default='boofuzz_baseline/data/iteration_history.jsonl',
        help='Path to iteration history JSONL',
    )
    parser.add_argument(
        '--work-dir', type=str, default=None,
        help='Isolated simulator working directory, for parallel campaigns',
    )

    args = parser.parse_args()

    fuzzer = BoofuzzFuzzer(
        max_iterations=args.max_iterations,
        available_vls=args.vls,
        output_dir=args.output_dir,
        history_path=args.history_path,
        work_dir=args.work_dir,
    )
    try:
        fuzzer.run()
    except KeyboardInterrupt:
        print("\n\nFuzzing interrupted by user.")
        print("History saved. You can resume later.")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
