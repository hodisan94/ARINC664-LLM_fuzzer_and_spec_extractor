#!/usr/bin/env python3
"""
Demo: Random Baseline Fuzzer with Mock Simulator

This demo shows how the random baseline fuzzer works with a mock simulator
(so you can test without running the actual ns-3 simulator).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from random_baseline.main import RandomFuzzer
from llm_fuzzer.utils.simulator_runner import SimulatorRunner


class MockSimulatorRunner(SimulatorRunner):
    """Mock simulator that returns fake results."""
    
    def run_simulation(self, test_inputs, scenario_name="mock", timeout=60, run_id=None):
        """Return mock simulation results."""
        import random
        
        # Mock metrics
        frames_received = test_inputs['metadata']['num_frames']
        frames_dropped = random.randint(0, frames_received // 2)
        frames_forwarded = frames_received - frames_dropped
        
        mock_log = f"""
Simulation Results:
frames received: {frames_received}
frames dropped (policing): {frames_dropped}
frames forwarded: {frames_forwarded}
frames dropped (invalid vl): 0
malformed accepted: 0
simulation time: 5.0
"""
        
        return {
            'success': True,
            'log_content': mock_log,
            'feedback_content': None,
            'stderr': '',
            'run_id': run_id or 'mock_run',
            'duration': 1.0,
            'error': None
        }


def main():
    """Run demo with mock simulator."""
    print("="*70)
    print("DEMO: Random Baseline Fuzzer with Mock Simulator")
    print("="*70)
    print("\nThis demo runs 3 iterations with a mock simulator")
    print("(no actual ns-3 execution)")
    print("")
    
    # Create fuzzer with mock simulator
    fuzzer = RandomFuzzer(
        max_iterations=3,
        history_path="random_baseline/data/demo_history.jsonl",
        output_dir="random_baseline/output/demo",
        random_seed=42  # For reproducibility
    )
    
    # Replace simulator with mock
    fuzzer.simulator_runner = MockSimulatorRunner(skip_ns3_check=True)
    
    # Run
    try:
        fuzzer.run()
    except KeyboardInterrupt:
        print("\nDemo interrupted.")
    except Exception as e:
        print(f"\nDemo error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

