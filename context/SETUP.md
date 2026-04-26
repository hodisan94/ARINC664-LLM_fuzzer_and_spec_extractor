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
pip install openai anthropic pandas numpy boofuzz PyPDF2 python-dotenv
```

It's recommended to use a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
pip install openai anthropic pandas numpy boofuzz PyPDF2 python-dotenv
```

### API Keys
Create a `.env` file in the project root (loaded automatically by `python-dotenv`):
```bash
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
MISTRAL_API_KEY=...
```

The code checks for both `ANTHROPIC_API_KEY` and `CLAUDE_API_KEY`.
At least 2 providers are needed for cross-validation in multi-model mode.

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

#### Open Discovery Pipeline
```bash
# Step 1: Extract rules with multiple LLMs (each discovers freely)
python3 spec_extraction/run_multimodel.py \
    --pdf configs/ARINC_664P7.pdf \
    --providers openai anthropic mistral

# Step 2: Align + resolve conflicts + verify unique (all-in-one)
python3 spec_extraction/align_rules.py \
    --input spec_extraction/multimodel_output \
    --pdf configs/ARINC_664P7.pdf \
    --full \
    --judge openai

# Step 3: Export validated rules (enriched with original extraction data)
python3 spec_extraction/export_validated.py \
    --mode open \
    --extraction-dir spec_extraction/multimodel_output \
    --output-dir configs
```

**Note:** Step 1 takes ~35 minutes (API calls per PDF chunk per provider).
Step 2 takes ~25 minutes (alignment batches + 464 verification calls).
Step 3 is instant.

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
| `context/` | This documentation |
