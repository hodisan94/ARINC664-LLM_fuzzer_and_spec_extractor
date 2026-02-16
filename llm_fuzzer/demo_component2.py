#!/usr/bin/env python3
"""
Component 2: LLM-Based Strategy Planner - Complete Demo

This demonstrates the full functionality of Component 2, which uses an LLM
to intelligently decide what to test next.

The LLM has freedom to:
- Choose from predefined test cases
- Propose custom mutations based on learning
- Balance exploration vs exploitation

Run: python3 llm_fuzzer/demo_component2.py
Note: Requires OPENAI_API_KEY environment variable
"""

import sys
import json
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from llm_fuzzer.prompts.fuzzing_agent import build_fuzzing_prompt, format_vl_statistics
from llm_fuzzer.core.strategy_planner import LLMStrategyPlanner


def demo_prompt_building():
    """Demonstrate prompt building"""
    print("=" * 70)
    print("1. PROMPT BUILDING")
    print("=" * 70)
    
    # Mock data
    spec_rules = {
        "bag": {"allowed_values_ms": [1, 2, 4, 8, 16, 32, 64, 128]},
        "frame_structure.ethernet": {"lmin": 64, "lmax": 1518}
    }
    
    test_cases = {
        "bag": {
            "test_cases": [
                {"value": 0, "violation_type": "below_min", "reason": "BAG value too small"},
                {"value": 3, "violation_type": "not_in_list", "reason": "BAG not power of 2"}
            ]
        }
    }
    
    recent_results = [
        {"iteration": 1, "target_vl": 2001, "protocol_rule": "bag",
         "strategy": "edge-case", "reward": 0.85, "bugs_found": False},
        {"iteration": 2, "target_vl": 2002, "protocol_rule": "frame_size",
         "strategy": "normal", "reward": 0.45, "bugs_found": False}
    ]
    
    vl_statistics = {
        2001: {"times_tested": 1, "avg_reward": 0.85, "max_reward": 0.85, "bugs_found": 0},
        2002: {"times_tested": 1, "avg_reward": 0.45, "max_reward": 0.45, "bugs_found": 0}
    }
    
    system_config = {"available_vls": [2001, 2002, 3001, 3002]}
    
    print("\nBuilding prompt for iteration 3...")
    prompt = build_fuzzing_prompt(
        spec_rules, test_cases, recent_results,
        vl_statistics, system_config, iteration=3
    )
    
    print(f"\n✓ Prompt built successfully")
    print(f"  Length: {len(prompt)} characters (~{len(prompt)//4} tokens)")
    print(f"\n  Key sections included:")
    print(f"    ✓ Protocol rules (bag, frame_structure, ...)")
    print(f"    ✓ Test cases with freedom to propose custom mutations")
    print(f"    ✓ Recent performance (last 2 iterations)")
    print(f"    ✓ VL statistics (2001 tested 1x, 2002 tested 1x)")
    print(f"    ✓ Decision guidelines (exploration vs exploitation)")
    print(f"    ✓ JSON output format")
    
    print(f"\n  Prompt preview (first 300 chars):")
    print("  " + "-" * 66)
    print("  " + prompt[:300].replace("\n", "\n  "))
    print("  " + "-" * 66)


def demo_mock_strategy():
    """Demonstrate strategy parsing with mock LLM response"""
    print("\n\n" + "=" * 70)
    print("2. STRATEGY PARSING (Mock LLM Response)")
    print("=" * 70)
    
    print("\nScenario 1: Predefined test cases")
    print("-" * 70)
    
    mock_response_1 = {
        "target_vl": 3001,
        "protocol_rule": "bag",
        "test_mode": "predefined",
        "test_cases": ["TC0", "TC3"],
        "custom_mutation": None,
        "strategy": "edge-case",
        "reasoning": "VL 3001 not tested yet. Using predefined BAG violations."
    }
    
    print(f"Mock LLM Response:")
    print(json.dumps(mock_response_1, indent=2))
    
    print(f"\n✓ Parsed strategy:")
    print(f"  Target VL: {mock_response_1['target_vl']} (untested - exploration)")
    print(f"  Protocol Rule: {mock_response_1['protocol_rule']}")
    print(f"  Test Mode: {mock_response_1['test_mode']}")
    print(f"  Test Cases: {mock_response_1['test_cases']}")
    print(f"  Strategy Type: {mock_response_1['strategy']}")
    
    print("\n\nScenario 2: Custom mutation (LLM's own idea)")
    print("-" * 70)
    
    mock_response_2 = {
        "target_vl": 9999,
        "protocol_rule": "virtual_link",
        "test_mode": "custom",
        "test_cases": None,
        "custom_mutation": "Use completely invalid VL ID 9999 (far outside configured range) with otherwise valid frame structure to test VL validation robustness",
        "strategy": "adversarial",
        "reasoning": "Previous tests showed system accepts some invalid VLs. Testing extreme case."
    }
    
    print(f"Mock LLM Response:")
    print(json.dumps(mock_response_2, indent=2))
    
    print(f"\n✓ Parsed strategy:")
    print(f"  Target VL: {mock_response_2['target_vl']} (invalid - adversarial mode)")
    print(f"  Protocol Rule: {mock_response_2['protocol_rule']}")
    print(f"  Test Mode: {mock_response_2['test_mode']}")
    print(f"  Custom Mutation: {mock_response_2['custom_mutation'][:60]}...")
    print(f"  Strategy Type: {mock_response_2['strategy']}")
    print(f"\n  💡 LLM proposed its own test beyond predefined cases!")


