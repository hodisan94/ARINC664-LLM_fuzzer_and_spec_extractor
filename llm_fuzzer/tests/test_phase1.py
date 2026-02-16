#!/usr/bin/env python3
"""
Unit tests for Phase 1: Data Loaders & Parsers

Run with: python3 -m pytest llm_fuzzer/tests/test_phase1.py -v
Or simply: python3 llm_fuzzer/tests/test_phase1.py
"""

import sys
import unittest
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from llm_fuzzer.utils.spec_loader import SpecificationLoader
from llm_fuzzer.utils.test_case_loader import TestCaseLoader
from llm_fuzzer.utils.log_parser import SimulatorLogParser


class TestSpecificationLoader(unittest.TestCase):
    """Test cases for SpecificationLoader"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures"""
        cls.spec_path = "configs/spec_rules.json"
        cls.loader = SpecificationLoader(cls.spec_path)
    
    def test_loader_initialization(self):
        """Test that loader initializes successfully"""
        self.assertIsNotNone(self.loader.spec_rules)
        self.assertIsInstance(self.loader.spec_rules, dict)
    
    def test_get_all_rules(self):
        """Test getting all rules"""
        rules = self.loader.get_all_rules()
        self.assertIsInstance(rules, dict)
        self.assertGreater(len(rules), 0)
    
    def test_get_specific_rule(self):
        """Test getting a specific rule (bag)"""
        bag_rule = self.loader.get_rule("bag")
        self.assertIsNotNone(bag_rule)
        self.assertIn("allowed_values_ms", bag_rule)
        self.assertEqual(bag_rule["allowed_values_ms"], [1, 2, 4, 8, 16, 32, 64, 128])
    
    def test_get_nested_rule(self):
        """Test getting nested rule (frame_structure.ethernet)"""
        frame_rule = self.loader.get_rule("frame_structure.ethernet")
        self.assertIsNotNone(frame_rule)
        self.assertEqual(frame_rule.get("lmin"), 64)
        self.assertEqual(frame_rule.get("lmax"), 1518)
    
    def test_get_rule_names(self):
        """Test getting all rule names"""
        names = self.loader.get_rule_names()
        self.assertIsInstance(names, list)
        self.assertIn("bag", names)
        self.assertGreaterEqual(len(names), 4)
    
    def test_search_rules(self):
        """Test searching for rules"""
        results = self.loader.search_rules("frame")
        self.assertIsInstance(results, dict)
        self.assertGreater(len(results), 0)
    
    def test_to_llm_format(self):
        """Test LLM format conversion"""
        llm_text = self.loader.to_llm_format()
        self.assertIsInstance(llm_text, str)
        self.assertIn("AVAILABLE PROTOCOL RULES", llm_text)
        self.assertIn("bag", llm_text)


class TestTestCaseLoader(unittest.TestCase):
    """Test cases for TestCaseLoader"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures"""
        cls.tc_path = "configs/test_cases.json"
        cls.loader = TestCaseLoader(cls.tc_path)
    
    def test_loader_initialization(self):
        """Test that loader initializes successfully"""
        self.assertIsNotNone(self.loader.test_cases)
        self.assertIsInstance(self.loader.test_cases, dict)
    
    def test_get_test_cases_for_rule(self):
        """Test getting test cases for 'bag' rule"""
        bag_tests = self.loader.get_test_cases_for_rule("bag")
        self.assertIsInstance(bag_tests, list)
        self.assertGreater(len(bag_tests), 0)
        
        # Check first test case structure
        first_tc = bag_tests[0]
        self.assertIn("value", first_tc)
        self.assertIn("violation_type", first_tc)
        self.assertIn("reason", first_tc)
    
    def test_get_test_case_by_index(self):
        """Test getting specific test case by index"""
        tc = self.loader.get_test_case_by_index("bag", 0)
        self.assertIsNotNone(tc)
        self.assertEqual(tc["value"], 0)  # First test case
    
    def test_get_random_test_case(self):
        """Test getting random test case"""
        tc = self.loader.get_random_test_case("bag")
        self.assertIsNotNone(tc)
        self.assertIn("value", tc)
    
    def test_get_rule_names(self):
        """Test getting rule names"""
        names = self.loader.get_rule_names()
        self.assertIsInstance(names, list)
        self.assertIn("bag", names)
    
    def test_get_test_case_count(self):
        """Test counting test cases"""
        count = self.loader.get_test_case_count("bag")
        self.assertGreater(count, 0)
    
    def test_get_violation_types(self):
        """Test getting violation types"""
        violations = self.loader.get_violation_types("bag")
        self.assertIsInstance(violations, list)
        self.assertIn("below_min", violations)
    
    def test_to_llm_format(self):
        """Test LLM format conversion"""
        llm_text = self.loader.to_llm_format(max_cases_per_rule=3)
        self.assertIsInstance(llm_text, str)
        self.assertIn("AVAILABLE TEST CASES", llm_text)


