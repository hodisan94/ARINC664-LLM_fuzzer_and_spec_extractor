# Model-based BOOFUZZ baseline

A baseline that works like the boofuzz fuzzer, adapted only as far as needed to drive the ns-3
AFDX simulator. Plan and decisions: `context/BOOFUZZ_MODEL_PLAN.md`.

It is separate from `boofuzz_baseline/`, which is a test-case sweep that does not use boofuzz
(REVISION_FINDINGS Bugs 26–37). This baseline does **not** read the test-case list or the rule
list.

## What is taken from boofuzz

- **A message model with typed fields and defaults.** The fields are the inputs the simulator
  accepts:

  | Field | boofuzz primitive | Default |
  |---|---|---|
  | Frame size (bytes) | `Word` (16-bit unsigned) | the VL's normal size |
  | Timing offset (ms) | `BitField(width=8, signed=True)` | 0 |
  | Sequence number | `Byte` (8-bit unsigned) | no change |
  | Source MAC change | `Group` of `spoof_src`, `spoof_dst`, `broadcast`, `invalid_src`, `zero_mac` | none |
  | Destination MAC change | `Group` of `corrupt_prefix`, `wrong_vl`, `zero` | none |
  | Drop probability | `Group` of 0.1, 0.5, 1.0 | 0 |

- **boofuzz's own test values.** `export_boofuzz_values.py` asks the boofuzz library (0.4.2)
  for the mutations of each field and writes them to `boofuzz_values.json`: 140 frame sizes,
  112 timing offsets, 112 sequence numbers, 5 + 3 + 3 group values. For integers these are
  0, the maximum, the maximum divided by 2, 3, 4, 8, 16, 32, and the values around each.
- **One field per test,** the others at their defaults.
- **A fixed order** and **no learning** from results.

## What is added or adapted, and why

- **The AFDX limits as the tester's own values** (decision D1): MinFrame−1, MinFrame,
  MinFrame+1, MaxFrame−1, MaxFrame, MaxFrame+1 and BAG±1 ms for each VL, and 1,517–1,519 bytes.
  boofuzz documents such additions (`fuzz_values`), but version 0.4.2 does not apply them to
  integer fields, so `model.py` adds them. They are the same VL table the LLM fuzzer receives.
- **Order** (`generator.py`): boofuzz would test all values of one field before the next, so
  200 tests would cover only small frame sizes. Here the fields take turns, and inside a field
  one value is taken from each boundary window in turn. AFDX values go to their own VL; other
  values to the next VL of the rotation.
- **Identical inputs are skipped.** The simulator clamps frames to 18–9,000 bytes and send
  intervals to at least 100 µs, so many of boofuzz's values send the same input; such tests,
  and the one that changes nothing (timing 0), are skipped. Of 442 candidate tests, 366 remain.
- **Sequence number 0 is sent as an override of 256** (the simulator keeps the low 8 bits;
  an override of 0 means "no change"; REVISION_FINDINGS Bug 31).
- **Delivery:** instead of a network connection, each test is passed to the same
  `SimulatorRunner` as the other fuzzers.

## No rule labels

Like boofuzz, this baseline mutates fields, not rules: `protocol_rule` is empty. Label-based
metrics (Rule Coverage, Executed Rule Coverage) do not apply to it. Bug detection
(`bdr_replay.py`), boundary-value coverage (`boundary_coverage.py`), distinct settings and
tests without mutation read only the simulator input and apply as to the other fuzzers.

## Usage

    # once, in an environment with boofuzz (not needed to run the baseline)
    ~/boofuzz_venv/bin/python boofuzz_model_baseline/export_boofuzz_values.py
    # run
    AFDX_NS3_PATH=<ns-3 tree> python3 boofuzz_model_baseline/main.py --max-iterations 200 \
        --history-path <file> --work-dir <dir> --force
    # checks (library comparison runs only where boofuzz is installed)
    python3 -m unittest boofuzz_model_baseline/test_model_baseline.py

## Files

| File | Content |
|---|---|
| `export_boofuzz_values.py` | Writes `boofuzz_values.json` from the boofuzz library |
| `boofuzz_values.json` | boofuzz 0.4.2's values for each field |
| `model.py` | Fields, AFDX values, boundary windows |
| `generator.py` | The fixed test list |
| `adapter.py` | One test → the simulator input |
| `main.py` | Run loop and history |
| `test_model_baseline.py` | 15 checks, including an independent re-implementation of boofuzz's integer rule and a comparison with the library |
