"""
Open-discovery prompts for LLM-based protocol rule extraction.

Unlike prompts_strict.py which forces a predefined schema, these prompts
let the LLM freely discover and categorize rules from the specification.
The only constraint is the per-rule micro-format (ensuring comparability).

This implements the improved "Guided Discovery with Open Extensions" approach:
1. LLMs discover rules freely (no predefined categories)
2. Each rule follows a consistent micro-format for cross-model comparison
3. Post-extraction alignment matches rules semantically across models
"""

import json


# ============================================================================
# OPEN EXTRACTION PROMPT
# ============================================================================

SYSTEM_PROMPT_OPEN_EXTRACTION = """You are an expert in avionics protocols, specifically ARINC 664 Part 7 (AFDX).

Your task is to extract ALL protocol rules, constraints, and requirements from the given specification text.

IMPORTANT: You decide which rules exist and how to categorize them. Do NOT limit yourself to any predefined set of categories. Extract EVERY rule you find.

For each rule, return a JSON object with these fields:

{
  "rules": [
    {
      "id": "rule_NNN",
      "category": "<your chosen category - e.g., 'bandwidth_allocation', 'frame_format', 'redundancy', etc.>",
      "subcategory": "<optional finer grouping or null>",
      "name": "<short descriptive name for this rule>",
      "field_name": "<the specific parameter or concept, e.g., 'BAG', 'Lmax', 'sequence_number'>",
      "data_type": "numeric | boolean | enum | string | range | behavioral",
      "constraint": {
        "type": "range | allowed_values | format | behavioral | boolean | formula",
        "value": "<the actual constraint - a number, list, formula, or description>",
        "unit": "<ms, bytes, us, Mbps, etc. or null>"
      },
      "source_quote": "<direct quote from the specification text that defines this rule>",
      "source_section": "<section or chapter reference if visible in the text>",
      "testable": true or false,
      "test_hint": "<if testable, brief description of how to violate this rule>"
    }
  ]
}

Guidelines:
- Extract EVERY rule, constraint, numerical limit, behavioral requirement, and protocol mandate
- YOU choose the categories - organize rules in whatever way makes sense
- Be precise with numerical values and include units
- Include the source_quote so the rule can be traced back to the specification
- A rule is "testable" if a fuzzer could generate traffic that violates it
- For testable rules, provide a test_hint explaining what violation looks like
- Use "behavioral" data_type for rules that describe process/behavior rather than values
- Do NOT skip rules just because they seem minor - extract everything
- If a single paragraph defines multiple distinct constraints, create separate rules for each
- Number rules sequentially within each chunk (rule_001, rule_002, ...)

Return ONLY valid JSON with the structure shown above.
"""


SYSTEM_PROMPT_OPEN_AGGREGATION = """You are an expert in avionics protocols, specifically ARINC 664 Part 7 (AFDX).

Your task is to aggregate protocol rules extracted from multiple text chunks into a single, deduplicated list.

When aggregating:
1. MERGE duplicate rules (same constraint described in different chunks) — keep the most complete version
2. PRESERVE unique rules from each chunk — do not drop rules just because they appear only once
3. RENUMBER rule IDs sequentially (rule_001, rule_002, ...)
4. STANDARDIZE categories — if two chunks use different category names for the same concept, pick the better name
5. KEEP the most specific source_quote for each rule
6. Do NOT invent rules — only include what was actually extracted

Output a single JSON with:
{
  "rules": [ ... ],
  "extraction_stats": {
    "total_rules": <number>,
    "categories_found": [<list of unique categories>],
    "testable_rules": <number of rules with testable=true>
  }
}
"""


# ============================================================================
# ALIGNMENT PROMPTS (for cross-model comparison)
# ============================================================================

SYSTEM_PROMPT_RULE_ALIGNMENT = """You are an expert in protocol specification analysis.

You are given protocol rule extractions from multiple LLM models, all analyzing the same ARINC 664 Part 7 specification. Each model independently extracted rules — they may use different wording, categories, or granularity.

Your task is to ALIGN rules across models by matching rules that describe the same protocol constraint.

For each group of matching rules, output:
{
  "aligned_groups": [
    {
      "group_id": "G001",
      "canonical_name": "<best descriptive name for this rule>",
      "canonical_category": "<best category name>",
      "matches": [
        {
          "provider": "<provider name>",
          "rule_id": "<rule ID from that provider>",
          "field_name": "<field name used by this provider>",
          "constraint_value": "<the value this provider extracted>"
        }
      ],
      "agreement": "full | partial | conflict",
      "consensus_value": "<agreed value, or null if conflicting>",
      "conflict_details": "<description of disagreement, or null>",
      "confidence": "high | medium | low"
    }
  ],
  "unique_rules": [
    {
      "provider": "<which provider found this>",
      "rule_id": "<rule ID>",
      "name": "<rule name>",
      "category": "<category>",
      "needs_verification": true,
      "reason": "Only found by one model"
    }
  ],
  "alignment_stats": {
    "total_groups": <number>,
    "full_agreement": <number>,
    "partial_agreement": <number>,
    "conflicts": <number>,
    "unique_rules": <number>
  }
}

Rules for alignment:
- Two rules MATCH if they describe the same protocol constraint, even with different wording
- "full" agreement = all models extracted the same value
- "partial" agreement = models agree on the concept but differ slightly in specifics
- "conflict" = models disagree on the actual value or interpretation
- A rule is "unique" if only ONE model found it — it still might be valid, just needs verification
- confidence: "high" = full agreement by 3+ models, "medium" = partial or 2-model agreement, "low" = conflict or unique
"""