class TestSimulatorLogParser(unittest.TestCase):
    """Test cases for SimulatorLogParser"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.mock_log_success = """
        [INFO] Starting AFDX simulation...
        [INFO] Frames received: 1000
        [INFO] Frames forwarded: 850
        [INFO] Frames dropped (policing): 100
        [INFO] Frames dropped (invalid VL): 50
        [INFO] Frames dropped: 150
        [INFO] Malformed frames accepted: 0
        [INFO] Simulation time: 10.5s
        """
        
        self.mock_log_with_bugs = """
        [INFO] Frames received: 500
        [INFO] Frames forwarded: 400
        [INFO] Frames dropped (policing): 50
        [INFO] Malformed frames accepted: 10
        [INFO] Simulation time: 5.2s
        """
    
    def test_parse_success(self):
        """Test parsing a successful log"""
        parser = SimulatorLogParser(log_content=self.mock_log_success)
        metrics = parser.parse()
        
        self.assertEqual(metrics["frames_received"], 1000)
        self.assertEqual(metrics["frames_forwarded"], 850)
        self.assertEqual(metrics["frames_dropped_policing"], 100)
        self.assertEqual(metrics["malformed_accepted"], 0)
        self.assertAlmostEqual(metrics["simulation_time_sec"], 10.5)
        self.assertTrue(metrics["parsing_success"])
    
    def test_parse_with_bugs(self):
        """Test parsing a log with bugs"""
        parser = SimulatorLogParser(log_content=self.mock_log_with_bugs)
        metrics = parser.parse()
        
        self.assertEqual(metrics["malformed_accepted"], 10)
        self.assertTrue(parser.has_bugs())
    
    def test_derived_metrics(self):
        """Test derived metrics (rates)"""
        parser = SimulatorLogParser(log_content=self.mock_log_success)
        metrics = parser.parse()
        
        self.assertAlmostEqual(metrics["forward_rate"], 0.85)  # 850/1000
        self.assertAlmostEqual(metrics["drop_rate"], 0.15)     # 150/1000
        self.assertAlmostEqual(metrics["policing_rate"], 0.10) # 100/1000
    
    def test_get_metric(self):
        """Test getting individual metrics"""
        parser = SimulatorLogParser(log_content=self.mock_log_success)
        
        self.assertEqual(parser.get_metric("frames_received"), 1000)
        self.assertEqual(parser.get_metric("nonexistent_metric", default=42), 42)
    
    def test_summary(self):
        """Test summary generation"""
        parser = SimulatorLogParser(log_content=self.mock_log_success)
        summary = parser.summary()
        
        self.assertIsInstance(summary, str)
        self.assertIn("SIMULATOR METRICS", summary)
        self.assertIn("1000", summary)  # frames received


def run_tests():
    """Run all tests"""
    print("=" * 70)
    print("RUNNING PHASE 1 TESTS")
    print("=" * 70)
    
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestSpecificationLoader))
    suite.addTests(loader.loadTestsFromTestCase(TestTestCaseLoader))
    suite.addTests(loader.loadTestsFromTestCase(TestSimulatorLogParser))
    
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

