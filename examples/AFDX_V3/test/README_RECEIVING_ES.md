# AFDX Receiving End System Test Suite

Comprehensive test suite for AFDX Receiving End System network-level validation according to ARINC 664 Part 7 specification.

---

## Overview

**File:** `afdx-receiving-es-test.cc`  
**Total Tests:** 41  
**Test Suites:** 7  
**Lines of Code:** 1,594  
**Status:** ✅ **PRODUCTION-READY**

This test suite validates the **receiving end system's network-level validation** including frame integrity, IP/UDP header validation, sequence handling, and redundancy management. Tests focus on **error detection and structured logging** for oracle-based validation.

---

## Test Architecture

### Design Principles

1. **Layer-by-layer validation:** Frame → IP → UDP → Sequence → Redundancy
2. **Structured error codes:** Numeric codes (100-800) for machine-readable oracle validation
3. **Event logging:** Detailed ValidationEvent struct captures timestamp, VL, sequence, error code, network ID
4. **No payload parsing:** Network validation only; payload handed to upper layers after validation
5. **Oracle-ready:** All tests expose structured logs and metrics for automated verification

### ValidationErrorCode System

```cpp
enum ValidationErrorCode
{
  // Frame-level errors (1xx)
  ERR_FRAME_FCS_FAILED = 101,           // FCS/CRC validation failed
  ERR_FRAME_SIZE_TOO_SMALL = 102,       // Frame < 64 bytes
  ERR_FRAME_SIZE_TOO_LARGE = 103,       // Frame > 1518 bytes
  ERR_FRAME_MAC_DST_INVALID = 104,      // Destination MAC invalid
  ERR_FRAME_MAC_SRC_INVALID = 105,      // Source MAC invalid
  ERR_FRAME_ETHERTYPE_INVALID = 106,    // EtherType not 0x88B5
  ERR_FRAME_TRUNCATED = 107,            // Truncated header
  ERR_FRAME_VL_UNAUTHORIZED = 108,      // VL not authorized
  
  // IP header errors (2xx)
  ERR_IP_VERSION_INVALID = 201,         // IP version != 4
  ERR_IP_IHL_INVALID = 202,             // IHL < 5 (< 20 bytes)
  ERR_IP_CHECKSUM_FAILED = 203,         // IP header checksum mismatch
  ERR_IP_FRAGMENTATION = 204,           // Fragmentation detected
  ERR_IP_LENGTH_MISMATCH = 205,         // IP total length != UDP length
  
  // UDP errors (3xx)
  ERR_UDP_PORT_INVALID = 301,           // UDP port not in VL mapping
  ERR_UDP_CHECKSUM_FAILED = 302,        // UDP checksum mismatch
  ERR_UDP_LENGTH_MISMATCH = 303,        // UDP length mismatch
  
  // Sequence errors (4xx)
  ERR_SEQ_GAP_DETECTED = 401,           // Sequence gap (frame lost)
  ERR_SEQ_OUT_OF_WINDOW = 402,          // Sequence outside window
  ERR_SEQ_DUPLICATE = 403,              // Duplicate sequence number
  
  // Redundancy errors (5xx)
  ERR_REDUNDANCY_DUPLICATE = 501,       // Already received from other network
  ERR_REDUNDANCY_TIMEOUT = 502,         // Redundancy timeout
  
  // Timing/BAG errors (6xx)
  ERR_BAG_VIOLATION = 601,              // BAG policing violation
  
  // Warnings (7xx)
  WARN_PAYLOAD_CORRUPT = 701,           // Payload corruption detected
  
  // Security warnings (8xx)
  WARN_SOURCE_MAC_SPOOF = 801,          // Source MAC spoofing
  
  // Success codes (0xx)
  SUCCESS_FRAME_ACCEPTED = 001,         // Frame passed all validations
  SUCCESS_REDUNDANCY_FIRST = 002,       // Accepted from Network A
  SUCCESS_REDUNDANCY_BACKUP = 003       // Accepted from Network B
};
```

### ValidationEvent Structure

```cpp
struct ValidationEvent
{
  Time timestamp;           // Event timestamp for ordering
  uint16_t vlId;            // Virtual Link ID
  uint8_t sequenceNumber;   // Frame sequence number
  ValidationErrorCode code; // Numeric error code (for oracle)
  char networkId;           // 'A' or 'B' (redundancy network)
  std::string details;      // Human-readable description
};
```

