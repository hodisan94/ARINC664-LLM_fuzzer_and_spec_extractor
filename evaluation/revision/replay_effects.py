"""What each logged input does on the bug-free simulator, submitted (v2) vs fixed.

TAES revision, fix plan stage 4. An input "has an effect" through a counter when that
counter differs from the clean run (no mutation) of the same simulator. Counts are over the
200 replayed iterations. Reads the replay caches only.

Usage (from the repository root):
  R=evaluation/results/revision
  python3 evaluation/revision/replay_effects.py . $R/bdr_replay_cache_fixed.json \
    LLM_r1=$R/runs/llm_full_r1.jsonl BOOFUZZ=$R/runs/boofuzz.jsonl ...
No LLM API and no simulator are used.
"""
import json
import sys
from pathlib import Path

W = Path(sys.argv[1])
sys.path.insert(0, str(W / "evaluation" / "revision"))
sys.path.insert(0, str(W))
import bdr_replay as br  # noqa: E402

old_cache = json.loads((W / "evaluation/results/revision/bdr_replay_cache_v2.json").read_text())
new_cache = json.loads(Path(sys.argv[2]).read_text())
CLEAN = br.config_key({"vlId": 1001, "prob": 0.0, "payload_delta_bytes": 0, "timing_jitter_ms": 0,
                       "mac_mutation": "none", "is_extreme_test": True,
                       "sequence_number_override": 0, "dest_mac_mutation": "none"})
COUNTERS = {"BAG policing": "frames_dropped_policing", "token bucket": "frames_dropped_token_bucket",
            "frame size": "frames_dropped_frame_error", "source MAC": "frames_dropped_mac_error",
            "ES rejection": "es_frames_rejected"}


def clean_of(cache):
    hits = [v for k, v in cache.items() if k.startswith("none|") and k.split("|", 1)[1] == CLEAN]
    return hits[0] if hits else None


campaigns = {}
for spec in sys.argv[3:]:
    name, path = spec.split("=", 1)
    campaigns[name] = br.logged_campaign(W / path, 200)

for label, cache in (("submitted", old_cache), ("fixed", new_cache)):
    clean = clean_of(cache)
    print(f"\n{label} simulator, clean run: " +
          (", ".join(f"{c}={clean.get(k, 0)}" for c, k in COUNTERS.items()) if clean else "NOT IN CACHE"))
    if not clean:
        continue
    for name, records in campaigns.items():
        counts = {c: 0 for c in COUNTERS}
        anything = 0
        for _, cfg in records:
            m = cache.get(f"none|{br.config_key(cfg)}")
            if not m or br.FAILED in m:
                continue
            hit = False
            for c, k in COUNTERS.items():
                if m.get(k, 0) != clean.get(k, 0):
                    counts[c] += 1
                    hit = True
            anything += hit
        print(f"  {name:12s} any effect {anything:3d}/{len(records)} | " +
              " ".join(f"{c} {n}" for c, n in counts.items()))
