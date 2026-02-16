# boofuzz Baseline - Industry-Standard Protocol Fuzzer for AFDX

This directory contains a **boofuzz-style baseline fuzzer** for fair comparison with the LLM-guided fuzzer.

## Overview

Unlike the LLM-guided fuzzer (intelligent) or random baseline (random), boofuzz represents the **industry-standard approach** to protocol fuzzing:

| Approach | Selection Strategy | Learning |
|----------|-------------------|----------|
| **LLM-Guided** | Intelligent, context-aware | Yes - adapts based on results |
| **boofuzz Baseline** | Deterministic, exhaustive | No - tests all violations in order |
| **Random Baseline** | Random selection | No - purely random |

## Key Features

1. **Same Test Cases**: Uses `configs/test_cases.json` - identical to LLM fuzzer
2. **Semantic Violations**: Tests protocol rule violations, NOT random bit flips
3. **Deterministic**: Same order every run for reproducibility
4. **Exhaustive**: Tests ALL violations in sequence
5. **Fair Comparison**: Same frame generator, simulator, and metrics

## Directory Structure

```
boofuzz_baseline/
├── __init__.py                    # Package init
├── README.md                      # This file
├── main.py                        # Main fuzzing entry point
├── afdx_protocol.py              # AFDX packet definition
├── boofuzz_strategy_generator.py # Deterministic strategy selection
├── data/                          # Data files
│   └── iteration_history.jsonl   # Fuzzing history
└── output/                        # Output files
    ├── iteration_XXX_test.json   # Generated test inputs
    └── boofuzz_summary_*.json    # Run summaries
```

## Usage

### Quick Start

```bash
# Run with defaults (50 iterations, mock simulator)
python3 boofuzz_baseline/main.py

# Run with custom iteration count
python3 boofuzz_baseline/main.py --max-iterations 100

# Specify VLs to test
python3 boofuzz_baseline/main.py --vls 1001 1002 2001 2002

# Use real ns-3 simulator
python3 boofuzz_baseline/main.py --use-real-simulator
```

### Compare with Other Fuzzers

```bash
# Run all three fuzzers and compare
python3 evaluation/run_full_evaluation.py --iterations 50

# Only run comparison (if fuzzers already ran)
python3 evaluation/three_way_comparison.py
```

## How It Works

### 1. Load Test Cases
```python
from boofuzz_baseline.afdx_protocol import AFDXTestCaseGenerator

generator = AFDXTestCaseGenerator()
print(f"Total violations: {generator.get_violation_count()}")  # ~98 violations
```

### 2. Deterministic Selection
```python
from boofuzz_baseline.boofuzz_strategy_generator import BoofuzzStrategyGenerator

strategy_gen = BoofuzzStrategyGenerator()

# Always returns next violation in order
strategy = strategy_gen.plan_next_iteration(
    history=None,  # Ignored - no learning
    iteration=0,
    system_config={'available_vls': [1001, 1002]}
)
```

### 3. Generate Frames
Uses the same `TestGenerator` as LLM fuzzer:
```python
from llm_fuzzer.core.test_generator import TestGenerator

generator = TestGenerator()
frames = generator.generate_test_inputs(strategy)
```

## Comparison with Real boofuzz

This baseline is **NOT** standard boofuzz (random mutations). Instead:

| Feature | Standard boofuzz | This Baseline |
|---------|-----------------|---------------|
| Mutations | Random (bit flip, format string, etc.) | Semantic (spec violations) |
| Test Cases | Auto-generated | From `test_cases.json` |
| Protocol Knowledge | Define structure | Uses AFDX rules |
| Comparison | Unfair (apples vs oranges) | Fair (same test cases) |

**Why?** Standard boofuzz mutations (bit flips) are not meaningful for AFDX. A random byte change is unlikely to create a valid-but-violating BAG value. Our baseline uses the SAME semantic violations, ensuring fair comparison.

## Test Cases Covered

The baseline tests all violations from `configs/test_cases.json`:

| Rule Category | Violation Types |
|---------------|-----------------|
| BAG | below_min, above_max, not_in_list, negative |
| Sequence Number | out_of_order, duplicate, wraparound |
| Frame Size | undersized, oversized |
| IP Header | invalid_version, invalid_address |
| Virtual Link | invalid_id, invalid_config |
| Priority | invalid_level |
| ... | ... |

Total: **~98 unique violations**

## Output Format

### History (JSONL)
```json
{
  "iteration": 0,
  "target_vl": 1001,
  "violation_id": "bag_TC0",
  "violation_type": "below_min",
  "reward": 0.65,
  "policing_rate": 80.0,
  "bugs_found": 1
}
```

### Summary (JSON)
```json
{
  "fuzzer_type": "boofuzz",
  "total_iterations": 50,
  "coverage_percent": 51.0,
  "reward_mean": 0.55,
  "total_bugs_found": 23
}
```

## Expected Results

Based on the deterministic nature of boofuzz:

| Metric | Expected |
|--------|----------|
| Coverage | 100% (if iterations >= violation count) |
| Reproducibility | 100% (same results every run) |
| Learning | 0% (no adaptation) |
| vs LLM | Lower efficiency (tests everything, not smart selection) |
| vs Random | Higher coverage (systematic vs random) |

## Metrics Compared

When comparing with LLM and Random fuzzers:

1. **Reward Statistics**: Mean, median, max, std
2. **Coverage**: VLs, rules, mutation types tested
3. **Efficiency**: Policing rate, bugs found, bugs per iteration
4. **Time**: First bug found, total duration
5. **Statistical Significance**: Mann-Whitney U test

## Requirements

```bash
# Same as LLM fuzzer
pip install pandas numpy
```

## Authors

AI Fuzzing Research Team

## License

Research project - see main repository for license

