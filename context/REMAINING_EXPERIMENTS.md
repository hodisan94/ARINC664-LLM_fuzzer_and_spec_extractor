# Experiments Still to Run (TAES-2026-2779)

**Written:** 2026-11-08. **Deadline:** 13 Nov 2026. Reviewer text and letter status:
`context/REVIEW_STATUS.md`. Metrics: `context/EVALUATION_METRICS.md`.

The evaluation now uses three metrics for the fuzzers: bug detection, boundary tests, and code
coverage (lines and branches). Rule Coverage is removed. Run the experiments one at a time, in
the order of the table. No paid run starts without explicit approval.

## Overview

| # | Experiment | Answers | Needed? | Cost | Time | Status |
|---|---|---|---|---|---|---|
| 1 | Ablation repeats (A0, A1, A2 × 4 more runs) | R1-3, R2-6 | **Required** | ≈ $102 | 3–4 h runs, 1 h scoring | Needs approval |
| 2 | Expert check of the judge AI (108 rules) | R2-2 | **Required** | free | ≈ 3.5 h of an expert, then minutes | Worksheet ready; needs a name |
| 3 | Reward-weight sensitivity | R1-4a | Recommended ("ideally" in the review) | ≈ $96 | 0.5 day of code, 2–3 h runs | Needs approval |
| 4 | Boundary combinations | R2-4 | Recommended | free | 0.5 day | Ready to start |
| 5 | Mutation testing | R2-1 | Optional | free | 1–2 days | Needs a decision |
| 6 | Larger topologies | R2-3 | Reviewer asks; hardest | ≈ $48 per topology | 1.5 days of code plus ≈ 3 h per topology | Needs a decision |
| 7 | NAV case study | none | Only if we keep effectiveness claims | ≈ $16 | 0.5 day | Needs a decision |

Already done, no run needed:
- Main comparison: LLM 5 runs, Random 5 seeds, boofuzz 1 run, with all three metrics.
- Curves by test budget (`budget_curves.py`).
- Code-coverage checks (`verify_code_coverage.py`).
- Redundancy ratio on the final test cases: **8 of 3,989 = 0.2%**, using the same computation as
  `evaluation/compute_metrics.py` (`compute_redundancy`). In that code a duplicate means the same
  value and violation type within one rule; the paper's wording must say this, not "semantically
  equivalent".

## Shared setup (WSL Ubuntu-24.04)

```bash
cd "/mnt/c/Users/Administrator/OneDrive - post.bgu.ac.il/שולחן העבודה/Noa/GitHub/ARINC664-fixes"
source ~/.afdx_openai.env
export AFDX_NS3_PATH=/tmp/ns3_fixtest PYTHONPATH=. PYTHONUTF8=1
PY=/home/hodisan1994/ns-3-reset/ns-3/.venv/bin/python
R=evaluation/results/revision
```

- `/tmp/ns3_fixtest` is the simulator used for every reported run. `/tmp/ns3_cov` is the same
  source with coverage counters (`evaluation/revision/build_coverage_simulator.sh` rebuilds it).
  `/tmp` can be lost when WSL restarts, so check that both exist first.
- Fuzzer code and simulator are unchanged since the Stage 7 commit `c348e53` (checked with
  `git diff`). Model: gpt-5 (the default). Instructions: `--prompt-version neutral`.
- Before a paid run, check by hand that the OpenAI project's spend limit leaves room for it; the
  limit stopped Stage 7 once. A run that hits it can continue with `--resume`.

### Scoring any new run (free, no LLM)

Replace the file list and output names per experiment.

```bash
# Bug detection
$PY -B evaluation/revision/bdr_replay.py --workers 8 --cache $R/bdr_replay_cache_stage7.json \
  --history $R/runs/stage7/<file>.jsonl=$R/runs/stage7/<file>.jsonl --out $R/<name>_bugs.json

# Boundary tests
$PY -B evaluation/revision/boundary_coverage.py --cache $R/bdr_replay_cache_stage7.json \
  --campaign "<NAME>=$R/runs/stage7/<glob>" --out $R/<name>_boundary.json

# Code coverage: lines and branches
AFDX_NS3_PATH=/tmp/ns3_cov $PY -B evaluation/revision/code_coverage.py --gcovr ~/cov_venv/bin/gcovr \
  --campaign "<NAME>=$R/runs/stage7/<glob>" --out $R/<name>_code.json
```

---

## 1. Ablation repeats (required)

**Why.** Reviewer 1: "Please repeat the main comparison and the ablation several times per
configuration, report mean and dispersion". Reviewer 2 asks for feedback removed with the
controller kept, and redirection removed with feedback kept. These are A1 and A2. We have one
run of each variant.

