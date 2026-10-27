# Revision Review: Additional Findings in the Harness and Simulator

**Date:** 2026-10-26/27
**Scope:** Review of the evaluation harness, simulator and response letter for the TAES
major revision (TAES-2026-2779), after the three harness fixes in commit `0253d49`.
**Method:** Code reading, analysis of the logged campaign histories and replay cache in
`evaluation/results/revision/`, and direct ns-3 runs in WSL (Ubuntu-24.04, ns-3.45).
No LLM API was called.

This document records what was found, the evidence, and what it means for the paper.
**Nothing in the code or results has been changed.** Section 8 describes how to
reproduce the measurements.

---

## 1. Summary

| # | Finding | Severity | Affects |
|---|---|---|---|
| A | "Send faster" (negative `timing_jitter_ms`, and every `bag_value` below the BAG) makes the stream send 2 frames and then go silent | High | Exp. 2 and 3, all fuzzers |
| B | Every VL is transmitted by **two** senders; the switch forwards the hidden, unmutated sender and drops the fuzzer's frames at BAG policing | High | Exp. 2 and 3, all fuzzers |
| C | Bug detection: 2 of the "6/8" bugs are detected with no mutation; 2 more are the same check | High | Exp. 3, response letter |
| D | Executed Rule Coverage still credits a rule when an unrelated parameter changed | Medium | Exp. 2 headline numbers |
| E | Every metric sums both senders, all 8 VLs and both switches | Medium | Reward, feedback, Exp. 3 |
| F | Statements in the paper and response letter that do not match the code | Medium | Manuscript, letter |
| G | Smaller issues | Low | Maintenance, reproducibility |

The three harness fixes described in the response letter (label-based coverage,
incomplete baseline logs, ignored ns-3 exit code) are present in the current code
(Section 2). Findings A and B are bugs in the **system under test**. They affect all three
fuzzers equally, so they do not by themselves favor one fuzzer. But they mean that much of
what the experiments claim to exercise was never exercised.

---

## 2. The three harness fixes (verified)

1. **Rule Coverage counted labels, not tested rules.** Fixed. Redirection now re-plans by
   default (`redirect_mode="replan"`, `llm_fuzzer/core/strategy_planner.py:607`), and all
   revised LLM runs log it. Executed Rule Coverage counts a label only if its `sim_config`
   changes at least one of the 7 simulator parameters
   (`evaluation/revision/analyze_campaigns.py:78`). See Finding D for what it still counts.
2. **Baseline histories did not log all parameters.** Fixed. Both baselines log
   `sim_config`, and `bdr_replay.py` replays exactly that config.
3. **ns-3 exit code ignored.** Fixed in code (`llm_fuzzer/utils/simulator_runner.py:129` and
   `:275`). However, the revised histories were recorded **without** this fix being
   effective. BOOFUZZ iterations 190 and 191 crash the simulator in the replay (their
   inputs overflow the C++ JSON parser), but the recorded history marks them as successful
   with made-up counters. `analyze_campaigns.py` corrects for this using the replay, so the
   numbers are right. The letter's wording ("with the corrected runner, these iterations
   count as not executed") should be adjusted.

Data handling to disclose: `runs/superseded/credit_exhausted_records_removed.jsonl` holds
40 failed records (5 from each of 8 LLM runs) removed after the API credit ran out, before
the runs were resumed. `runs/superseded/llm_full_r3_crashed.jsonl` is a full run discarded
after a fuzzer crash (`cannot convert float NaN to integer`) and re-run.

---

## 3. Finding A: "send faster" silences the stream

### What happens
`SimulatorRunner._translate_to_cpp_format` expresses `bag_value < BAG` as a negative
`timing_jitter_ms`. The traffic generator applies it with

```cpp
// examples/AFDX_V3/model/afdx-traffic-generator.cc:641 (same at :518)
int applied_jitter = static_cast<int>(jitterRng->GetInteger(0, 2 * jitter_ms)) - jitter_ms;
```

