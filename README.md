# AI-Driven AFDX Fuzzing and Validation

This repository contains an ns-3 based AFDX digital twin, an LLM-guided fuzzing framework, two baseline fuzzers, a specification-extraction pipeline, and evaluation scripts for measuring protocol-rule coverage and injected-bug detection.

The project was developed for research on stateless avionics protocol fuzzing. The main target is ARINC 664 Part 7, also known as Avionics Full-Duplex Switched Ethernet (AFDX). The codebase also contains an AFDX-NAV prototype that layers a navigation-style payload over the same AFDX stack for future work.

## What This Repository Contains

The project has five main parts:

1. `examples/AFDX_V3/` - the primary ns-3 AFDX simulator used as the System Under Test (SUT).
2. `spec_extraction/` - the LLM-based pipeline that extracts protocol rules and violation test cases from the ARINC 664 specification.
3. `llm_fuzzer/` - the LLM-guided iterative fuzzer.
4. `random_baseline/` and `boofuzz_baseline/` - comparison fuzzers that use the same simulator, rule set, test cases, and feedback path.
5. `evaluation/` - scripts that compute rule coverage, redundancy, diversity, unique findings, rule correctness, rule completeness, and Bug Detection Rate (BDR).

The repository is built on top of the full ns-3 tree. Most upstream ns-3 files are intentionally ignored by `.gitignore`; only the project-specific implementation, configs, results, and documentation are tracked.

## High-Level Pipeline

The complete research pipeline is:

```text
ARINC 664 Part 7 PDF
  -> spec_extraction/run_multimodel.py
  -> spec_extraction/align_rules.py
  -> spec_extraction/export_validated.py
  -> spec_extraction/filter_rules.py
  -> spec_extraction/extract_test_cases.py
  -> llm_fuzzer/main.py
  -> random_baseline/main.py
  -> boofuzz_baseline/main.py
  -> evaluation/compute_metrics.py
  -> evaluation/compute_bdr.py
```

The extraction stage produces machine-readable protocol rules and violation-oriented test cases. The fuzzing stage uses those rules and test cases to generate AFDX frame mutations. The evaluation stage compares the LLM-guided fuzzer against the two baselines and measures bug detection on injected-fault variants.

## Main Results From The Current Run

The current checked-in result files describe the latest AFDX experiment:

- `774` validated protocol rules were extracted by the three-model pipeline.
- `643` rules were retained as relevant to the AFDX simulator.
- `2,703` violation test cases were generated.
- The normalized SUT-relevant rule set contains `185` canonical rules/categories.
- Under a fixed budget of `N = 200` iterations:
  - LLM fuzzer: `85.4%` normalized rule coverage.
  - Boofuzz baseline: `47.0%` normalized rule coverage.
  - Random baseline: `29.2%` normalized rule coverage.
- Injected-bug detection:
  - LLM fuzzer: `6/8` bugs detected.
  - Boofuzz baseline: `4/8` bugs detected.
  - Random baseline: `2/8` bugs detected.

Primary result files:

- `evaluation/results/metrics_report.json`
- `evaluation/results/bdr_report.json`
- `evaluation/results/rule_correctness.json`
- `evaluation/results/rule_completeness.json`
- `llm_fuzzer/output/fuzzing_report_20260418_204517.txt`
- `llm_fuzzer/output/history_20260418_204517.csv`
- `llm_fuzzer/data/iteration_history.jsonl`
- `random_baseline/data/iteration_history.jsonl`
- `boofuzz_baseline/data/iteration_history.jsonl`

## Repository Layout

```text
.
|-- examples/
|   |-- AFDX_V3/                 # Primary AFDX simulator used in the paper
|   `-- AFDX_NAV/                # NAV prototype for future extension work
|-- spec_extraction/             # LLM rule extraction and test-case generation
|-- llm_fuzzer/                  # LLM-guided fuzzing loop
|-- random_baseline/             # Random mutation baseline
|-- boofuzz_baseline/            # Systematic/boofuzz-style baseline
|-- evaluation/                  # Metrics, BDR, correctness, completeness
|-- configs/                     # Runtime rule/test-case/config data
|-- nav_experiment/              # AFDX-NAV experiment wrapper and results
|-- context/                     # Internal architecture/setup notes
|-- Latex/                       # Paper source, tracked separately by ignore rules
|-- .env.example                 # API key template
`-- README.md                    # This document
```

