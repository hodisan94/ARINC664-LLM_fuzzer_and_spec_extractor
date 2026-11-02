# Plan: a model-based BOOFUZZ baseline

**Status:** implemented and run on 2026-11-02 (`boofuzz_model_baseline/`, commits `415d132`,
`904af3e`, `919a822` and later). Results in section 7. **Decision D1 was reversed and the
paper's BOOFUZZ variant is `--mode config` (D5); see section 8 before using any number.**
Written 2026-11-02.
**Branch:** `fix/revision-bugs`. Related documents: `REVISION_FINDINGS.md` (Bugs 24, 26–37),
`FIX_PLAN.md` ("Open after Stage 7"), `PAPER_CHANGES.md` (4.8, boundary-value coverage).

---

## 1. Why a new baseline

The current "BOOFUZZ" baseline (`boofuzz_baseline/`) does not use the boofuzz library and does
not work like boofuzz. It walks the test-case list and turns each test case into the 7
simulator fields with keyword rules. The audit after Stage 7 found (details in
`REVISION_FINDINGS.md`, Part C):

| Bug | Problem |
|---|---|
| 26 | Only TC0 of 200 of the 626 rules runs (5% of the test cases) |
| 27 | 27% of the rules get no mutation at all (`pass` for "ip", "switch", "vl_", "priority", …) |
| 28 | Most test-case values (text, structures) are replaced by fixed defaults |
| 29 | Numbers go into the wrong parameter, ignoring units |
| 30 | CRC rules are tested as sequence-number rules |
| 33 | Fixed value lists that do not depend on the VL; only the LLM sees the VL limits |
| 36 | The "AFDX grammar" described in the paper is dead code |
| 37 | Code, README and paper call it industry-standard and exhaustive |

A reviewer who knows boofuzz would not accept this as a BOOFUZZ comparison. Fixing it inside
the existing design would still leave it tied to the test-case list.

**Decision:** add a second baseline that works like real boofuzz, with only the adaptations
needed to drive our simulator. It does not use the test-case list.

## 2. How real boofuzz works

Sources: https://github.com/jtpereyda/boofuzz (README), https://boofuzz.readthedocs.io
(quickstart, static protocol definition), and the source files
`boofuzz/primitives/bit_field.py`, `boofuzz/primitives/string.py`,
`boofuzz/sessions/session.py`. Read on 2026-11-01.

1. **The tester describes the message, not the test values.** A message ("request") is a list
   of typed fields ("primitives") with default values: `s_byte`, `s_word`, `s_dword`
   (integers of 8, 16, 32 bits), `s_string`, `s_static`, `s_group` (a list of allowed
   values), blocks, sizes, checksums.