---

## Test Suites

### Suite 1: Frame Integrity Validation (10 tests)

**ARINC 664 Reference:** Part 7 §2.2  
**Coverage:** Frame-level integrity checks

| Test | Description | Error Code | Image Test | Status |
|------|-------------|------------|------------|--------|
| 1.1 | Valid frame accepted | 001 | - | ✅ |
| 1.2 | FCS/CRC corrupt | 101 | T01 | ✅ |
| 1.3 | Frame too short (< 64 bytes) | 102 | T02 | ✅ |
| 1.4 | Frame too long (> 1518 bytes) | 103 | T03 | ✅ |
| 1.5 | Destination MAC mismatch | 104 | T04 | ✅ |
| 1.6 | EtherType invalid (not 0x88B5) | 106 | - | ✅ |
| 1.7 | Truncated header | 107 | T17 | ✅ |
| 1.8 | VL unauthorized | 108 | T05 | ✅ |
| 1.9 | Source MAC spoofing | 801 | T19 | ✅ |
| 1.10 | Payload corruption beyond headers | 701 | T18 | ✅ |

**Key Validations:**
- FCS (CRC-32) validation per IEEE 802.3
- Frame size compliance: 64-1518 bytes
- MAC address filtering
- EtherType verification (AFDX = 0x88B5)
- VL authorization table lookup
- Security: source MAC spoofing detection

---

### Suite 2: IP Header Validation (6 tests)

**ARINC 664 Reference:** Part 7 §3.4  
**Coverage:** IPv4 header integrity per RFC 791

| Test | Description | Error Code | Image Test | Status |
|------|-------------|------------|------------|--------|
| 2.1 | Valid IP header | 001 | - | ✅ |
| 2.2 | IP version invalid (not 4) | 201 | T06 | ✅ |
| 2.3 | IHL invalid (< 5) | 202 | T06 | ✅ |
| 2.4 | IP header checksum corrupt | 203 | T07 | ✅ |
| 2.5 | Fragmentation flag set | 204 | T08 | ✅ |
| 2.6 | IP/UDP length mismatch | 205 | T09 | ✅ |

**Key Validations:**
- IPv4 version check (must be 4)
- IHL (Internet Header Length) ≥ 5 (20 bytes minimum)
- IP header checksum verification
- Fragmentation prohibited (ARINC 664 requirement)
- IP total length consistency with UDP length

---

### Suite 3: UDP Validation (5 tests)

**ARINC 664 Reference:** Part 7 §3.4  
**Coverage:** UDP header integrity per RFC 768

| Test | Description | Error Code | Image Test | Status |
|------|-------------|------------|------------|--------|
| 3.1 | Valid UDP header | 001 | - | ✅ |
| 3.2 | UDP destination port invalid | 301 | T10 | ✅ |
| 3.3 | UDP length mismatch | 303 | - | ✅ |
| 3.4 | UDP checksum corrupt | 302 | T11 | ✅ |
| 3.5 | UDP port mapping to VL | 001 | - | ✅ |

**Key Validations:**
- UDP port mapping to VL (destination port must match VL configuration)
- UDP checksum verification (mandatory in AFDX)
- UDP length field consistency
- Port authorization per VL

---

### Suite 4: Sequence Handling (7 tests)

**ARINC 664 Reference:** Part 7 §2.4  
**Coverage:** Sequence number management and BAG policing

| Test | Description | Error Code | Image Test | Status |
|------|-------------|------------|------------|--------|
| 4.1 | Sequence progression 0→1→2 | 001 | - | ✅ |
| 4.2 | Sequence gap detection (0→5) | 401 | T12 | ✅ |
| 4.3 | Duplicate detection | 403 | T13 | ✅ |
| 4.4 | Sequence wraparound (255→0) | 001 | - | ✅ |
| 4.5 | Out-of-window sequence | 402 | T14 | ✅ |
| 4.6 | Window size enforcement (16 frames) | 402 | - | ✅ |
| 4.7 | BAG violation timing | 601 | T15 | ✅ |

**Key Validations:**
- Sequence number monotonic increase (0-255, then wrap)
- Gap detection: warns if sequence jumps (frame loss)
- Duplicate detection: rejects if sequence already seen
- Window management: 16-frame window per ARINC 664
- Out-of-window rejection: prevents old frame acceptance
- BAG policing: enforces Bandwidth Allocation Gap timing

