"""Diagnostic: identify sets in card_catalog with no or sparse raw sales coverage.

Usage:
    python diag_catalog_gaps.py [--sport NHL|NBA|NFL|MLB|ALL] [--min-sales N] [--limit N]
"""
import os
import sys
import argparse
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sport",     default="ALL")
    parser.add_argument("--min-sales", type=int, default=10, dest="min_sales")
    parser.add_argument("--limit",     type=int, default=100)
    args = parser.parse_args()

    conn = psycopg2.connect(DATABASE_URL)
    cur  = conn.cursor()

    sport_filter = "" if args.sport == "ALL" else f"AND cc.sport = '{args.sport.upper()}'"

    # Cards per set
    cur.execute(f"""
        SELECT
            cc.sport,
            cc.year,
            cc.set_name,
            COUNT(*)                    AS total_cards,
            COUNT(DISTINCT cc.player_name) AS unique_players,
            COUNT(mrs.id)               AS raw_sales
        FROM card_catalog cc
        LEFT JOIN market_raw_sales mrs ON mrs.card_catalog_id = cc.id
        WHERE 1=1 {sport_filter}
        GROUP BY cc.sport, cc.year, cc.set_name
        ORDER BY cc.year DESC, cc.sport, cc.set_name
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    total_sets   = len(rows)
    zero_sales   = [r for r in rows if r[5] == 0]
    sparse       = [r for r in rows if 0 < r[5] < args.min_sales]
    covered      = [r for r in rows if r[5] >= args.min_sales]

    print(f"\n{'='*70}")
    print(f"  CATALOG DATA GAPS REPORT  (sport={args.sport}, sparse_threshold={args.min_sales})")
    print(f"{'='*70}")
    print(f"  Total sets in catalog : {total_sets:,}")
    print(f"  Well covered (≥{args.min_sales} sales): {len(covered):,}")
    print(f"  Sparse (1–{args.min_sales-1} sales)  : {len(sparse):,}")
    print(f"  Zero sales            : {len(zero_sales):,}")
    print()

    # By sport breakdown
    from collections import Counter
    sport_zero = Counter(r[0] for r in zero_sales)
    if sport_zero:
        print("  Zero-sales sets by sport:")
        for sp, cnt in sorted(sport_zero.items()):
            print(f"    {sp:<8} {cnt:,}")
        print()

    # Zero-sales list
    if zero_sales:
        print(f"  SETS WITH ZERO SALES (showing up to {args.limit}):")
        print(f"  {'Sport':<6} {'Year':<10} {'Cards':>6} {'Players':>8}  Set Name")
        print(f"  {'-'*6} {'-'*10} {'-'*6} {'-'*8}  {'-'*40}")
        for r in zero_sales[:args.limit]:
            sport_val, year, set_name, cards, players, _ = r
            print(f"  {sport_val or '?':<6} {year or '?':<10} {cards:>6} {players:>8}  {set_name}")
        if len(zero_sales) > args.limit:
            print(f"  ... and {len(zero_sales) - args.limit} more")
        print()

    if sparse:
        print(f"  SPARSE SETS (<{args.min_sales} sales, showing up to {args.limit}):")
        print(f"  {'Sport':<6} {'Year':<10} {'Sales':>6} {'Cards':>6}  Set Name")
        print(f"  {'-'*6} {'-'*10} {'-'*6} {'-'*6}  {'-'*40}")
        for r in sparse[:args.limit]:
            sport_val, year, set_name, cards, players, sales = r
            print(f"  {sport_val or '?':<6} {year or '?':<10} {sales:>6} {cards:>6}  {set_name}")
        if len(sparse) > args.limit:
            print(f"  ... and {len(sparse) - args.limit} more")

    print(f"\n{'='*70}\n")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
