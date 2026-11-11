#!/usr/bin/env bash
# LLM campaigns that use steering (5 x full, A1) after fixes F31-F32 (global category
# check, predefined-test-case fallback when the LLM declines a redirect, rule-to-category
# map of the baseline and the metric), in parallel.
# A0 and A2 do not steer and are unchanged; baselines are unchanged.
#
# Usage: evaluation/revision/run_campaigns_v4.sh [iterations]   (default 200)
set -euo pipefail
cd "$(dirname "$0")/../.."
source venv/bin/activate

ITER="${1:-200}"
OUT=evaluation/results/revision2/runs
WORK=/tmp/afdx_campaigns_v4
TC=configs/test_cases.json
mkdir -p "$OUT/logs" "$WORK"

launch() {  # name, command...
  local name="$1"; shift
  [ -s "$OUT/$name.jsonl" ] && { echo "skip $name (history exists)"; return; }
  nohup "$@" > "$OUT/logs/$name.log" 2>&1 &
  echo "started $name (pid $!)"
}

for r in 1 2 3 4 5; do
  launch "llm_full_r$r" python3 llm_fuzzer/main.py --max-iterations "$ITER" --ablation full \
    --test-cases "$TC" --history-path "$OUT/llm_full_r$r.jsonl" \
    --output-dir "$WORK/out_llm_full_r$r" --work-dir "$WORK/wd_llm_full_r$r"
done
launch llm_A1 python3 llm_fuzzer/main.py --max-iterations "$ITER" --ablation A1 \
  --test-cases "$TC" --history-path "$OUT/llm_A1.jsonl" \
  --output-dir "$WORK/out_llm_A1" --work-dir "$WORK/wd_llm_A1"
echo "progress: wc -l $OUT/*.jsonl"
