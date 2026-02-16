# Project Roadmap

## Status Overview

| Component | Status | Notes |
|-----------|--------|-------|
| AFDX Simulator (C++) | Done | Fully functional, builds and runs |
| Spec Extraction (single model) | Done | 10 rules, 96 test cases extracted |
| Spec Extraction (multi-model) | Done | GPT + Claude + Gemini with arbitration |
| LLM Fuzzer | Done | Full iterative loop with GPT-5 |
| Random Baseline | Done | 15+ iterations completed |
| Boofuzz Baseline | Done (code) | Implementation exists, not yet documented in paper |
| Evaluation Framework | Done | Three-way comparison ready |
| Paper | In Progress | Some implementations not yet reflected in paper |

---

## What Has Been Implemented

### Phase 1: Specification Knowledge Extraction
- [x] PDF text extraction from ARINC 664 Part 7
- [x] Single-model rule extraction (GPT)
- [x] Multi-model parallel extraction (GPT + Claude + Gemini)
- [x] Cross-model comparison and conflict detection
- [x] Conflict arbitration with judge LLM
- [x] Test case generation from extracted rules
- [x] Test case validation
- [x] Export to `spec_rules.json` and `test_cases.json`

### Phase 2: LLM-Guided Iterative Fuzzing
- [x] LLM Strategy Planner (GPT-5 based)
- [x] Test Generator (predefined + custom mutations)
- [x] Simulator Runner (ns-3 integration)
- [x] Feedback Analyzer + Reward Calculator
- [x] Iteration history logging (JSONL)
- [x] Resumable execution
- [x] Hybrid approach (LLM chooses test cases OR custom mutations)

### Baselines
- [x] Random fuzzer baseline
- [x] Boofuzz systematic baseline

### Evaluation
- [x] Three-way comparison framework
- [x] LaTeX table generation
- [x] Statistical analysis scripts

---

## What Still Needs to Be Done

### Paper Updates
- [ ] Document boofuzz baseline in the paper
- [ ] Add three-way comparison results to evaluation section
- [ ] Update methodology section with hybrid approach details
- [ ] Add multi-model extraction with arbitration details

### Experiments
- [ ] Run full LLM fuzzer evaluation with sufficient iterations (50+)
- [ ] Run full boofuzz baseline evaluation
- [ ] Generate final three-way comparison tables
- [ ] Produce definitive results for paper

### Code Improvements
- [ ] Replace hardcoded absolute paths with relative/environment-based paths
- [ ] Standardize `sys.path` modifications across all modules
- [ ] Add proper `__init__.py` files for cleaner imports
- [ ] Add comprehensive error handling and logging
- [ ] Create a unified CLI entry point (instead of running individual scripts)

### Future Enhancements
- [ ] Support for additional LLM providers in fuzzer (not just GPT)
- [ ] Automated CI/CD pipeline for running evaluations
- [ ] Web dashboard for monitoring fuzzing progress
- [ ] Extended AFDX model with more protocol features
- [ ] Real hardware-in-the-loop testing support

---

## Previous Results Summary

### Phase 1 Results
- **Protocol Rules Extracted:** 10
- **Test Cases Generated:** 96
- **Average Test Cases per Rule:** 6.9
- **Categories:** Virtual Link, Sequence Numbers, Filtering/Policing, Switching, Priority/QoS, Buffer Management, Frame Aging, Monitoring, Redundancy, Performance
- **Violation Types:** 36 unique types (top: invalid_format=18, above_max=16, below_min=13)

### Random Baseline Results (15 iterations)
- **VL Coverage:** 5/8 (62.5%)
- **Rule Coverage:** 8/10
- **Average Reward:** 0.854
- **Distribution:** Uneven (33% vs 7%)

### Expected LLM Fuzzer Improvement
- **VL Coverage:** 8/8 (100%)
- **Rule Coverage:** 10+
- **Reward:** Higher than 0.854
- **Distribution:** More uniform
- **Learning:** Visible improvement across iterations