**Current single-run results:**

| Variant | Feedback | Steering | Bugs (of 8) | Boundary points (of 79) | Ranges (of 51) | Lines |
|---|---|---|---|---|---|---|
| Full (5 runs) | yes | yes | 8 | 31–34 | 45–47 | 1,467–1,473 |
| A2 | yes | no | 8 | 30 | 47 | 1,473 |
| A1 | no | yes | 8 | 22 | 27 | 1,462 |
| A0 | no | no | 7 | 17 | 23 | 1,440 |

**What runs.** 12 runs: A0, A1 and A2, runs 2–5. The existing `llm_A0/A1/A2.jsonl` count as run 1.
Cost per set of three in Stage 7: A0 $4.82 + A1 $6.49 + A2 $14.28 = $25.59, so about $102 for
four sets.

```bash
mkdir -p /tmp/abl
for v in A0 A1 A2; do for r in 2 3 4 5; do
  $PY llm_fuzzer/main.py --ablation $v --prompt-version neutral --force --max-iterations 200 \
    --test-cases configs/test_cases_rules_2026-10.json \
    --history-path $R/runs/stage7/llm_${v}_r$r.jsonl \
    --output-dir /tmp/abl/${v}_$r/out --work-dir /tmp/abl/${v}_$r/work \
    > /tmp/abl/${v}_$r.log 2>&1 &
done; done; wait
```

Use two batches of 6 if the machine is too slow with 12 at once (8 cores). Stage 7's 8 runs in
parallel took about 2.3 hours.

**Then.** Score all 15 ablation files (the new ones plus the originals). Compare each variant
with the full fuzzer by exact Mann–Whitney on the three metrics. With 5 vs. 5 runs the smallest
possible p is 0.008.

**Done when:** the ablation table has mean ± SD for 5 runs per variant, and reply R1-3 and R2-6
can be closed. Whatever the runs show is reported as it is.

## 2. Expert check of the judge AI (required; a person, not a run)

**Why.** Reviewer 2: "assess the judge's accuracy and error types against a reference set of
rules verified by domain experts using the specification."

**What exists.** `evaluation/results/revision/judge_expert_worksheet.xlsx`: 108 rules, the same
sample GPT-5 already judged, with the AI verdicts hidden and an instructions sheet. The expert
needs the ARINC 664 Part 7 PDF, which is not in the repository.

**Who.** One expert labels all 108. If there are two, both label rows 1–30 and one labels rows
31–108.

**After it comes back:**

```bash
python evaluation/revision/expert_worksheet.py merge --filled <filled.xlsx> --expert <initials>
python evaluation/revision/audit_final_rules.py score --reference expert
```

**Done when:** we report accuracy, κ, the confusion table and error types for the audit judge
against the expert, and also for GPT-5.

## 3. Reward-weight sensitivity (recommended)

**Why.** Reviewer 1: "these must be reported, ideally with a brief sensitivity check." The
student's argument was that the variant which never sees the reward (A1) matches the full
fuzzer, so the weights do not matter. **That argument holds only for Rule Coverage, which is
removed.** On the new metrics A1 reaches 22 boundary points against 31–34 for the full fuzzer.
Without this experiment the letter can only say that no sensitivity check was done.

**Fixed before running** (reported whatever they show; default is λ_imp, λ_viol, λ_nov, λ_rep =
0.5, 0.6, 0.3, 0.2):

| Setting | λ_imp | λ_viol | λ_nov | λ_rep | Idea |
|---|---|---|---|---|---|
| S1 equal | 0.4 | 0.4 | 0.4 | 0.4 | No term preferred |
| S2 exploration | 0.25 | 0.3 | 0.6 | 0.4 | Effect terms halved, exploration terms doubled |

**Steps.**
1. Add `--reward-weights a,b,c,d` to `llm_fuzzer/main.py`, passed to `RewardCalculator`. The
   defaults stay the same. One commit, with a test.
2. Run the full fuzzer 3 times per setting: 6 runs × about $16 = about $96. Same command as
   experiment 1, with `--ablation full`, history files `llm_full_S1_r1..3.jsonl` and
   `llm_full_S2_r1..3.jsonl`.
3. Score them and compare with the 5 default runs. With 3 vs. 5 runs the smallest possible p is
   0.036.

**Done when:** one short table is in the paper and reply R1-4a is closed.

## 4. Boundary combinations (recommended, free)

