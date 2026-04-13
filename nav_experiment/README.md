# NAV-APP Fuzzing Experiment

This directory contains results from running the LLM-guided fuzzing pipeline
against the AFDX Navigation Application (GPS + Flight Control) simulator.

**This experiment is separate from the main paper evaluation** — it serves as
a demonstration for supervisors that the pipeline generalises to new AFDX
components.

## Structure

```
nav_experiment/
├── spec/                 # Reference specs (IS-GPS-200N.pdf)
├── configs/              # NAV-specific spec_rules and test_cases
├── extraction_output/    # Multi-model rule extraction results
└── results/              # Fuzzer run results (LLM, Boofuzz, Random)
    ├── llm/
    ├── boofuzz/
    └── random/
```

## How to run

1. **Build the NAV simulator:**
   ```bash
   ./ns3 build afdx-nav-app-simulation
   ```

2. **Extract rules from GPS spec:**
   ```bash
   cd spec_extraction
   python3 run_multimodel.py --pdf ../nav_experiment/spec/IS-GPS-200N.pdf \
       --providers openai anthropic mistral \
       --outdir ../nav_experiment/extraction_output
   ```

3. **Run fuzzers (TBD):** Requires adapting `SimulatorRunner` for the NAV target.
