# Full Simulator Diagnosis — Manual Tests Results

**Date:** 2026-02-16
**Method:** Direct C++ simulator runs with hand-crafted `mutations.json` files

---

## 1. Test Results Summary

### Baseline (no mutations)
| Metric (Switch A) | Value |
|---|---|
| Frames Received | 7118 |
| Frames Forwarded | 1757 |
| Frames Dropped (Policing) | 5361 |
| Frames Dropped (InvalidVL) | 0 |
| Frames Dropped (FrameError) | 0 |
| **Policing Rate** | **~75.3%** |

### Test: payload_delta=+5000 (VL 1001, max_frame=512)
| Metric | Value | Change from Baseline |
|---|---|---|
| Frames Received | 7118 | 0 |
| Frames Forwarded | 1757 | 0 |
| Frames Dropped (Policing) | 5361 | 0 |
| payloadAppliedBytes | 224 | — |
| **payloadClampCount** | **1** | — |
| **RESULT** | **C++ clamped 5000→224. NO EFFECT on policing.** | |

### Test: timing_jitter=-7ms (VL 1001, BAG=4ms)
| Metric | Value | Change from Baseline |
|---|---|---|
| Frames Received | 6222 | **-896** |
| Frames Forwarded | 1645 | **-112** |
| Frames Dropped (Policing) | 4577 | **-784** |
| **RESULT** | **Jitter WORKS — frame counts change.** | |
| **Policing Rate** | **~73.6%** | **Only -1.7% change** |

### Test: mac_mutation=spoof_src (VL 1001)
| Metric | Value | Change from Baseline |
|---|---|---|
| Frames Received | 7118 | 0 |
| Frames Forwarded | 1757 | 0 |
| macSpoofCount | 450 | Applied! |
| **RESULT** | **MAC spoofing IS applied but switch DOESN'T check MAC → no policing effect** | |

### Test: prob=0.5 / prob=1.0 (VL 1001)
| prob | Received | Forwarded | DroppedPol | txDrops | PolicingRate |
|---|---|---|---|---|---|
| 0.0 | 7118 | 1757 | 5361 | 0 | 75.3% |
| 0.5 | 6654 | 1714 | 4940 | 232 | 74.2% |
| 1.0 | 6218 | 1645 | 4573 | 450 | 73.5% |
| **RESULT** | **Frame counts change but policing RATE stays ~73-75%** | | | | |

### Test: Invalid VL IDs (9999, 5000, 0)
| Metric | Value | Change from Baseline |
|---|---|---|
| ALL metrics | Identical to baseline | 0 |
| DroppedInvalidVL | 0 | 0 |
| **RESULT** | **No effect — mutations can only modify EXISTING VLs, cannot inject new VL traffic** | |

### VL + Jitter Sweep (all 6 VLs × jitter={-3, 0, +5})
| VL | BAG | Recv(j=-3) | Recv(j=0) | Recv(j=+5) |
|---|---|---|---|---|
| 1001 | 4ms | 6222 (-896) | 7118 | 7090 (-28) |
| 1002 | 4ms | 6222 (-896) | 7118 | 7080 (-38) |
| 2001 | 8ms | 6670 (-448) | 7118 | 7112 (-6) |
| 2002 | 16ms | 6894 (-224) | 7118 | 7114 (-4) |
| 3001 | 32ms | 7006 (-112) | 7118 | 7114 (-4) |
| 3002 | 32ms | 7008 (-110) | 7118 | 7114 (-4) |

**Key pattern:** Impact is proportional to BAG. Smaller BAG = bigger effect from jitter.
But policing RATE stays ~73-75% in ALL cases.

---

## 2. Root Cause Analysis

### Finding 1: Payload Delta is USELESS (CRITICAL)

**Location:** `afdx-demo.cc` lines 739-766

The C++ code **clamps** the `payload_delta_bytes` to the VL's `[minFrameSize, maxFrameSize]` range:

```
candidate = baseSize + payloadDeltaBytes
if candidate < minFrameSize → clamp to minFrameSize
if candidate > maxFrameSize → clamp to maxFrameSize
```

For VL 1001: base=288, min=64, max=512. So delta is limited to [-224, +224].
**The switch's frame validation can NEVER fail** because frames are always within valid bounds.

**Impact:** `afdxFramesDroppedFrameError` counter can NEVER be triggered by fuzzing.

### Finding 2: Policing Rate is a STRUCTURAL CONSTANT (~75%)

The switch has **both** `SetReceiveCallback` and `SetPromiscReceiveCallback` registered on all ports.
This means:
1. Each incoming frame triggers **both** callbacks → double counting
2. Each **forwarded** frame is seen by the switch's own port in promiscuous mode → additional counting

The policing rate is a function of the **topology** (number of ports, BAG ratios, double-counting),
NOT a function of mutations. Mutations change absolute frame counts but the **ratio** stays constant.

### Finding 3: MAC Validation Does NOT Exist in Switch

**Location:** `afdx-switch.cc` `ProcessFrame()` method

The switch checks:
1. ✅ Frame size validation (but never triggered — see Finding 1)
2. ✅ VL authorization (`IsVLAuthorized`)
3. ✅ BAG policing (`CheckBagPolicing`)
4. ✅ Token bucket (`CheckTokenBucket`)
5. ❌ **NO MAC address validation**

