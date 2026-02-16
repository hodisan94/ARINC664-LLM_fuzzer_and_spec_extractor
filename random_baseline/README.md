# Random Baseline Fuzzer

This directory contains a **purely random fuzzer** that serves as a fair baseline for comparing the LLM-guided fuzzer's performance.

## Key Design Principle: Fair Comparison

The random baseline uses **THE EXACT SAME infrastructure** as the LLM-guided fuzzer:

| Component | LLM Fuzzer | Random Baseline | Status |
|-----------|------------|-----------------|--------|
| Feedback Analyzer | `llm_fuzzer.core.feedback_analyzer` | Same | Identical |
| Reward Calculator | `llm_fuzzer.core.reward_calculator` | Same | Identical |
| Test Generator | `llm_fuzzer.core.test_generator` | Same | Identical |
| Simulator Runner | `llm_fuzzer.utils.simulator_runner` | Same | Identical |
| Strategy Planner | `llm_fuzzer.core.strategy_planner` (LLM) | `random_baseline.random_strategy_generator` (Random) | **ONLY DIFFERENCE** |

**This ensures the ONLY difference is:**
- LLM intelligence vs. random selection

**Everything else is identical:**
- Same protocol rules
- Same test cases
- Same simulator
- Same reward function
- Same analysis tools

## How It Works

### Random Strategy Generator

Replaces `LLMStrategyPlanner` with `RandomStrategyGenerator`:

```python
# LLM Fuzzer (intelligent decisions based on history, rules, etc.)
strategy = llm_planner.plan_next_iteration(history, iteration, config)

# Random Baseline (purely random decisions)
strategy = random_generator.plan_next_iteration(history, iteration, config)
```

### What Gets Randomized

**All decisions are random:**

1. **Target VL**: Random choice from available VLs
   ```python
   target_vl = random.choice([1001, 1002, 2001, 2002, ...])
   ```

2. **Protocol Rule**: Random choice from rules that have test cases
   ```python
   protocol_rule = random.choice(["bag", "sequence_numbers", ...])
   ```

3. **Test Mode**: Random choice between predefined and custom
   ```python
   test_mode = random.choice(["predefined", "custom"])
   ```

4. **Test Cases** (if predefined mode): Random selection of 1-3 test cases
   ```python
   num_cases = random.randint(1, 3)
   test_cases = random.sample(available_cases, num_cases)
   ```

5. **Custom Mutation** (if custom mode): Random mutation description
   ```python
   custom_mutation = random.choice([
       "Set bag to random invalid value",
       "Test extreme boundary",
       ...
   ])
   ```

6. **Strategy Type**: Random choice of strategy
   ```python
   strategy = random.choice(["conformance", "edge-case", "adversarial"])
   ```

### What Does NOT Happen

**No learning or adaptation:**
- Does not read or learn from history
- Does not adapt based on rewards
- Does not explore/exploit intelligently
- Does not reason about choices

**Just pure randomness.**

## Usage

### Basic Run

```bash
# Run with defaults (50 iterations, no seed)
python3 random_baseline/main.py
```

### With Random Seed (Reproducible)

```bash
# Run with seed for reproducibility
python3 random_baseline/main.py --seed 42
```

### Custom Iterations

```bash
# Run 100 iterations
python3 random_baseline/main.py --max-iterations 100
```

### Specify VLs

```bash
# Test only specific VLs
python3 random_baseline/main.py --vls 1001 1002 2001 2002
```

### Full Example

```bash
# 50 iterations, seed 42, custom output dir
python3 random_baseline/main.py \
  --max-iterations 50 \
  --seed 42 \
  --output-dir random_baseline/output/run1
```

## Output Files

### Iteration History

**File:** `random_baseline/data/iteration_history.jsonl`

JSONL format (one JSON object per line):
```json
{"iteration": 0, "target_vl": 1001, "protocol_rule": "bag", "reward": 1.23, ...}
{"iteration": 1, "target_vl": 2002, "protocol_rule": "sequence_numbers", "reward": 0.98, ...}
```

### Test Inputs

**Directory:** `random_baseline/output/`

One file per iteration:
```
iteration_000_test.json
iteration_001_test.json
iteration_002_test.json
...
```

### Final Report

**File:** `random_baseline/output/random_fuzzing_report_YYYYMMDD_HHMMSS.txt`

Contains:
- Total iterations
- Success/failure counts
- Reward statistics (mean, max, min, std)
- Bugs found
- VL coverage
- Rule coverage
- Strategy distribution
- Test mode distribution
- Top 5 iterations by reward

### CSV Export

**File:** `random_baseline/output/random_history_YYYYMMDD_HHMMSS.csv`

