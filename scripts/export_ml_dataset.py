"""
ML dataset export — writes market_raw_sales + card_catalog to a CSV
suitable for training price-prediction and market-trend models.

Usage (via GH Actions):
    python export_ml_dataset.py [--out /tmp/sales_ml.csv] [--days 365] [--min-sales 3]

Output schema (one row per sale):
    sale_id, sold_date, price_val, source, is_auction,
    grade, grade_company, grade_numeric,
    serial_number, print_run,
    player_name, year, set_name, variant, sport, is_rookie,
    scrape_tier,
    days_since_sold,            # derived: days between sold_date and export date
    price_zscore_player,        # z-score of price within player's sales (outlier flag)
"""

import os, sys, csv, math, argparse
from datetime import date, timedelta
from collections import defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass

from db import get_db

TODAY = date.today()

COLUMNS = [
    "sale_id", "sold_date", "price_val", "source", "is_auction",
    "grade", "grade_company", "grade_numeric",
    "serial_number", "print_run",
    "player_name", "year", "set_name", "variant", "sport", "is_rookie",
    "scrape_tier",
    "days_since_sold", "price_zscore_player",
]


def _zscore(val, mean, std):
    if std == 0 or val is None:
        return None
    return round((val - mean) / std, 4)


def export(out_path: str, days: int, min_sales: int):
    cutoff = TODAY - timedelta(days=days)

    with get_db() as conn:
        cur = conn.cursor()
        print(f"Querying sales since {cutoff}…")
        cur.execute("""
            SELECT
                mrs.id,
                mrs.sold_date,
                mrs.price_val,
                mrs.source,
                mrs.is_auction,
                mrs.grade,
                mrs.grade_company,
                mrs.grade_numeric,
                mrs.serial_number,
                mrs.print_run,
                cc.player_name,
                cc.year,
                cc.set_name,
                cc.variant,
                cc.sport,
                cc.is_rookie,
                cc.scrape_tier
            FROM market_raw_sales mrs
            JOIN card_catalog cc ON cc.id = mrs.card_catalog_id
            WHERE mrs.sold_date >= %s
              AND mrs.price_val IS NOT NULL
              AND mrs.price_val > 0
            ORDER BY mrs.sold_date DESC
        """, [cutoff])
        rows = cur.fetchall()

    print(f"  {len(rows):,} rows fetched")

    # Build per-player price stats for z-score
    player_prices = defaultdict(list)
    for r in rows:
        if r[2]:
            player_prices[r[10]].append(float(r[2]))

    def stats(prices):
        n = len(prices)
        if n < 2:
            return 0.0, 0.0
        mean = sum(prices) / n
        std  = math.sqrt(sum((x - mean) ** 2 for x in prices) / n)
        return mean, std

    player_stats = {p: stats(v) for p, v in player_prices.items() if len(v) >= min_sales}

    written = 0
    skipped = 0
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for r in rows:
            player = r[10]
            if player not in player_stats:
                skipped += 1
                continue
            mean, std = player_stats[player]
            price = float(r[2]) if r[2] else None
            sold  = r[1]
            writer.writerow({
                "sale_id":             r[0],
                "sold_date":           sold.isoformat() if sold else "",
                "price_val":           price,
                "source":              r[3],
                "is_auction":          r[4],
                "grade":               r[5] or "",
                "grade_company":       r[6] or "",
                "grade_numeric":       float(r[7]) if r[7] else "",
                "serial_number":       r[8] or "",
                "print_run":           r[9] or "",
                "player_name":         player,
                "year":                r[11] or "",
                "set_name":            r[12] or "",
                "variant":             r[13] or "",
                "sport":               r[14] or "",
                "is_rookie":           r[15],
                "scrape_tier":         r[16] or "base",
                "days_since_sold":     (TODAY - sold).days if sold else "",
                "price_zscore_player": _zscore(price, mean, std),
            })
            written += 1

    print(f"  Written: {written:,}  Skipped (< {min_sales} sales): {skipped:,}")
    print(f"  Output:  {out_path}")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--out',       default='/tmp/sales_ml.csv')
    ap.add_argument('--days',      type=int, default=365)
    ap.add_argument('--min-sales', type=int, default=3, dest='min_sales')
    args = ap.parse_args()
    export(args.out, args.days, args.min_sales)
