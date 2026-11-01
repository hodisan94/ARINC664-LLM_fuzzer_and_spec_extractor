# Fix Plan for the Revision Bugs

**Created:** 2026-10-28
**Deadline:** revision due 2026-11-13
**Bug numbers** refer to `context/REVISION_FINDINGS.md`.

The plan runs from the simplest fixes to the most involved. Stages 1–5 need no paid LLM
calls. Stages 6 and 7 do, and need approval before they start.

## Ground rules

- **Second sender:** confirm with the author whether the second sender is intentional
  (Bug 1). Stage 2 depends on the answer; the other stages do not.
- **Branch:** fixes go on the branch `fix/revision-bugs` (created from `revision`), one
  commit per fix, so each change can be reviewed or reverted on its own. The work is done
  in a separate git worktree. The author's WSL ns-3 tree links into the main checkout, so
  editing that checkout would change what the WSL tree builds.
- **Simulator testing:** simulator changes are built and tested in a separate,
  self-contained copy of ns-3 (`/tmp/ns3_fixtest`), never in the author's WSL tree.

## Stage 1: small, isolated fixes (about 1 day, $0)

Each fix is a few lines and does not change the experiment's design.

| Fix | Bugs | Check |
|---|---|---|
| Accept Windows line endings in `virtual_links.csv` | 25 | Simulator runs with a CRLF copy |
| Make the 1% BAG tolerance actually 1% | 12 | Small test |
| Count token-bucket drops separately from BAG drops | 13 | Counter names in the output |
| Receiver checks payload size against the VLs it *receives* | 14 | Simulator run |
| Stop ignoring requests: `frame_size = 0`, `bag_value` together with timing | 16 | Rebuilt settings for the logged inputs |
| Feedback compares the policing rate in the right unit (percent, not fraction) | 20 | Recompute over the logs |
| Clearer metric definitions (`valid_ratio`, `distinct_settings`) | 21 | Recompute |
| Windows path keys in the analysis script | 22 | Run the analysis on Windows |
| BOOFUZZ continues its schedule when resumed | 23 | Resume test |
| Configurable ns-3 path instead of a hard-coded one | 24 | Run with the setting |

These should not change the paper's numbers much. They remove traps for the later stages.

## Stage 2: core simulator fixes (2–3 days, $0)

1. Remove the hidden second sender (Bug 1): the end systems no longer transmit.
2. Fix "send faster / slower" (Bug 2): a fixed, signed time offset instead of the broken
   random one.
3. Fix the 17 extra bytes (Bug 3): a requested frame size becomes exactly that frame size.
4. Fix the reward's reference values (Bug 6).
5. Update the planner prompt so it describes what each parameter really does.

**Checks:**

- The simulator's unit tests pass.
- A clean run has 0 drops and 0 rejections.
- Boundary tests on every VL: exactly the maximum frame size passes; one byte more is
  rejected.
- "Send faster" really sends faster, and the switch catches it.
- The receivers see the fuzzer's frames.

## Stage 3: re-score coverage from the existing logs (about 1 day, $0)

- Count one category per label instead of several (Bug 17).
- Report coverage on the 90 categories every fuzzer can reach (Bug 4).
- If possible, count a rule as "executed" only when the mutation matches that rule
  (Bug 18). This needs a table of which parameters can test which rules.

## Stage 4: replay the existing tests on the fixed simulator (about 1 day, $0)

Replay all ~2,800 logged inputs on the old and the fixed simulator, with and without each
injected bug. This gives honest bug-detection numbers for the tests that were already
chosen, and shows how much the ranking changes.

## Stage 5: rebuild the injected-bug suite (2–3 days, $0)

- Remove the undetectable bugs (Bugs 7–8) and merge the duplicate (Bug 9).
- Add reachable bugs that can separate the fuzzers, for example an off-by-one sequence
  window, a wraparound error, or the BAG in the wrong unit.