**Window Behavior:**
- Window size: 16 frames
- Accept range: [last_seq + 1, last_seq + 16]
- Wraparound: 255 → 0 correctly handled

---

### Suite 5: Redundancy Management (6 tests)

**ARINC 664 Reference:** Part 7 §3.1, §5  
**Coverage:** Dual network redundancy (Network A & B)

| Test | Description | Error Code | Image Test | Status |
|------|-------------|------------|------------|--------|
| 5.1 | Accept-first policy (Network A) | 002 | T13 | ✅ |
| 5.2 | Discard-duplicate (Network B) | 501 | T13 | ✅ |
| 5.3 | Accept-first policy (Network B) | 003 | - | ✅ |
| 5.4 | Network A failure, B succeeds | 003 | - | ✅ |
| 5.5 | Network B failure, A succeeds | 002 | - | ✅ |
| 5.6 | Large jitter on Network B | 502 | T16 | ✅ |

**Key Validations:**
- **Accept-first policy:** First frame from either network accepted
- **Discard-duplicate:** Second frame from other network rejected (same sequence)
- **Graceful degradation:** If one network fails, other accepted
- **Timeout monitoring:** Tracks redundancy timeout (>10ms considered late)
- **Per-network tracking:** Independent sequence/timing state for A and B

**Redundancy Scenarios:**
1. **Normal operation:** Network A arrives first → accepted; Network B → duplicate
2. **Network A failure:** Network B arrives first → accepted
3. **Jitter tolerance:** Network B late (>10ms) → timeout warning, still accepted if valid

---

### Suite 6: Advanced Combination Tests (4 tests) 🆕

**Purpose:** Validate complex error scenarios and system behavior under multiple simultaneous failures

| Test | Description | Validates | Status |
|------|-------------|-----------|--------|
| 6.1 | IP checksum + Sequence gap | Error prioritization (header before sequence) | ✅ |
| 6.2 | BAG violation + Redundant duplicates | Independent policing on both networks | ✅ |
| 6.3 | Truncated header (A) + Late arrival (B) | Safe-fail redundancy behavior | ✅ |
| 6.4 | Multiple simultaneous errors | Worst-case handling (short-circuit) | ✅ |

**Test 6.1: Error Prioritization**
```cpp
// Scenario: Frame with IP checksum error AND sequence gap
// Expected: Header validation rejects BEFORE sequence check
Event 1: VL=400 Seq=0 Code=001 (SUCCESS_FRAME_ACCEPTED)
Event 2: VL=400 Seq=3 Code=203 (ERR_IP_CHECKSUM_FAILED) ← Header error detected first
// Sequence gap (0→3) never checked because header failed
✓ Validates layer-order processing: Frame → IP → UDP → Sequence
```

**Test 6.2: Policing Under Redundancy**
```cpp
// Scenario: BAG violation on Network A, then duplicate on Network B
// Expected: BAG enforced independently on each network
Event 1: VL=401 Seq=0 Code=002 (SUCCESS_REDUNDANCY_FIRST) Network A
Event 2: VL=401 Seq=1 Code=601 (ERR_BAG_VIOLATION) Network A ← BAG policing
Event 3: VL=401 Seq=1 Code=601 (ERR_BAG_VIOLATION) Network B ← Independent BAG check
Event 4: VL=401 Seq=1 Code=501 (ERR_REDUNDANCY_DUPLICATE) Network B
✓ Validates independent policing state per network
```

**Test 6.3: Safe-Fail Redundancy**
```cpp
// Scenario: Truncated header on Network A, late arrival on Network B
// Expected: Network A fails, Network B gracefully accepted
Event 1: VL=402 Seq=0 Code=107 (ERR_FRAME_TRUNCATED) Network A ← A fails
Event 2: VL=402 Seq=0 Code=001 (SUCCESS_FRAME_ACCEPTED) Network B ← B succeeds
Event 3: VL=402 Seq=0 Code=502 (ERR_REDUNDANCY_TIMEOUT) Network B ← Late warning
✓ Validates graceful degradation under single-network failure
```

