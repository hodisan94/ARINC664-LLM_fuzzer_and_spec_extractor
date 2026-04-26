# Dependency Map

This document maps all cross-directory dependencies. **Consult this before moving any files or directories.**

---

## Python Import Dependencies

### `llm_fuzzer/` imports
- `llm_fuzzer.core.*` → internal
- `llm_fuzzer.utils.*` → internal
- `llm_fuzzer.prompts.*` → internal

### `boofuzz_baseline/` imports
- `boofuzz_baseline.*` → internal
- `llm_fuzzer.core.test_generator` → `llm_fuzzer/core/`
- `llm_fuzzer.core.feedback_analyzer` → `llm_fuzzer/core/`
- `llm_fuzzer.core.reward_calculator` → `llm_fuzzer/core/`
- `llm_fuzzer.utils.simulator_runner` → `llm_fuzzer/utils/`

### `random_baseline/` imports
- `random_baseline.*` → internal
- `llm_fuzzer.core.feedback_analyzer` → `llm_fuzzer/core/`
- `llm_fuzzer.core.test_generator` → `llm_fuzzer/core/`
- `llm_fuzzer.utils.simulator_runner` → `llm_fuzzer/utils/`
- `llm_fuzzer.utils.spec_loader` → `llm_fuzzer/utils/`
- `llm_fuzzer.utils.test_case_loader` → `llm_fuzzer/utils/`

### `spec_extraction/` imports
- Only internal imports (self-contained)
- `run_multimodel.py` → `llm_providers.py`, `prompts_open.py`, `pdf_utils.py`
- `align_rules.py` → `llm_providers.py`, `prompts_open.py`, `pdf_utils.py`
- `export_validated.py` → reads `alignment_results.json` + `multimodel_output/rules_*.json`

### `evaluation/` imports
- Only internal imports (uses subprocess to call other modules)

### `tests/` imports
- `llm_fuzzer.core.strategy_planner`
- `llm_fuzzer.core.test_generator`

---

## Path Resolution Method

All modules use `sys.path.insert(0, str(Path(__file__).parent.parent))` to add the **project root** to Python path. This means:

> **All module directories MUST remain as direct children of the project root.**

Moving `llm_fuzzer/`, `random_baseline/`, `boofuzz_baseline/`, `evaluation/`, `spec_extraction/`, or `configs/` into a subdirectory will break all imports.

---

## File Path References

### `configs/spec_rules.json`
Referenced by:
- `llm_fuzzer/main.py`, `llm_fuzzer/core/strategy_planner.py`, `llm_fuzzer/core/test_generator.py`
- `llm_fuzzer/utils/spec_loader.py` (generic indexer for all rule formats)
- `random_baseline/main.py`, `random_baseline/random_strategy_generator.py`
- `boofuzz_baseline/main.py`, `boofuzz_baseline/afdx_protocol.py`, `boofuzz_baseline/boofuzz_strategy_generator.py`
- `evaluation/run_comparison.py`, `evaluation/analysis_without_llm.py`, `evaluation/comprehensive_analysis.py`
- `tests/test_hybrid_freedom.py`, `tests/test_paper_alignment.py`

### `configs/spec_rules_validated.json`
Referenced by:
- `spec_extraction/export_validated.py` (writes it)
- Used for academic reporting and analysis (not loaded by fuzzer)

### `configs/validation_report.json`
Referenced by:
- `spec_extraction/export_validated.py` (writes it)
- Used for paper metrics (not loaded by fuzzer)

### `configs/test_cases.json`
Referenced by same files as spec_rules.json, plus:
- `tests/test_smart_sequences.py`
- `llm_fuzzer/demo.py`

### `spec_extraction/alignment_results.json`
Referenced by:
- `spec_extraction/align_rules.py` (writes it)
- `spec_extraction/export_validated.py` (reads it)

### `spec_extraction/multimodel_output/rules_*.json`
Referenced by:
- `spec_extraction/run_multimodel.py` (writes them)
- `spec_extraction/align_rules.py` (reads them)
- `spec_extraction/export_validated.py` (reads them for enriched export)

### `examples/AFDX_V3/mutations.json`
- Written by: `llm_fuzzer/utils/simulator_runner.py`
- Read by: `examples/AFDX_V3/model/afdx-traffic-generator.cc`

### `examples/AFDX_V3/output/csv/AFDX-LOG-OUTPUT.csv`
- Written by: `examples/AFDX_V3/simulations/afdx-demo.cc`
- Read by: `llm_fuzzer/utils/simulator_runner.py`

### `llm_fuzzer/data/seed_frames.json`
Referenced by:
- `llm_fuzzer/main.py`
- `llm_fuzzer/core/test_generator.py`
- `random_baseline/main.py`
- `tests/test_hybrid_freedom.py`, `tests/test_paper_alignment.py`

### Iteration History Files
- `llm_fuzzer/data/iteration_history.jsonl` → read by `evaluation/`
- `random_baseline/data/iteration_history.jsonl` → read by `evaluation/`
- `boofuzz_baseline/data/iteration_history.jsonl` → read by `evaluation/`

---

## Absolute Paths (should be replaced)

The following files contain hardcoded absolute paths to `/home/hodisan1994/ns-3-reset/ns-3`:

| File | Line | Type |
|------|------|------|
| `llm_fuzzer/utils/simulator_runner.py` | ~33 | Default `ns3_path` parameter |

> **Recommendation:** Replace with `Path(__file__).resolve().parent.parent` or environment variable.

---

## C++ Dependencies

### `examples/AFDX_V3/`
- Self-contained (no external C++ dependencies beyond standard ns-3)
- Linked via `CMakeLists.txt` in the `examples/AFDX_V3/` directory

---

## Safe to Move (no code dependencies)

| Item | Can move to |
|------|------------|
| `.log` / `.txt` files | `logs/` |
| Loose `.md` summaries | `archive/` |
| `paper_sections/` | `docs/paper/` |
| `presentation_context/` | `docs/presentation/` |
| `test_*.py` (top-level) | `tests/` (use absolute sys.path) |

## DO NOT Move

| Item | Reason |
|------|--------|
| `llm_fuzzer/` | Cross-imported by random_baseline, boofuzz_baseline, evaluation, tests |
| `random_baseline/` | Uses sys.path relative to project root |
| `boofuzz_baseline/` | Uses sys.path relative to project root |
| `evaluation/` | Uses sys.path relative to project root |
| `spec_extraction/` | Uses sys.path relative to project root |
| `configs/` | Referenced by virtually every module |
| `examples/AFDX_V3/` | Part of ns-3 build system, referenced by simulator_runner |
