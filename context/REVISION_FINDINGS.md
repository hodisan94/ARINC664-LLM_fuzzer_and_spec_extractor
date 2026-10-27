# Revision Review: Bugs Found in the Harness, Simulator and Evaluation

**Dates:** 2026-10-26 to 2026-10-27
**Scope:** Review of the evaluation harness, the ns-3 simulator, the evaluation scripts and
the response letter for the TAES major revision (TAES-2026-2779), after the harness fixes
in commit `0253d49`.
**No LLM API was called. Nothing in the code or the results has been changed.**

## How to read this document

Each bug has the same parts:

- **In plain words:** what is wrong, without jargon.
- **Details:** the code involved (file and line) and the mechanism.
- **Evidence:** the numbers that show it.
- **How it was found:** the method used.
- **Why it matters:** the effect on the paper.
- **Suggested fix.**
- **Status:**
  - *Verified*: checked directly against the code, the logs or a simulator run.
  - *Reported*: found by a code reviewer and not independently re-checked.

### Methods used

| Method | What it means |
|---|---|
| **Code reading** | Reading the source and following the path of a value from the fuzzer to the simulator and back. |
| **Log analysis** | Small read-only Python scripts over the logged campaigns in `evaluation/results/revision/runs/*.jsonl` and the replay results in `evaluation/results/revision/bdr_replay_*.json`. The cached simulator results in `bdr_replay_cache_v2.json` are keyed by bug and input. |
| **Simulator runs** | The ns-3 simulator installed in WSL (Ubuntu-24.04, ns-3.45), run with hand-written inputs in a scratch folder under `/tmp`. Each run takes about 2 seconds. |
| **Fix test** | A one-line change tested in a separate, self-contained copy of ns-3 (`/tmp/ns3_fixtest`). The unchanged copy reproduces the repository's numbers exactly and serves as the control. |
| **Independent review** | Two code reviewers, one for the C++ simulator and one for the Python evaluation, were told the already-known bugs and asked to find new ones. Each of their claims used below was then checked; unchecked claims are marked *Reported*. |

### Background: how one fuzzing iteration works

1. The **planner** (the LLM, or a baseline) chooses a target virtual link (VL), a rule
   **label** (the rule it says it is testing), and mutation parameters.
2. `SimulatorRunner._translate_to_cpp_format` turns the plan into a small settings file
   (`mutations.json`) with 7 fields:
   - the target VL;
   - `payload_delta_bytes` (frame size);
   - `timing_jitter_ms` (timing);
   - `mac_mutation` (source MAC);
   - `dest_mac_mutation` (destination MAC);
   - `sequence_number_override`;
   - `prob` (drop at the sender).

   Nothing else reaches the simulator.
3. ns-3 runs the scenario `examples/AFDX_V3/simulations/afdx-demo.cc` for 2 simulated
   seconds. Three end systems send 8 VLs through two redundant switches (A and B).
4. The simulator prints counters, for example frames forwarded, frames dropped by
   policing, and frames rejected at the receivers. `llm_fuzzer/utils/log_parser.py` reads
   them. They feed the reward, the feedback to the LLM, and Experiment 3 (bug detection).
5. **Rule Coverage** (Experiment 2) maps each logged label to the 185 rule categories in
   `configs/spec_rules_filtered.json` and counts the categories reached.
6. **Experiment 3** replays each logged input on the bug-free simulator and on 8
   versions, each with one injected bug. An injected bug counts as detected if a chosen
   counter changes.

---

## Summary

| # | Bug | Area | Severity | Status |
|---|---|---|---|---|
| 1 | Two senders on every VL; the fuzzer's frames are dropped by the switch | Simulator | High | Verified |
| 2 | "Send faster" makes the VL go silent; "slower" is random | Simulator | High | Verified |
| 3 | Every frame is 17 bytes larger than requested | Harness + simulator | High | Verified |
| 4 | The baselines can only reach 90 of the 185 categories; the LLM can reach all | Evaluation fairness | High | Verified |
| 5 | The test-case list was built from an older version of the rules | Data | High (cause of 4) | Verified |
| 6 | The impact part of the reward is always at its maximum | Reward | High | Verified |
| 7 | The token-bucket bug can never be detected | Bug suite | High | Verified |
| 8 | The VL-check bug can never be detected | Bug suite | High | Verified |
| 9 | Two bug IDs disable the same check | Bug suite | Medium | Verified |
| 10 | Two bugs are "detected" with no mutation at all | Bug suite | High (consequence of 1) | Verified |
| 11 | A constant sequence number is discarded as a duplicate, not checked | Simulator | Medium | Verified |
| 12 | The BAG tolerance rounds down to 0 | Simulator | Low | Verified |
| 13 | Token-bucket drops are counted as BAG drops | Simulator counters | Low | Verified |
| 14 | The receiver checks payload size against the wrong table | Simulator | Low | Verified |
| 15 | No check exists for a wrong destination MAC | Simulator | Medium | Verified (run) |
| 16 | Some requested mutations are silently ignored | Harness | Medium | Verified |
| 17 | One label can count for many categories (prefix matching) | Evaluation | Medium | Verified (examples) |
| 18 | Executed Rule Coverage credits unrelated mutations | Evaluation | Medium | Verified |
| 19 | Every metric mixes both senders, all 8 VLs and both switches | Metrics | Medium | Verified |
| 20 | Feedback labels and `bugs_found` carry no information | Feedback | Medium | Verified |
| 21 | Metric names that do not mean what they say | Evaluation | Low | Verified / Reported |
| 22 | The crash fix was not active when the campaigns were recorded | Harness | Low | Verified |
| 23 | Resuming a BOOFUZZ campaign restarts its schedule | Baseline | Low | Reported |
| 24 | Other code-health issues | Various | Low | Verified |

Section 25 lists statements in the paper and the response letter that do not match the
code. Section 26 explains how to reproduce the simulator results. Section 27 lists open
questions.

---

## Part A: The simulator