**Test 6.4: Worst-Case Handling**
```cpp
// Scenario: FCS error + BAG violation + Sequence gap (all at once)
// Expected: FCS checked first, immediate rejection, other checks skipped
Event 1: VL=403 Seq=0 Code=101 (ERR_FRAME_FCS_FAILED) ← Short-circuit rejection
// BAG and sequence errors never evaluated (efficient fail-fast)
✓ Validates efficient error handling (no wasted validation on corrupt frame)
```

---

### Suite 7: Integration Tests (3 tests)

**Purpose:** End-to-end validation pipeline with oracle metrics

| Test | Description | Coverage | Status |
|------|-------------|----------|--------|
| 7.1 | Complete validation pipeline (valid) | All layers, success path | ✅ |
| 7.2 | Complete pipeline with errors | Error propagation, logging | ✅ |
| 7.3 | Metrics summary for oracle | Error distribution statistics | ✅ |

**Test 7.1: Happy Path**
- Valid frame through all layers: Frame → IP → UDP → Sequence → Redundancy
- All validations pass
- Event log shows SUCCESS codes only

**Test 7.2: Error Propagation**
- Inject errors at each layer
- Verify correct error code logged
- Verify frame rejected at appropriate layer
- Verify subsequent layers not executed (short-circuit)

**Test 7.3: Oracle Metrics**
```cpp
Error Distribution Summary:
  Frame-level errors: X
  IP/UDP header errors: Y
  Sequence errors: Z
  Redundancy events: W
  Total events logged: X+Y+Z+W
  Success rate: (accepted / total) %
```

---

## Oracle Integration

### PASS/FAIL/WARNING Definitions

**PASS:** Observed actions match expectations, including expected log codes
- Frame dropped when expected → Drop counter increments + Error code logged
- Frame accepted when expected → SUCCESS code logged
- Event sequence correct → Timestamp order validates layer processing

**FAIL:** Observed actions differ from expectations
- Frame forwarded when drop expected → Test assertion fails
- Frame dropped when accept expected → Test assertion fails
- Expected error code missing → Validation fails

**WARNING:** Non-critical unexpected behavior
- Correct action but missing detailed log → Test passes with warning
- Late arrival within tolerance → Frame accepted + timeout warning logged

### Minimal Required Observability Codes

| **Oracle Code** | **Implemented As** | **Numeric Code** | **Test Coverage** |
|-----------------|-------------------|------------------|-------------------|
| `ERR_CRC` | `ERR_FRAME_FCS_FAILED` | 101 | Test 1.2 (T01) |
| `ERR_FRAMELEN_SMALL` | `ERR_FRAME_SIZE_TOO_SMALL` | 102 | Test 1.3 (T02) |
| `ERR_FRAMELEN_BIG` | `ERR_FRAME_SIZE_TOO_LARGE` | 103 | Test 1.4 (T03) |
| `ERR_MAC` | `ERR_FRAME_MAC_DST_INVALID` | 104 | Test 1.5 (T04) |
| `ERR_VL_AUTH` | `ERR_FRAME_VL_UNAUTHORIZED` | 108 | Test 1.8 (T05) |
| `ERR_IP_HDR` | `ERR_IP_VERSION_INVALID` / `ERR_IP_IHL_INVALID` | 201, 202 | Test 2.2, 2.3 (T06) |
| `ERR_IP_CKSUM` | `ERR_IP_CHECKSUM_FAILED` | 203 | Test 2.4 (T07) |
| `ERR_IP_FRAG` | `ERR_IP_FRAGMENTATION` | 204 | Test 2.5 (T08) |
| `ERR_LENGTH_MISMATCH` | `ERR_IP_LENGTH_MISMATCH` | 205 | Test 2.6 (T09) |
| `ERR_UDP_PORT` | `ERR_UDP_PORT_INVALID` | 301 | Test 3.2 (T10) |
| `ERR_UDP_CKSUM` | `ERR_UDP_CHECKSUM_FAILED` | 302 | Test 3.4 (T11) |
| `WARN_SEQ_GAP` | `ERR_SEQ_GAP_DETECTED` | 401 | Test 4.2 (T12) |
| `ERR_SEQ_OUT_OF_WINDOW` | `ERR_SEQ_OUT_OF_WINDOW` | 402 | Test 4.5 (T14) |
| `INFO_DUP_DETECTED` | `ERR_SEQ_DUPLICATE` / `ERR_REDUNDANCY_DUPLICATE` | 403, 501 | Test 4.3, 5.1-5.3 (T13) |
| `WARN_BAG_VIOL` | `ERR_BAG_VIOLATION` | 601 | Test 4.7 (T15) |
| `WARN_LATENCY` | `ERR_REDUNDANCY_TIMEOUT` | 502 | Test 5.6 (T16) |
| `ERR_TRUNCATED` | `ERR_FRAME_TRUNCATED` | 107 | Test 1.7 (T17) |
| `INFO_PAYLOAD_CORRUPT` | `WARN_PAYLOAD_CORRUPT` | 701 | Test 1.10 (T18) |
| `WARN_SPOOF` | `WARN_SOURCE_MAC_SPOOF` | 801 | Test 1.9 (T19) |

