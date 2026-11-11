#!/usr/bin/env bash
# All campaigns of the second re-run (after the code fixes of 2026-11-09), in parallel.
# 5 x LLM full, A0, A1, A2 (GPT-5, about US$16 per full run), BOOFUZZ-style x 1, Random seeds 1-5.
# Each campaign runs in its own simulator working directory. Logs: $OUT/logs/.
#
# Usage: evaluation/revision/run_campaigns_v2.sh [iterations]   (default 200)
set -euo pipefail
cd "$(dirname "$0")/../.."
source venv/bin/activate

ITER="${1:-200}"
OUT=evaluation/results/revision2/runs
WORK=/tmp/afdx_campaigns_v2
TC=configs/test_cases.json
mkdir -p "$OUT/logs" "$WORK"

python3 evaluation/revision/sanity_checks.py --jobs 8 > "$OUT/logs/sanity_checks.log" 2>&1 \
  || { echo "sanity checks failed, see $OUT/logs/sanity_checks.log"; exit 1; }

launch() {  # name, command...
  local name="$1"; shift
  [ -s "$OUT/$name.jsonl" ] && { echo "skip $name (history exists; use --resume manually)"; return; }
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
launch boofuzz python3 boofuzz_baseline/main.py --max-iterations "$ITER" \
  --history-path "$OUT/boofuzz.jsonl" --output-dir "$WORK/out_boofuzz" --work-dir "$WORK/wd_boofuzz"
for s in 1 2 3 4 5; do
  launch "random_s$s" python3 random_baseline/main.py --max-iterations "$ITER" --seed "$s" \
    --history-path "$OUT/random_s$s.jsonl" --output-dir "$WORK/out_random_s$s" --work-dir "$WORK/wd_random_s$s"
done
echo "progress: wc -l $OUT/*.jsonl"