### Bug 1. Two senders on every virtual link

**In plain words.** Every stream of messages is sent by two separate programs at the same
time. One of them is the program the fuzzer controls. The other is a "hidden" sender that
the fuzzer cannot touch. The hidden sender started first, so the switch keeps its messages
and throws away the fuzzer's messages for arriving too early. The fuzzer's messages
therefore never reach the receivers.

This is **not** the A/B redundancy of AFDX. In redundancy, one sender sends the same frame,
with the same sequence number, on network A and on network B. That part is implemented
separately and works. Here, two different programs send different frames, with different
sizes and separate sequence counters, on the **same** network.

**Details.**

- `examples/AFDX_V3/simulations/afdx-demo.cc` creates two kinds of sender:
  1. **`AfdxEndSystem`** (lines 676–692). It is attached to each node with
     `AggregateObject`, then given every VL as a *transmit* VL by `AddTransmitVL`
     (lines 723, 725, 727). The comment above that loop (line 696) says "Configure Virtual
     Links on End Systems **(for receiving)**".
     - It is never registered with `AddApplication`. But ns-3 initializes every object
       attached to a node at time 0 (`Object::Initialize` calls
       `Application::DoInitialize`, which schedules `StartApplication`), so it starts
       anyway.
     - It sends from 10 ms + (VL id mod 50) ms, every BAG, on both networks.
     - It reads only the sequence-number and destination-MAC mutations
       (`afdx-end-system.cc:218-256`).
  2. **`AfdxTrafficGenerator`** (lines 748–858). It is registered with `AddApplication`,
     starts at 0.1 s, and applies all fuzzer mutations. **This is the fuzzer's sender.**
- The switch remembers when it last accepted a frame on each VL and drops any frame that
  arrives less than one BAG later (`afdx-switch.cc:447-488`).
  - On VL 1002 (BAG 4 ms) the two streams are 2 ms apart.
  - The hidden stream owns the slot, so the generator's frame is always the one dropped.
- The switch checks every frame in this order (`afdx-switch.cc`, `ProcessFrame`):
  1. frame size;
  2. VL id;
  3. source MAC;
  4. BAG policing ← **the fuzzer's frames are dropped here**;
  5. token bucket;
  6. forwarding to receivers.

  As a result, steps 5–6 and every check in the receiving end systems (sequence numbers,
  duplicates, constant fields) only ever see the hidden sender's unmutated traffic.

**Evidence** (simulator run, no mutation, VL 1002, network A, after t = 0.1 s):

| Sender | Frame size in the log | Sequence numbers | Frames sent | Frames that reached the receivers (ES2, ES3) |
|---|---|---|---|---|
| Hidden end system | 530 B | continues 21, 22, 23… | 475 | **475** |
| Fuzzer's generator | 323 B | restarts at 1 | 450 | **0** |

- VLs 2001 and 3001 show the same pattern.
- On every VL, the switch forwards exactly the BAG rate and drops about the same number
  again. In total that is 3,492 policing drops out of 7,118 frames (49%), with no mutation
  at all.

**How it was found.**

1. Log analysis showed that an unmutated run already has 3,492 policing drops and 264
   receiver rejections.
2. A simulator run showed that each switch receives every VL at exactly twice its BAG
   rate. Each port receives twice what its end system should send, on both switches.
3. The simulator's CSV log showed two interleaved streams on one wire. They differ in
   start time (12 ms vs. 102 ms), size (530 B vs. 323 B) and sequence counter.
4. Code reading found the two senders. Reading the ns-3 source (`Object::Initialize`,
   `Application::DoInitialize`) explained why the unregistered one starts.
5. Counting received frames by size showed that only the 530-byte frames reach the
   receivers.

**Is it intended?** There is no evidence that it is.

- The paper (Section IV-B) says conforming traffic is emitted once per BAG and that the
  strict check "does not drop conforming frames".
- The code comment says the end systems are configured "for receiving".
- `context/DIAGNOSIS.md` (Feb 2026) lists the high policing rate on clean traffic as a
  problem and blames double counting. That fix lowered it from 75% to 49%; the rest went
  unexplained.
- Jitter is measured at the receivers (`afdx-demo.cc:285-300`) and does not need a second
  sender.
- Both senders are present in the repository's first commit (`dafc4c9`), so git history
  does not show why. **Please confirm with the author.**

**Fix test.** In a separate copy of ns-3, the three `esN->AddTransmitVL(vl)` calls were
removed, so the end systems only receive. 8 inputs (7 real ones from `llm_full_r1` and one
synthetic) were run bug-free and with each injected bug: 144 runs.

Bug-free counters, before → after:

| Input | Forwarded | Policing drops | MAC drops | Receiver rejections | Target VL forwarded |
|---|---|---|---|---|---|
| No mutation | 3626 → 3380 | 3492 → **0** | 0 → 0 | 264 → **0** | 884 → 900 |
| Larger frame (1,000 B on VL 3002, within its limit) | 3626 → 3380 | 3492 → 0 | 0 → 0 | 264 → 0 | 126 → 114 |
| Fake source MAC (VL 2003) | 3626 → 3154 | 3266 → 0 | 226 → 226 | 264 → 0 | 250 → **0** |
| Wrong destination MAC (VL 2001) | 3626 → 3380 | 3492 → 0 | 0 → 0 | 264 → 0 | 498 → 450 |
| Forced sequence number 255 (VL 2002) | 3626 → 3380 | 3492 → 0 | 0 → 0 | 260 → 0 | 250 → 226 |
| "Send faster", jitter −12 (VL 2002) | 3626 → 3156 | 3268 → 0 | 0 → 0 | 264 → 0 | 250 → **2** |
| Larger frame + jitter +100 (VL 3001) | 3626 → 3306 | 3462 → **44** | 0 → 0 | 264 → 0 | 126 → 40 |
| Drop half at sender (VL 1002, synthetic) | 3626 → 2932 | 3044 → 0 | 0 → 0 | 264 → 0 | 994 → 452 |