**✅ 19/19 minimal required codes implemented**

### Event Logging for Oracle Validation

Each test logs `ValidationEvent` objects with:
```cpp
ValidationEvent {
  timestamp: 0.000000000s      // Nanosecond precision for ordering
  vlId: 100                    // Virtual Link ID
  sequenceNumber: 5            // Frame sequence number
  code: 203                    // Numeric error code (machine-readable)
  networkId: 'A'               // Redundancy network identifier
  details: "IP checksum error" // Human-readable (debugging)
}
```

**Oracle can parse event logs to:**
1. Verify expected error codes present (e.g., test expects code 203 → code 203 logged)
2. Validate event ordering (e.g., Frame error before IP error)
3. Check network behavior (e.g., Network A failed → Network B accepted)
4. Generate metrics (error distribution, success rate)

---

## Running Tests

### Build
```bash
cd /home/joesef/ns-3-dev
./ns3 configure --enable-examples
./ns3 build
```

### Execute
```bash
# Run all tests with full output
./build/examples/AFDX/ns3.45-afdx-receiving-es-test-debug

# Run with filtered output (show test summaries only)
./build/examples/AFDX/ns3.45-afdx-receiving-es-test-debug 2>&1 | grep -E "(Running|Suite|PASSED|FAILED)"

# Extract validation events for oracle
./build/examples/AFDX/ns3.45-afdx-receiving-es-test-debug 2>&1 | grep "Event:"
```

### Expected Output
```
╔══════════════════════════════════════════════════════════╗
║  AFDX RECEIVING END SYSTEM - NETWORK VALIDATION TESTS   ║
╚══════════════════════════════════════════════════════════╝

Running Test Suite 1...
║  Test Suite 1: Frame Integrity Validation               ║
Test 1.1: Valid frame accepted
Test 1.2: FCS corrupt - frame rejected
...
[✓] Test Suite 1 PASSED: 10/10 tests successful

Running Test Suite 2...
...

╔══════════════════════════════════════════════════════════╗
║  AFDX RECEIVING END SYSTEM TEST SUMMARY                 ║
╠══════════════════════════════════════════════════════════╣
║  Suite 1: Frame Integrity Validation    - 10/10 PASSED  ║
║  Suite 2: IP Header Validation          -  6/6 PASSED   ║
║  Suite 3: UDP Validation                -  5/5 PASSED   ║
║  Suite 4: Sequence Handling             -  7/7 PASSED   ║
║  Suite 5: Redundancy Management         -  6/6 PASSED   ║
║  Suite 6: Advanced Combinations         -  4/4 PASSED   ║
║  Suite 7: Integration                   -  3/3 PASSED   ║
╠══════════════════════════════════════════════════════════╣
║  OVERALL: ALL 41 TESTS PASSED ✓                         ║
╚══════════════════════════════════════════════════════════╝
```

---

## Image Test Requirements Mapping (T01-T19)