## Core Concepts

### AFDX

AFDX is a deterministic Ethernet-based avionics network. It uses Virtual Links (VLs), Bandwidth Allocation Gap (BAG) timing, frame-size constraints, sequence numbers, static switching, policing, and redundant A/B network paths.

This matters for fuzzing because AFDX is mostly stateless. There is no request/response session state that naturally guides a fuzzer. Useful tests require protocol knowledge: valid VL identifiers, BAG ranges, frame-size limits, MAC/VL authorization, sequence-number behavior, redundancy handling, and switch policing.

### Protocol Rules

Protocol rules are machine-readable constraints extracted from ARINC 664 Part 7. Examples include:

- valid BAG values,
- Ethernet frame-size limits,
- sequence-number range and wraparound behavior,
- VL authorization constraints,
- switch filtering and policing behavior,
- redundancy and duplicate-discard rules.

Rules are stored in:

- `configs/spec_rules_validated.json` - full metadata from cross-validation.
- `configs/spec_rules.json` - clean exported rules.
- `configs/spec_rules_filtered.json` - SUT-relevant rules used by the fuzzers.

### Test Cases

Test cases are violation scenarios generated from the protocol rules. Each test case describes an out-of-range or malformed value that intentionally challenges a rule. Examples:

- `BAG = 0`
- `frame_size = 1519`
- invalid source MAC for an otherwise valid VL
- sequence number outside the accepted window

Test cases are stored in:

- `configs/test_cases.json`

### Seed Frames

Fuzzing starts from valid AFDX seed frames rather than arbitrary bytes. The test generator mutates these seed frames according to the selected strategy.

Seed frames are stored in:

- `llm_fuzzer/data/seed_frames.json`

### Iteration History

Each fuzzer writes a JSONL history file. Each line is one iteration containing the selected rule, VL, mutation parameters, simulator metrics, reward, and success/failure state.

History files:

- `llm_fuzzer/data/iteration_history.jsonl`
- `random_baseline/data/iteration_history.jsonl`
- `boofuzz_baseline/data/iteration_history.jsonl`
- `nav_experiment/results/*/iteration_history.jsonl`

## Requirements

### System Requirements

- Linux or WSL2
- Python 3.10 recommended
- C++ compiler supported by ns-3
- CMake and the ns-3 `./ns3` wrapper
- Internet/API access for LLM-based extraction and LLM-guided fuzzing

### Python Dependencies

Install dependencies from the repository root:

```bash
pip install -r llm_fuzzer/requirements.txt
pip install anthropic PyPDF2 python-dotenv matplotlib matplotlib-venn
```

The current `llm_fuzzer/requirements.txt` covers the core fuzzer dependencies. The extra packages above are used by the multi-provider extraction and evaluation scripts.

### API Keys

Copy `.env.example` to `.env` and fill in the keys you need:

```bash
cp .env.example .env
```

Expected variables:

```bash
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
MISTRAL_API_KEY=...
```

Notes:

- `.env` is ignored by Git and must not be committed.
- `OPENAI_API_KEY` is required for the LLM fuzzer and test-case extraction.
- `ANTHROPIC_API_KEY` is used for Claude in the extraction pipeline and as a fuzzer fallback.
- `MISTRAL_API_KEY` is used for the third extractor model.
- The fuzzer also accepts `CLAUDE_API_KEY` as an alias for `ANTHROPIC_API_KEY`.

## Build The Simulator

From the repository root:

```bash
./ns3 configure --enable-examples --enable-tests
./ns3 build
```

To build only the primary AFDX demo target:

```bash
./ns3 build afdx-demo
```

To build the NAV prototype target:

```bash
./ns3 build afdx-nav-fuzz
```

## Primary Simulator: `examples/AFDX_V3`

The primary simulator lives in:

```text
examples/AFDX_V3/
```

Important files:

