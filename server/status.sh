#!/usr/bin/env bash
# Quick progress check — run from repo root or server/
# Shows coverage % by tier and recent log activity.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$REPO_ROOT/.venv"

source "$VENV/bin/activate"

python3 - <<'EOF'
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
from db import get_db

with get_db() as conn:
    cur = conn.cursor()
    cur.execute("""
        SELECT
            cc.scrape_tier,
            COUNT(DISTINCT cc.id)                                       AS total,
            COUNT(DISTINCT mp.card_catalog_id)
                FILTER (WHERE mp.fair_value IS NOT NULL)                AS priced,
            COUNT(DISTINCT mp.card_catalog_id)
                FILTER (WHERE mp.confidence = 'no_market')              AS no_market,
            MAX(mp.scraped_at)                                          AS last_scrape
        FROM card_catalog cc
        LEFT JOIN market_prices mp ON mp.card_catalog_id = cc.id
        GROUP BY cc.scrape_tier
        ORDER BY CASE cc.scrape_tier
            WHEN 'elite'   THEN 1 WHEN 'staple'  THEN 2
            WHEN 'premium' THEN 3 WHEN 'stars'   THEN 4 ELSE 5 END
    """)
    rows = cur.fetchall()

print(f"\n{'Tier':<10} {'Priced':>10} {'No-market':>10} {'Total':>10}  {'Progress':<22} {'Pct':>6}  Last scraped")
print("-" * 90)
for tier, total, priced, no_market, last_scrape in rows:
    pct  = priced / total * 100 if total else 0
    bar  = ("█" * int(pct / 10)).ljust(10, "░")
    last = last_scrape.strftime("%m-%d %H:%M") if last_scrape else "never"
    print(f"{tier:<10} {priced:>10,} {no_market:>10,} {total:>10,}  {bar}  {pct:5.1f}%  {last}")
print()
EOF

echo "Active log files:"
ls -lt "$REPO_ROOT/scraping/logs/"*.log 2>/dev/null | head -12 || echo "  (none)"
echo ""
echo "Recent activity (last 5 lines from each active log):"
for f in "$REPO_ROOT/scraping/logs/"*.log; do
    [ -f "$f" ] || continue
    # Only show logs modified in the last 10 minutes
    if [ "$(find "$f" -mmin -10 2>/dev/null)" ]; then
        echo "  ── $(basename $f) ──"
        tail -3 "$f" | sed 's/^/    /'
    fi
done