Injected bugs detected (rule from `compute_bdr.py`: counter difference > 0.5):

| Input | Before | After |
|---|---|---|
| No mutation | BAG, sequence | none |
| Larger frame | BAG, sequence | none |
| Fake source MAC | BAG, MAC, sequence | MAC |
| Wrong destination MAC | BAG, sequence | none |
| Forced sequence number 255 | BAG, sequence | none |
| "Send faster" | BAG, sequence | none |
| Larger frame + jitter +100 | BAG, sequence | BAG |
| Drop half at sender | BAG, sequence | none |

After the change, clean traffic is clean, the "free" detections disappear (Bug 10), and
the remaining detections are caused by the fuzzer's input.

**Why it matters.** The fuzzer could only ever test the first three switch checks. The
token bucket, forwarding, and all receiver checks described in the paper never saw fuzzed
traffic. This affects every fuzzer equally, so it is not unfair by itself. But it changes
what Experiments 2 and 3 can claim.

**Suggested fix.** Do not call `AddTransmitVL` on the end systems, as tested above, or do
not start the generator. Then re-run the simulator's unit tests and replay all logged
inputs.

---

### Bug 2. "Send faster" makes the VL go silent, and "send slower" is random

**In plain words.** When a fuzzer asks to send messages faster than the speed limit, the
stream sends 2 messages and then nothing for the rest of the run. When it asks for
"slower", each gap is randomly shorter or longer, so it sometimes sends *faster*.
No campaign ever really tested "too fast".

**Details.**

- The runner turns `bag_value < BAG` into a negative `timing_jitter_ms`
  (`simulator_runner.py:199-203`).
- The generator then computes
  `applied_jitter = (int) jitterRng->GetInteger(0, 2 * jitter_ms) - jitter_ms`
  (`afdx-traffic-generator.cc:641`, and the same at `:518`).
- In ns-3.45, `UniformRandomVariable::GetInteger(uint32_t min, uint32_t max)` takes
  **unsigned** numbers. A negative `2 * jitter_ms` turns into about 4.29 billion. The next
  send time is then either clamped to 100 µs or pushed hours into the future.
- A positive value gives a random gap anywhere in `[BAG − j, BAG + j]` for every frame.
  It is not a fixed slower offset.