- Each bug must pass two checks: it is **not** detected by an unmutated input, and **at
  least one** input detects it.
- Decide how to handle sequence numbers being discarded as duplicates before they are
  checked (Bug 11).

## Stage 6: fix the test-case data (1–2 days, paid LLM calls)

The test cases still come from March, from an older rule extraction (Bug 5). Either:

- **regenerate them** from the current rules (paid LLM calls), or
- **map the old names** onto the current rules where they match (free, but partial).

Either way, the baselines get the same label universe as the LLM fuzzer.

## Stage 7: new fuzzing campaigns (2–3 days, about $150–200, approval needed; done, see Status)

These run only after Stages 2, 5 and 6.

| Campaign | Runs | Approximate cost |
|---|---|---|
| LLM fuzzer | 5 | about $80 |
| Random | 5 | free |
| BOOFUZZ | 1 | free |
| Ablation (all 3 variants) | repeated | about $80 |
| "Controller + random planner" control | — | cheap or free |

The last row answers what the LLM adds beyond the controller.

## Stage 8: update the paper and the response letter (2–3 days)

- Correct the statements listed in Section 25 of `REVISION_FINDINGS.md`.
- Report the new numbers.
- Choose the framing that fits the results.

## Timeline

| Stages | Working days | Cost |
|---|---|---|
| 1–5 | 7–9 | none |
| 6–8 | 6–8 | paid LLM calls in 6 and 7 |

Paid runs need to start by about 2026-11-05. If time runs short, Stage 4 gives honest
Experiment 3 numbers and Stage 3 gives honest Experiment 2 numbers, both without new
campaigns.

## Status

| Stage | Status |
|---|---|
| 1 | Done (2026-10-28), branch `fix/revision-bugs`, one commit per bug |
| 2 | Done (2026-10-28), same branch, one commit per fix |
| 3 | Done (2026-10-28), same branch; recorded campaigns re-scored, nothing re-run |
| 4 | Done (2026-10-28), same branch; all logged inputs replayed on the fixed simulator |
| 5 | Done (2026-10-29), same branch; 10-bug suite built, checked and used to re-score all recorded inputs; see `context/BUG_SUITE.md` |
| 6 | Done (2026-10-30), same branch; test cases regenerated from the current rules, `configs/test_cases_rules_2026-10.json` |
| 7 | Done (2026-10-31), same branch; 14 campaigns of 200 iterations, scored; `ec29788`, see "Stage 7 results" |
| 8 | Not started |

### Stage 7 results

Details of the runs, the interruption and the scoring commands:
`evaluation/results/revision/runs/stage7/README.md`. Metrics:
`evaluation/results/revision/campaign_metrics_stage7.json`; bug replay:
`bdr_replay_stage7.json`.

- **Setup.** Code `c348e53`, fixed simulator, 10-bug suite, new test cases (626 rules), neutral
  planner instructions, gpt-5. LLM full ×5, A0, A1, A2, random ×5 (seeds 1–5), BOOFUZZ ×1;
  200 iterations each. The controller's fixed test schedule (iterations 21–46) was kept (6.1a
  in PAPER_CHANGES). No "controller + random planner" control was run.
- **Interruption.** The OpenAI project spend limit stopped the 8 LLM runs at iterations
  65–135; the 40 failed records (5 per run) were removed and kept, and the runs were resumed
  from their histories after the limit was raised. Verified that the kept prefixes are
  unchanged and the planner flags match before and after.
- **Cost.** $106.60 (full runs $15.90–16.52, A0 $4.82, A1 $6.49, A2 $14.28). One BOOFUZZ
  simulator failure; no crash in the replay.