# ============================================================================
# VERIFICATION PROMPT (for unique rules)
# ============================================================================

SYSTEM_PROMPT_VERIFY_UNIQUE = """You are an expert in ARINC 664 Part 7 (AFDX).

A protocol rule was found by only one LLM model during extraction. Your task is to verify whether this rule is genuine by checking it against the specification text.

For each rule, determine:
1. Is this a real rule stated in the specification?
2. Is the extracted value correct?
3. Should this rule be included in the final validated set?

Output:
{
  "verification": "confirmed | rejected | modified",
  "confidence": "high | medium | low",
  "corrected_value": "<corrected value if modified, else null>",
  "justification": "<why you confirmed, rejected, or modified this rule>",
  "source_quote": "<quote from spec that supports your decision>"
}
"""


# ============================================================================
# PROMPT GENERATORS
# ============================================================================

def get_open_extraction_prompt(
    chapter_name: str,
    text_chunk: str,
    chunk_index: int,
    total_chunks: int
) -> str:
    """Generate user prompt for open rule extraction from a text chunk."""
    return f"""Extract ALL protocol rules from this section of ARINC 664 Part 7.

Chapter: {chapter_name}
Chunk: {chunk_index + 1} of {total_chunks}

SPECIFICATION TEXT:
---
{text_chunk}
---

Extract every rule, constraint, numerical limit, and behavioral requirement.
YOU decide the categories — organize rules however makes sense for this text.
Number rules starting from rule_001 for this chunk.
Return ONLY valid JSON matching the required structure.
"""


def get_open_aggregation_prompt(extracted_rules_list: list) -> str:
    """Generate prompt for aggregating rules from multiple chunks."""
    chunks_text = "\n\n---\n\n".join([
        f"Chunk {i+1} ({len(rules.get('rules', []))} rules):\n{json.dumps(rules, indent=2)}"
        for i, rules in enumerate(extracted_rules_list)
    ])

    return f"""Aggregate the following rule extractions from {len(extracted_rules_list)} text chunks into a single deduplicated list.

{chunks_text}

---

Merge duplicates, preserve unique rules, renumber IDs sequentially (rule_001, rule_002, ...).
Standardize category names where different chunks used different names for the same concept.
Return ONLY valid JSON with the aggregated rules and extraction_stats.
"""


def get_alignment_prompt(provider_extractions: dict) -> str:
    """
    Generate prompt for aligning rules across multiple providers.
    
    Args:
        provider_extractions: Dict of provider_name -> {"rules": [...]}
    """
    providers_text = "\n\n" + "=" * 60 + "\n\n".join([
        f"\n{'=' * 60}\nProvider: {provider.upper()} ({len(data.get('rules', []))} rules)\n{'=' * 60}\n{json.dumps(data.get('rules', []), indent=2)}"
        for provider, data in provider_extractions.items()
    ])

    provider_names = list(provider_extractions.keys())

    return f"""Align and match protocol rules extracted by {len(provider_names)} different LLM models: {', '.join(provider_names)}.

{providers_text}

---

Match rules that describe the SAME protocol constraint across models.
Group matched rules, identify consensus values, flag conflicts.
List rules found by only one model as "unique_rules" needing verification.
Return ONLY valid JSON with aligned_groups, unique_rules, and alignment_stats.
"""


def get_verify_unique_prompt(
    rule: dict,
    spec_text: str,
    provider_name: str
) -> str:
    """Generate prompt for verifying a unique rule against the spec."""
    return f"""Verify whether this protocol rule (found only by {provider_name}) is genuine.

RULE TO VERIFY:
{json.dumps(rule, indent=2)}

RELEVANT SPECIFICATION TEXT:
---
{spec_text}
---

Is this rule genuinely stated in the specification text above?
If yes, confirm it. If the value is wrong, provide the corrected value.
If the rule is not actually in the spec, reject it.
Return ONLY valid JSON with your verification decision.
"""
