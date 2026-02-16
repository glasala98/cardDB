#!/bin/bash
# run_all_scrapes.sh — Run all scraping jobs in sequence
#
# Usage:
#   bash run_all_scrapes.sh                  # Daily: raw prices + NHL stats
#   bash run_all_scrapes.sh --graded         # Include graded price scraping
#   bash run_all_scrapes.sh --bios           # Include player bio fetching
#   bash run_all_scrapes.sh --graded --bios  # Full weekly run
#
# Crontab setup (add with: crontab -e):
#   # Daily at 6:00 AM UTC: raw prices + NHL stats
#   0 6 * * * cd /opt/card-dashboard && bash run_all_scrapes.sh >> /var/log/card-scrape.log 2>&1
#
#   # Weekly Sunday 7:00 AM UTC: graded + bios
#   0 7 * * 0 cd /opt/card-dashboard && bash run_all_scrapes.sh --graded --bios >> /var/log/card-scrape.log 2>&1

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate venv if it exists
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
elif [ -f "/opt/card-dashboard/venv/bin/activate" ]; then
    source /opt/card-dashboard/venv/bin/activate
fi

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
echo ""
echo "=========================================="
echo "SCRAPE RUN: $TIMESTAMP"
echo "=========================================="

# Step 1: Raw price scrape (daily)
echo ""
echo "--- Step 1: Raw price scrape ---"
python3 scrape_master_db.py 2>&1 || echo "WARNING: Raw scrape had errors"

# Step 2: NHL stats scrape (daily)
echo ""
echo "--- Step 2: NHL player stats ---"
STATS_FLAGS=""
if [[ "$*" == *"--bios"* ]]; then
    STATS_FLAGS="--fetch-bios"
fi
python3 scrape_nhl_stats.py $STATS_FLAGS 2>&1 || echo "WARNING: NHL stats scrape had errors"

# Step 3: Graded scrape (only if --graded flag passed)
if [[ "$*" == *"--graded"* ]]; then
    echo ""
    echo "--- Step 3: Graded price scrape ---"
    python3 scrape_master_db.py --graded 2>&1 || echo "WARNING: Graded scrape had errors"
fi

echo ""
echo "=========================================="
echo "SCRAPE COMPLETE: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="