Full history exported to CSV for analysis with pandas, Excel, etc.

## Comparison with LLM Fuzzer

### Running Both Fuzzers

```bash
# Run LLM fuzzer (50 iterations)
python3 llm_fuzzer/main.py --max-iterations 50

# Run random baseline (50 iterations, same seed)
python3 random_baseline/main.py --max-iterations 50 --seed 42
```

### Metrics to Compare

1. **Bugs Found**
   - Total count
   - Time to first bug
   - Types of bugs

2. **Coverage**
   - VL coverage (% of VLs tested)
   - Rule coverage (% of rules tested)
   - Diversity of test cases

3. **Reward Trends**
   - Average reward
   - Max reward
   - Reward over time (learning curve)

4. **Efficiency**
   - Bugs per iteration
   - Coverage per iteration
   - Time to discover bugs

### Expected Outcomes

**LLM Fuzzer should be better at:**
- Finding bugs faster (time to first bug)
- Achieving higher average reward
- Exploring systematically (better coverage)
- Learning from history (improving over time)
- Exploiting promising areas (high-reward VLs/rules)

**Random Baseline should:**
- Have more variance (no consistency)
- Miss promising areas (no exploitation)
- Not improve over time (no learning)
- Have lower average reward
- Take longer to find bugs (if at all)

### Statistical Tests

To prove LLM fuzzer is significantly better:

1. **Mann-Whitney U Test** (rewards)
   ```python
   from scipy.stats import mannwhitneyu
   statistic, p_value = mannwhitneyu(llm_rewards, random_rewards)
   ```

2. **Time-to-Event Analysis** (bugs)
   ```python
   # Kaplan-Meier curves for time to first bug
   ```

3. **Coverage Comparison**
   ```python
   llm_coverage = len(llm_vls_tested) / total_vls
   random_coverage = len(random_vls_tested) / total_vls
   ```

## Files

```
random_baseline/
├── __init__.py                    # Package init
├── random_strategy_generator.py   # Random strategy generator
├── main.py                        # Main loop (entry point)
├── README.md                      # This file
├── data/                          # Data directory (created at runtime)
│   └── iteration_history.jsonl    # Iteration history
└── output/                        # Output directory (created at runtime)
    ├── iteration_XXX_test.json    # Test inputs per iteration
    ├── random_fuzzing_report_*.txt # Final report
    └── random_history_*.csv        # CSV export
```

## Design Rationale

### Why Same Infrastructure?

Using the same infrastructure ensures:
1. **Fair comparison** - only strategy differs
2. **No implementation bias** - same bugs/features in both
3. **Direct comparison** - same metrics, same format
4. **Scientific validity** - controlled experiment

### Why Random?

Random baseline is the standard in fuzzing research:
- AFL vs. random
- libFuzzer vs. random
- Grammar-based fuzzers vs. random

It proves the intelligent approach is better than "just trying random things."

### Why Not Just Compare with Existing `tools/random_fuzzer_baseline.py`?

The existing implementation:
- Uses different infrastructure (mutations.json, bitflip, etc.)
- Uses different simulator interface
- Uses different metrics
- Not fair comparison

This new random baseline:
- **Identical infrastructure**
- **Only difference: random vs. LLM**
- **Fair and scientific**

## Development

### Testing Random Strategy Generator

```bash
python3 random_baseline/random_strategy_generator.py
```

Output:
```
======================================================================
RANDOM STRATEGY GENERATOR TEST
======================================================================

Generating 5 random strategies:

Iteration 0:
  VL: 1001
  Rule: bag
  Mode: predefined
  Strategy: edge-case
  Test cases: ['TC0', 'TC1']
  Custom: None

Iteration 1:
  VL: 2002
  Rule: sequence_numbers
  Mode: custom
  Strategy: adversarial
  Test cases: None
  Custom: Test extreme boundary
...
```

### Testing Full Loop

```bash
# Quick test with 3 iterations
python3 random_baseline/main.py --max-iterations 3 --seed 42
```

## Reproducibility

**With random seed:**
```bash
python3 random_baseline/main.py --seed 42
```
- Same VL choices
- Same rule choices
- Same test case selections
- **Reproducible results**

**Without random seed:**
```bash
python3 random_baseline/main.py
```
- Different results each run
- Non-deterministic
- For production fuzzing

## Notes

- Random baseline does NOT learn from history (by design)
- Random baseline does NOT adapt based on rewards (by design)
- Random baseline is PURELY random exploration
- This is the STANDARD baseline in fuzzing research
- Fair comparison requires same infrastructure

## Authors

AI Fuzzing Research Team

## License

Research project - refer to main repository for license details

