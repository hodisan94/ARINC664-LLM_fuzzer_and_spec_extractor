#!/usr/bin/env python3
"""
LLM Fuzzing Agent Prompt Builder

Builds prompts for the LLM to make intelligent fuzzing decisions.
The LLM has freedom to choose from predefined test cases OR propose
custom mutations based on what it learned from previous iterations.
"""

from typing import Dict, List, Any, Optional
import pandas as pd


def build_fuzzing_prompt(
    spec_rules: Dict[str, Any],
    test_cases: Dict[str, Any],
    recent_results: List[Dict[str, Any]],
    vl_statistics: Dict[int, Dict[str, Any]],
    system_config: Dict[str, Any],
    iteration: int
) -> str:
    """
    Build complete prompt for LLM-guided fuzzing.
    
    The prompt gives the LLM:
    - Complete visibility into protocol rules and test cases
    - Recent performance history
    - Freedom to choose predefined test cases OR propose custom mutations
    - Guidelines for exploration vs exploitation
    
    Args:
        spec_rules: Protocol rules from spec_rules.json
        test_cases: Violation test cases from test_cases.json
        recent_results: Last N iteration results
        vl_statistics: Statistics per VL (times tested, avg reward, etc.)
        system_config: System configuration (available VLs, etc.)
        iteration: Current iteration number
        
    Returns:
        Complete prompt string for LLM
    """
    
    # Build prompt sections
    role_definition = _build_role_definition()
    protocol_rules_section = _build_protocol_rules_section(spec_rules)
    test_cases_section = _build_test_cases_section(test_cases)
    recent_performance = _build_recent_performance_section(recent_results)
    vl_stats_section = _build_vl_statistics_section(vl_statistics, system_config)
    decision_guidelines = _build_decision_guidelines(iteration)
    output_format = _build_output_format()
    
    # Combine all sections
    prompt = f"""
{role_definition}

{protocol_rules_section}

{test_cases_section}

{recent_performance}

{vl_stats_section}

{decision_guidelines}

{output_format}

CURRENT ITERATION: {iteration}

YOUR DECISION:
"""
    
    return prompt


def _build_role_definition() -> str:
    """Define the LLM's role and mission."""
    return """You are an expert AFDX protocol fuzzing agent. Your mission is to intelligently test an AFDX network implementation to find bugs, edge cases, and protocol violations.

You have TWO modes of operation:
1. **Structured Testing**: Use predefined test cases from the specification
2. **Creative Exploration**: Propose your own custom mutations based on patterns you learned

You should balance between:
- **Exploration**: Testing new VLs and rules you haven't tested much
- **Exploitation**: Deepening investigation of promising areas (high reward, bugs found)"""


def _build_protocol_rules_section(spec_rules: Dict[str, Any]) -> str:
    """Format protocol rules for the prompt."""
    lines = ["=" * 70]
    lines.append("AVAILABLE PROTOCOL RULES:")
    lines.append("=" * 70)

    for idx, (rule_name, rule_data) in enumerate(sorted(spec_rules.items()), 1):
        lines.append(f"\n{idx}. {rule_name}")

        if isinstance(rule_data, dict):
            for key, value in rule_data.items():
                val_str = str(value)
                if len(val_str) <= 120:
                    lines.append(f"   - {key}: {value}")
                else:
                    lines.append(f"   - {key}: {val_str[:120]}...")
        elif isinstance(rule_data, (list, int, float, bool)):
            lines.append(f"   {rule_data}")
        elif isinstance(rule_data, str) and len(rule_data) <= 120:
            lines.append(f"   {rule_data}")

    return "\n".join(lines)


def _build_test_cases_section(test_cases: Dict[str, Any]) -> str:
    """Format test cases for the prompt."""
    lines = ["\n" + "=" * 70]
    lines.append("PREDEFINED TEST CASES (You can use these OR propose your own):")
    lines.append("=" * 70)
    
    for rule_name, rule_data in sorted(test_cases.items())[:10]:
        if "test_cases" not in rule_data:
            continue
            
        cases = rule_data["test_cases"]
        lines.append(f"\n{rule_name}: ({len(cases)} test cases available)")
        
        # Show first 3-4 examples
        for idx, tc in enumerate(cases[:4]):
            lines.append(f"  TC{idx}: {tc.get('violation_type', 'unknown')}")
            lines.append(f"       value={tc.get('value')}, reason: {tc.get('reason', '')[:50]}...")
        
        if len(cases) > 4:
            lines.append(f"  ... and {len(cases) - 4} more test cases")
    
    lines.append("\nNOTE: You can also propose CUSTOM mutations beyond these test cases!")
    
    return "\n".join(lines)