The MAC spoofing mutation IS applied at the traffic generator (450 spoofed frames confirmed),
but the switch has no logic to detect or drop spoofed-MAC frames.

### Finding 4: Invalid VL Injection is IMPOSSIBLE

The mutation system can only modify **existing** VLs (by targeting a `vlId`).
There is no mechanism to inject frames on VL IDs that don't exist in `virtual_links.csv`.
Therefore, the `afdxFramesDroppedInvalidVL` counter can **never** be triggered.

### Finding 5: Only timing_jitter Produces Observable Changes

Of all 5 mutation parameters:

| Parameter | Applied? | Changes Policing? | Useful? |
|---|---|---|---|
| `payload_delta_bytes` | Yes (clamped) | ❌ Never | ❌ No |
| `timing_jitter_ms` | Yes | ✅ Changes absolute counts | ⚠️ Partially |
| `mac_mutation` | Yes | ❌ No MAC check in switch | ❌ No |
| `prob` (TX drop) | Yes | ❌ Rate stays constant | ❌ No |
| `is_extreme_test` | Flag only | N/A | N/A |

---

## 3. What This Means for the Paper

### The Good News
1. **The fuzzing pipeline works end-to-end**: Mutations are loaded, applied, and the simulator runs correctly
2. **The infrastructure is solid**: Log parsing, metric extraction, iteration history — all working
3. **Timing mutations DO have an effect**: Frame counts change measurably with jitter
4. **The switch policing IS real**: BAG enforcement and token bucket are implemented correctly

### The Bad News
1. **Policing RATE is not a meaningful fuzzer comparison metric** — it's a constant
2. **3 out of 5 mutation types have zero observable effect** on switch behavior
3. **Frame size violations can't be triggered** due to C++ clamping
4. **Invalid VL violations can't be triggered** — no injection mechanism
5. **MAC violations can't be detected** — no switch-side MAC validation

---

## 4. Required C++ Simulator Changes (By Priority)

### P0 — Remove Payload Clamping (enables frame-size violations)
**File:** `afdx-demo.cc` lines 744-754
**Change:** Remove or relax the clamping logic. Allow `payload_delta_bytes` to produce
frames outside the `[minFrameSize, maxFrameSize]` range. This would trigger
`ValidateFrame()` in the switch, causing `afdxFramesDroppedFrameError` to increment.

### P1 — Fix Double-Counting (accurate metrics)
**File:** `afdx-switch.cc` lines 160-167
**Change:** Remove the promiscuous callback OR add a "seen" flag to prevent processing
the same frame twice. This would make `afdxFramesReceived` reflect actual unique incoming
frames and give meaningful policing rate changes.

### P2 — Add MAC Address Validation to Switch
**File:** `afdx-switch.cc` `ProcessFrame()` method
**Change:** After VL authorization check, verify that the source MAC matches the expected
MAC for that VL (from `virtual_links.csv`). Drop frame if MAC doesn't match.
This would make `mac_mutation=spoof_src` detectable.

### P3 — Add Invalid VL Injection Capability
**File:** `afdx-traffic-generator.cc` or new injection mechanism
**Change:** Allow the mutation system to generate frames on arbitrary VL IDs, not just
modify existing VLs. This would trigger `afdxFramesDroppedInvalidVL`.

### P4 — Add Sequence Number Validation
**File:** `afdx-switch.cc`
**Change:** Track expected sequence numbers per VL and detect gaps/duplicates.
This would enable sequence-number fuzzing to be observable.

---

## 5. Alternative: Change Metrics Instead of Simulator

If modifying the C++ code is not feasible, change what we MEASURE:

### Replace policing_rate with:
1. **Absolute Frame Delta**: `|frames_received(mutated) - frames_received(baseline)|`
2. **Per-VL Drop Distribution**: Track which VLs are being policed differently
3. **Forwarded Frame Delta**: `|frames_forwarded(mutated) - frames_forwarded(baseline)|`
4. **Mutation Application Rate**: How many mutations were actually applied (not clamped)

### Focus the paper on:
- Timing mutations (the one dimension that works)
- Rule coverage and diversity (which rules the fuzzer explores)
- Comparison of exploration strategies (LLM vs Random vs Boofuzz)
- Cost-effectiveness of LLM guidance

---

## 6. Recommended Path Forward

**Option A (Best for paper quality, ~2-3 days):**
1. Fix P0 (remove clamping) — enables 80% more mutation types
2. Fix P1 (double-counting) — makes policing rate meaningful
3. Fix P2 (MAC validation) — enables MAC-based violations
4. Re-run all fuzzers with fixed simulator
5. Results will show real differences between fuzzers

**Option B (Faster, ~1 day):**
1. Fix P0 only (remove clamping)
2. Change metrics to absolute deltas instead of rates
3. Re-run fuzzers
4. Show that LLM fuzzer explores more mutation dimensions

**Option C (Minimal changes, ~half day):**
1. Don't change C++ at all
2. Redesign metrics around what works (timing mutations, rule coverage, diversity)
3. Accept that policing rate is not a useful comparison metric
4. Focus paper on methodology and LLM-guided exploration strategy
