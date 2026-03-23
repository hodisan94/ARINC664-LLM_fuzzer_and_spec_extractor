#!/usr/bin/env python3
"""
LLM Fuzzing Agent Prompt Builder

Builds prompts for the LLM to make intelligent fuzzing decisions.
The LLM has freedom to choose from predefined test cases OR propose
custom mutations based on what it learned from previous iterations.
"""

from typing import Dict, List, Any, Optional
import pandas as pd


def _build_coverage_section(coverage_stats: Optional[Dict[str, Any]], iteration: int) -> str:
    """Build coverage awareness section showing which rules are tested/untested."""
    if not coverage_stats:
        return ""

    lines = ["\n" + "=" * 70]
    lines.append("COVERAGE STATUS (CRITICAL — READ THIS FIRST!):")
    lines.append("=" * 70)

    covered = coverage_stats.get("covered_rules", [])
    uncovered = coverage_stats.get("uncovered_rules", [])
    mt_counts = coverage_stats.get("mutation_type_counts", {})
    total_rules = len(covered) + len(uncovered)
    coverage_pct = (len(covered) / total_rules * 100) if total_rules > 0 else 0

    lines.append(f"\nCoverage: {len(covered)}/{total_rules} rules = {coverage_pct:.1f}%")

    if mt_counts:
        overused = {k: v for k, v in sorted(mt_counts.items(), key=lambda x: -x[1]) if v >= 3}
        if overused:
            lines.append("\nOVERUSED mutation_types (AVOID THESE — you lose reward for repeating):")
            for mt, count in list(overused.items())[:10]:
                lines.append(f"  '{mt}' — used {count} times (PENALTY applied!)")

    if uncovered:
        lines.append(f"\nUNTESTED RULES ({len(uncovered)} remaining — high reward bonus for testing new ones!):")
        for rule in uncovered[:30]:
            lines.append(f"  - {rule}")
        if len(uncovered) > 30:
            lines.append(f"  ... and {len(uncovered) - 30} more")

    if covered:
        lines.append(f"\nALREADY TESTED ({len(covered)} rules — no new-rule bonus):")
        for rule in covered[:15]:
            count = mt_counts.get(rule, "?")
            lines.append(f"  - {rule} (tested ~{count}x)" if isinstance(count, int) else f"  - {rule}")
        if len(covered) > 15:
            lines.append(f"  ... and {len(covered) - 15} more")

    lines.append(f"\nYOUR GOAL: Maximize coverage by testing UNTESTED rules. You get a +1.0 BONUS for each new rule!")
    return "\n".join(lines)


def build_fuzzing_prompt(
    spec_rules: Dict[str, Any],
    test_cases: Dict[str, Any],
    recent_results: List[Dict[str, Any]],
    vl_statistics: Dict[int, Dict[str, Any]],
    system_config: Dict[str, Any],
    iteration: int,
    coverage_stats: Optional[Dict[str, Any]] = None
) -> str:
    """
    Build complete prompt for LLM-guided fuzzing.
    
    The prompt gives the LLM:
    - Complete visibility into protocol rules and test cases
    - Recent performance history
    - Coverage statistics (which rules tested, which untested)
    - Freedom to choose predefined test cases OR propose custom mutations
    - Guidelines for exploration vs exploitation
    
    Args:
        spec_rules: Protocol rules from spec_rules.json
        test_cases: Violation test cases from test_cases.json
        recent_results: Last N iteration results
        vl_statistics: Statistics per VL (times tested, avg reward, etc.)
        system_config: System configuration (available VLs, etc.)
        iteration: Current iteration number
        coverage_stats: Dict with covered_rules, uncovered_rules, mutation_type_counts
        
    Returns:
        Complete prompt string for LLM
    """
    
    role_definition = _build_role_definition()
    coverage_section = _build_coverage_section(coverage_stats, iteration)
    protocol_rules_section = _build_protocol_rules_section(spec_rules)
    test_cases_section = _build_test_cases_section(test_cases)
    recent_performance = _build_recent_performance_section(recent_results)
    vl_stats_section = _build_vl_statistics_section(vl_statistics, system_config)
    decision_guidelines = _build_decision_guidelines(iteration, coverage_stats)
    output_format = _build_output_format()
    
    prompt = f"""
{role_definition}

{coverage_section}

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
    for result in recent_results[-10:]:
        iteration = result.get('iteration', '?')
        vl = result.get('target_vl', '?')
        rule = result.get('protocol_rule', '?')
        strategy = result.get('strategy', '?')
        reward = result.get('reward', 0)
        bugs = result.get('bugs_found', False)
        recommendation = result.get('recommendation', '')
        
        bug_indicator = " [BUG FOUND!]" if bugs else ""
        lines.append(f"Iter {iteration}: VL={vl}, rule={rule}, strategy={strategy}, reward={reward:.2f}{bug_indicator}")
        if recommendation and len(recommendation) > 10:
            lines.append(f"  Feedback: {recommendation[:120]}")
    
    return "\n".join(lines)


def _build_vl_statistics_section(
    vl_statistics: Dict[int, Dict[str, Any]],
    system_config: Dict[str, Any]
) -> str:
    """Format VL testing statistics."""
    lines = ["\n" + "=" * 70]
    lines.append("VIRTUAL LINK (VL) CONFIGURATION & STATISTICS:")
    lines.append("=" * 70)
    
    available_vls = system_config.get('available_vls', [1001, 1002, 2001, 2002, 3001, 3002])
    lines.append(f"\nAVAILABLE VLs (you MUST choose ONLY from this list): {available_vls}")
    lines.append("WARNING: Any VL not in this list does not exist and will be IGNORED!")
    
    lines.append("\nVL CONFIGURATION (use this to choose effective mutation values):")
    lines.append("  VL    | BAG(ms) | MaxFrame | MinFrame | Source | MaxPayload")
    lines.append("  ------|---------|----------|----------|--------|----------")
    lines.append("  1001  |   4     |   512    |    64    |  ES1   |   495")
    lines.append("  1002  |   4     |   512    |    64    |  ES1   |   495")
    lines.append("  1003  |   8     |   512    |    64    |  ES1   |   495")
    lines.append("  2001  |   8     |   256    |    64    |  ES2   |   239")
    lines.append("  2002  |  16     |   256    |    64    |  ES2   |   239")
    lines.append("  2003  |  16     |   512    |    64    |  ES2   |   495")
    lines.append("  3001  |  32     |  1024    |    64    |  ES3   |  1007")
    lines.append("  3002  |  32     |  1024    |    64    |  ES3   |  1007")
    
    lines.append("\nMUTATION PARAMETERS THAT ACTUALLY AFFECT THE SIMULATOR:")
    lines.append("  1. frame_size: frames exceeding MaxFrame trigger FrameError drop at switch")
    lines.append("  2. timing_jitter_ms: changes send timing (negative=faster, positive=slower)")
    lines.append("  3. bag_value: converted to jitter relative to BAG (e.g. bag_value=2 on VL with BAG=4 => jitter=-2)")
    lines.append("  4. mac_mutation_type: 'spoof_src'|'spoof_dst'|'broadcast'|'invalid_src'|'zero_mac' => source MAC error drop at switch")
    lines.append("  5. prob: 0.0-1.0 TX-drop probability (frames silently dropped before sending)")
    lines.append("  6. sequence_number_override: force a specific seq num (e.g. 0=invalid, 255=stale) => rejection at receiving ES")
    lines.append("  7. dest_mac_mutation: 'corrupt_prefix'|'wrong_vl'|'zero' => constant field rejection at receiving ES")
    lines.append("")
    lines.append("  NOTE: payload_pattern is NOT yet supported by the simulator.")
    
    if not vl_statistics:
        lines.append("\nNo VL statistics yet (first iteration)")
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


def _build_decision_guidelines(iteration: int, coverage_stats: Optional[Dict[str, Any]] = None) -> str:
    """Provide decision-making guidelines to the LLM."""
    uncovered_count = len(coverage_stats.get("uncovered_rules", [])) if coverage_stats else "unknown"
    covered_count = len(coverage_stats.get("covered_rules", [])) if coverage_stats else 0

    exploration_priority = "HIGH" if (isinstance(covered_count, int) and covered_count < 40) else "MEDIUM"

    return f"""
{"=" * 70}
DECISION GUIDELINES:
{"=" * 70}

