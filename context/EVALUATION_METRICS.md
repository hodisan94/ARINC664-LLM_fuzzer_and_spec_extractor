# Evaluation metrics independent of our method: bug detection and code coverage

**Written:** 2026-11-05. **Branch:** `fix/revision-bugs`. Related: `PAPER_CHANGES.md` 4.8–4.10,
`BUG_SUITE.md`, `BOOFUZZ_MODEL_PLAN.md` §8.3 (principles P1–P2), `RANDOM_MODEL_PLAN.md`.

**Status:** bug detection is implemented and in use (`bdr_replay.py`); code coverage is being
implemented (`evaluation/revision/code_coverage.py` written; the instrumented simulator is
being built).

---

## 1. Why these two metrics

The paper's headline metric, Rule Coverage, counts categories of our own extracted rules,
reached through rule labels that the fuzzers declare about their own tests. It depends on our
pipeline and favors the LLM-guided fuzzer by construction (Reviewer 1, comment 2; a fuzzer that
walks the rule list reaches 184 of 185 categories without testing them). The evaluation needs
metrics that depend only on **what happened in the system under test**: what the simulator
received and what its code did.

### What the fuzzing-evaluation literature recommends

G. Klees, A. Ruef, B. Cooper, S. Wei, M. Hicks, **"Evaluating Fuzz Testing"**, ACM CCS 2018
(arXiv:1808.09700). The authors examined the experimental evaluations of 32 fuzzing papers and
report finding problems in every one. Quotes below are from the arXiv HTML version
(https://arxiv.org/html/1808.09700v2), sections 1 and 4, read on 2026-11-04:

- On code coverage: "14 out of 32 papers we examined used code coverage to assess fuzzing
  effectiveness." Coverage "intuitively correlates with finding more bugs", but "the
  correlation may be weak, so directly measuring the number of bugs found is preferred."
- On ground truth: "A better approach is to measure against ground truth directly", i.e. known
  bugs, rather than heuristics such as "unique crashes".
- On statistics: researchers "should perform multiple trials and use statistical tests"; "one
  should use the Mann Whitney U-test" to compare fuzzers.

**Consequence for our evaluation:**

| Role | Metric | Section |
|---|---|---|
| **Primary** | Bug detection against a known set of injected bugs (ground truth) | 2 |
| Secondary, independent | Code coverage of the simulator | 3 |
| Testing depth (Reviewer 2) | Boundary-value coverage | `PAPER_CHANGES.md` 4.8 |
| Secondary, not independent | Rule Coverage (labels), with the explanation above | `PAPER_CHANGES.md` 4.1–4.3 |

All fuzzers are scored by the same scripts, from the simulator inputs recorded in their run
histories, with several runs per fuzzer and exact two-sided Mann–Whitney U tests
(`analyze_campaigns.mann_whitney_exact`). Metrics are fixed before results are looked at and
reported whatever they show (P2).

---

## 2. Bug detection (primary metric)

### 2.1 What it measures

Whether a fuzzer's tests expose known faults. Ten faults are planted in the simulator, each
switched on by a flag; a fault counts as found if at least one of the fuzzer's tests makes the
faulty simulator behave observably differently from the correct one. The faults are the ground
truth.

### 2.2 The injected bugs

Fixed before the Stage 7 campaigns ran (commit `b2e6ef8`), each with two acceptance checks
(details: `BUG_SUITE.md`, sections 2–5). Catalogue: `evaluation/compute_bdr.py`, `BUGS`.

| Bug | What the faulty simulator does | Where | Detection signal |
|---|---|---|---|
| `skip_bag_policing` | Switch skips BAG timing enforcement | `afdx-switch.cc` | fewer BAG-policing drops |
| `skip_frame_validation` | Switch skips frame-size validation | `afdx-switch.cc` | fewer frame-size drops |
| `skip_mac_validation` | Switch skips the source-MAC check | `afdx-switch.cc` | fewer MAC drops |
| `skip_token_bucket` | Switch skips token-bucket policing | `afdx-switch.cc` | fewer token-bucket drops (**unreachable**) |
| `skip_vl_check` | Switch skips VL authorization | `afdx-switch.cc` | more frames forwarded (**unreachable**) |
| `skip_constant_field` | End system skips the constant-field MAC check | `afdx-end-system.cc` | fewer receiver rejections |
| `skip_sequence_check` | End system skips the sequence-number check | `afdx-end-system.cc` | fewer receiver rejections |
| `accept_oversized` | Switch skips the upper frame-size bounds (MaxFrame, 1,518 bytes) | `afdx-switch.cc` | fewer frame-size drops |
| `max_frame_off_by_one` | Switch accepts a frame 1 byte above the VL's MaxFrame | `afdx-switch.cc` | fewer frame-size drops |
| `loose_bag_tolerance` | Switch BAG check allows 10% early arrival instead of 1% | `afdx-switch.cc` | fewer BAG-policing drops |

Two bugs are **unreachable** through the simulator's inputs: with the BAG check in front of it
the token bucket never drops a frame, and no input can set an unknown VL id
(`REVISION_FINDINGS.md` Bugs 7–8). Results are reported as found of 10 and found of the 8
reachable.

### 2.3 How it is computed

By **replay** (`evaluation/revision/bdr_replay.py`), not by running the fuzzers against faulty
simulators:

1. Every run history records the exact simulator input of each test (`sim_config`).
2. Each distinct input is run once on the correct simulator (`inject_bug = "none"`) and once
   on each faulty variant. The simulator is deterministic, so one run per input and variant is
   enough; results are cached and shared between fuzzers.
3. A test **detects** a bug when the bug's counter differs between the two runs in the expected
   direction by at least one frame (`compute_bdr.bug_detected`, threshold 0.5). Example:
   `skip_bag_policing` is detected when the faulty switch drops fewer frames for BAG violations
   than the correct one.
4. A bug is **found** by a run when at least one of its tests detects it.
5. Inputs that crash the simulator count as not executed.

### 2.4 What is reported

- Bugs found per run (of 10 and of the 8 reachable); mean, spread and Mann–Whitney p per pair
  of fuzzers.
- For each bug: which runs found it, how many tests detected it, and the first test that did
  (iterations to first detection).
- For each bug, which boundary classes its detecting inputs hit (`boundary_coverage.py`,
  `per_bug`), which links testing depth to detection (Reviewer 2).

### 2.5 Limitations, to state in the paper

- **The bugs are ours.** They were chosen and fixed before the campaigns, with acceptance checks,
  but they are planted faults, not faults found in a real AFDX product; their representativeness
  is a limitation (Reviewer 2's question).
- **Some bugs need specific inputs by design**, e.g. `max_frame_off_by_one` is found only by a
  frame of exactly MaxFrame+1 bytes. Report which inputs each bug needs; do not claim that a
  fuzzer's strategy caused a detection when the bug was built around a boundary.
- **Eight reachable bugs are a small set**, so differences of one bug should not be overstated.

### 2.6 Draft paragraph for the paper

> Following Klees et al. [ref], we use bug detection against a known ground truth as the primary
> measure of fuzzing effectiveness. We inject ten faults into the simulator, each disabling or
> weakening one validation of the switch or the end systems, and fixed the list before running
> the campaigns. Detection is measured by replay: every distinct simulator input recorded in a
> campaign is executed on the correct simulator and on each faulty variant, and a test detects a
> fault when the corresponding drop or rejection counter differs by at least one frame. A fault
> is found by a run if at least one of its tests detects it. Two of the ten faults cannot be
> exposed through any input of the simulator; we report results over all ten and over the eight
> reachable faults, over several runs per fuzzer, with exact two-sided Mann–Whitney U tests.

---

## 3. Code coverage of the simulator (secondary metric)

### 3.1 What it measures

The simulator is a program. Code coverage measures which parts of its code ran while the
fuzzer's tests were executed:

- **Line coverage:** the share of code lines that ran at least once.
- **Branch coverage:** for each condition (`if`, `switch`, loop test), whether each of its
  outcomes was reached. Example: the switch's frame-size check has a "drop" branch that runs
  only if some test sent a frame larger than the VL allows.

It counts only what ran in the simulator, so it depends on no rule, label or table of ours, and
it is computed for every fuzzer in exactly the same way. Following Klees et al., it is reported
as a secondary metric next to bug detection.

### 3.2 Scope

Only the AFDX code is measured, not the ns-3 library it runs on:

| File | Content |
|---|---|
| `examples/AFDX_V3/model/afdx-switch.cc` | Switch: frame validation, MAC and VL checks, BAG policing, token bucket, forwarding |
| `examples/AFDX_V3/model/afdx-end-system.cc` | End system: reception, redundancy, constant-field and sequence checks |
| `examples/AFDX_V3/model/afdx-traffic-generator.cc` | Sender: frame construction and the input mutations |
| `examples/AFDX_V3/model/afdx-frame.cc`, `afdx-virtual-link.cc` | Frame and VL objects |
| `examples/AFDX_V3/simulations/afdx-demo.cc` | Scenario: topology, configuration, reading the mutation file |

### 3.3 Tools

- **gcov** (part of GCC 13.3, the compiler of the simulator build): code compiled with
  `--coverage` writes, when the program exits, how many times each line and branch ran (files
  `.gcda`, next to the compile-time notes `.gcno`). Counts from several runs of the same build
  add up.
- **gcovr** (a Python package, installed in a separate environment `~/cov_venv` in WSL) reads
  gcov's data and reports line and branch coverage per file and in total.
- Python's `coverage.py` does not apply: it measures Python code, i.e. the fuzzers, not the
  C++ simulator.

### 3.4 The instrumented simulator

A separate copy of the fixed simulator (`/tmp/ns3_fixtest`, the build used for every Stage 7
run and for bug detection) is made at `/tmp/ns3_cov` and built with the compiler flag
`--coverage` (`CXXFLAGS="--coverage" LDFLAGS="--coverage"`, same modules and profile as the
fixed build). ns-3's own `--enable-gcov` option was not used because it requires the `lcov`
package, which is not installed. The source is identical to the fixed simulator; only the
compiler flag differs, so the simulator behaves the same. Script:
`evaluation/revision/build_coverage_simulator.sh`.

### 3.5 How it is computed (`evaluation/revision/code_coverage.py`)

For each run of each fuzzer:

1. Read the run's successful records exactly as the bug replay does (`logged_campaign`) and keep
   its **distinct** simulator inputs (an identical input runs identical code, so repeats add
   nothing).
2. **Delete the coverage counters** (`.gcda`) of the instrumented build, so the run starts from
   zero.
3. **Run every distinct input** on the correct simulator (`inject_bug = "none"`), several in
   parallel, each in its own working directory. gcov adds up the counts of all of them.
4. **Report** with gcovr, restricted to `examples/AFDX_V3/`, with throw branches and branches
   the compiler marks unreachable excluded (standard for C++ coverage): lines covered of total,
   branches covered of total, overall and per file.

Then, per fuzzer: mean, spread, and exact Mann–Whitney p for each pair of fuzzers.

**Baseline.** The unmutated input alone (normal traffic, no fuzzing) is measured as well. It
shows how much of the code normal traffic already runs; what a fuzzer adds is the difference.

**Runs measured:** the LLM-guided fuzzer (5 runs), the model-based random baseline (5 seeds),
boofuzz as is (1 deterministic run), the ablations A0/A1/A2 (1 run each), and for reference
the student's random and BOOFUZZ-style baselines.

### 3.6 Checks before using the numbers

- **Parallel runs:** gcov merges counts from processes that write the same files. The coverage of
  one run is computed both in parallel and one input at a time; the two must be identical.
- **Same behavior:** for a sample of inputs, the drop and rejection counters of the instrumented
  simulator must equal those of the fixed simulator.
- **Reproducibility:** measuring the same run twice gives the same numbers.

Script: `evaluation/revision/check_code_coverage.py`. **Result (2026-11-05),** 24 distinct inputs
of `llm_full_r1`: parallel 1,459 lines and 1,916 branches, one at a time the same, a repeat the
same, per file as well; counters of the instrumented and the fixed simulator identical for 8 of
8 inputs. All three checks pass. The unmutated input alone covers 1,322 of 2,213 lines (60%) and
1,768 of 7,758 branches. (The branch total is large because ns-3's logging and assertion macros
expand into many branches; report lines as the main coverage number and branches alongside.)

### 3.7 Limitations, to state in the paper

- **The simulator is small** and normal traffic already runs much of it, so coverage may differ
  little between fuzzers. It is reported whatever it shows (P2).
- **Coverage is not bugs** (Klees et al.): code that ran is not code that was checked for the
  right outcome. That is why bug detection is the primary metric.
- **What the simulator does not implement cannot be covered** (e.g. IP fragmentation; see
  `PAPER_CHANGES.md` 4.5a), for any fuzzer.

### 3.8 Draft paragraph for the paper

> As a secondary, implementation-independent measure, we report line and branch coverage of the
> simulator's AFDX code (switch, end-system and traffic-generator models and the scenario), the
> measure most often used in fuzzing evaluations [Klees et al.]. We compile a separate copy of
> the simulator with gcov instrumentation, replay every distinct simulator input recorded in a
> campaign on the correct simulator, and report coverage with gcovr, excluding exception and
> unreachable branches. The coverage of the unmutated traffic is reported as a reference point.
> Coverage does not depend on the rule base, the rule labels or any mapping of ours; it reflects
> only which code the fuzzers' inputs executed.

---

## 4. Order of work

1. Bug detection for the new baselines (model-based random, boofuzz as is): replay running.
2. Code coverage: build the instrumented simulator, run the checks of 3.6, then all runs.
3. Report both, with the boundary-value coverage, in one table per fuzzer, and update
   `PAPER_CHANGES.md`.
