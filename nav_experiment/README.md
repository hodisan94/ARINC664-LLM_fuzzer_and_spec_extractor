# NAV-APP Fuzzing Experiment

Runs the same LLM / Boofuzz / Random pipeline against the **AFDX_NAV** example
(`afdx-nav-fuzz`) so supervisors can see portability without touching the main
paper branch.

## Structure

```
nav_experiment/
├── spec/                      # Reference PDFs (e.g. IS-GPS-200N.pdf)
├── configs/spec_rules.json    # AFDX filtered rules + gps_isgps200n (merged)
├── build_merged_spec_rules.py # Rebuild merged spec from extraction_output
├── extraction_output/         # GPS rule extraction artifacts
├── results/{llm,boofuzz,random}/
├── run_nav_fuzzers.py         # Entry point (patches paths + scenario)
└── RESULTS_SUMMARY.md         # Latest numbers for reporting
```

## Quick start

1. **Build fuzz target**
   ```bash
   ./ns3 build afdx-nav-fuzz
   ```

2. **(Re)build merged rules** — ARINC 664 rules from `configs/spec_rules_filtered.json`
   plus GPS rules under `gps_isgps200n`:
   ```bash
   python3 nav_experiment/build_merged_spec_rules.py
   ```

3. **Run fuzzers** (default **200** iterations each if `--fuzzer all`):
   ```bash
   python3 -u nav_experiment/run_nav_fuzzers.py --fuzzer all --iterations 200
   ```

See `RESULTS_SUMMARY.md` for the latest headline metrics.