| Fuzzer | Rule Coverage (paper, of 185) | Mechanism-matched coverage (of 54 testable) | Bugs found (of 10; 8 reachable) | Iterations without mutation |
|---|---|---|---|---|
| LLM full (5 runs) | 121, 113, 110, 112, 114 (mean 114.0) | 35, 38, 37, 37, 39 (mean 37.2) | 8, 8, 8, 8, 8 | 2–4 |
| Random (5 runs) | 106, 112, 108, 103, 102 (mean 106.2) | 20, 15, 18, 15, 18 (mean 17.2) | 7, 7, 7, 7, 7 | 55–69 |
| BOOFUZZ (1 run) | 184 | 27 | 7 | 68 |
| A0 | 8 | 4 | 7 | 0 |
| A1 (steering only) | 78 | 31 | 8 | 0 |
| A2 (feedback only) | 83 | 27 | 8 | 3 |

Exact two-sided Mann–Whitney, LLM full vs. random (5 vs. 5): Rule Coverage p = 0.024,
mechanism-matched coverage p = 0.008, bugs found p = 0.008. BOOFUZZ has one run, so it is not
tested. Unique Findings (labels, paired runs): BOOFUZZ 30–35, LLM 0, random 0. BOOFUZZ reaches
80% of the categories at iteration 119; no other run reaches 80%.

- **Bugs.** All runs find the same 7 reachable bugs; only the LLM-guided runs (and A0–A2) also
  find `max_frame_off_by_one` (1–4 detecting inputs per full run). As predicted before the
  runs (BUG_SUITE §6), this bug favours the LLM. The LLM-guided runs also trigger the BAG
  bugs far more often (`skip_bag_policing` 59–72 detecting inputs vs. 11–28;
  `loose_bag_tolerance` 39–53 vs. 11–22).
- **Coverage.** By labels, BOOFUZZ is highest because it walks through the test-case list;
  with the new list that reaches 184 categories. Counting only categories whose iteration
  executed a mutation that can exercise them, the LLM fuzzer is highest.
- **Ablation.** One run per variant. Steering alone (A1) keeps most of the matched coverage;
  without steering and feedback (A0) the planner repeats a few rules (40 of its first 65
  iterations used one label).
- **Not usable for these runs:** the "shared" universe in `analyze_campaigns.py` is still
  computed from the old `configs/test_cases.json`.
- **Interim result, same picture:** at the first 65 iterations of every run, LLM 51–54 vs.
  random 52–59 by labels, 21–23 vs. 5–11 matched, bugs 8,7,8,8,8 vs. 7.

### Stage 6 results

- **Root cause found first** (`1ddfb79`): the test-case schema let the LLM name each
  parameter itself, so the keys of `test_cases.json` often matched no rule. Regenerating
  without this fix would have repeated Bug 5. Test cases are now filed under the rule's full
  name (`Category.rule`); the LLM's own parameter name is kept inside each test case.
- **Generation** (`b2acfbf`): 626 rules of `configs/spec_rules_filtered.json`, one call each,
  GPT-4o (`gpt-4o-2024-08-06`, temperature 0.7, as in the paper), 2026-10-30, 48 minutes,
  **$3.98** at list prices (266,659 input and 331,566 output tokens). Every rule answered;
  3,989 test cases (4–18 per rule, mostly 6–7). A 10-rule sample ($0.06) was run first.
- **Reach:** every one of the 626 names maps to a rule category, reaching **184 of 185**
  categories, which is every category the matcher reaches from rule names (one category is
  reached by no rule name at all, a matcher artifact). The old file reaches 90.
- The old `configs/test_cases.json` is unchanged. The per-call log with token use is
  `spec_extraction/test_case_extraction_2026-10.jsonl`.
- **Needed before Stage 7:** the LLM fuzzer takes `--test-cases`, but the BOOFUZZ and random
  baselines read `configs/test_cases.json` from a constructor default and have no command-line
  option. Add the option so that all three use the new file.
- **Note for the paper:** the paper reports 2,703 test cases; the new file has 3,989.


### Stage 5 bug suite, fixed before any scoring (decided 2026-10-29)

This list was agreed before any campaign was scored against it, so that no bug is chosen
for the fuzzer that finds it. Every fuzzer is scored against the same list.

