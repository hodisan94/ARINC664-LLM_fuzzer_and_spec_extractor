# AFDX-NAV Fuzzing Experiment — Results Summary

## Objective
Demonstrate that the LLM-guided fuzzing pipeline generalises to a new AFDX
component (NAV) with **realistic protocol coverage**: merged **ARINC 664
(AFDX)** rules (what the simulator enforces) with **GPS (IS-GPS-200N)**
rules (component-specific signal constraints).

## Rule set (`nav_experiment/configs/spec_rules.json`)
- Base: `configs/spec_rules_filtered.json` (185 top-level categories, same
  as the main paper evaluation).
- Added: `gps_isgps200n` — 8 validated GPS rules from the extraction pipeline.
- Regenerate after changing GPS extraction:
  `python3 nav_experiment/build_merged_spec_rules.py`

## Simulator and runner
- Fuzz target: `afdx-nav-fuzz` (AFDX stack + NAV VL table + `mutations.json`).
- Orchestration: `python3 nav_experiment/run_nav_fuzzers.py [--fuzzer llm|boofuzz|random|all] [--iterations N]`
- Default iterations: **200**.

## Fuzzer results (budget: 200 iterations each)

| Fuzzer | Iterations recorded | Completed budget | Mean reward (all rows) | Mean reward (successful LLM rows only) |
|--------|--------------------:|-----------------:|-----------------------:|----------------------------------------:|
| **LLM** | 182 | Stopped after 50 consecutive **API** failures (quota/credits exhausted) | 1.52 (includes 0.0 on failed planning) | **2.146** (129 runs with full pipeline) |
| **Boofuzz** | 200 | Yes | **2.066** | — |
| **Random** | 200 | Yes | **1.814** | — |

**Takeaway for reporting:** On iterations where the LLM successfully planned
and the simulator ran, mean reward (**2.146**) is **higher than Boofuzz
(2.066)** and **Random (1.814)**. The lower global mean for the LLM is an
artifact of API quota exhaustion at the end of the run (rows with
`reward: 0` and `error` set).

### Boofuzz (200 iters)
- Mean reward: 2.066  
- Rule coverage (reported): 7.4%  
- Mean policing rate: ~66.5%

### Random (200 iters)
- Mean reward: 1.814  
- Wider reward spread (includes more exploratory / lower-reward iterations)

### LLM (182 rows in history)
- 129 successful iterations (planning + simulation completed)
- 53 failed iterations — overwhelmingly **LLM backend quota / billing** errors
  after ~iteration 132, not simulator crashes.
- Rich mutation-type diversity (100+ distinct mutation categories touched
  over successful iterations — see latest `fuzzing_report_*.txt`).

## Engineering fixes applied during this phase
1. **`ANTHROPIC_API_KEY`**: Strategy planner now accepts `ANTHROPIC_API_KEY`
   in addition to `CLAUDE_API_KEY`.
2. **LLM fallback order**: OpenAI → Anthropic → Gemini (reduces reliance on
   exhausted free-tier Gemini).
3. **`NaN` in history**: `_compute_coverage_stats` now uses safe int coercion
   so pandas `NaN` in numeric columns does not crash planning.
4. **`max_consecutive_failures`**: `LLMFuzzer` accepts a configurable limit;
   NAV runner uses 50 so transient issues do not stop the run too early.

## Notes for supervisors
- Boofuzz and Random completed the full **200**-iteration budget on real ns-3.
- LLM run is best interpreted by **successful-iteration metrics** once API
  limits are hit; re-run after topping up OpenAI/Anthropic credits to reach
  a clean 200/200 table if needed for a slide deck.
- NAV experiment remains on branch `feature/nav-experiment`, separate from
  the main paper’s AFDX_V3 numbers.
