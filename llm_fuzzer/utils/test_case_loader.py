#!/usr/bin/env python3
"""
Test Case Loader

Loads and provides access to violation test cases from test_cases.json.
This module does NOT decide which test cases to use - it only provides
access to all available test cases for the LLM to choose from.
"""

import json
import random
from pathlib import Path
from typing import Dict, List, Any, Optional


class TestCaseLoader:
    """
    Loads AFDX test cases from JSON file.
    
    Provides access to test cases without imposing any selection logic.
    The LLM is free to choose any test case based on its strategy.
    """
    
    def __init__(self, test_cases_path: str):
        """
        Initialize the test case loader.
        
        Args:
            test_cases_path: Path to test_cases.json file
            
        Raises:
            FileNotFoundError: If test cases file doesn't exist
            json.JSONDecodeError: If file is invalid JSON
        """
        self.test_cases_path = Path(test_cases_path)
        
        if not self.test_cases_path.exists():
            raise FileNotFoundError(f"Test cases file not found: {test_cases_path}")
        
        with open(self.test_cases_path, 'r', encoding='utf-8') as f:
            self.test_cases = json.load(f)
        
        # Build index for quick lookups
        self._test_case_index = self._build_test_case_index()
    
    def _build_test_case_index(self) -> Dict[str, List[Dict]]:
        """
        Build an index mapping rule names to their test cases.
        
        Returns:
            Dictionary mapping rule_name -> list of test cases
        """
        index = {}
        
        for rule_name, rule_data in self.test_cases.items():
            if "test_cases" in rule_data:
                index[rule_name] = rule_data["test_cases"]
            else:
                # Sometimes the structure is different
                index[rule_name] = []
        
        return index
    
    def get_all_test_cases(self) -> Dict[str, Any]:
        """
        Get all test cases as a dictionary.
        
        Returns:
            Complete test cases dictionary
        """
        return self.test_cases
    
    def get_test_cases_for_rule(self, rule_name: str) -> List[Dict]:
        """
        Get all test cases for a specific rule.
        
        Args:
            rule_name: Name of the rule (e.g., "bag")
            
        Returns:
            List of test case dictionaries, or empty list if not found
        """
        return self._test_case_index.get(rule_name, [])
    
    def get_test_case_by_index(self, rule_name: str, index: int) -> Optional[Dict]:
        """
        Get a specific test case by rule name and index.
        
        Args:
            rule_name: Name of the rule
            index: Index of the test case (0-based)
            
        Returns:
            Test case dictionary, or None if not found
        """
        test_cases = self.get_test_cases_for_rule(rule_name)
        if 0 <= index < len(test_cases):
            return test_cases[index]
        return None
    
    def get_random_test_case(self, rule_name: str) -> Optional[Dict]:
        """
        Get a random test case for a rule.
        
        Note: This is provided as a utility, but the LLM should
        make its own informed choice rather than using random selection.
        
        Args:
            rule_name: Name of the rule
            
        Returns:
            Random test case dictionary, or None if no cases exist
        """
        test_cases = self.get_test_cases_for_rule(rule_name)
        return random.choice(test_cases) if test_cases else None
    
    def get_rule_names(self) -> List[str]:
        """
        Get list of all rules that have test cases.
        
        Returns:
            List of rule names
        """
        return sorted(self._test_case_index.keys())
    
    def get_test_case_count(self, rule_name: str) -> int:
        """
        Get the number of test cases for a rule.
        
        Args:
            rule_name: Name of the rule
            
        Returns:
            Number of test cases
        """
        return len(self.get_test_cases_for_rule(rule_name))
    
    def get_violation_types(self, rule_name: str) -> List[str]:
        """
        Get all violation types for a rule.
        
        Args:
            rule_name: Name of the rule
            
        Returns:
            List of unique violation types
        """
        test_cases = self.get_test_cases_for_rule(rule_name)
        return list(set(tc.get("violation_type", "unknown") for tc in test_cases))
    
    def to_llm_format(self, max_cases_per_rule: int = 7) -> str:
        """
        Convert test cases to LLM-friendly text format.
        
        This presents all available test cases without imposing choices.
        
        Args:
            max_cases_per_rule: Maximum test cases to show per rule
            
        Returns:
            Formatted string suitable for LLM prompts
        """
        lines = ["AVAILABLE TEST CASES:"]
        lines.append("=" * 70)
        
        for rule_name in sorted(self.get_rule_names()):
            test_cases = self.get_test_cases_for_rule(rule_name)
            
            lines.append(f"\n{rule_name}: ({len(test_cases)} test cases)")
            
            # Show first N test cases
            for idx, tc in enumerate(test_cases[:max_cases_per_rule]):
                lines.append(f"  TC{idx}: {tc.get('violation_type', 'unknown')}")
                lines.append(f"      value: {tc.get('value')}")
                lines.append(f"      reason: {tc.get('reason', 'N/A')[:80]}...")
            
            if len(test_cases) > max_cases_per_rule:
                lines.append(f"  ... and {len(test_cases) - max_cases_per_rule} more")
        
        lines.append("\n" + "=" * 70)
        return "\n".join(lines)


if __name__ == "__main__":
    # Quick test
    loader = TestCaseLoader("../../configs/test_cases.json")
    print(f"Loaded test cases for {len(loader.get_rule_names())} rules:")
    
    for rule_name in loader.get_rule_names()[:3]:
        count = loader.get_test_case_count(rule_name)
        print(f"  - {rule_name}: {count} test cases")