*** MOST IMPORTANT RULE ***
You MUST test a DIFFERENT protocol rule each iteration. You get +1.0 bonus
for each NEW rule and a HARSH PENALTY for reusing mutation_types you already tried.
Check the COVERAGE STATUS section and pick from UNTESTED RULES.
Remaining untested: {uncovered_count}. Exploration priority: {exploration_priority}.

1. COVERAGE-FIRST STRATEGY:
   - Look at the UNTESTED RULES list above
   - Pick a rule name from that list as your mutation_type
   - Use predefined test cases when available for that rule
   - This is the FASTEST way to maximize your reward

2. TEST CASE SELECTION:
   You have TWO options (PREFER OPTION A for untested rules):
   
   A) USE PREDEFINED TEST CASES (RECOMMENDED for broad coverage):
      - Choose 1-3 test cases from the "PREDEFINED TEST CASES" section
      - Match the rule name to find relevant test cases
      - Specify test case IDs like ["TC0", "TC2"]
   
   B) PROPOSE CUSTOM MUTATIONS:
      - Only use this for rules where no test cases exist
      - Or to go deeper on a rule that found bugs

3. STRATEGY TYPES:
   - "conformance": Test protocol compliance with valid parameters
   - "edge-case": Test boundary values, invalid identifiers (recommended)
   - "adversarial": Test extreme violations, stress testing

4. LEARNING FROM HISTORY:
   - If bug was found: Continue testing that area
   - If reward was high on a NEW rule: Good, now move to another new rule
   - If reward was high on a REPEATED rule: STOP — you already tested it, move on!

5. DIVERSITY:
   - NEVER repeat the same mutation_type more than 2 times total
   - Rotate through VLs: each VL should be tested roughly equally
   - Vary strategy types: mix conformance, edge-case, adversarial

ITERATION {iteration}: {"Early exploration — test as many NEW rules as possible!" if iteration < 15 else "Active coverage — fill remaining gaps in untested rules!" if iteration < 35 else "Late phase — revisit high-reward rules or go deeper on bug areas."}
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
  "mac_mutation_type": "<spoof_src|spoof_dst|broadcast|invalid_src|zero_mac or null>",
  "prob": <float 0.0-1.0 or null>,
  "sequence_number_override": <int 0-255 or null>,
  "dest_mac_mutation": "<corrupt_prefix|wrong_vl|zero or null>",
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
  "target_vl": 2002,
  "mutation_type": "bag_boundary",
  "test_cases": null,
  "bag_value": 3,
  "frame_size": 1519,
  "sequence_number": null,
  "timing_jitter_ms": null,
  "payload_pattern": null,
  "strategy": "adversarial",
  "reasoning": "BAG=3ms is not in the allowed discrete set [1,2,4,8,...128] and frame size 1519 exceeds 1518 max. Isolating policing behavior on VL 2002."
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

