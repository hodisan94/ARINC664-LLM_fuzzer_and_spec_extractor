# Project Roadmap

## Status Overview

| Component | Status | Notes |
|-----------|--------|-------|
| AFDX Simulator (C++) | Done | Fully functional, builds and runs |
| Spec Extraction (single model) | Done | Legacy — 10 rules, 96 test cases |
| Spec Extraction (multi-model, strict) | Done | Legacy — GPT + Claude + Gemini with arbitration |
| **Spec Extraction (open discovery)** | **Done** | **GPT + Claude, free discovery + alignment + judge** |
| LLM Fuzzer | Done | Full iterative loop with GPT |
| Random Baseline | Done | 15+ iterations completed |
| Boofuzz Baseline | Done (code) | Implementation exists, not yet documented in paper |
| Evaluation Framework | Done | Three-way comparison ready |
| **Rule Filtering** | **Done** | **LLM-analyzed sim capabilities → 236 / 431 rules (54.8%)** |
| **Test Case Regeneration** | **Next** | **Regenerate from 236 filtered rules** |
| **Fuzzer Integration Test** | **Planned** | **End-to-end test with filtered rules (5-10 iterations)** |
| Paper | In Progress | Needs update with open discovery results |

---

## What Has Been Implemented

### Phase 1: Specification Knowledge Extraction

#### Legacy (Strict Mode)
- [x] PDF text extraction from ARINC 664 Part 7
- [x] Single-model rule extraction (GPT)
- [x] Multi-model parallel extraction (GPT + Claude + Gemini)
- [x] Cross-model comparison and conflict detection
- [x] Conflict arbitration with judge LLM
- [x] Test case generation from extracted rules
- [x] Test case validation
- [x] Export to `spec_rules.json` and `test_cases.json`

#### Open Discovery Mode (Current)
- [x] Open-discovery prompts — LLMs freely discover rules with micro-format
- [x] Relevance-focused prompts — guide LLMs to extract only network-behavior rules
- [x] Improved numeric/list value extraction (actual numbers instead of strings)
- [x] Robust JSON parsing — handles Claude's markdown code-block wrapping
- [x] Semantic alignment across models (batch-based for large extractions)
- [x] Explicit conflict resolution — judge LLM consults spec text for disagreements
- [x] Unique rule verification — judge confirms/rejects rules found by only one model
- [x] Enriched export — rules include `test_hint`, `data_type`, `unit`, `source_quote`
- [x] Original extraction data lookup — export pulls constraint values from per-provider files

### Phase 2: LLM-Guided Iterative Fuzzing
- [x] LLM Strategy Planner (GPT based)
- [x] Test Generator (predefined + custom mutations)
- [x] Simulator Runner (ns-3 integration)
- [x] Feedback Analyzer + Reward Calculator
- [x] Iteration history logging (JSONL)
- [x] Resumable execution
- [x] Hybrid approach (LLM chooses test cases OR custom mutations)
- [x] Generic rule consumption — fuzzer reads any rule format, not hardcoded keys
- [x] Generic rule indexing — `spec_loader.py` indexes all leaf-value nodes

#### Rule Filtering (Current)
- [x] Systematic analysis of simulator capabilities vs. extracted rule categories
- [x] 12 relevant domains mapped (Frame, Switch, VL, Redundancy, Timing, QoS, etc.)
- [x] 11 excluded domains identified (TCP, ICMP, SAP, Data Encoding, IP Routing, etc.)
- [x] `filter_rules.py` with documented justification per domain
- [x] Output: `spec_rules_filtered.json` (236 rules, 72 categories) + `filter_report.json`
- [x] Zero unmapped categories — every extracted category accounted for

### Baselines
- [x] Random fuzzer baseline
- [x] Boofuzz systematic baseline

### Evaluation
- [x] Three-way comparison framework
- [x] LaTeX table generation
- [x] Statistical analysis scripts

---

## Latest Extraction Results (Feb 19, 2026)

### Pipeline Run: Open Discovery with GPT + Claude

| Metric | Value |
|--------|-------|
| Models used | OpenAI (GPT-4o) + Anthropic (Claude Sonnet) |
| OpenAI raw rules | 257 (94 categories) |
| Anthropic raw rules | 408 (121 categories) |
| Aligned groups (both models agree) | 109 |
| — Full agreement | 88 |
| — Partial agreement | 21 |
| — Conflicts | 0 |
| Unique rules (one model only) | 464 |
| — Confirmed by judge | 323 |
| — Rejected by judge | 52 |
| — Modified by judge | 2 |
| — Errors (API timeout) | 89 |
| **Final validated rules** | **434** |
| High confidence | 408 (94%) |
| Medium confidence | 24 (5.5%) |
| Categories in final output | 161 |
| Rules with values (not None) | 431/431 (100%) |

### Value Types in spec_rules.json
- Numeric values: 24
- Lists (e.g. BAG [1,2,4,...,128]): 59
- Booleans: 39
- String descriptions: 83
- Enriched dicts (value + test_hint + unit): 226