In ns-3.45, `UniformRandomVariable::GetInteger(uint32_t min, uint32_t max)` takes
**unsigned** arguments. A negative `2 * jitter_ms` wraps to about 4.29 billion. The next
send time is then either clamped to 100 µs or pushed hours into the future. The stream
sends a short burst and then nothing for the rest of the run.

A positive value is not a fixed "slower" offset either: each gap is drawn uniformly from
`[BAG - j, BAG + j]`, so some gaps are shorter than the BAG.

### Evidence (direct runs, VL 1002, BAG 4 ms)

| `timing_jitter_ms` | Fuzzer-controlled frames sent on network A | `AfdxMutation.jitterAppliedMs` |
|---|---|---|
| 0 | 450, one every 4.0 ms | 0 |
| -1 | **2** (at 102.0 and 102.1 ms), then silence | 132,521,920 |
| -3 | **2** (identical to -1) | 132,521,922 |
| +2 | 453, gaps 2 to 6 ms (random) | -1 |

The replay cache (`bdr_replay_cache_v2.json`) shows the same: on a given VL, every
negative jitter value produces byte-identical counters (e.g. VL 1001, jitter -1 to -5:
all 2,708 policing drops).

### Impact
- No campaign ever tested "frames sent faster than the BAG".
- The planner prompt describes `timing_jitter_ms` as "negative = faster, positive =
  slower", and the paper and letter call it "a timing offset". Neither is what the code does.
- `context/DIAGNOSIS.md` (Feb 2026) reports "Jitter WORKS — frame counts change" for
  -7 ms. The counts changed because the VL went silent.

### Possible fix
Apply a deterministic signed offset to the send interval (`nextSend = BAG + offset`,
floored at a small positive value). Use a separate parameter if random jitter is also
wanted.

---

## 4. Finding B: two senders on every virtual link

### What happens
`examples/AFDX_V3/simulations/afdx-demo.cc` creates **two** independent senders for every VL:

1. **`AfdxEndSystem`** (lines 676-692). It is attached with `AggregateObject` and then given
   every VL as a *transmit* VL (`AddTransmitVL`, lines 723/725/727). The comment above the
   loop (line 696) says "Configure Virtual Links on End Systems **(for receiving)**". It is
   never registered with `AddApplication`, but ns-3 initializes every object aggregated to
   a node at time 0 (`Object::Initialize` → `Application::DoInitialize`), so it starts
   anyway. It sends from 10 ms + (VL id mod 50) ms, every BAG, on both networks.
   **The fuzzer does not control this sender.**
2. **`AfdxTrafficGenerator`** (lines 748-858). It is added with `AddApplication`, starts at
   0.1 s, and applies the fuzzer's `mutations.json`. **This is the fuzzer's sender.**

Both send every VL at the correct rate, but about 2 ms apart (VL 1002). Each switch keeps
the last accepted frame time per VL and drops a frame that arrives less than one BAG
later. The end-system stream started first, so it owns the slot, and the generator's frame
always arrives second.

This is **not** A/B redundancy. Redundancy (one sender, same frame and sequence number on
network A and network B) is implemented separately and works. Here, two different
programs send different frames (different sizes and sequence counters) on the **same**
network.

### Evidence (direct runs, clean input)

Transmissions on network A, VL 1002, after 0.1 s:

| Sender | Frame size | Sequence numbers | Frames sent | Frames reaching receivers (ES2, ES3) |
|---|---|---|---|---|
| End system (hidden) | 530 B | continues from 21, 22, ... | 475 | **475** |
| Traffic generator (fuzzer) | 323 B | restarts at 1 | 450 | **0** |

VLs 2001 and 3001 show the same pattern. Switch statistics: on every VL, the switch
forwards exactly the BAG rate and polices a near-equal number of frames. In total that is
3,492 policing drops out of 7,118 frames (49%) on traffic with no mutation at all.

