# Components Reference

Detailed description of every project component, its files, inputs, outputs, and dependencies.

---

## 1. AFDX Simulator (`examples/AFDX_V3/`)

**Language:** C++ (ns-3 module)

### Files
| File | Purpose |
|------|---------|
| `model/afdx-switch.cc/h` | AFDX switch with BAG policing, filtering, scheduling |
| `model/afdx-end-system.cc/h` | End system with traffic shaping and redundancy management |
| `model/afdx-virtual-link.cc/h` | Virtual Link abstraction (unidirectional logical channels) |
| `model/afdx-frame.cc/h` | AFDX frame structure (Ethernet + IP/UDP + SN) |
| `model/afdx-traffic-generator.cc/h` | Traffic generator reading `mutations.json` for fuzzing |
| `simulations/afdx-demo.cc` | Main simulation entry point, reads config and mutations |
| `helper/afdx-helper.cc/h` | ns-3 helper for setting up topology |
| `config/virtual_links.csv` | VL configuration (IDs, BAG, Lmax, source, destination) |
| `mutations.json` | Mutation input consumed by traffic generator |

### Inputs
- `config/virtual_links.csv` — defines network topology
- `mutations.json` — test frame definitions from the fuzzer

### Outputs
- `output/csv/AFDX-LOG-OUTPUT.csv` — frame-level log (sent, received, dropped, policing events)
- `output/pcap/` — packet captures

### Build
```bash
./ns3 configure --enable-examples
./ns3 build afdx-demo
```

---

## 2. LLM-Guided Fuzzer (`llm_fuzzer/`)

**Language:** Python

### Core Components (`core/`)

#### Strategy Planner (`core/strategy_planner.py`)
- **What:** Uses GPT-5 to decide the next test strategy
- **Input:** Iteration history (past strategies + rewards), available VLs, spec rules
- **Output:** Strategy dict: `{target_vl, mutation_type, test_cases, strategy, reasoning, ...}`
- **Dependencies:** OpenAI API, `spec_loader`, `test_case_loader`

#### Test Generator (`core/test_generator.py`)
- **What:** Converts LLM strategy into concrete AFDX frames
- **Input:** Strategy dict from planner
- **Output:** Test inputs dict: `{frames, vl_id, metadata}`
- **Modes:** Predefined (from test_cases.json) or Custom (LLM-specified mutations)
- **Dependencies:** `test_case_loader`, `mutation_parser`

#### Feedback Analyzer (`core/feedback_analyzer.py`)
- **What:** Analyzes simulator output, computes reward
- **Input:** Simulator log content, strategy, history
- **Output:** `{reward, metrics, analysis}`
- **Dependencies:** `log_parser`, `reward_calculator`

#### Reward Calculator (`core/reward_calculator.py`)
- **What:** Computes reward score using paper formula
- **Formula:** `R = A1·r_policing - A2·r_forward + A3·r_novelty - A4·r_repeat + bonus`
- **Input:** Metrics dict, history DataFrame, strategy
- **Output:** Float reward score

#### Mutation Parser (`core/mutation_parser.py`)
- **What:** Parses LLM natural language mutations into concrete values
- **Input:** String like "Set BAG to 5ms"
- **Output:** Parsed parameters `{bag_value: 5, ...}`

### Utilities (`utils/`)

| File | Purpose |
|------|---------|
| `simulator_runner.py` | Executes ns-3 simulator via subprocess, writes mutations.json, collects output |
| `log_parser.py` | Parses simulator CSV output into metrics dict |
| `spec_loader.py` | Loads `configs/spec_rules.json` |
| `test_case_loader.py` | Loads `configs/test_cases.json` |

### Data Files (`data/`)
- `seed_frames.json` — initial seed frames for test generation
- `iteration_history.jsonl` — log of all iterations (strategy + reward per iteration)

### Entry Point
```bash
python3 llm_fuzzer/main.py --max-iterations 50
```

---

## 3. Specification Extraction (`spec_extraction/`)

**Language:** Python

### Two Extraction Modes

#### Open Mode (recommended, `--mode open`)
LLMs freely discover and categorize rules — no predefined schema.
```
PDF → run_multimodel.py --mode open (GPT + Claude + Gemini)
   → Each LLM outputs a list of rules it discovered
   → align_rules.py (semantic matching across models)
   → export_validated.py --mode open → configs/spec_rules.json
                                      → configs/test_cases.json
```

#### Strict Mode (legacy, `--mode strict`)
LLMs fill a predefined JSON schema — 12 hardcoded categories.
```
PDF → run_multimodel.py --mode strict
   → compare_extractions.py (key-based comparison)
   → arbitrate_conflicts.py (judge resolves)
   → export_validated.py --mode strict → configs/spec_rules.json
```

