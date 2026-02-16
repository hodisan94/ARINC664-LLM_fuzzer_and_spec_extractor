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
- Same frame generator
- Same simulator runner
- Same reward calculator
- Same output format

Only the STRATEGY SELECTION differs.
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
import pandas as pd

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from boofuzz_baseline.boofuzz_strategy_generator import BoofuzzStrategyGenerator
from llm_fuzzer.core.test_generator import TestGenerator
from llm_fuzzer.core.feedback_analyzer import FeedbackAnalyzer
from llm_fuzzer.core.reward_calculator import RewardCalculator


class MockSimulatorRunner:
    """Mock simulator for testing without ns-3."""
    
    def __init__(self):
        pass
    
    def run(self, test_file: str) -> Dict[str, Any]:
        """Simulate running the test."""
        import random
        
        # Generate realistic mock results
        policing_rate = random.uniform(20, 90)
        forward_rate = 100 - policing_rate
        bugs_found = 1 if random.random() > 0.7 else 0
        
        return {
            'success': True,
            'log_content': f'Mock simulation completed for {test_file}',
            'frames_sent': 20,
            'frames_dropped': int(20 * policing_rate / 100),
            'policing_rate': policing_rate,
            'forward_rate': forward_rate,
            'bugs_found': bugs_found
        }


