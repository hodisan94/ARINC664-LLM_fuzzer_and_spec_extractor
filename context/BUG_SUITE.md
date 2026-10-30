# The Injected-Bug Suite (Experiment 3)

**Status:** Stage 5 of `context/FIX_PLAN.md`, 2026-10-29, branch `fix/revision-bugs`.
**Bug numbers** such as "Bug 7" refer to `context/REVISION_FINDINGS.md`.

This document describes every injected bug the evaluation uses: what it changes in the
simulator, how it is detected, how we checked that it behaves as intended, and how each
fuzzer scores against it. It is written so that the paper's Experiment 3 section and
Table III can be written from it.

Everything here was measured on the **fixed simulator** (Stages 1–2: no second sender,
exact frame sizes, timing as a fixed signed offset, 1% BAG tolerance). No LLM API was called
for this stage.

---

## 1. How bug detection works

Bug detection is measured by **replay**, not by running the fuzzers against buggy
simulators.

1. Each fuzzer campaign records the exact simulator input of every iteration (`sim_config`:
   target VL, frame-size change, timing offset, source-MAC mutation, destination-MAC mutation,
   sequence-number override, sender drop probability).
2. Each distinct input is run once on the **reference** simulator (`inject_bug = "none"`) and
   once on each **buggy variant** (`inject_bug = <bug id>`). The simulator is deterministic, so
   one run per input and variant is enough.
3. An iteration **detects** a bug when the bug's detection counter differs between the two
   runs in the expected direction by at least one frame (`compute_bdr.bug_detected`, threshold
   0.5). For example, `skip_bag_policing` is detected when the buggy switch drops fewer
   frames for BAG violations than the reference switch.
4. A bug counts as **found** by a campaign when at least one of its iterations detects it.
   The score is the number of bugs found.

Each bug is switched on by a string in the simulator's mutation file (`inject_bug`), read by
`afdx-demo.cc` and checked inside the switch or end-system code. With `inject_bug = "none"`
the simulator is unchanged.

**Detection counters** (summed over the whole run):

| Signal | Counter | Direction that detects |
|---|---|---|
| `policing_drop_decrease` | switch BAG-policing drops | fewer in the buggy run |
| `token_bucket_drop_decrease` | switch token-bucket drops | fewer |
| `frame_error_drop_decrease` | switch frame-size drops | fewer |
| `mac_error_drop_decrease` | switch source-MAC drops | fewer |
| `forward_increase` | frames forwarded by the switch | more |
| `es_rejection_decrease` | frames rejected by the receiving end systems | fewer |

Code: `evaluation/compute_bdr.py` (catalogue `BUGS`, `bug_detected`),
`evaluation/revision/bdr_replay.py` (replay and scoring).

---

## 2. The suite

The list was fixed and committed (`b2e6ef8`) **before** any campaign was scored against it.
All fuzzers are scored against the same list.

**Caveat on "before scoring".** The recorded inputs were already in the logs when the list
was chosen, and the Stage 4 notes already said that the LLM often aims exactly at MaxFrame.
Whether a fuzzer ever sends exactly MaxFrame + 1 could therefore have been looked up; it was
not, and the prediction written down with the list ("may favour the baselines") was wrong
(Section 6, caveat 2). The difference in bugs found between the LLM-guided runs and the
baselines comes almost entirely from `max_frame_off_by_one`. Describe the list as chosen
before scoring, not as blind to the data, and report this bug's effect separately. The new
campaigns of Stage 7 are scored against a list fixed before they ran, so for them the
pre-registration is clean.

