# Independent Review of `REVISION_FINDINGS.md`

**Reviewer:** Auto (Composer), independent of the Claude writeup  
**Source reviewed:** `context/REVISION_FINDINGS.md`  
**Date:** 2026-10-27  
**Method:** Re-read the cited C++/Python paths, recompute counts from `evaluation/results/revision/runs/*.jsonl` and `campaign_metrics.json`, and (for Bugs 1–2) confirm against the already-run clean simulator output and the installed ns-3.45 `GetInteger` signature. Claude’s “fix test” that removes `AddTransmitVL` was **not** re-run; those tables are treated as reported, not re-measured.

## Verdict legend

| Verdict | Meaning |
|---|---|
| **Confirmed** | Mechanism and evidence hold under independent check |
| **Confirmed, nuance** | Real, but numbers, wording, or scope need a caveat |
| **Partly confirmed** | Core idea right; some detail wrong or overstated |
| **Not confirmed** | Could not verify, or claim is wrong |
| **Already known** | True, but already in the response letter / earlier diagnosis |

## How this affects the paper (short)

The three claims that most need attention before resubmission:

1. **Experiment 3 (“6/8 bugs”)** is mostly a property of the bug suite and of background double-traffic, not of the fuzzers (Bugs 1, 7–10).
2. **Experiment 2 (Rule Coverage lead)** is partly an artifact of unequal label pools (Bugs 4–5, amplified by 17–18).
3. **Simulator behaviour described in Sections IV-B and V-B** (clean traffic, jitter, frame size, A/B timing, who transmits) does not match the code (Bugs 1–3, 12, and Section 25).

Bugs that hit all fuzzers equally (1–3, 7–8, 11–15) hurt absolute claims more than ranking. Bugs that hit baselines harder or the LLM’s feedback loop (4–6, 16–18, 20) affect comparative claims.

---

## Bug-by-bug

### Bug 1. Two senders on every VL; fuzzer frames dropped

**Verdict: Confirmed**

Both `AfdxEndSystem` (via `AggregateObject` + `AddTransmitVL`) and `AfdxTrafficGenerator` (`AddApplication`) transmit every VL on networks A and B. ns-3’s `Object::Initialize` starts aggregated `Application` subclasses, so the end system transmits even without `AddApplication`. Clean-run counters match: ~3,492 policing drops / 7,118 received (~49%), `esFramesSent = 1869`. For VL 1002 the sizes (530 vs 323), starts (~12 ms vs ~102 ms), and separate sequence counters match the writeup. This is not A/B redundancy.

**Paper / results impact:** High. Conforming traffic is not “emitted once per BAG,” and the strict check does drop it — contradicts IV-B(b). After ~100 ms the switch keeps the hidden end-system stream and drops the generator (fuzzer) stream, so token-bucket, forwarding, and most receiver checks rarely see mutated traffic. Explains free detections of `skip_bag_policing` / `skip_sequence_check` (Bug 10). Affects all fuzzers equally, so ranking is less distorted than absolute “we exercised the AFDX stack” claims.

**Caveat:** Fix-test tables (before/after removing `AddTransmitVL`) were not re-run here. The mechanism is solid; exact post-fix detection counts should be treated as Claude’s measurement until reproduced.

---

### Bug 2. “Send faster” silences the VL; “slower” is random ±j

**Verdict: Confirmed**

`simulator_runner.py` maps `bag_value < BAG` to negative `timing_jitter_ms`. The generator calls `GetInteger(0, 2 * jitter_ms)` (`afdx-traffic-generator.cc` ~518 and ~641). In ns-3.45 that API takes `uint32_t`; a negative upper bound wraps, so the next gap is either ~100 µs or days ahead → ~2 frames then silence. Positive jitter is uniform in `[BAG−j, BAG+j]`, not a fixed slower offset. Replay-cache identity across negative values is consistent with this.

**Paper / results impact:** High. Every BAG-violation / “send faster” test in all three fuzzers tested silence, not overspeed. Prompt, paper V-B, and letter wording are wrong. `DIAGNOSIS.md` (“Jitter WORKS”) misread count changes caused by silence. Undermines any claim that timing mutations exercised BAG policing meaningfully.

---

### Bug 3. Every frame is 17 bytes larger than requested

**Verdict: Confirmed**

Runner and `afdx-demo.cc` compute a **frame** mid-point + delta, then pass that integer to `AddVirtualLink` as **payload**. Headers (+17) are added on top; the switch compares payload to `max_frame − 17`. Independently recomputed from logs:

