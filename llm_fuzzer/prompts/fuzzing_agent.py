#!/usr/bin/env python3
"""
LLM Fuzzing Agent Prompt Builder

Builds prompts for the LLM to make intelligent fuzzing decisions.
The LLM has freedom to choose from predefined test cases OR propose
custom mutations based on what it learned from previous iterations.
"""

from typing import Dict, List, Any, Optional
import pandas as pd


# Prompt versions (TAES revision). "original" is the text used in the submitted campaigns;
# "revised" describes the mutation parameters as the simulator applies them (no test_cases
# recommendation, no token-bucket claim, corrected sequence-number and wrong_vl semantics).
# The two differ only in the passages below; everything else in the prompt is shared.
# "neutral" describes only what each mutation parameter changes in the traffic and the
# protocol rules, and says nothing about how this simulator reacts (what it drops, rejects
# or ignores, or which mutation "finds bugs"); it also replaces the shared mechanism list,
# test-case footer and output examples, which contain such statements.
PROMPT_VERSIONS = ("revised", "original", "neutral")

_MUTATION_PARAMETERS = {
    "original": [
        "\nMUTATION PARAMETERS THAT ACTUALLY AFFECT THE SIMULATOR:",
        "  1. frame_size: frames exceeding MaxFrame trigger FrameError drop at switch",
        "  2. timing_jitter_ms: changes send timing (negative=faster, positive=slower)",
        "  3. bag_value: converted to jitter relative to BAG (e.g. bag_value=2 on VL with BAG=4 => jitter=-2)",
        "  4. mac_mutation_type: 'spoof_src'|'spoof_dst'|'broadcast'|'invalid_src'|'zero_mac' => source MAC error drop at switch",
        "  5. prob: 0.0-1.0 TX-drop probability (frames silently dropped before sending)",
        "  6. sequence_number_override: force a specific seq num (e.g. 0=invalid, 255=stale) => rejection at receiving ES",
        "  7. dest_mac_mutation: 'corrupt_prefix'|'wrong_vl'|'zero' => constant field rejection at receiving ES",
        "",
        "  NOTE: payload_pattern is NOT yet supported by the simulator.",
    ],
    "revised": [
        "\nMUTATION PARAMETERS THAT ACTUALLY AFFECT THE SIMULATOR (nothing else reaches it):",
        "  1. frame_size: total frame size in bytes. Frames above the VL's MaxFrame or below its",
        "     MinFrame (or outside 64..1518) are dropped by the switch's frame validation; MaxFrame",
        "     and MinFrame themselves are valid.",
        "  2. timing_jitter_ms: fixed offset in ms added to EVERY send interval of the target VL",
        "     (e.g. -1 on a VL with BAG=4 sends every 3 ms; negative = faster than the BAG, which",
        "     the switch's BAG policing should drop; positive = slower).",
        "  3. bag_value: send interval in ms; converted to an offset relative to the BAG and added",
        "     to timing_jitter_ms (e.g. bag_value=2 on a VL with BAG=4 => offset -2).",
        "  4. mac_mutation_type: 'spoof_src'|'spoof_dst'|'broadcast'|'invalid_src'|'zero_mac' changes the",
        "     source MAC; frames whose source MAC does not match the VL are dropped at the switch.",
        "  5. prob: 0.0-1.0 probability of dropping each frame of the target VL at the sender.",
        "  6. sequence_number_override: 1-255 forces this sequence number on every frame; 0 or null =",
        "     no override (use 256 to send sequence number 0). A constant number makes the receiver",
        "     discard the repeated frames as duplicates.",
        "  7. dest_mac_mutation: 'corrupt_prefix'|'zero' break the constant 03:00:00:00 prefix, which",
        "     the receiving ES rejects; 'wrong_vl' changes only the VL bytes, which nothing checks.",
        "",
        "  NOTE: payload_pattern, sequence-number ranges in test cases, and the predefined",
        "  test_cases themselves are NOT sent to the simulator; only the parameters above are.",
    ],
    "neutral": [
        "\nMUTATION PARAMETERS (only these change the traffic; every other field is ignored):",
        "  All of them apply to the frames of target_vl only.",
        "  1. frame_size: total frame size in bytes (the VL table gives MinFrame and MaxFrame;",
        "     any value from 18 to 9000 can be sent).",
        "  2. timing_jitter_ms: whole milliseconds added to every send interval",
        "     (e.g. -1 on a VL with BAG=4 sends every 3 ms; +2 sends every 6 ms).",
        "  3. bag_value: a send interval in ms; bag_value minus the VL's BAG is added to",
        "     timing_jitter_ms (e.g. bag_value=2 on a VL with BAG=4 adds -2).",
        "  4. mac_mutation_type: 'spoof_src' sets a random unicast source MAC; 'invalid_src' a",
        "     random multicast source MAC; 'spoof_dst' a random multicast destination MAC;",
        "     'broadcast' the destination MAC ff:ff:ff:ff:ff:ff; 'zero_mac' both MACs to zero.",
        "  5. prob: probability 0.0-1.0 that each frame is not sent.",
        "  6. sequence_number_override: 1-255 writes this sequence number into every frame;",
        "     256 writes 0; 0 or null leaves the sequence numbers unchanged.",
        "     (sequence_number is used the same way when sequence_number_override is not set.)",
        "  7. dest_mac_mutation: 'corrupt_prefix' sets the first byte of the destination MAC",
        "     to 04 (the AFDX constant field is 03:00:00:00); 'wrong_vl' adds 1 to the fifth",
        "     byte (the VL identifier); 'zero' sets the destination MAC to zero.",
        "",
        "  NOTE: test_cases and payload_pattern are not applied to the traffic. To test a rule,",
        "  set the parameters above to the values you want to send.",
    ],
}