The switch checks a frame in this order (`afdx-switch.cc`, `ProcessFrame`): (1) frame
validation, (2) VL check, (2b) source-MAC check, (3) BAG policing, (4) token bucket,
(5) forwarding. So the fuzzer's frames are seen by checks 1-2b and then dropped at 3. The
token bucket, forwarding, and every receiving end-system check (sequence number, constant
fields, redundancy, duplicates) only ever see the hidden sender's unmutated traffic.
Exception: `sequence_number_override` and `dest_mac_mutation` are also applied by the
end-system sender (`afdx-end-system.cc:218-256`), so those two reach the receivers through
the hidden sender.

### Is it intended?
No evidence that it is. The paper (Section IV-B) says "conforming traffic is emitted
exactly once per BAG… the stricter check does not drop conforming frames". The code comment
says the end systems are configured "for receiving". `context/DIAGNOSIS.md` lists the high
clean-traffic policing rate under "Root Cause Analysis" and attributes it to double
counting; the switch fix for that lowered it from 75% to 49%, and the rest went
unexplained. Jitter is measured at the receivers (`afdx-demo.cc:285-300`) and does not need
a second sender. Both senders are already present in the first commit (`dafc4c9`), so git
history does not show why. **Please confirm with the author.**

### Fix tested (in an isolated copy, not in this repository)
Remove the three `esN->AddTransmitVL(vl)` calls so the end systems only receive. Built in a
separate, de-linked copy of ns-3 (`/tmp/ns3_fixtest`). The unchanged copy reproduces the
repository's numbers exactly (control). 8 inputs (7 real ones from `llm_full_r1`, 1
synthetic), each bug-free and with each injected bug: 144 runs.

Bug-free counters, before → after:

| Input | Forwarded | Policing drops | MAC drops | ES rejections | Target-VL forwarded |
|---|---|---|---|---|---|
| No mutation | 3626 → 3380 | 3492 → **0** | 0 → 0 | 264 → **0** | 884 → 900 |
| Larger frame (1,000 B, within VL 3002 max of 1,024) | 3626 → 3380 | 3492 → 0 | 0 → 0 | 264 → 0 | 126 → 114 |
| Fake source MAC (VL 2003) | 3626 → 3154 | 3266 → 0 | 226 → 226 | 264 → 0 | 250 → **0** |
| Wrong destination MAC (VL 2001) | 3626 → 3380 | 3492 → 0 | 0 → 0 | 264 → 0 | 498 → 450 |
| Forced sequence number 255 (VL 2002) | 3626 → 3380 | 3492 → 0 | 0 → 0 | 260 → 0 | 250 → 226 |
| "Send faster", jitter -12 (VL 2002) | 3626 → 3156 | 3268 → 0 | 0 → 0 | 264 → 0 | 250 → **2** |
| Larger frame + jitter +100 (VL 3001) | 3626 → 3306 | 3462 → **44** | 0 → 0 | 264 → 0 | 126 → 40 |
| Drop half at sender (VL 1002, synthetic) | 3626 → 2932 | 3044 → 0 | 0 → 0 | 264 → 0 | 994 → 452 |

Injected bugs detected (rule of `compute_bdr.py`, difference > 0.5), before → after:

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

After the change, clean traffic is clean, the "free" detections disappear, and the
remaining detections are caused by the fuzzer's input. Finding A is not fixed by this
change: "send faster" still sends 2 frames.

---

## 5. Findings C-E: consequences for the metrics

### C. Bug detection (Experiment 3)
Per-bug detecting iterations from the replay reports (`bdr_replay_v2_*.json`):

