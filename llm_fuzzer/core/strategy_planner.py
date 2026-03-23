#!/usr/bin/env python3
"""
LLM-Based Strategy Planner

This is Component 2 of the LLM-Guided Iterative Fuzzing Process.
It uses an LLM (GPT-5) to intelligently decide what to test next based on:
- Protocol rules and test cases
- Recent performance history
- VL statistics
- Reward scores

The LLM has freedom to choose predefined test cases OR propose custom mutations.
"""

import json
import os
import pandas as pd
from typing import Dict, List, Any, Optional
from pathlib import Path

# Import sibling modules
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from llm_fuzzer.utils.spec_loader import SpecificationLoader
from llm_fuzzer.utils.test_case_loader import TestCaseLoader
from llm_fuzzer.prompts.fuzzing_agent import build_fuzzing_prompt, format_vl_statistics

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class LLMStrategyPlanner:
    """
    Uses LLM to plan next fuzzing iteration.
    
    The LLM receives complete information about:
    - Available protocol rules
    - Test cases (with freedom to propose custom mutations)
    - Recent performance
    - VL testing statistics
    
    And decides:
    - Which VL to test
    - Which protocol rule to focus on
    - Whether to use predefined test cases or custom mutation
    - What strategy to use (conformance/edge-case/adversarial)
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-5",
        spec_rules_path: str = "configs/spec_rules.json",
        test_cases_path: str = "configs/test_cases.json"
    ):
        """
        Initialize LLM Strategy Planner.
        
        Args:
            api_key: OpenAI API key (reads from env if not provided)
            model: LLM model to use (default: gpt-5)
            spec_rules_path: Path to spec_rules.json
            test_cases_path: Path to test_cases.json
            
        Raises:
            ImportError: If openai package not installed
            ValueError: If API key not provided and not in environment
        """
        if not OPENAI_AVAILABLE:
            raise ImportError("openai package required. Install with: pip install openai")
        
        # Get API key
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key required. Set OPENAI_API_KEY env variable or pass api_key parameter.")
        
        self.model = model
        self.client = OpenAI(api_key=self.api_key)
        
        # Load spec rules and test cases
        self.spec_loader = SpecificationLoader(spec_rules_path)
        self.test_case_loader = TestCaseLoader(test_cases_path)
        
        self.spec_rules = self.spec_loader.get_all_rules()
        self.test_cases = self.test_case_loader.get_all_test_cases()
    
    def plan_next_iteration(
        self,
        history: Optional[pd.DataFrame] = None,
        iteration: int = 1,
        system_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Plan next fuzzing iteration using LLM.
        
        Args:
            history: DataFrame of previous iterations with columns:
                     iteration, target_vl, protocol_rule, reward, bugs_found, etc.
            iteration: Current iteration number
            system_config: System configuration (available VLs, etc.)
            
        Returns:
            Strategy dictionary (PAPER-ALIGNED FORMAT):
            {
                "target_vl": int,
                "mutation_type": str,
                "bag_value": int | None,
                "frame_size": int | None,
                "sequence_number": int | None,
                "timing_jitter_ms": int | None,
                "payload_pattern": str | None,
                "strategy": "conformance" | "edge-case" | "adversarial",
                "reasoning": str,
                "llm_raw_response": str
            }
        """
        vl_stats = format_vl_statistics(history) if history is not None else {}
        recent_results = self._prepare_recent_results(history, n=10)
        coverage_stats = self._compute_coverage_stats(history)
        
        if system_config is None:
            system_config = {
                "available_vls": [1001, 1002, 1003, 2001, 2002, 2003, 3001, 3002]
            }
        
        prompt = build_fuzzing_prompt(
            spec_rules=self.spec_rules,
            test_cases=self.test_cases,
            recent_results=recent_results,
            vl_statistics=vl_stats,
            system_config=system_config,
            iteration=iteration,
            coverage_stats=coverage_stats
        )
        
        llm_response = self._query_llm(prompt)
        strategy = self._parse_strategy(llm_response)
        strategy["llm_raw_response"] = llm_response
        self._validate_strategy(strategy, system_config)
        
        return strategy
    
    def _compute_coverage_stats(self, history: Optional[pd.DataFrame]) -> Dict[str, Any]:
        """
        Compute which rules have been covered vs uncovered.
        
        Uses the full spec_rules list as the universe, and checks which
        protocol_rule / mutation_type values appear in history.
        """
        all_rule_names = sorted(self.spec_rules.keys())
        all_tc_names = sorted(self.test_cases.keys())
        all_known = set(all_rule_names) | set(all_tc_names)
        
        if history is None or len(history) == 0:
            return {
                "covered_rules": [],
                "uncovered_rules": sorted(all_known),
                "mutation_type_counts": {},
                "total_rules": len(all_known),
            }
        
        seen_rules = set()
        mt_counts = {}
        
        if "protocol_rule" in history.columns:
            for val in history["protocol_rule"].dropna().unique():
                seen_rules.add(str(val))
        if "mutation_type" in history.columns:
            for val in history["mutation_type"].dropna().unique():
                seen_rules.add(str(val))
            for val in history["mutation_type"].dropna():
                mt_counts[str(val)] = mt_counts.get(str(val), 0) + 1
        
        covered = sorted(seen_rules & all_known)
        uncovered = sorted(all_known - seen_rules)
        
        return {
            "covered_rules": covered,
            "uncovered_rules": uncovered,
            "mutation_type_counts": mt_counts,
            "total_rules": len(all_known),
        }
    
    def _prepare_recent_results(
        self,
        history: Optional[pd.DataFrame],
        n: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Prepare recent iteration results for prompt.
        
        Args:
            history: DataFrame of previous iterations
            n: Number of recent iterations to include
            
        Returns:
            List of result dictionaries
        """
        if history is None or len(history) == 0:
            return []
        
        recent = history.tail(n)
        results = []
        
        for _, row in recent.iterrows():
            results.append({
                "iteration": int(row.get("iteration", 0)),
                "target_vl": int(row.get("target_vl", 0)),
                "protocol_rule": str(row.get("protocol_rule", "")),
                "strategy": str(row.get("strategy", "")),
                "reward": float(row.get("reward", 0.0)),
                "bugs_found": bool(row.get("bugs_found", False)),
                "recommendation": str(row.get("recommendation", ""))
            })
        
        return results
    
    def _query_llm(self, prompt: str) -> str:
        """
        Query LLM with prompt.
        
        Args:
            prompt: Complete fuzzing prompt
            
        Returns:
            LLM response text
            
        Raises:
            Exception: If LLM query fails
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert protocol fuzzing agent. Respond ONLY with valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                # temperature=0.7 removed - some models don't support non-default values
                max_completion_tokens=8000,   # Large limit for reasoning models (gpt-5 uses ~2000 reasoning + JSON)
                response_format={"type": "json_object"}  # Force JSON output
            )
            
            # Debug: print full response
            print(f"[DEBUG] Finish reason: {response.choices[0].finish_reason}")
            print(f"[DEBUG] Refusal: {response.choices[0].message.refusal}")
            
            content = response.choices[0].message.content
            
            print(f"[DEBUG] Content ({len(content) if content else 0} chars):")
            if content:
                print(content[:500])
            else:
                print("  EMPTY RESPONSE!")
                print(f"[DEBUG] Full response object: {response}")
            
            return content
            
        except Exception as e:
            raise Exception(f"LLM query failed: {str(e)}")
    
    def _parse_strategy(self, llm_response: str) -> Dict[str, Any]:
        """
        Parse LLM JSON response into strategy dictionary (HYBRID - FULL FREEDOM).
        
        LLM can choose:
        - test_cases (predefined)
        - specific mutation values
        - both combined
        
        Args:
            llm_response: Raw LLM response text
            
        Returns:
            Parsed strategy dictionary with all parameters
            
        Raises:
            ValueError: If response is not valid JSON or missing required fields
        """
        try:
            strategy = json.loads(llm_response)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM response is not valid JSON: {str(e)}")
        
        # Check required fields
        required_fields = ["target_vl", "mutation_type", "strategy", "reasoning"]
        missing = [f for f in required_fields if f not in strategy]
        if missing:
            raise ValueError(f"LLM response missing required fields: {missing}")
        
        # Ensure all parameter fields exist (can be null) - HYBRID SUPPORT
        all_params = ["test_cases", "bag_value", "frame_size", "sequence_number", 
                     "timing_jitter_ms", "payload_pattern", "mac_mutation_type", "prob",
                     "sequence_number_override", "dest_mac_mutation"]
        for param in all_params:
            if param not in strategy:
                strategy[param] = None
        
        return strategy
    
    def _validate_strategy(self, strategy: Dict[str, Any], system_config: Optional[Dict[str, Any]] = None) -> None:
        """
        Validate strategy components.
        
        Args:
            strategy: Parsed strategy dictionary
            system_config: System configuration with available_vls
            
        Raises:
            ValueError: If strategy contains invalid values
        """
        # Validate target_vl is an integer
        if not isinstance(strategy["target_vl"], int):
            raise ValueError(f"target_vl must be integer, got {type(strategy['target_vl'])}")
        
        # Validate target_vl exists in the simulator
        if system_config and 'available_vls' in system_config:
            valid_vls = system_config['available_vls']
            if strategy["target_vl"] not in valid_vls:
                import random
                corrected_vl = random.choice(valid_vls)
                print(f"  [WARN] LLM chose invalid VL {strategy['target_vl']}, correcting to {corrected_vl}")
                strategy["target_vl"] = corrected_vl
        
        # Validate strategy type
        valid_strategies = ["conformance", "edge-case", "adversarial"]
        if strategy["strategy"] not in valid_strategies:
            raise ValueError(f"strategy must be one of {valid_strategies}, got {strategy['strategy']}")
        
        # Validate mutation_type exists
        if not isinstance(strategy["mutation_type"], str) or not strategy["mutation_type"]:
            raise ValueError("mutation_type must be non-empty string")
        
        # Validate at least SOMETHING is set (test_cases OR mutation params)
        has_test_cases = strategy.get("test_cases") and len(strategy.get("test_cases", [])) > 0
        mutation_params = ["bag_value", "frame_size", "sequence_number", 
                          "timing_jitter_ms", "payload_pattern", "mac_mutation_type", "prob",
                          "sequence_number_override", "dest_mac_mutation"]
        has_mutation_params = any(strategy.get(p) is not None for p in mutation_params)
        
        if not has_test_cases and not has_mutation_params:
            raise ValueError("LLM must specify either test_cases OR mutation parameters (or both)")


