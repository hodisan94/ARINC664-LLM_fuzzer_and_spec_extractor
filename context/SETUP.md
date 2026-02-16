# Setup & Running Guide

## Prerequisites

### System Requirements
- Linux (tested on Ubuntu/WSL2)
- C++ compiler (g++ 9+)
- CMake 3.16+
- Python 3.8+

### ns-3 Setup
The project is built on top of ns-3. The ns-3 installation is already in place at the project root.

### Python Dependencies
```bash
pip install openai anthropic google-generativeai pandas numpy boofuzz PyPDF2
```

### API Keys
Create a `.env` file in the project root:
```bash
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AI...
```

Or export them:
```bash
export OPENAI_API_KEY="sk-..."
```

---

## Building the Simulator

```bash
cd /home/hodisan1994/ns-3-reset/ns-3

# Configure ns-3 with examples enabled
./ns3 configure --enable-examples

# Build the AFDX demo
./ns3 build afdx-demo
```

The built binary will be at: `build/examples/AFDX_V3/ns3-dev-afdx-demo-debug`

### Verify Build
```bash
timeout 3 ./ns3 run afdx-demo --no-build 2>&1 | head -20
```

---

## Running Components

All commands should be run from the project root: `/home/hodisan1994/ns-3-reset/ns-3`

### 1. Specification Extraction

#### Open Discovery Mode (recommended)
```bash
# Step 1: Extract rules with multiple LLMs (each discovers freely)
python3 spec_extraction/run_multimodel.py --pdf configs/ARINC_664P7.pdf --mode open

# Step 2: Semantically align rules across models
python3 spec_extraction/align_rules.py

# Step 3 (optional): Verify rules found by only one model
python3 spec_extraction/align_rules.py --verify-unique --pdf configs/ARINC_664P7.pdf

# Step 4: Export validated rules
python3 spec_extraction/export_validated.py --mode open
```

#### Legacy Strict Mode
```bash
python3 spec_extraction/run_multimodel.py --pdf configs/ARINC_664P7.pdf --mode strict
python3 spec_extraction/compare_extractions.py
python3 spec_extraction/arbitrate_conflicts.py --pdf configs/ARINC_664P7.pdf
python3 spec_extraction/export_validated.py --mode strict
```

#### Single-Model Extraction (quick test)
```bash
python3 spec_extraction/extract_rules.py
```

### 2. LLM Fuzzer
```bash
python3 llm_fuzzer/main.py --max-iterations 50
```

Options:
- `--max-iterations N` — number of fuzzing iterations (default: 50)

### 3. Random Baseline
```bash
python3 random_baseline/main.py --max-iterations 50
```

### 4. Boofuzz Baseline
```bash
python3 boofuzz_baseline/main.py --max-iterations 50
```

### 5. Evaluation

#### Full Automated Evaluation (runs all 3 fuzzers + comparison)
```bash
python3 evaluation/run_full_evaluation.py
```

#### Three-Way Comparison (after running all fuzzers)
```bash
python3 evaluation/three_way_comparison.py
```

#### Generate LaTeX Tables
```bash
python3 evaluation/generate_latex_tables.py
```

#### Analysis Without LLM (no API key needed)
```bash
python3 evaluation/analysis_without_llm.py
```

---

## Shell Scripts

Located in `scripts/`:

| Script | Purpose | Usage |
|--------|---------|-------|
| `run_experiments.sh` | Full experiment runner | `bash scripts/run_experiments.sh` |
| `run_e2e.sh` | End-to-end test | `bash scripts/run_e2e.sh` |
| `run_ai_fuzzer.sh` | AI fuzzer launcher | `bash scripts/run_ai_fuzzer.sh` |
| `QUICK_REWARD_FIX.sh` | Recompute rewards | `bash scripts/QUICK_REWARD_FIX.sh` |

---

## Directory Reference

| Directory | What's There |
|-----------|-------------|
| `configs/` | Protocol rules, test cases, spec PDF |
| `llm_fuzzer/data/` | Seed frames, iteration history |
| `random_baseline/data/` | Random baseline iteration history |
| `boofuzz_baseline/data/` | Boofuzz baseline iteration history |
| `evaluation/results/` | Comparison reports, data, LaTeX |
| `examples/AFDX_V3/output/` | Simulator outputs (CSV, PCAP) |
| `logs/` | Past run logs |
| `docs/` | Paper and presentation materials |
| `context/` | This documentation |
| `archive/` | Old summaries and reports |