**Evidence** (simulator runs, VL 1002, BAG 4 ms, fuzzer's frames on network A):

| `timing_jitter_ms` | Frames sent | Simulator's own `jitterAppliedMs` |
|---|---|---|
| 0 | 450, one every 4.0 ms | 0 |
| −1 | **2** (at 102.0 and 102.1 ms), then silence | 132,521,920 |
| −3 | **2**, identical to −1 | 132,521,922 |
| +2 | 453, gaps randomly 2–6 ms | −1 |

The replay cache shows the same thing across all campaigns: on any one VL, every negative
value gives byte-identical counters. For example, VL 1001 with −1 to −5 always gives
2,708 policing drops.

**How it was found.**

1. Code reading of where `timing_jitter_ms` is used.
2. Checking the `GetInteger` signature in the installed ns-3 source.
3. Log analysis showed identical results for every negative value.
4. Simulator runs with −1, −3 and +2 confirmed it.

**Why it matters.**

- Every BAG-violation test in the paper, for every fuzzer, actually tested "two frames,
  then silence".
- The planner prompt (`fuzzing_agent.py`), the paper and the letter all describe the
  parameter as a timing offset ("negative = faster, positive = slower").
- `context/DIAGNOSIS.md` concluded "Jitter WORKS — frame counts change". The counts
  changed because the VL went silent.

**Suggested fix.** Apply a fixed, signed offset to the send interval
(`next = BAG + offset`, with a small positive minimum). Add a separate parameter if random
jitter is also wanted.

---

### Bug 3. Every frame is 17 bytes larger than requested

**In plain words.** When the fuzzer asks for a frame of X bytes, the simulator sends
X + 17. A test of "exactly the largest legal size" is rejected as too big. A test of
"slightly too small" is accepted.

**Details.**

1. The runner computes `payload_delta_bytes = frame_size − (min_frame + max_frame) // 2`
   (`simulator_runner.py:82, 189-193`). It works in **frame** sizes.
2. `afdx-demo.cc:778-827` adds this delta to `(minFrameSize + maxFrameSize) / 2` and passes
   the result to `gen->AddVirtualLink(vl, frameSize)`.
3. That parameter is the **payload** size (`afdx-traffic-generator.cc:113-136`). The 17
   header bytes are added on top.
4. The switch checks the payload against `max_frame − 17` (`afdx-virtual-link.cc:59-78`,
   `afdx-switch.cc:426-432`).

**Evidence** (log analysis):

| Campaign | Requested | VL limit | Result |
|---|---|---|---|
| LLM r1, iteration 9 | `frame_size` 1024 | VL 3001, max 1,024 (legal) | 114 frame-error drops |
| BOOFUZZ, iterations 0, 4, 8 | `frame_size` 63 | min 64 (illegal) | 0 frame-error drops |

Reviewer counts, consistent with the examples:

- Legal sizes that were dropped: 70, 74, 62, 56, 69 iterations in LLM runs r1–r5.
- Illegal sizes that were accepted: 47 iterations in BOOFUZZ and 15–20 in each random run.
- Of the LLM's frame-validation detections, 56–74 per run come from legal sizes.

**How it was found.**

1. The independent review traced `frame_size` from the runner into the C++ code.
2. The path was checked by code reading.
3. The examples above were checked in the logs.

**Why it matters.**

- Frame-size boundary tests are shifted by 17 bytes. A reviewer explicitly asked for
  boundary-value testing.
- Most of the LLM's frame-validation "detections" come from frames that should have been
  legal. The baselines' undersize tests (63 B) never trigger anything.
- The planner prompt (`fuzzing_agent.py:273`) tells the LLM that frames above the maximum
  trigger an error, which is not what happens at the exact boundary.

**Suggested fix.** Translate a frame size into a payload size: `payload = frame_size − 17`.
Pass the payload to the generator, and clamp against payload limits, not frame limits.

---

### Bug 4 (see Part B). Coverage fairness

This is described in Part B, because it is an evaluation bug, not a simulator bug.

---

### Bug 7. The token-bucket bug can never be detected

**In plain words.** One of the 8 planted bugs switches off a check that, by its own
arithmetic, can never fail. Removing it changes nothing, so no fuzzer can ever detect it.

**Details.**

- The token bucket (`afdx-switch.cc:363-377, 508-560`) refills `(maxPayload + 20)` bytes
  per BAG and holds at most twice that.
- A frame costs its size, which is at most `maxPayload + 17`. Larger frames are dropped
  earlier, at step 1.
- The BAG check (step 4) only lets frames through at least one BAG apart. So every frame
  that reaches the bucket has earned more credit than it can cost. For VL 1001 it earns 515
  bytes, and the maximum cost is 512.
- The planner's scheduled "token bucket stress" test uses `frame_size` 1500
  (`strategy_planner.py:422-431`). Because of Bug 3, that is above every VL's payload
  limit, so it is dropped at step 1 before reaching the bucket.

**Evidence.** `skip_token_bucket` has 0 detections in every campaign and every replay.

**How it was found.** The independent review of the simulator, followed by a check of the
arithmetic against `afdx-virtual-link.cc` and `afdx-switch.cc`.

**Why it matters.**

- It is an "equivalent mutant": it cannot separate fuzzers, yet it is counted in the
  denominator of "x/8 bugs".
- The response letter says it "cannot be reached through the mutation interface". The real
  reason is the arithmetic, together with Bug 1.

**Suggested fix.** Remove it from the suite, or make the bucket able to fail. For example,
debit the real frame cost and let bursts through when BAG policing is off.

---

### Bug 8. The VL-check bug can never be detected

**In plain words.** The fuzzer can only send on VLs that exist. The check for "unknown VL"
therefore never fires, and switching it off changes nothing.

**Details.**

- The fuzzer has no parameter for the VL id field. Both senders write the configured id.
  `wrong_vl` changes only the destination MAC.
- `IsVLAuthorized` (`afdx-switch.cc:318-327`) therefore always passes.
- Side issue: if the check were skipped for an unknown VL, `m_vlConfig[vlId]` at line 333
  would silently create a default entry.

**Evidence.** `skip_vl_check` has 0 detections in every campaign.

**How it was found.** The independent review, checked by code reading.
`context/DIAGNOSIS.md` (Finding 4) already noted that invalid-VL injection is impossible.

**Why it matters / fix.** Same as Bug 7: remove it, or add a mutation that sets the VL id.

---

### Bug 9. Two bug IDs disable the same check

**In plain words.** `skip_frame_validation` and `accept_oversized` are listed as two bugs,
but they switch off exactly the same code. One detection is counted twice.

**Details.** `afdx-switch.cc:302`:
`if (activeBug != "skip_frame_validation" && activeBug != "accept_oversized")`.

**Evidence.** Their detection counts are identical in all 17 replay reports (for example
82 / 41 / 39 for LLM r1 / random s1 / BOOFUZZ).

**How it was found.** Code reading, plus comparing per-bug counts in the replay reports.
The letter already discloses this.

---

### Bug 10. Two bugs are "detected" with no mutation at all

**In plain words.** `skip_bag_policing` and `skip_sequence_check` count as detected by
every test, including tests that change nothing. This comes from Bug 1: switching either
check off changes how the two senders' messages interact.

**Evidence** (replay reports):

| Bug | LLM r1 | Random s1 | BOOFUZZ |
|---|---|---|---|
| skip_bag_policing | 200 of 200 (first at iteration 0) | 200 (0) | 198 (0) |
| skip_sequence_check | 200 (0) | 200 (0) | 198 (0) |
| skip_frame_validation | 82 | 41 | 39 |
| accept_oversized | 82 | 41 | 39 |
| skip_mac_validation | 5 | 16 | 13 |
| skip_constant_field | 5 | 13 | 24 |
| skip_token_bucket | 0 | 0 | 0 |
| skip_vl_check | 0 | 0 | 0 |

In the fix test (Bug 1), both "free" detections disappear.

**How it was found.** Log analysis of the replay reports, then the fix test.

**Why it matters.** With Bugs 7–10 together, only **3 genuinely different behaviours**
remain in the 8-bug suite: frame validation, the source-MAC check, and the constant-field
check. "6/8 for every fuzzer" mostly reflects the suite, not the fuzzers. The letter
discloses that two bugs are found without mutation, but treats the 49% baseline drop rate
as normal.

---

### Bug 11. A constant sequence number is thrown away as a duplicate, not checked

**In plain words.** Forcing every frame to carry the same sequence number never triggers
the sequence-number check. The receiver drops the repeated frames earlier as duplicates.

**Details.**

- The receiver first runs "first valid frame wins" duplicate removal
  (`afdx-end-system.cc:447`), and only then the sequence check (`:461`).
- A repeated number is discarded as a duplicate or "unexpected retransmit" (`:614-625`)
  before the check sees it.
- The hidden sender (Bug 1) counts 0…255 and wraps to 0 (`afdx-end-system.cc:105, 309`).
  The receiver rejects sequence 0 as invalid (`:553`), so the hidden sender produces some
  rejections in every run.
- The sequence check also wraps differences with `+= 255`, assuming a 1–255 range.

**Evidence.** In the fix test, forcing sequence number 255 on VL 2002 gives **0**
receiver rejections. The repeated frames are discarded as duplicates.

**How it was found.** The fix-test run raised the question; code reading of the receive
path explained it. The independent review proposed a formula for the 264 baseline
rejections, but it gives about 40 and was not confirmed. The exact source of the 264 is
still open (Section 27).

**Why it matters.** The paper's sequence-number mutation cannot exercise the
sequence-number check. Only the hidden sender and its interaction with the generator
produce sequence errors.

---

### Bug 12. The BAG tolerance rounds down to 0

**In plain words.** The switch is meant to allow a 1% timing tolerance, but the tolerance
is computed as 0, so a frame that is a few microseconds early is dropped.

**Details.** `afdx-switch.cc:475`: `Time tolerance = MilliSeconds(bag.GetMilliSeconds() * 0.01);`.
`bag.GetMilliSeconds()` is a whole number of ms (4 to 32). Times 0.01 that is 0.04 to 0.32,
which `MilliSeconds` truncates to a whole number: 0.

**How it was found.** The independent review, then code reading.

**Why it matters.** Small. With Bug 1 fixed, the clean run had 0 policing drops, so it
does not affect the baseline on its own. It makes the switch stricter than the paper's
"tolerance of 1%".

**Suggested fix.** `MicroSeconds(bag.GetMicroSeconds() / 100)`.

---

### Bug 13. Token-bucket drops are counted as BAG drops

**In plain words.** When the token bucket drops a frame, the switch adds it to the same
counter as BAG drops, with the same label. The two cannot be told apart.

**Details.** `afdx-switch.cc:365-371` increments `m_framesDroppedPolicing` and
`policingViolations` and logs "BAG_Violation", exactly as the BAG check does.
`afdxTokenBucketViolations` prints a counter that resets on every success, so it is not
a total.

**How it was found.** The independent review, then code reading.

---

### Bug 14. The receiver checks payload size against the wrong table

**In plain words.** The receiving end system is supposed to check each frame's size
against that VL's limits. It looks the VL up in its list of VLs it *sends*. A receiver
never sends the VLs it receives, so the per-VL check never applies.

**Details.** `afdx-end-system.cc:499-503` uses `m_transmitVLs` instead of the receive
configuration.

**How it was found.** The independent review, then code reading.

---

### Bug 15. No check exists for a wrong destination MAC

**In plain words.** The fuzzer can set a wrong destination MAC (`wrong_vl`), but no check
in the switch or the receiver compares the destination MAC with the VL. The mutation is
invisible.

**Details.**

- The only comparison is a log warning in `AfdxFrame::Serialize`
  (`afdx-frame.cc:240-245`).
- That warning fires on every normal frame anyway: `virtual_links.csv` writes the VL id in
  hexadecimal in the MAC (VL 1001 → `03:00:00:00:10:01`), while the code expects decimal.

**Evidence.** In the fix test, "wrong destination MAC" detects no bug, before or after.

**How it was found.** The independent review, checked by a simulator run.

---

## Part B: The evaluation and the harness

### Bug 4. The baselines can only reach 90 of the 185 categories; the LLM can reach all 185

**In plain words.** Think of Rule Coverage as an exam with 185 topics. Each fuzzer scores
one point for every topic it touched.

- The random and BOOFUZZ fuzzers may only choose questions from a printed sheet (the
  test-case list) that covers 90 of the topics.
- The LLM may choose from the whole book (the rule list) and can reach all 185.

The LLM's higher score partly reflects the bigger book, not better fuzzing. Counting only
the 90 topics that every fuzzer can reach, BOOFUZZ scores highest.

**Details.**

- The random baseline picks its label from the test-case names
  (`random_strategy_generator.py:64, 110`: `available_rules = list(test_cases.keys())`).
- BOOFUZZ builds its schedule from the test-case violations
  (`boofuzz_strategy_generator.py`).
- The LLM sees both the rule list and the test cases. It can also write a free-form label,
  which `_normalize_to_known_rule` keeps if nothing matches.
- Coverage maps each label to categories by name (`recompute_coverage_venn.build_matcher`).
  - 423 test-case names exist; only 206 match any category, and together they reach **90**
    of the 185 categories.
  - The rule names reach all 185.
- The baselines could not simply be given the rule list. They need concrete violating
  values to send, which only the test-case list provides. This is why they were built on
  it; no one intended the imbalance. Bug 5 explains why the two lists disagree.

**Evidence** (log analysis; the BOOFUZZ crash iterations 190–191 excluded):

Categories reached outside the 90 the baselines could reach: LLM r1–r5 **27, 27, 36, 31,
29**; A1 41; every random run 0; BOOFUZZ 0.

Coverage counting only the 90 shared categories (no new runs; the existing logs are
re-scored):

| | By labels | Executed (traffic mutated) |
|---|---|---|
| **BOOFUZZ-style** | **86** | **61** |
| LLM full (mean of 5) | 65.4 (60, 64, 71, 65, 67) | 58.2 (54, 60, 59, 60, 58) |
| A1 (steering only) | 54 | 54 |
| A2 (feedback only) | 49 | 43 |
| Random (mean of 5) | 47.2 | 39.6 |
| A0 | 6 | 6 |

**How it was found.**

1. The independent review of the Python code noticed that the baselines draw labels only
   from `test_cases.json`.
2. A check computed which categories the test-case names can reach (90) and how many
   categories each run reached outside them.
3. Each run was then re-scored on the 90 shared categories.

No fuzzer was re-run, and no fuzzer was given a different input. This is a re-scoring of
the existing logs only.

**Why it matters.**

- The paper's coverage lead (for example 88 vs. 61 executed categories) and most of the
  LLM's Unique Findings come from categories the baselines could never reach.
- On the categories everyone can reach, BOOFUZZ leads in every run, by both measures.
- Random's 0 Unique Findings follows by construction.
- The Mann–Whitney test on coverage partly tests this imbalance.

**Suggested fix.** Report coverage on the shared 90 categories as well, or give all
fuzzers the same label pool. Most important is fixing Bug 5, so that the test-case list
covers the current rules.

---

### Bug 5. The test-case list was built from an older version of the rules

**In plain words.** The rule list and the test-case list should describe the same rules.
Most of the test-case names, however, do not exist in the current rule list. It looks as
if the rules were extracted again and renamed after the test cases had been generated, and
the test cases were never regenerated.

**Details.**

- `configs/test_cases.json`: 423 rule names, each with test cases.
- The current rule list, `configs/spec_rules_filtered.json`, has 185 categories and
  626 sub-rules.
- Of the 217 test-case names that match no category:
  - 36 exist only in the unfiltered list `configs/spec_rules.json` (231 categories,
    757 sub-rules);
  - **181 exist in neither file**, for example `domain_id_coding`,
    `fifo_discipline_for_queuing`, `signed_32_integer`, `ethernet_bit_order`.
- Only 63 of the 626 current sub-rules have a test case under their own name.
- 87 of the 185 categories have no test case for any of their sub-rules.
- `spec_extraction/extract_test_cases.py` generates test cases from `configs/spec_rules.json`
  by default. Git history shows a new 3-LLM extraction ("774 rules") on 2026-04-04, after
  test-case generation was added (2026-03-10). `configs/` is not tracked by git, so the
  generation date of `test_cases.json` cannot be confirmed.

**How it was found.** Investigating why the test-case names reach only 90 categories
(Bug 4): every test-case name was compared against both rule files.

**Why it matters.**

- This is the root cause of Bug 4.
- The response letter states that the baselines were re-run "on the final rule base". But
  their labels come from test cases that were generated from an earlier one.

**Suggested fix.** Regenerate `test_cases.json` from the final rule base (this needs LLM
calls), or map the existing test cases onto the current rule names.

---

### Bug 6. The impact part of the reward is always at its maximum

**In plain words.** The LLM learns from a score that compares each test with "normal"
reference numbers. The reference numbers were taken from **one** switch, but the
measurements add up **two** switches. Every test, even one that changes nothing, looks like
a huge change, and that part of the score is stuck at its maximum.

**Details.**

- `reward_calculator.py:21-25` sets `BASELINE_RECEIVED = 3559`,
  `BASELINE_FORWARDED = 1757` and `BASELINE_POLICING = 1802`. These are switch A's numbers
  alone.
- `log_parser.py` sums both switches: an unmutated run gives 7,118 received,
  3,626 forwarded and 3,492 policed.
- `_compute_impact_score` averages the relative differences, multiplies by 5, and caps
  at 1.0.

**Evidence.** Recomputing the impact score from the logged counters gives **1.0 in
2,800 of 2,800 iterations** (all 14 campaign files).

**How it was found.** The independent review flagged it; I recomputed the score with an
exact copy of `_compute_impact_score` over every logged iteration.

**Why it matters.**

- The impact term (weight 0.5) gave the LLM no information.
- This is consistent with the ablation finding that feedback adds little: the feedback had
  little to say.
- The paper should not describe the reward as informative without this caveat.

**Suggested fix.** Measure the baseline values from the same summed counters (an unmutated
run), or compare against a bug-free run with the same input.

---

### Bug 16. Some requested mutations are silently ignored

**In plain words.** In a few cases, a fuzzer asks for a change and the code that writes
the simulator's settings file ignores it. The test then runs without the change, but the
log still shows the request.

**Details** (`simulator_runner.py`):

| Request | What happens | Line | Affected iterations |
|---|---|---|---|
| `frame_size = 0` | `if frame_size:` treats 0 as "no value" | 192 | 13–22 per random run, 3 BOOFUZZ, 0 LLM (reviewer counts) |
| `sequence_number` (random's custom mode) | Only `sequence_number_override` is read | 218 | 5 in random_s2 (reviewer count) |
| `bag_value` together with `timing_jitter_ms` | `bag_value` is ignored | 200 | 7–15 per LLM run (reviewer count) |

Example of the last row: `llm_full_r4` iteration 44, VL 3001 (BAG 32), `bag_value` 1 with
jitter −10. The simulator received jitter −10, not −31.

**How it was found.** The independent review; I confirmed lines 192, 200 and 218 by code
reading.

**Why it matters.** Requested and executed tests differ, and the effect is uneven
across fuzzers.

---

### Bug 17. One label can count for many categories

**In plain words.** The code that turns a label into categories also accepts partial name
matches in both directions. A short or general label therefore scores several categories
at once.

**Details.** `recompute_coverage_venn.py:75`:
`norm.startswith(nc + "_") or nc.startswith(norm + "_")`. `analyze_campaigns.py` uses this
matcher, and so does the planner's steering (`strategy_planner.py:200-204`), so the
controller optimizes exactly this matcher.

**Evidence** (verified):

| Label | Categories it counts for |
|---|---|
| `switch` | 16 |
| `virtual_link` | 10 |
| `Virtual Link Bandwidth` | 3 |
| `switch_configuration.port_operational_state` | 3 |

Reviewer estimate of the inflation compared with one category per label: +9, +9, +10, +8,
+11 for LLM r1–r5, +5 for BOOFUZZ, +4 to +10 for random.

**How it was found.** The independent review; I checked the examples.

**Why it matters.** It inflates every fuzzer's coverage, and the LLM's slightly more.

---

### Bug 18. Executed Rule Coverage credits unrelated mutations

**In plain words.** "Executed" coverage counts a rule as tested when *any* of the 7
parameters changed, even one that has nothing to do with the rule. The LLM changes the
frame size in almost every plan, often to a legal size. So rules such as
`ip_header_checksum` count as executed through a harmless size change.

**Evidence** (log analysis). The same metric, but ignoring iterations whose only change is
an in-range frame size (a rough sensitivity check, not a proposed metric):

| Run | Executed coverage | Without in-range-size-only iterations |
|---|---|---|
| LLM full (mean of 5) | 47.6% | ≈34.7% |
| BOOFUZZ-style | 33.0% | 31.9% |
| Random (mean of 5) | 21.4% | 21.2% |
| A1 | 51.4% | 48.6% |
| A2 | 23.2% | 11.9% |
| A0 | 3.2% | 2.2% |

**How it was found.** Code reading of `analyze_campaigns.py:78-84` and
`executed_settings.mechanisms`, and sampling which mutation "executed" each category.

**Related.** The controller's steering and the coverage state shown to the LLM count
labels. A category whose label was logged without being executed counts as covered, and
the controller never returns to it.

**Why it matters.** The letter says the measure "does not check that the traffic violates
the labeled rule". It still relies on it for its strongest results.

---

### Bug 19. Every metric mixes both senders, all 8 VLs and both switches

**In plain words.** The numbers used for the reward and for bug detection are totals over
the whole network. Because of Bug 1, they mix the fuzzer's frames with the hidden
sender's. The fuzzer mutates one VL, but the totals also include the 7 other VLs, which
dilutes its effect.

**Details.**

- `log_parser.py` reads the end-of-run counters (`afdxFramesForwarded.*`,
  `afdxFramesDroppedPolicing.*`, `esFramesRejected`, …) and sums them.
- `frames_dropped_policing` is mostly the fuzzer's frames. `frames_forwarded` and the
  receiver counters are mostly the hidden sender's.
- Some mutation counters (`seqMutationCount`, `destMacMutationCount`) are incremented by
  both senders. `jitterAppliedMs` is the last random value drawn, not a total.

**How it was found.** Code reading of `log_parser.py` and `compute_bdr.py`, together with
the simulator runs for Bug 1.

---

### Bug 20. The feedback labels and `bugs_found` carry no information

**In plain words.** The text the LLM receives after each test rates the switch's
behaviour, but that rating is always "Excellent", and the `bugs_found` flag is never true.

**Details.**

- `feedback_analyzer.py:130` compares `policing_rate` (a percentage between 0 and 100) with
  thresholds written as fractions (`>= 0.8`), so the test is always true.
- `bugs_found` is `malformed_accepted > 0` (`feedback_analyzer.py:139`). Nothing in the
  simulator produces malformed-accepted frames.

**Evidence.** `bugs_found` is false in all 200 iterations of LLM r1 (verified) and in all
2,800 iterations (reviewer).

**How it was found.** The independent review; I checked line 130 and the r1 log.

---

### Bug 21. Metric names that do not mean what they say

- **`valid_ratio`** (`analyze_campaigns.py:112`) is the share of iterations with
  `frames_received > 0`. With background traffic on 8 VLs, that is every iteration that did
  not crash. It equals 1 minus the crash rate (BOOFUZZ 0.99 = 2 crashes). *Verified (code).*
- **`distinct_settings`** (`executed_settings.py:109`) counts the VL id even when nothing is
  mutated, although an unmutated run gives identical output on every VL. This adds up to 7
  to each run. *Reported.*
- **`payloadClampCount` and `payloadAppliedBytes`** (`afdx-demo.cc:790-818`) are not updated
  correctly in extreme mode, so they can misstate the size actually sent. *Reported.*

---

### Bug 22. The crash fix was not active when the campaigns were recorded

**In plain words.** The fix that detects a crashed simulation is in the code now. But the
revised campaigns were recorded before it worked, so their logs still contain two crashed
iterations marked as successful. The analysis corrects for this afterwards.

**Details.**

- BOOFUZZ iterations 190 and 191 have inputs that overflow the simulator's input parser
  (jitter −2,147,483,681; payload delta about −9.2e18). They crash in the replay, but the
  history records them as successful with made-up counters.
- `analyze_campaigns.py:76-78` excludes them using the replay's crash list, so the reported
  numbers are correct.
- The letter's wording ("with the corrected runner, these iterations count as not
  executed") should be adjusted.
- Related risk (reported): on Windows, `analyze_campaigns.py:77, 125` looks up replay
  results by a path with backslashes, while the replay keys use forward slashes. The crash
  list and bug-detection numbers would then be silently lost.

**Data handling to disclose:**

- `runs/superseded/credit_exhausted_records_removed.jsonl` holds 40 failed records
  (5 from each of 8 LLM runs) that were removed before the runs were resumed after the API
  credit ran out.
- `runs/superseded/llm_full_r3_crashed.jsonl` is a full run that was discarded after a
  fuzzer crash (`cannot convert float NaN to integer`) and run again.

**How it was found.** The BOOFUZZ replay reported 2 crashed iterations while the recorded
history reported 0 failures. The comment in `analyze_campaigns.py` confirmed it.

---

### Bug 23. Resuming a BOOFUZZ campaign restarts its schedule

**In plain words.** If a BOOFUZZ run is stopped and resumed, it starts its list of tests
from the beginning again.

**Details.** `boofuzz_baseline/main.py:305` resumes at `len(history)`, but the generator's
`current_index` starts at 0 (`boofuzz_strategy_generator.py:56`). The revised BOOFUZZ run
was not resumed, so its results are not affected. This may explain how the original,
stitched BOOFUZZ history came about. *Reported; line 56 verified.*

---

### Bug 24. Other code-health issues

- **The `frames` list never reaches the simulator.** `TestGenerator` builds a list of
  frames, including predefined test-case values such as `TC0`. Only the 7 fields of
  `sim_config` reach ns-3, and the logged `num_frames` describes the unused list.
- **`MutationConfig` is defined four times** (`afdx-demo.cc`,
  `afdx-traffic-generator.cc`, `afdx-end-system.cc`, `afdx-switch.cc`) and shared through
  `extern`. The copies are identical today, but if one changes, fields will be read at the
  wrong offsets without any error.
- **The generator's receive code never runs.** The scenario never calls
  `SubscribeToVirtualLink`, so its stricter sequence check and its own bug branches are
  dead code (`afdx-traffic-generator.cc:189, 749, 769, 861-907`).
- **Every generator frame gets a random bit flip.** `PollMutations` turns on fuzz mode
  whenever `mutations.json` exists (`afdx-traffic-generator.cc:1033`). *Reported.*
- **`configs/` is not tracked by git**, and the ns-3 path is hard-coded
  (`simulator_runner.py`: `/home/hodisan1994/ns-3-reset/ns-3`). The public repository
  cannot reproduce the results as it is.
- **The WSL ns-3 tree links into this repository.** In
  `/home/hodisan1994/ns-3-reset/ns-3`, `examples/AFDX_V3`, `examples/AFDX_NAV`,
  `llm_fuzzer`, `configs`, `evaluation` and others are symlinks to this Windows folder.
  Editing "the WSL copy" edits the repository, and `cp` or `tar` copies keep the links.
- **`virtual_links.csv`** shows as modified in git; the difference is line endings only.

---

## 25. Statements in the paper and letter that do not match the code

| Where | Statement | What the code does |
|---|---|---|
| Paper IV-B(b) | Conforming traffic is emitted once per BAG; the strict check does not drop conforming frames | Two senders; 49% of clean traffic is policed (Bug 1) |
| Paper IV-B(b) | Tolerance of 1% of the BAG | Tolerance is 0 (Bug 12) |
| Paper IV-B(c) | The A and B copies are sent "at exactly the same time" | B is sent 100 µs after A (`afdx-traffic-generator.cc:549-553`) |
| Paper Fig. 3, VIII-C; letter (R2 C3) | ES1 transmits, ES2 and ES3 only receive | All three transmit: ES1 sends VLs 1001–1003, ES2 2001–2003, ES3 3001–3002 |
| Letter summary; paper V-B; planner prompt | `timing_jitter_ms` is a timing offset | Random ±j for positive values, silence for negative (Bug 2) |
| Planner prompt; Exp. 3 interpretation | `frame_size` is the frame size | The sent frame is frame_size + 17 (Bug 3) |
| Letter (R2 C1) | The two missed bugs "cannot be reached through the mutation interface" | The token bucket cannot fail at all (Bug 7); the VL check is unreachable (Bug 8) |
| Letter (summary, R1 C2/C3); paper Exp. 2 | The LLM fuzzer exercises more categories, and the lead is not an artifact of the shared denominator | The baselines' label pool reaches only 90 categories; on those, BOOFUZZ leads (Bugs 4, 5) |
| Letter (Additional corrections) | Baselines re-run "on the final rule base" | Their labels come from test cases built on an older rule base (Bug 5) |
| Paper V-B; letter (R1 C4a) | The reward guides the planner | The impact term is constant (Bug 6) |
| Letter (Additional corrections) | "With the corrected runner, these iterations count as not executed" | The histories were recorded before the fix worked (Bug 22) |
| Letter (R1 C4b) | The public repository reproduces the results | `configs/` is untracked and the ns-3 path is hard-coded (Bug 24) |
| Letter (R1 C3) | Interrupted LLM campaigns "resumed from their history" | Also: 40 failed records removed, and run r3 discarded and re-run (Bug 22) |
| Letter (R2 C6) | Coverage comes from the controller's steering, not the LLM | Steering's re-plan step is itself an LLM call; a "controller + random planner" control is needed to separate them |

---

## 26. How to reproduce the simulator results

All commands run in WSL (`wsl -d Ubuntu-24.04`). They use the existing build and write only
to `/tmp`.

**Run one input without touching the tree.** This uses the same mechanism as
`SimulatorRunner(work_dir=...)`.

```bash
NS=/home/hodisan1994/ns-3-reset/ns-3
W=/tmp/afdx_work/clean
mkdir -p $W/examples/AFDX_V3/output/csv $W/examples/AFDX_V3/output/pcap $W/examples/AFDX_V3/config
cp $NS/examples/AFDX_V3/config/virtual_links.csv $W/examples/AFDX_V3/config/
cat > $W/examples/AFDX_V3/mutations.json <<'EOF'
{"vlId": 1002, "prob": 0.0, "payload_delta_bytes": 0, "timing_jitter_ms": 0,
 "mac_mutation": "none", "is_extreme_test": true, "sequence_number_override": 0,
 "dest_mac_mutation": "none", "inject_bug": "none"}
EOF
cd $NS && ./ns3 run afdx-demo --no-build --cwd $W > $W/stdout.txt
```

- **Bug 2:** set `timing_jitter_ms` to −1 or −3. In
  `$W/examples/AFDX_V3/output/csv/AFDX-LOG-OUTPUT.csv`, the fuzzer's frames for VL 1002
  are the `TX` rows on network `A` with `PacketSize` 323; the hidden sender's have 530.
- **Bug 1:** count `RX` rows per node and per size for VL 1002 with `t >= 0.1`. The
  subscribers (nodes 1 and 2) receive only 530-byte frames.

**Testing a simulator change.**

1. Copy the tree to `/tmp`.
2. Replace every symlink with a real copy **before** editing: find them with
   `find . -maxdepth 2 -type l`, and check each one with `readlink -f`.
3. Configure the copy:
   `./ns3 configure --build-profile=default --enable-examples --disable-tests --enable-modules='core;network;internet;csma;bridge'`
4. Build with `./ns3 build afdx-demo`.
5. Confirm that `CMAKE_HOME_DIRECTORY` in `cmake-cache/CMakeCache.txt` points to the copy.

---

## 27. Open questions and suggested next steps

1. Confirm with the author whether the end-system sender is intended (Bug 1).
2. Fix Bugs 1, 2 and 3 in the simulator, then replay every logged campaign input on the
   fixed simulator. This needs no LLM calls and gives corrected Experiment 3 numbers.
3. Decide how to make the coverage comparison fair (Bugs 4, 5, 17, 18). Regenerating
   `test_cases.json` from the final rule base needs LLM calls.
4. Replace the 8-bug suite with faults that the fuzzers can actually reach and that can
   separate them (Bugs 7–10). The reviewer's suggestions fit: an off-by-one sequence
   window, wraparound, a wrong BAG unit.
5. Fix the reward baseline (Bug 6), or state in the paper that the impact term was
   constant during the campaigns.
6. Find the exact source of the 264 baseline receiver rejections (Bug 11).
7. Correct the statements in Section 25 before resubmission.
8. Commit `configs/` (or archive it with the artifact), and make the ns-3 path
   configurable.