| # | Bug ID | What it switches off | Site | ARINC 664 P7 clause | Detection signal | Reachable |
|---|---|---|---|---|---|---|
| 1 | `skip_bag_policing` | The switch's BAG check | `afdx-switch.cc`, `ProcessFrame` step 3 | §4.2.2 | `policing_drop_decrease` | Yes |
| 2 | `skip_frame_validation` | The whole switch frame-size check (too big and too small) | `ProcessFrame` step 1 | §4.2.1 | `frame_error_drop_decrease` | Yes |
| 3 | `skip_mac_validation` | The switch's source-MAC check | `ProcessFrame` step 2b | §3.2.1, §3.2.5.2 | `mac_error_drop_decrease` | Yes |
| 4 | `skip_token_bucket` | The switch's token bucket | `ProcessFrame` step 4 | §4.2.2 | `token_bucket_drop_decrease` | **No** |
| 5 | `skip_vl_check` | The switch's VL authorization | `ProcessFrame` step 2 | §4.2.1 | `forward_increase` | **No** |
| 6 | `skip_constant_field` | The receiver's check of the `03:00:00:00` MAC prefix | `afdx-end-system.cc`, step 2 | §3.2.5.1, §4.2.1 | `es_rejection_decrease` | Yes |
| 7 | `skip_sequence_check` | The receiver's sequence-number check | `afdx-end-system.cc`, step 5 | §3.2.6.2.1 | `es_rejection_decrease` | Yes |
| 8 | `accept_oversized` | Only the "too big" half of the switch frame-size check | `AfdxSwitch::ValidateFrame` | §4.2.1 | `frame_error_drop_decrease` | Yes |
| 9 | `max_frame_off_by_one` | The switch accepts a frame one byte above the VL's MaxFrame | `AfdxSwitch::ValidateFrame` | §4.2.1 (new) | `frame_error_drop_decrease` | Yes |
| 10 | `loose_bag_tolerance` | The switch's BAG check tolerates 10% early arrival instead of 1% | `AfdxSwitch::CheckBagPolicing` | §4.2.2 (new) | `policing_drop_decrease` | Yes |

The clauses of bugs 1–8 are those of the paper's Table III. The clauses of bugs 9 and 10
were assigned by analogy with bugs 8 and 1 (the same checks) and should be confirmed against
the specification text before they go into the paper.

**Scores are reported two ways:** bugs found out of all 10, and out of the 8 reachable bugs.
`bdr_replay.py` writes both (`bugs_detected` / `bugs_total` and `bugs_detected_reachable` /
`bugs_reachable`).

---

## 3. Each bug in detail

### Bug 1. `skip_bag_policing`

- **Correct behaviour.** The switch drops a frame of a VL that arrives less than
  `BAG − 1% of BAG` after the previous accepted frame of that VL.
- **Injected fault.** The check is skipped; every frame passes.
- **Reached by.** A negative `timing_jitter_ms`, which shortens every send interval of the
  target VL (for example −1 ms on a VL with a 4 ms BAG sends every 3 ms).
- **Unchanged from the submitted suite.** In the submitted simulator it was "detected" by
  every input, including inputs with no mutation, because of the second sender (Bug 1 of the
  findings, Bug 10). On the fixed simulator a clean run has 0 policing drops, so only inputs
  that send too fast detect it.

### Bug 2. `skip_frame_validation`

- **Correct behaviour.** The switch drops frames below 64 or above 1518 bytes, and frames
  whose payload is outside the VL's configured range (MinFrame..MaxFrame).
- **Injected fault.** The whole check is skipped.
- **Reached by.** A `frame_size` (`payload_delta_bytes`) that makes the frame too small or
  too large for its VL.

### Bug 3. `skip_mac_validation`

- **Correct behaviour.** The switch drops frames whose source MAC is not the one configured
  for the VL.
- **Injected fault.** The check is skipped.
- **Reached by.** `mac_mutation_type` (for example `spoof_src`).

### Bug 4. `skip_token_bucket` (unreachable)

- **Correct behaviour.** The switch keeps a per-VL token bucket; a frame that costs more
  credit than is available is dropped.
- **Why no input reaches it** (Bug 7). The bucket refills `maxPayload + 20` bytes per BAG and
  a frame costs at most `maxPayload + 17`. The BAG check runs first and lets frames through
  at least one BAG apart, so every frame that reaches the bucket has earned more credit than
  it can cost. A frame large enough to empty the bucket is dropped earlier by the size check.
  Switching the bucket off therefore never changes a counter.
- **Kept in the suite** by decision, and reported as unreachable through the mutation
  interface. Making it reachable would require a different policing design (for example
  account-based policing with bursts), which this simulator does not model.

### Bug 5. `skip_vl_check` (unreachable)

- **Correct behaviour.** The switch drops frames whose VL id is not configured.
- **Why no input reaches it** (Bug 8). No mutation parameter changes the VL id field; every
  fuzzer can only send on configured VLs. `wrong_vl` changes only the destination MAC bytes.
- **Kept in the suite**, reported as unreachable.

