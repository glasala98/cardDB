#!/usr/bin/env bash
# =============================================================================
# CardDB Backfill Launcher — external Ubuntu server
#
# Single-server mode (default):
#   ./server/run_backfill.sh
#   Runs all tiers. Workers capped by eBay's single-IP rate limit (~30-50).
#
# Multi-server mode (scales linearly with server count):
#   Server 0:  ./server/run_backfill.sh --shards 3 --this-shard 0
#   Server 1:  ./server/run_backfill.sh --shards 3 --this-shard 1
#   Server 2:  ./server/run_backfill.sh --shards 3 --this-shard 2
#   Each server gets a different IP → independent eBay rate limit.
#   3 servers × 50 workers = effective 150-worker throughput.
#
# Why sharding matters more than workers:
#   curl_cffi is I/O-bound — workers just = concurrent eBay requests.
#   eBay rate-limits per IP. One IP can sustain ~30-50 concurrent requests
#   before hitting 429s. More workers on one IP just piles up retries.
#   More IPs (shards) = actually more throughput.
#
# Recommended hardware per server:
#   2 vCPU, 4GB RAM — handles all 3 tiers at 40 workers each
#   Hetzner CX21 ~$4/month or Digital Ocean Basic ~$18/month
#
# DB connection budget (per server, all tiers running):
#   premium: 4 sports × 1 shard = 4 procs  ─┐
#   stars:   4 sports × 1 shard = 4 procs   ├─ ~22 connections peak
#   base:    3 sports × 1 shard = 3 procs  ─┘
#   GH Actions (elite+staple only):           ~20 connections
#   Railway app:                               5 connections
#   ─────────────────────────────────────────────────────────────────
#   Total per shard server: ~47 / 100 max  ✅
#   3 servers: ~47 × 3 = 141 — DISABLE GH Actions workflows while running!
#
# IMPORTANT for multi-server: disable premium/stars GH Actions first:
#   gh workflow disable "Premium Tier — Delta Scrape"
#   gh workflow disable "Stars Tier — Delta Scrape"
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$REPO_ROOT/.venv"
SESSION="carddb"

# ── Defaults ──────────────────────────────────────────────────────────────────
WORKERS=40        # workers per subprocess — eBay single-IP limit ~30-50
SHARDS=1          # total servers in the pool (1 = single-server mode)
THIS_SHARD=""     # which shard this server owns (empty = all shards)
TIERS=(premium stars base)

# ── Arg parsing ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --workers)    WORKERS="$2";    shift 2 ;;
        --shards)     SHARDS="$2";     shift 2 ;;
        --this-shard) THIS_SHARD="$2"; shift 2 ;;
        --tiers)      IFS=',' read -ra TIERS <<< "$2"; shift 2 ;;
        premium|stars|base|staple|elite) TIERS=("$1"); shift ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

SHARD_ARGS="--shards $SHARDS"
if [ -n "$THIS_SHARD" ]; then
    SHARD_ARGS="--shards $SHARDS --this-shard $THIS_SHARD"
    SHARD_LABEL="shard $THIS_SHARD of $SHARDS"
else
    SHARD_LABEL="single server (all shards)"
fi

# ── Sanity checks ──────────────────────────────────────────────────────────────
if [ ! -f "$VENV/bin/activate" ]; then
    echo "ERROR: venv not found at $VENV. Run ./server/setup.sh first."
    exit 1
fi
if [ ! -f "$REPO_ROOT/.env" ]; then
    echo "ERROR: .env not found. Copy server/.env.example to .env and set DATABASE_URL."
    exit 1
fi

source "$VENV/bin/activate"

echo "Checking DB connection..."
python3 -c "
import sys, os
sys.path.insert(0, '$REPO_ROOT')
from dotenv import load_dotenv; load_dotenv('$REPO_ROOT/.env')
from db import get_db
with get_db() as conn:
    conn.cursor().execute('SELECT 1')
print('  DB OK')
" || { echo "ERROR: DB connection failed. Check DATABASE_URL in .env"; exit 1; }

# ── tmux session ───────────────────────────────────────────────────────────────
if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo ""
    echo "tmux session '$SESSION' already exists."
    echo "  Attach:  tmux attach -t $SESSION"
    echo "  Kill it: tmux kill-session -t $SESSION"
    exit 1
fi

echo ""
echo "=== CardDB Backfill ==="
echo "  Tiers:   ${TIERS[*]}"
echo "  Workers: $WORKERS per subprocess"
echo "  Mode:    $SHARD_LABEL"
echo ""

tmux new-session -d -s "$SESSION" -n "status"

for TIER in "${TIERS[@]}"; do
    echo "  Launching $TIER..."
    tmux new-window -t "$SESSION" -n "$TIER"
    CMD="source $VENV/bin/activate && cd $REPO_ROOT && python scraping/run_tier.py $TIER --workers $WORKERS $SHARD_ARGS 2>&1 | tee -a scraping/logs/${TIER}_server.log"
    tmux send-keys -t "$SESSION:$TIER" "$CMD" Enter
done

# Status window — live coverage check every 5 min
tmux select-window -t "$SESSION:status"
tmux send-keys -t "$SESSION:status" \
    "watch -n 300 './server/status.sh'" \
    Enter

echo ""
echo "All tiers launched."
echo ""
echo "  tmux attach:    tmux attach -t $SESSION"
echo "  Switch window:  Ctrl-b <window name>  (status / premium / stars / base)"
echo "  Detach:         Ctrl-b d"
echo "  Live log:       tail -f scraping/logs/premium_NHL_0of1_raw.log"
echo "  Progress:       ./server/status.sh"
echo ""
if [ "$SHARDS" -gt 1 ]; then
    echo "Multi-server mode: this server handles shard $THIS_SHARD of $SHARDS"
    echo "Make sure other servers are configured with their --this-shard value."
fi
