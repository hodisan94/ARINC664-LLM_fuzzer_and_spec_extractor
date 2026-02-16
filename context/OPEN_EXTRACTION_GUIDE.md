# Open Discovery Extraction — Guide

## Background: Why This Change Was Made

The original spec extraction pipeline used a **hardcoded JSON schema** with 12 predefined categories (bag, frame_structure, virtual_link, etc.). The LLMs could only fill in values within this fixed structure — they couldn't discover rules outside the predefined categories.

### Problems with the old approach
1. **Predefined categories limit discovery** — if ARINC 664 has a rule that doesn't fit the 12 categories, it gets lost
2. **Predefined field names** — the LLM must use exact field names like `lmin`, `lmax`, `allowed_values_ms`
3. **No way to discover new rules** — Phase 1 (Discovery) found things freely, but Phase 2 forced everything into the rigid schema
4. **Comparison was key-based** — two models could only be compared on identical JSON keys, not on semantic meaning

### The new approach: Open Discovery
1. LLMs freely discover rules — they choose their own categories, field names, and structure
2. Each rule follows a small consistent **micro-format** (so outputs are comparable)
3. After extraction, a separate **alignment step** matches rules semantically across models
4. Rules found by only one model are flagged for **verification** instead of being silently dropped

---

## What Changed (Files)

### New Files

| File | Purpose |
|------|---------|
| `spec_extraction/prompts_open.py` | Open-discovery prompts — LLMs discover freely with micro-format |
| `spec_extraction/align_rules.py` | Semantic alignment of rules across multiple model extractions |

### Modified Files

| File | What Changed |
|------|-------------|
| `spec_extraction/run_multimodel.py` | Added `--mode open\|strict` flag (default: `open`) |
| `spec_extraction/compare_extractions.py` | Auto-detects format; routes open format to `align_rules.py` |
| `spec_extraction/export_validated.py` | Added `--mode open\|strict\|auto` with `export_from_alignment()` |
| `spec_extraction/extract_test_cases.py` | `flatten_rules()` now handles both open list format and legacy nested format |

### Unchanged Files (still work as before)

| File | Status |
|------|--------|
| `spec_extraction/prompts_strict.py` | Untouched — used when `--mode strict` |
| `spec_extraction/prompts.py` | Untouched — used by `extract_rules.py` |
| `spec_extraction/arbitrate_conflicts.py` | Untouched — used in strict mode only |
| `spec_extraction/llm_client.py` | Untouched |
| `spec_extraction/llm_providers.py` | Untouched |
| `spec_extraction/pdf_utils.py` | Untouched |
| `spec_extraction/validate_test_cases.py` | Untouched |

---

## How to Run: Open Discovery Pipeline

All commands from project root: `/home/hodisan1994/ns-3-reset/ns-3`

### Prerequisites
```bash
# API keys must be set
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."    # optional
export GOOGLE_API_KEY="AI..."             # optional

# At least 2 providers needed for cross-validation
```

### Step 1: Multi-Model Open Extraction

```bash
python3 spec_extraction/run_multimodel.py \
    --pdf configs/ARINC_664P7.pdf \
    --mode open \
    --output-dir spec_extraction/multimodel_output
```

**What this does:**
- Reads the ARINC 664 Part 7 PDF
- Sends each chapter chunk to each available LLM provider (GPT, Claude, Gemini)
- Each LLM discovers rules freely — no predefined categories
- Aggregates rules per provider (deduplicates across chunks)
- Saves: `spec_extraction/multimodel_output/rules_openai.json`, `rules_anthropic.json`, `rules_google.json`

**Output format** (per provider):
```json
{
  "rules": [
    {
      "id": "rule_001",
      "category": "bandwidth_allocation",
      "name": "BAG Allowed Values",
      "field_name": "BAG",
      "data_type": "enum",
      "constraint": {
        "type": "allowed_values",
        "value": [1, 2, 4, 8, 16, 32, 64, 128],
        "unit": "ms"
      },
      "source_quote": "The BAG values shall be limited to powers of 2...",
      "source_section": "3.1",
      "testable": true,
      "test_hint": "Use BAG value not in the allowed list (e.g., 3, 5, 100)"
    }
  ],
  "extraction_stats": {
    "total_rules": 18,
    "categories_found": ["bandwidth_allocation", "frame_format", ...],
    "testable_rules": 15
  }
}
```

**Options:**
- `--parallel` — run providers in parallel (faster, uses more API quota)
- `--providers openai anthropic` — use specific providers only

### Step 2: Semantic Alignment

```bash
python3 spec_extraction/align_rules.py \
    --input-dir spec_extraction/multimodel_output \
    --output spec_extraction/alignment_results.json
```

