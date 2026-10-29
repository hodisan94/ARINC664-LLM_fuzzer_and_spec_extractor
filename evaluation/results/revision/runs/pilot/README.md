# Pilot: original vs revised planner instructions

Four LLM campaigns of 100 iterations each, run on 2026-10-29 (07:56–10:01 UTC) on the fixed
simulator (`AFDX_NS3_PATH` = de-linked ns-3 copy with the stage 1–2 fixes), code at
`fix/revision-bugs` 14bf062, model gpt-5, ablation `full`.

| File | `--prompt-version` |
|---|---|
| `original_r1.jsonl`, `original_r2.jsonl` | `original` (text of the submitted campaigns) |
| `revised_r1.jsonl`, `revised_r2.jsonl` | `revised` (text describing what the simulator applies) |

Command per run:

    python3 llm_fuzzer/main.py --max-iterations 100 --prompt-version <v> --force \
      --history-path evaluation/results/revision/runs/pilot/<v>_r<n>.jsonl \
      --output-dir <tmp>/out --work-dir <tmp>/work

LLM cost: $31.03 in total at gpt-5 list prices ($7.64–7.86 per run). No simulator failures.

Scoring (no LLM calls), with the planted-bug suite as it is before stage 5:

    bdr_replay.py --max-iterations 100 --cache bdr_replay_cache_fixed.json \
      --history <file>=<file> ... --out bdr_replay_fixed_pilot.json
    analyze_campaigns.py --campaign "Original=runs/pilot/original_r*.jsonl" \
      --campaign "Revised=runs/pilot/revised_r*.jsonl" --bdr bdr_replay_fixed_pilot.json \
      --out pilot_prompt_versions_metrics.json
    replay_effects.py . bdr_replay_cache_fixed.json <name>=<file> ...

Two runs per version: this can show a large difference, not a statistically significant one
(the smallest possible Mann-Whitney p-value with 2 vs 2 runs is 0.33).