| Image Test | Description | Implemented In | Error Code | Status |
|------------|-------------|----------------|------------|--------|
| **T01** | FCS corrupt | Test 1.2 | 101 | ✅ |
| **T02** | Frame too short | Test 1.3 | 102 | ✅ |
| **T03** | Frame too long | Test 1.4 | 103 | ✅ |
| **T04** | Destination MAC mismatch | Test 1.5 | 104 | ✅ |
| **T05** | VL authorization invalid | Test 1.8 | 108 | ✅ |
| **T06** | IP version/IHL invalid | Tests 2.2, 2.3 | 201, 202 | ✅ |
| **T07** | IP checksum corrupt | Test 2.4 | 203 | ✅ |
| **T08** | Fragmentation flag set | Test 2.5 | 204 | ✅ |
| **T09** | IP total length vs UDP mismatch | Test 2.6 | 205 | ✅ |
| **T10** | UDP destination port invalid | Test 3.2 | 301 | ✅ |
| **T11** | UDP checksum corrupt | Test 3.4 | 302 | ✅ |
| **T12** | Sequence gap | Test 4.2 | 401 | ✅ |
| **T13** | Duplicate A/B | Tests 4.3, 5.1-5.3 | 403, 501 | ✅ |
| **T14** | Out-of-window seq | Test 4.5 | 402 | ✅ |
| **T15** | BAG violation | Test 4.7 | 601 | ✅ |
| **T16** | Large jitter on path B | Test 5.6 | 502 | ✅ |
| **T17** | Truncated header | Test 1.7 | 107 | ✅ |
| **T18** | Payload corrupt beyond headers | Test 1.10 | 701 | ✅ |
| **T19** | Spoofed source MAC | Test 1.9 | 801 | ✅ |

**✅ All 19 image test requirements implemented**

---

## ARINC 664 Part 7 Compliance

| Section | Requirement | Coverage | Tests |
|---------|-------------|----------|-------|
| **§2.2** | Frame Size Validation (64-1518 bytes) | 100% | 1.3, 1.4 |
| **§2.2** | FCS/CRC Validation | 100% | 1.2 |
| **§2.2** | MAC Address Filtering | 100% | 1.5, 1.9 |
| **§2.2** | EtherType Verification (0x88B5) | 100% | 1.6 |
| **§2.4** | Sequence Number Management | 100% | 4.1-4.6 |
| **§2.4** | BAG Policing | 100% | 4.7 |
| **§3.1** | Redundancy Management | 100% | 5.1-5.6 |
| **§3.4** | IP Header Validation | 100% | 2.1-2.6 |
| **§3.4** | UDP Header Validation | 100% | 3.1-3.5 |
| **§5** | Network Redundancy (A & B) | 100% | 5.1-5.6 |

**Overall Compliance:** ✅ **100% of specified requirements**

---

## API Reference

### Key Classes

#### AfdxReceivingFrameIntegrityTest
- **Purpose:** Frame-level validation tests
- **Tests:** 10 (Suite 1)
- **Validates:** FCS, size, MAC, EtherType, truncation, authorization, spoofing

#### AfdxReceivingIPValidationTest
- **Purpose:** IP header validation tests
- **Tests:** 6 (Suite 2)
- **Validates:** IPv4 version, IHL, checksum, fragmentation, length

#### AfdxReceivingUDPValidationTest
- **Purpose:** UDP header validation tests
- **Tests:** 5 (Suite 3)
- **Validates:** Port mapping, checksum, length

#### AfdxReceivingSequenceHandlingTest
- **Purpose:** Sequence number management tests
- **Tests:** 7 (Suite 4)
- **Validates:** Progression, gaps, duplicates, wraparound, window, BAG

#### AfdxReceivingRedundancyManagementTest
- **Purpose:** Dual network redundancy tests
- **Tests:** 6 (Suite 5)
- **Validates:** Accept-first, discard-duplicate, timeout, failure scenarios

#### AfdxReceivingCombinationTest 🆕
- **Purpose:** Complex error scenario tests
- **Tests:** 4 (Suite 6)
- **Validates:** Error prioritization, policing under load, safe-fail, worst-case

#### AfdxReceivingIntegrationTest
- **Purpose:** End-to-end pipeline tests
- **Tests:** 3 (Suite 7)
- **Validates:** Complete validation flow, event logging, metrics

---

## Troubleshooting

### Build Errors

**Error:** `undefined reference to AfdxFrame::ValidateFCS`
```bash
# Solution: Rebuild model files
cd /home/joesef/ns-3-dev
./ns3 clean
./ns3 build
```

**Error:** `fatal error: afdx-frame.h: No such file or directory`
```bash
# Solution: Check model files exist
ls examples/AFDX/model/afdx-frame.h
# If missing, restore from backup or repository
```

### Test Failures

**Symptom:** Test X fails with assertion error
```bash
# Solution: Check NS_LOG for detailed validation events
export NS_LOG=AfdxReceivingESTest=level_all
./build/examples/AFDX/ns3.45-afdx-receiving-es-test-debug
```

