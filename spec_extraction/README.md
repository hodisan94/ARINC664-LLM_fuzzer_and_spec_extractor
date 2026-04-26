# AFDX Specification Extraction

This directory implements the paper's current Specification Knowledge Extraction pipeline for ARINC 664 Part 7.

The active pipeline is:

1. Extract protocol rules with three independent LLM providers: OpenAI, Anthropic, and Mistral.
2. Semantically align rules across providers.
3. Resolve conflicts and verify unique rules with a judge LLM.
4. Export validated rules for the fuzzer.
5. Generate compact violation test cases.

## Rule Extraction

Run from the repository root:

```bash
python3 spec_extraction/run_multimodel.py \
  --pdf configs/ARINC_664P7.pdf \
  --providers openai anthropic mistral
```

Outputs are written to `spec_extraction/multimodel_output/`:

- `rules_openai.json`
- `rules_anthropic.json`
- `rules_mistral.json`
- `extraction_summary.json`

## Alignment And Validation

```bash
python3 spec_extraction/align_rules.py \
  --input-dir spec_extraction/multimodel_output \
  --output spec_extraction/alignment_results.json \
  --pdf configs/ARINC_664P7.pdf \
  --full \
  --judge openai
```

Then export the validated rules:

```bash
python3 spec_extraction/export_validated.py \
  --mode open \
  --alignment spec_extraction/alignment_results.json \
  --extraction-dir spec_extraction/multimodel_output \
  --output-dir configs
```

Primary outputs:

- `configs/spec_rules_validated.json`
- `configs/spec_rules.json`
- `configs/validation_report.json`

## SUT-Relevance Filtering

Filter validated rules to the subset implemented by the AFDX simulator:

```bash
python3 spec_extraction/filter_rules.py \
  --input configs/spec_rules_validated.json \
  --output configs/spec_rules_filtered.json
```

## Test Case Extraction

Generate violation-oriented test cases from the filtered rule set:

```bash
python3 spec_extraction/extract_test_cases.py \
  --spec-file configs/spec_rules_filtered.json \
  --output configs/test_cases.json \
  --validate
```

## Active Files

- `run_multimodel.py` — multi-provider open-discovery extraction.
- `prompts_open.py` — extraction, alignment, verification, and conflict-resolution prompts.
- `align_rules.py` — semantic alignment, conflict resolution, and unique-rule verification.
- `export_validated.py` — exports validated rules and fuzzer-ready rule JSON.
- `filter_rules.py` — removes rules outside the simulator's implemented feature set.
- `extract_test_cases.py` — generates targeted violation test cases.
- `test_case_prompts.py` — prompts for test-case generation.
- `validate_test_cases.py` — validation logic for generated test cases.
- `llm_providers.py` — OpenAI, Anthropic, and Mistral provider abstraction.
- `llm_client.py` — OpenAI client used by test-case extraction.
- `pdf_utils.py` — PDF reading, chapter extraction, and text chunking.
