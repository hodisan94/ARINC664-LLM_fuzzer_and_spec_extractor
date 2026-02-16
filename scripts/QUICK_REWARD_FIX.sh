#!/bin/bash
# Quick Reward Recomputation Script
# 
# Usage:
#   ./QUICK_REWARD_FIX.sh <path_to_expanded_run_directory>
#
# Example:
#   ./QUICK_REWARD_FIX.sh experiments/expanded/20251102_002656_my_test_run

set -e

if [ $# -eq 0 ]; then
    echo "❌ Error: Missing argument"
    echo ""
    echo "Usage: $0 <path_to_expanded_run_directory>"
    echo ""
    echo "Example:"
    echo "  $0 experiments/expanded/20251102_002656_my_test_run"
    echo ""
    echo "Available runs:"
    ls -1 experiments/expanded/ 2>/dev/null | head -5
    exit 1
fi

RUN_DIR="$1"

if [ ! -d "$RUN_DIR" ]; then
    echo "❌ Error: Directory not found: $RUN_DIR"
    exit 1
fi

if [ ! -f "$RUN_DIR/meta_expanded.csv" ]; then
    echo "❌ Error: meta_expanded.csv not found in $RUN_DIR"
    exit 1
fi

echo ""
echo "╔═══════════════════════════════════════════════════════════════════╗"
echo "║           🔧 QUICK REWARD RECOMPUTATION 🔧                       ║"
echo "╚═══════════════════════════════════════════════════════════════════╝"
echo ""
echo "📂 Run Directory: $RUN_DIR"
echo ""

# Step 1: Recompute rewards
echo "🧮 Step 1: Recomputing rewards..."
python3 tools/recompute_rewards.py \
    --csv "$RUN_DIR/meta_expanded.csv" \
    --outdir "$RUN_DIR/recomputed"

if [ $? -ne 0 ]; then
    echo "❌ Reward recomputation failed!"
    exit 1
fi

echo ""
echo "✅ Rewards recomputed successfully!"
echo ""

# Step 2: Generate report
echo "📊 Step 2: Generating new report..."
python3 tools/afdx_make_report.py \
    --meta "$RUN_DIR/recomputed/meta_expanded_with_rewards.csv" \
    --outdir "$RUN_DIR/recomputed/report"

if [ $? -ne 0 ]; then
    echo "❌ Report generation failed!"
    exit 1
fi

echo ""
echo "╔═══════════════════════════════════════════════════════════════════╗"
echo "║                        ✅ SUCCESS! ✅                             ║"
echo "╚═══════════════════════════════════════════════════════════════════╝"
echo ""
echo "📂 Output Files:"
echo "   • CSV:    $RUN_DIR/recomputed/meta_expanded_with_rewards.csv"
echo "   • Report: $RUN_DIR/recomputed/report/report.md"
echo "   • Plots:  $RUN_DIR/recomputed/report/*.png"
echo ""
echo "📖 Quick View Commands:"
echo "   # View report"
echo "   cat $RUN_DIR/recomputed/report/report.md | less"
echo ""
echo "   # View anomalies"
echo "   cat $RUN_DIR/recomputed/report/anomalies.json | python3 -m json.tool"
echo ""
echo "   # View reward stats"
echo "   python3 << 'EOF'"
echo "import pandas as pd"
echo "df = pd.read_csv('$RUN_DIR/recomputed/meta_expanded_with_rewards.csv')"
echo "print('Reward Stats:')"
echo "print(df['reward'].describe())"
echo "EOF"
echo ""
echo "   # Open plots (requires GUI)"
echo "   xdg-open $RUN_DIR/recomputed/report/reward_trend.png"
echo "   xdg-open $RUN_DIR/recomputed/report/heatmap_reward_vl_prob.png"
echo ""
echo "═══════════════════════════════════════════════════════════════════"