### Comparison with Previous Extraction
| | Old (Strict Mode) | New (Open Discovery) |
|---|---|---|
| Rules extracted | ~10 | 434 |
| Categories | 7 hardcoded | 161 LLM-chosen |
| Numeric precision | Some hardcoded | LLM-extracted actual values |
| Test hints | None | 226 rules have test_hint |
| Source quotes | None | Included for most rules |
| Conflict resolution | Arbiter picks one | Judge consults spec text |

---

## What Still Needs to Be Done

### Step 1: Test Case Regeneration (NEXT)
The current `configs/test_cases.json` is based on the old 10-rule extraction.
It must be regenerated from the 236 filtered rules so the fuzzer has relevant predefined test cases.

- [ ] Run `extract_test_cases.py` with `configs/spec_rules_filtered.json` (236 rules)
- [ ] Validate generated test cases are compatible with `test_generator.py`
- [ ] Verify the `test_case_loader.py` can parse the new format

### Step 2: Fuzzer Integration Test
Verify the full pipeline works end-to-end with the filtered rules before running real experiments.

- [ ] Verify the simulator still builds and runs (`./ns3 build afdx-demo`)
- [ ] Confirm `spec_loader.py` correctly loads the filtered rule format
- [ ] Run LLM fuzzer for 5-10 iterations — check that strategies, mutations, and rewards are sane

### Step 3: Full Experiments
Once integration is verified, run the real evaluation.

- [ ] Run full LLM fuzzer evaluation (50+ iterations) with filtered rules
- [ ] Run full random baseline evaluation with same rule set
- [ ] Run full boofuzz baseline evaluation
- [ ] Generate three-way comparison tables
- [ ] Produce definitive results for paper

### Paper Updates
- [ ] Document open discovery methodology (free discovery + alignment + judge)
- [ ] Add multi-model alignment + verification results (434 rules, 94% high confidence)
- [ ] Update extraction section: 10 rules → 434 rules with methodology comparison
- [ ] Document boofuzz baseline
- [ ] Add three-way comparison results to evaluation section
- [ ] Update methodology section with hybrid approach details

### Code Improvements
- [ ] Replace hardcoded absolute paths with relative/environment-based paths
- [ ] Standardize `sys.path` modifications across all modules
- [ ] Add proper `__init__.py` files for cleaner imports
- [ ] Add comprehensive error handling and logging
- [ ] Create a unified CLI entry point

### Future Enhancements
- [ ] Add Gemini to extraction (currently no API key)
- [ ] Support for additional LLM providers in fuzzer (not just GPT)
- [ ] Automated CI/CD pipeline for running evaluations
- [ ] Extended AFDX model with more protocol features
- [ ] Real hardware-in-the-loop testing support

---

## Change Log

### Feb 16, 2026 — Rule Filtering Implemented
- Created `filter_rules.py` — LLM-analyzed mapping of simulator features to rule categories
- 12 relevant domains (Frame, Switch, VL, Redundancy, Timing, QoS, Addressing, etc.)
- 11 excluded domains (TCP, ICMP, SAP, Data Encoding, IP Routing, Physical Layer, etc.)
- Result: 236 / 431 rules retained (54.8%), 72 categories, zero unmapped
- Output: `configs/spec_rules_filtered.json` + `configs/filter_report.json`
- For paper: filtering was performed by LLM analysis of the simulator's implementation

### Feb 21, 2026 — Planning & Context Update
- Updated all context/ documentation with current state
- Decided to skip rule filtering for now — let LLM learn what works
- Defined clear next steps: test case regeneration → integration test → experiments
- Rule filtering deferred to "if needed" based on fuzzer behavior

### Feb 19, 2026 — Open Discovery Pipeline v2
- Ran full open discovery extraction with GPT + Claude
- Fixed `export_validated.py` — save code was unreachable (function split bug)
- Added original extraction data lookup — unique rules now include constraint values
- Enriched clean rules with `test_hint`, `data_type`, `unit`, `source_quote`
- Result: 434 validated rules with 100% value coverage (0 Nones)

### Feb 18, 2026 — Open Discovery Improvements
- Improved `SYSTEM_PROMPT_OPEN_EXTRACTION` — focus on network behavior, skip irrelevant content
- Added explicit conflict resolution (`resolve_conflicts` in `align_rules.py`)
- Fixed Claude JSON parsing (markdown code-block stripping in `llm_providers.py`)
- Increased `max_tokens` for extraction (8192) and aggregation (16000)
- Made fuzzer rule consumption generic (`fuzzing_agent.py`, `spec_loader.py`)

### Earlier — Open Discovery Foundation
- Created `prompts_open.py` with micro-format for free rule discovery
- Created `align_rules.py` for semantic alignment across models
- Modified `run_multimodel.py` with `--mode open|strict`
- Modified `export_validated.py` with alignment-based export
- Modified `compare_extractions.py` for format auto-detection

### Earlier — Project Reorganization
- Reorganized directory structure (logs/, archive/, docs/, scripts/, tests/)
- Created context/ documentation directory
- Set up GitHub repository with proper .gitignore
- Created orphan branch for clean history