- `model/afdx-frame.*` - AFDX frame representation.
- `model/afdx-end-system.*` - sending and receiving end systems.
- `model/afdx-switch.*` - filtering, forwarding, policing, and counters.
- `model/afdx-virtual-link.*` - VL configuration and BAG-related behavior.
- `model/afdx-traffic-generator.*` - traffic generation and mutation application.
- `config/virtual_links.csv` - VL configuration.
- `mutations.json` - mutation input written by the Python fuzzers.
- `simulations/afdx-demo.cc` - primary ns-3 scenario.
- `output/` - simulator outputs such as CSV logs and PCAPs.

The simulator is normally run indirectly through `llm_fuzzer/utils/simulator_runner.py`, which:

1. writes `examples/AFDX_V3/mutations.json`,
2. executes `./ns3 run afdx-demo`,
3. reads simulator stdout and `examples/AFDX_V3/output/csv/AFDX-LOG-OUTPUT.csv`,
4. returns parsed feedback to the fuzzer.

Manual smoke run:

```bash
./ns3 run afdx-demo
```

## Specification Extraction Pipeline

The extraction pipeline converts ARINC 664 Part 7 into protocol rules and violation test cases.

### Step 1: Multi-Model Rule Extraction

Run:

```bash
python3 spec_extraction/run_multimodel.py \
  --pdf configs/ARINC_664P7.pdf \
  --providers openai anthropic mistral
```

Options:

- `--pdf PATH` - input ARINC 664 PDF.
- `--output-dir DIR` - output directory, default `spec_extraction/multimodel_output`.
- `--providers ...` - subset of `openai`, `anthropic`, `mistral`.
- `--parallel` - run provider extraction in parallel.

Outputs:

- `spec_extraction/multimodel_output/rules_openai.json`
- `spec_extraction/multimodel_output/rules_anthropic.json`
- `spec_extraction/multimodel_output/rules_mistral.json`
- `spec_extraction/multimodel_output/extraction_summary.json`
- `spec_extraction/multimodel_output/checkpoints/` during long runs

What happens:

- The PDF is split into relevant chapter text.
- Each chapter is chunked into pieces that fit the LLM context window.
- Each provider independently extracts rules using the same open-discovery prompt.
- Each provider aggregates its chunk-level results into one rule set.

### Step 2: Semantic Alignment And Judge Verification

Run:

```bash
python3 spec_extraction/align_rules.py \
  --input-dir spec_extraction/multimodel_output \
  --output spec_extraction/alignment_results.json \
  --pdf configs/ARINC_664P7.pdf \
  --full \
  --arbiter openai \
  --judge openai
```

Options:

- `--input-dir DIR` - directory containing `rules_*.json`.
- `--output PATH` - alignment output JSON.
- `--arbiter {openai,anthropic,mistral}` - model provider used to align rules.
- `--resolve-conflicts` - resolve conflicting values against the spec.
- `--verify-unique` - verify rules found by only one model.
- `--judge {openai,anthropic,mistral}` - provider used for conflict/unique-rule judgment.
- `--pdf PATH` - specification PDF used by judge passes.
- `--full` - shortcut for alignment + conflict resolution + unique-rule verification.

Output:

- `spec_extraction/alignment_results.json`

What happens:

- Similar rules from different providers are grouped semantically.
- Full agreement, partial agreement, conflicts, and unique rules are classified.
- Conflicts are sent to a judge LLM with source text.
- Rules found by only one model are verified against the specification.

### Step 3: Export Validated Rules

Run:

```bash
python3 spec_extraction/export_validated.py \
  --alignment spec_extraction/alignment_results.json \
  --extraction-dir spec_extraction/multimodel_output \
  --output-dir configs
```

Options:

- `--alignment PATH` - alignment result from Step 2.
- `--extraction-dir DIR` - original provider outputs used for enrichment.
- `--output-dir DIR` - where final config files are written.
- `--mode open` - accepted for compatibility; open discovery is the only supported export mode.

Outputs:

- `configs/spec_rules_validated.json`
- `configs/spec_rules.json`
- `configs/validation_report.json`

### Step 4: Filter Rules To The Simulator Scope

Run:

```bash
python3 spec_extraction/filter_rules.py \
  --input configs/spec_rules.json \
  --output configs/spec_rules_filtered.json \
  --report configs/filter_report.json \
  --verbose
```

