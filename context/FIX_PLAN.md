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
| 1 | In progress |
| 2–8 | Not started |
