#!/usr/bin/env python3
"""
Unit tests for Component 2: LLM-Based Strategy Planner

Tests for:
- Prompt building (fuzzing_agent.py)
- Strategy planning (strategy_planner.py)
- LLM response parsing and validation

Run with: python3 llm_fuzzer/tests/test_component2.py
Or: python3 -m pytest llm_fuzzer/tests/test_component2.py -v
"""

import sys
import unittest
import json
import pandas as pd
from pathlib import Path
from unittest.mock import Mock, patch

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from llm_fuzzer.prompts.fuzzing_agent import (
    build_fuzzing_prompt,
    format_vl_statistics,
    _build_role_definition,
    _build_output_format
)
from llm_fuzzer.core.strategy_planner import LLMStrategyPlanner


class TestPromptBuilder(unittest.TestCase):
    """Test cases for fuzzing_agent.py prompt building"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.spec_rules = {
            "bag": {"allowed_values_ms": [1, 2, 4, 8, 16, 32, 64, 128]},
            "frame_structure.ethernet": {"lmin": 64, "lmax": 1518}
        }
        
        self.test_cases = {
            "bag": {
                "test_cases": [
                    {"value": 0, "violation_type": "below_min", "reason": "test"},
                    {"value": 3, "violation_type": "not_in_list", "reason": "test"}
                ]
            }
        }
        
        self.recent_results = [
            {"iteration": 1, "target_vl": 2001, "protocol_rule": "bag", 
             "strategy": "edge-case", "reward": 0.85, "bugs_found": False}
        ]
        
        self.vl_statistics = {
            2001: {"times_tested": 1, "avg_reward": 0.85, "max_reward": 0.85, "bugs_found": 0}
        }
        
        self.system_config = {"available_vls": [2001, 2002, 3001]}
    
    def test_prompt_includes_protocol_rules(self):
        """Test that prompt contains protocol rules"""
        prompt = build_fuzzing_prompt(
            self.spec_rules, self.test_cases, self.recent_results,
            self.vl_statistics, self.system_config, iteration=1
        )
        
        self.assertIn("PROTOCOL RULES", prompt)
        self.assertIn("bag", prompt)
        self.assertIn("allowed_values_ms", prompt)
    
    def test_prompt_includes_test_cases(self):
        """Test that prompt contains test cases"""
        prompt = build_fuzzing_prompt(
            self.spec_rules, self.test_cases, self.recent_results,
            self.vl_statistics, self.system_config, iteration=1
        )
        
        self.assertIn("TEST CASES", prompt)
        self.assertIn("below_min", prompt)
        self.assertIn("propose your own", prompt.lower())  # Freedom to customize
    
    def test_prompt_includes_recent_results(self):
        """Test that prompt includes recent performance"""
        prompt = build_fuzzing_prompt(
            self.spec_rules, self.test_cases, self.recent_results,
            self.vl_statistics, self.system_config, iteration=2
        )
        
        self.assertIn("RECENT PERFORMANCE", prompt)
        self.assertIn("Iter 1", prompt)
        self.assertIn("VL=2001", prompt)
    
    def test_prompt_includes_vl_statistics(self):
        """Test that prompt includes VL statistics"""
        prompt = build_fuzzing_prompt(
            self.spec_rules, self.test_cases, self.recent_results,
            self.vl_statistics, self.system_config, iteration=2
        )
        
        self.assertIn("VIRTUAL LINK (VL) CONFIGURATION & STATISTICS", prompt)
        self.assertIn("VL 2001", prompt)
        self.assertIn("tested 1 times", prompt)
    
    def test_prompt_has_output_format(self):
        """Test that prompt specifies JSON output format"""
        prompt = build_fuzzing_prompt(
            self.spec_rules, self.test_cases, self.recent_results,
            self.vl_statistics, self.system_config, iteration=1
        )
        
        self.assertIn("OUTPUT FORMAT", prompt)
        self.assertIn("JSON", prompt)
        self.assertIn("target_vl", prompt)
        self.assertIn("mutation_type", prompt)
    
    def test_prompt_has_decision_guidelines(self):
        """Test that prompt includes decision guidelines"""
        prompt = build_fuzzing_prompt(
            self.spec_rules, self.test_cases, self.recent_results,
            self.vl_statistics, self.system_config, iteration=1
        )
        
        self.assertIn("DECISION GUIDELINES", prompt)
        self.assertIn("EXPLORATION", prompt.upper())
        self.assertIn("EXPLOITATION", prompt.upper())
    
    def test_prompt_length_reasonable(self):
        """Test that prompt is not too long"""
        prompt = build_fuzzing_prompt(
            self.spec_rules, self.test_cases, self.recent_results,
            self.vl_statistics, self.system_config, iteration=1
        )
        
        # Prompt should stay within a reasonable LLM context budget.
        self.assertLess(len(prompt), 15000)
        # But should have substantial content
        self.assertGreater(len(prompt), 1000)
    
    def test_format_vl_statistics(self):
        """Test VL statistics calculation from history"""
        history = pd.DataFrame({
            "target_vl": [2001, 2001, 3001, 2001],
            "reward": [0.8, 0.9, 0.5, 0.7],
            "bugs_found": [False, False, False, True]
        })
        
        stats = format_vl_statistics(history)
        
        self.assertIn(2001, stats)
        self.assertEqual(stats[2001]["times_tested"], 3)
        self.assertAlmostEqual(stats[2001]["avg_reward"], 0.8, places=1)
        self.assertEqual(stats[2001]["bugs_found"], 1)


class TestStrategyPlanner(unittest.TestCase):
    """Test cases for strategy_planner.py"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.mock_strategy_predefined = {
            "target_vl": 2001,
            "mutation_type": "bag",
            "protocol_rule": "bag",
            "test_mode": "predefined",
            "test_cases": ["TC0", "TC1"],
            "custom_mutation": None,
            "strategy": "edge-case",
            "reasoning": "Testing VL 2001 with BAG violations"
        }
        
        self.mock_strategy_custom = {
            "target_vl": 9999,
            "mutation_type": "virtual_link",
            "protocol_rule": "virtual_link",
            "test_mode": "custom",
            "test_cases": None,
            "custom_mutation": "Use invalid VL ID 9999 to test validation",
            "strategy": "adversarial",
            "reasoning": "Testing with completely invalid VL"
        }
    
    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    def test_initialization(self):
        """Test planner initializes correctly"""
        planner = LLMStrategyPlanner(api_key="test-key")
        
        self.assertEqual(planner.model, "gpt-5")
        self.assertIsNotNone(planner.spec_rules)
        self.assertIsNotNone(planner.test_cases)
    
    def test_initialization_without_api_key(self):
        """Test that initialization fails without API key"""
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaises(ValueError):
                LLMStrategyPlanner(api_key=None)
    
    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    def test_parse_strategy_predefined(self):
        """Test parsing valid predefined strategy"""
        planner = LLMStrategyPlanner(api_key="test-key")
        
        response = json.dumps(self.mock_strategy_predefined)
        strategy = planner._parse_strategy(response)
        
        self.assertEqual(strategy["target_vl"], 2001)
        self.assertEqual(strategy["test_mode"], "predefined")
        self.assertIsNotNone(strategy["test_cases"])
        self.assertIsNone(strategy["custom_mutation"])
    
    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    def test_parse_strategy_custom(self):
        """Test parsing valid custom strategy"""
        planner = LLMStrategyPlanner(api_key="test-key")
        
        response = json.dumps(self.mock_strategy_custom)
        strategy = planner._parse_strategy(response)
        
        self.assertEqual(strategy["target_vl"], 9999)
        self.assertEqual(strategy["test_mode"], "custom")
        self.assertIsNone(strategy["test_cases"])
        self.assertIsNotNone(strategy["custom_mutation"])
    
    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    def test_parse_strategy_invalid_json(self):
        """Test handling of invalid JSON"""
        planner = LLMStrategyPlanner(api_key="test-key")
        
        with self.assertRaises(ValueError):
            planner._parse_strategy("not valid json")
    
    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    def test_parse_strategy_missing_fields(self):
        """Test handling of missing required fields"""
        planner = LLMStrategyPlanner(api_key="test-key")
        
        incomplete = {"target_vl": 2001}  # Missing other required fields
        with self.assertRaises(ValueError):
            planner._parse_strategy(json.dumps(incomplete))
    
    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    def test_validate_strategy(self):
        """Test strategy validation"""
        planner = LLMStrategyPlanner(api_key="test-key")
        
        # Valid strategy should not raise
        planner._validate_strategy(self.mock_strategy_predefined)
        
        # Invalid strategy type should raise (must be conformance/edge-case/adversarial)
        invalid = self.mock_strategy_predefined.copy()
        invalid["strategy"] = "invalid_type"
        with self.assertRaises(ValueError):
            planner._validate_strategy(invalid)
    
    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    def test_prepare_recent_results(self):
        """Test preparation of recent results"""
        planner = LLMStrategyPlanner(api_key="test-key")
        
        history = pd.DataFrame({
            "iteration": [1, 2, 3],
            "target_vl": [2001, 2002, 3001],
            "protocol_rule": ["bag", "frame_size", "virtual_link"],
            "strategy": ["edge-case", "normal", "attack"],
            "reward": [0.8, 0.5, 0.9],
            "bugs_found": [False, False, True]
        })
        
        results = planner._prepare_recent_results(history, n=2)
        
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["iteration"], 2)
        self.assertEqual(results[1]["iteration"], 3)
    
    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    @patch('llm_fuzzer.core.strategy_planner.OpenAI')
    def test_plan_with_mock_llm(self, mock_openai_class):
        """Test complete planning with mocked LLM"""
        # Setup mock
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = json.dumps(self.mock_strategy_predefined)
        mock_client.chat.completions.create.return_value = mock_response
        
        # Create planner
        planner = LLMStrategyPlanner(api_key="test-key")
        planner.client = mock_client  # Use mocked client
        expected_rule = planner._normalize_to_known_rule("bag")
        
        # Plan iteration
        strategy = planner.plan_next_iteration(history=None, iteration=1)
        
        # Verify
        self.assertEqual(strategy["target_vl"], 2001)
        self.assertEqual(strategy["protocol_rule"], expected_rule)
        self.assertIn("llm_raw_response", strategy)

    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    def test_redirect_clears_stale_mutation_fields(self):
        """Redirected strategies should not retain abandoned mutation params."""
        planner = LLMStrategyPlanner(api_key="test-key")
        planner._query_llm = Mock(return_value=json.dumps({
            "target_vl": 2001,
            "mutation_type": "bag timing violation",
            "test_cases": ["TC1"],
            "bag_value": 0,
            "frame_size": None,
            "sequence_number": None,
            "timing_jitter_ms": None,
            "payload_pattern": None,
            "mac_mutation_type": None,
            "prob": None,
            "sequence_number_override": None,
            "dest_mac_mutation": None,
            "strategy": "edge-case",
            "reasoning": "Test BAG timing boundary behavior."
        }))
        planner._normalize_to_known_rule = Mock(return_value="bag")
        planner._pick_untested_rule_from_category = Mock(return_value="mac_address")

        history = pd.DataFrame([{
            "target_vl": 2001,
            "protocol_rule": "bag",
            "mutation_type": "bag",
            "simulation_success": True,
        }])

        strategy = planner.plan_next_iteration(
            history=history,
            iteration=2,
            system_config={"available_vls": [2001]}
        )

        self.assertEqual(strategy["protocol_rule"], "mac_address")
        self.assertEqual(strategy["mutation_type"], "mac_address")
        self.assertEqual(strategy["redirected_from_rule"], "bag")
        self.assertIsNone(strategy["bag_value"])
        self.assertIsNone(strategy["frame_size"])
        self.assertEqual(strategy["test_cases"], ["TC0"])
        self.assertFalse(strategy["compound_test"])
        self.assertEqual(strategy["planner_actions"][0]["type"], "redirect")

    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    def test_scheduled_mechanism_is_standalone(self):
        """Scheduled mechanism coverage should replace, not stack onto, LLM choice."""
        planner = LLMStrategyPlanner(api_key="test-key")
        planner._query_llm = Mock(return_value=json.dumps({
            "target_vl": 1002,
            "mutation_type": "sequence_numbers",
            "test_cases": ["TC0"],
            "bag_value": 0,
            "frame_size": None,
            "sequence_number": None,
            "timing_jitter_ms": None,
            "payload_pattern": None,
            "mac_mutation_type": None,
            "prob": None,
            "sequence_number_override": None,
            "dest_mac_mutation": None,
            "strategy": "edge-case",
            "reasoning": "Test sequence number behavior."
        }))

        strategy = planner.plan_next_iteration(
            history=pd.DataFrame(),
            iteration=21,
            system_config={"available_vls": [1002]}
        )

        self.assertEqual(strategy["protocol_rule"], "mac_address")
        self.assertEqual(strategy["primary_rule"], "mac_address")
        self.assertEqual(strategy["mac_mutation_type"], "spoof_src")
        self.assertEqual(strategy["prob"], 1.0)
        self.assertIsNone(strategy["test_cases"])
        self.assertIsNone(strategy["bag_value"])
        self.assertFalse(strategy["compound_test"])
        self.assertEqual(strategy["injected_mechanism"], "mac_mutation_type:spoof_src")
        self.assertEqual(strategy["planner_actions"][0]["type"], "scheduled_standalone")

    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    def test_llm_selected_compound_strategy_is_marked(self):
        """Intentional LLM compound strategies should be recorded explicitly."""
        planner = LLMStrategyPlanner(api_key="test-key")
        planner._query_llm = Mock(return_value=json.dumps({
            "target_vl": 1002,
            "mutation_type": "frame_structure.ethernet",
            "test_cases": ["TC0"],
            "bag_value": None,
            "frame_size": 2000,
            "sequence_number": None,
            "timing_jitter_ms": None,
            "payload_pattern": None,
            "mac_mutation_type": None,
            "prob": None,
            "sequence_number_override": None,
            "dest_mac_mutation": None,
            "strategy": "adversarial",
            "reasoning": "Use a frame test case and an oversized direct value."
        }))

        strategy = planner.plan_next_iteration(
            history=pd.DataFrame(),
            iteration=3,
            system_config={"available_vls": [1002]}
        )

        self.assertTrue(strategy["compound_test"])
        self.assertEqual(strategy["planner_actions"], [])
        self.assertEqual(strategy["frame_size"], 2000)
        self.assertEqual(strategy["test_cases"], ["TC0"])

    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    def test_dedup_allows_same_rule_on_different_vl(self):
        """Testing a rule on one VL should not redirect the same rule on another VL."""
        planner = LLMStrategyPlanner(api_key="test-key")
        planner._query_llm = Mock(return_value=json.dumps({
            "target_vl": 3001,
            "mutation_type": "bag",
            "test_cases": ["TC0"],
            "bag_value": None,
            "frame_size": None,
            "sequence_number": None,
            "timing_jitter_ms": None,
            "payload_pattern": None,
            "mac_mutation_type": None,
            "prob": None,
            "sequence_number_override": None,
            "dest_mac_mutation": None,
            "strategy": "edge-case",
            "reasoning": "Test BAG on a different VL."
        }))
        expected_rule = planner._normalize_to_known_rule("bag")

        history = pd.DataFrame([{
            "target_vl": 1001,
            "protocol_rule": expected_rule,
            "mutation_type": expected_rule,
            "simulation_success": True,
        }])

        strategy = planner.plan_next_iteration(
            history=history,
            iteration=2,
            system_config={"available_vls": [1001, 3001]}
        )

        self.assertEqual(strategy["target_vl"], 3001)
        self.assertEqual(strategy["protocol_rule"], expected_rule)
        self.assertNotIn("redirected_from_rule", strategy)
        self.assertEqual(strategy["planner_actions"], [])


def run_tests():
    """Run all tests"""
    print("=" * 70)
    print("RUNNING COMPONENT 2 TESTS")
    print("=" * 70)
    
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestPromptBuilder))
    suite.addTests(loader.loadTestsFromTestCase(TestStrategyPlanner))
    
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

