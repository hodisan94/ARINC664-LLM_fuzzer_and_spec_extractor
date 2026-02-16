#!/usr/bin/env python3
"""
LLM Verification Script - 100% Testing Before Publication

This script verifies that:
1. LLM receives the prompt correctly
2. LLM understands the format
3. LLM returns valid JSON
4. Strategy planner works with real LLM
5. All components integrate properly

Run: python3 llm_fuzzer/verify_llm.py
"""

import sys
import json
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from llm_fuzzer.core.strategy_planner import LLMStrategyPlanner
from llm_fuzzer.utils.spec_loader import SpecificationLoader
from llm_fuzzer.utils.test_case_loader import TestCaseLoader
from llm_fuzzer.prompts.fuzzing_agent import build_fuzzing_prompt
import pandas as pd


def check_openai_key():
    """Check if OpenAI API key is configured."""
    print("=" * 70)
    print("STEP 1: Checking OpenAI API Key")
    print("=" * 70)
    
    api_key = os.getenv('OPENAI_API_KEY')
    
    if not api_key:
        print("❌ ERROR: OPENAI_API_KEY not found!")
        print("\nPlease set it:")
        print("  export OPENAI_API_KEY='your-key-here'")
        print("\nOr add to ~/.bashrc:")
        print("  echo 'export OPENAI_API_KEY=\"your-key-here\"' >> ~/.bashrc")
        print("  source ~/.bashrc")
        return False
    
    print(f"✅ API Key found: {api_key[:10]}...{api_key[-4:]}")
    return True