| Run | Legal `frame_size` with frame-error drops | Undersize with 0 frame-error drops |
|---|---|---|
| LLM r1–r5 | 70, 74, 62, 56, 69 | 0–3 |
| BOOFUZZ | 0 | 51 |
| random s1 | 0 | 36 |

Matches Claude’s order of magnitude (LLM legal-but-dropped; BOOFUZZ undersize never triggers). Example: LLM r1 iter 9, `frame_size=1024` on VL 3001 (max 1024) → 114 frame-error drops.

**Paper / results impact:** High for frame-boundary claims and for many LLM frame-validation “detections.” Baselines’ 63-byte undersize tests are ineffective. Reviewer requests for boundary-value testing are not met as written.

---

### Bug 4. Baselines can reach only 90 of 185 categories

**Verdict: Confirmed**

Random picks labels from `test_cases.json` keys only. BOOFUZZ schedules from the same catalogue. LLM sees the full rule list and free-form labels. Recomputed: 423 test-case names → 206 match ≥1 category → **90** shared categories. Categories outside that pool: LLM r1–r5 = 27, 27, 36, 31, 29; A1 = 41; random/BOOFUZZ/A0/A2 = 0.

Shared-90 rescoring (existing logs only):

| Fuzzer | Label cats / 90 | Executed / 90 |
|---|---|---|
| BOOFUZZ | **86** | **61** |
| LLM full (r1–r5) | 60–71 (mean ~65.4) | 54–60 (mean ~58.2) |
| Random (s1–s5) | 42–54 | 37–45 |
| A1 / A2 / A0 | 54 / 49 / 6 | 54 / 43 / 6 |

**Paper / results impact:** High for Experiment 2 comparative claims. The LLM’s coverage lead and Unique Findings partly come from categories baselines cannot name. On the shared 90, BOOFUZZ leads. Mann–Whitney on full 185 partly tests this imbalance. Fairness caveat belongs in the paper/letter even if absolute LLM exploration is still interesting.

---

### Bug 5. Test-case list from an older rule base

**Verdict: Confirmed, nuance**

217 test-case names match no current category. Many (e.g. `domain_id_coding`, `fifo_discipline_for_queuing`, `signed_32_integer`) are absent from both filtered and unfiltered rule files. Exact “181 in neither / 36 only unfiltered” depends on matching strictness; with a slightly looser check the split was ~130 / ~87 — same qualitative conclusion. Root cause of Bug 4. Letter claim that baselines were re-run “on the final rule base” is misleading: their **labels** still come from the stale catalogue.

**Nuance:** `configs/` **is** tracked in git today (`spec_rules*.json`, `test_cases.json`, etc.). Claude’s Section 24 / 25 claim that `configs/` is untracked is **wrong for the current tree**. History of when names diverged may still be hard to reconstruct, but the files are in the repo.

**Paper / results impact:** High (cause of 4). Fix = regenerate or remap test cases; needs LLM calls if regenerating.

---

### Bug 6. Impact term of the reward always maxed

**Verdict: Confirmed**

`reward_calculator.py` baselines (`3559` / `1757` / `1802`) are roughly one switch; `log_parser.py` sums both (~7118 / 3626 / 3492). Recomputed `_compute_impact_score` on all 2,800 revised iterations → **1.0 in 2,800/2,800**.

**Paper / results impact:** High for any claim that the impact reward guided the planner. Ablation “feedback adds little” is consistent with a dead impact term. Other reward terms (novelty, new violations, etc.) can still vary; do not say the whole reward is constant.

---

### Bug 7. Token-bucket mutant never detectable

**Verdict: Confirmed**

Refill ≈ `(maxPayload+20)` per BAG; frame cost ≤ `maxPayload+17` after size check; BAG gate forces ≥1 BAG between accepted frames → bucket cannot go negative under conforming spacing. Planner’s `frame_size=1500` “token bucket stress” is rejected at frame validation (and worsened by Bug 3). `skip_token_bucket`: 0 detections in all campaigns.

**Paper / results impact:** High for Experiment 3 denominator. Letter’s “unreachable via mutation interface” is incomplete; arithmetic alone makes the mutant equivalent. Counting it in “x/8” inflates the suite.

---

### Bug 8. VL-check mutant never detectable

**Verdict: Confirmed**