2. **boofuzz generates the test values itself, per field type.**
   - Integers (`bit_field.py`): it builds "interesting boundaries" from the field width: 0, the
     maximum, and the maximum divided by 2, 3, 4, 8, 16 and 32. Around each boundary it tries
     the values from 10 below to 9 above (only inside the field's range, without repeats).
     For an 8-bit field this includes 0–9 and 246–255. A `full_range` option tries every value.
   - Strings (`string.py`): a fixed library of malformed strings (very long strings, format
     strings such as `%n`, path traversal, command injection, …).
   - Groups: each listed value.
   - The documentation describes a `fuzz_values` option to add the tester's own values to a
     field. In the source we read (`bit_field.py`) we did not find it implemented for integer
     fields; this is checked in step 1.
3. **One field at a time.** Each test case mutates one field; the other fields keep their
   defaults. The order is fixed and repeatable; nothing is learned from results.
4. **Delivery and failure detection.** Each test case is rendered to bytes and sent to a target
   through a connection (TCP, UDP, raw socket, serial). Monitors detect crashes and restart the
   target.

Even real boofuzz takes integer boundaries from the field **width**, not from protocol limits
such as MaxFrame = 512, unless the tester adds them.

## 3. Decisions taken

| # | Question | Decision | Reason |
|---|---|---|---|
| D1 | Add the AFDX limits as the tester's own values (MinFrame/MaxFrame per VL, BAG±1 per VL, 1,518)? | ~~Yes, and say so in the paper~~ **Reversed on 2026-11-02, see section 8 and D5.** Kept only as the reference variant `--mode expert` | Original reason: a tester writing an AFDX model would know them; it is the same VL table the LLM receives (Bug 33); boofuzz documents this kind of addition (`fuzz_values`). Why it was wrong: section 8 |
| D2 | Replace the current baseline, or add a new one? | **Add.** Keep the current one under an accurate name ("BOOFUZZ-style test-case sweep") | The current one is the only label-based baseline besides random, so it keeps the Rule Coverage comparison that the paper needs; the new one answers how a real tool performs |
| D3 | Use the test-case list? | **No** | Real boofuzz does not read rule lists; extracting the rules is part of our contribution |
| D4 | Change the simulator so that sequence number 0 can be sent? | **No** (see step 2) | Not needed: an override of 256 already sends 0 |
| D5 | Which variant is the BOOFUZZ result of the paper? (2026-11-02) | **`--mode config`**: each VL's frame-size field is declared with that VL's maximum (boofuzz's `max_num`), and boofuzz generates every value itself | It gives boofuzz exactly the information the LLM gets (the VL table) and no human test rule (principles P1–P2, section 8) |

## 4. Open questions (to settle before or during implementation)

| # | Question | Recommendation |
|---|---|---|
| Q1 | Test order within the 200-test budget (step 4) | Interleave fields, and inside a field spread over boundary groups; document as a budget adaptation |
| Q2 | Skip test cases that reach the simulator as an identical input (e.g. 10,000 and 65,535 are both sent as 9,000 bytes)? | Yes, and report how many were skipped |
| Q3 | Width and sign of the timing field | 8-bit signed (−128…127 ms); confirm boofuzz's signed handling in step 1 |
| Q4 | Values for the drop-probability group | 0.1, 0.5, 1.0 (the simulator's other fuzzers use values in this range) |
| Q5 | Library version | Pin the version installed in step 1 and cite it in the paper |

---

## 5. Steps

### Step 0: decisions

Done: D1 and D2 accepted (2026-11-02). D1 was reversed the same day and replaced by D5
(section 8).

### Step 1: check how to get boofuzz's values (about half a day)

**What it means.** We want boofuzz itself to produce the list of values it would try for each
field, for example "all the values boofuzz would try for a 16-bit integer field". Normally
boofuzz produces these values while it runs a fuzzing session against a network target. We do
not have a network target, we have a simulator that reads 7 numbers from a file. So the
first step is to check whether the library can give us the value list **without** running a
session against a network target.

**What to do.**

1. Install the boofuzz library in the project's Python environment (the WSL venv used for all
   runs), and record the exact version in the requirements.
2. Define one field of each type we need (16-bit integer, 8-bit integer, signed 8-bit integer,
   group) and ask the library for its list of mutations.
3. Compare the list with the rule in `bit_field.py` (section 2), to make sure we understand it.
4. Check whether `fuzz_values` (adding the tester's own values) works for integer fields.

**Outcomes.**

- If the library gives the lists directly: the new baseline calls the library. This is the
  strongest answer to a reviewer: the values come from boofuzz itself.
- If not: copy the value rule from the library's source into our code, with the version and a
  reference to the file, and test that our list equals what the library produces.
- If `fuzz_values` is not implemented for integers: add the AFDX values (D1) ourselves, after
  boofuzz's values, and say so.

### Step 2: sequence number 0, without changing the simulator

**The problem (Bug 31).** The simulator treats a sequence override of 0 as "no change". boofuzz
will try 0 for the sequence field, since 0 is one of its boundaries.

**Considered and rejected:** changing the simulator so that "no change" has its own marker.
That changes simulator code, needs a rebuild, the bug-suite checks again, and raises the
question of re-running earlier campaigns.

**Chosen solution (D4).** The simulator keeps only the low 8 bits of the override
(`& 0xFF`, `afdx-traffic-generator.cc:335`), so an override of **256 sends sequence number 0**.
The new baseline's adapter (step 5) translates 0 → 256 before writing the simulator input.

- No change to the simulator, no rebuild, no effect on any earlier result.
- The boundary-coverage script already counts an override of 256 as sequence number 0.
- The logged `sim_config` will show 256; the README and the paper explain why.
- Every LLM run already reached sequence 0 this way.

Negative values cannot appear: the field is 8 bits unsigned.

**For the old baselines** (random, the test-case sweep), the same translation can be done in
the shared runner (`simulator_runner.py`), Python only. It changes only requests of exactly 0,
which the LLM never makes, so only the baselines need to be re-run, which is needed anyway for
Bug 24. This is a separate decision, outside this plan.

### Step 3: the message model (the boofuzz "grammar")

One message with these fields. "Default" is the value used when the field is not the one being
mutated; every default means "no change".

| Field | boofuzz type | Default | Values (boofuzz) | AFDX values added (D1) |
|---|---|---|---|---|
| Frame size (bytes) | 16-bit unsigned integer (`s_word`) | The VL's normal size | 0–9, around 2,048, 4,096, 8,192, 16,384, 21,845, 32,768, and 65,526–65,535 | MinFrame−1, MinFrame, MinFrame+1, MaxFrame−1, MaxFrame, MaxFrame+1 for each VL; 1,517, 1,518, 1,519 |
| Timing change (ms) | 8-bit signed integer | 0 | Around 0, the extremes and fractions (to confirm in step 1) | −1 and +1 for each VL (BAG−1, BAG+1) |
| Sequence number | 8-bit unsigned integer (`s_byte`) | No change | 0–9, around 8, 16, 32, 64, 85, 128, and 246–255 | none needed (0, 1, 254, 255 are already there) |
| Source address | Group (`s_group`) | No change | `spoof_src`, `spoof_dst`, `broadcast`, `invalid_src`, `zero_mac` | — |
| Destination address | Group | No change | `corrupt_prefix`, `wrong_vl`, `zero` | — |
| Drop probability | Group | 0 | 0.1, 0.5, 1.0 (Q4) | — |
| VL | The target of the message | — | See step 4 | — |

Approximate sizes (to confirm in step 1): about 140 frame-size values, about 110
sequence-number values, about 110 timing values, 5 + 3 + 3 group values, plus 51 frame-size
and 16 timing AFDX values. In total roughly 430 test cases, more than the 200-test budget, so
the order matters (step 4).

**A note about the simulator.** The simulator never sends a frame smaller than 18 bytes or
larger than 9,000 bytes: it clamps the size to that range (`afdx-demo.cc`, lines 797–803). So
some values boofuzz generates for a 16-bit field arrive as the same frame. For example 10,000,
32,768 and 65,535 are all sent as 9,000 bytes, and 0–9 are all sent as 18 bytes. These tests
are identical for the simulator. This is not an error, but it wastes budget; see Q2 and step 4.

### Step 4: the test order

**What we keep from boofuzz:** each test mutates exactly one field, the others keep their
defaults; the order is fixed and repeatable; nothing is learned from results.

**The deviation, and why.** Real boofuzz takes all values of the first field, then all values
of the second field, and so on. With 200 tests it would test only frame sizes, and only the
lowest of them (boofuzz goes from small to large). That would not represent boofuzz fairly,
only its first few minutes. Because the budget is much smaller than boofuzz's full list, we
change only the order:

1. **Fields in rotation:** frame size, timing, sequence number, source address, destination
   address, drop probability, then frame size again, and so on. When a field's values are
   exhausted, it leaves the rotation.
2. **Inside a field, spread over boundaries:** take one value from each boundary group in turn
   (0–9, around 2,048, around 4,096, …, then the AFDX values), so that the budget reaches every
   boundary, not only the first one.
3. **VLs:** an AFDX value belongs to its VL (MaxFrame+1 of VL 2001 is sent on VL 2001). Every
   other value is sent to the next VL in rotation (1001, 1002, … 3002), as in the current
   baseline.
4. **Identical inputs are skipped (Q2):** if a test would reach the simulator exactly like an
   earlier one, it is skipped and the next one is taken. The number of skipped tests is
   reported.

**Assessment.** This is reasonable and defensible: the values, the one-field-at-a-time rule and
the determinism are boofuzz's; only the order is adapted to the budget. The paper must state
it in one or two sentences. A reviewer could ask what happens with boofuzz's original order;
if time permits, also report a run in the original order as a sensitivity check (free).

### Step 5: the code

A new folder, `boofuzz_model_baseline/`. The existing `boofuzz_baseline/` is not touched.

- `model.py`: the field definitions of step 3, including the AFDX values from
  `virtual_links.csv`.
- `generator.py`: builds the fixed test list of step 4 from boofuzz's values (step 1).
- `adapter.py`: turns one test case (one mutated field and the target VL) into the 7 simulator
  fields that `SimulatorRunner` expects, including sequence 0 → 256 (step 2).
- `main.py`: the run loop, using the same `SimulatorRunner` as the other fuzzers. It writes the
  history in the same format (one JSON line per test with `iteration`, `target_vl`,
  `sim_config`, `simulation_success` and the simulator counters), so the existing scoring scripts
  read it unchanged. Additional fields: `boofuzz_field` (which field was mutated),
  `boofuzz_value` (the value boofuzz chose) and `boofuzz_source` (`library` or `afdx`).
  `protocol_rule` is empty (see step 7).
- `README.md`: what is taken from boofuzz, what was adapted and why, the library version.

### Step 6: tests

- **Unit tests** (with known answers, as in `test_boundary_coverage.py`):
  - every test case mutates exactly one field;
  - the value lists equal what the boofuzz library produces (or the copied rule, if step 1
    goes that way);
  - two builds of the list give identical lists;
  - the adapter's output is correct for hand-written examples, for instance
    "MaxFrame+1 on VL 3001" → frame-size change +481 on VL 3001, and "sequence 0" →
    override 256;
  - skipped duplicates are really identical simulator inputs.
- **Independent check:** recompute the value lists in a separate small script, without the
  baseline's code, and compare.
- **Smoke run:** 5 tests on the fixed simulator; check that each one ran and changed what it
  should.

### Step 7: run and score (free)

**Run.** One run of 200 tests on the fixed simulator (`/tmp/ns3_fixtest`). The list is
deterministic, so one run represents it, as with the current BOOFUZZ-style baseline. No LLM
call.

**How it is compared without labels.** The new baseline does not record which rule a test is
for, because boofuzz has no notion of rules. So the label-based metrics do not apply to it.
Every other metric works on it exactly as on the other fuzzers, because they read only what
the simulator received:

| Metric | Script | Needs labels? | New baseline |
|---|---|---|---|
| Rule Coverage (paper) | `analyze_campaigns.py` | Yes | Not applicable |
| Executed Rule Coverage | `analyze_campaigns.py` | Yes | Not applicable |
| Bugs found (10-bug suite) | `bdr_replay.py` | No | Yes |
| Boundary-value coverage (79 points, 51 ranges) | `boundary_coverage.py` | No | Yes |
| Distinct simulator settings | `analyze_campaigns.py` (`distinct_settings`) | No | Yes |
| Tests without mutation | `analyze_campaigns.py` | No | Yes (expected 0) |

In the paper, the Rule Coverage cell of this baseline reads "n/a: label-free, like boofuzz".
The Rule Coverage comparison stays between the LLM, random and the test-case sweep (D2).

**Possible later addition (not part of this plan):** a label-free rule coverage, where a rule
counts as covered if any test sent a change that exercises it, regardless of labels. It needs a
per-rule table checked by an author (REVISION_FINDINGS Bug 38), and would apply to all fuzzers.

### Step 8: documentation

- `REVISION_FINDINGS.md`: a short note that the new baseline exists and which bugs it avoids.
- `PAPER_CHANGES.md`: a draft paragraph describing the baseline (fields, boofuzz's value
  generation, the AFDX values, the order adaptation, the library version), and the change of
  name of the current baseline.
- `FIX_PLAN.md`: status.

---

## 6a. What was found while implementing

- **Step 1:** the library gives each field's values directly (`mutations()`), without a
  target. boofuzz 0.4.2 is installed in a separate environment (`~/boofuzz_venv` in WSL), not
  in the ns-3 tree's environment; `export_boofuzz_values.py` writes the values to
  `boofuzz_values.json`, which the baseline reads.
- **`fuzz_values` is accepted but ignored** by integer fields in boofuzz 0.4.2 (checked: values
  passed through it do not appear in the mutations). The AFDX values are added by `model.py`.
- **Signed fields:** `mutations()` yields 0–255 also for a signed 8-bit field; the sign is
  applied when the value is rendered. The export renders each value and reads it back, so the
  JSON holds −128…127.
- **Windows:** boofuzz's windows that overlap are one run of consecutive values (for an 8-bit
  field, 0–41 is one window). Q1 was settled as planned: fields in rotation, one value per
  window in turn, ascending inside a window.
- **Identical inputs (Q2):** with the AFDX values, 442 candidate tests, 76 skipped (75 identical
  inputs, 1 that changes nothing), 366 kept; without them, 375 candidates, 73 skipped, 302 kept.
- **Option `--no-afdx-values`** runs boofuzz's own values only, to measure how much of the
  result comes from the AFDX values (decided 2026-11-02).
- **`.gitignore`** ignores every path not listed; the new folder had to be added to it.

## 7. Results (2026-11-02)

Both runs: 200 tests on the fixed simulator, no simulator failure, 200 distinct inputs, no
test without a mutation. Histories `runs/stage7/boofuzz_model.jsonl` (with AFDX values) and
`runs/stage7/boofuzz_model_pure.jsonl` (without); bug replay `bdr_replay_boofuzz_model*.json`;
boundary classes in `boundary_coverage_stage7.json`. The other fuzzers are the Stage 7 runs
(their baseline numbers are still before the Bug 24 / sequence-0 fixes).

| Fuzzer | Bugs found (of 8 reachable) | Boundary points (of 79) | Boundary ranges (of 51) | Tests without mutation |
|---|---|---|---|---|
| LLM (5 runs) | 8, 8, 8, 8, 8 | 31–34 | 45–47 | 2–4 |
| Random (5 runs) | 7 in each | 23–25 | 35–40 | 55–69 |
| BOOFUZZ-style test-case sweep | 7 | 14 | 33 | 68 |
| **Model-based BOOFUZZ, with AFDX values** | **8** | **71** | **50** | 0 |
| **Model-based BOOFUZZ, boofuzz values only** | **7** | **14** | **39** | 0 |

Where the boundary points come from:

| Boundary classes | With AFDX values | Boofuzz values only |
|---|---|---|
| Frame size around MinFrame (24) | 21 | 0 |
| Frame size around MaxFrame (24) | 20 | 0 |
| Ethernet maximum 1,517–1,519 (3) | 2 | 0 |
| Timing BAG±1 (16) | 16 | 2 |
| Sequence number 0, 1, 254, 255 (4) | 4 | 4 |
| Source / destination MAC types (8) | 8 | 8 |

- **58 of the 71 points of the AFDX run come from the AFDX values** (a recount by value
  source). boofuzz's own values reach 13 classes there, and 14 in the run without them. Its
  frame sizes come from the field width (0–9, around 2,048, 4,096, … 65,535), and none of them is
  a VL's MinFrame or MaxFrame ±1.
- **`max_frame_off_by_one`** is found only with the AFDX values (4 detecting inputs, all
  MaxFrame+1). Without them boofuzz finds the same 7 bugs as random and the sweep.
- **Reading:** a boofuzz tester who enters the VL limits gets the best boundary coverage, by
  construction: the values entered are the points the metric checks (the metric and the AFDX
  values both come from `virtual_links.csv`). That run shows what systematic testing of known
  limits achieves, not what boofuzz's method finds by itself. The run with boofuzz's values only
  shows the method; on boundary points it equals the sweep (14) and is below the LLM (31–34).
  Report both, and say so. **Superseded by section 8:** neither of these two is the paper's
  BOOFUZZ result.

## 8. Review of D1, the fairness principles, and the paper's variant (2026-11-02)

### 8.1 What D1 did, in the code

In `--mode expert`, `model.py` adds, for every VL, the frame sizes MinFrame−1, MinFrame,
MinFrame+1, MaxFrame−1, MaxFrame, MaxFrame+1, the timing offsets −1 and +1 ms, and the sizes
1,517–1,519 (`field_groups`, the `if afdx:` blocks). boofuzz does not compute these values:
they are written in our code. In other words, the baseline was told exactly what to test.

### 8.2 Why D1 was wrong

1. **It mixed information with a test rule.** Fairness requires that boofuzz gets the same
   *information* as the LLM fuzzer: the VL table (BAG, MinFrame, MaxFrame). D1 also gave it a
   *test rule*, "test exactly each limit −1, 0, +1" (boundary-value analysis). That rule is an
   expert's decision about what to test, not information about the network. The LLM fuzzer
   receives the table and must decide by itself which values to test.
2. **The rule is the boundary metric's own definition.** The boundary-value metric
   (`boundary_coverage.py`, PAPER_CHANGES 4.8) checks exactly MinFrame/MaxFrame ±1 and BAG ±1.
   So `--mode expert` reaches 71 of 79 points because it was given the metric's list of points,
   not because of anything boofuzz did. The comparison is circular.
3. **It is not boofuzz.** boofuzz generates values from each field's definition. Writing the
   values by hand is possible in the library (the `Group` / `s_group` primitive sends a listed
   set of values exactly; checked in boofuzz 0.4.2), but it is a person deciding the tests.
4. **It works against the paper's claim.** The point of the approach is that no human needs to
   model the protocol or decide the test values. A baseline in which a human wrote the test
   values measures something else (an expert with a tool), not the tool.
5. **The plan did not say this clearly.** D1 was presented as "add the AFDX limits as the
   tester's own values" and accepted. It should have said that this means hand-written test
   values that coincide with the metric's points.

### 8.3 The principles (decided 2026-11-02)

- **P1. Configure every fuzzer by fairness alone, before looking at results:** the same
  information for every fuzzer, and no human test rules for any of them.
- **P2. Do not optimize any fuzzer, or the choice of variant, toward one metric.** Fix all
  metrics in advance (bug detection, boundary-value coverage, input diversity, tests without
  mutation, and label-based coverage where labels exist), measure every fuzzer with all of them,
  and report the results whatever they show. A variant that wins on one metric because it was
  built around that metric's definition is not a fair comparison point.

### 8.4 The paper's BOOFUZZ variant: `--mode config` (decision D5)

- **What it does:** each VL's frame-size field is declared with that VL's maximum frame size
  from the configuration, using boofuzz's own `max_num` parameter (`max_num = MaxFrame + 1`, the
  field holds 0…MaxFrame). boofuzz then builds its boundaries from that maximum (0, max/2,
  max/3, max/4, max/8, max/16, max/32, max) and tries the values around each, as for any
  field. The values of each VL are sent on that VL. Timing, sequence number, MAC changes and
  drop probability are as in `--mode boofuzz`: BAG is not a field of the frame, so boofuzz has
  no native way to use it.
- **Why it is the fair one:** it gets exactly the information the LLM fuzzer gets and no human
  test rule (P1), and it was chosen by that principle, not by any metric (P2).
- **What boofuzz produces this way** (checked against the library before the run; exported in
  `boofuzz_values.json`, key `frame_size_by_max_frame`): 112, 132 and 140 values for MaxFrame
  256, 512 and 1,024. They include 63, 64, 65 (64 is 1/4, 1/8 or 1/16 of each MaxFrame) and
  MaxFrame−1 and MaxFrame, but **never MaxFrame+1**: boofuzz does not generate values above the
  maximum a field is declared with.
- **Results:** section 9 (run on 2026-11-02): 6 of 8 reachable bugs, 14 of 79 boundary points.

### 8.5 The other variants

| Variant | Status in the paper |
|---|---|
| `--mode config` | **The BOOFUZZ result** (D5) |
| `--mode boofuzz` (field types only, no configuration) | Optional supplementary row: boofuzz used as is, without the information the LLM gets |
| `--mode expert` (hand-written boundary values) | At most a clearly labeled reference point ("an expert with boofuzz"), never the comparison; or omitted |

The code of all three is kept (`--mode`), so every number in this document can be reproduced.

### 8.6 Results of `--mode config` (section 9 below)

## 9. Results of the paper's variant, `--mode config` (2026-11-02)

200 tests on the fixed simulator, no simulator failure, 200 distinct inputs, none without a
mutation. History `runs/stage7/boofuzz_model_config.jsonl`; bug replay
`bdr_replay_boofuzz_model_config.json`; boundary classes in `boundary_coverage_stage7.json`.

| Fuzzer | Bugs found (of 8 reachable) | Boundary points (of 79) | Boundary ranges (of 51) | Tests without mutation |
|---|---|---|---|---|
| LLM (5 runs) | 8, 8, 8, 8, 8 | 31–34 | 45–47 | 2–4 |
| Random (5 runs) | 7 in each | 23–25 | 35–40 | 55–69 |
| BOOFUZZ-style test-case sweep | 7 | 14 | 33 | 68 |
| **Model-based BOOFUZZ, `--mode config`** | **6** | **14** | **39** | 0 |

(Baseline numbers other than this one are still before the Bug 24 / sequence-0 fixes.)

- **Bugs:** found `skip_bag_policing`, `skip_frame_validation`, `skip_mac_validation`,
  `skip_constant_field`, `skip_sequence_check`, `loose_bag_tolerance`; missed
  `accept_oversized` and `max_frame_off_by_one`. The configuration declares MaxFrame as the
  field's maximum and boofuzz never goes above it, so this variant sends no frame larger than the
  VL allows, and the two bugs about oversized frames cannot be found by it.
- **Boundary points:** 14, all outside frame size (sequence number 4, MAC types 8, timing 2). Its
  frame-size list does contain 63, 64, 65, MaxFrame−1 and MaxFrame, but **the first 200 tests did
  not reach them.** The frame-size field got 62 of the 200 tests; with 8 VLs and several boundary
  windows per VL, each window gets one or two values, and boofuzz orders a window from its
  boundary −10 upward. The sizes actually sent were the starts of windows, e.g. on VL 1001:
  0, 54, 55, 118, 119, 161, 162, 246, 247, 503, 504.
- **This is the order rule fixed before the run (Q1, step 4), applied unchanged.** It is not
  changed after seeing the result (P2). What the variant would reach with more tests is a
  separate question (time to reach), not a reason to reorder.
- **Reading:** with the same information as the LLM fuzzer and the same 200-test budget,
  boofuzz's own value generation found 6 of 8 reachable bugs and 14 of 79 boundary points; the
  LLM fuzzer found 8 of 8 and 31–34.

### 9.1 Claim for the paper

The comparison shows what the LLM-guided approach achieves without a human writing test values,
against boofuzz given the same information. All metrics are reported, including those on which
boofuzz does better.

## 6. Effort, cost and risks

**Effort:** about 2 working days (step 1 half a day; steps 3–6 one day; run, scoring and
documents half a day). **Cost:** none (no LLM).

| Risk | Effect | Mitigation |
|---|---|---|
| The library cannot give values without a target | The baseline cannot call the library directly | Copy the value rule from the source (step 1) and test it against the library |
| `fuzz_values` is not implemented for integers | The AFDX values must be added by us | Add them after boofuzz's values and state it (D1) |
| The new baseline is stronger on boundaries, especially with the AFDX values | The LLM's lead on boundary-value coverage may shrink | Accept it: a credible comparison matters more than a large lead |
| Another change in the revision | More to explain | Separate folder, nothing existing changes; one paragraph in the paper |
| A reviewer questions the order adaptation | — | Explain it; optionally report a run in boofuzz's original order (free) |