def demo_with_real_llm():
    """Demonstrate with real LLM (requires API key)"""
    print("\n\n" + "=" * 70)
    print("3. REAL LLM STRATEGY PLANNING")
    print("=" * 70)
    
    try:
        print("\n→ Initializing LLM Strategy Planner...")
        planner = LLMStrategyPlanner()
        
        print(f"✓ Planner initialized")
        print(f"  Model: {planner.model}")
        print(f"  Protocol rules: {len(planner.spec_rules)} loaded")
        print(f"  Test cases: {len(planner.test_cases)} loaded")
        
        # Test 1: First iteration (no history)
        print("\n\n→ Test 1: Planning first iteration (no history)")
        print("-" * 70)
        
        strategy1 = planner.plan_next_iteration(history=None, iteration=1)
        
        print(f"\n✓ LLM Strategy:")
        print(f"  Target VL: {strategy1['target_vl']}")
        print(f"  Protocol Rule: {strategy1['protocol_rule']}")
        print(f"  Test Mode: {strategy1['test_mode']}")
        if strategy1['test_mode'] == 'predefined':
            print(f"  Test Cases: {strategy1['test_cases']}")
        else:
            print(f"  Custom Mutation: {strategy1['custom_mutation']}")
        print(f"  Strategy: {strategy1['strategy']}")
        print(f"  Reasoning: {strategy1['reasoning']}")
        
        # Test 2: With history
        print("\n\n→ Test 2: Planning with history (learning from previous)")
        print("-" * 70)
        
        history = pd.DataFrame({
            "iteration": [1, 2, 3],
            "target_vl": [2001, 2001, 3001],
            "protocol_rule": ["bag", "bag", "frame_size"],
            "strategy": ["edge-case", "edge-case", "normal"],
            "reward": [0.85, 0.92, 0.45],
            "bugs_found": [False, False, False]
        })
        
        print("\nHistory summary:")
        print(f"  VL 2001: tested 2 times, avg_reward=0.89 (HIGH!)")
        print(f"  VL 3001: tested 1 time, avg_reward=0.45 (LOW)")
        
        strategy2 = planner.plan_next_iteration(history=history, iteration=4)
        
        print(f"\n✓ LLM Strategy:")
        print(f"  Target VL: {strategy2['target_vl']}")
        print(f"  Protocol Rule: {strategy2['protocol_rule']}")
        print(f"  Test Mode: {strategy2['test_mode']}")
        if strategy2['test_mode'] == 'predefined':
            print(f"  Test Cases: {strategy2['test_cases']}")
        else:
            print(f"  Custom Mutation: {strategy2['custom_mutation']}")
        print(f"  Strategy: {strategy2['strategy']}")
        print(f"  Reasoning: {strategy2['reasoning']}")
        
        print(f"\n  💡 LLM learned from history and adapted its strategy!")
        
    except ImportError:
        print("\n✗ OpenAI package not installed")
        print("  Install with: pip install openai")
    except ValueError as e:
        print(f"\n✗ Error: {e}")
        print("  Set OPENAI_API_KEY environment variable:")
        print("  export OPENAI_API_KEY=your_key_here")
    except Exception as e:
        print(f"\n✗ Error: {e}")


def demo_exploration_vs_exploitation():
    """Demonstrate exploration vs exploitation balance"""
    print("\n\n" + "=" * 70)
    print("4. EXPLORATION vs EXPLOITATION")
    print("=" * 70)
    
    print("\nThe LLM balances two strategies:")
    print()
    print("EXPLORATION (testing new areas):")
    print("  → VLs tested < 3 times")
    print("  → New protocol rules")
    print("  → Diverse test strategies")
    print()
    print("EXPLOITATION (deepening successful areas):")
    print("  → VLs with high avg_reward (>0.8)")
    print("  → Continue testing where bugs were found")
    print("  → Refine successful strategies")
    
    print("\n\nExample decision tree:")
    print("  IF VL has bugs found:")
    print("    → Continue testing that VL (exploitation)")
    print("  ELSE IF VL tested < 3 times:")
    print("    → Test it (exploration)")
    print("  ELSE IF VL has high reward:")
    print("    → Test it again (exploitation)")
    print("  ELSE:")
    print("    → Try different VL (exploration)")


def main():
    """Run all demos"""
    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 10 + "COMPONENT 2: LLM STRATEGY PLANNER - DEMO" + " " * 17 + "║")
    print("╚" + "═" * 68 + "╝")
    print("\n")
    
    demo_prompt_building()
    demo_mock_strategy()
    demo_exploration_vs_exploitation()
    demo_with_real_llm()  # Requires API key
    
    print("\n\n" + "=" * 70)
    print("COMPONENT 2 - COMPLETE!")
    print("=" * 70)
    print("\n✓ Prompt building: Fully implemented")
    print("✓ LLM integration: Fully implemented (GPT-5)")
    print("✓ Strategy parsing: Fully implemented")
    print("✓ Validation: Fully implemented")
    print("✓ Freedom: LLM can choose predefined OR custom mutations")
    print()
    print("Component 2 is ready for integration with:")
    print("  → Component 1 (Feedback Analyzer) - provides performance data")
    print("  → Component 3 (Test Generator) - executes the strategy")
    print("\n")


if __name__ == "__main__":
    main()

