#!/usr/bin/env bash
set -uo pipefail
ROOT="$HOME/ns-3-reset/ns-3"
BUILD_BIN="$ROOT/build/examples/AFDX_V3/ns3-dev-afdx-demo-debug"
CONTROLLER="$ROOT/tools/ai_fuzzer_controller.py"
OUTDIR="$ROOT/experiments"
LOGS_DIR="$ROOT/logs"
MUTATIONS_PATH="$ROOT/examples/AFDX_V3/mutations.json"
META_CSV="$OUTDIR/meta.csv"
NPROC="$(nproc 2>/dev/null || echo 1)"
mkdir -p "$OUTDIR"
mkdir -p "$LOGS_DIR"
if [ ! -f "$META_CSV" ]; then
  echo "run_id,vl,probability,seed,timestamp,stdout_log,pcap_dir,csv_file,frames_received,frames_forwarded,frames_dropped,frames_dropped_invalid_vl" > "$META_CSV"
fi
PROBS=(0.01 0.05 0.1 0.2)
VLS=(1001 1002 1003 2001 2002 2003 3001 3002)
SEEDS=(1 2 3 4 5)

# Extract metrics from log file (not CSV)
extract_metrics_from_log() {
  local logfile="$1"
  if [ ! -f "$logfile" ]; then
    echo "0,0,0,0"
    return
  fi
  local rx=$(grep "afdxFramesReceived.0" "$logfile" 2>/dev/null | tail -n1 | sed -E 's/.*= *([0-9]+).*/\1/' || echo "")
  local fwd=$(grep "afdxFramesForwarded.0" "$logfile" 2>/dev/null | tail -n1 | sed -E 's/.*= *([0-9]+).*/\1/' || echo "")
  local drop=$(grep "afdxFramesDropped.0" "$logfile" 2>/dev/null | tail -n1 | sed -E 's/.*= *([0-9]+).*/\1/' || echo "")
  local dropInv=$(grep "afdxFramesDroppedInvalidVL.0" "$logfile" 2>/dev/null | tail -n1 | sed -E 's/.*= *([0-9]+).*/\1/' || echo "")
  echo "${rx:-0},${fwd:-0},${drop:-0},${dropInv:-0}"
}

for prob in "${PROBS[@]}"; do
  for vl in "${VLS[@]}"; do
    for seed in "${SEEDS[@]}"; do
      ts=$(date +%s)
      RUNID="run_vl${vl}_p${prob/_/.}_s${seed}_${ts}"
      RUN_DIR="$OUTDIR/$RUNID"
      STDOUT_LOG="$LOGS_DIR/${RUNID}.log"
      mkdir -p "$RUN_DIR"
      echo "=== START $RUNID ==="
      echo "VL=$vl PROB=$prob SEED=$seed"
      if [ -f "$CONTROLLER" ]; then
        echo "Calling controller to generate mutations.json..."
        if python3 "$CONTROLLER" --target-vl "$vl" --prob "$prob" --seed "$seed" --out "$MUTATIONS_PATH" 1>/dev/null 2>&1; then
          echo "Controller created mutations.json (with flags)."
        else
          echo "Controller did not accept flags or failed; trying without flags."
          if python3 "$CONTROLLER" 1>/dev/null 2>&1; then
            echo "Controller created mutations.json (no flags)."
          else
            echo "Controller failed; creating fallback mutations.json."
            cat > "$MUTATIONS_PATH" <<EOF
[
  {
    "vl": $vl,
    "type": "bitflip",
    "probability": $prob,
    "seed": $seed,
    "notes": "auto-generated fallback mutation entry"
  }
]
EOF
            echo "Wrote fallback $MUTATIONS_PATH"
          fi
        fi
      else
        echo "Controller not found — creating fallback mutations.json."
        cat > "$MUTATIONS_PATH" <<EOF
[
  {
    "vl": $vl,
    "type": "bitflip",
    "probability": $prob,
    "seed": $seed,
    "notes": "auto-generated fallback mutation entry"
  }
]
EOF
      fi
      rm -rf "$ROOT/examples/AFDX_V3/output" "$ROOT/examples/AFDX_V3/output/pcap" "$ROOT/examples/AFDX_V3/output/csv" || true
      mkdir -p "$ROOT/examples/AFDX_V3/output/pcap" "$ROOT/examples/AFDX_V3/output/csv" || true
      if [ ! -x "$BUILD_BIN" ]; then
        echo "Simulator binary not found or not executable: $BUILD_BIN"
        echo "${RUNID},${vl},${prob},${seed},$(date --iso-8601=seconds),MISSING_BINARY,,,0,0,0,0" >> "$META_CSV"
        continue
      fi
      echo "Running simulator..."
      (cd "$ROOT" && "./build/examples/AFDX_V3/$(basename "$BUILD_BIN")") 2>&1 | tee "$STDOUT_LOG"
      cp -r "$ROOT/examples/AFDX_V3/output" "$RUN_DIR/" || true
      CSV_PATH_CAND="$RUN_DIR/output/csv/AFDX-LOG-OUTPUT.csv"
      if [ -f "$CSV_PATH_CAND" ]; then
        CSV_FILE="$CSV_PATH_CAND"
      else
        CSV_FILE=$(find "$RUN_DIR" -type f -iname "*AFDX*.csv" | head -n1 || true)
      fi
      
      # Extract metrics from log file
      metrics=$(extract_metrics_from_log "$STDOUT_LOG")
      IFS=',' read -r framesReceived framesForwarded framesDropped framesDroppedInvalidVL <<< "$metrics"
      
      echo "${RUNID},${vl},${prob},${seed},$(date --iso-8601=seconds),${STDOUT_LOG},${RUN_DIR}/output/pcap,${CSV_FILE},${framesReceived},${framesForwarded},${framesDropped},${framesDroppedInvalidVL}" >> "$META_CSV"
      echo "=== END $RUNID (dropped=${framesDropped}, invalid_vl=${framesDroppedInvalidVL}) ==="
      echo
    done
  done
done
echo "All runs finished. Meta CSV: $META_CSV"
