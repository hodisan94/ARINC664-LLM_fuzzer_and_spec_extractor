# Model-based random baseline

A random fuzzer over the simulator's input fields. Plan and decisions:
`context/RANDOM_MODEL_PLAN.md`. It is separate from `random_baseline/` (the student's random
baseline, which draws rule labels from the test-case list and values from short fixed lists;
REVISION_FINDINGS Bugs 24, 31, 32, 33). This baseline reads no test-case or rule list and records
no rule labels.

## How a test is drawn

As Peach Fuzzer 2.x's `RandomMutationStrategy` (`Peach/MutateStrategies/rand.py`) does for a data
model with no more fields than `maxFieldsToMutate` (default 7):

1. a VL, uniformly among the 8 configured VLs;
2. a number k uniformly from 1 to 6, then k of the 6 fields uniformly without replacement;
3. for each chosen field, a value uniformly from its full range;
4. the same adapter as the model-based BOOFUZZ baseline turns them into the simulator input
   (frame sizes clamped to 18–9,000 bytes, timing floored at −BAG, sequence 0 sent as 256).

As in Peach, the generator is reseeded for every test from the seed and the test number, so test
i is the same whatever the budget or a resume.

| Field | Range |
|---|---|
| Frame size (bytes) | 0 … 65,535 |
| Timing offset (ms) | −32,768 … 32,767 |
| Sequence number | 0 … 255 |
| Source MAC change | `spoof_src`, `spoof_dst`, `broadcast`, `invalid_src`, `zero_mac` |
| Destination MAC change | `corrupt_prefix`, `wrong_vl`, `zero` |
| Drop probability | (0, 1] |

## Usage

    AFDX_NS3_PATH=<ns-3 tree> python3 random_model_baseline/main.py --seed 1 \
        --max-iterations 200 --history-path <file> --work-dir <dir> --force
    python3 -m unittest random_model_baseline/test_random_baseline.py

## Files

| File | Content |
|---|---|
| `generator.py` | The seeded draw of each test |
| `main.py` | Run loop and history (same format as the model-based BOOFUZZ baseline) |
| `test_random_baseline.py` | 8 checks: reproducibility, ranges, Peach's distribution, the multi-field adapter |