| # | Bug ID | What it switches off | Status |
|---|---|---|---|
| 1 | `skip_bag_policing` | Switch BAG check | Kept |
| 2 | `skip_frame_validation` | Whole switch frame-size check (too big and too small) | Kept |
| 3 | `skip_mac_validation` | Switch source-MAC check | Kept |
| 4 | `skip_token_bucket` | Switch token bucket | Kept, reported as unreachable (Bug 7) |
| 5 | `skip_vl_check` | Switch VL authorization | Kept, reported as unreachable (Bug 8) |
| 6 | `skip_constant_field` | Receiver check of the 03:00:00:00 MAC prefix | Kept |
| 7 | `skip_sequence_check` | Receiver sequence-number check | Kept; reachable only indirectly (Bug 11), documented |
| 8 | `accept_oversized` | Only the "too big" half of the switch frame-size check | Changed: no longer identical to #2 (Bug 9) |
| 9 | `max_frame_off_by_one` | Switch accepts a frame one byte above the VL's MaxFrame | New |
| 10 | `loose_bag_tolerance` | Switch BAG check allows 10% early arrival instead of 1% | New |

Acceptance checks for every bug: (a) an input with no mutation does not detect it;
(b) at least one input that the mutation parameters can express detects it, except the two
bugs listed as unreachable. Results are reported per bug and as "detected of 10" and
"detected of 8 reachable".

Known bias to report: in Stage 4 BOOFUZZ and Random often sent frames exactly one byte past
the limit, and the LLM frames exactly at the limit, so bug 9 may favour the baselines.

**Correction after scoring (the list above was not changed):** the baseline frames "one byte
past the limit" were one byte below MinFrame, not above MaxFrame. No baseline input is
exactly MaxFrame + 1, and every LLM-guided run has 4–7 such inputs, so bug 9 favours the
LLM-guided fuzzer, not the baselines.

### Stage 5 results

Full description, acceptance checks and per-bug results: `context/BUG_SUITE.md`.

- All 10 bugs pass both acceptance checks on the fixed simulator; the two unreachable bugs
  are detected by no probe, as expected. All AFDX unit tests pass.
- Recorded inputs re-scored against the 10-bug suite (found of 10; the two unreachable bugs
  are found by nobody, so this equals found of 8 reachable): LLM-guided 8, 7, 7, 7, 8;
  BOOFUZZ-style 7; Random 7 in every seed; A0 6, A1 8, A2 7; pilot original 7, 8; pilot
  revised 8, 8.
- `max_frame_off_by_one` is found by every LLM-guided run and by no baseline run;
  `skip_sequence_check` by every baseline run and by 2 of 5 LLM-guided runs.

### Open: planner instructions reveal the simulator's implementation (decided 2026-10-29 to postpone)

Both the original and the revised planner instructions (`llm_fuzzer/prompts/fuzzing_agent.py`,
`_MUTATION_PARAMETERS`, `_MECHANISM_DESCRIPTIONS`, `_GUIDELINES_2_TO_4`) contain hand-written
knowledge of how this simulator is built, which a real tester would not have and BOOFUZZ and
Random do not get. Original: "`spoof_src` => finds bugs in switch MAC validation", "negative
jitter => finds bugs in BAG policing". Revised: "`wrong_vl` ... nothing checks", "no input can
exercise" the token bucket, "the receiver discards repeats as duplicates", "dropped at the
switch", "the receiving ES rejects".

**Errors in the revised text found by the review of 2026-10-30** (the pilot of `d3b7e46` ran
with this text):

- It still recommends test cases in three passages shared by both versions
  (`fuzzing_agent.py:314`, "Example 1 - Using PREDEFINED test cases" at line 513 with every
  mutation parameter null, and "3. COMBINE both" at line 502). Commit `1e3bfc9` claimed to
  remove the recommendation; it removed it only from the guidelines.
