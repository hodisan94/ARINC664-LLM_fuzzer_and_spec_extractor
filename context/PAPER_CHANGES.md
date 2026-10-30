# Changes Needed in the Paper and the Response Letter

**Created:** 2026-10-30. **Keep this file up to date** whenever a fix, a run or a decision
affects what the paper or the letter says.

**Sources:** `context/REVISION_FINDINGS.md` (Bug numbers), `context/FIX_PLAN.md` (stage
results), `context/BUG_SUITE.md` (Experiment 3). Section numbers refer to the revised
manuscript of 2026-10-24 and its response letter.

**Status labels:**

- **Ready**: the new text can be written now.
- **Needs Stage 7**: the numbers come from the new campaigns.
- **Decision**: needs a decision first.
- **Verify**: a statement that has not been checked against the code yet.

---

## 1. Simulator description (Section IV)

| # | Where | What the paper says now | What to change | Source | Status |
|---|---|---|---|---|---|
| 1.1 | IV-B(b) switch implementation | "Conforming traffic is emitted exactly once per BAG … the stricter check does not drop conforming frames" | Was false in the submitted simulator: a second, unmutated sender on every VL caused 3,492 policing drops and 264 receiver rejections in a run without mutation. Now true after the fix. Say the second sender was removed, and that every result was recomputed on the corrected simulator. | Bug 1, `203302e` | Ready |
| 1.2 | IV-B(b) | "minus a tolerance of 1% of the BAG" | Was effectively 0 (integer milliseconds truncated); now 1% in microseconds. The fix alone changed the old clean run (BAG drops 3,492 → 3,467). The text can stay; add the correction to the list of simulator fixes. | Bug 12, `7f00f08` | Ready |
| 1.3 | IV-B(b) | Policing: strict inter-arrival check, then token bucket | Add that the token bucket can never drop a frame that passed the inter-arrival check in this configuration (refill per BAG exceeds the largest frame), so the bucket is never exercised. Token-bucket drops are now counted separately. | Bugs 7, 13 | Ready |
| 1.4 | IV-B(c) redundancy | The A and B copies are sent "at exactly the same time" | In the code the B copy is sent 100 µs after A (`afdx-traffic-generator.cc:560-563` on the fix branch). Correct the sentence, or change the code. | REVISION_FINDINGS §25 | Decision |
| 1.5 | Fig. 3 caption, VIII-C | "ES1 transmits …; ES2 and ES3 act as receivers" | The VL configuration has sources in all three end systems (ES1: VLs 1001–1003, ES2: 2001–2003, ES3: 3001–3002). Correct the caption and the topology text. | REVISION_FINDINGS §25 | Verify against the fixed build, then Ready |
| 1.6 | II-C(b) vs. IV | The standard's receiver accepts SN in [PSN+1, PSN+2] and SN 0 (reset) | The simulator's receiver rejects SN 0 and accepts any SN up to 128 ahead. Describe the simulator's rule in Section IV and say it differs from the standard; it matters for `skip_sequence_check`. | BUG_SUITE §3 bug 7 | Ready |
| 1.7 | IV-B(b) / II | Receiver frame-size check | The receiver checked payload size against the VLs it sends, not the VLs it receives; fixed. Mention in the list of fixes. | Bug 14, `ea41044` | Ready |
| 1.8 | IV, new paragraph or appendix | — | Add a short list of the simulator corrections made during the revision (Bugs 1, 2, 3, 12, 13, 14, 25) and state that all campaigns and replays were re-run on the corrected simulator. Reviewers will compare with the submitted numbers. | FIX_PLAN Stages 1–2 | Ready |

## 2. Fuzzing harness and method (Section V)

