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

## Stage 7: new fuzzing campaigns (2–3 days, about $150–200, approval needed)

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
| 4–8 | Not started |

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
