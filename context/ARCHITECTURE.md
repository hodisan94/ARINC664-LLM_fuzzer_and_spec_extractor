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
├── extensions/                # C++ fuzzing extensions
│   └── fuzzing/               #   feedback-logger.h, violation-checker.h, payload-provider.h
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
│   ├── extract_rules.py       #   Single-model rule extraction from PDF
│   ├── extract_test_cases.py  #   Test case generation from rules
│   ├── llm_client.py          #   OpenAI API client
│   ├── llm_providers.py       #   Multi-provider LLM (GPT/Claude/Gemini)
│   ├── run_multimodel.py      #   Multi-model extraction (--mode open|strict)
│   ├── prompts_open.py        #   Open-discovery prompts (NEW)
│   ├── align_rules.py         #   Semantic rule alignment across models (NEW)
│   ├── compare_extractions.py #   Cross-model comparison (auto-detects format)
│   ├── arbitrate_conflicts.py #   Conflict resolution with judge LLM (legacy)
│   ├── export_validated.py    #   Export final validated rules (both modes)
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
│   ├── three_way_comparison.py    # LLM vs Random vs Boofuzz comparison
│   ├── run_full_evaluation.py     # Full automated evaluation pipeline
│   ├── run_comparison.py          # Two-way comparison (LLM vs Random)
│   ├── comprehensive_analysis.py  # Deep analysis
│   ├── analysis_without_llm.py    # Analysis using only random data
│   └── generate_latex_tables.py   # LaTeX table generation for paper
│
├── configs/                   # Configuration & Data Files
│   ├── spec_rules.json            # Extracted protocol rules
│   ├── spec_rules_validated.json  # Cross-validated rules
│   ├── test_cases.json            # Violation test cases
│   ├── ARINC_664P7.pdf            # ARINC 664 Part 7 specification
│   └── validation_report.json     # Validation metadata
│
├── tools/                     # Standalone Tools
│   ├── ai_fuzzer_agent.py         # AI-driven fuzzer agent
│   └── random_fuzzer_baseline.py  # Standalone random baseline
│
├── scripts/                   # Shell Scripts
│   ├── run_experiments.sh         # Full experiment runner
│   ├── run_e2e.sh                 # End-to-end test
│   ├── run_ai_fuzzer.sh           # AI fuzzer launcher
│   └── QUICK_REWARD_FIX.sh        # Reward recomputation fix
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
                    │  GPT ──┐  Free discovery     │
                    │  Claude─┼─► Semantic Align   │
                    │  Gemini─┘  + Verify unique   │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │  spec_rules.json             │
                    │  test_cases.json              │
                    │  (configs/)                   │
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
- `configs/spec_rules.json` — protocol rules loaded by `spec_loader.py`
- `configs/test_cases.json` — violation test cases loaded by `test_case_loader.py`

### Fuzzer → Evaluation Interface
- `llm_fuzzer/data/iteration_history.jsonl` — LLM fuzzer results
- `random_baseline/data/iteration_history.jsonl` — Random baseline results
- `boofuzz_baseline/data/iteration_history.jsonl` — Boofuzz baseline results