Options:

- `--input PATH` - full rule set.
- `--output PATH` - filtered rule set.
- `--report PATH` - filtering decision report.
- `--verbose` - print detailed include/exclude reasoning.

Outputs:

- `configs/spec_rules_filtered.json`
- `configs/filter_report.json`

What gets filtered out:

- TCP-only behavior,
- ICMP behavior,
- IP routing features not implemented in the simulator,
- file transfer,
- SNMP/configuration management,
- physical-layer details outside the current SUT,
- other specification areas that cannot be exercised by `examples/AFDX_V3`.

### Step 5: Generate Violation Test Cases

Run:

```bash
python3 spec_extraction/extract_test_cases.py \
  --spec-file configs/spec_rules_filtered.json \
  --output configs/test_cases.json \
  --validate
```

Options:

- `--spec-file PATH` - rules to generate test cases for.
- `--output PATH` - output test-case JSON.
- `--validate` - run validation after generation.
- `--checkpoint PATH` - JSONL checkpoint for resumable extraction.

Relevant environment variable:

```bash
TEST_CASE_MODEL=gpt-4o
```

If not set, the script defaults to `gpt-4o`.

Outputs:

- `configs/test_cases.json`
- validation output printed to the console
- checkpoint file if the run is interrupted

## Fuzzing Pipeline

All three fuzzers target the same simulator, use the same seed frames, consume the same rules/test cases, and produce compatible iteration histories.

### Shared Inputs

- Rules: `configs/spec_rules_filtered.json`
- Test cases: `configs/test_cases.json`
- Seed frames: `llm_fuzzer/data/seed_frames.json`
- VL configuration: `examples/AFDX_V3/config/virtual_links.csv`
- Mutation bridge: `examples/AFDX_V3/mutations.json`

### Shared Outputs

Each run writes:

- generated iteration input files under the chosen output directory,
- a JSONL history file,
- a final text/JSON summary,
- optional CSV exports.

The per-iteration `iteration_*_test.json` files are regenerable and ignored by Git.

## LLM-Guided Fuzzer

Entry point:

```bash
python3 llm_fuzzer/main.py
```

Recommended paper-style run:

```bash
python3 llm_fuzzer/main.py \
  --max-iterations 200 \
  --spec-rules configs/spec_rules_filtered.json \
  --output-dir llm_fuzzer/output
```

Options:

- `--max-iterations N` - number of iterations, default `50`.
- `--vls ID ...` - restrict the VLs available to the planner.
- `--output-dir DIR` - output directory, default `llm_fuzzer/output`.
- `--spec-rules PATH` - rule file, default `configs/spec_rules_filtered.json`.
- `--resume` - accepted by the CLI; the run resumes automatically when the history file already exists.

How it works:

1. Load `configs/spec_rules_filtered.json`.
2. Load `configs/test_cases.json`.
3. Load seed frames from `llm_fuzzer/data/seed_frames.json`.
4. Load previous iteration history from `llm_fuzzer/data/iteration_history.jsonl`.
5. Prompt GPT-5 to choose a strategy.
6. Fall back to Claude Sonnet 4 if the primary provider is unavailable.
7. Apply coverage-driven local post-processing.
8. Generate mutated AFDX frame sequences.
9. Run the ns-3 simulator.
10. Parse logs and CSV output.
11. Compute reward.
12. Append the result to iteration history.

Planner outputs can include:

- `target_vl`
- `protocol_rule`
- `mutation_type`
- `test_cases`
- `bag_value`
- `frame_size`
- `sequence_number`
- `timing_jitter_ms`
- `payload_pattern`
- `mac_mutation_type`
- `dest_mac_mutation`
- `sequence_number_override`
- `prob`
- `strategy`
- `reasoning`

Primary outputs:

- `llm_fuzzer/data/iteration_history.jsonl`
- `llm_fuzzer/output/fuzzing_report_<timestamp>.txt`
- `llm_fuzzer/output/history_<timestamp>.csv`
- `llm_fuzzer/output/iteration_<NNN>_test.json`

## Random Baseline

Entry point:

```bash
python3 random_baseline/main.py
```