def _build_recent_performance_section(recent_results: List[Dict[str, Any]]) -> str:
    """Format recent iteration results."""
    lines = ["\n" + "=" * 70]
    lines.append("RECENT PERFORMANCE (Last iterations):")
    lines.append("=" * 70)
    
    if not recent_results:
        lines.append("\nNo previous iterations yet. This is your first test!")
        return "\n".join(lines)
    
    lines.append("")
    for result in recent_results[-5:]:  # Last 5
        iteration = result.get('iteration', '?')
        vl = result.get('target_vl', '?')
        rule = result.get('protocol_rule', '?')
        strategy = result.get('strategy', '?')
        reward = result.get('reward', 0)
        bugs = result.get('bugs_found', False)
        
        bug_indicator = " 🚨 BUG!" if bugs else ""
        lines.append(f"Iteration {iteration}: VL={vl}, rule={rule}, strategy={strategy}")
        lines.append(f"  → Reward: {reward:.2f}{bug_indicator}")
    
    return "\n".join(lines)


def _build_vl_statistics_section(
    vl_statistics: Dict[int, Dict[str, Any]],
    system_config: Dict[str, Any]
) -> str:
    """Format VL testing statistics."""
    lines = ["\n" + "=" * 70]
    lines.append("VIRTUAL LINK (VL) STATISTICS:")
    lines.append("=" * 70)
    
    if not vl_statistics:
        lines.append("\nNo VL statistics yet (first iteration)")
        available_vls = system_config.get('available_vls', [1001, 1002, 2001, 2002, 3001, 3002])
        lines.append(f"Available VLs: {available_vls}")
        return "\n".join(lines)
    
    lines.append("")
    for vl, stats in sorted(vl_statistics.items()):
        times_tested = stats.get('times_tested', 0)
        avg_reward = stats.get('avg_reward', 0)
        max_reward = stats.get('max_reward', 0)
        bugs_found = stats.get('bugs_found', 0)
        
        lines.append(f"VL {vl}: tested {times_tested} times, "
                    f"avg_reward={avg_reward:.2f}, max_reward={max_reward:.2f}, bugs={bugs_found}")
    
    return "\n".join(lines)


def _build_decision_guidelines(iteration: int) -> str:
    """Provide decision-making guidelines to the LLM."""
    return f"""
{"=" * 70}
DECISION GUIDELINES:
{"=" * 70}

1. EXPLORATION vs EXPLOITATION:
   - If a VL has been tested < 3 times: Consider testing it (exploration)
   - If a VL has high avg_reward (>0.8): Consider testing it more (exploitation)
   - If last 3 tests all used same VL: Try a different VL (diversity)

2. TEST CASE SELECTION:
   You have TWO options:
   
   A) USE PREDEFINED TEST CASES:
      - Choose 1-3 test cases from the "PREDEFINED TEST CASES" section
      - Good for systematic protocol violation testing
      - Specify test case IDs like ["TC0", "TC2"]
   
   B) PROPOSE CUSTOM MUTATIONS (Advanced - use your judgment!):
      - If you learned patterns from previous iterations
      - If you see gaps in the predefined test cases
      - Describe the mutation in natural language
      - Example: "Set BAG to 5ms (not in allowed list) and frame size to 2000 bytes"

3. STRATEGY TYPES:
   - "conformance": Test protocol compliance with valid parameters (baseline)
   - "edge-case": Test boundary values, invalid identifiers (recommended)
   - "adversarial": Test extreme violations, stress testing (aggressive)

4. LEARNING FROM HISTORY:
   - If recent test had high reward (>0.8): Similar approach might work
   - If bug was found: Continue testing that area/rule
   - If reward was low (<0.4): Try different approach

5. NOVELTY:
   - Prefer testing protocols/VLs you haven't tested recently
   - But if you found bugs, dig deeper in that area

ITERATION {iteration}: {"Early exploration phase" if iteration < 5 else "Active learning phase"}
"""


