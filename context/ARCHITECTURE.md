# Project Architecture

## Directory Structure

```
ns-3/
│
├── examples/AFDX_V3/          # AFDX Simulator (C++, ns-3 module)
│   ├── model/                 #   Core AFDX models
│   ├── simulations/           #   Simulation entry points
│   ├── helper/                #   ns-3 helper classes
│   ├── config/                #   VL configuration (CSV)
│   ├── test/                  #   C++ unit tests
│   ├── output/                #   Simulation outputs (CSV, PCAP)
│   └── mutations.json         #   Mutation input from fuzzer
│
├── llm_fuzzer/                # LLM-Guided Fuzzer (Python)
│   ├── main.py                #   Main fuzzing loop
│   ├── core/                  #   Core components
│   │   ├── strategy_planner.py    # LLM strategy planning
│   │   ├── test_generator.py      # Test frame generation
│   │   ├── feedback_analyzer.py   # Result analysis
│   │   ├── reward_calculator.py   # Reward computation
│   │   └── mutation_parser.py     # NL mutation parsing
│   ├── utils/                 #   Utilities
│   │   ├── simulator_runner.py    # ns-3 execution wrapper
│   │   ├── log_parser.py         # Log parsing
│   │   ├── spec_loader.py        # Spec rules loader
│   │   └── test_case_loader.py   # Test cases loader
│   ├── prompts/               #   LLM prompt templates
│   ├── data/                  #   Runtime data (seed_frames, iteration history)
│   └── tests/                 #   Unit tests for fuzzer
│
├── spec_extraction/           # Specification Extraction Pipeline (Python)
│   ├── extract_test_cases.py  #   Test case generation from rules
│   ├── llm_providers.py       #   Multi-provider LLM (GPT/Claude/Mistral)
│   ├── run_multimodel.py      #   Multi-model open-discovery extraction
│   ├── prompts_open.py        #   Open-discovery prompts
│   ├── align_rules.py         #   Semantic rule alignment across models
│   ├── filter_rules.py        #   Rule filtering by simulator relevance
│   ├── export_validated.py    #   Export final validated rules
│   └── multimodel_output/     #   Per-provider extraction results
│
├── random_baseline/           # Random Fuzzer Baseline (Python)
│   ├── main.py                #   Random fuzzing loop
│   └── random_strategy_generator.py
│
├── boofuzz_baseline/          # Boofuzz Fuzzer Baseline (Python)
│   ├── main.py                #   Systematic fuzzing loop
│   ├── afdx_protocol.py       #   AFDX protocol definition for boofuzz
│   └── boofuzz_strategy_generator.py
│
├── evaluation/                # Evaluation & Comparison (Python)
│   ├── compute_metrics.py         # Coverage, diversity, and comparison metrics
│   ├── compute_bdr.py             # Injected-bug detection metrics
│   ├── compute_rule_correctness.py
│   ├── compute_rule_completeness.py
│   └── generate_latex_tables.py   # LaTeX table generation for paper
│
├── configs/                   # Configuration & Data Files
│   ├── spec_rules.json            # Full extracted rules
│   ├── spec_rules_filtered.json   # Simulator-relevant rules
│   ├── spec_rules_validated.json  # Cross-validated rules (full metadata)
│   ├── test_cases.json            # Violation test cases
│   └── validation_report.json     # Validation metadata
│
├── tests/                     # Integration Tests
│   ├── test_hybrid_freedom.py     # Hybrid approach test
│   ├── test_paper_alignment.py    # Paper alignment verification
│   └── test_smart_sequences.py    # Smart sequence test
│
├── docs/                      # Documentation
│   ├── paper/                     # Academic paper files
│   └── presentation/              # Presentation materials
│
├── context/                   # Project Context (you are here)
├── archive/                   # Old summaries and reports
├── logs/                      # Log files from past runs
└── .env                       # API keys (not committed)
```

## Data Flow Diagram

