#!/usr/bin/env bash
# =============================================================================
# CardDB Backfill Launcher — run on external Ubuntu server
#
# Launches one tmux window per tier. Each tier runs all its sports in parallel
# subprocesses (one per sport × shard) with no time limit.
#
# DB connection budget:
#   premium: 4 sports × 1 shard = 4 procs
#   stars:   4 sports × 1 shard = 4 procs
#   base:    3 sports × 1 shard = 3 procs
#   ─────────────────────────────────────
#   Total:   11 procs × ~2 avg DB conns  ≈ 22 server connections
#   GH Actions (elite+staple only): ~20 connections
#   App (Railway):                   5 connections
#   ─────────────────────────────────────────────────────────────
#   Peak total:  ~47 / 100 max  ✅
#
# IMPORTANT: Before running, disable the premium/stars GH Actions workflows
# to avoid double-scraping and connection budget overflow:
#   gh workflow disable "Premium Tier — Delta Scrape"
#   gh workflow disable "Stars Tier — Delta Scrape"
# Re-enable after backfill completes:
#   gh workflow enable  "Premium Tier — Delta Scrape"
#   gh workflow enable  "Stars Tier — Delta Scrape"
#
# Usage:
#   ./server/run_backfill.sh            # all tiers
#   ./server/run_backfill.sh premium    # single tier
#   ./server/run_backfill.sh stars base # specific tiers
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$REPO_ROOT/.venv"
RUNNER="$REPO_ROOT/scraping/run_tier.py"
SESSION="carddb"

# Workers per subprocess. curl_cffi is I/O-bound so high counts are safe.
# Tune down if you see eBay 429s in the logs.
WORKERS=25

# Shards per sport. 1 is fine on a server — just use more workers instead.
SHARDS=1

# Which tiers to run (default: all backfill tiers; skip elite/staple since GH Actions handles those)
TIERS=("${@:-premium stars base}")
if [ $# -gt 0 ]; then
    TIERS=("$@")
else
    TIERS=(premium stars base)
fi

# ── Sanity checks ──────────────────────────────────────────────────────────────
if [ ! -f "$VENV/bin/activate" ]; then
    echo "ERROR: venv not found at $VENV. Run server/setup.sh first."
    exit 1
fi

if [ ! -f "$REPO_ROOT/.env" ]; then
    echo "ERROR: .env not found. Copy server/.env.example to .env and set DATABASE_URL."
    exit 1
fi

source "$VENV/bin/activate"

# Quick DB connectivity check before launching 11 processes
python3 -c "
import sys, os
sys.path.insert(0, '$REPO_ROOT')
from dotenv import load_dotenv; load_dotenv('$REPO_ROOT/.env')
from db import get_db
with get_db() as conn:
    conn.cursor().execute('SELECT 1')
print('DB connection OK')
" || { echo "ERROR: DB connection failed. Check DATABASE_URL in .env"; exit 1; }

# ── tmux session ───────────────────────────────────────────────────────────────
if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "tmux session '$SESSION' already exists."
    echo "Attach with:  tmux attach -t $SESSION"
    echo "Or kill it:   tmux kill-session -t $SESSION"
    exit 1
fi

tmux new-session -d -s "$SESSION" -n "monitor"

echo ""
echo "Launching tiers: ${TIERS[*]}"
echo "  Workers per subprocess : $WORKERS"
echo "  Shards per sport       : $SHARDS"
echo ""

for TIER in "${TIERS[@]}"; do
    echo "  Starting $TIER..."
    tmux new-window -t "$SESSION" -n "$TIER"
    tmux send-keys -t "$SESSION:$TIER" \
        "source $VENV/bin/activate && cd $REPO_ROOT && python scraping/run_tier.py $TIER --workers $WORKERS --shards $SHARDS" \
        Enter
done

# Set up monitor window with a live tail of all logs
tmux select-window -t "$SESSION:monitor"
tmux send-keys -t "$SESSION:monitor" \
    "watch -n 30 'tail -n 5 scraping/logs/*.log 2>/dev/null | grep -E \"Found|Stamped|Error|done|SUMMARY\" | tail -40'" \
    Enter

echo ""
echo "All tiers launched in tmux session '$SESSION'."
echo ""
echo "  Attach:        tmux attach -t $SESSION"
echo "  Switch window: Ctrl-b then window name (e.g. premium, stars, base)"
echo "  Detach:        Ctrl-b then d"
echo "  Live logs:     tail -f scraping/logs/<tier>_<sport>_0of1_raw.log"
echo ""
echo "Check progress any time:"
echo "  ./server/status.sh"
