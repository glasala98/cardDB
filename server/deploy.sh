#!/usr/bin/env bash
# =============================================================================
# CardDB Hetzner Deploy — run this from your Windows PC (Git Bash or WSL)
# Sets up all 4 scraper servers in one shot.
#
# Usage:
#   chmod +x server/deploy.sh
#   ./server/deploy.sh
# =============================================================================
set -euo pipefail

# ── Fill these in after creating Hetzner servers ──────────────────────────────
TAILSCALE_IP="YOUR_TAILSCALE_IP"        # your PC's Tailscale IP: tailscale ip -4
PG_PASSWORD="YOUR_POSTGRES_PASSWORD"    # same password as local PostgreSQL
SSH_KEY="$HOME/.ssh/id_ed25519"         # or id_rsa — your SSH key

SERVER_IPS=(
    "1.2.3.4"   # scraper-0  Nuremberg
    "1.2.3.5"   # scraper-1  Helsinki
    "1.2.3.6"   # scraper-2  Falkenstein
    "1.2.3.7"   # scraper-3  Ashburn
)
# ─────────────────────────────────────────────────────────────────────────────

REPO="https://github.com/glasala98/cardDB.git"
DB_URL="postgresql://postgres:${PG_PASSWORD}@${TAILSCALE_IP}:5432/carddb"
TOTAL=${#SERVER_IPS[@]}

echo ""
echo "=== CardDB Hetzner Deploy ==="
echo "  Servers:      $TOTAL"
echo "  DB target:    $TAILSCALE_IP (your PC via Tailscale)"
echo ""

for i in "${!SERVER_IPS[@]}"; do
    IP="${SERVER_IPS[$i]}"
    SHARD=$i
    echo "── Deploying scraper-$SHARD ($IP) ──────────────────────────────"

    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no root@"$IP" bash -s -- \
        "$REPO" "$DB_URL" "$SHARD" "$TOTAL" <<'REMOTE'
set -euo pipefail
REPO=$1; DB_URL=$2; SHARD=$3; TOTAL=$4

echo "[1/5] Installing system deps..."
apt-get update -q
apt-get install -y -q git python3.11 python3.11-venv python3-pip build-essential tmux curl

echo "[2/5] Installing Tailscale..."
curl -fsSL https://tailscale.com/install.sh | sh
systemctl enable tailscaled
systemctl start tailscaled
echo "  --> Run 'tailscale up' on this server and authenticate with your account"
echo "  --> Then re-run this script or manually start the backfill"

echo "[3/5] Cloning repo..."
if [ -d /root/cardDB ]; then
    cd /root/cardDB && git pull
else
    git clone "$REPO" /root/cardDB
fi
cd /root/cardDB

echo "[4/5] Setting up Python venv..."
python3.11 -m venv .venv
source .venv/bin/activate
pip install --quiet --upgrade pip wheel
pip install --quiet -r requirements.txt

echo "[5/5] Writing .env..."
cat > .env <<EOF
DATABASE_URL=$DB_URL
EOF

chmod +x server/*.sh

echo ""
echo "=== scraper-$SHARD ready ==="
echo "  After Tailscale auth, start backfill with:"
echo "    tmux new -s carddb"
echo "    source .venv/bin/activate && cd /root/cardDB"
echo "    ./server/run_backfill.sh --shards $TOTAL --this-shard $SHARD --workers 40"
echo ""
REMOTE

    echo "  scraper-$SHARD done."
    echo ""
done

echo "=== All servers deployed ==="
echo ""
echo "NEXT STEPS:"
echo ""
echo "  1. SSH into each server and run: tailscale up"
echo "     Log in with your Tailscale account on each one."
echo ""
echo "  2. On your PC, confirm all servers appear in: tailscale status"
echo ""
echo "  3. Disable GH Actions premium/stars workflows:"
echo "       gh workflow disable 'Premium Tier — Delta Scrape'"
echo "       gh workflow disable 'Stars Tier — Delta Scrape'"
echo ""
echo "  4. Start each server's backfill:"
for i in "${!SERVER_IPS[@]}"; do
    IP="${SERVER_IPS[$i]}"
    echo "       ssh root@$IP 'cd /root/cardDB && tmux new -ds carddb && tmux send-keys -t carddb \"source .venv/bin/activate && ./server/run_backfill.sh --shards $TOTAL --this-shard $i --workers 40\" Enter'"
done
echo ""
echo "  5. Monitor progress from your PC:"
echo "       ./server/status.sh"