class BoofuzzFuzzer:
    """
    boofuzz Baseline Fuzzer - Systematic Protocol Testing
    
    This fuzzer tests all violations in deterministic order,
    representing the industry-standard approach to protocol fuzzing.
    """
    
    def __init__(
        self,
        max_iterations: int = 50,
        available_vls: list = None,
        output_dir: str = "boofuzz_baseline/output",
        use_mock_simulator: bool = True
    ):
        """
        Initialize boofuzz fuzzer.
        
        Args:
            max_iterations: Maximum iterations to run
            available_vls: VLs to test
            output_dir: Output directory
            use_mock_simulator: Use mock simulator (True) or real ns-3 (False)
        """
        self.max_iterations = max_iterations
        self.available_vls = available_vls or [1001, 1002, 2001, 2002]
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.use_mock_simulator = use_mock_simulator
        
        # Initialize components (same as LLM fuzzer)
        self.strategy_generator = BoofuzzStrategyGenerator()
        self.test_generator = TestGenerator()
        self.feedback_analyzer = FeedbackAnalyzer()
        self.reward_calculator = RewardCalculator()
        
        # Use mock or real simulator
        if use_mock_simulator:
            self.simulator_runner = MockSimulatorRunner()
        else:
            from llm_fuzzer.utils.simulator_runner import SimulatorRunner
            self.simulator_runner = SimulatorRunner(skip_ns3_check=True)
        
        # History tracking
        self.history_file = self.output_dir.parent / "data" / "iteration_history.jsonl"
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        self.iteration_history = []
        
        # System config
        self.system_config = {
            'available_vls': self.available_vls,
            'fuzzer_type': 'boofuzz'
        }
    
    def run(self) -> Dict[str, Any]:
        """
        Run the boofuzz fuzzing campaign.
        
        Returns:
            Summary statistics
        """
        print("=" * 70)
        print("BOOFUZZ BASELINE FUZZER")
        print("=" * 70)
        print(f"\nMax iterations: {self.max_iterations}")
        print(f"Available VLs: {self.available_vls}")
        print(f"Total test cases: {len(self.strategy_generator.all_violations)}")
        print(f"Simulator: {'Mock' if self.use_mock_simulator else 'ns-3'}")
        print("=" * 70 + "\n")
        
        start_time = datetime.now()
        consecutive_failures = 0
        
        for iteration in range(self.max_iterations):
            print(f"\n--- Iteration {iteration + 1}/{self.max_iterations} ---")
            
            try:
                # 1. Get next strategy (deterministic)
                strategy = self.strategy_generator.plan_next_iteration(
                    history=None,  # boofuzz doesn't learn
                    iteration=iteration,
                    system_config=self.system_config
                )
                
                print(f"Testing: {strategy['violation_id']} on VL {strategy['target_vl']}")
                print(f"Type: {strategy['violation_type']}")
                
                # 2. Generate test frames
                test_inputs = self.test_generator.generate_test_inputs(strategy)
                
                # Save test inputs
                test_file = self.output_dir / f"iteration_{iteration:03d}_test.json"
                self.test_generator.save_to_file(test_inputs, str(test_file))
                
                # 3. Run simulator
                sim_result = self.simulator_runner.run(str(test_file))
                
                if not sim_result.get('success', False):
                    print(f"  Simulation failed!")
                    consecutive_failures += 1
                    
                    if consecutive_failures >= 5:
                        print("\n5 consecutive failures - stopping")
                        break
                    continue
                
                consecutive_failures = 0
                
                # 4. Analyze results
                analysis = self.feedback_analyzer.analyze(sim_result)
                
                # 5. Calculate reward - extract metrics from analysis
                metrics = {
                    'policing_rate': analysis.get('policing_rate', 0),
                    'forward_rate': analysis.get('forward_rate', 0),
                    'frames_sent': analysis.get('frames_sent', 20),
                    'frames_dropped': analysis.get('frames_dropped', 0),
                    'bugs_found': analysis.get('bugs_found', 0)
                }
                
                # Convert history to DataFrame if needed
                history_df = pd.DataFrame(self.iteration_history) if self.iteration_history else None
                
                reward = self.reward_calculator.calculate(
                    metrics=metrics,
                    strategy=strategy,
                    history=history_df
                )
                
                print(f"  Reward: {reward['reward']:.3f}")
                print(f"  Policing rate: {analysis.get('policing_rate', 0):.1f}%")
                
                # 6. Record iteration
                iteration_record = {
                    'iteration': iteration,
                    'timestamp': datetime.now().isoformat(),
                    'target_vl': strategy['target_vl'],
                    'mutation_type': strategy['mutation_type'],
                    'protocol_rule': strategy['protocol_rule'],
                    'violation_id': strategy['violation_id'],
                    'violation_type': strategy['violation_type'],
                    'strategy': strategy['strategy'],
                    'test_cases': strategy.get('test_cases'),
                    'bag_value': strategy.get('bag_value'),
                    'frame_size': strategy.get('frame_size'),
                    'sequence_number': strategy.get('sequence_number'),
                    'reasoning': strategy['reasoning'],
                    'simulation_success': True,
                    'reward': reward['reward'],
                    'policing_rate': analysis.get('policing_rate', 0),
                    'forward_rate': analysis.get('forward_rate', 0),
                    'bugs_found': analysis.get('bugs_found', 0),
                    'frames_sent': analysis.get('frames_sent', 0),
                    'frames_dropped': analysis.get('frames_dropped', 0)
                }
                
                self.iteration_history.append(iteration_record)
                
                # 7. Save to history file
                with open(self.history_file, 'a') as f:
                    f.write(json.dumps(iteration_record) + '\n')
            
            except KeyboardInterrupt:
                print("\n\nInterrupted by user")
                break
            except Exception as e:
                print(f"  Error: {e}")
                consecutive_failures += 1
                
                if consecutive_failures >= 5:
                    print("\n5 consecutive failures - stopping")
                    break
                continue
        
        # Generate summary
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        summary = self._generate_summary(duration)
        self._save_report(summary)
        
        return summary
    
    def _generate_summary(self, duration: float) -> Dict[str, Any]:
        """Generate summary statistics."""
        if not self.iteration_history:
            return {'error': 'No successful iterations'}
        
        df = pd.DataFrame(self.iteration_history)
        progress = self.strategy_generator.get_progress()
        
        return {
            'fuzzer_type': 'boofuzz',
            'total_iterations': len(df),
            'duration_seconds': duration,
            'violations_tested': progress['tested_violations'],
            'total_violations': progress['total_violations'],
            'coverage_percent': progress['coverage_percent'],
            'reward_mean': float(df['reward'].mean()),
            'reward_max': float(df['reward'].max()),
            'reward_min': float(df['reward'].min()),
            'reward_std': float(df['reward'].std()),
            'total_bugs_found': int(df['bugs_found'].sum()),
            'avg_policing_rate': float(df['policing_rate'].mean()),
            'vls_tested': df['target_vl'].nunique(),
            'rules_tested': df['protocol_rule'].nunique(),
            'violation_types_tested': df['violation_type'].nunique()
        }
    
    def _save_report(self, summary: Dict[str, Any]):
        """Save final report."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Save JSON summary
        summary_file = self.output_dir / f"boofuzz_summary_{timestamp}.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        # Save CSV history
        if self.iteration_history:
            df = pd.DataFrame(self.iteration_history)
            csv_file = self.output_dir / f"boofuzz_history_{timestamp}.csv"
            df.to_csv(csv_file, index=False)
        
        # Print summary
        print("\n" + "=" * 70)
        print("BOOFUZZ BASELINE SUMMARY")
        print("=" * 70)
        print(f"Total iterations: {summary.get('total_iterations', 0)}")
        print(f"Duration: {summary.get('duration_seconds', 0):.1f} seconds")
        print(f"Coverage: {summary.get('coverage_percent', 0):.1f}%")
        print(f"Mean reward: {summary.get('reward_mean', 0):.3f}")
        print(f"Bugs found: {summary.get('total_bugs_found', 0)}")
        print(f"Avg policing rate: {summary.get('avg_policing_rate', 0):.1f}%")
        print("=" * 70)
        print(f"\nSummary saved to: {summary_file}")


def main():
    parser = argparse.ArgumentParser(
        description="boofuzz Baseline Fuzzer for AFDX"
    )
    
    parser.add_argument(
        '--max-iterations',
        type=int,
        default=50,
        help='Maximum iterations (default: 50)'
    )
    
    parser.add_argument(
        '--vls',
        type=int,
        nargs='+',
        default=[1001, 1002, 2001, 2002],
        help='VLs to test (default: 1001 1002 2001 2002)'
    )
    
    parser.add_argument(
        '--use-real-simulator',
        action='store_true',
        help='Use real ns-3 simulator instead of mock'
    )
    
    args = parser.parse_args()
    
    fuzzer = BoofuzzFuzzer(
        max_iterations=args.max_iterations,
        available_vls=args.vls,
        use_mock_simulator=not args.use_real_simulator
    )
    
    fuzzer.run()


if __name__ == "__main__":
    main()