No mutation changes the VL id field; both senders write the configured id. `IsVLAuthorized` always passes for emitted traffic. `skip_vl_check`: 0 detections. Already noted in `DIAGNOSIS.md`.

**Paper / results impact:** Same as Bug 7 — dead mutant in the 8-bug suite.

---

### Bug 9. Two bug IDs disable the same check

**Verdict: Confirmed (Already known)**

`afdx-switch.cc:302` gates both `skip_frame_validation` and `accept_oversized` on the same block. Detection counts are identical in `campaign_metrics.json` (e.g. LLM r1: 82/82). Letter already discloses this.

**Paper / results impact:** Medium. Double-counts one behaviour in “6/8.”

---

### Bug 10. Two bugs “detected” with no mutation

**Verdict: Confirmed (partly Already known)**

`skip_bag_policing` and `skip_sequence_check`: 200/200 (or 198) with first detection at iteration 0 across campaigns. Mechanism is Bug 1 (two senders). Letter discloses no-mutation detection but treats the 49% clean drop as normal rather than a scenario bug.

**Paper / results impact:** High. Together with 7–9, only about **three distinct reachable behaviours** remain (frame validation, source MAC, constant-field). “6/8 for every fuzzer” overstates fuzzer skill.

---

### Bug 11. Constant sequence discarded as duplicate, not seq-checked

**Verdict: Confirmed, nuance**

Receive path runs First-Valid-Frame-Wins before `CheckSequenceNumber`. Same seq on same network → duplicate discard; seq check never sees a stuck override. Seq 0 invalid explains some clean-run rejections from the hidden sender wrapping through 0. Fix-test claim of 0 rejections under forced seq 255 was not re-run; code path supports it.

**Nuance:** Exact accounting of the clean-run **264** rejections remains open (agree with Claude’s Section 27).

**Paper / results impact:** Medium–High for sequence-mutation claims. Sequence override does not exercise the sequence-integrity check as described.

---

### Bug 12. BAG tolerance rounds to 0

**Verdict: Confirmed**

`MilliSeconds(bag.GetMilliSeconds() * 0.01)` truncates 0.04–0.32 to 0.

**Paper / results impact:** Low alone. Contradicts “1% tolerance” in IV-B(b). With Bug 1 fixed, clean traffic would still be fine if senders stay on BAG; matters for micro-jitter edge cases.

---

### Bug 13. Token-bucket drops counted as BAG drops

**Verdict: Confirmed**

Same `m_framesDroppedPolicing` / `LogDrop(..., "BAG_Violation")` path. `afdxTokenBucketViolations` is not a cumulative total.

**Paper / results impact:** Low for ranking; medium for interpreting policing counters / feedback.

---

### Bug 14. Receiver payload check uses transmit VL table

**Verdict: Confirmed**

`ValidateFrame` looks up `m_transmitVLs`. Receivers of a VL typically do not transmit it, so the per-VL range check falls through to the global 1..1471 band.

**Paper / results impact:** Low–Medium. Weakens claims about receiver-side size validation; with Bug 1, receivers mostly see hidden traffic anyway.

---

### Bug 15. No destination-MAC check; CSV encoding mismatch

**Verdict: Confirmed**

No switch/ES drop on wrong dest MAC; only a serialize warning. CSV uses decimal-looking last bytes (`03:00:00:00:10:01` for VL 1001) while the warning compares hex VL field (`0x03E9` → `03:e9`), so the warning fires on normal frames too. `wrong_vl` mutation is effectively invisible to detection.

**Paper / results impact:** Medium. One of the seven knobs does not produce observable counter changes for Experiment 3.

---

### Bug 16. Some mutations silently ignored

**Verdict: Confirmed**

| Issue | Code | Independent count |
|---|---|---|
| `frame_size=0` falsy | `if frame_size:` ~192 | random s1/s2: 19/13; BOOFUZZ: 3; LLM r1: 0 |
| `bag_value` ignored if jitter set | `if ... and timing_jitter == 0` ~200 | LLM r1: 10; r4: 20 iterations with both set |
| Random’s `sequence_number` vs `sequence_number_override` | ~218 | mechanism confirmed; per-run “5 in s2” not fully re-tallied |

**Paper / results impact:** Medium. Logged intent ≠ executed input; uneven across fuzzers (hurts random/BOOFUZZ more for size 0).

---

### Bug 17. Prefix matching inflates categories per label

**Verdict: Confirmed**

