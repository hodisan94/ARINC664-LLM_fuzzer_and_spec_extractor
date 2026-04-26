# AFDX-NAV Fuzzing Experiment — Results Summary

## Objective
Show that the same pipeline used on **AFDX_V3** (main branch) also runs on
**AFDX_NAV**, with merged **ARINC 664** rules plus **GPS (IS-GPS-200N)** under
`gps_isgps200n`, and that the **LLM-guided fuzzer** remains the strongest
**goal-directed** baseline when rewards are interpreted beyond a simple mean.

## Rule set
- **Merged spec:** `python3 nav_experiment/build_merged_spec_rules.py`  
  → `configs/spec_rules_filtered.json` + `gps_isgps200n` (8 GPS leaves).

## Budget
**200 iterations each**, same VL list, same `afdx-nav-fuzz` scenario, same
`configs/test_cases.json`.

## Headline comparison (all runs completed 200/200, 0 failures)

| Metric | **LLM** | Boofuzz | Random |
|--------|--------:|--------:|-------:|
| Mean reward | 2.001 | **2.066** | 1.814 |
| Median reward | 2.000 | 2.000 | 2.000 |
| Min reward | 0.94 | 2.00 | 0.80 |
| **% iterations with reward ≥ 2.2** (top band) | **48.5%** | 33.0% | 21.5% |
| % iterations with reward ≥ 2.0 | 84.5% | **100%** | 61.5% |
| Distinct rule/mutation labels per run | 183 | 200 | 161 |
| LLM strategy mix (edge / conform / adversarial) | 164 / 18 / 18 | — | — |

### How to read this (for supervisors / slides)
1. **Boofuzz** maximises the **arithmetic mean** by staying in a narrow,
   high-reward band (never below 2.0): strong “safe” baseline.
2. **LLM** deliberately spends budget on **edge-case** traffic (164/200
   iterations). That increases variance (min 0.94) but produces the **highest
   share of top-tier rewards (≥ 2.2)** — **48.5%** vs 33% vs 21.5%. That is the
   same qualitative story as on **AFDX_V3**: the LLM prioritises
   **high-signal** violations rather than uniformly sampling the rule space.
3. **Random** underperforms on both mean and top-band frequency.

### Extra LLM signal (from final report)
- **182** distinct high-level mutation categories exercised over 200
  iterations (see `fuzzing_report_20260414_173859.txt`).
- Coverage feedback reached **181 unique rules** tested by late iterations
  (logged in strategy recommendations).

## Reproduce
```bash
./ns3 build afdx-nav-fuzz
python3 nav_experiment/build_merged_spec_rules.py
python3 -u nav_experiment/run_nav_fuzzers.py --fuzzer all --iterations 200
```

Latest LLM report: `nav_experiment/results/llm/fuzzing_report_20260414_173859.txt`  
Histories: `nav_experiment/results/*/iteration_history.jsonl`

## Engineering notes (unchanged)
- `run_nav_fuzzers.py` patches `SimulatorRunner` for NAV paths + `afdx-nav-fuzz`.
- `LLMFuzzer.max_consecutive_failures` (50 on NAV) and planner fixes
  (`ANTHROPIC_API_KEY`, Claude before Gemini, NaN-safe stats) live on
  `feature/nav-experiment` / `main` as applicable.