### Bug 6. `skip_constant_field`

- **Correct behaviour.** The receiving end system rejects frames whose destination MAC does
  not start with `03:00:00:00`.
- **Injected fault.** The check is skipped.
- **Reached by.** `dest_mac_mutation` = `corrupt_prefix` or `zero`. (`wrong_vl` changes only
  the last two bytes, which nothing checks: Bug 15.)

### Bug 7. `skip_sequence_check`

- **Correct behaviour in this simulator.** The receiver rejects sequence number 0 and
  sequence numbers more than 128 behind the last accepted one.
- **Injected fault.** The check is skipped.
- **Reached by.** Two routes, both confirmed by the acceptance checks (Section 5):
  - forcing sequence number 0 (`sequence_number_override = 256` in the revised parameter
    description; 0 means "no override");
  - long bursts of policing drops, which leave large gaps in the received sequence (for
    example large frames sent far faster than the BAG).
- **Not reached by** a constant non-zero sequence number: the repeated frames are discarded
  earlier as duplicates, before the sequence check (Bug 11).
- **Kept unchanged** and documented. The receiver's order of checks was not changed.
- **Caveat for the paper.** ARINC 664 uses sequence number 0 to signal a sender reset. A
  receiver that always rejects 0 is this simulator's simplification; the paper should
  describe the simulator's rule, not claim it is the standard's.

### Bug 8. `accept_oversized` (changed)

- **Submitted version.** Switched off exactly the same code as `skip_frame_validation`
  (`afdx-switch.cc`: `if (activeBug != "skip_frame_validation" && activeBug != "accept_oversized")`),
  so the two always had identical results (Bug 9).
- **New version** (`2205a1f`). Only the upper bounds are skipped: frames above 1518 bytes or
  above the VL's MaxFrame pass; frames below 64 bytes or below MinFrame are still dropped.
- **Reached by.** A frame larger than the VL's MaxFrame. A too-small frame now detects
  `skip_frame_validation` but not `accept_oversized`, so the two bugs are distinct.

### Bug 9. `max_frame_off_by_one` (new)

- **Injected fault** (`5b23991`). The switch compares the payload with `MaxFrame + 1`
  instead of `MaxFrame`, so a frame exactly one byte too large is accepted. This is a
  classic boundary error.
- **Reached by.** Only a frame of exactly MaxFrame + 1 bytes. Frames of MaxFrame bytes are
  valid on both switches; frames of MaxFrame + 2 or more are dropped by both.
- **Why it was added.** It is reachable with the existing parameters and rewards testing
  exactly at the boundary, which an omitted-check bug does not.

### Bug 10. `loose_bag_tolerance` (new)

- **Injected fault** (`1c8a1e6`). The BAG check tolerates frames arriving up to 10% of the
  BAG early instead of 1%.
- **Reached by.** A send interval between 90% and 99% of the BAG. With whole-millisecond
  timing offsets this is possible on VLs with a 16 ms BAG (−1 ms) or a 32 ms BAG (−1 to
  −3 ms), but not on the 4 ms and 8 ms VLs. Heavy overload of a fast VL also reaches it,
  because queueing then varies the arrival gaps.
- **Note.** The 1% tolerance itself is a choice of this simulator, not a value from the
  standard, so this bug is a weaker match to the specification than bug 9.

---

## 4. Changes from the submitted suite, and why

| Change | Reason |
|---|---|
| `accept_oversized` checks only the upper bounds | It was identical to `skip_frame_validation`; one detection counted twice (Bug 9). |
| New `max_frame_off_by_one` | Reachable boundary fault; the submitted suite had no boundary fault that differed from an omitted check. The paper's own limitations paragraph names off-by-one faults as missing. |
| New `loose_bag_tolerance` | Reachable fault in a timing threshold rather than an omitted check. |
| `skip_token_bucket` and `skip_vl_check` kept, marked unreachable | Removing them was discussed; the decision was to keep them and report them separately (Bugs 7, 8). |
| `skip_sequence_check` unchanged | Fixing Bug 11 would change the receiver's order of checks; documented instead. |
| Scores reported of 10 and of 8 reachable | A score out of 10 counts two bugs that no fuzzer can find. |

The paper's sentence that the suite "does not include faults such as off-by-one window
checks, incorrect sequence-number wraparound, or wrong BAG units" needs updating: it now
includes one off-by-one fault (bug 9) and one threshold fault (bug 10).

