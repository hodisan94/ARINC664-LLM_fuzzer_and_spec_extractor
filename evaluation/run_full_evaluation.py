#!/usr/bin/env python3
"""
Full Evaluation Pipeline: Run All Three Fuzzers and Compare

This script automates the complete evaluation process:
1. Run LLM-Guided Fuzzer
2. Run boofuzz Baseline
3. Run Random Baseline
4. Generate comprehensive comparison report

Usage:
    python3 evaluation/run_full_evaluation.py --iterations 50
"""

import sys
import subprocess
import argparse
from pathlib import Path
from datetime import datetime
import json

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class FullEvaluation:
    """
    Run complete evaluation of all three fuzzers.
    """
    
    def __init__(
        self,
        iterations: int = 50,
        available_vls: list = None,
        use_mock: bool = True
    ):
        """
        Initialize evaluation.
        
        Args:
            iterations: Iterations per fuzzer
            available_vls: VLs to test
            use_mock: Use mock simulator
        """
        self.iterations = iterations
        self.available_vls = available_vls or [1001, 1002, 2001, 2002]
        self.use_mock = use_mock
        
        self.base_path = Path(__file__).parent.parent
        self.results = {}
    
    def run_llm_fuzzer(self) -> bool:
        """Run LLM-guided fuzzer."""
        print("\n" + "=" * 70)
        print("RUNNING LLM-GUIDED FUZZER")
        print("=" * 70)
        
        # Clear previous history
        history_file = self.base_path / "llm_fuzzer/data/iteration_history.jsonl"
        if history_file.exists():
            backup = history_file.parent / f"history_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
            history_file.rename(backup)
            print(f"Backed up previous history to: {backup}")
        
        cmd = [
            sys.executable, "llm_fuzzer/main.py",
            "--max-iterations", str(self.iterations)
        ]
        
        if self.available_vls:
            cmd.extend(["--vls"] + [str(vl) for vl in self.available_vls])
        
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.base_path),
                check=True
            )
            print("\n✓ LLM Fuzzer completed successfully!")
            return True
        except subprocess.CalledProcessError as e:
            print(f"\n✗ LLM Fuzzer failed: {e}")
            return False
        except FileNotFoundError:
            print("\n✗ LLM Fuzzer script not found")
            return False
    
    def run_boofuzz_fuzzer(self) -> bool:
        """Run boofuzz baseline."""
        print("\n" + "=" * 70)
        print("RUNNING BOOFUZZ BASELINE")
        print("=" * 70)
        
        # Clear previous history
        history_file = self.base_path / "boofuzz_baseline/data/iteration_history.jsonl"
        if history_file.exists():
            backup = history_file.parent / f"history_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
            history_file.rename(backup)
            print(f"Backed up previous history to: {backup}")
        
        cmd = [
            sys.executable, "boofuzz_baseline/main.py",
            "--max-iterations", str(self.iterations)
        ]
        
        if self.available_vls:
            cmd.extend(["--vls"] + [str(vl) for vl in self.available_vls])
        
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.base_path),
                check=True
            )
            print("\n✓ boofuzz Baseline completed successfully!")
            return True
        except subprocess.CalledProcessError as e:
            print(f"\n✗ boofuzz Baseline failed: {e}")
            return False
        except FileNotFoundError:
            print("\n✗ boofuzz Baseline script not found")
            return False
    
    def run_random_fuzzer(self) -> bool:
        """Run random baseline."""
        print("\n" + "=" * 70)
        print("RUNNING RANDOM BASELINE")
        print("=" * 70)
        
        # Clear previous history
        history_file = self.base_path / "random_baseline/data/iteration_history.jsonl"
        if history_file.exists():
            backup = history_file.parent / f"history_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
            history_file.rename(backup)
            print(f"Backed up previous history to: {backup}")
        
        cmd = [
            sys.executable, "random_baseline/main.py",
            "--max-iterations", str(self.iterations)
        ]
        
        if self.available_vls:
            cmd.extend(["--vls"] + [str(vl) for vl in self.available_vls])
        
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.base_path),
                check=True
            )
            print("\n✓ Random Baseline completed successfully!")
            return True
        except subprocess.CalledProcessError as e:
            print(f"\n✗ Random Baseline failed: {e}")
            return False
        except FileNotFoundError:
            print("\n✗ Random Baseline script not found")
            return False
    
    def run_comparison(self) -> dict:
        """Run three-way comparison."""
        print("\n" + "=" * 70)
        print("RUNNING THREE-WAY COMPARISON")
        print("=" * 70)
        
        from evaluation.three_way_comparison import ThreeWayComparison
        
        comparison = ThreeWayComparison()
        return comparison.compare_all()
    
    def run(self):
        """Run complete evaluation."""
        print("=" * 70)
        print("FULL FUZZER EVALUATION")
        print("=" * 70)
        print(f"\nIterations per fuzzer: {self.iterations}")
        print(f"Available VLs: {self.available_vls}")
        print(f"Simulator: {'Mock' if self.use_mock else 'ns-3'}")
        print("=" * 70)
        
        start_time = datetime.now()
        
        # Run each fuzzer
        llm_success = self.run_llm_fuzzer()
        boofuzz_success = self.run_boofuzz_fuzzer()
        random_success = self.run_random_fuzzer()
        
        # Run comparison
        if llm_success or boofuzz_success or random_success:
            self.results = self.run_comparison()
        
        # Summary
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print("\n" + "=" * 70)
        print("EVALUATION COMPLETE")
        print("=" * 70)
        print(f"Total duration: {duration:.1f} seconds")
        print(f"LLM Fuzzer: {'✓' if llm_success else '✗'}")
        print(f"boofuzz Baseline: {'✓' if boofuzz_success else '✗'}")
        print(f"Random Baseline: {'✓' if random_success else '✗'}")
        print("=" * 70)
        
        return self.results


def main():
    parser = argparse.ArgumentParser(
        description="Run complete fuzzer evaluation"
    )
    
    parser.add_argument(
        '--iterations',
        type=int,
        default=50,
        help='Iterations per fuzzer (default: 50)'
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
    
    parser.add_argument(
        '--skip-llm',
        action='store_true',
        help='Skip LLM fuzzer (use existing results)'
    )
    
    parser.add_argument(
        '--skip-boofuzz',
        action='store_true',
        help='Skip boofuzz (use existing results)'
    )
    
    parser.add_argument(
        '--skip-random',
        action='store_true',
        help='Skip random fuzzer (use existing results)'
    )
    
    parser.add_argument(
        '--compare-only',
        action='store_true',
        help='Only run comparison (skip all fuzzers)'
    )
    
    args = parser.parse_args()
    
    evaluation = FullEvaluation(
        iterations=args.iterations,
        available_vls=args.vls,
        use_mock=not args.use_real_simulator
    )
    
    if args.compare_only:
        # Just run comparison
        from evaluation.three_way_comparison import ThreeWayComparison
        comparison = ThreeWayComparison()
        comparison.compare_all()
    else:
        # Run full evaluation
        evaluation.run()


if __name__ == "__main__":
    main()