Recommended paper-style run:

```bash
python3 random_baseline/main.py \
  --max-iterations 200 \
  --seed 42 \
  --output-dir random_baseline/output
```

Options:

- `--max-iterations N` - number of iterations, default `50`.
- `--seed N` - random seed for reproducibility.
- `--vls ID ...` - restrict available VLs.
- `--output-dir DIR` - output directory, default `random_baseline/output`.

How it differs from the LLM fuzzer:

- It uses the same simulator runner.
- It uses the same test generator.
- It uses the same feedback analyzer and reward calculation.
- It does not use LLM reasoning.
- It selects rules and test cases randomly.
- It does not learn from previous iterations.

Outputs:

- `random_baseline/data/iteration_history.jsonl`
- `random_baseline/output/random_fuzzing_report_<timestamp>.txt`
- `random_baseline/output/random_history_<timestamp>.csv`
- `random_baseline/output/iteration_<NNN>_test.json`

## Boofuzz-Style Baseline

Entry point:

```bash
python3 boofuzz_baseline/main.py
```

Recommended paper-style run:

```bash
python3 boofuzz_baseline/main.py \
  --max-iterations 200 \
  --output-dir boofuzz_baseline/output
```

Options:

- `--max-iterations N` - number of iterations, default `50`.
- `--vls ID ...` - restrict available VLs.
- `--output-dir DIR` - output directory, default `boofuzz_baseline/output`.

How it differs from the LLM fuzzer:

- It uses deterministic/systematic strategy generation.
- It follows an AFDX protocol grammar/violation catalogue.
- It does not adapt based on previous feedback.
- It uses the same simulator, test generator, and feedback path as the LLM and random fuzzers.

Outputs:

- `boofuzz_baseline/data/iteration_history.jsonl`
- `boofuzz_baseline/output/boofuzz_summary_<timestamp>.json`
- `boofuzz_baseline/output/boofuzz_history_<timestamp>.csv`
- `boofuzz_baseline/output/iteration_<NNN>_test.json`

## Comparing The Three Fuzzers

Use the same iteration budget and same rule/test-case configuration for all three fuzzers.

Example:

```bash
python3 llm_fuzzer/main.py --max-iterations 200
python3 random_baseline/main.py --max-iterations 200 --seed 42
python3 boofuzz_baseline/main.py --max-iterations 200
```

Then compute metrics:

```bash
python3 evaluation/compute_metrics.py \
  --llm-history llm_fuzzer/data/iteration_history.jsonl \
  --random-history random_baseline/data/iteration_history.jsonl \
  --boofuzz-history boofuzz_baseline/data/iteration_history.jsonl \
  --test-cases configs/test_cases.json \
  --spec-rules configs/spec_rules_filtered.json
```

Options:

- `--llm-history PATH`
- `--random-history PATH`
- `--boofuzz-history PATH`
- `--test-cases PATH`
- `--spec-rules PATH`
- `--window N` - moving-average window.
- `--cost-per-call FLOAT` - estimated LLM API cost per call.

Outputs:

- `evaluation/results/metrics_report.json`
- figures under `evaluation/results/figures/`

Metrics include:

- rule coverage,
- normalized spec coverage,
- time to coverage,
- redundancy ratio,
- violation diversity,
- unique findings,
- cost/efficiency related fields when available.

## Rule Correctness And Completeness

### Rule Correctness

Rule correctness checks whether extracted rules are accurate with respect to the ARINC specification.

```bash
python3 evaluation/compute_rule_correctness.py \
  --model gpt-4o-mini
```

Options:

- `--model MODEL` - OpenAI model used as judge.
- `--force` - revalidate all rules instead of using cached results.

Output:

- `evaluation/results/rule_correctness.json`

### Rule Completeness

Rule completeness checks whether the extracted rule set covers the normative requirements in the specification.

```bash
python3 evaluation/compute_rule_completeness.py \
  --model gpt-4o-mini
```

Options:

- `--model MODEL` - OpenAI model used for enumeration/matching.
- `--force` - rerun from scratch instead of using cached results.

Output:

- `evaluation/results/rule_completeness.json`

## Bug Detection Rate Evaluation