`recompute_coverage_venn.py` / steering matcher: `norm.startswith(nc+"_") or nc.startswith(norm+"_")`. Examples verified: `switch`→16, `virtual_link`→10, etc. Inflates all fuzzers; LLM free-form short names may gain slightly more.

**Paper / results impact:** Medium. Absolute coverage % is soft; comparative effect is secondary to Bugs 4–5.

---

### Bug 18. Executed coverage credits unrelated mutations

**Verdict: Confirmed, nuance**

`mechanisms()` is any non-default of the seven fields; in-range `payload_delta_bytes` counts. Steering still marks coverage from labels. Rough sensitivity (drop iterations whose only mutation is in-range size), recomputed:

| Run | Executed % of 185 | Without in-range-size-only |
|---|---|---|
| LLM full mean | ~47.6% | **~34.7%** |
| BOOFUZZ | 33.0% | 31.9% |
| Random s1 | 21.6% | 21.1% |

Claude’s ≈34.7% for LLM is consistent with this rough check. It is a sensitivity probe, not a proposed official metric — agree with that framing.

**Paper / results impact:** Medium–High for the letter’s strongest executed-coverage claims. Letter already says the measure does not require the traffic to violate the named rule; that caveat should be louder if executed coverage remains the headline.

---

### Bug 19. Metrics mix both senders, all VLs, both switches

**Verdict: Confirmed**

`log_parser.py` sums global counters. With Bug 1, policing is mostly generator frames; forwarded/RX mostly hidden sender; one mutated VL is diluted by seven others.

**Paper / results impact:** Medium. Weakens reward sharpness and BDR sensitivity; not a separate root cause from Bug 1.

---

### Bug 20. Feedback labels / `bugs_found` useless

**Verdict: Confirmed**

`policing_rate` is stored as **0–100** (`log_parser.py`), but thresholds are `>= 0.8` etc. → almost always “Excellent”. `bugs_found = malformed_accepted > 0`; that counter is never produced. Recomputed: `bugs_found` true in **0 / 2800** iterations.

**Paper / results impact:** Medium for ablation/feedback narrative. Aligns with “feedback adds little.”

---

### Bug 21. Misleading metric names

**Verdict: Partly confirmed**

- **`valid_ratio`:** Confirmed — essentially non-crash with `frames_received > 0` under background traffic.
- **`distinct_settings` includes `vlId`:** Confirmed in `SETTING_KEYS`; “adds up to 7” is plausible but not re-measured as an exact inflation figure (*Reported* numbers).
- **`payloadClampCount` / `payloadAppliedBytes` in extreme mode:** Code path can zero clamp count while still changing size; marked *Reported* — mechanism plausible, not fully stress-tested here.

**Paper / results impact:** Low.

---

### Bug 22. Crash fix not active when campaigns recorded

**Verdict: Confirmed (Already known)**

BOOFUZZ 190–191 overflow `stoi` / extreme jitter; histories show success; `analyze_campaigns.py` excludes via replay crash list. Letter wording should say analysis excludes them, not that the recording runner already did. Superseded files (`credit_exhausted_records_removed.jsonl`, `llm_full_r3_crashed.jsonl`) exist and should stay disclosed.

**Windows path slash risk:** plausible from code; not reproduced on this machine’s analysis run.

**Paper / results impact:** Low for reported numbers (analysis corrects); medium for reproducibility wording.

---

### Bug 23. BOOFUZZ resume restarts schedule

**Verdict: Confirmed mechanism; impact as stated**

`main.py` resumes at `len(history)` but `current_index` starts at 0. Revised BOOFUZZ run reportedly not resumed — then results unaffected. Useful for explaining older stitched histories.

**Paper / results impact:** Low for the revised tables.

---

### Bug 24. Other code-health issues

| Sub-claim | Verdict |
|---|---|
| `frames` list never reaches ns-3 | **Confirmed** — only 7-field `sim_config` is used |
| `MutationConfig` defined four times via `extern` | **Confirmed** — fragile |
| Generator receive / `SubscribeToVirtualLink` unused | **Confirmed** — dead receive path |
| Every generator frame bit-flipped | **Confirmed, nuance** — `StartMutationPolling` + `m_fuzzProbability=1.0` enables payload bit flips after poll sees `mutations.json`; does not change size/timing; payload-level noise |
| `configs/` untracked | **Wrong** — five config files are tracked in git |
| Hard-coded ns-3 path | **Confirmed** |
| WSL tree symlinked to this repo | **Confirmed** (from setup) |
| `virtual_links.csv` LF-only dirty | **Confirmed** (line endings) |