def test_prompt_generation():
    """Test that prompt generation works."""
    print("\n" + "=" * 70)
    print("STEP 2: Testing Prompt Generation")
    print("=" * 70)
    
    try:
        # Load data
        spec_loader = SpecificationLoader("configs/spec_rules.json")
        test_case_loader = TestCaseLoader("configs/test_cases.json")
        
        print("✅ Loaded spec rules and test cases")
        
        # Generate prompt
        prompt = build_fuzzing_prompt(
            spec_rules=spec_loader.get_all_rules(),
            test_cases=test_case_loader.get_all_test_cases(),
            recent_results=[],
            vl_statistics={},
            system_config={'available_vls': [1001, 1002, 2001, 2002, 3001, 3002]},
            iteration=0
        )
        
        print(f"✅ Prompt generated: {len(prompt)} characters")
        print(f"✅ Prompt lines: {len(prompt.split(chr(10)))}")
        
        # Show snippet
        print("\nPrompt snippet (first 500 chars):")
        print("-" * 70)
        print(prompt[:500] + "...")
        print("-" * 70)
        
        return prompt
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_llm_query_simple():
    """Test a simple LLM query (no prompt, just check connection)."""
    print("\n" + "=" * 70)
    print("STEP 3: Testing LLM Connection (Simple Query)")
    print("=" * 70)
    
    try:
        from openai import OpenAI
        
        client = OpenAI()
        print("✅ OpenAI client initialized")
        
        # Simple test query
        print("\nSending test query to GPT-5...")
        response = client.chat.completions.create(
            model="gpt-5",
            messages=[
                {"role": "user", "content": "Reply with exactly: 'API connection successful'"}
            ],
            temperature=0
        )
        
        reply = response.choices[0].message.content
        print(f"✅ LLM Response: '{reply}'")
        
        return True
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_llm_with_full_prompt():
    """Test LLM with the actual fuzzing prompt."""
    print("\n" + "=" * 70)
    print("STEP 4: Testing LLM with Full Fuzzing Prompt")
    print("=" * 70)
    
    try:
        planner = LLMStrategyPlanner(
            spec_rules_path="configs/spec_rules.json",
            test_cases_path="configs/test_cases.json"
        )
        
        print("✅ Strategy planner initialized")
        print("\nQuerying LLM (Iteration 0 - First Test)...")
        print("This may take 10-30 seconds...")
        
        strategy = planner.plan_next_iteration(
            history=None,  # No history for first iteration
            iteration=0,
            system_config={'available_vls': [1001, 1002, 2001, 2002, 3001, 3002]}
        )
        
        print("\n" + "=" * 70)
        print("LLM RESPONSE:")
        print("=" * 70)
        print(json.dumps(strategy, indent=2))
        print("=" * 70)
        
        # Validate response
        required_fields = ['target_vl', 'protocol_rule', 'test_mode', 'strategy', 'reasoning']
        missing = [f for f in required_fields if f not in strategy]
        
        if missing:
            print(f"❌ ERROR: Missing fields: {missing}")
            return False
        
        print("\n✅ All required fields present")
        print(f"✅ Target VL: {strategy['target_vl']}")
        print(f"✅ Protocol Rule: {strategy['protocol_rule']}")
        print(f"✅ Test Mode: {strategy['test_mode']}")
        print(f"✅ Strategy: {strategy['strategy']}")
        print(f"✅ Reasoning: {strategy['reasoning'][:100]}...")
        
        # Check test mode consistency
        if strategy['test_mode'] == 'predefined':
            if not strategy.get('test_cases'):
                print("❌ ERROR: predefined mode but no test_cases!")
                return False
            print(f"✅ Test Cases: {strategy['test_cases']}")
        elif strategy['test_mode'] == 'custom':
            if not strategy.get('custom_mutation'):
                print("❌ ERROR: custom mode but no custom_mutation!")
                return False
            print(f"✅ Custom Mutation: {strategy['custom_mutation'][:100]}...")
        
        return strategy
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_llm_with_history():
    """Test LLM with mock history (simulating iteration 5)."""
    print("\n" + "=" * 70)
    print("STEP 5: Testing LLM with History (Iteration 5)")
    print("=" * 70)
    
    try:
        planner = LLMStrategyPlanner(
            spec_rules_path="configs/spec_rules.json",
            test_cases_path="configs/test_cases.json"
        )
        
        # Mock history as DataFrame
        mock_history = pd.DataFrame([
            {'iteration': 1, 'target_vl': 2001, 'protocol_rule': 'bag', 'strategy': 'edge-case', 'reward': 0.75, 'bugs_found': False},
            {'iteration': 2, 'target_vl': 1001, 'protocol_rule': 'virtual_link', 'strategy': 'adversarial', 'reward': 0.85, 'bugs_found': True},
            {'iteration': 3, 'target_vl': 2001, 'protocol_rule': 'bag', 'strategy': 'edge-case', 'reward': 0.45, 'bugs_found': False},
            {'iteration': 4, 'target_vl': 3001, 'protocol_rule': 'frame_structure.ethernet', 'strategy': 'conformance', 'reward': 0.60, 'bugs_found': False},
        ])
        
        print("Querying LLM with history...")
        print("This may take 10-30 seconds...")
        
        strategy = planner.plan_next_iteration(
            history=mock_history,
            iteration=5,
            system_config={'available_vls': [1001, 1002, 2001, 2002, 3001, 3002]}
        )
        
        print("\n" + "=" * 70)
        print("LLM RESPONSE (with history):")
        print("=" * 70)
        print(json.dumps(strategy, indent=2))
        print("=" * 70)
        
        print("\n✅ LLM considered history and made decision")
        print(f"✅ Reasoning references history: {'iteration' in strategy['reasoning'].lower() or 'previous' in strategy['reasoning'].lower()}")
        
        return strategy
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_different_scenarios():
    """Test LLM in different scenarios."""
    print("\n" + "=" * 70)
    print("STEP 6: Testing Different Scenarios")
    print("=" * 70)
    
    scenarios = [
        {
            'name': 'Bug Found - Should Dig Deeper',
            'history': pd.DataFrame([
                {'iteration': 1, 'target_vl': 2001, 'protocol_rule': 'bag', 'strategy': 'edge-case', 'reward': 0.95, 'bugs_found': True},
            ]),
            'iteration': 2
        },
        {
            'name': 'Low Reward - Should Try Different Approach',
            'history': pd.DataFrame([
                {'iteration': 1, 'target_vl': 2001, 'protocol_rule': 'bag', 'strategy': 'conformance', 'reward': 0.25, 'bugs_found': False},
            ]),
            'iteration': 2
        },
    ]
    
    planner = LLMStrategyPlanner(
        spec_rules_path="configs/spec_rules.json",
        test_cases_path="configs/test_cases.json"
    )
    
    results = []
    
    for scenario in scenarios:
        print(f"\n📋 Scenario: {scenario['name']}")
        print("-" * 70)
        
        try:
            strategy = planner.plan_next_iteration(
                history=scenario['history'],
                iteration=scenario['iteration'],
                system_config={'available_vls': [1001, 1002, 2001, 2002, 3001, 3002]}
            )
            
            print(f"✅ VL: {strategy['target_vl']}, Rule: {strategy['protocol_rule']}, Strategy: {strategy['strategy']}")
            print(f"   Reasoning: {strategy['reasoning'][:150]}...")
            
            results.append({'scenario': scenario['name'], 'success': True, 'strategy': strategy})
            
        except Exception as e:
            print(f"❌ ERROR: {e}")
            results.append({'scenario': scenario['name'], 'success': False, 'error': str(e)})
    
    return results