_MECHANISM_DESCRIPTIONS = {
    "original": {
        "sequence_number_override>0": "Sequence number override — triggers ES sequence check",
        "token_bucket_stress": "Token bucket stress (frame_size=1500 + default BAG timing) — overflows bandwidth budget",
    },
    "revised": {
        "sequence_number_override>0": "Sequence number override — constant number on every frame (receiver discards repeats as duplicates)",
        "token_bucket_stress": "Token bucket stress (frame_size=1500 + default BAG timing) — frame_size 1500 is above every VL's MaxFrame, so these frames are dropped by frame validation first",
    },
    # The neutral version lists unused parameters instead (_build_unused_parameters_section)
    "neutral": {},
}

# Parameters whose use the neutral version tracks, in the order of _MUTATION_PARAMETERS
_NEUTRAL_PARAMETERS = ("frame_size", "timing_jitter_ms", "bag_value", "mac_mutation_type", "prob",
                       "sequence_number_override", "dest_mac_mutation")

# Decision guidelines 2-4; {total_rules} is filled in.
_GUIDELINES_2_TO_4 = {
    "original": """2. USE PREDEFINED TEST CASES (STRONGLY RECOMMENDED):
   - Look at the "PREDEFINED TEST CASES" section — {total_rules}+ rules available
   - Match your chosen rule name to find its test cases
   - Set test_cases to e.g. ["TC0", "TC1"]

3. CUSTOM MUTATIONS (when no predefined TCs exist):
   - Propose specific values: bag_value, frame_size, sequence_number, etc.

4. IMPORTANT — MUTATION MECHANISMS FOR BUG FINDING:
   - mac_mutation_type: "spoof_src" => finds bugs in switch MAC validation
   - dest_mac_mutation: "corrupt_prefix" => finds bugs in ES constant-field check
   - frame_size: >1518 (e.g. 2000) => finds bugs in frame-size validation
   - sequence_number_override: 0 or 255 => finds bugs in sequence checking
   - timing_jitter_ms: negative value (e.g. -5) => finds bugs in BAG policing
   - TOKEN BUCKET STRESS: frame_size=1500 (do NOT change bag_value!)
     => Sends max-size VALID frames at the VL's NORMAL BAG rate.
        CRITICAL: Do NOT set bag_value — keep default timing so BAG policing passes.
        The large frame_size causes cumulative bandwidth to overflow the
        token bucket, triggering policing drops from the bandwidth check.
        This is the ONLY way to test token-bucket enforcement!""",
    "revised": """2. PREDEFINED TEST CASES:
   - Look at the "PREDEFINED TEST CASES" section — {total_rules}+ rules available
   - Use them to choose violating VALUES for your rule. The test_cases field itself
     (e.g. ["TC0", "TC1"]) is NOT sent to the simulator: to exercise the rule, also set
     the mutation parameters (frame_size, timing_jitter_ms, ...) to those values.

3. CUSTOM MUTATIONS:
   - Propose specific values: bag_value, frame_size, timing_jitter_ms, etc.

4. IMPORTANT — MUTATION MECHANISMS FOR BUG FINDING:
   - mac_mutation_type: "spoof_src" => exercises switch source-MAC validation
   - dest_mac_mutation: "corrupt_prefix" => exercises the ES constant-field check
   - frame_size: above MaxFrame or below MinFrame of the VL => exercises frame-size validation
   - sequence_number_override: forces one sequence number on every frame (the receiver
     discards the repeats as duplicates)
   - timing_jitter_ms: negative value (e.g. -1 on BAG=4) => exercises BAG policing
   - Token bucket: frames that pass the BAG check never exceed the token bucket in this
     switch configuration, so no input can exercise it.""",
    "neutral": """2. PREDEFINED TEST CASES:
   - Look at the "PREDEFINED TEST CASES" section — {total_rules}+ rules available
   - Use them as ideas for violating VALUES of a rule. The test_cases field is not applied
     to the traffic: set the mutation parameters to the values you want to send.

3. CHOOSING VALUES:
   - Base them on the protocol rules and the VL table: limits, allowed sets, field formats.
   - Vary them across iterations: below, at and above limits, and far outside them.

4. USE ALL PARAMETERS:
   - Over the campaign, try every mutation parameter, alone and in combination, on
     different VLs.""",
}