def _build_output_format() -> str:
    """Specify the expected JSON output format - FULL FREEDOM FOR LLM."""
    return """
{"=" * 70}
OUTPUT FORMAT (JSON):
{"=" * 70}

You have FULL CONTROL over testing approach. Choose what makes most sense:

{
  "target_vl": <int>,
  "mutation_type": "<primary_mutation>",
  "test_cases": ["<tc_id>", ...] OR null,
  "bag_value": <int or null>,
  "frame_size": <int or null>,
  "sequence_number": <int or null>,
  "timing_jitter_ms": <int or null>,
  "payload_pattern": "<pattern or null>",
  "strategy": "conformance" OR "edge-case" OR "adversarial",
  "reasoning": "<brief explanation of your choice>"
}

YOUR CHOICE - MULTIPLE OPTIONS:
1. Use PREDEFINED test cases: set "test_cases": ["TC0", "TC1"] (values from test cases list)
2. Set SPECIFIC values yourself: set "bag_value": 0, etc. (you choose exact values)
3. COMBINE both: use test cases AND add your own values
4. You decide what's best based on protocol rules, history, and reward!

IMPORTANT:
- You see ALL protocol rules → understand constraints
- You see ALL test cases → can use them or not
- You see history → learn what worked
- YOU DECIDE the best approach!

EXAMPLES:

Example 1 - Using PREDEFINED test cases:
{
  "target_vl": 2001,
  "mutation_type": "bag_violation",
  "test_cases": ["TC0", "TC1"],
  "bag_value": null,
  "frame_size": null,
  "sequence_number": null,
  "timing_jitter_ms": null,
  "payload_pattern": null,
  "strategy": "edge-case",
  "reasoning": "VL 2001 tested only once. Using predefined BAG test cases (below_min, not_in_list)."
}

Example 2 - Using SPECIFIC values (your choice):
{
  "target_vl": 9999,
  "mutation_type": "vl_validation",
  "test_cases": null,
  "bag_value": 8,
  "frame_size": 128,
  "sequence_number": 1,
  "timing_jitter_ms": null,
  "payload_pattern": null,
  "strategy": "adversarial",
  "reasoning": "Testing invalid VL 9999 with otherwise valid parameters. I chose 8ms BAG (valid) to isolate VL validation."
}

Example 3 - COMBINING test cases + custom values:
{
  "target_vl": 1002,
  "mutation_type": "combined_test",
  "test_cases": ["TC2"],
  "bag_value": null,
  "frame_size": 1519,
  "sequence_number": null,
  "timing_jitter_ms": 50,
  "payload_pattern": null,
  "strategy": "edge-case",
  "reasoning": "Using TC2 for base mutation, but adding frame size 1519 (boundary) and jitter 50ms for additional stress."
}

Example 4 - Learned from history (high reward approach):
{
  "target_vl": 3001,
  "mutation_type": "sequence_exploration",
  "test_cases": ["TC0", "TC4"],
  "bag_value": null,
  "frame_size": null,
  "sequence_number": 256,
  "timing_jitter_ms": null,
  "payload_pattern": null,
  "strategy": "edge-case",
  "reasoning": "Previous tests on sequences had high reward. Combining TC0,TC4 plus seq=256 (overflow) for comprehensive test."
}

Example 5 - Full control (stress test):
{
  "target_vl": 1001,
  "mutation_type": "aggressive_stress",
  "test_cases": null,
  "bag_value": 0,
  "frame_size": 2000,
  "sequence_number": 300,
  "timing_jitter_ms": 100,
  "payload_pattern": "malformed",
  "strategy": "adversarial",
  "reasoning": "I decided to test multiple violations simultaneously: BAG=0, oversized frame, invalid seq, jitter, malformed payload."
}

THINK STEP BY STEP:
1. Which VL should I test? Why?
2. What mutation parameters will expose bugs?
3. What specific VALUES should I test? (not just rule names!)
4. What strategy (conformance/edge-case/adversarial)?
5. What do I expect to learn?
"""


def format_vl_statistics(history: pd.DataFrame) -> Dict[int, Dict[str, Any]]:
    """
    Calculate VL statistics from iteration history.
    
    Args:
        history: DataFrame with columns: target_vl, reward, bugs_found, etc.
        
    Returns:
        Dictionary mapping VL ID to statistics
    """
    if history is None or len(history) == 0:
        return {}
    
    # Check if required columns exist
    if 'target_vl' not in history.columns:
        return {}
    
    stats = {}
    
    for vl in history['target_vl'].unique():
        vl_data = history[history['target_vl'] == vl]
        
        stats[int(vl)] = {
            'times_tested': len(vl_data),
            'avg_reward': float(vl_data['reward'].mean()) if 'reward' in vl_data else 0.0,
            'max_reward': float(vl_data['reward'].max()) if 'reward' in vl_data else 0.0,
            'bugs_found': int(vl_data['bugs_found'].sum()) if 'bugs_found' in vl_data else 0
        }
    
    return stats


if __name__ == "__main__":
    # Quick test
    print("=" * 70)
    print("PROMPT BUILDER TEST")
    print("=" * 70)
    
    # Mock data
    spec_rules = {"bag": {"allowed_values_ms": [1, 2, 4, 8, 16, 32, 64, 128]}}
    test_cases = {"bag": {"test_cases": [{"value": 0, "violation_type": "below_min", "reason": "test"}]}}
    recent_results = []
    vl_statistics = {}
    system_config = {"available_vls": [2001, 2002, 3001]}
    
    prompt = build_fuzzing_prompt(
        spec_rules, test_cases, recent_results, 
        vl_statistics, system_config, iteration=1
    )
    
    print(f"\nPrompt length: {len(prompt)} characters")
    print(f"Prompt preview (first 500 chars):\n")
    print(prompt[:500])
    print("\n...")