- It says all five `mac_mutation_type` values change the source MAC; in
  `afdx-traffic-generator.cc:372-416` `spoof_dst` and `broadcast` change the destination
  MAC and `zero_mac` changes both.
- It says no input can exercise the token bucket, but the mechanism list still advertises
  `token_bucket_stress` as an untested mechanism, and the controller still schedules it
  (`strategy_planner.py:429`).
- The output schema still says `sequence_number_override` is 0–255, while parameter 6 says
  256 sends sequence number 0.
- `prompt_version` (and `ablation_mode`) are missing from the error records of
  `llm_fuzzer/main.py`, and `--resume` does not check that the version matches.

**Neutral version written (2026-10-30, `8018ba4`)**: `--prompt-version neutral`. Not yet
piloted.

**Also implementation knowledge, outside the prompt:** the controller's steering
(`strategy_planner.py:402-440`, active in `full` and `A1`) injects a fixed schedule of
standalone tests at iterations 21, 26, 31, 36, 41 and 46: `spoof_src`, `corrupt_prefix`,
frame size 2000, timing −5 ms, sequence override 255, and the token-bucket stress. These
target the injected bugs directly, whatever the prompt says. A neutral prompt does not
remove this; it needs its own decision (keep and disclose, or remove).

To do before the Stage 7 campaigns:
- Add a third, "neutral" prompt version that keeps only how to operate the mutation parameters
  (what each one changes, allowed values, 0 = no override, `test_cases` are not sent to the
  simulator) and protocol facts from the extracted rules; remove every statement of what the
  simulator drops, rejects, ignores or "finds bugs" in.
- Pilot it like the original/revised pilot (2 runs x 100 iterations, about $16, ask first).
- Say in the paper that the prompt describes the mutation interface, and that the submitted
  version also contained implementation hints.

### Stage 1 results

**How it was checked**

- **Simulator test programs.** Built in `/tmp/ns3_fixtest` from the fix branch; all
  145 tests pass (58 sending end system, 46 switch, 41 receiving end system), the same
  as on the unchanged code.
- **Translation.** The previous translation is kept as `legacy=True`.
  `executed_settings.Translator`, and through it `bdr_replay.py`, uses it, so analyses of
  the recorded campaigns are unchanged. Legacy mode reproduces the logged `sim_config`
  of all 2,800 recorded iterations.

**What each fix changes**

| Bug | Fix | Effect |
|---|---|---|
| 25 | CRLF `virtual_links.csv` | The simulator loads LF and CRLF files with identical results. |
| 12 | BAG tolerance | **This changes the clean baseline.** Forwarded 3,626 → 3,651, BAG drops 3,492 → 3,467, receiver rejections 264 → 214. Reverting only this line restores the original numbers exactly, so the whole change comes from this fix. Some frames arrive a few microseconds early because of queueing, and the old zero tolerance dropped them. This contradicts the "no demonstrated effect" status of Bug 12 in `REVISION_FINDINGS.md`. |
| 13 | Separate token-bucket counter | New counter `afdxFramesDroppedTokenBucket`, 0 in all checked runs. `skip_token_bucket` is now detected through it. |
| 14 | Receiver size check | No change in the clean run. With Bug 1 still present, oversized fuzzer frames never reach the receivers, even with frame validation skipped. It becomes observable after Stage 2. |
| 16 | Ignored requests | The fixed translation differs from the logged inputs in 0–22 iterations per run (random 16–22, LLM 7–15, BOOFUZZ 3). |
| 20 | Policing rate units | On the logged runs every iteration is now labelled "Fair" instead of "Excellent", because of the 49% clean drop rate (Bug 1). It becomes informative after Stage 2. `bugs_found` is unchanged: it is a valid oracle that the bug-free simulator never triggers. |
| 21 | Metric names | `distinct_settings` falls by 6–7 per run (A0 and A1 are unchanged). `valid_ratio` is renamed `noncrash_ratio`; the table row is now "Non-crashing iterations". |
| 22 | Windows paths | Checked: a backslash path now finds the BOOFUZZ crash list. |
| 23 | BOOFUZZ resume | A campaign resumed at iteration 120 now plans the same 200 violations as an uninterrupted one. The old code did not. |
| 24 | ns-3 path | Set with `AFDX_NS3_PATH`; the default is unchanged. |