| Bug | LLM r1 | Random s1 | BOOFUZZ |
|---|---|---|---|
| skip_bag_policing | 200 (first at 0) | 200 (0) | 198 (0) |
| skip_sequence_check | 200 (0) | 200 (0) | 198 (0) |
| skip_frame_validation | 82 | 41 | 39 |
| accept_oversized | 82 | 41 | 39 |
| skip_mac_validation | 5 | 16 | 13 |
| skip_constant_field | 5 | 13 | 24 |
| skip_token_bucket | 0 | 0 | 0 |
| skip_vl_check | 0 | 0 | 0 |

- `skip_bag_policing` and `skip_sequence_check` are detected at iteration 0 by every
  input, because of Finding B. The letter discloses that they are detected without
  mutation, but treats the clean-traffic drops as normal behavior.
- `skip_frame_validation` and `accept_oversized` disable the same check (disclosed).
- `skip_token_bucket` is unreachable because the fuzzer's frames never get past BAG
  policing (Finding B), not because of the mutation interface, as the letter states.
- Open question: forcing every sequence number to 255 causes **no** receiver rejections,
  even after the Finding B change. The receiver probably counts repeated numbers as
  duplicates, not errors. Not yet checked.

### D. Executed Rule Coverage still credits unrelated mutations
A label counts as executed if any of the 7 parameters changed, related to the rule or not.
The LLM sets `frame_size` in almost every plan, often to a legal size. So labels such as
`ip_header_checksum`, `ip_options_prohibited` or `low_priority_vl_output_buffer` count as
executed through a harmless size change. Sensitivity check: the same metric, but ignoring
iterations whose only change is an in-range frame size (my own rough cut, not a proposed
metric):

| Run | Executed coverage | Without in-range-size-only iterations |
|---|---|---|
| LLM full (mean of 5) | 47.6% | ≈34.7% |
| BOOFUZZ-style | 33.0% | 31.9% |
| Random (mean of 5) | 21.4% | 21.2% |
| A1 (steering only) | 51.4% | 48.6% |
| A2 (feedback only) | 23.2% | 11.9% |
| A0 (neither) | 3.2% | 2.2% |

The letter states that the measure "does not check that the traffic violates the labeled
rule", but still relies on it for its strongest results (88 vs. 61 categories; about 40
categories that only the LLM fuzzer reaches).

Related design point: the controller's steering and the coverage state shown to the LLM
both count **labels**. A category whose label was logged without being executed counts as
covered, and the controller never steers back to it.

### E. What the metrics count
`llm_fuzzer/utils/log_parser.py` reads end-of-run counters that are **summed over both
switches and all 8 VLs**:

- `frames_dropped_policing` is mostly the fuzzer sender's frames (Finding B).
- `frames_forwarded`, `es_frames_received` and `es_frames_rejected` are mostly the hidden
  sender's frames.
- The fuzzer mutates one VL, but the counters include 7 other, unmutated VLs, so its effect
  is diluted.

The reward, the feedback shown to the LLM, and the Experiment 3 detection rule all use
these totals.

---

## 6. Finding F: paper and letter statements that do not match the code

| Where | Statement | What the code does |
|---|---|---|
| Paper IV-B(b) | Conforming traffic is emitted once per BAG; the strict check does not drop conforming frames | Two senders; 49% of clean traffic is policed (Finding B) |
| Paper IV-B(c) | The A and B copies are sent "at exactly the same time" | B is sent 100 µs after A (`afdx-traffic-generator.cc:549-553`) |
| Paper Fig. 3, VIII-C; letter (R2 C3) | ES1 transmits, ES2 and ES3 only receive ("of which one transmits") | All three transmit: ES1 → VLs 1001-1003, ES2 → 2001-2003, ES3 → 3001-3002 (`config/virtual_links.csv`, confirmed in runs) |
| Letter summary; paper V-B | `timing_jitter_ms` is "a timing offset" | Random ±j for positive values; silence for negative values (Finding A) |
| Letter (R2 C1) | The two missed bugs "cannot be reached through the mutation interface" | `skip_token_bucket` is unreachable because of Finding B |
| Letter (Additional corrections) | "With the corrected runner, these iterations count as not executed" | Histories were recorded before the fix worked; exclusion comes from the replay |
| Letter (R1 C4b) | The public repository reproduces the results | `configs/` (rule base, test cases) is not tracked by git; the ns-3 path is hard-coded (`/home/hodisan1994/ns-3-reset/ns-3`) |
| Letter (R1 C3) | Interrupted LLM campaigns "resumed from their history" | Also: 40 failed records were removed before resuming, and run r3 was discarded and re-run |
| Letter (R1 C6 / R2 C6) | Coverage comes from the controller's steering, not the LLM | Steering's re-plan step is itself an LLM call; a "controller + random planner" control is needed to separate them |

