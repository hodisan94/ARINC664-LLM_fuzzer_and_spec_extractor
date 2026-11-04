# Plan: a model-based random baseline

**Status:** plan only, nothing implemented. Written 2026-11-04. Proposals accepted the same day,
including 16-bit timing for both baselines (3.2) and several fields per test for the random
baseline (3.4).
**Branch:** `fix/revision-bugs`. Related documents: `BOOFUZZ_MODEL_PLAN.md` (the model this plan
reuses; principles P1–P2 in its section 8.3), `REVISION_FINDINGS.md` (Bugs 24, 31, 32, 33),
`PAPER_CHANGES.md` (4.6a, 4.8, 4.9).

---

## 1. Why a new random baseline

The current random baseline (`random_baseline/random_strategy_generator.py`, 210 lines, written
by the student) works as follows (line numbers of that file):

1. **A random VL** (line 107) and **a random rule label from the test-case list** (lines 64, 110):
   `protocol_rule = random.choice(self.available_rules)`, where `available_rules` is
   `list(self.test_cases.keys())`.
2. **A coin flip between two modes** (lines 66, 113).
   - **"predefined"** (lines 120–128): picks 1–3 test-case numbers (TC0, TC1, …) and sets no
     simulator field. The test-case values never reach the simulator (Bug 24), so this mode sends
     normal traffic.
   - **"custom"** (lines 131–142): chooses the field from **words in the label** and draws the
     value **from a short fixed list**:

     | Label contains | Field | Fixed list |
     |---|---|---|
     | "bag" | BAG | 0, 1, 2, 3, 4, 16, 32, 64, 128 |
     | "frame" or "ethernet" | Frame size | 0, 17, 63, 65, 1518, 1519, 2000, 10000 |
     | "sequence" | Sequence number | −1, 0, 256, 65535, 99999 |
     | "mac" or "address" | Source MAC change | spoof_src, spoof_dst, broadcast, invalid_src, zero_mac |
     | none of these | BAG **and** frame size | BAG 0, 1, 2, 3; size 0, 63, 1519, 5000 |
3. **Four extras, 10% each** (lines 145–154), independent of the label: drop probability
   (0.1–1.0), source MAC (3 types), sequence override (0, 1, 127, 255), destination MAC (3 types).

**What happened in Stage 7 run `random_s1` (200 tests):** 90 "predefined" tests, 62 of which
sent no change at all; 110 "custom" tests, 75 of which had a label with none of the words and so
changed BAG and frame size together, unrelated to the label. Most frequent frame sizes: 1519
(27), 5000 (21), 0 (20), 63 (18). Examples: test 5, label
`Switch Performance.interframe_gap_minimum`, frame size 10,000 (sent as 9,000); test 0, label
`switch_timing.delayed_frame_latency_formula`, "predefined" with TC0 and TC3, no change sent.

