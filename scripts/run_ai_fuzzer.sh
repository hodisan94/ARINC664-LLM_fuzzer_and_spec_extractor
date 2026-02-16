#!/bin/bash
# AI Fuzzer Agent Runner Script
# This script loads environment variables from .env and runs the AI agent

set -e

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "❌ Error: .env file not found!"
    echo "Please create .env file with your OPENAI_API_KEY"
    exit 1
fi

# Load environment variables from .env
echo "📝 Loading environment variables from .env..."
export $(grep -v '^#' .env | grep -v '^$' | xargs)

# Check if API key is set
if [ -z "$OPENAI_API_KEY" ] || [ "$OPENAI_API_KEY" = "sk-YOUR-KEY-HERE" ]; then
    echo "❌ Error: OPENAI_API_KEY not set in .env file!"
    echo "Please edit .env and add your actual OpenAI API key"
    exit 1
fi

echo "✅ Environment loaded successfully"
echo "🚀 Starting AI Fuzzer Agent..."
echo ""

# Run the AI agent
python3 tools/ai_fuzzer_agent.py