---

## 7. Finding G: smaller issues

- **The `frames` list never reaches the simulator.** `TestGenerator` builds a frame list,
  including predefined test-case values such as `TC0`. Only the 7 flat fields of
  `sim_config` are sent to ns-3. The logged `num_frames` describes the unused list.
- **`MutationConfig` is defined four times** (in `afdx-demo.cc`, `afdx-traffic-generator.cc`,
  `afdx-end-system.cc`, `afdx-switch.cc`) and shared through `extern`. The copies are
  identical today; if one changes, fields will be read at the wrong offsets without any error.
- **`virtual_links.csv` shows as modified in git**; the difference is line endings only.
- **The WSL ns-3 tree links into this repository.** In
  `/home/hodisan1994/ns-3-reset/ns-3`, `examples/AFDX_V3`, `examples/AFDX_NAV`,
  `llm_fuzzer`, `configs`, `evaluation` and others are symlinks to this Windows folder.
  Editing "the WSL copy" edits the repository, and `cp`/`tar` copies keep the links.

---

## 8. How to reproduce

All commands run in WSL (`wsl -d Ubuntu-24.04`). They use the existing build and write only
to `/tmp`.

**Run the simulator on one input without touching the tree** (the same mechanism as
`SimulatorRunner(work_dir=...)`):

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

- Set `timing_jitter_ms` to `-1` or `-3` to reproduce Finding A. In
  `$W/examples/AFDX_V3/output/csv/AFDX-LOG-OUTPUT.csv`, the fuzzer's frames for VL 1002
  are the `TX` rows on network `A` with `PacketSize` 323; the hidden sender's are 530.
- For Finding B, count `RX` rows per node and size for VL 1002 after `t >= 0.1`: the
  subscribers (nodes 1 and 2) receive only 530-byte frames.

**Testing a simulator change.** Copy the tree to `/tmp` and replace every symlink with a
real copy before editing (`find . -maxdepth 2 -type l`, then `readlink -f`). Configure the
copy with
`./ns3 configure --build-profile=default --enable-examples --disable-tests --enable-modules='core;network;internet;csma;bridge'`
and run `./ns3 build afdx-demo`. Check that `CMAKE_HOME_DIRECTORY` in
`cmake-cache/CMakeCache.txt` points to the copy.

---

## 9. Open questions and suggested next steps

1. Confirm with the author whether the end-system sender is intended (Finding B).
2. Fix Findings A and B in the simulator, then replay all logged campaign inputs on the
   fixed simulator. This costs no LLM calls and gives corrected Experiment 3 numbers.
   Coverage (Experiment 2) does not depend on the simulator's counters, but the reward and
   feedback the LLM saw during the campaigns did.
3. Decide how Executed Rule Coverage should treat changes unrelated to the labeled rule
   (Finding D), and report the sensitivity either way.
4. Correct the manuscript and letter statements in Finding F before resubmission.
5. Commit `configs/` (or archive it with the artifact) and make the ns-3 path
   configurable, so the public repository can reproduce the results.
6. Check why a constant sequence number causes no receiver rejections (Finding C).