**Notes for Stage 2**

- `compute_bdr.run_single_iteration` (the original Experiment 3 script) still calls the
  runner's current translation. Use `bdr_replay.py` to reproduce the recorded results.
- The planner prompt says `sequence_number_override` 0 means "invalid". In the
  simulator, 0 means "no override". *(Fixed in Stage 2.)*

### Stage 2 results

**Commits**

| Commit | Fix |
|---|---|
| `203302e` | Bug 1: the end systems only receive; one sender per VL |
| `7f68b29` | Bug 2: `timing_jitter_ms` is a fixed signed offset |
| `f0e35af` | Bug 3: exact frame size; the extreme-mode clamp counter is fixed |
| `0d6d02b` | Bug 6: reward impact baseline from the fixed simulator, as a share of traffic |
| `1e3bfc9` | Planner prompt and feedback describe the parameters as the simulator applies them |

The author has **not** confirmed whether the second sender (Bug 1) was intended.

**Checks** (fixed build in `/tmp/ns3_fixtest`)

- **Simulator test programs:** all 145 still pass.
- **Clean run:** received 3,380 = forwarded 3,380 = end-system received 3,380. Policing
  drops 0, token-bucket drops 0, frame and MAC errors 0, receiver rejections 0. Each frame's
  network-B copy is discarded as a duplicate (3,380), as A/B redundancy intends.
- **Frame-size boundaries, all 8 VLs:** frame sizes Min and Max pass; Min−1 and Max+1 are
  rejected by frame validation.
- **Timing, VL 1002 (BAG 4 ms):**

  | `timing_jitter_ms` | Result |
  |---|---|
  | 0 | 450 frames, gap 4.0 ms |
  | −1 | 600 frames, every gap 3.0 ms, 600 policing drops |
  | −3 | every gap 1.0 ms |
  | +2 | every gap 6.0 ms, no drops |
  | −1 with `skip_bag_policing` | no policing drops |

- **The receivers get the fuzzer's frames:** 450 per network per subscriber on VL 1002,
  all from the traffic generator.
- **Reward impact term:**

  | Input | Impact |
  |---|---|
  | Clean run | 0.000 |
  | Legal frame size | 0.000 |
  | Size violations | 0.067–0.533 |
  | Timing −1 ms | 0.444 |
  | Timing −3 ms | 1.000 |
  | Timing +2 ms (legal, slower) | 0.266 |

  Impact measures the change in traffic, not whether a rule was violated.

**Injected-bug detection**

8 inputs from before, plus 2 new ones, each run bug-free and with each of the 8 bugs:

| Input | Original simulator | After stages 1–2 |
|---|---|---|
| No mutation | BAG, sequence | none |
| Frame 1,000 B on VL 3002 (legal) | BAG, sequence | none |
| Fake source MAC | BAG, MAC, sequence | MAC |
| Wrong destination MAC (`wrong_vl`) | BAG, sequence | none |
| Forced sequence number 255 | BAG, sequence | none |
| Timing −12 ms (VL 2002) | BAG, sequence | **BAG** |
| Frame 1,000 B + timing +100 ms | BAG, sequence | none |
| Drop half at sender | BAG, sequence | none |
| Frame 1,025 B on VL 3001 (new) | — | frame, oversized |
| Corrupt destination prefix (new) | — | constant field |

**Still to do**

- These inputs never detect the sequence, token-bucket and VL-check bugs. That is
  Bugs 7, 8 and 11, for Stage 5.
- `skip_frame_validation` and `accept_oversized` are still the same check (Bug 9).

