"""Compare bug detection of the logged inputs on the submitted (v2) and the fixed simulator.

TAES revision, fix plan stage 4. The submitted results are bdr_replay_v2_*.json; the fixed
ones are bdr_replay.py outputs run with AFDX_NS3_PATH pointing at the fixed ns-3 build.

Usage (from the repository root):
  R=evaluation/results/revision
  python3 evaluation/revision/compare_bdr_replays.py $R $R/bdr_replay_fixed_llm.json \
    $R/bdr_replay_fixed_ablation.json $R/bdr_replay_fixed_baselines_original.json
No LLM API and no simulator are used.
"""
import json
import sys
from pathlib import Path
from statistics import mean

R = Path(sys.argv[1])  # evaluation/results/revision
FIXED = {p: json.loads(Path(p).read_text()) for p in sys.argv[2:]}

old = {}
for f in ("bdr_replay_v2_llm", "bdr_replay_v2_ablation", "bdr_replay_v2_baselines_original"):
    old.update({k: v for k, v in json.loads((R / f"{f}.json").read_text()).items()
                if isinstance(v, dict) and "bdr" in v})
new = {}
for d in FIXED.values():
    new.update({k: v for k, v in d.items() if isinstance(v, dict) and "bdr" in v})

bugs = list(next(iter(new.values()))["per_bug"])
short = lambda k: k.replace("evaluation/results/revision/runs/", "").replace(".jsonl", "")

print("Per campaign: bugs detected (of 8), old -> fixed; then bugs gained (+) / lost (-)")
for k in old:
    if k not in new:
        print(f"  {short(k):28s} MISSING in fixed results")
        continue
    o, n = old[k], new[k]
    gained = [b for b in bugs if n["per_bug"][b]["detected"] and not o["per_bug"][b]["detected"]]
    lost = [b for b in bugs if o["per_bug"][b]["detected"] and not n["per_bug"][b]["detected"]]
    print(f"  {short(k):28s} {o['bugs_detected']} -> {n['bugs_detected']}"
          f"  crashed {len(o['crashed_iterations'])}->{len(n['crashed_iterations'])}"
          f"  +{gained} -{lost}")

groups = {"LLM (5 runs)": [k for k in new if "llm_full_r" in k],
          "Random (5 seeds)": [k for k in new if "random_s" in k],
          "BOOFUZZ (re-run)": [k for k in new if k.endswith("boofuzz.jsonl")],
          "A0": [k for k in new if "llm_A0" in k], "A1": [k for k in new if "llm_A1" in k],
          "A2": [k for k in new if "llm_A2" in k],
          "LLM (submitted)": ["original/LLM"], "BOOFUZZ (submitted)": ["original/Boofuzz"]}
print("\nPer bug: share of campaigns detecting it, old -> fixed; mean detecting iterations old -> fixed")
for g, ks in groups.items():
    print(f"  {g}: mean bugs {mean(old[k]['bugs_detected'] for k in ks):.1f} -> "
          f"{mean(new[k]['bugs_detected'] for k in ks):.1f}")
    for b in bugs:
        od = sum(old[k]["per_bug"][b]["detected"] for k in ks)
        nd = sum(new[k]["per_bug"][b]["detected"] for k in ks)
        oi = mean(old[k]["per_bug"][b]["detecting_iterations"] for k in ks)
        ni = mean(new[k]["per_bug"][b]["detecting_iterations"] for k in ks)
        print(f"      {b:22s} {od}/{len(ks)} -> {nd}/{len(ks)}   iters {oi:6.1f} -> {ni:6.1f}")
