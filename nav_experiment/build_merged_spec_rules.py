#!/usr/bin/env python3
"""Merge AFDX filtered rules with GPS (IS-GPS-200N) extraction for NAV fuzzing."""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AFDX_PATH = ROOT / "configs" / "spec_rules_filtered.json"
GPS_PATH = ROOT / "nav_experiment" / "extraction_output" / "spec_rules.json"
OUT_PATH = ROOT / "nav_experiment" / "configs" / "spec_rules.json"


def main():
    with open(AFDX_PATH) as f:
        merged = json.load(f)
    with open(GPS_PATH) as f:
        gps = json.load(f)
    if "gps_isgps200n" in merged:
        del merged["gps_isgps200n"]
    merged["gps_isgps200n"] = gps
    backup = OUT_PATH.with_suffix(".json.bak")
    if OUT_PATH.exists():
        shutil.copy2(OUT_PATH, backup)
    with open(OUT_PATH, "w") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    cats = len(merged)
    gps_rules = sum(
        len(v) if isinstance(v, dict) else 1 for v in gps.values()
    )
    print(f"Wrote {OUT_PATH}")
    print(f"  Top-level categories: {cats} (includes gps_isgps200n)")
    print(f"  GPS sub-rules (leaf strings): {gps_rules}")


if __name__ == "__main__":
    main()
