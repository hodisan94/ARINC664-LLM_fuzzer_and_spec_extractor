#!/usr/bin/env python3
"""
Unit tests for Component 1: Test Feedback Analyzer

Tests for:
- RewardCalculator
- FeedbackAnalyzer

Run with: python3 llm_fuzzer/tests/test_component1.py
Or: python3 -m pytest llm_fuzzer/tests/test_component1.py -v
"""

import sys
import unittest
import pandas as pd
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from llm_fuzzer.core.reward_calculator import RewardCalculator
from llm_fuzzer.core.feedback_analyzer import FeedbackAnalyzer
from llm_fuzzer.utils.log_parser import SimulatorLogParser


class TestRewardCalculator(unittest.TestCase):
    """Test cases for RewardCalculator"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.calculator = RewardCalculator()
    
    def test_initialization(self):
        """Test calculator initializes with correct defaults"""
        self.assertEqual(self.calculator.lambda_policing, 0.6)
        self.assertEqual(self.calculator.lambda_forward, 0.2)
        self.assertEqual(self.calculator.lambda_novelty, 0.4)
        self.assertEqual(self.calculator.lambda_repeat, 0.2)
    
    def test_policing_score(self):
        """Test policing score calculation"""
        metrics = {
            "frames_received": 1000,
            "frames_dropped_policing": 800
        }
        score = self.calculator._compute_policing_score(metrics)
        self.assertAlmostEqual(score, 0.8)
    
    def test_forward_score(self):
        """Test forward score calculation"""
        metrics = {
            "frames_received": 1000,
            "frames_forwarded": 200
        }
        score = self.calculator._compute_forward_score(metrics)
        self.assertAlmostEqual(score, 0.2)
    
    def test_novelty_score_first_test(self):
        """Test novelty score for first test (should be 1.0)"""
        strategy = {"target_vl": 2001, "protocol_rule": "bag"}
        score = self.calculator._compute_novelty_score(strategy, history=None)
        self.assertEqual(score, 1.0)
    
    def test_novelty_score_with_history(self):
        """Test novelty score with existing history"""
        strategy = {"target_vl": 2001, "protocol_rule": "bag"}
        
        # Create history with multiple tests of same VL
        history = pd.DataFrame({
            "target_vl": [2001, 2001, 2001, 1002],
            "protocol_rule": ["bag", "bag", "frame_size", "bag"]
        })
        
        score = self.calculator._compute_novelty_score(strategy, history)
        self.assertLess(score, 1.0)  # Should be less than 1 due to repetition
    
    def test_repeat_penalty_no_history(self):
        """Test repeat penalty with no history (should be 0)"""
        strategy = {"target_vl": 2001, "protocol_rule": "bag"}
        penalty = self.calculator._compute_repeat_penalty(strategy, history=None)
        self.assertEqual(penalty, 0.0)
    
    def test_repeat_penalty_with_recent_matches(self):
        """Test repeat penalty with recent matching tests"""
        strategy = {"target_vl": 2001, "protocol_rule": "bag"}
        
        # Recent history with matches
        history = pd.DataFrame({
            "target_vl": [2001, 2001, 1002, 2001],
            "protocol_rule": ["bag", "bag", "frame_size", "bag"]
        })
        
        penalty = self.calculator._compute_repeat_penalty(strategy, history)
        self.assertGreater(penalty, 0.0)  # Should have some penalty
    
    def test_edge_bonus_normal_strategy(self):
        """Test edge bonus for normal strategy"""
        strategy = {"strategy": "normal", "test_cases": []}
        metrics = {"frames_dropped_invalid_vl": 0}
        
        bonus = self.calculator._compute_edge_bonus(strategy, metrics)
        self.assertLess(bonus, 0.5)  # Should be low for normal strategy
    
    def test_edge_bonus_edge_case_strategy(self):
        """Test edge bonus for edge-case strategy"""
        strategy = {
            "strategy": "edge-case",
            "test_cases": ["tc1", "tc2"]
        }
        metrics = {"frames_dropped_invalid_vl": 10}
        
        bonus = self.calculator._compute_edge_bonus(strategy, metrics)
        self.assertGreater(bonus, 0.5)  # Should be higher for edge cases
    
    def test_safety_bonus_no_bugs(self):
        """Test safety bonus when no bugs found"""
        metrics = {
            "malformed_accepted": 0,
            "parsing_success": True
        }
        
        bonus = self.calculator._compute_safety_bonus(metrics)
        self.assertEqual(bonus, self.calculator.bonus_safety)
    
    def test_safety_bonus_with_bugs(self):
        """Test safety bonus when bugs found"""
        metrics = {
            "malformed_accepted": 10,
            "parsing_success": True
        }
        
        bonus = self.calculator._compute_safety_bonus(metrics)
        self.assertEqual(bonus, 0.0)  # No bonus if bugs found
    
    def test_calculate_complete_reward(self):
        """Test complete reward calculation"""
        metrics = {
            "frames_received": 1000,
            "frames_forwarded": 100,
            "frames_dropped_policing": 800,
            "frames_dropped_invalid_vl": 50,
            "malformed_accepted": 0,
            "parsing_success": True
        }
        
        strategy = {
            "target_vl": 2001,
            "protocol_rule": "bag",
            "test_cases": ["below_min"],
            "strategy": "edge-case"
        }
        
        result = self.calculator.calculate(metrics, strategy, history=None)
        
        # Verify structure
        self.assertIn("reward", result)
        self.assertIn("components", result)
        self.assertIn("breakdown", result)
        
        # Verify reward is reasonable
        self.assertIsInstance(result["reward"], float)
        self.assertGreater(result["reward"], 0)  # Should be positive for good test
        
        # Verify all components exist
        components = result["components"]
        self.assertIn("r_policing", components)
        self.assertIn("r_forward", components)
        self.assertIn("r_novelty", components)
        self.assertIn("r_repeat", components)
        self.assertIn("bonus_edge", components)
        self.assertIn("bonus_safety", components)


class TestFeedbackAnalyzer(unittest.TestCase):
    """Test cases for FeedbackAnalyzer"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.analyzer = FeedbackAnalyzer()
        
        self.mock_log_good = """
        [INFO] Frames received: 1000
        [INFO] Frames forwarded: 150
        [INFO] Frames dropped (policing): 800
        [INFO] Frames dropped (invalid VL): 50
        [INFO] Malformed frames accepted: 0
        [INFO] Simulation time: 10.5s
        """
        
        self.mock_log_bugs = """
        [INFO] Frames received: 500
        [INFO] Frames forwarded: 400
        [INFO] Frames dropped (policing): 50
        [INFO] Malformed frames accepted: 25
        [INFO] Simulation time: 5.2s
        """
        
        self.mock_strategy = {
            "target_vl": 2001,
            "protocol_rule": "bag",
            "test_cases": ["below_min", "negative"],
            "strategy": "edge-case"
        }
    
    def test_analyze_good_behavior(self):
        """Test analysis of good system behavior"""
        feedback = self.analyzer.analyze(
            log_content=self.mock_log_good,
            strategy=self.mock_strategy
        )
        
        # Verify success
        self.assertTrue(feedback["success"])
        
        # Verify metrics extracted
        self.assertIn("metrics", feedback)
        self.assertEqual(feedback["metrics"]["frames_received"], 1000)
        self.assertEqual(feedback["metrics"]["frames_dropped_policing"], 800)
        
        # Verify reward calculated
        self.assertIn("reward", feedback)
        self.assertIsInstance(feedback["reward"], float)
        
        # Verify analysis performed
        self.assertIn("analysis", feedback)
        self.assertFalse(feedback["analysis"]["bugs_found"])
    
    def test_analyze_with_bugs(self):
        """Test analysis when bugs are found"""
        feedback = self.analyzer.analyze(
            log_content=self.mock_log_bugs,
            strategy=self.mock_strategy
        )
        
        self.assertTrue(feedback["success"])
        self.assertTrue(feedback["analysis"]["bugs_found"])
        self.assertEqual(feedback["metrics"]["malformed_accepted"], 25)
    
    def test_analyze_missing_log(self):
        """Test analysis with missing log"""
        feedback = self.analyzer.analyze(strategy=self.mock_strategy)
        
        self.assertFalse(feedback["success"])
        self.assertIn("error", feedback)
    
    def test_summary_generation(self):
        """Test summary string generation"""
        feedback = self.analyzer.analyze(
            log_content=self.mock_log_good,
            strategy=self.mock_strategy
        )
        
        summary = self.analyzer.summary(feedback)
        
        self.assertIsInstance(summary, str)
        self.assertIn("FEEDBACK ANALYSIS", summary)
        self.assertIn("Frames received", summary)
        self.assertIn("Reward Score", summary)
    
    def test_policing_effectiveness_analysis(self):
        """Test policing effectiveness categorization"""
        # High policing rate
        feedback_high = self.analyzer.analyze(
            log_content=self.mock_log_good,
            strategy=self.mock_strategy
        )
        self.assertIn("Excellent", feedback_high["analysis"]["policing_effectiveness"])
        
        # Low policing rate
        feedback_low = self.analyzer.analyze(
            log_content=self.mock_log_bugs,
            strategy=self.mock_strategy
        )
        self.assertIn("Poor", feedback_low["analysis"]["policing_effectiveness"])
    
    def test_recommendation_generation(self):
        """Test recommendation generation"""
        # Test with bugs
        feedback_bugs = self.analyzer.analyze(
            log_content=self.mock_log_bugs,
            strategy=self.mock_strategy
        )
        self.assertIn("BUG", feedback_bugs["analysis"]["recommendation"])
        
        # Test without bugs
        feedback_good = self.analyzer.analyze(
            log_content=self.mock_log_good,
            strategy=self.mock_strategy
        )
        self.assertIsInstance(feedback_good["analysis"]["recommendation"], str)
    
    def test_batch_analysis(self):
        """Test batch analysis of multiple results"""
        results = [
            (self.mock_log_good, self.mock_strategy),
            (self.mock_log_bugs, self.mock_strategy)
        ]
        
        df = self.analyzer.analyze_batch(results)
        
        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(len(df), 2)
        self.assertIn("reward", df.columns)
        self.assertIn("bugs_found", df.columns)


def run_tests():
    """Run all tests"""
    print("=" * 70)
    print("RUNNING COMPONENT 1 TESTS")
    print("=" * 70)
    
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestRewardCalculator))
    suite.addTests(loader.loadTestsFromTestCase(TestFeedbackAnalyzer))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "=" * 70)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print("=" * 70)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)

