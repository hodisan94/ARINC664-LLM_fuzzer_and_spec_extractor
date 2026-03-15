#!/usr/bin/env python3
"""
boofuzz Strategy Generator - Deterministic Protocol Fuzzing

This module provides a strategy generator that iterates through ALL
test cases in a deterministic order. Unlike the LLM fuzzer (intelligent)
or random fuzzer (random), boofuzz goes through every violation systematically.

Key characteristics:
1. Deterministic: Same order every time
2. Exhaustive: Tests every violation in test_cases.json
3. No learning: Does not adapt based on results
4. Industry-standard approach: This is how traditional fuzzers work
"""

import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from boofuzz_baseline.afdx_protocol import AFDXTestCaseGenerator


class BoofuzzStrategyGenerator:
    """
    Deterministic strategy generator for boofuzz baseline.
    
    Unlike LLM (intelligent selection) or Random (random selection),
    boofuzz systematically tests every violation in order.
    
    This represents the "industry standard" approach where you:
    1. Define all test cases upfront
    2. Execute them in sequence
    3. Record results
    """
    
    def __init__(
        self,
        test_cases_path: str = "configs/test_cases.json",
        spec_rules_path: str = "configs/spec_rules_filtered.json"
    ):
        """
        Initialize boofuzz strategy generator.
        
        Args:
            test_cases_path: Path to test_cases.json
            spec_rules_path: Path to spec_rules.json
        """
        # Initialize AFDX test case generator
        self.afdx_generator = AFDXTestCaseGenerator(test_cases_path, spec_rules_path)
        
        # Get all violations in deterministic order
        self.all_violations = self.afdx_generator.get_all_violations()
        
        # Current position in the test sequence
        self.current_index = 0
        
        # Track what we've tested
        self.tested_violations = set()
    
    def plan_next_iteration(
        self,
        history: Optional[pd.DataFrame] = None,
        iteration: int = 0,
        system_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Plan next iteration - deterministically select next violation.
        
        Unlike LLM fuzzer, we ignore history and don't adapt.
        Unlike random fuzzer, we don't randomly select.
        We simply go to the next violation in sequence.
        
        Args:
            history: Previous results (IGNORED - no learning)
            iteration: Current iteration number
            system_config: System config with 'available_vls'
            
        Returns:
            Strategy dictionary compatible with TestGenerator
        """
        if not system_config or 'available_vls' not in system_config:
            raise ValueError("system_config must contain 'available_vls'")
        
        available_vls = system_config['available_vls']
        
        # Get next violation (wrap around if needed)
        if self.current_index >= len(self.all_violations):
            self.current_index = 0  # Start over
        
        violation = self.all_violations[self.current_index]
        self.current_index += 1
        
        # Mark as tested
        self.tested_violations.add(violation['id'])
        
        # Select VL (round-robin through available VLs)
        vl_index = (iteration) % len(available_vls)
        target_vl = available_vls[vl_index]
        
        # Map violation to strategy format (compatible with TestGenerator)
        rule_id = violation['rule_id']
        
        # Determine mutation type from rule_id
        if 'bag' in rule_id.lower():
            mutation_type = 'bag'
        elif 'sequence' in rule_id.lower():
            mutation_type = 'sequence_number'
        elif 'frame' in rule_id.lower() or 'ethernet' in rule_id.lower():
            mutation_type = 'frame_size'
        elif 'ip' in rule_id.lower():
            mutation_type = 'ip_header'
        elif 'virtual_link' in rule_id.lower():
            mutation_type = 'vl_id'
        elif 'priority' in rule_id.lower():
            mutation_type = 'priority'
        else:
            mutation_type = 'generic'
        
        # Extract value for direct application
        value = violation['value']
        bag_value = None
        frame_size = None
        sequence_number = None
        
        if mutation_type == 'bag' and isinstance(value, (int, float)):
            bag_value = int(value)
        elif mutation_type == 'frame_size' and isinstance(value, int):
            frame_size = value
        elif mutation_type == 'sequence_number' and isinstance(value, int):
            sequence_number = value
        
        # Create strategy (deterministic - no intelligence)
        strategy = {
            "target_vl": target_vl,
            "mutation_type": mutation_type,
            "protocol_rule": rule_id,
            "test_mode": "predefined",  # Always predefined for boofuzz
            "test_cases": [f"TC{self.current_index - 1}"],  # Reference to test case
            "custom_mutation": None,
            "strategy": "edge-case",  # boofuzz is always systematic
            "bag_value": bag_value,
            "frame_size": frame_size,
            "sequence_number": sequence_number,
            "reasoning": (
                f"boofuzz baseline: iteration {iteration}. "
                f"Systematically testing violation '{violation['id']}' "
                f"({violation['violation_type']}) on VL {target_vl}. "
                f"No learning or adaptation - exhaustive sequential testing."
            ),
            # Additional metadata for analysis
            "violation_id": violation['id'],
            "violation_type": violation['violation_type'],
            "expected_behavior": violation.get('expected_behavior', 'N/A')
        }
        
        return strategy
    
    def get_progress(self) -> Dict[str, Any]:
        """
        Get testing progress.
        
        Returns:
            Progress dictionary
        """
        total = len(self.all_violations)
        tested = len(self.tested_violations)
        
        return {
            'total_violations': total,
            'tested_violations': tested,
            'coverage_percent': (tested / total * 100) if total > 0 else 0,
            'remaining': total - tested,
            'current_index': self.current_index
        }
    
    def reset(self):
        """Reset to start testing from beginning."""
        self.current_index = 0
        self.tested_violations.clear()


if __name__ == "__main__":
    print("=" * 70)
    print("BOOFUZZ STRATEGY GENERATOR TEST")
    print("=" * 70)
    
    generator = BoofuzzStrategyGenerator()
    system_config = {'available_vls': [1001, 1002, 2001, 2002]}
    
    print(f"\nTotal violations to test: {len(generator.all_violations)}")
    print("\nGenerating first 5 strategies:")
    
    for i in range(5):
        strategy = generator.plan_next_iteration(
            history=None,
            iteration=i,
            system_config=system_config
        )
        
        print(f"\nIteration {i}:")
        print(f"  VL: {strategy['target_vl']}")
        print(f"  Rule: {strategy['protocol_rule']}")
        print(f"  Violation ID: {strategy['violation_id']}")
        print(f"  Violation Type: {strategy['violation_type']}")
        print(f"  BAG value: {strategy['bag_value']}")
    
    print("\n" + "-" * 70)
    progress = generator.get_progress()
    print(f"Progress: {progress['tested_violations']}/{progress['total_violations']} "
          f"({progress['coverage_percent']:.1f}%)")