if __name__ == "__main__":
    # Quick test (requires OPENAI_API_KEY in environment)
    print("=" * 70)
    print("STRATEGY PLANNER TEST")
    print("=" * 70)
    
    try:
        planner = LLMStrategyPlanner()
        print("✓ Planner initialized successfully")
        print(f"  Model: {planner.model}")
        print(f"  Protocol rules loaded: {len(planner.spec_rules)} rules")
        print(f"  Test cases loaded: {len(planner.test_cases)} rules")
        
        # Test with empty history (first iteration)
        print("\n→ Planning first iteration (no history)...")
        strategy = planner.plan_next_iteration(history=None, iteration=1)
        
        print("\n✓ Strategy received:")
        print(f"  Target VL: {strategy['target_vl']}")
        print(f"  Protocol Rule: {strategy['protocol_rule']}")
        print(f"  Test Mode: {strategy['test_mode']}")
        if strategy['test_mode'] == 'predefined':
            print(f"  Test Cases: {strategy['test_cases']}")
        else:
            print(f"  Custom Mutation: {strategy['custom_mutation']}")
        print(f"  Strategy: {strategy['strategy']}")
        print(f"  Reasoning: {strategy['reasoning']}")
        
    except ImportError as e:
        print(f"✗ Error: {e}")
        print("  Install openai package: pip install openai")
    except ValueError as e:
        print(f"✗ Error: {e}")
        print("  Set OPENAI_API_KEY environment variable")
    except Exception as e:
        print(f"✗ Error: {e}")

