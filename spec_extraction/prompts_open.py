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

CONTEXT: We are building an AFDX network simulator and a protocol fuzzer that tests it. The fuzzer generates network traffic (frames) and sends them through a simulated AFDX network (End Systems, Switches, Virtual Links). We need to know the protocol rules so the fuzzer can intentionally violate them and observe how the network reacts.

Your task: extract protocol rules that define how an AFDX network BEHAVES — rules that govern frame transmission, reception, switching, policing, scheduling, redundancy, and any constraint that a network device must enforce or that network traffic must comply with.

IMPORTANT: You decide which rules exist and how to categorize them. Do NOT limit yourself to any predefined set of categories. If you find a rule that describes network behavior or a constraint on traffic, extract it.

SKIP rules that are NOT about network behavior — for example: document structure, publication dates, project management processes, editorial conventions, or liability disclaimers. These cannot be tested by a network fuzzer.

For each rule, return a JSON object with these fields:

{
  "rules": [
    {
      "id": "rule_NNN",
      "category": "<your chosen category>",
      "subcategory": "<optional finer grouping or null>",
      "name": "<short descriptive name for this rule>",
      "field_name": "<the specific parameter or concept, e.g., 'BAG', 'Lmax', 'sequence_number'>",
      "data_type": "numeric | boolean | enum | string | range | behavioral",
      "constraint": {
        "type": "range | allowed_values | format | behavioral | boolean | formula",
        "value": "<the actual constraint — use numbers when the spec gives numbers, lists when the spec gives enumerations, formulas when the spec gives formulas>",
        "unit": "<ms, bytes, us, Mbps, etc. or null>"
      },
      "source_quote": "<direct quote from the specification text that defines this rule>",
      "source_section": "<section or chapter reference if visible in the text>",
      "testable": true or false,
      "test_hint": "<if testable, brief description of how a fuzzer could violate this rule>"
    }
  ]
}

Guidelines:
- YOU choose the categories — organize rules in whatever way makes sense
- When the spec states a numeric value (e.g., "minimum 64 bytes"), use the actual number (64), not a string description
- When the spec lists allowed values (e.g., BAG = 1, 2, 4, ..., 128 ms), return them as a JSON list [1, 2, 4, 8, 16, 32, 64, 128]
- Include the source_quote so the rule can be traced back to the specification
- A rule is "testable" if a fuzzer could generate traffic that violates it in a network simulator
- For testable rules, provide a test_hint explaining what violation looks like
- If a single paragraph defines multiple distinct constraints, create separate rules for each
- Number rules sequentially within each chunk (rule_001, rule_002, ...)

Return ONLY valid JSON. Do NOT wrap the response in markdown code blocks.
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
# CONFLICT RESOLUTION PROMPT (for disagreements between models)
# ============================================================================

SYSTEM_PROMPT_RESOLVE_CONFLICT = """You are an expert judge for ARINC 664 Part 7 (AFDX) protocol rules.

Two or more LLM models independently extracted a protocol rule from the same specification, but they DISAGREE on the value or interpretation.

Your task: read the ACTUAL specification text provided and determine which model (if any) got the correct answer.

You MUST base your decision ONLY on what is written in the specification text. Do NOT guess or use external knowledge.

Output:
{
  "resolution": "model_a | model_b | synthesized | unresolvable",
  "chosen_value": "<the correct value based on the spec>",
  "confidence": "high | medium | low",
  "justification": "<explain WHY this is the correct value, referencing the spec text>",
  "source_quote": "<direct quote from the specification that proves the correct answer>"
}

Rules:
- "model_a" / "model_b": one model was right, use their exact value
- "synthesized": both models were partially right — combine into the complete answer
- "unresolvable": the specification text does not contain enough information to determine the correct value
- ALWAYS provide a source_quote from the spec to back up your decision
- If neither model is clearly correct, say "unresolvable" — do not guess
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
    return f"""Extract protocol rules relevant to AFDX network behavior from this section.

Chapter: {chapter_name}
Chunk: {chunk_index + 1} of {total_chunks}

SPECIFICATION TEXT:
---
{text_chunk}
---

Focus on rules that govern how frames are transmitted, received, switched, policed, or validated in an AFDX network. Skip purely administrative or documentary content.
Use actual numeric values where the spec provides them.
Number rules starting from rule_001 for this chunk.
Return ONLY valid JSON. Do NOT wrap in markdown code blocks.
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


def get_resolve_conflict_prompt(
    group: dict,
    spec_text: str
) -> str:
    """
    Generate prompt for resolving a conflict between models.

    Args:
        group: An aligned_group dict with matches showing conflicting values
        spec_text: Relevant section from the ARINC 664 spec
    """
    matches = group.get("matches", [])
    canonical_name = group.get("canonical_name", "Unknown rule")
    canonical_category = group.get("canonical_category", "Unknown")

    values_text = "\n".join([
        f"  - {m.get('provider', '?').upper()}: field=\"{m.get('field_name', '?')}\"  value=\"{m.get('constraint_value', '?')}\""
        for m in matches
    ])

    return f"""The following protocol rule has CONFLICTING extractions from different LLM models.

RULE: {canonical_name}
CATEGORY: {canonical_category}

CONFLICTING VALUES:
{values_text}

CONFLICT DETAILS: {group.get('conflict_details', 'Values differ across models')}

RELEVANT SPECIFICATION TEXT:
---
{spec_text}
---

Based ONLY on the specification text above, determine the correct value for this rule.
Return ONLY valid JSON with your resolution decision.
"""
