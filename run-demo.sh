#!/usr/bin/env bash
# run-demo.sh — one-command demo for Uwazi.
#
# The challenge brief says: "A README that gets a stranger running in
# one command." This is that command.
#
# What it does:
#   1. Creates a Python virtualenv (if missing)
#   2. Installs Uwazi + dependencies
#   3. Seeds the sample tender + 3 bids into the SQLite DB
#   4. Runs the agentic evaluation (LangGraph orchestrator)
#   5. Demonstrates the human-in-the-loop boundary (refuses an agent principal)
#   6. Starts the FastAPI review UI at http://localhost:8000
#
# Requirements:
#   - Python 3.11+
#   - Internet access for the initial pip install
#
# If you have an OPENAI_API_KEY (or Qwen via ModelScope), set it in .env
# before running. Otherwise the agent runs in STUB mode (deterministic
# canned responses for development only). A STUB run does not satisfy the
# hackathon requirement to show one full task on an open-weights model.

set -euo pipefail

cd "$(dirname "$0")"

# Colors (best-effort)
GREEN=$'\033[0;32m'
BOLD=$'\033[1m'
RESET=$'\033[0m'

echo "${BOLD}=== Uwazi — one-command demo ===${RESET}"
echo ""

# Step 1: venv
if [ ! -d ".venv" ]; then
  echo "${GREEN}[1/6]${RESET} Creating Python virtualenv..."
  python3 -m venv .venv
fi
source .venv/bin/activate

# Step 2: install
echo "${GREEN}[2/6]${RESET} Installing Uwazi + dependencies (this takes ~1 min on first run)..."
pip install -e ".[dev]" -q 2>&1 | tail -2

# Step 3: seed
echo ""
echo "${GREEN}[3/6]${RESET} Seeding sample tender + 3 bids..."
rm -f uwazi.db
python scripts/seed.py 2>&1 | grep -E "^\[|Seeded|Tender ID"

# Step 4: evaluate
echo ""
echo "${GREEN}[4/6]${RESET} Running the agentic evaluation (LangGraph orchestrator)..."
python -m uwazi.cli evaluate --tender-id makueni-water-2026 2>&1 | python -c "
import json, sys
data = json.load(sys.stdin)
if 'error' in data:
    print('  ERROR:', data['error'])
else:
    print(f\"  ✓ Report produced. {data['bids_evaluated']} bids evaluated.\")
    print(f\"  ✓ {data['criteria_extracted']} criteria extracted.\")
    print(f\"  ✓ Token cost: {data['correlation_id'][:8]} (stub={not data.get('ai_generated', False) is False and True or True})\")
    print()
    print('  Ranking:')
    for r in data['ranking']:
        print(f\"    #{r['rank']} {r['bidder_name']:20s}  score={r['weighted_score']:5.2f}  →  {r['recommendation']}\")
    print()
    print('  AI has proposed. The procurement officer must finalize.')
"

# Step 5: human-in-the-loop
echo "${GREEN}[5/6]${RESET} Demonstrating the human-in-the-loop boundary..."
echo "  Attempting to record a decision with principal_kind='agent'..."
RESULT=$(python -m uwazi.cli decide \
  --tender-id makueni-water-2026 \
  --bid-id bid-sahara \
  --decision accept \
  --rationale "agent attempt — should be refused" \
  --principal-id uwazi-agent \
  --principal-kind agent 2>&1)
if echo "$RESULT" | grep -q "human-in-the-loop"; then
  echo "  ✓ REFUSED — agents may not record decisions."
else
  echo "  ✗ UNEXPECTED: $RESULT"
fi

# Step 6: serve
echo ""
echo "${GREEN}[6/6]${RESET} Starting the procurement officer review UI..."
echo ""
echo "  ┌────────────────────────────────────────────────────────────┐"
echo "  │  Uwazi is running. Open http://localhost:8000            │"
echo "  │                                                          │"
echo "  │  Press Ctrl+C to stop.                                    │"
echo "  └────────────────────────────────────────────────────────────┘"
echo ""

exec python -m uwazi.cli serve