| # | Where | What the paper says now | What to change | Source | Status |
|---|---|---|---|---|---|
| 2.1 | V-B, letter summary | `timing_jitter_ms` is a timing offset | In the submitted campaigns a negative value silenced the VL and a positive value was random. Now a fixed signed offset added to every send interval. | Bug 2, `7f68b29` | Ready |
| 2.2 | V-B, Exp. 3 interpretation | `frame_size` is the frame size | Every frame was 17 bytes larger than requested. Now exact. This reversed several frame-size detections (the LLM aimed exactly at MaxFrame, which the old simulator treated as too large). | Bug 3, `f0e35af` | Ready |
| 2.3 | V-B "Predefined mode" | The generator "looks up the out-of-range values in the test cases catalogue and injects them into the seed frame" | The `test_cases` field of a strategy is **not** sent to the simulator; only the seven mutation parameters are. Rewrite: test cases inform the planner's choice of values, which must be set as parameters. | Prompt finding, `1e3bfc9` | Verify the exact code path, then Ready |
| 2.4 | V-B | Generator "interleaves valid seed frames with the mutated ones" | Not checked. | — | Verify |
| 2.5 | V-B, Appendix C | Reward guides the planner | In the submitted campaigns the impact term was always at its maximum (reference values from the broken simulator). Recalibrated. State it for the recorded campaigns; new campaigns use the fixed reward. | Bug 6, `0d6d02b` | Ready |
| 2.6 | V-B, Appendix (planner prompt) | Planner prompt text | Two versions now exist, `--prompt-version original/revised`. The original described three parameters wrongly (sequence number 0 = "invalid" is "no override"; `wrong_vl` "rejected" is checked by nothing; the token-bucket recipe cannot work) and recommended test-case names that never reach the simulator. Print the version used in the final campaigns in the appendix. | `1e3bfc9`, `580f802` | Decision (see 6.1) |
| 2.7 | V-B (feedback) | Policing-rate feedback | Compared a percent with a fraction; fixed. | Bug 20, `9b6fa39` | Ready |
| 2.8 | V-B / VII-B | Mutation requests | Some requests were silently ignored (`frame_size = 0`, `bag_value` together with timing); fixed. | Bug 16, `2375dfd` | Ready |

## 3. Experiment 1: rule extraction and test cases

| # | Where | What the paper says now | What to change | Source | Status |
|---|---|---|---|---|---|
| 3.1 | Abstract, intro, Table IV, conclusion (lines with "2,703 test cases") | 2,703 test cases, redundancy 0.4% (10/2,703) | The test cases were generated in March from an earlier extraction; most of their names match no current rule. Regenerated from the final rule base on 2026-10-30: **3,989 test cases for 626 rules**. Recompute the redundancy ratio on the new file. | Bug 5, `b2acfbf` | Ready (redundancy: recompute) |
| 3.2 | VI (models) | GPT-4o, temperature 0.7, generates the test cases | Still true. Add the snapshot (`gpt-4o-2024-08-06`) and the run date (2026-10-30). | `b2acfbf` | Ready |
| 3.3 | Method / appendix | Test cases are generated per rule | Add: each test case is filed under the rule it was generated for (previously the LLM named the parameter itself, which broke the link to the rules). | `1ddfb79` | Ready |
| 3.4 | Appendix, "Test Case Extraction System Prompt" | Shows a shorter prompt ("at least 3 test cases", three fields) | The code's prompt asks for 3–7 test cases, a rule summary and valid range per rule, and four fields per case (value, violation type, reason, expected behaviour) (`spec_extraction/test_case_prompts.py`). Print the prompt actually used, and say that each test case is then filed under its rule's name by the code (3.3). | Code reading | Ready |
| 3.5 | Table IV / text | 643 SUT-relevant rules | The fuzzers and the test-case generation use `configs/spec_rules_filtered.json`, which holds **626** rules. Of the 643 rules in `spec_extraction/multimodel_output/spec_rules_filtered.json`: **16 are left out on purpose**: all have low confidence and are either unverified unique rules (14) or unresolved conflicts (2), the rules the letter says are "kept with a low-confidence label"; they stay in the rule base but are not given to the fuzzers. Restoring them would add one category ("Interface Identification", 185 → 186). **1 is lost by a bug**: rule_035 "Boolean Representation in 32-bit Field" and rule_266 "Boolean representation in 32-bit field" get the same key (computed at `export_validated.py:181`, overwritten at line 199), so rule_266 overwrites rule_035. Note: the current `export_validated.py` keeps only high- and medium-confidence rules and would produce 617 rules, so the 626-rule file (which also keeps 9 low-confidence full or partial rules) was not produced by the current exporter; say which filter defines the fuzzers' rules. **Decided 2026-10-30: keep the file as it is (626 rules, collision not repaired).** State in the paper that the fuzzers use 626 rules: the 643 without the 16 low-confidence unverified and conflicting rules, and with one of two near-identical "Boolean representation in 32-bit field" rules. | Checked 2026-10-30 | Ready |
| 3.6 | Exp. 1 / 2 | 185 categories | They are 153 distinct names; 31 groups differ only in case, spaces or punctuation, and the matcher merges each group to one member. State it and report the merged count, or merge them in the rule base. | Bug 26 | Decision |