**Why.** Reviewer 2: "report coverage of boundary values and combinations of conditions within
each rule category, and assess how testing depth affects bug detection." Boundary values are
done. Combinations are not.

**Definition, fixed before computing.** Each test is reduced to its classes on four independent
fields: frame size, timing, sequence number, MAC address (`boundary_coverage.classify`, range
level). A combination is a pair of classes from two different fields, on the same VL, in the same
test. The universe is every such pair, the same list for all fuzzers.

**Steps.**
1. Add `combination_coverage()` to `boundary_coverage.py`, with hand-checked unit tests.
2. Compute it per run from the logged inputs. No simulator run and no LLM.
3. For depth vs. detection, report per bug how many detecting inputs hit a boundary point and
   how many hit only a range (`per_bug_classes` already produces most of this).

**Note.** Boofuzz changes one field per test by design, so its combination count will be close
to zero. The Peach-rule random and the LLM change several. State this next to the result.

**Done when:** a row is added to the main table and reply R2-4 mentions it.

## 5. Mutation testing (optional, free)

**Why.** Reviewer 2: "How were the eight injected bugs selected, and what evidence supports their
representativeness". A tool generates faults with no human choice, so the authors do not pick
them.

**Fixed before running.**
- Tool: `universalmutator` (pip, text-based, no LLVM needed; neither Mull nor clang is installed).
- Scope: `examples/AFDX_V3/model/afdx-switch.cc` and `afdx-end-system.cc`, the checking code.
- Sample: a random sample of mutants with a fixed seed, size set after the pilot.
- A mutant counts as detected if any counter from `parse_metrics` differs from the unmutated
  simulator for at least one input of the run. No bug-specific signal.
- Mutants that fail to compile are discarded. Mutants that no fuzzer detects are reported as
  undetected, with the caveat that some change nothing observable.

**Steps.**
1. Pilot on one file: count mutants, time one rebuild and one replay. Then decide the sample size
   that fits.
2. Work in a separate copy, `/tmp/ns3_mut`. Never edit `/tmp/ns3_fixtest`.
3. Replay the logged inputs of the 11 paper runs per mutant.
4. Report the mutation score per fuzzer, with Mann–Whitney for LLM vs. Random.

**Done when:** one row is in the main table and reply R2-1 cites it.

## 6. Larger topologies (reviewer request; hardest)

**Why.** Reviewer 2: "The authors should evaluate configurations with varying numbers of
transmitting end systems, hop counts, and delay differences between redundant paths."

**What has to change.** `examples/AFDX_V3/simulations/afdx-demo.cc` hard-codes 3 end systems
(`es1`, `es2`, `es3`, lines 622–646 and 678–721) and one switch per network, star only.

**Fixed before running: one factor changed per topology.**

| Topology | Change from the reference | New settings |
|---|---|---|
| T-ES | More transmitting end systems | 6 ES, about 16 VLs |
| T-HOP | Two switches in a row per network | ES → SW1 → SW2 → ES |
| T-SKEW | Delay difference between redundant paths | Network B links slower than network A (values to fix) |

**Steps.**
1. Make the number of end systems, the hops and the per-network delay configurable from the
   command line, in the repository's `examples/AFDX_V3` and a new copy under `/tmp`. The default
   must reproduce the reference topology exactly: same counters on the existing inputs.
2. For each topology: a VL table, then a normal-traffic run with no drops or rejections.
3. **Recalibrate per topology.** The reward's reference counters (`BASELINE_RECEIVED = 3380` and
   others in `reward_calculator.py`) are for the reference topology. The boundary list comes from
   the VL table, and the 10-bug acceptance checks must be repeated.
4. Runs per topology: LLM 3, Random 3 seeds, boofuzz 1. About $48 per topology, about 3 hours.
5. Score with the three metrics.

**Decision.** Three topologies cost about $144 and about 3 days in total, which does not fit
13 Nov without an extension. If there is no extension, the options are one topology (T-ES, the
reviewer's first item), or a stated limitation.

**Done when:** a table per topology is in the paper and reply R2-3 is closed.

## 7. NAV case study (only if we keep effectiveness claims)

The submitted paper reports "distinct rule/mutation labels" and "reward ≥ 2.2", which are not
among the new metrics. No reviewer asked about NAV. `examples/AFDX_NAV` is a separate copy of the
simulator, and its files differ from `AFDX_V3`.

- **Shorten** to "the pipeline extracts 8 NAV rules and the loop runs 200 iterations", or
  **remove** it: no run needed.
- **Keep effectiveness claims:** apply the same simulator changes to `AFDX_NAV`, then run the LLM
  once (about $16) and score it. Not recommended.
