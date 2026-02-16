# LLM-Guided AFDX Fuzzer

This directory contains the complete implementation of an **LLM-Guided Iterative Fuzzing System** for AFDX networks, as described in our research paper. The fuzzer uses an LLM (GPT-4o/GPT-5) to intelligently select test strategies based on protocol rules, test cases, and historical performance feedback.

## Overview

The fuzzer operates in an iterative loop with three main components:

1. **Test Feedback Analyzer** (Component 1): Parses simulator logs, computes performance metrics, calculates reward scores, and generates recommendations
2. **LLM-Based Strategy Planner** (Component 2): Uses the LLM to decide which Virtual Link (VL) to test, which protocol rule to violate, and which test cases to apply
3. **Strategy-Driven Test Input Generator** (Component 3): Transforms the LLM's strategy into concrete AFDX frames and executes them on the ns-3 simulator

### Key Design Principles

- **No Predetermined Choices**: The LLM has complete freedom to choose strategies based on all available data
- **Learning & Adaptation**: The system learns from previous iterations and adapts its strategy
- **Exploration & Exploitation**: Balances testing untested areas vs. deepening investigation of promising areas
- **Reward-Based Optimization**: Uses a multi-component reward function to guide the LLM toward effective testing
- **Explainable Decisions**: Every LLM decision includes reasoning, making the fuzzer's behavior transparent

## Directory Structure

```
llm_fuzzer/
├── README.md                    # This file
├── requirements.txt             # Python dependencies
├── __init__.py
├── main.py                      # Main fuzzing loop (ENTRY POINT)
│
├── core/                        # Core fuzzing components
│   ├── __init__.py
│   ├── feedback_analyzer.py    # Component 1: Analyze results & compute reward
│   ├── reward_calculator.py    # Reward function implementation
│   ├── strategy_planner.py     # Component 2: LLM decision maker
│   ├── test_generator.py       # Component 3: Generate AFDX frames
│   └── mutation_parser.py      # Parse custom mutations from LLM
│
├── utils/                       # Data loaders and utilities
│   ├── __init__.py
│   ├── spec_loader.py          # Load protocol rules from JSON
│   ├── test_case_loader.py     # Load violation test cases from JSON
│   ├── log_parser.py           # Parse ns-3 simulator logs
│   └── simulator_runner.py     # Execute ns-3 simulator
│
├── prompts/                     # LLM prompts
│   ├── __init__.py
│   └── fuzzing_agent.py        # Main fuzzing agent prompt builder
│
├── data/                        # Data files
│   ├── seed_frames.json        # Valid AFDX frames dataset
│   └── iteration_history.jsonl # Historical results (JSONL format)
│
├── tests/                       # Comprehensive unit tests
│   ├── __init__.py
│   ├── test_phase1.py          # Tests for data loaders
│   ├── test_component1.py      # Tests for feedback analyzer
│   ├── test_component2.py      # Tests for strategy planner
│   ├── test_component3.py      # Tests for test generator
│   └── test_main_loop.py       # Tests for main loop
│
├── output/                      # Output directory (created at runtime)
│   ├── iteration_XXX_test.json # Generated test inputs
│   ├── fuzzing_report_*.txt    # Final reports
│   └── history_*.csv           # History exports
│
├── demo.py                      # Demo for Phase 1 components
├── demo_component1.py           # Demo for Component 1
├── demo_component2.py           # Demo for Component 2
├── demo_main_loop.py            # Demo with mock simulator
└── verify_llm.py                # LLM integration verification
```

## Quick Start

### 1. Install Dependencies

```bash
cd /home/hodisan1994/ns-3-reset/ns-3
pip install -r llm_fuzzer/requirements.txt
```

### 2. Set OpenAI API Key

```bash
export OPENAI_API_KEY=your_key_here
```

### 3. Run the Fuzzer

```bash
# Run with defaults (50 iterations)
python3 llm_fuzzer/main.py

# Run with custom iteration count
python3 llm_fuzzer/main.py --max-iterations 100

# Specify custom VLs to test
python3 llm_fuzzer/main.py --vls 1001 1002 2001 2002

# Resume from previous run
python3 llm_fuzzer/main.py --resume
```

### 4. Test with Mock Simulator (No ns-3 Required)

```bash
python3 llm_fuzzer/demo_main_loop.py
```

## Components

### Component 1: Test Feedback Analyzer

**Files:** `core/feedback_analyzer.py`, `core/reward_calculator.py`

**Purpose:** Analyzes simulator output and computes a reward score to guide the LLM.

**Reward Function:**
```
Reward = λ1·r_policing - λ2·r_forward + λ3·r_novelty - λ4·r_repeat
       + bonus_edge + bonus_safety
```

