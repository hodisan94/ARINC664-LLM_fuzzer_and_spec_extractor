# Stage 7: full campaigns on the fixed simulator

Fourteen campaigns of 200 iterations each, code at `fix/revision-bugs` c348e53, fixed simulator
(`AFDX_NS3_PATH` = de-linked ns-3 copy with the stage 1–2 fixes and the 10-bug suite), test
cases `configs/test_cases_rules_2026-10.json` (626 rules), model gpt-5.

| Files | Fuzzer | Settings |
|---|---|---|
| `llm_full_r1..r5.jsonl` | LLM | `--ablation full --prompt-version neutral` |
| `llm_A0.jsonl`, `llm_A1.jsonl`, `llm_A2.jsonl` | LLM ablations | `--ablation A0/A1/A2 --prompt-version neutral` |
| `random_s1..s5.jsonl` | Random | `--seed 1..5` |
| `boofuzz.jsonl` | BOOFUZZ | default schedule |

Command per run (all with `--max-iterations 200 --test-cases configs/test_cases_rules_2026-10.json`):

    python3 llm_fuzzer/main.py --prompt-version neutral --ablation <mode> --force \
      --history-path <file> --output-dir <tmp>/out --work-dir <tmp>/work
    python3 random_baseline/main.py --seed <s> --history-path <file> ...
    python3 boofuzz_baseline/main.py --history-path <file> ...

## Interruption and resume

All 14 runs started on 2026-10-30 15:04 UTC. The baselines finished at 200 iterations. At about
16:08 UTC the OpenAI project reached its configured spend limit, every call returned
`project_spend_limit_exceeded`, and each LLM run stopped after 5 consecutive failed iterations
(the harness's own stop rule), at iterations 65–135.

- The 40 failed records (5 per LLM run, all at the end of the run, all
  `project_spend_limit_exceeded`) were removed and are kept in `spend_limit_records_removed.jsonl`.
  Before the first of them, no call in any run had failed.
- After the limit was raised, the 8 LLM runs were resumed with `--resume` and the same settings
  (2026-10-31 20:58–22:10 UTC, same commit). The planner keeps no state between iterations other
  than the history file, so a resumed run continues as an uninterrupted one would.
- Checked: each final history starts with exactly the records kept before the resume, the
  iterations are 0–199 without gaps, and the feedback/steering flags are the same before and
  after the resume.

Result: 14 × 200 iterations; 1 BOOFUZZ simulator failure, none in the other runs; no simulator
crash in the replay. LLM cost $106.60 at gpt-5 list prices (full runs $15.90–16.52, A0 $4.82,
A1 $6.49, A2 $14.28).

## Scoring (no LLM calls)

    bdr_replay.py --workers 8 --cache bdr_replay_cache_stage7.json \
      --history <file>=<file> ... --out bdr_replay_stage7.json
    analyze_campaigns.py --campaign "AI=runs/stage7/llm_full_r*.jsonl" \
      --campaign "Random=runs/stage7/random_s*.jsonl" --campaign "BOOFUZZ=runs/stage7/boofuzz.jsonl" \
      --campaign "A0=..." --campaign "A1=..." --campaign "A2=..." \
      --bdr bdr_replay_stage7.json --unique AI,Random,BOOFUZZ --out campaign_metrics_stage7.json

The cache started from `bdr_replay_cache_stage5.json`.

Note: `analyze_campaigns.py` still computes its "shared" universe from the old
`configs/test_cases.json`; with the new test cases that measure no longer describes what the
baselines can reach and should not be used for these runs.