---

## 5. Acceptance checks

Every bug must pass two checks:

- **(a)** an input with **no mutation** does not detect it;
- **(b)** at least one input that the mutation parameters can express **does** detect it,
  except bugs 4 and 5, for which no input should.

`evaluation/revision/check_bug_suite.py` runs 18 hand-written probes (17 distinct inputs;
the token-bucket probe is the same input as "exactly MaxFrame") against the reference
simulator and all 10 variants (187 simulator runs). Results:
`evaluation/results/revision/bug_suite_checks.json`. All AFDX unit tests passed on the same
build (sending ES 58, switch 46, receiving ES 41).

**Reference counters of each probe** (fixed simulator, no bug):

| Probe | Forwarded | BAG drops | Bucket drops | Size drops | MAC drops | ES rejections |
|---|---|---|---|---|---|---|
| No mutation (VL 1001 or 3001) | 3380 | 0 | 0 | 0 | 0 | 0 |
| Frame 63 B, 1 byte below MinFrame (VL 1001) | 2480 | 0 | 0 | 900 | 0 | 0 |
| Frame 512 B, exactly MaxFrame (VL 1001) | 3380 | 0 | 0 | 0 | 0 | 0 |
| Frame 513 B, 1 byte above MaxFrame | 2480 | 0 | 0 | 900 | 0 | 0 |
| Frame 514 B, 2 bytes above MaxFrame | 2480 | 0 | 0 | 900 | 0 | 0 |
| Frame 2000 B, above 1518 | 2480 | 0 | 0 | 900 | 0 | 0 |
| Every 3 ms on BAG 4 (VL 1001, −1 ms) | 3080 | 600 | 0 | 0 | 0 | 0 |
| Every 31 ms on BAG 32 (VL 3001, −1 ms) | 3326 | 58 | 0 | 0 | 0 | 0 |
| Every 29 ms on BAG 32 (VL 3001, −3 ms) | 3330 | 62 | 0 | 0 | 0 | 0 |
| Every 28 ms on BAG 32 (VL 3001, −4 ms) | 3332 | 64 | 0 | 0 | 0 | 0 |
| Spoofed source MAC (VL 1001) | 2480 | 0 | 0 | 0 | 900 | 0 |
| Corrupted MAC prefix (VL 1001) | 3380 | 0 | 0 | 0 | 0 | 1800 |
| Wrong VL bytes in destination MAC | 3380 | 0 | 0 | 0 | 0 | 0 |
| Constant sequence number 255 | 3380 | 0 | 0 | 0 | 0 | 0 |
| Sequence number 0 (override 256) | 3380 | 0 | 0 | 0 | 0 | 1800 |
| Large frames sent far too fast (VL 1002, +212 B, −5 ms) | 3378 | 35062 | 0 | 0 | 0 | 4 |

(The "512 B frames at BAG 4" token-bucket probe is the same input as "exactly MaxFrame".)

**Which probes detect which bug:**

| Bug | (a) | (b) | Detected by |
|---|---|---|---|
| `skip_bag_policing` | pass | pass | all five fast-sending probes |
| `skip_frame_validation` | pass | pass | 63 B, 513 B, 514 B, 2000 B |
| `skip_mac_validation` | pass | pass | spoofed source MAC |
| `skip_token_bucket` | pass | pass (none, as expected) | — |
| `skip_vl_check` | pass | pass (none, as expected) | — |
| `skip_constant_field` | pass | pass | corrupted MAC prefix |
| `skip_sequence_check` | pass | pass | sequence number 0; large frames sent far too fast |
| `accept_oversized` | pass | pass | 513 B, 514 B, 2000 B (not 63 B) |
| `max_frame_off_by_one` | pass | pass | 513 B only |
| `loose_bag_tolerance` | pass | pass | −1 and −3 ms on BAG 32 (not −4 ms, not −1 ms on BAG 4); large frames sent far too fast |

The probes also show that the new bugs separate as designed: 512 B detects nothing, 513 B
detects bugs 2, 8 and 9, 514 B detects only bugs 2 and 8, and 63 B detects only bug 2. On
BAG 32, −3 ms (90.6% of the BAG) detects bug 10 and −4 ms (87.5%) does not.