**Paper / results impact:** Low–Medium for artifact reproducibility (path, symlink hygiene). Do **not** tell reviewers that `configs/` is missing from the repo.

---

## Section 25 (paper/letter mismatches)

| Claim | Review |
|---|---|
| IV-B(b) clean traffic / no conforming drops | **Confirmed mismatch** (Bug 1) |
| IV-B(b) 1% tolerance | **Confirmed mismatch** (Bug 12) |
| IV-B(c) A/B “exactly the same time” | **Confirmed mismatch** (B delayed 100 µs in generator) |
| Only ES1 transmits | **Confirmed mismatch** — all three ES transmit their VLs |
| Jitter = timing offset | **Confirmed mismatch** (Bug 2) |
| `frame_size` = on-wire frame size | **Confirmed mismatch** (Bug 3) |
| Two missed bugs “unreachable via interface” | **Partly incomplete** — token bucket also arithmetically dead (Bug 7) |
| Coverage lead not an artifact | **Challenged** by Bugs 4–5; shared-90 flips the lead to BOOFUZZ |
| Baselines on “final rule base” | **Misleading** (Bug 5) |
| Reward guides planner | **Overstated** for impact term (Bug 6) |
| Corrected runner recorded campaigns | **Wording issue** (Bug 22) |
| Public repo reproduces | **Partly** — configs **are** present; hard-coded path still blocks out-of-box runs |
| Interrupted LLM resumes / discarded records | **Disclose** superseded files (Bug 22) |
| Coverage from steering not LLM | **Fair open point** — replan is still an LLM call; needs a control |

---

## Summary table

| # | Claude severity | Independent verdict | Affects paper claims? |
|---|---|---|---|
| 1 | High | Confirmed | Yes — IV-B, Exp 3, absolute “stack exercised” |
| 2 | High | Confirmed | Yes — timing / BAG tests |
| 3 | High | Confirmed | Yes — frame boundaries, many detections |
| 4 | High | Confirmed | Yes — Exp 2 ranking |
| 5 | High | Confirmed (configs *are* tracked) | Yes — root of 4 |
| 6 | High | Confirmed | Yes — reward / ablation story |
| 7 | High | Confirmed | Yes — Exp 3 denominator |
| 8 | High | Confirmed | Yes — Exp 3 denominator |
| 9 | Medium | Confirmed (known) | Yes — double count |
| 10 | High | Confirmed (partly known) | Yes — free 2/8 |
| 11 | Medium | Confirmed + open 264 | Yes — seq mutation story |
| 12 | Low | Confirmed | Minor IV-B wording |
| 13 | Low | Confirmed | Counter interpretation |
| 14 | Low | Confirmed | Receiver validation claims |
| 15 | Medium | Confirmed | One knob ineffective |
| 16 | Medium | Confirmed | Logged vs executed |
| 17 | Medium | Confirmed | Softens coverage % |
| 18 | Medium | Confirmed (≈34.7% sensitivity OK) | Executed-coverage headline |
| 19 | Medium | Confirmed | Metrics quality |
| 20 | Medium | Confirmed | Feedback / ablation |
| 21 | Low | Partly confirmed | Naming only |
| 22 | Low | Confirmed | Wording / disclosure |
| 23 | Low | Mechanism confirmed | Low if run not resumed |
| 24 | Low | Mostly confirmed; **configs tracked** | Repro path; fix the untracked claim |

---

## Recommended priority for the revision (opinion)

1. **Must address in text even before code fixes:** Bugs 1, 4–5, 7–10, and Section 25 mismatches. Otherwise Exp 2/3 and IV-B overclaim.
2. **Must fix in code before trusting new numbers:** Bugs 1, 2, 3 (simulator truthfulness).
3. **Suite redesign:** Drop or replace Bugs 7–9 equivalents; stop counting free detections (10).
4. **Evaluation fairness:** Report shared-90 coverage (and/or regenerate test cases); qualify executed coverage (18).
5. **Reward / feedback:** Fix baselines (6) and policing_rate units (20), or state they were constant/broken during the reported campaigns.
6. **Do not** claim `configs/` is missing from git; it is present. Do fix the hard-coded ns-3 path for reproducibility.

Nothing in this review changed repository code or results files.