Where:
- `r_policing`: Rate of frames dropped by legitimate policing (high = good)
- `r_forward`: Rate of frames forwarded under malformed conditions (high = bad)
- `r_novelty`: Reward for testing new strategies (1.0 if novel, 0.0 if repeated recently)
- `r_repeat`: Penalty for repeating exact previous tests (1.0 if exact repeat, 0.0 otherwise)
- `bonus_edge`: Bonus for edge-case or adversarial testing (0.0-1.0)
- `bonus_safety`: Bonus if no crashes or hangs occurred (0.3)

**Default Weights:**
- λ1 (policing) = 0.6
- λ2 (forward) = 0.2
- λ3 (novelty) = 0.4
- λ4 (repeat) = 0.2

**Output:** Reward score, metrics, analysis, and recommendation for next iteration.

**Tests:** `tests/test_component1.py` (19 tests, all passing)

### Component 2: LLM-Based Strategy Planner

**Files:** `core/strategy_planner.py`, `prompts/fuzzing_agent.py`

**Purpose:** Uses the LLM to decide what to test next based on protocol rules, test cases, history, and VL statistics.

**LLM Model:** GPT-5

**LLM Input:**
- Protocol rules from `configs/spec_rules.json`
- Violation test cases from `configs/test_cases.json`
- Recent performance results (last 5 iterations)
- VL statistics (times tested, avg reward, bugs found)
- System configuration (available VLs)

**LLM Output (JSON):**
```json
{
  "target_vl": 1001,
  "protocol_rule": "bag",
  "test_mode": "predefined",
  "test_cases": ["TC0", "TC1", "TC2"],
  "custom_mutation": null,
  "strategy": "edge-case",
  "reasoning": "Testing BAG boundary violations on VL 1001..."
}
```

**Strategy Types:**
- `conformance`: Test protocol compliance with valid parameters (baseline)
- `edge-case`: Test boundary values, invalid identifiers (recommended)
- `adversarial`: Test extreme violations, stress testing (aggressive)

**Test Modes:**
- `predefined`: Use predefined test cases from `configs/test_cases.json`
- `custom`: LLM proposes custom mutations in natural language

**Tests:** `tests/test_component2.py` (17 tests, all passing)

**LLM Verification:** `verify_llm.py` (6 tests, all passing)

### Component 3: Strategy-Driven Test Input Generator

**Files:** `core/test_generator.py`, `core/mutation_parser.py`, `data/seed_frames.json`, `utils/simulator_runner.py`

**Purpose:** Transforms the LLM's abstract strategy into concrete AFDX frames and executes them on the ns-3 simulator.

**Process:**
1. Load seed frame for target VL from `data/seed_frames.json`
2. Apply mutations:
   - **Predefined mode**: Look up test cases by ID (e.g., TC0 = BAG=0ms)
   - **Custom mode**: Parse LLM's natural language mutation (e.g., "Set BAG to 5ms")
3. Generate a sequence of 20 frames with:
   - Correct timing (based on mutated BAG or default interval)
   - Sequential numbering (or mutated sequence numbers)
   - Payload adjustment to match target frame size
4. Serialize to JSON format expected by ns-3 simulator
5. Execute simulation and collect logs

**Output Format (ns-3 JSON):**
```json
{
  "vl_id": 1001,
  "frames": [
    {"time": 0.0, "seq": 1, "bag_ms": 8, "payload_hex": "AABBCCDD..."},
    {"time": 0.008, "seq": 2, "bag_ms": 8, "payload_hex": "AABBCCDD..."},
    ...
  ]
}
```

**Tests:** `tests/test_component3.py` (15 tests, all passing)

### Main Fuzzing Loop

**File:** `main.py`

**Purpose:** Orchestrates all components in an iterative loop.

**Loop Flow:**
```
for iteration in range(max_iterations):
    1. Load history from previous iterations
    2. Component 1: Analyze previous results (if any)
    3. Component 2: LLM plans next strategy
    4. Component 3: Generate frames + run simulator
    5. Component 1: Analyze new results + calculate reward
    6. Save iteration data to history
    7. Check stopping conditions
```

**Stopping Conditions:**
- Maximum iterations reached
- 5 consecutive failures
- User interrupt (Ctrl+C)

**Output:**
- `data/iteration_history.jsonl`: Full iteration history (JSONL format, one line per iteration)
- `output/iteration_XXX_test.json`: Generated test inputs for each iteration
- `output/fuzzing_report_*.txt`: Final report with statistics
- `output/history_*.csv`: Full history exported to CSV

**Tests:** `tests/test_main_loop.py` (9 tests, all passing)

## Usage Examples

### Basic Fuzzing Run

```bash
python3 llm_fuzzer/main.py --max-iterations 50
```

### Resume from Previous Run

```bash
python3 llm_fuzzer/main.py --resume
```

### Test Specific VLs