---

## 6. Results: recorded inputs scored against the new suite

**What was scored.** The inputs that the fuzzers already chose in the campaigns of
2026-10-23/24 (the campaigns of the response letter, run on the **unfixed** simulator), the
reconstructed inputs of the submitted campaigns, and the 2026-10-29 pilot (run on the fixed
simulator, 100 iterations per run). All were replayed on the fixed simulator against the
10-bug suite. Results: `evaluation/results/revision/bdr_replay_stage5_*.json`.

The replay reused the Stage 4 cache except for `accept_oversized`, whose code changed. As a
check, 40 randomly chosen reused results were re-run on the rebuilt simulator; all 40
matched exactly.

### Bugs found

| Campaign | Iterations | Found of 10 | Found of 8 reachable |
|---|---|---|---|
| LLM-guided, runs 1–5 | 200 | 8, 7, 7, 7, 8 | 8, 7, 7, 7, 8 |
| BOOFUZZ-style | 200 | 7 | 7 |
| Random, seeds 1–5 | 200 | 7, 7, 7, 7, 7 | 7, 7, 7, 7, 7 |
| Ablation A0 (no feedback, no steering) | 200 | 6 | 6 |
| Ablation A1 (steering only) | 200 | 8 | 8 |
| Ablation A2 (feedback only) | 200 | 7 | 7 |
| Pilot, original instructions, 2 runs | 100 | 7, 8 | 7, 8 |
| Pilot, revised instructions, 2 runs | 100 | 8, 8 | 8, 8 |
| Submitted LLM campaign (reconstructed) | 200 | 7 | 7 |
| Submitted BOOFUZZ campaign (reconstructed) | 200 | 7 | 7 |

For comparison, on the old 8-bug suite and the fixed simulator (Stage 4) the scores were
6, 5, 5, 5, 6 for the LLM-guided runs and 6 for every baseline run.

### Per bug: campaigns that found it, and mean number of detecting iterations

| Bug | LLM r1–5 | BOOFUZZ | Random s1–5 | Pilot original | Pilot revised |
|---|---|---|---|---|---|
| `skip_bag_policing` | 5/5 (31.6) | 1/1 (25) | 5/5 (31.2) | 2/2 (11.5) | 2/2 (33.0) |
| `skip_frame_validation` | 5/5 (17.8) | 1/1 (86) | 5/5 (65.0) | 2/2 (13.0) | 2/2 (31.5) |
| `skip_mac_validation` | 5/5 (5.4) | 1/1 (13) | 5/5 (16.2) | 2/2 (3.0) | 2/2 (4.5) |
| `skip_token_bucket` | 0/5 | 0/1 | 0/5 | 0/2 | 0/2 |
| `skip_vl_check` | 0/5 | 0/1 | 0/5 | 0/2 | 0/2 |
| `skip_constant_field` | 5/5 (7.2) | 1/1 (14) | 5/5 (17.6) | 2/2 (5.5) | 2/2 (14.5) |
| `skip_sequence_check` | **2/5** (0.6) | 1/1 (8) | 5/5 (13.4) | 1/2 (1.5) | 2/2 (11.5) |
| `accept_oversized` | 5/5 (16.4) | 1/1 (16) | 5/5 (43.6) | 2/2 (13.0) | 2/2 (26.0) |
| `max_frame_off_by_one` | **5/5** (6.2) | **0/1** | **0/5** | 2/2 (6.5) | 2/2 (10.0) |
| `loose_bag_tolerance` | 5/5 (10.4) | 1/1 (21) | 5/5 (23.0) | 2/2 (5.5) | 2/2 (15.5) |

Pilot iterations are out of 100, all others out of 200.

### What the results show

- **The suite now separates the fuzzers.** On the old suite every baseline scored 6/8.
  Now the LLM-guided runs and the baselines differ on two bugs, in opposite directions:
  - **`max_frame_off_by_one`** is found by every LLM-guided run and by no baseline run. In the
    recorded runs the LLM often aimed exactly at the VL's MaxFrame (42–47 iterations per
    run) and sometimes one byte above it (4–7 iterations per
    run). The baselines' frame sizes come from the test-case catalogue and from fixed
    generation rules; in all six baseline runs no input is exactly MaxFrame or MaxFrame + 1
    on any VL.
  - **`skip_sequence_check`** is found by every baseline run but by only 2 of 5 LLM-guided
    runs.
