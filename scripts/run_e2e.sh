#!/usr/bin/env bash
#
# AFDX End-to-End Runner Wrapper
#
# Executes the complete AI fuzzing pipeline from project root
#
# Usage:
#   bash run_e2e.sh --iters 30
#   bash run_e2e.sh --iters 50 --outdir experiments
#

set -euo pipefail

# Change to project root
cd "$(dirname "$0")"

# Source .env if exists (for OPENAI_API_KEY)
if [ -f .env ]; then
    source .env
fi

# Run E2E pipeline
python3 tools/afdx_run_e2e.py "$@"