**Problems** (REVISION_FINDINGS Bugs 24, 31, 32, 33): tied to the test-case list; decisions by
keywords; half of the tests in a mode that sends nothing; values from short fixed lists that do
not depend on the VL; a requested sequence number 0 is ignored. This is not random fuzzing as
the literature means it (random values over an input's range).

**Decision (2026-11-04):** add a model-based random baseline, in the spirit of "boofuzz as is"
(BOOFUZZ_MODEL_PLAN D6). The student's baseline stays in the repository unchanged.

## 2. Principles (from BOOFUZZ_MODEL_PLAN §8.3)

- **P1.** The same information for every fuzzer, and no human test rules. The configuration of
  each fuzzer is fixed by fairness alone, before looking at results.
- **P2.** No fuzzer, and no choice of variant, is tuned toward one metric. All metrics are fixed
  in advance and reported whatever they show.

## 3. Design

**The three fuzzers then differ only in how they choose tests:** the LLM-guided fuzzer plans
them, boofuzz walks its systematic values one field at a time, the random fuzzer draws a random
set of fields and random values from their full ranges (3.4). Everything else is shared: the same fields, the same adapter to the simulator, the same
simulator, the same history format, the same metrics.

**Reused from `boofuzz_model_baseline/`:** the field list, the adapter (`adapter.py`: one
mutated field → the 9 simulator keys, including frame-size clamping to 18–9,000 bytes, timing
floored at −BAG, and sequence number 0 sent as 256), the VL table loader, and the run loop's
history format.

**Not used:** the test-case list, the rule list, rule labels (`protocol_rule` is empty), and the
VL table as a source of test values (P1: boofuzz as is does not get it either). The VL table is
used only to send each test to an existing VL, as in every fuzzer.

### 3.1 Fields and ranges

| Field | Range drawn from | Why this range |
|---|---|---|
| Frame size (bytes) | 0 … 65,535 (16-bit) | The same field as boofuzz. Already beyond what the simulator can send: it clamps every frame to 18–9,000 bytes, so all fuzzers reach 9,000 and larger values arrive identical |
| Timing offset (ms) | **−32,768 … +32,767 (16-bit signed)** | See 3.2 |
| Sequence number | 0 … 255 (8-bit) | The AFDX field is 8 bits; the simulator keeps the low 8 bits (256 → 0). A real limit of the protocol |
| Source MAC change | one of `spoof_src`, `spoof_dst`, `broadcast`, `invalid_src`, `zero_mac` | All types the simulator supports |
| Destination MAC change | one of `corrupt_prefix`, `wrong_vl`, `zero` | All types the simulator supports |
| Drop probability | uniform in (0, 1] | The whole meaningful range |

### 3.2 The range question (raised 2026-11-04)

**Question:** should the random fuzzer get a wider range than the fields' own, so that it can
reach large values like the other fuzzers?

**What the fuzzers actually sent in Stage 7** (from the logged simulator inputs; values, not
metrics):

| Fuzzer | Frame sizes sent | Timing offsets sent | Sequence overrides |
|---|---|---|---|
| LLM (5 runs) | 20–9,000 | −100 … +746 ms | 1–256 |
| Random, student's (5 runs) | 18–9,000 | −32 … +24 | 1–99,999 |
| BOOFUZZ-style sweep | 18–8,193 | −33 … +1,284 | 255 |
| Model-based BOOFUZZ, as is | 18–9,000 | −32 … +127 | 1–256 |

**Answer:**
- **Frame size: no wider range.** 0–65,535 already exceeds the simulator's 9,000-byte cap.
- **Timing: yes.** An 8-bit signed field (−128 … +127 ms, as first planned and as in the
  model-based BOOFUZZ) cannot hold offsets the LLM sent (+746 ms). So the timing field becomes
  **16-bit signed for both the random and the boofuzz baseline**, so that every fuzzer uses the
  same field model.
- **Sequence number: no.** 8 bits is the protocol's field.

**Principle:** the range is fixed by what the field must be able to hold (every value any fuzzer
may send), not by what improves a result (P2). Only the requested values were looked at, not
their metrics.

**Consequence:** the model-based BOOFUZZ (`--mode boofuzz`, the paper's variant, D6) must be
re-exported with a 16-bit signed timing field and re-run (free). Its earlier run stays in the
repository as the 8-bit version.

### 3.3 How a test is drawn

Each test, with a seeded random generator:
1. a VL, uniformly among the 8;
2. the set of fields to mutate, by Peach's rule (3.5): a number k uniformly from 1…6, then k
   fields uniformly without replacement;
3. for each chosen field, a value uniformly from its range (3.1);
4. the adapter turns them into the simulator input (it must accept several fields at once; the
   boofuzz baseline's adapter takes one).

**Expected properties, to state in the paper (not reasons to change the design):** with a
uniform draw, most frame sizes are above 9,000 and arrive as 9,000-byte frames; half of the
timing draws are below −BAG and all send at the 100 µs floor; most of the rest are very slow
offsets. Exact boundary values (e.g. MaxFrame+1) are rare. That is how random fuzzing behaves.

### 3.4 Several fields per test (raised 2026-11-04)

**Question:** should the random fuzzer mutate several fields in a test, for fairness?

**Fields mutated per test in Stage 7** (logged simulator inputs):

| Fuzzer | 0 fields | 1 | 2 | 3 or more |
|---|---|---|---|---|
| LLM (5 runs) | 1% | 34% | 62% | 2% |
| Random, student's (5 runs) | 30% | 29% | 30% | 11% |
| BOOFUZZ-style sweep | 34% | 39% | 18% | 9% |
| Model-based BOOFUZZ | 0% | 100% | 0% | 0% |

**Decision: several fields for the random baseline; one for the boofuzz baseline.**
- **Random:** random fuzzers usually stack several random changes on one input; one field at a
  time is a systematic method, characteristic of boofuzz. The LLM fuzzer combines fields in most
  tests (62% mutate two), so a one-field random fuzzer would be confined to a narrower space of
  tests than the LLM. The student's random baseline also combined fields.
- **The rule:** first proposed as each field independently with probability ½; replaced by
  Peach's published rule (3.5, decided 2026-11-04). Fixed before any run. It deliberately does not copy the LLM's distribution (mostly two fields), which would
  copy the strategy of the method under comparison (P1).
- **boofuzz stays at one field per test within the budget.** Checked in boofuzz 0.4.2's own code
  (`sessions/session.py`, `fuzz(max_depth=None)` and `_generate_mutations_indefinitely`):
  boofuzz first yields every one-field mutation (depth 1), and only after all of them moves on to
  pairs of fields (depth 2), then triples, and so on; `max_depth=1` is "simple" fuzzing. With our
  model there are 302 one-field tests, more than the 200-test budget, so boofuzz as is never
  reaches the pairs. One field per test within 200 tests is therefore what boofuzz itself does.
- **To state in the paper:** more fields per test is not better by construction. A test with an
  oversized frame and a spoofed source MAC is dropped at the switch's size check and never
  reaches the MAC check. The rule is meant to make the baseline a typical random fuzzer, not to
  make it win (P2).

### 3.5 A published random fuzzer to base the design on (looked up 2026-11-04)

**ThreadFuzzer** (I. Siroš, J. Heirwegh, D. Singelée, B. Preneel, KU Leuven; "ThreadFuzzer:
Fuzzing Framework for Thread Protocol", arXiv:2511.17283, 2025, revised 2026; read on arXiv,
venue not confirmed) uses a **Random fuzzer introduced in CovFuzz**, by the same group. Its
definition (Section IV-C2, quoted from the arXiv HTML): it "alters the values of specific fields
within the intercepted packet"; every field gets a mutation probability `p_f = k / |F_P|`, where
"k is a hyperparameter representing the average number of mutated fields per packet". The
paper's coverage-guided fuzzer "extends Random fuzzer". According to a summary of the same page
(not yet checked word for word), the evaluation fixes `k = 2`.

This is the rule of 3.4 in a published, citable form: each field independently, with probability
`k / (number of fields)`. Our "probability ½ per field" is `k = 3` for 6 fields. **Recommendation:
adopt the ThreadFuzzer / CovFuzz Random fuzzer, with the k its authors chose, and cite it** —
after checking `k = 2` in the paper's text (then each of our 6 fields is mutated with probability
1/3). Choosing k from the published design, not from our results, keeps P2.

**Mutating every field in every test** (k = 6) was considered and is not recommended: every test
would carry an oversized or undersized frame size in most draws and be dropped at the switch's
first check, so the other changes (MAC, sequence number) would almost never reach their checks.
It is also not what the published random fuzzers do.

**Peach Fuzzer's random strategy (source read 2026-11-04).** Peach is a widely used
structure-aware ("generation") fuzzer: the tester writes a data model of the message, as in
boofuzz. Its Python 2.x code, `Peach/MutateStrategies/rand.py`, read from a copy kept in the UMass
LASER "CausalTesting_ICSE20" repository
(https://holmes.cs.umass.edu/LASER-UMASS/CausalTesting_ICSE20/blob/58a8a7a3956201a6f3318cd771e1a7d23bedd5a5/Holmes/fuzzers/Peach/MutateStrategies/rand.py;
not the official repository, so cite the Peach version, and check against an official copy if
possible):
- Class `RandomMutationStrategy`, docstring: "This mutation strategy will randomly select N
  fields from a data model to fuzz on each test case."
- `self._n = 7`, overridden by the XML attribute `maxFieldsToMutate`.
- Candidate fields: every mutable element of the data model
  (`dataModel.getAllChildDataElements()`, non-mutable ones removed).
- **Number of fields per test is random, not exactly N:** with more fields than N,
  `fields = self._random.sample(nodes, self._random.randint(1, self._n))`, i.e. a uniform number
  1…N, then a uniform sample of that many fields. With N or fewer fields (our case: 6 ≤ 7), all
  fields are candidates and `self._random.sample(fields, self._random.randint(1, len(fields)))`
  picks a uniform number 1…6 of them (one round, since `maxN = 7 − 6 = 1`).
- Value: for each chosen field, one mutator is drawn from those that support the field
  (weighted by `m.weight ** 4`) and applied with `mutator.randomMutation(node, self._random)`.
  The mutators' own code was not read.
- Seeded: the generator is reseeded every test from the seed and the test number
  (`hashlib.sha512(SEED + iterationCount)`), so a run is reproducible.

**Applied to our 6 fields, Peach's rule is:** draw a number k uniformly from 1…6, then k fields
uniformly without replacement (about 3.5 fields per test on average); a uniform random value for
each (3.1).

**Two published rules, compared:**

| Source | Rule | Fields per test, our 6 fields |
|---|---|---|
| Peach `RandomMutationStrategy` (default `maxFieldsToMutate = 7`) | uniform count 1…min(7, 6), then a uniform set of that size | 1–6, average 3.5 |
| ThreadFuzzer / CovFuzz Random fuzzer | each field independently with probability k / 6 (k = 2 per a summary, not yet checked) | average 2, can be 0 (redrawn) |

**Decided 2026-11-04: Peach's rule.** Peach is a well-known, long-established fuzzer whose random
strategy is exactly "a random number of randomly chosen fields of a message model, each given a
random value", which is what this baseline is; its default needs no tuning for our model
(6 fields ≤ 7). The ThreadFuzzer rule is a reasonable alternative, but its k still has to be
checked and it is a recent arXiv paper.

## 4. Open questions

| # | Question | Recommendation |
|---|---|---|
| R1 | Skip a draw whose simulator input equals an earlier one, as the boofuzz baseline does? | **No.** Repeats are part of random fuzzing; report the number of distinct inputs |
| R2 | One field per test, or a random number of fields? | **Revised 2026-11-04: several fields.** First proposed: ½ per field; then the ThreadFuzzer / CovFuzz rule; **now recommended: Peach's `RandomMutationStrategy` rule** (a uniform number 1…6 of fields, then a uniform set of that size; 3.5). **Decided 2026-11-04: Peach's rule** |
| R3 | Number of runs | **5 seeds** (1–5), as the other random runs and the LLM runs |
| R4 | Budget | **200 tests per run**, as every other fuzzer |

## 5. Steps

1. **Shared timing field.** Change the timing field of the model to 16-bit signed: in
   `export_boofuzz_values.py` (boofuzz's values for the boofuzz baseline) and in the random
   baseline's range. Re-export `boofuzz_values.json` with the boofuzz library; update the unit
   tests.
2. **Code**, a new folder `random_model_baseline/`, nothing existing changes:
   - `generator.py`: draws the tests (3.3) from a seed;
   - `main.py`: the run loop, same history format as the boofuzz baseline, with
     `random_field`, `random_value` and `seed`; `protocol_rule` empty;
   - `README.md`;
   - the adapter and field definitions are imported from `boofuzz_model_baseline/`.
   `.gitignore` must list the new folder (it ignores every path not listed).
3. **Tests:**
   - the same seed gives the same test list; different seeds differ;
   - each test mutates at least one field, and only the fields drawn for it;
   - over many draws, the number of fields is uniform over 1…6 and each field is chosen in
     about 7/12 of the tests (the average share for a uniform count with a uniform subset);
   - every value lies in its field's range;
   - over many draws, each field and VL is chosen in about equal shares;
   - no test-case or rule file is read.
4. **Runs (free):**
   - random: 5 seeds × 200 tests on the fixed simulator;
   - boofuzz as is: re-run with the 16-bit timing field (200 tests).
5. **Scoring** with the same scripts as every fuzzer: `bdr_replay.py` (bugs),
   `boundary_coverage.py` (boundary points and ranges), `analyze_campaigns.py` (distinct inputs,
   tests without mutation). Label metrics do not apply.
6. **Documents:** results in this file; `PAPER_CHANGES.md` (the random baseline's description
   and numbers, the timing-field change for boofuzz); `REVISION_FINDINGS.md` (a note that the
   new baseline avoids Bugs 24, 31, 32, 33).

## 6. Effort and risks

**Effort:** about a working day, including the boofuzz re-run. **Cost:** none (no LLM).

| Risk | Mitigation |
|---|---|
| The new random baseline is weaker than the student's on some metric | Report it (P2); the student's baseline was not random fuzzing |
| Changing boofuzz's timing field after its run | The change follows a stated rule (the field must hold every value any fuzzer sends) and only requested values were inspected; the 8-bit run is kept and both are documented |
| The old random runs are already in the paper's draft numbers | Replace them; keep the old runs in the repository |
