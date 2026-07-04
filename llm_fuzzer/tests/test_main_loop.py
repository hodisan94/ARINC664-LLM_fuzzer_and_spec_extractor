#!/usr/bin/env python3
"""
Unit tests for main fuzzing loop.
"""

import unittest
import sys
import tempfile
import shutil
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from llm_fuzzer.main import LLMFuzzer


class TestMainLoop(unittest.TestCase):
    """Test main fuzzing loop functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create temporary directory
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        
        # Create test paths
        self.history_path = self.temp_path / "test_history.jsonl"
        self.output_dir = self.temp_path / "output"
        
    def tearDown(self):
        """Clean up test files."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_fuzzer_initialization(self):
        """Test fuzzer initializes correctly."""
        fuzzer = LLMFuzzer(
            history_path=str(self.history_path),
            output_dir=str(self.output_dir),
            max_iterations=10
        )
        
        self.assertEqual(fuzzer.max_iterations, 10)
        self.assertTrue(fuzzer.output_dir.exists())
        self.assertIsNotNone(fuzzer.feedback_analyzer)
        self.assertIsNotNone(fuzzer.strategy_planner)
        self.assertIsNotNone(fuzzer.test_generator)
        self.assertIsNotNone(fuzzer.simulator_runner)
    
    def test_load_empty_history(self):
        """Test loading history when file doesn't exist."""
        fuzzer = LLMFuzzer(
            history_path=str(self.history_path),
            output_dir=str(self.output_dir)
        )
        
        history = fuzzer.load_history()
        self.assertTrue(history.empty)
    
    def test_load_existing_history(self):
        """Test loading history from existing file."""
        # Create sample history
        sample_data = [
            {"iteration": 0, "reward": 1.5, "target_vl": 1001},
            {"iteration": 1, "reward": 1.2, "target_vl": 1002}
        ]
        
        with open(self.history_path, 'w') as f:
            for item in sample_data:
                f.write(json.dumps(item) + '\n')
        
        fuzzer = LLMFuzzer(
            history_path=str(self.history_path),
            output_dir=str(self.output_dir)
        )
        
        history = fuzzer.load_history()
        self.assertEqual(len(history), 2)
        self.assertEqual(history.iloc[0]['iteration'], 0)
        self.assertEqual(history.iloc[1]['reward'], 1.2)

    def test_run_refuses_existing_history_without_resume_or_force(self):
        """Test fresh runs do not silently reuse existing history."""
        with open(self.history_path, 'w') as f:
            f.write(json.dumps({"iteration": 0, "reward": 1.5}) + '\n')

        fuzzer = LLMFuzzer(
            history_path=str(self.history_path),
            output_dir=str(self.output_dir),
            max_iterations=1
        )

        with self.assertRaises(FileExistsError):
            fuzzer.run()

    def test_run_resume_allows_existing_history(self):
        """Test explicit resume loads existing history."""
        with open(self.history_path, 'w') as f:
            f.write(json.dumps({
                "iteration": 0,
                "target_vl": 1001,
                "protocol_rule": "bag",
                "reward": 1.5,
                "bugs_found": False,
                "strategy": "edge-case",
                "simulation_success": True
            }) + '\n')

        fuzzer = LLMFuzzer(
            history_path=str(self.history_path),
            output_dir=str(self.output_dir),
            max_iterations=1
        )

        fuzzer.run(resume=True)

    def test_run_force_removes_existing_history(self):
        """Test force starts from a clean history file."""
        with open(self.history_path, 'w') as f:
            f.write(json.dumps({"iteration": 0, "reward": 1.5}) + '\n')

        fuzzer = LLMFuzzer(
            history_path=str(self.history_path),
            output_dir=str(self.output_dir),
            max_iterations=0
        )

        fuzzer.run(force=True)
        self.assertFalse(self.history_path.exists())
    
    def test_save_iteration(self):
        """Test saving iteration data."""
        fuzzer = LLMFuzzer(
            history_path=str(self.history_path),
            output_dir=str(self.output_dir)
        )
        
        iteration_data = {
            "iteration": 0,
            "reward": 1.5,
            "target_vl": 1001,
            "bugs_found": False
        }
        
        fuzzer.save_iteration(iteration_data)
        
        # Verify file exists and contains data
        self.assertTrue(self.history_path.exists())
        
        with open(self.history_path, 'r') as f:
            loaded = json.loads(f.read())
        
        self.assertEqual(loaded['iteration'], 0)
        self.assertEqual(loaded['reward'], 1.5)
    
    def test_should_stop_max_iterations(self):
        """Test stopping condition: max iterations."""
        fuzzer = LLMFuzzer(
            history_path=str(self.history_path),
            output_dir=str(self.output_dir),
            max_iterations=50
        )
        
        history = pd.DataFrame()
        
        self.assertFalse(fuzzer.should_stop(45, history, 0))
        self.assertTrue(fuzzer.should_stop(50, history, 0))
    
    def test_should_stop_consecutive_failures(self):
        """Test stopping condition: consecutive failures."""
        fuzzer = LLMFuzzer(
            history_path=str(self.history_path),
            output_dir=str(self.output_dir),
            max_iterations=50
        )
        
        history = pd.DataFrame()
        
        self.assertFalse(fuzzer.should_stop(10, history, 3))
        self.assertTrue(fuzzer.should_stop(10, history, 5))
    
    def test_generate_report_empty_history(self):
        """Test report generation with empty history."""
        fuzzer = LLMFuzzer(
            history_path=str(self.history_path),
            output_dir=str(self.output_dir)
        )
        
        history = pd.DataFrame()
        report = fuzzer.generate_report(history)
        
        self.assertIn("FINAL REPORT", report)
        self.assertIn("No iterations completed", report)
    
    def test_generate_report_with_data(self):
        """Test report generation with data."""
        fuzzer = LLMFuzzer(
            history_path=str(self.history_path),
            output_dir=str(self.output_dir)
        )
        
        history = pd.DataFrame([
            {
                'iteration': 0,
                'target_vl': 1001,
                'protocol_rule': 'bag',
                'reward': 1.5,
                'bugs_found': False,
                'strategy': 'edge-case',
                'test_mode': 'predefined',
                'simulation_success': True
            },
            {
                'iteration': 1,
                'target_vl': 1002,
                'protocol_rule': 'sequence_numbers',
                'reward': 1.2,
                'bugs_found': True,
                'strategy': 'adversarial',
                'test_mode': 'custom',
                'simulation_success': True
            }
        ])
        
        report = fuzzer.generate_report(history)
        
        self.assertIn("Total Iterations: 2", report)
        self.assertIn("Successful: 2", report)
        self.assertIn("Bugs Found: 1", report)
        self.assertIn("VLs Tested: 2", report)
        self.assertIn("Protocol Rules Tested: 2", report)

    def test_generate_report_calls_out_fuzzer_errors(self):
        """Test report surfaces code-level iteration errors."""
        fuzzer = LLMFuzzer(
            history_path=str(self.history_path),
            output_dir=str(self.output_dir)
        )

        history = pd.DataFrame([
            {
                'iteration': 0,
                'target_vl': 1001,
                'protocol_rule': 'bag',
                'reward': 1.5,
                'bugs_found': False,
                'strategy': 'edge-case',
                'simulation_success': True
            },
            {
                'iteration': 1,
                'target_vl': -1,
                'protocol_rule': 'unknown',
                'reward': 0.0,
                'bugs_found': False,
                'strategy': 'unknown',
                'simulation_success': False,
                'error': "missing required field 'mutation_type'",
                'error_type': 'KeyError',
                'failure_kind': 'fuzzer_error'
            }
        ])

        report = fuzzer.generate_report(history)

        self.assertIn("Fuzzer Code Errors:", report)
        self.assertIn("Iterations with exceptions: 1", report)
        self.assertIn("KeyError: 1", report)
        self.assertIn("Iter 1: KeyError: missing required field", report)
    
    def test_run_iteration_with_mocks(self):
        """Test single iteration with mocked components."""
        fuzzer = LLMFuzzer(
            history_path=str(self.history_path),
            output_dir=str(self.output_dir)
        )
        
        # Mock strategy planner
        mock_strategy = {
            'target_vl': 1001,
            'protocol_rule': 'bag',
            'test_mode': 'predefined',
            'test_cases': ['TC0'],
            'strategy': 'edge-case',
            'reasoning': 'Test reasoning'
        }
        fuzzer.strategy_planner.plan_next_iteration = Mock(return_value=mock_strategy)
        
        # Mock test generator
        mock_test_inputs = {
            'vl_id': 1001,
            'frames': [],
            'metadata': {'num_frames': 20}
        }
        fuzzer.test_generator.generate_test_inputs = Mock(return_value=mock_test_inputs)
        fuzzer.test_generator.save_to_file = Mock()
        
        # Mock simulator runner
        mock_sim_result = {
            'success': True,
            'log_content': 'frames received: 20\nframes dropped (policing): 5\nframes forwarded: 15',
            'duration': 1.0,
            'error': None
        }
        fuzzer.simulator_runner.run_simulation = Mock(return_value=mock_sim_result)
        
        # Mock feedback analyzer
        mock_feedback = {
            'success': True,
            'metrics': {
                'frames_received': 20,
                'frames_dropped_policing': 5,
                'frames_forwarded': 15,
                'policing_rate': 25.0,
                'forward_rate': 75.0
            },
            'reward': 1.5,
            'reward_components': {},
            'reward_breakdown': 'Test breakdown',
            'analysis': {
                'bugs_found': False,
                'recommendation': 'Continue testing'
            }
        }
        fuzzer.feedback_analyzer.analyze = Mock(return_value=mock_feedback)
        
        # Run iteration
        history = pd.DataFrame()
        result = fuzzer.run_iteration(0, history)
        
        # Verify result
        self.assertEqual(result['iteration'], 0)
        self.assertEqual(result['target_vl'], 1001)
        self.assertEqual(result['reward'], 1.5)
        self.assertEqual(result['simulation_success'], True)
        self.assertEqual(result['bugs_found'], False)
        
        # Verify mocks were called
        fuzzer.strategy_planner.plan_next_iteration.assert_called_once()
        fuzzer.test_generator.generate_test_inputs.assert_called_once()
        fuzzer.simulator_runner.run_simulation.assert_called_once()
        fuzzer.feedback_analyzer.analyze.assert_called_once()


if __name__ == "__main__":
    unittest.main()

