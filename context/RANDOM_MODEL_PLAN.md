# Plan: a model-based random baseline

**Status:** plan only, nothing implemented. Written 2026-11-04.
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

**The three fuzzers then differ only in how they choose values:** the LLM-guided fuzzer plans
them, boofuzz walks its systematic values, the random fuzzer draws from the full range.
Everything else is shared: the same fields, the same adapter to the simulator, the same
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
2. a field, uniformly among the 6;
3. a value, uniformly from that field's range (3.1);
4. the adapter turns it into the simulator input.

One field per test, as in boofuzz, so the two baselines differ only in how the value is chosen.

**Expected properties, to state in the paper (not reasons to change the design):** with a
uniform draw, most frame sizes are above 9,000 and arrive as 9,000-byte frames; half of the
timing draws are below −BAG and all send at the 100 µs floor; most of the rest are very slow
offsets. Exact boundary values (e.g. MaxFrame+1) are rare. That is how random fuzzing behaves.

## 4. Open questions

| # | Question | Recommendation |
|---|---|---|
| R1 | Skip a draw whose simulator input equals an earlier one, as the boofuzz baseline does? | **No.** Repeats are part of random fuzzing; report the number of distinct inputs |
| R2 | One field per test, or a random number of fields? | **One**, as boofuzz, so that only value selection differs |
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
   - each test mutates exactly one field;
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