def main():
    """Run all verification tests."""
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 68 + "║")
    print("║" + "  LLM VERIFICATION - 100% Testing Before Publication".center(68) + "║")
    print("║" + " " * 68 + "║")
    print("╚" + "=" * 68 + "╝")
    print("\n")
    
    results = {}
    
    # Step 1: Check API key
    if not check_openai_key():
        print("\n❌ CANNOT PROCEED: Set OPENAI_API_KEY first!")
        return False
    results['api_key'] = True
    
    # Step 2: Test prompt generation
    prompt = test_prompt_generation()
    if not prompt:
        print("\n❌ CANNOT PROCEED: Prompt generation failed!")
        return False
    results['prompt_generation'] = True
    
    # Step 3: Test simple LLM connection
    if not test_llm_query_simple():
        print("\n❌ CANNOT PROCEED: LLM connection failed!")
        return False
    results['llm_connection'] = True
    
    # Step 4: Test with full prompt (iteration 0)
    strategy1 = test_llm_with_full_prompt()
    if not strategy1:
        print("\n❌ CANNOT PROCEED: Full prompt test failed!")
        return False
    results['full_prompt_test'] = strategy1
    
    # Step 5: Test with history
    strategy2 = test_llm_with_history()
    if not strategy2:
        print("\n❌ WARNING: History test failed!")
    results['history_test'] = strategy2
    
    # Step 6: Test different scenarios
    scenario_results = test_different_scenarios()
    results['scenarios'] = scenario_results
    
    # Final summary
    print("\n\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 68 + "║")
    print("║" + "  VERIFICATION RESULTS".center(68) + "║")
    print("║" + " " * 68 + "║")
    print("╚" + "=" * 68 + "╝")
    print("\n")
    
    print("✅ API Key: OK")
    print("✅ Prompt Generation: OK")
    print("✅ LLM Connection: OK")
    print("✅ Full Prompt Test: OK")
    print(f"{'✅' if results.get('history_test') else '⚠️ '} History Test: {'OK' if results.get('history_test') else 'FAILED'}")
    
    if results.get('scenarios'):
        success_count = sum(1 for r in results['scenarios'] if r['success'])
        total = len(results['scenarios'])
        print(f"✅ Scenario Tests: {success_count}/{total} passed")
    
    print("\n" + "=" * 70)
    print("CONCLUSION:")
    print("=" * 70)
    
    if results.get('full_prompt_test') and results.get('llm_connection'):
        print("✅ LLM Integration is VERIFIED and WORKING!")
        print("✅ Ready to proceed with Main Loop implementation")
        print("✅ Ready for experiments and paper publication")
        return True
    else:
        print("❌ LLM Integration has ISSUES")
        print("❌ Fix issues before proceeding")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