- **The baselines still trigger the common checks more often.** For example, frame
  validation: 86 detecting iterations for BOOFUZZ and 65 on average for Random, against 17.8
  for the LLM.
- **With the revised instructions** the LLM finds all 8 reachable bugs in both pilot runs,
  and triggers every reachable bug more often than with the original instructions: from
  1.5 times (source MAC, off-by-one) to 7.7 times (sequence check), and 2–3 times for 5 of
  the 8 bugs (mean detecting iterations per run, revised over original).

### Caveats

1. **The recorded campaigns ran on the unfixed simulator.** The LLM chose its inputs from
   that simulator's feedback and from the original instructions; the baselines do not use
   feedback. These scores describe the submitted inputs on a correct simulator, not the
   fuzzers' ability. New campaigns on the fixed simulator (Stage 7) are needed for that.
2. **A prediction recorded before scoring was wrong.** The pre-registration
   (`b2e6ef8`) said `max_frame_off_by_one` "may favour the baselines", because Stage 4 showed
   baseline frames one byte past a limit. Those frames were one byte **below MinFrame**
   (63 B), not above MaxFrame. In fact the bug favours the LLM-guided fuzzer. The bug list
   itself was not changed after scoring.
3. **The revised instructions describe boundaries** ("MaxFrame and MinFrame themselves are
   valid"). This is one of the implementation hints listed as open in `FIX_PLAN.md`; it may
   help the LLM find `max_frame_off_by_one` in new campaigns. The recorded campaigns used the
   original instructions, which do not contain it.
4. **Small numbers.** One BOOFUZZ run, five Random and LLM runs, single ablation runs, and two
   pilot runs per instruction version. A one-bug difference is a single bug.
5. **Detection uses whole-run counters.** A difference of one frame anywhere in the run
   counts. This is the paper's definition and is kept unchanged.
6. **Very large frames disturb timing on other VLs.** 9 of the 1,037 distinct recorded inputs
   have no timing offset yet detect `skip_bag_policing` and `loose_bag_tolerance`. All send
   frames of about 8–9 KB (extreme mode allows up to 9,000 bytes). These frames are dropped
   for their size, but transmitting them delays other VLs' frames on the shared links, and
   some of those then arrive too early. This is a real network effect, not a scoring error,
   but it means a size-only input can detect the two BAG bugs.
7. **`loose_bag_tolerance` is only reachable on the 16 ms and 32 ms BAG VLs** by a timing
   offset (Section 3, bug 10), because offsets are whole milliseconds. A fuzzer that never
   targets VLs 2002, 2003, 3001 or 3002 with a small negative offset cannot find it except
   through effect 6.
8. **Reconstructed submitted campaigns.** The table uses the `original/` reconstruction. The
   `original_as_run/` inputs (as the submitted `compute_bdr.py` rebuilt them) score lower:
   BOOFUZZ 5 of 10 and Random 0 of 10, because that script lost most baseline mutations
   (letter, problem 2).

---

## 7. How to reproduce

All commands run in WSL from the repository root, with the fixed ns-3 build:

```bash
export AFDX_NS3_PATH=/tmp/ns3_fixtest PYTHONPATH=. PYTHONUTF8=1
R=evaluation/results/revision

# acceptance checks (Section 5)
python3 evaluation/revision/check_bug_suite.py --cache $R/bug_suite_checks_cache.json \
  --out $R/bug_suite_checks.json

# re-scoring (Section 6), e.g. the LLM-guided runs
python3 evaluation/revision/bdr_replay.py --cache $R/bdr_replay_cache_stage5.json \
  --history $R/runs/llm_full_r1.jsonl=$R/runs/llm_full_r1.jsonl ... \
  --out $R/bdr_replay_stage5_llm.json
```

The cache files hold every simulator result used here, so the scores can be recomputed
without the simulator. The pilot runs need `--max-iterations 100`.

**Commits of this stage:** `b2e6ef8` (suite fixed before scoring), `2205a1f`
(`accept_oversized`), `5b23991` (`max_frame_off_by_one`), `1c8a1e6` (`loose_bag_tolerance`),
`f99a074` (acceptance checks), `4b7f210` (scores of 8 reachable), `a243f54` (re-scoring).