**What this does:**
- Loads all `rules_*.json` files from the output directory
- Uses an LLM (default: OpenAI) to semantically match rules across providers
- Groups rules that describe the same constraint (even with different wording)
- Classifies each group: `full` agreement, `partial` agreement, or `conflict`
- Lists rules found by only one model as `unique_rules`
- Computes agreement metrics (pairwise agreement, Fleiss' Kappa)

**Output example:**
```json
{
  "alignment": {
    "aligned_groups": [
      {
        "group_id": "G001",
        "canonical_name": "BAG Allowed Values",
        "canonical_category": "bandwidth_allocation",
        "matches": [
          {"provider": "openai", "rule_id": "rule_003", "constraint_value": [1,2,4,8,16,32,64,128]},
          {"provider": "anthropic", "rule_id": "rule_007", "constraint_value": [1,2,4,8,16,32,64,128]},
          {"provider": "google", "rule_id": "rule_002", "constraint_value": [1,2,4,8,16,32,64,128]}
        ],
        "agreement": "full",
        "consensus_value": [1,2,4,8,16,32,64,128],
        "confidence": "high"
      }
    ],
    "unique_rules": [
      {
        "provider": "anthropic",
        "rule_id": "rule_019",
        "name": "ICMP Echo Prohibition",
        "needs_verification": true,
        "reason": "Only found by one model"
      }
    ]
  },
  "metrics": {
    "total_aligned_groups": 14,
    "full_agreement": 10,
    "partial_agreement": 3,
    "conflicts": 1,
    "unique_rules": 8,
    "fleiss_kappa": 0.723
  }
}
```

**Options:**
- `--arbiter anthropic` — use a different LLM as the alignment arbiter

### Step 3 (Optional): Verify Unique Rules

```bash
python3 spec_extraction/align_rules.py \
    --input-dir spec_extraction/multimodel_output \
    --output spec_extraction/alignment_results.json \
    --verify-unique \
    --pdf configs/ARINC_664P7.pdf
```

**What this does:**
- For each rule found by only one model, sends the rule + relevant spec text to an LLM
- The LLM verifies: is this a genuine rule? Is the value correct?
- Decision: `confirmed`, `rejected`, or `modified` (with corrected value)
- Confirmed rules get added to the final output; rejected ones are dropped

### Step 4: Export Validated Rules

```bash
python3 spec_extraction/export_validated.py --mode open
```

Or let it auto-detect:
```bash
python3 spec_extraction/export_validated.py
```

**What this does:**
- Reads `spec_extraction/alignment_results.json`
- Builds `configs/spec_rules.json` (clean rules for fuzzer)
- Builds `configs/spec_rules_validated.json` (rules with confidence metadata)
- Builds `configs/validation_report.json` (academic reporting)

**Options:**
- `--latex` — also generate a LaTeX table for the paper

### Step 5: Generate Test Cases

```bash
python3 spec_extraction/extract_test_cases.py \
    --spec-file configs/spec_rules.json \
    --output configs/test_cases.json \
    --validate
```

This works the same as before — it reads `spec_rules.json` and generates violation test cases. The `flatten_rules()` function now auto-detects whether the rules are in the new open format or legacy nested format.

---

## How to Run: Legacy Strict Pipeline

If you want to use the old predefined-schema approach:

```bash
python3 spec_extraction/run_multimodel.py --mode strict --pdf configs/ARINC_664P7.pdf
python3 spec_extraction/compare_extractions.py
python3 spec_extraction/arbitrate_conflicts.py --pdf configs/ARINC_664P7.pdf
python3 spec_extraction/export_validated.py --mode strict
python3 spec_extraction/extract_test_cases.py --validate
```

Everything works exactly as before.

---

## Technical Details

### The Micro-Format

Each rule from any model follows this structure:

```json
{
  "id": "rule_NNN",
  "category": "<LLM chooses>",
  "subcategory": "<optional>",
  "name": "<descriptive name>",
  "field_name": "<specific parameter>",
  "data_type": "numeric | boolean | enum | string | range | behavioral",
  "constraint": {
    "type": "range | allowed_values | format | behavioral | boolean | formula",
    "value": "<the actual constraint>",
    "unit": "<ms, bytes, etc.>"
  },
  "source_quote": "<direct quote from spec>",
  "source_section": "<section reference>",
  "testable": true/false,
  "test_hint": "<how to violate this rule>"
}
```

The LLM decides `category`, `name`, `field_name`, and `constraint.value`. The format itself is fixed so that we can compare outputs across models.

### Alignment Logic

The alignment step works in three layers:

1. **LLM Semantic Matching** (primary) — an arbiter LLM reads all provider outputs and groups rules by meaning
2. **Batch Processing** — if there are >60 rules, alignment runs in category batches to stay within prompt limits
3. **Fallback Matching** — if the LLM alignment fails, a simple `field_name`-based matching runs as a fallback

### Agreement Levels

| Level | Meaning | Confidence |
|-------|---------|------------|
| `full` | All models extracted the same rule with the same value | `high` |
| `partial` | Models agree on the concept but differ slightly in specifics | `medium` |
| `conflict` | Models disagree on the actual value or interpretation | `low` |
| `unique` | Only one model found this rule | `low` (until verified) |

### Backward Compatibility

- `--mode strict` works exactly as before
- `compare_extractions.py` auto-detects format and routes correctly
- `export_validated.py` auto-detects which input file exists
- `extract_test_cases.py` handles both rule formats transparently
- No existing configs or outputs were modified
