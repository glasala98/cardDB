#!/usr/bin/env bash
# =============================================================================
# CardDB Server Setup — Ubuntu 22.04 / 24.04
# Run once after provisioning. Then set DATABASE_URL in .env and run backfill.
#
# Usage:
#   chmod +x server/setup.sh
#   ./server/setup.sh
# =============================================================================
set -euo pipefail

echo "=== CardDB server setup ==="

# ── System deps ───────────────────────────────────────────────────────────────
apt-get update -q
apt-get install -y -q \
    python3.11 python3.11-venv python3-pip \
    git tmux curl wget htop \
    build-essential libssl-dev libffi-dev

# ── Venv ──────────────────────────────────────────────────────────────────────
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$REPO_ROOT/.venv"

echo "Creating virtualenv at $VENV..."
python3.11 -m venv "$VENV"
source "$VENV/bin/activate"

pip install --upgrade pip wheel
pip install -r "$REPO_ROOT/requirements.txt"

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Copy server/.env.example to .env and fill in DATABASE_URL:"
echo "        cp server/.env.example .env"
echo "        nano .env"
echo ""
echo "  2. Test DB connection:"
echo "        source .venv/bin/activate"
echo "        python -c \"from db import get_db; get_db().__enter__(); print('DB OK')\""
echo ""
echo "  3. Launch backfill:"
echo "        ./server/run_backfill.sh"
echo ""
echo "  4. Monitor in tmux:"
echo "        tmux attach -t carddb"