_OUTPUT_OPTION_1 = {
    "original": '1. Use PREDEFINED test cases: set "test_cases": ["TC0", "TC1"] (values from test cases list)',
    "revised": ('1. Use PREDEFINED test cases to pick values, and set the matching parameters: the\n'
                '   "test_cases" field alone is not sent to the simulator'),
}

# Footer of the test-case section (shared by "original" and "revised")
_TEST_CASES_FOOTER = {
    "shared": ["\nTo use a test case: set protocol_rule to the rule name above "
               "and test_cases to e.g. [\"TC0\", \"TC1\"].",
               "You can ALSO propose CUSTOM mutations beyond these test cases!"],
    "neutral": ["\nTo use a test case: set protocol_rule to the rule name above and set the "
                "mutation parameters to its values.",
                "You can also choose values that are not in any test case."],
}


def _build_coverage_section(coverage_stats: Optional[Dict[str, Any]], iteration: int) -> str:
    """Build coverage awareness section with category-level + rule-level info."""
    if not coverage_stats:
        return ""

    lines = ["\n" + "=" * 70]
    lines.append("COVERAGE STATUS (CRITICAL — READ THIS FIRST!):")
    lines.append("=" * 70)

    # --- Category-level coverage (primary metric) ---
    covered_cats = coverage_stats.get("covered_categories", [])
    uncovered_cats = coverage_stats.get("uncovered_categories", [])
    cat_pct = coverage_stats.get("category_coverage_pct", 0.0)
    cat_to_rules = coverage_stats.get("cat_to_rules", {})
    total_cats = len(covered_cats) + len(uncovered_cats)

    lines.append(f"\n*** SPEC CATEGORY COVERAGE: {len(covered_cats)}/{total_cats} = {cat_pct:.1f}% ***")

    if uncovered_cats:
        lines.append(f"\nUNCOVERED CATEGORIES ({len(uncovered_cats)} remaining — target these!):")
        for cat in uncovered_cats:
            example_rules = cat_to_rules.get(cat, [])
            examples = ", ".join(example_rules[:3]) if example_rules else cat
            lines.append(f"  [{cat}] try: {examples}")

    if covered_cats:
        lines.append(f"\nCOVERED CATEGORIES ({len(covered_cats)}):")
        for cat in covered_cats[:20]:
            lines.append(f"  [OK] {cat}")
        if len(covered_cats) > 20:
            lines.append(f"  ... +{len(covered_cats) - 20} more")

    # --- Rule-level details ---
    covered = coverage_stats.get("covered_rules", [])
    uncovered = coverage_stats.get("uncovered_rules", [])
    mt_counts = coverage_stats.get("mutation_type_counts", {})

    if mt_counts:
        overused = {k: v for k, v in sorted(mt_counts.items(), key=lambda x: -x[1]) if v >= 3}
        if overused:
            lines.append("\nOVERUSED mutation_types (AVOID — penalty applied):")
            for mt, count in list(overused.items())[:10]:
                lines.append(f"  '{mt}' — used {count}x")

    if uncovered:
        lines.append(f"\nUNTESTED RULES ({len(uncovered)} remaining — +1.0 BONUS for each new one!):")
        for rule in uncovered[:40]:
            lines.append(f"  - {rule}")
        if len(uncovered) > 40:
            lines.append(f"  ... and {len(uncovered) - 40} more")

    lines.append(f"\nYOUR GOAL: Cover as many SPEC CATEGORIES as possible!")
    lines.append(f"Pick rules from UNCOVERED CATEGORIES above to maximize coverage.")
    return "\n".join(lines)