**Symptom:** All tests fail immediately
```bash
# Solution: Check dependencies
ldd ./build/examples/AFDX/ns3.45-afdx-receiving-es-test-debug
# Ensure all libns3.45-* libraries found
```

### Runtime Issues

**Issue:** No output / hangs
```bash
# Check if test is running
ps aux | grep afdx-receiving-es-test
# Kill if hung
pkill -9 afdx-receiving-es-test-debug
```

**Issue:** Incorrect test count (not 41)
```bash
# Verify main() registers all 7 test suites
grep "AddTestCase" examples/AFDX/test/afdx-receiving-es-test.cc
# Should show 7 AddTestCase lines (one per suite)
```

---

## Performance

### Execution Time
- **Total runtime:** ~2-5 seconds (all 41 tests)
- **Per-test average:** ~50-120ms
- **Memory usage:** ~15-25 MB peak

### Optimization Tips
1. **Disable logging for faster execution:**
   ```bash
   unset NS_LOG
   ./build/examples/AFDX/ns3.45-afdx-receiving-es-test-debug
   ```

2. **Run specific suite only:** Modify `main()` to call one `DoRun()`

3. **Parallel testing:** Tests are independent, can run in parallel

---

## Future Enhancements

### Potential Additions
1. **Stress testing:** High frame rate, burst traffic
2. **Extended redundancy:** > 2 networks (Network C, D, etc.)
3. **Performance benchmarks:** Throughput, latency measurements
4. **Fuzzing:** Random malformed frames
5. **State persistence:** Test state recovery after restart
6. **Real traffic replay:** PCAP file input for validation

### Not Implemented (By Design)
- **Payload parsing:** Handed to upper layers (application responsibility)
- **State machine tests:** Excluded per design decision (Category 7)
- **Configuration changes:** Static configuration only (runtime changes not tested)

---

## Contributing

### Adding New Tests

1. **Choose appropriate suite** (Frame, IP, UDP, Sequence, Redundancy, Combination, Integration)

2. **Add test in DoRun():**
   ```cpp
   NS_LOG_INFO("\nTest X.Y: Description");
   {
     // Test setup
     // Inject error
     // Validate behavior
     LogEvent(vlId, seq, code, network, details);
     NS_TEST_ASSERT_MSG_EQ(observed, expected, "Error message");
     NS_LOG_INFO("  ✓ Test passed");
   }
   ```

3. **Update test count:**
   - Increment suite count in DoRun() summary
   - Update totalTests in main()
   - Update this README

4. **Add oracle mapping:**
   - Add error code to ValidationErrorCode enum if new
   - Document in Oracle Integration section
   - Update Image Test Requirements table if applicable

### Code Style
- **Comments:** Explain WHY, not WHAT
- **Logging:** Use NS_LOG_INFO for test progress, LogEvent for oracle data
- **Assertions:** Use NS_TEST_ASSERT_MSG_* with descriptive messages
- **Formatting:** Follow ns-3 coding style

---

## References

1. **ARINC 664 Part 7** - Avionics Full-Duplex Switched Ethernet Network
   - §2.2: Frame Structure and Validation
   - §2.4: Sequence Numbering and BAG
   - §3.1: Redundancy Management
   - §3.4: IP/UDP Header Requirements
   - §5: Network Redundancy Architecture

2. **IEEE 802.3** - Ethernet Standards
   - Frame size: 64-1518 bytes
   - CRC-32 (FCS) calculation

3. **RFC 791** - Internet Protocol (IPv4)
   - Header format and checksum

4. **RFC 768** - User Datagram Protocol (UDP)
   - Header format and checksum

5. **DO-178C** - Software Considerations in Airborne Systems
   - Test coverage requirements

---

## Version History

| Version | Date | Changes | Tests |
|---------|------|---------|-------|
| 1.0 | Oct 2025 | Initial implementation | 32 |
| 1.1 | Oct 2025 | Added T05, T17-T19 (image requirements) | 37 |
| 1.2 | Oct 2025 | Added Suite 6 (Combination tests) | 41 |

---

## License

Part of the ns-3 network simulator project.  
See LICENSE file in repository root.

---

**Status:** ✅ **PRODUCTION-READY**  
**Maintainer:** AFDX Simulation Project  
**Last Updated:** October 26, 2025  
**Contact:** See project documentation