### Stage 3 results

**Commits**

| Commit | Change |
|---|---|
| `1116a2d` | Bug 17: one category per label (`build_single_matcher`) |
| `f866995` | Bug 4: coverage on the label universe shared by all fuzzers |
| `52d5a49` | Bug 18: mechanism-matched coverage |
| `5516145` | Re-scored metrics saved as `evaluation/results/revision/campaign_metrics_rescored.json` |

The original `campaign_metrics.json` is untouched. Every metric present in both files is
identical, except `distinct_settings` (Stage 1) and `valid_ratio`, which is renamed
`noncrash_ratio`.

**New finding (Bug 26): the 185 categories are 153 distinct names.** 31 groups differ
only in case, spaces, underscores or hyphens ("Frame Size" / "frame_size", "Physical
Layer" / "Physical_Layer" / "physical_layer"). The paper's matcher merges each group to
one member, so the others are almost unreachable, and every coverage percentage over 185
is understated. The new measures count over the 153 merged names.

**The mechanism table (Bug 18).** It is approximate, built from category names. 54 of
the 153 merged categories can be tested by at least one simulator parameter. The other
99 cannot: IP and UDP fields, ports, configuration, initialization, and generic names
such as "Switch" or "Performance". The rules are conservative and identical for every
fuzzer. Review them in `category_mechanisms.json`.

**Re-scored recorded campaigns** (mean over runs; LLM and Random have 5 runs, the others
1):

| Measure | Universe | LLM | BOOFUZZ | Random | A1 | A2 | A0 |
|---|---|---|---|---|---|---|---|
| Labels, paper matcher | 185 | 95.4 | 86 | 47.2 | 95 | 49 | 6 |
| Executed, paper matcher | 185 | 88.0 | 61 | 39.6 | 95 | 43 | 6 |
| Labels, one category per label | 153 merged | 85.0 | 72 | 41.0 | 88 | 42 | 5 |
| Executed, one category per label | 153 merged | 79.2 | 51 | 34.4 | 88 | 35 | 5 |
| Labels, shared universe | 90 | 65.4 | **86** | 47.2 | 54 | 49 | 6 |
| Executed, shared universe | 90 | 58.2 | **61** | 39.6 | 54 | 43 | 6 |
| Labels, merged and shared | 75 | 54.0 | **72** | 41.0 | 47 | 42 | 5 |
| Executed, merged and shared | 75 | 48.4 | **51** | 34.4 | 47 | 35 | 5 |
| Mechanism-matched | 54 testable | **24.0** | 14 | 6.4 | 32 | 8 | 3 |
| Mechanism-matched and shared | 27 | 14.2 | 14 | 6.4 | 17 | 8 | 3 |

**How to read the table**

- On every measure restricted to the shared label universe, BOOFUZZ is level with or
  ahead of the LLM fuzzer.
- Only the mechanism-matched measure over all testable categories favors the LLM fuzzer
  (24.0 vs 14). That lead comes from categories the baselines cannot name.
- These numbers come from the **recorded campaigns**, which ran on the unfixed simulator.
  Coverage is computed from labels and planned parameters, so the simulator bugs do not
  change it directly. They did shape what the LLM was told and which feedback it received.

**Other notes**

- Running `analyze_campaigns.py` on Windows needs `PYTHONUTF8=1`: some files are read with
  the system's default encoding. This is a portability issue only.
- The controller's steering (`strategy_planner.rule_category`) still uses the paper's
  matcher. Changing it would change future campaigns, so it is left for the Stage 7
  decision.

### Stage 4 results

All 8,199 distinct (input, bug) runs behind the submitted Experiment 3 were replayed on the
fixed simulator (stages 1–2), as logged, with no LLM calls (commit 306c301). The submitted
`bdr_replay_v2_*.json` files are unchanged; the new results are `bdr_replay_fixed_*.json`.
The same 2 BOOFUZZ inputs (out-of-range integers) crash both simulators.

**Bugs detected (of 8), submitted → fixed simulator**

| Campaign | Submitted | Fixed | Lost |
|---|---|---|---|
| LLM, 5 runs | 6, 6, 6, 6, 6 | 6, 5, 5, 5, 6 | sequence check in r2–r4 |
| BOOFUZZ re-run | 6 | 6 | – |
| Random, 5 seeds | 6 each | 6 each | – |
| A0 / A1 / A2 | 6 / 6 / 6 | 5 / 6 / 5 | sequence check (A0, A2) |
| Submitted LLM / BOOFUZZ (reconstructed) | 6 / 6 | 6 / 6 | – |
| Submitted Random, as compute_bdr rebuilt it | 2 | 0 | BAG, sequence check |

Token bucket and VL check are detected by no campaign on either simulator (bugs 7, 8;
stage 5).

**What changed underneath the counts**

- On the submitted simulator, BAG-policing and sequence-check detection fired in **every**
  iteration (200 of 200; 198 for BOOFUZZ, whose 2 crashed iterations do not count). The hidden second sender (bug 1) produced 3,492 policing drops
  and 264 rejections even in the clean run, so any input "detected" those bugs. On the
  fixed simulator the clean run has 0 drops and 0 rejections, and detection needs an input
  that actually violates the rule. Example: BAG detection, LLM mean 31.6 detecting
  iterations of 200, Random 31.2, BOOFUZZ 25.
- **Sequence check** is now found mainly through timing overload, not through the
  sequence-number override: sending a VL far faster than its BAG causes long bursts of
  policing drops, and the resulting gaps in the received sequence numbers trip the
  receiver's check. Of the 70 detecting inputs in the Stage 5 cache, 63 have a negative
  timing offset and 57 have no sequence override; a constant non-zero override is discarded
  earlier as a duplicate (Bug 11). *(Corrected 2026-10-30; an earlier version said the
  override found it.)* Detecting iterations: LLM 0–2 (found in 2 of 5 runs); Random about
  13 per seed (5 of 5); BOOFUZZ 8.
- **Frame size** (skip_frame_validation, accept_oversized): the frame size starts at the
  midpoint of the VL's range plus the logged delta. The LLM often chose deltas that land
  **exactly on** MaxFrame or MinFrame (e.g. +224 on VL 1001 = 512 bytes; 39–43% of the
  iterations with a size change). The 17-byte header bug (bug 3) made those frames
  invalid, so they "detected" the bug; now they are valid. LLM detecting iterations fell
  from 82.6 to 17.8 per run. BOOFUZZ and Random chose deltas one byte **below MinFrame**
  (e.g. −225 = 63 bytes), which the header bug made valid; their detecting iterations rose
  (BOOFUZZ 39 → 86, Random 45.8 → 65.0).

**How many logged inputs change anything** (`replay_effects.py`; counters compared with
the clean run of the same simulator; of 200)

| Campaign | Submitted simulator | Fixed simulator |
|---|---|---|
| LLM r1–r5 | 105–117 | 54–68 |
| BOOFUZZ | 97 | 122 |
| Random s1–s5 | 115–128 | 103–126 |

On the submitted simulator any change to the fuzzed VL's timing moved the noisy policing
count, so these numbers overstate effective tests there.

**How to read this**

- The headline BDR (6/8 for every fuzzer) barely moves, but on the submitted simulator two
  of those six bugs were found by every input. On the fixed simulator the LLM's recorded
  tests find **fewer** bugs than both baselines and change the bug-free simulator in only
  about a third of iterations, against about half or more for the baselines.
- These are the **same inputs**, chosen while the LLM was steered by wrong feedback and
  wrong instructions. They show what the submitted tests do, not what the LLM fuzzer does
  on a correct simulator. That needs new campaigns (stage 7).
- Before stage 7, stage 5 must make the token-bucket, VL and sequence bugs detectable.