BDR evaluation replays historical fuzzer iterations against injected-fault variants and measures whether observable behavior changes.

Run:

```bash
python3 evaluation/compute_bdr.py \
  --max-iterations 200 \
  --fuzzers LLM Boofuzz Random \
  --output evaluation/results/bdr_report.json
```

Options:

- `--max-iterations N` - max successful iterations per fuzzer to replay, default `50`.
- `--fuzzers ...` - subset of `LLM`, `Boofuzz`, `Random`.
- `--output PATH` - report output path.

Injected bug catalogue:

- `skip_bag_policing` - switch skips BAG timing enforcement.
- `skip_frame_validation` - switch skips frame-size validation.
- `skip_mac_validation` - switch skips source MAC validation.
- `skip_token_bucket` - switch skips token-bucket policing.
- `skip_vl_check` - switch skips VL authorization.
- `skip_constant_field` - end system skips constant-field MAC check.
- `skip_sequence_check` - end system skips sequence-number integrity checks.
- `accept_oversized` - switch accepts frames larger than the AFDX limit.

Output:

- `evaluation/results/bdr_report.json`

Detection logic:

- A clean run is compared to a buggy run.
- A bug is detected when the expected metric changes, such as fewer drops, more forwarding, or fewer end-system rejections.
- This is behavioral detection, not source-code coverage.

## Evaluation Table Generation

There is a helper for generating LaTeX tables:

```bash
python3 evaluation/generate_latex_tables.py
```

This script expects `evaluation/results/complete_results_*.json` files. The current primary paper numbers are already represented in `metrics_report.json`, `bdr_report.json`, `rule_correctness.json`, and `rule_completeness.json`.

## NAV Prototype

The NAV prototype is intentionally kept because it is likely to become future paper work.

Relevant directories:

- `examples/AFDX_NAV/` - AFDX-NAV ns-3 example and simulator target.
- `nav_experiment/` - wrapper scripts, extracted GPS/NAV rules, merged configs, and NAV results.

Build:

```bash
./ns3 build afdx-nav-fuzz
```

Build merged NAV rules:

```bash
python3 nav_experiment/build_merged_spec_rules.py
```

Run NAV fuzzers:

```bash
python3 -u nav_experiment/run_nav_fuzzers.py \
  --fuzzer all \
  --iterations 200
```

Options:

- `--fuzzer llm`
- `--fuzzer boofuzz`
- `--fuzzer random`
- `--fuzzer all`
- `--iterations N`

Outputs:

- `nav_experiment/results/llm/`
- `nav_experiment/results/boofuzz/`
- `nav_experiment/results/random/`
- `nav_experiment/RESULTS_SUMMARY.md`

Important caveat:

`nav_experiment/run_nav_fuzzers.py` monkey-patches `SimulatorRunner` to use `examples/AFDX_NAV` paths and the `afdx-nav-fuzz` scenario. This keeps the core fuzzer reusable but means NAV is currently a prototype wrapper rather than the main paper pipeline.

## Output And Storage Rules

Important generated files:

- `examples/AFDX_V3/mutations.json` - latest simulator mutation input.
- `examples/AFDX_V3/output/` - simulator CSV/PCAP outputs.
- `llm_fuzzer/output/` - LLM fuzzer reports, CSV history exports, generated test JSONs.
- `random_baseline/output/` - random baseline reports and generated test JSONs.
- `boofuzz_baseline/output/` - boofuzz baseline summaries and generated test JSONs.
- `evaluation/results/` - final metrics reports.
- `spec_extraction/multimodel_output/` - extraction artifacts.

Regenerable files that should not normally be reviewed line by line:

- `**/iteration_*_test.json`
- simulator CSV/PCAP outputs,
- checkpoint directories,
- `.log` files,
- Python caches,
- build directories.

The current `.gitignore` keeps the repository focused on project files while avoiding most ns-3 build artifacts and large generated outputs.

## Security Notes

- Never commit `.env`.
- If `.env` has been shared or committed anywhere outside this local workspace, rotate the API keys.
- `.env.example` is safe to commit because it contains placeholders only.
- The repository may contain PDF or paper-related artifacts outside Git tracking; verify packaging before external handoff.