## 4. Experiment 2: coverage

| # | Where | What the paper says now | What to change | Source | Status |
|---|---|---|---|---|---|
| 4.1 | VII-C, abstract, letter | The LLM-guided fuzzer covers more categories; the order "is not an artifact of the shared denominator" | In the submitted and re-run campaigns the baselines could reach only 90 of 185 categories (their labels come from the old test-case file; 90 with the coverage matcher of `recompute_coverage_venn.py`, 81 with BOOFUZZ's own category lookup; state which matcher a number uses). On those 90, BOOFUZZ-style had more labeled categories than the LLM in every run. With the new test cases the baselines can reach 184; the comparison must be redone on the new campaigns. | Bugs 4, 5 | Needs Stage 7 |
| 4.2 | VII-A, Eq. (4) | Rule Coverage counts categories of labels | One label could count for several categories. Add the one-category-per-label count. | Bug 17, `1116a2d` | Ready (definition); Needs Stage 7 (numbers) |
| 4.3 | VII-A | Executed Rule Coverage counts labels of iterations with any mutation | Any mutation counted, even one unrelated to the rule. Add mechanism-matched coverage (only 54 of 153 categories are testable by any simulator parameter), and say so. | Bug 18, `52d5a49` | Ready (definition); Needs Stage 7 (numbers) |
| 4.4 | VII-C | Coverage tables and Venn figures | All numbers to be replaced by the Stage 7 campaigns. | — | Needs Stage 7 |
| 4.5 | VIII (limitations) | — | State that 99 of 153 categories (IP/UDP fields, ports, configuration …) cannot be exercised by any simulator parameter, so coverage of them is by label only, for every fuzzer. | Stage 3 | Ready |
| 4.6 | VII-B (baselines) | The baselines "apply each test value to a seed frame" | The baselines map each test case to a parameter by keywords in the rule name and use fixed defaults when the value is not numeric (e.g. 63 or 1519 bytes, sequence 0). Describe this. | `boofuzz_strategy_generator.py:243-301` | Ready |

## 5. Experiment 3: injected bugs

Details and numbers: `context/BUG_SUITE.md`.

| # | Where | What the paper says now | What to change | Source | Status |
|---|---|---|---|---|---|
| 5.1 | VII-B setup, Table III | Eight bugs, `accept_oversized` "accepts frames larger than the 1518-byte AFDX limit" and is identical to `skip_frame_validation` | Ten bugs. `accept_oversized` now skips only the upper bounds. New: `max_frame_off_by_one`, `loose_bag_tolerance`. Add their rows to Table III (clauses to confirm: §4.2.1 and §4.2.2). | `2205a1f`, `5b23991`, `1c8a1e6` | Ready (clauses: Verify) |
| 5.2 | VII-B | "it does not include faults such as off-by-one window checks, incorrect sequence-number wraparound, or wrong BAG units" (also lines ~2551, ~2633) | The suite now includes one off-by-one fault and one threshold fault; update the sentence and the limitation. | BUG_SUITE §4 | Ready |
| 5.3 | VII-B / Table VII | BDR out of 8 | Report found of 10 and found of 8 reachable, and say why `skip_token_bucket` and `skip_vl_check` are unreachable through the mutation interface (arithmetic of the bucket; no VL-id parameter). | Bugs 7, 8, `4b7f210` | Ready (text); Needs Stage 7 (numbers) |
| 5.4 | VII-B, letter (R2 C1) | The two missed bugs "cannot be reached through the mutation interface" | The token bucket cannot fail at all after the BAG check (not an interface limit). Correct the wording. | Bug 7 | Ready |
| 5.5 | VII-C, letter | "Two of the six bugs are exposed without any mutation … 3,492 policing drops and 264 rejections" | This came from the second sender (Bug 1), not from normal traffic. On the corrected simulator a run without mutation has 0 drops and 0 rejections, and no bug is detected without mutation (acceptance check (a) in BUG_SUITE §5). Replace the paragraph. | Bugs 1, 10 | Ready |
| 5.6 | VII-B | `skip_sequence_check` detected by out-of-window sequence numbers | A constant sequence number is discarded earlier as a duplicate; the check is reached by sequence number 0 or by long drop bursts. Describe this. | Bug 11, BUG_SUITE §3 | Ready |
| 5.7 | Table VII, VIII | Detection results | Replace with Stage 7 numbers. Note: on the recorded inputs, `max_frame_off_by_one` is found only by the LLM-guided runs and `skip_sequence_check` by every baseline run but 2 of 5 LLM-guided runs. | BUG_SUITE §6 | Needs Stage 7 |
| 5.8 | VII-B | Bug selection | State that the 10-bug list was fixed before the new campaigns ran and before any campaign was scored against it (`b2e6ef8`), and that each bug passed two acceptance checks. For the recorded campaigns, do not call it blind: their inputs were already logged (BUG_SUITE §2 caveat). | BUG_SUITE §2, §5 | Ready |

## 6. Planner instructions and fairness

| # | Where | What to change | Source | Status |
|---|---|---|---|---|
| 6.1 | V-B, appendix, VIII-A | Both the original and the revised planner instructions contain hints about how this simulator is built (original: "`spoof_src` => finds bugs in switch MAC validation", "negative jitter => finds bugs in BAG policing"; revised: "`wrong_vl` … nothing checks", "no input can exercise" the token bucket, "dropped at the switch", "the receiving ES rejects", "MaxFrame and MinFrame themselves are valid"). The baselines get no such hints. Either write a neutral version (parameter interface and protocol facts only) and use it in Stage 7, or disclose the hints and their possible effect. | FIX_PLAN "Open" item | Decision (postponed 2026-10-29) |
| 6.1a | V-B, VIII-A | The controller's steering injects a fixed schedule of tests aimed at the injected bugs (iterations 21–46: spoofed source MAC, corrupted MAC prefix, 2000-byte frame, −5 ms timing, sequence 255, token-bucket stress; `strategy_planner.py:402-440`). The baselines have no such schedule. Disclose it, or remove it before Stage 7; it also affects the ablation (A1 has it, A2 and A0 do not). | Code reading 2026-10-30 | Decision |
| 6.1b | V-B | The revised text also has errors (FIX_PLAN, "Errors in the revised text"): it still shows a test-case-only example, misdescribes 2 of 5 MAC mutation values, and contradicts itself on the token bucket. Fix them in whichever version Stage 7 uses, and do not describe the pilot's revised text as fully correct. `--prompt-version original` reproduces only the submitted planner text; the reward, translation and feedback are the fixed ones, so the pilot is not a re-run of the submitted campaigns. | Review 2026-10-30 | Ready |
| 6.2 | VIII-A or appendix | Report the pilot of original vs. revised instructions (2 × 100 iterations each, fixed simulator, $31): with the original text 22–23 iterations per run sent no mutation at all and 29–35 of 100 changed any simulator counter; with the revised text 0 and 84–87. Two runs per version: an indication, not a significance claim. | `d3b7e46` | Ready (if reported) |
| 6.3 | VIII-A | The controller and the baselines were developed against the same simulator; the letter already says so. Keep. | Letter | Ready |

## 7. Abstract, introduction, results and conclusion

| # | What to change | Status |
|---|---|---|
| 7.1 | Every coverage and detection number (abstract, intro contributions, results, conclusion) comes from the Stage 7 campaigns. | Needs Stage 7 |
| 7.2 | Choose the framing after Stage 7. On the recorded inputs replayed on the corrected simulator, the LLM-guided fuzzer did not outperform the baselines in bug detection (6, 5, 5, 5, 6 of 8 vs. 6 for every baseline run). Do not keep a claim the new numbers do not support. | Needs Stage 7 |
| 7.3 | Ablation conclusion ("coverage comes mainly from steering, not feedback"): the steering's re-plan step is itself an LLM call, so this does not separate the controller from the LLM. Add the "controller + random planner" control or soften the claim. | Decision |

## 8. Reproducibility (Section VI, letter R1 C4b)

| # | What to change | Source | Status |
|---|---|---|---|
| 8.1 | The ns-3 path was hard-coded; now set with `AFDX_NS3_PATH`. | Bug 24, `302ebd5` | Ready |
| 8.2 | A Windows checkout could break the simulator's CSV parsing (CRLF); fixed. | Bug 25, `63203b1` | Ready |
| 8.3 | Report the code commit and the simulator build used for the final campaigns. | Stage 7 | Needs Stage 7 |
| 8.4 | Interrupted LLM campaigns: besides resuming from history, 40 failed records were removed and run r3 was discarded and re-run. Say so, or avoid it in Stage 7. | Bug 22 | Ready |

## 9. Response letter

Corrections to the letter of 2026-10-24, in addition to the items above that it repeats:

| # | Letter passage | Correction | Source |
|---|---|---|---|
| 9.1 | Summary of main changes | Add the simulator corrections (Bugs 1, 2, 3, 12–14) as a fourth problem found during the revision, with their effect on the results. | Bugs 1–3 |
| 9.2 | Summary, "Bug detection. All fuzzers detect the same 6 of 8 bugs" | Replace with the Stage 7 numbers on the 10-bug suite. | Stage 7 |
| 9.3 | R1 C2 "the order is not an artifact of the shared denominator" | Not supported: the baselines' labels reached 90 categories. Rewrite with the new test cases and the Stage 7 numbers. | Bugs 4, 5 |
| 9.4 | Additional corrections, "Baseline campaigns … re-run … on the final rule base" | Their labels came from test cases built on an older rule base; now regenerated. | Bug 5 |
| 9.5 | Additional corrections, "Simulator crash … With the corrected runner, these iterations count as not executed" | The recorded histories were made before that fix worked; state how they were handled. | Bug 22 |
| 9.6 | R1 C4a, reward | The impact term was constant in the submitted campaigns. | Bug 6 |
| 9.7 | R2 C1, Question 1 (bug selection) | Describe the new suite, the pre-registration and the acceptance checks; correct "cannot be reached through the mutation interface" for the token bucket. | BUG_SUITE |
| 9.8 | R2 C6, ablation | See 7.3. | — |
| 9.9 | Additional corrections, "Injected bugs … we now report detection over the 7 distinct faults" | Superseded: `accept_oversized` is now a distinct fault; report of 10 and of 8 reachable. | `2205a1f` |

## 10. Open decisions that change the text

1. Neutral planner instructions for Stage 7 (6.1).
2. Number of ablation runs, and whether to add the "controller + random planner" control (7.3).
3. A/B copies 100 µs apart: correct the text or the code (1.4).
4. 185 vs. 153 categories (3.6).
5. Confirm with the student whether the second sender was intended (1.1).