def build_fuzzing_prompt(
    spec_rules: Dict[str, Any],
    test_cases: Dict[str, Any],
    recent_results: List[Dict[str, Any]],
    vl_statistics: Dict[int, Dict[str, Any]],
    system_config: Dict[str, Any],
    iteration: int,
    coverage_stats: Optional[Dict[str, Any]] = None,
    prompt_version: str = "revised"
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
        prompt_version: "revised" (default), "original" or "neutral"; see PROMPT_VERSIONS

    Returns:
        Complete prompt string for LLM
    """
    if prompt_version not in PROMPT_VERSIONS:
        raise ValueError(f"prompt_version must be one of {PROMPT_VERSIONS}, got {prompt_version!r}")

    role_definition = _build_role_definition()
    coverage_section = _build_coverage_section(coverage_stats, iteration)
    protocol_rules_section = _build_protocol_rules_section(spec_rules)
    test_cases_section = _build_test_cases_section(test_cases, prompt_version)
    recent_performance = _build_recent_performance_section(recent_results)
    vl_stats_section = _build_vl_statistics_section(vl_statistics, system_config, prompt_version)
    decision_guidelines = _build_decision_guidelines(iteration, coverage_stats, prompt_version)
    output_format = _build_output_format(prompt_version)
    
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


def _build_test_cases_section(test_cases: Dict[str, Any], prompt_version: str = "revised") -> str:
    """Format test cases for the prompt.

    Shows ALL rule names with summary + case count so the LLM can pick
    any of them, plus detailed examples for a handful of rules.
    """
    lines = ["\n" + "=" * 70]
    lines.append("PREDEFINED TEST CASES (You can use ANY of these by name):")
    lines.append("=" * 70)

    sorted_items = sorted(test_cases.items())

    lines.append(f"\nTotal rule categories with test cases: {len(sorted_items)}")
    lines.append("Pick any rule below as your 'protocol_rule' and reference its TC indices.\n")

    DETAILED_COUNT = 5
    for idx, (rule_name, rule_data) in enumerate(sorted_items):
        cases = rule_data.get("test_cases", [])
        summary = rule_data.get("rule_summary", "")
        if not cases:
            continue

        if idx < DETAILED_COUNT:
            lines.append(f"\n{rule_name}: ({len(cases)} TCs) — {summary[:100]}")
            for tc_idx, tc in enumerate(cases[:3]):
                lines.append(f"  TC{tc_idx}: {tc.get('violation_type', '?')} "
                             f"value={tc.get('value', '?')}")
            if len(cases) > 3:
                lines.append(f"  ... +{len(cases) - 3} more TCs")
        else:
            short_summary = f" — {summary[:80]}" if summary else ""
            lines.append(f"  {rule_name} ({len(cases)} TCs){short_summary}")

    lines.extend(_TEST_CASES_FOOTER["neutral" if prompt_version == "neutral" else "shared"])

    return "\n".join(lines)


def _build_recent_performance_section(recent_results: List[Dict[str, Any]]) -> str:
    """Format recent iteration results with metrics and category info."""
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
        cat = result.get('spec_category', 'unmapped')
        policing = result.get('policing_rate', 0.0)
        es_rej = result.get('es_rejection_rate', 0.0)
        mac_err = result.get('frames_dropped_mac_error', 0)
        
        bug_indicator = " [BUG!]" if bugs else ""
        cat_tag = f" [{cat}]" if cat != "unmapped" else " [no-category]"
        lines.append(
            f"Iter {iteration}: VL={vl}, rule={rule}{cat_tag}, "
            f"reward={reward:.2f}, policing={policing:.0f}%, "
            f"es_rej={es_rej:.0f}%, mac_err={mac_err}{bug_indicator}"
        )
    
    return "\n".join(lines)


def _build_vl_statistics_section(
    vl_statistics: Dict[int, Dict[str, Any]],
    system_config: Dict[str, Any],
    prompt_version: str = "revised"
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
    
    lines.extend(_MUTATION_PARAMETERS[prompt_version])

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


def _build_decision_guidelines(iteration: int, coverage_stats: Optional[Dict[str, Any]] = None,
                               prompt_version: str = "revised") -> str:
    """Provide decision-making guidelines using category-level coverage."""
    cat_pct = coverage_stats.get("category_coverage_pct", 0.0) if coverage_stats else 0.0
    uncovered_cats = coverage_stats.get("uncovered_categories", []) if coverage_stats else []
    total_rules = coverage_stats.get("total_rules", 1) if coverage_stats else 1

    if cat_pct < 40:
        phase = "EXPLORE"
        phase_msg = (f"Category coverage is LOW ({cat_pct:.0f}%) — "
                     f"{len(uncovered_cats)} spec categories uncovered. "
                     f"Pick rules from UNCOVERED CATEGORIES for maximum impact!")
    elif cat_pct < 80:
        phase = "FILL GAPS"
        phase_msg = (f"Good progress ({cat_pct:.0f}%)! {len(uncovered_cats)} categories remain. "
                     f"Focus on the UNCOVERED CATEGORIES list above.")
    else:
        phase = "DEEPEN"
        phase_msg = (f"Category coverage is HIGH ({cat_pct:.0f}%). "
                     f"Now DEEPEN: re-test covered categories with different VLs, "
                     f"parameters, and strategies. Overuse penalty is reduced.")

    if prompt_version == "neutral":
        return f"""
{"=" * 70}
DECISION GUIDELINES — Phase: {phase} (category coverage {cat_pct:.0f}%)
{"=" * 70}

{phase_msg}
{_build_unused_parameters_section(coverage_stats)}

1. PICK YOUR RULE:
   - Look at the UNCOVERED CATEGORIES list above — each shows example rules
   - Set your 'mutation_type' to EXACTLY a rule name from the test cases list
   - This covers a new spec category AND gives you +1.0 new-rule bonus

{_GUIDELINES_2_TO_4[prompt_version].format(total_rules=total_rules)}

5. STRATEGY TYPES:
   - "edge-case": boundary values
   - "adversarial": extreme violations, stress testing
   - "conformance": valid parameters, verify compliance

6. VL ROTATION: spread tests across VLs (1001-3002)

ITERATION {iteration}: {phase_msg}
"""

    # Build mutation mechanism coverage section
    used_mechs = coverage_stats.get("used_mutation_mechanisms", set()) if coverage_stats else set()
    all_mechs = {
        "mac_mutation_type:spoof_src": "Source MAC spoofing — triggers switch MAC validation",
        "dest_mac_mutation:corrupt_prefix": "Dest MAC corruption — triggers ES constant-field check",
        "frame_size>1518": "Oversized frames — triggers switch frame-size validation",
        "timing_jitter_ms<0": "BAG violation (fast timing) — triggers BAG policing",
        **_MECHANISM_DESCRIPTIONS[prompt_version],
    }
    untested_mechs = {k: v for k, v in all_mechs.items() if k not in used_mechs}

    mech_section = ""
    if untested_mechs:
        mech_lines = [
            "\n*** UNTESTED MUTATION MECHANISMS (use these to find MORE bugs!) ***",
            "These mutation types exercise DIFFERENT validation paths in the simulator.",
            "Each one can reveal bugs that NO other mutation can find!",
        ]
        for mech, desc in untested_mechs.items():
            param_hint = mech.split(":")[0] if ":" in mech else mech.split(">")[0] if ">" in mech else mech.split("<")[0]
            mech_lines.append(f"  UNTESTED: {desc}")
            mech_lines.append(f"           Set: {mech}")
        mech_lines.append(f"\n{len(untested_mechs)} mutation mechanisms never tested — BIG opportunity!")
        mech_section = "\n".join(mech_lines)

    return f"""
{"=" * 70}
DECISION GUIDELINES — Phase: {phase} (category coverage {cat_pct:.0f}%)
{"=" * 70}

{phase_msg}
{mech_section}

1. PICK YOUR RULE:
   - Look at the UNCOVERED CATEGORIES list above — each shows example rules
   - Set your 'mutation_type' to EXACTLY a rule name from the test cases list
   - This covers a new spec category AND gives you +1.0 new-rule bonus

{_GUIDELINES_2_TO_4[prompt_version].format(total_rules=total_rules)}
   Combine these with different rules for maximum coverage!

5. STRATEGY TYPES:
   - "edge-case": boundary values (RECOMMENDED — most findings)
   - "adversarial": extreme violations, stress testing
   - "conformance": valid parameters, verify compliance

6. VL ROTATION: spread tests across VLs (1001-3002)

ITERATION {iteration}: {phase_msg}
"""


def _build_unused_parameters_section(coverage_stats: Optional[Dict[str, Any]]) -> str:
    """Neutral version: name the mutation parameters this campaign has not used yet."""
    used = coverage_stats.get("used_parameters", set()) if coverage_stats else set()
    unused = [p for p in _NEUTRAL_PARAMETERS if p not in used]
    if not unused:
        return ""
    return ("\nMUTATION PARAMETERS NOT USED YET in this campaign (no iteration has set them "
            "to a non-default value):\n  " + ", ".join(unused))


def _build_output_format(prompt_version: str = "revised") -> str:
    """Specify the expected JSON output format - FULL FREEDOM FOR LLM."""
    if prompt_version == "neutral":
        return _NEUTRAL_OUTPUT_FORMAT
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
""" + _OUTPUT_OPTION_1[prompt_version] + """
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

Example 6 - MAC spoofing (finds MAC validation bugs):
{
  "target_vl": 2001,
  "mutation_type": "mac_source_validation",
  "test_cases": null,
  "bag_value": null,
  "frame_size": null,
  "sequence_number": null,
  "timing_jitter_ms": null,
  "mac_mutation_type": "spoof_src",
  "prob": 1.0,
  "sequence_number_override": null,
  "dest_mac_mutation": null,
  "payload_pattern": null,
  "strategy": "adversarial",
  "reasoning": "Testing source MAC validation at the switch. spoof_src should trigger MAC error drops."
}

Example 7 - Destination MAC corruption (finds constant-field bugs):
{
  "target_vl": 1002,
  "mutation_type": "constant_field_check",
  "test_cases": null,
  "bag_value": null,
  "frame_size": null,
  "sequence_number": null,
  "timing_jitter_ms": null,
  "mac_mutation_type": null,
  "prob": null,
  "sequence_number_override": null,
  "dest_mac_mutation": "corrupt_prefix",
  "payload_pattern": null,
  "strategy": "adversarial",
  "reasoning": "Testing ARINC 664 constant field check at receiving ES by corrupting the multicast prefix."
}

Example 8 - Sequence number override (finds sequence check bugs):
{
  "target_vl": 3001,
  "mutation_type": "sequence_number_integrity",
  "test_cases": null,
  "bag_value": null,
  "frame_size": null,
  "sequence_number": null,
  "timing_jitter_ms": null,
  "mac_mutation_type": null,
  "prob": null,
  "sequence_number_override": 255,
  "dest_mac_mutation": null,
  "payload_pattern": null,
  "strategy": "edge-case",
  "reasoning": "Override sequence number to 255 (max uint8) to test sequence number boundary and integrity checking."
}

THINK STEP BY STEP:
1. Which VL should I test? Why?
2. What mutation parameters will expose bugs?
3. What specific VALUES should I test? (not just rule names!)
4. What strategy (conformance/edge-case/adversarial)?
5. What do I expect to learn?
6. Have I tested ALL mutation mechanisms? (mac_mutation_type, dest_mac_mutation, etc.)
"""


_NEUTRAL_OUTPUT_FORMAT = "\n" + "=" * 70 + """
OUTPUT FORMAT (JSON):
""" + "=" * 70 + """

{
  "target_vl": <int, one of the available VLs>,
  "mutation_type": "<rule name you are testing>",
  "test_cases": ["<tc_id>", ...] OR null,
  "bag_value": <int or null>,
  "frame_size": <int or null>,
  "timing_jitter_ms": <int or null>,
  "mac_mutation_type": "<spoof_src|invalid_src|spoof_dst|broadcast|zero_mac or null>",
  "prob": <float 0.0-1.0 or null>,
  "sequence_number_override": <int 1-256 or null>,
  "dest_mac_mutation": "<corrupt_prefix|wrong_vl|zero or null>",
  "strategy": "conformance" OR "edge-case" OR "adversarial",
  "reasoning": "<brief explanation of your choice>"
}

Only the mutation parameters (bag_value, frame_size, timing_jitter_ms, mac_mutation_type,
prob, sequence_number_override, dest_mac_mutation) change the traffic. A strategy that sets
none of them sends normal traffic. test_cases only records which test cases your values
come from.

EXAMPLES (format only; choose your own rules, VLs and values):

Example 1 - one parameter:
{
  "target_vl": 2002,
  "mutation_type": "Traffic Shaping.bag_value",
  "test_cases": null,
  "bag_value": 8,
  "frame_size": null,
  "timing_jitter_ms": null,
  "mac_mutation_type": null,
  "prob": null,
  "sequence_number_override": null,
  "dest_mac_mutation": null,
  "strategy": "edge-case",
  "reasoning": "The rule fixes the BAG of each VL; VL 2002 has BAG 16 ms, so this sends every 8 ms."
}

Example 2 - values taken from a predefined test case:
{
  "target_vl": 1003,
  "mutation_type": "<rule name from the test cases list>",
  "test_cases": ["TC2"],
  "bag_value": null,
  "frame_size": 40,
  "timing_jitter_ms": null,
  "mac_mutation_type": null,
  "prob": null,
  "sequence_number_override": null,
  "dest_mac_mutation": null,
  "strategy": "edge-case",
  "reasoning": "TC2 of this rule is a 40-byte frame; frame_size is set to that value."
}

Example 3 - several parameters together:
{
  "target_vl": 3002,
  "mutation_type": "<rule name>",
  "test_cases": null,
  "bag_value": null,
  "frame_size": 1100,
  "timing_jitter_ms": -6,
  "mac_mutation_type": null,
  "prob": 0.2,
  "sequence_number_override": null,
  "dest_mac_mutation": "zero",
  "strategy": "adversarial",
  "reasoning": "Combines a frame above this VL's MaxFrame, a shorter interval, sender loss and an all-zero destination address."
}

THINK STEP BY STEP:
1. Which rule and which VL? Why?
2. Which parameter values express a violation (or a boundary) of that rule?
3. Have I varied the parameters, values and VLs across iterations?
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