```bash
python3 llm_fuzzer/main.py --vls 1001 1002 2001 2002 --max-iterations 100
```

### Demo with Mock Simulator

```bash
python3 llm_fuzzer/demo_main_loop.py
```

## Testing

All components have comprehensive unit tests:

```bash
# Test all components
python3 -m unittest discover llm_fuzzer/tests

# Test specific component
python3 -m unittest llm_fuzzer/tests/test_component1.py
python3 -m unittest llm_fuzzer/tests/test_component2.py
python3 -m unittest llm_fuzzer/tests/test_component3.py
python3 -m unittest llm_fuzzer/tests/test_main_loop.py

# Verify LLM integration (requires OpenAI API key)
python3 llm_fuzzer/verify_llm.py
```

**Test Coverage:**
- Component 1: 19 tests
- Component 2: 17 tests
- Component 3: 15 tests
- Main Loop: 9 tests
- LLM Verification: 6 tests
- **Total: 66 tests, all passing**

## Integration with Paper Methodology

This implementation directly corresponds to our research paper:

### Specification Knowledge Extraction (Section V.A)

**Status:** COMPLETED

- Protocol rules extracted from ARINC 664 Part 7 using LLM
- Output: `configs/spec_rules.json` (247 lines, comprehensive)
- Violation test cases generated by LLM
- Output: `configs/test_cases.json` (validated)
- Tools: `spec_extraction/` directory

### LLM-Guided Iterative Fuzzing (Section V.B)

**Status:** COMPLETED

All three components are fully implemented and tested:

1. **Component 1: Test Feedback Analyzer** (100% complete)
   - Parses logs using `SimulatorLogParser`
   - Calculates reward using `RewardCalculator`
   - Generates recommendations
   - 19 passing tests

2. **Component 2: LLM-Based Strategy Planner** (100% complete)
   - Builds comprehensive prompt with all data
   - Queries LLM (GPT-4o/GPT-5) with JSON mode
   - Parses and validates strategy
   - 17 passing tests + 6 LLM verification tests

3. **Component 3: Strategy-Driven Test Input Generator** (100% complete)
   - Loads seed frames
   - Applies mutations (predefined or custom)
   - Generates ns-3 compatible JSON
   - Executes simulator
   - 15 passing tests

4. **Main Fuzzing Loop** (100% complete)
   - Orchestrates all components
   - Manages iteration history
   - Implements stopping conditions
   - Generates reports
   - 9 passing tests

## Design Philosophy

### LLM Freedom

The system gives the LLM **complete autonomy** in decision-making:

- **All protocol rules** are presented (not filtered)
- **All test cases** are available (not pre-selected)
- **All VLs** can be tested (valid and invalid)
- **Historical data** is provided without interpretation
- **Two test modes** are offered: structured (predefined) and creative (custom mutations)

The LLM receives **guidelines** (e.g., "prefer undertested VLs"), but makes its own choices.

### Learning from Feedback

The system learns from each iteration:

- **Iteration History**: Complete record of all tests and results
- **VL Statistics**: Per-VL metrics (times tested, avg reward, bugs found)
- **Recent Performance**: Last 5 iterations for pattern recognition
- **Reward Signal**: Multi-component feedback guides exploration

### Intelligent Mutations

The system applies mutations **precisely**, not randomly:

- **Predefined mode**: Direct mapping from test case ID to specific value
- **Custom mode**: NLP parsing of LLM's natural language instructions
- **Smart frame generation**: Correct timing, sequencing, and payload adjustment

This ensures the fuzzer is **intelligent and explainable**, not just a random generator.

## Requirements

```
python >= 3.8
openai >= 1.0.0
pandas >= 2.0.0
numpy >= 1.24.0
```

Install with:
```bash
pip install -r llm_fuzzer/requirements.txt
```

## Environment Setup

Set your OpenAI API key:
```bash
export OPENAI_API_KEY=your_key_here
```

Or create a `.env` file:
```
OPENAI_API_KEY=your_key_here
```

## Troubleshooting

### "No module named 'openai'"
```bash
pip install openai
```

### "API key not found"
```bash
export OPENAI_API_KEY=your_key_here
```

### "ns3 script not found"
If you want to run with the real simulator (not mock), ensure ns-3 is built:
```bash
cd /home/hodisan1994/ns-3-reset/ns-3
./ns3 configure --enable-examples --enable-tests
./ns3 build
```

## Next Steps

1. **Run full fuzzing campaign**: 50-100 iterations with real simulator
2. **Compare with random baseline**: Run `tools/random_fuzzer_baseline.py`
3. **Analyze results**: Coverage metrics, bugs found, reward trends
4. **Prepare for paper**: Export plots, statistics, and examples

## Authors

AI Fuzzing Research Team

## License

Research project - refer to main repository for license details