## Typical Workflows

### Workflow A: Use Existing Extracted Rules And Run Experiments

Use this when you do not want to spend time or API budget re-running extraction.

```bash
./ns3 build afdx-demo
python3 llm_fuzzer/main.py --max-iterations 200
python3 random_baseline/main.py --max-iterations 200 --seed 42
python3 boofuzz_baseline/main.py --max-iterations 200
python3 evaluation/compute_metrics.py
python3 evaluation/compute_bdr.py --max-iterations 200
```

### Workflow B: Rebuild Rules From The Specification

Use this when the specification, prompts, or provider set changes.

```bash
python3 spec_extraction/run_multimodel.py \
  --pdf configs/ARINC_664P7.pdf \
  --providers openai anthropic mistral

python3 spec_extraction/align_rules.py \
  --input-dir spec_extraction/multimodel_output \
  --output spec_extraction/alignment_results.json \
  --pdf configs/ARINC_664P7.pdf \
  --full

python3 spec_extraction/export_validated.py \
  --alignment spec_extraction/alignment_results.json \
  --extraction-dir spec_extraction/multimodel_output \
  --output-dir configs

python3 spec_extraction/filter_rules.py \
  --input configs/spec_rules.json \
  --output configs/spec_rules_filtered.json \
  --report configs/filter_report.json

python3 spec_extraction/extract_test_cases.py \
  --spec-file configs/spec_rules_filtered.json \
  --output configs/test_cases.json \
  --validate
```

### Workflow C: Quick Smoke Test

Use this before a demo to verify the basic stack still runs.

```bash
./ns3 build afdx-demo
python3 llm_fuzzer/main.py --max-iterations 2 --output-dir /tmp/afdx_llm_smoke
python3 random_baseline/main.py --max-iterations 2 --seed 1 --output-dir /tmp/afdx_random_smoke
python3 boofuzz_baseline/main.py --max-iterations 2 --output-dir /tmp/afdx_boofuzz_smoke
```

### Workflow D: NAV Prototype

```bash
./ns3 build afdx-nav-fuzz
python3 nav_experiment/build_merged_spec_rules.py
python3 -u nav_experiment/run_nav_fuzzers.py --fuzzer all --iterations 200
```

## Known Implementation Details

- `llm_fuzzer/utils/simulator_runner.py` defaults `ns3_path` to `/home/hodisan1994/ns-3-reset/ns-3`. If the repository is moved, either run from the same path or update/parameterize this default.
- `nav_experiment/run_nav_fuzzers.py` also uses the same absolute root in its NAV monkey patch.
- The root README intentionally documents this research fork, not upstream ns-3. Upstream ns-3 documentation remains available under `doc/`, `CHANGES.md`, and `RELEASE_NOTES.md`.
- The LLM fuzzer uses OpenAI as primary backend and Claude as fallback.
- Specification extraction uses OpenAI, Anthropic, and Mistral as independent extractor providers.
- The `scripts/` and old `tools/` paths were removed because they were stale and not part of the current paper pipeline.

## What To Show In A Code Walkthrough

For a concise walkthrough, use this order:

1. `examples/AFDX_V3/README.md` and `examples/AFDX_V3/model/` - the SUT.
2. `spec_extraction/README.md` - how rules and test cases are created.
3. `configs/spec_rules_filtered.json` and `configs/test_cases.json` - fuzzer knowledge.
4. `llm_fuzzer/main.py` - the adaptive LLM loop.
5. `llm_fuzzer/core/strategy_planner.py` - LLM planning and fallback.
6. `llm_fuzzer/core/test_generator.py` - strategy to concrete frames.
7. `llm_fuzzer/utils/simulator_runner.py` - Python-to-ns-3 bridge.
8. `random_baseline/main.py` and `boofuzz_baseline/main.py` - baselines.
9. `evaluation/compute_metrics.py` and `evaluation/compute_bdr.py` - results.
10. `nav_experiment/README.md` - future NAV extension.

## License

The underlying ns-3 code is licensed under GPL-2.0-only as provided by the upstream ns-3 project. Project-specific additions in this repository are part of the same source tree and should be handled consistently with the repository license and any organization-specific release process.
