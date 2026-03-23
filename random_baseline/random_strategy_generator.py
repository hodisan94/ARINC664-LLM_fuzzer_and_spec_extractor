#!/usr/bin/env python3
"""
Random Strategy Generator - Replaces LLM Strategy Planner with Pure Randomness

This module provides a drop-in replacement for LLMStrategyPlanner that makes
completely random decisions. It uses the same interface and returns the same
strategy format, but without any intelligence or learning.

Purpose: Fair baseline comparison for the LLM-guided fuzzer.
"""

import sys
import random
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from llm_fuzzer.utils.spec_loader import SpecificationLoader
from llm_fuzzer.utils.test_case_loader import TestCaseLoader


class RandomStrategyGenerator:
    """
    Random strategy generator - makes purely random decisions.
    
    This class mimics the LLMStrategyPlanner interface but makes random
    choices instead of using an LLM. It ensures fair comparison by:
    - Using the same data sources (spec_rules.json, test_cases.json)
    - Returning the same strategy format
    - Working with the same downstream components (TestGenerator, etc.)
    
    The only difference is: LLM intelligence → random selection
    """
    
    def __init__(
        self,
        spec_rules_path: str = "configs/spec_rules.json",
        test_cases_path: str = "configs/test_cases.json",
        seed: Optional[int] = None
    ):
        """
        Initialize Random Strategy Generator.
        
        Args:
            spec_rules_path: Path to spec_rules.json
            test_cases_path: Path to test_cases.json
            seed: Random seed for reproducibility (optional)
        """
        # Set random seed if provided
        if seed is not None:
            random.seed(seed)
        
        # Load spec rules and test cases (same as LLM fuzzer)
        self.spec_loader = SpecificationLoader(spec_rules_path)
        self.test_case_loader = TestCaseLoader(test_cases_path)
        
        self.spec_rules = self.spec_loader.get_all_rules()
        self.test_cases = self.test_case_loader.get_all_test_cases()
        
        # Get available options
        self.available_rules = list(self.test_cases.keys())  # Rules that have test cases
        self.strategy_types = ["conformance", "edge-case", "adversarial"]
        self.test_modes = ["predefined", "custom"]
    
    def plan_next_iteration(
        self,
        history: Optional[pd.DataFrame] = None,
        iteration: int = 0,
        system_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate a random strategy for the next iteration.
        
        This method makes completely random choices:
        - Random VL from available VLs
        - Random protocol rule
        - Random test mode (predefined/custom)
        - Random test cases or random custom mutation
        - Random strategy type
        
        Args:
            history: Previous iteration history (IGNORED - no learning!)
            iteration: Current iteration number (only for logging)
            system_config: System configuration (must contain 'available_vls')
            
        Returns:
            Strategy dictionary with same format as LLM planner:
            {
                "target_vl": int,
                "protocol_rule": str,
                "test_mode": "predefined" | "custom",
                "test_cases": List[str] | None,
                "custom_mutation": str | None,
                "strategy": "conformance" | "edge-case" | "adversarial",
                "reasoning": str
            }
        """
        if not system_config or 'available_vls' not in system_config:
            raise ValueError("system_config must contain 'available_vls'")
        
        available_vls = system_config['available_vls']
        
        # 1. Random VL
        target_vl = random.choice(available_vls)
        
        # 2. Random protocol rule
        protocol_rule = random.choice(self.available_rules)
        
        # 3. Random test mode
        test_mode = random.choice(self.test_modes)
        
        # 4. Random test cases or custom mutation
        test_cases = None
        custom_mutation = None
        strategy_extra = {}
        
        if test_mode == "predefined":
            # Get test cases for this rule
            rule_test_cases = self.test_case_loader.get_test_cases_for_rule(protocol_rule)
            if rule_test_cases:
                # Random number of test cases (1-3)
                num_cases = random.randint(1, min(3, len(rule_test_cases)))
                # Random selection — use original indices so TestGenerator picks the right cases
                selected_indices = random.sample(range(len(rule_test_cases)), num_cases)
                test_cases = [f"TC{i}" for i in selected_indices]
        else:
            # Custom mode: generate concrete mutation parameters that TestGenerator understands
            if 'bag' in protocol_rule.lower():
                strategy_extra['bag_value'] = random.choice([0, 1, 2, 3, 4, 16, 32, 64, 128])
            elif 'frame' in protocol_rule.lower() or 'ethernet' in protocol_rule.lower():
                strategy_extra['frame_size'] = random.choice([0, 17, 63, 65, 1518, 1519, 2000, 10000])
            elif 'sequence' in protocol_rule.lower():
                strategy_extra['sequence_number'] = random.choice([-1, 0, 256, 65535, 99999])
            elif 'mac' in protocol_rule.lower() or 'address' in protocol_rule.lower():
                strategy_extra['mac_mutation_type'] = random.choice(
                    ['spoof_src', 'spoof_dst', 'broadcast', 'invalid_src', 'zero_mac'])
            else:
                strategy_extra['bag_value'] = random.choice([0, 1, 2, 3])
                strategy_extra['frame_size'] = random.choice([0, 63, 1519, 5000])
        
        # Randomly add prob, mac_mutation_type, seq override, or dest MAC mutation (10% each)
        if random.random() < 0.10:
            strategy_extra['prob'] = random.choice([0.1, 0.3, 0.5, 0.7, 1.0])
        if random.random() < 0.10:
            strategy_extra['mac_mutation_type'] = random.choice(
                ['spoof_src', 'broadcast', 'zero_mac'])
        if random.random() < 0.10:
            strategy_extra['sequence_number_override'] = random.choice([0, 1, 127, 255])
        if random.random() < 0.10:
            strategy_extra['dest_mac_mutation'] = random.choice(
                ['corrupt_prefix', 'wrong_vl', 'zero'])
        
        # 5. Random strategy type
        strategy_type = random.choice(self.strategy_types)
        
        # 6. Generic reasoning (indicates randomness)
        reasoning = (
            f"Random baseline: iteration {iteration}. "
            f"Randomly selected VL {target_vl}, rule '{protocol_rule}', "
            f"mode '{test_mode}', strategy '{strategy_type}'. "
            f"No learning or adaptation - purely random exploration."
        )
        
        result = {
            "target_vl": target_vl,
            "mutation_type": protocol_rule,  # Use protocol_rule as mutation_type
            "protocol_rule": protocol_rule,  # Keep for compatibility
            "test_mode": test_mode,
            "test_cases": test_cases,
            "custom_mutation": custom_mutation,
            "strategy": strategy_type,
            "reasoning": reasoning
        }
        result.update(strategy_extra)
        return result


if __name__ == "__main__":
    # Quick test
    print("=" * 70)
    print("RANDOM STRATEGY GENERATOR TEST")
    print("=" * 70)
    print()
    
    generator = RandomStrategyGenerator(seed=42)
    
    system_config = {'available_vls': [1001, 1002, 2001, 2002]}
    
    print("Generating 5 random strategies:")
    print()
    
    for i in range(5):
        strategy = generator.plan_next_iteration(
            history=None,
            iteration=i,
            system_config=system_config
        )
        
        print(f"Iteration {i}:")
        print(f"  VL: {strategy['target_vl']}")
        print(f"  Rule: {strategy['protocol_rule']}")
        print(f"  Mode: {strategy['test_mode']}")
        print(f"  Strategy: {strategy['strategy']}")
        print(f"  Test cases: {strategy['test_cases']}")
        print(f"  Custom: {strategy['custom_mutation']}")
        print()

