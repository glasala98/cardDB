"""
catalog_gap_analysis.py — Card catalog coverage + quality checks.

Usage:
    python -X utf8 catalog_gap_analysis.py [--sport NHL|NBA|NFL|MLB|ALL]

Checks:
  1. Summary: cards / sets / years per sport
  2. Years with zero cards (gaps in coverage)
  3. Sets with suspiciously low card counts (< 5 cards) — likely scrape failures
  4. Duplicate set names within the same year (possible double-scrape)
  5. Cards with missing player names or card numbers
"""

import os
import sys
import argparse
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv()

SPORTS = ["NHL", "NBA", "NFL", "MLB"]

# Expected year ranges per sport (for gap detection)
SPORT_YEAR_RANGES = {
    "NHL": (1910, 2026),
    "NBA": (1948, 2026),
    "NFL": (1935, 2026),
    "MLB": (1869, 2026),
}

parser = argparse.ArgumentParser()
parser.add_argument("--sport", default="ALL", help="Sport to analyze (or ALL)")
args = parser.parse_args()

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor(cursor_factory=RealDictCursor)

target_sports = SPORTS if args.sport == "ALL" else [args.sport.upper()]

# ── 1. Summary ────────────────────────────────────────────────────────────────
print("=" * 60)
print("CATALOG SUMMARY")
print("=" * 60)
cur.execute("""
    SELECT sport,
           COUNT(*)                    AS total_cards,
           COUNT(DISTINCT year)        AS years_covered,
           COUNT(DISTINCT set_name)    AS unique_sets,
           COUNT(DISTINCT player_name) AS unique_players
    FROM card_catalog
    WHERE sport = ANY(%s)
    GROUP BY sport
    ORDER BY sport
""", (target_sports,))
for row in cur.fetchall():
    print(f"  {row['sport']:4s} | {row['total_cards']:>8,} cards | "
          f"{row['years_covered']:>4} years | {row['unique_sets']:>6,} sets | "
          f"{row['unique_players']:>7,} players")

# ── 2. Year gaps ──────────────────────────────────────────────────────────────
for sport in target_sports:
    if sport not in SPORT_YEAR_RANGES:
        continue
    start_yr, end_yr = SPORT_YEAR_RANGES[sport]
    cur.execute("""
        SELECT DISTINCT SPLIT_PART(year, '-', 1)::int AS yr
        FROM card_catalog
        WHERE sport = %s
        AND year ~ '^[0-9]{4}'
        ORDER BY yr
    """, (sport,))
    covered = {row["yr"] for row in cur.fetchall()}
    gaps = [y for y in range(start_yr, end_yr + 1) if y not in covered]
    print(f"\n{'=' * 60}")
    print(f"{sport} YEAR GAPS ({len(gaps)} missing years out of {end_yr - start_yr + 1})")
    print("=" * 60)
    if gaps:
        # Print in ranges
        ranges, start = [], gaps[0]
        prev = gaps[0]
        for y in gaps[1:]:
            if y != prev + 1:
                ranges.append((start, prev))
                start = y
            prev = y
        ranges.append((start, prev))
        for s, e in ranges:
            label = str(s) if s == e else f"{s}–{e}"
            print(f"  Missing: {label}")
    else:
        print("  No gaps — full coverage!")

# ── 3. Thin sets (< 5 cards) ─────────────────────────────────────────────────
print(f"\n{'=' * 60}")
print("THIN SETS (< 5 cards) — possible scrape failures")
print("=" * 60)
cur.execute("""
    SELECT sport, year, set_name, COUNT(*) AS card_count
    FROM card_catalog
    WHERE sport = ANY(%s)
    GROUP BY sport, year, set_name
    HAVING COUNT(*) < 5
    ORDER BY sport, year, card_count
    LIMIT 100
""", (target_sports,))
rows = cur.fetchall()
if rows:
    for row in rows:
        print(f"  {row['sport']:4s} | {row['year']:7s} | {row['card_count']:>3} cards | {row['set_name']}")
    if len(rows) == 100:
        print("  ... (limited to 100 results)")
else:
    print("  None found.")

# ── 4. Empty player names ─────────────────────────────────────────────────────
print(f"\n{'=' * 60}")
print("CARDS WITH MISSING PLAYER NAMES")
print("=" * 60)
cur.execute("""
    SELECT sport, COUNT(*) AS cnt
    FROM card_catalog
    WHERE sport = ANY(%s)
    AND (player_name = '' OR player_name IS NULL)
    GROUP BY sport
""", (target_sports,))
rows = cur.fetchall()
if rows:
    for row in rows:
        print(f"  {row['sport']}: {row['cnt']:,} cards with no player name")
else:
    print("  None — all cards have player names.")

# ── 5. Missing card numbers ───────────────────────────────────────────────────
print(f"\n{'=' * 60}")
print("CARDS WITH MISSING CARD NUMBERS")
print("=" * 60)
cur.execute("""
    SELECT sport, COUNT(*) AS cnt
    FROM card_catalog
    WHERE sport = ANY(%s)
    AND (card_number = '' OR card_number IS NULL)
    GROUP BY sport
""", (target_sports,))
rows = cur.fetchall()
if rows:
    for row in rows:
        print(f"  {row['sport']}: {row['cnt']:,} cards with no card number")
else:
    print("  None — all cards have card numbers.")

# ── 6. Top sets by card count ─────────────────────────────────────────────────
print(f"\n{'=' * 60}")
print("TOP 10 SETS BY CARD COUNT (per sport)")
print("=" * 60)
for sport in target_sports:
    cur.execute("""
        SELECT year, set_name, COUNT(*) AS cnt
        FROM card_catalog
        WHERE sport = %s
        GROUP BY year, set_name
        ORDER BY cnt DESC
        LIMIT 10
    """, (sport,))
    rows = cur.fetchall()
    print(f"\n  {sport}:")
    for row in rows:
        print(f"    {row['year']:7s} | {row['cnt']:>5,} cards | {row['set_name']}")

cur.close()
conn.close()
print(f"\n{'=' * 60}")
print("Done.")
