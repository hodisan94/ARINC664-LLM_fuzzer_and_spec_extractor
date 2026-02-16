#!/usr/bin/env python3
"""
Phase 1 Components Demo

This script demonstrates how to use all Phase 1 components:
- SpecificationLoader: Load protocol rules
- TestCaseLoader: Load violation test cases  
- SimulatorLogParser: Parse simulator logs

Run from ns-3 root: python3 llm_fuzzer/demo.py
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from llm_fuzzer.utils.spec_loader import SpecificationLoader
from llm_fuzzer.utils.test_case_loader import TestCaseLoader
from llm_fuzzer.utils.log_parser import SimulatorLogParser


def demo_spec_loader():
    """Demonstrate SpecificationLoader usage"""
    print("=" * 70)
    print("1. SPECIFICATION LOADER DEMO")
    print("=" * 70)
    
    loader = SpecificationLoader("configs/spec_rules.json")
    
    print(f"\nLoaded {len(loader.get_rule_names())} protocol rules:")
    for rule_name in loader.get_rule_names():
        print(f"  - {rule_name}")
    
    print("\nBAG Rule Details:")
    bag_rule = loader.get_rule("bag")
    print(f"  Allowed values: {bag_rule['allowed_values_ms']}")
    print(f"  Constraints: {bag_rule['constraints'][:60]}...")
    
    print("\n")


def demo_test_case_loader():
    """Demonstrate TestCaseLoader usage"""
    print("=" * 70)
    print("2. TEST CASE LOADER DEMO")
    print("=" * 70)
    
    loader = TestCaseLoader("configs/test_cases.json")
    
    print(f"\nLoaded test cases for {len(loader.get_rule_names())} rules")
    
    # Show BAG test cases
    print(f"\nBAG Test Cases ({loader.get_test_case_count('bag')} total):")
    bag_tests = loader.get_test_cases_for_rule("bag")
    
    for idx, tc in enumerate(bag_tests[:3]):  # Show first 3
        print(f"\n  Test Case {idx}:")
        print(f"    Value: {tc['value']}")
        print(f"    Type: {tc['violation_type']}")
        print(f"    Reason: {tc['reason'][:50]}...")
        print(f"    Expected: {tc['expected_behavior'][:50]}...")
    
    print(f"\n  ... and {len(bag_tests) - 3} more test cases")
    print("\n")


def demo_log_parser():
    """Demonstrate SimulatorLogParser usage"""
    print("=" * 70)
    print("3. SIMULATOR LOG PARSER DEMO")
    print("=" * 70)
    
    # Mock log with good behavior
    mock_log_good = """
    [INFO] Starting AFDX simulation...
    [INFO] Frames received: 1000
    [INFO] Frames forwarded: 850
    [INFO] Frames dropped (policing): 100
    [INFO] Frames dropped (invalid VL): 50
    [INFO] Frames dropped: 150
    [INFO] Malformed frames accepted: 0
    [INFO] Simulation time: 10.5s
    """
    
    print("\nScenario 1: Good behavior (policing works correctly)")
    print("-" * 70)
    parser = SimulatorLogParser(log_content=mock_log_good)
    print(parser.summary())
    
    # Mock log with bugs
    mock_log_bug = """
    [INFO] Frames received: 500
    [INFO] Frames forwarded: 450
    [INFO] Frames dropped (policing): 10
    [INFO] Malformed frames accepted: 25
    [INFO] Simulation time: 5.2s
    """
    
    print("\nScenario 2: BUG DETECTED (malformed frames accepted!)")
    print("-" * 70)
    parser2 = SimulatorLogParser(log_content=mock_log_bug)
    print(parser2.summary())
    
    if parser2.has_bugs():
        print("\n🚨 BUG FOUND: The system accepted malformed frames!")
        print(f"   This is a critical violation of AFDX specification.")
    
    print("\n")


def demo_combined():
    """Demonstrate how components work together"""
    print("=" * 70)
    print("4. COMBINED USAGE DEMO")
    print("=" * 70)
    
    # Load data
    spec_loader = SpecificationLoader("configs/spec_rules.json")
    tc_loader = TestCaseLoader("configs/test_cases.json")
    
    # Simulate a fuzzing iteration
    print("\nSimulated Fuzzing Iteration:")
    print("-" * 70)
    
    # 1. Choose a rule to test
    rule_name = "bag"
    print(f"1. Selected rule: {rule_name}")
    
    # 2. Get available test cases
    test_cases = tc_loader.get_test_cases_for_rule(rule_name)
    print(f"2. Available test cases: {len(test_cases)}")
    
    # 3. Choose a test case (in real fuzzer, LLM decides this)
    chosen_tc = test_cases[0]
    print(f"3. Chosen test case: {chosen_tc['violation_type']}")
    print(f"   Value: {chosen_tc['value']}")
    print(f"   Reason: {chosen_tc['reason'][:50]}...")
    
    # 4. Simulate execution (mock log)
    print(f"4. Execute simulator with mutated frames...")
    mock_result = """
    [INFO] Frames received: 100
    [INFO] Frames dropped (policing): 100
    [INFO] Frames forwarded: 0
    [INFO] Malformed frames accepted: 0
    """
    
    # 5. Parse results
    parser = SimulatorLogParser(log_content=mock_result)
    metrics = parser.parse()
    
    print(f"5. Results:")
    print(f"   - Policing rate: {metrics['policing_rate']:.1%}")
    print(f"   - Forward rate: {metrics['forward_rate']:.1%}")
    print(f"   - Bugs found: {parser.has_bugs()}")
    
    print(f"\n✅ Success: System correctly rejected invalid BAG values!")
    print("\n")


def main():
    """Run all demos"""
    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 15 + "LLM-GUIDED FUZZER - PHASE 1 DEMO" + " " * 20 + "║")
    print("╚" + "═" * 68 + "╝")
    print("\n")
    
    demo_spec_loader()
    demo_test_case_loader()
    demo_log_parser()
    demo_combined()
    
    print("=" * 70)
    print("DEMO COMPLETED")
    print("=" * 70)
    print("\nAll Phase 1 components are working correctly!")
    print("Ready to proceed to Phase 2: Feedback Analyzer & Reward Calculator")
    print("\n")


if __name__ == "__main__":
    main()