```
                    ┌─────────────────────────────┐
                    │   ARINC 664 Part 7 PDF      │
                    │   (configs/ARINC_664P7.pdf)  │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │  Spec Extraction Pipeline    │
                    │  (spec_extraction/)          │
                    │                              │
                    │  1. GPT ──┐  Free discovery  │
                    │     Claude─┘  (open prompts) │
                    │                              │
                    │  2. Semantic Alignment        │
                    │     (match rules by meaning)  │
                    │                              │
                    │  3. Conflict Resolution       │
                    │     (judge consults spec)     │
                    │                              │
                    │  4. Unique Verification       │
                    │     (judge confirms/rejects)  │
                    │                              │
                    │  5. Enriched Export            │
                    │     (values + test_hint + src) │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │  spec_rules.json (434 rules)  │
                    │  spec_rules_validated.json    │
                    │  validation_report.json       │
                    │  (configs/)                   │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │  Rule Filter (DONE)           │
                    │  (filter_rules.py)            │
                    │                              │
                    │  LLM analysis of simulator    │
                    │  → 12 relevant domains        │
                    │  → 11 excluded domains        │
                    │                              │
                    │  431 → 236 rules (54.8%)      │
                    │  → spec_rules_filtered.json   │
                    └──────────────┬──────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
          ▼                        ▼                        ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  LLM Fuzzer     │    │  Random Fuzzer  │    │  Boofuzz Fuzzer │
│  (llm_fuzzer/)  │    │(random_baseline)│    │(boofuzz_baseline)│
│                 │    │                 │    │                 │
│ ┌─────────────┐ │    │ Random strategy │    │ Exhaustive test │
│ │ LLM Planner │ │    │ selection       │    │ all violations  │
│ └──────┬──────┘ │    │                 │    │ in order        │
│        │        │    │                 │    │                 │
│ ┌──────▼──────┐ │    │                 │    │                 │
│ │  Test Gen   │ │    │                 │    │                 │
│ └──────┬──────┘ │    │                 │    │                 │
│        │        │    │                 │    │                 │
│ ┌──────▼──────┐ │    │ ┌─────────────┐ │    │ ┌─────────────┐ │
│ │ Sim Runner  │ │    │ │ Sim Runner  │ │    │ │ Sim Runner  │ │
│ └──────┬──────┘ │    │ └─────────────┘ │    │ └─────────────┘ │
│        │        │    │                 │    │                 │
│ ┌──────▼──────┐ │    │                 │    │                 │
│ │  Feedback   │ │    │                 │    │                 │
│ │  Analyzer   │ │    │                 │    │                 │
│ └──────┬──────┘ │    │                 │    │                 │
│        │        │    │                 │    │                 │
│     (loop)      │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
          │                        │                        │
          └────────────────────────┼────────────────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │  Evaluation & Comparison     │
                    │  (evaluation/)               │
                    │                              │
                    │  Three-way comparison         │
                    │  LaTeX tables for paper       │
                    │  Statistical analysis         │
                    └─────────────────────────────┘
```

## Key Interfaces Between Components

### Simulator ↔ Fuzzer Interface
- **Input**: `examples/AFDX_V3/mutations.json` — written by `simulator_runner.py`
- **Output**: `examples/AFDX_V3/output/csv/AFDX-LOG-OUTPUT.csv` — read by `log_parser.py`

### Spec Extraction → Fuzzer Interface
- `configs/spec_rules.json` — 434 validated protocol rules (full extraction)
- `configs/spec_rules_filtered.json` — 236 simulator-relevant rules loaded by `spec_loader.py`
- `configs/test_cases.json` — violation test cases loaded by `test_case_loader.py`
- `configs/spec_rules_validated.json` — full rules with confidence metadata (for analysis)
- `configs/validation_report.json` — extraction quality summary (for paper)

### Fuzzer → Evaluation Interface
- `llm_fuzzer/data/iteration_history.jsonl` — LLM fuzzer results
- `random_baseline/data/iteration_history.jsonl` — Random baseline results
- `boofuzz_baseline/data/iteration_history.jsonl` — Boofuzz baseline results