### Files
| File | Purpose |
|------|---------|
| `extract_rules.py` | Single-model rule extraction from PDF |
| `extract_test_cases.py` | LLM-based test case generation per rule |
| `run_multimodel.py` | Parallel multi-provider extraction (supports `--mode open\|strict`) |
| **`prompts_open.py`** | **Open-discovery prompts (LLMs freely discover rules)** |
| **`align_rules.py`** | **Semantic alignment of rules across models** |
| `compare_extractions.py` | Cross-model comparison (legacy strict + auto-detect) |
| `arbitrate_conflicts.py` | Conflict resolution via judge LLM (legacy strict) |
| `export_validated.py` | Export final validated outputs (supports both modes) |
| `llm_client.py` | OpenAI API wrapper |
| `llm_providers.py` | Multi-provider abstraction (GPT/Claude/Gemini) |
| `pdf_utils.py` | PDF text extraction utilities |
| `prompts.py` | Discovery + extraction prompts (Phase 1/2) |
| `prompts_strict.py` | Strict schema prompts (legacy) |
| `test_case_prompts.py` | Test case generation prompts |
| `validate_test_cases.py` | Test case validation logic |

### Inputs
- `configs/ARINC_664P7.pdf` — the ARINC 664 Part 7 specification

### Outputs
- `configs/spec_rules.json` — extracted and validated protocol rules
- `configs/spec_rules_validated.json` — rules with confidence metadata
- `configs/test_cases.json` — violation test cases
- `multimodel_output/` — per-provider extraction results
- `alignment_results.json` — semantic alignment output (open mode)

---

## 4. Random Baseline (`random_baseline/`)

**Language:** Python

### Files
| File | Purpose |
|------|---------|
| `main.py` | Random fuzzing loop (same structure as LLM fuzzer) |
| `random_strategy_generator.py` | Random strategy selection (uniform random VL + mutation) |

### Key Difference from LLM Fuzzer
Replaces `LLMStrategyPlanner` with random selection. Uses the same `TestGenerator`, `SimulatorRunner`, and `FeedbackAnalyzer` from `llm_fuzzer/` for fair comparison.

---

## 5. Boofuzz Baseline (`boofuzz_baseline/`)

**Language:** Python

### Files
| File | Purpose |
|------|---------|
| `main.py` | Systematic fuzzing loop |
| `afdx_protocol.py` | AFDX protocol definition for boofuzz framework |
| `boofuzz_strategy_generator.py` | Deterministic exhaustive strategy — tests all violations in order |

### Key Difference
Systematic, exhaustive testing of all violations in predefined order. No learning, no randomness. Useful as a "complete coverage" baseline.

---

## 6. Evaluation (`evaluation/`)

**Language:** Python

### Files
| File | Purpose |
|------|---------|
| `three_way_comparison.py` | LLM vs Random vs Boofuzz comparison |
| `run_full_evaluation.py` | Automated full pipeline (run all 3 fuzzers + compare) |
| `run_comparison.py` | Two-way comparison (LLM vs Random) |
| `comprehensive_analysis.py` | Deep statistical analysis |
| `analysis_without_llm.py` | Analysis using only random data (no API needed) |
| `generate_latex_tables.py` | Generate LaTeX tables for paper |

### Inputs
- `llm_fuzzer/data/iteration_history.jsonl`
- `random_baseline/data/iteration_history.jsonl`
- `boofuzz_baseline/data/iteration_history.jsonl`

### Outputs
- `evaluation/results/` — comparison reports, JSON data, LaTeX tables

---

## 7. Tools (`tools/`)

| File | Purpose |
|------|---------|
| `ai_fuzzer_agent.py` | Standalone AI fuzzer agent (reads meta.csv, proposes mutations) |
| `random_fuzzer_baseline.py` | Standalone random baseline (alternative implementation) |

---

## 8. Configuration (`configs/`)

| File | Description |
|------|-------------|
| `spec_rules.json` | Protocol rules (10 rules covering BAG, frame structure, SN, etc.) |
| `spec_rules_validated.json` | Rules with cross-model validation metadata and confidence scores |
| `test_cases.json` | 96 violation test cases organized by parameter type |
| `test_cases_validation.json` | Validation report for test cases |
| `validation_report.json` | Multi-model validation summary |
| `spec_rules_old.json` | Backup of older rule extraction |
| `ARINC_664P7.pdf` | ARINC 664 Part 7 specification document |
