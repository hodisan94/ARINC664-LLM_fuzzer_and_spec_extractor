#!/usr/bin/env bash
# LLM campaigns after the steering fixes F28-F29 (5 x full, A0, A1, A2) and the
# BOOFUZZ-style baseline in test-case file order, in parallel. The BOOFUZZ-style
# (category order) and Random campaigns of run_campaigns_v2.sh are unchanged.
#
# Usage: evaluation/revision/run_campaigns_v3.sh [iterations]   (default 200)
set -euo pipefail
cd "$(dirname "$0")/../.."
source venv/bin/activate

ITER="${1:-200}"
OUT=evaluation/results/revision2/runs
WORK=/tmp/afdx_campaigns_v3
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
for v in A0 A1 A2; do
  launch "llm_$v" python3 llm_fuzzer/main.py --max-iterations "$ITER" --ablation "$v" \
    --test-cases "$TC" --history-path "$OUT/llm_$v.jsonl" \
    --output-dir "$WORK/out_llm_$v" --work-dir "$WORK/wd_llm_$v"
done
launch boofuzz_file_order python3 boofuzz_baseline/main.py --max-iterations "$ITER" --order file \
  --history-path "$OUT/boofuzz_file_order.jsonl" --output-dir "$WORK/out_boofuzz_file" \
  --work-dir "$WORK/wd_boofuzz_file"
echo "progress: wc -l $OUT/*.jsonl"
