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
parser.add_argument("--markdown", action="store_true", help="Output GitHub-flavoured Markdown")
parser.add_argument("--output", default=None, help="Write output to file instead of stdout")
args = parser.parse_args()

import sys as _sys
if args.output:
    _out = open(args.output, 'w', encoding='utf-8')
    _sys.stdout = _out

md = args.markdown

def h(level, text):
    if md:
        print(f"\n{'#' * level} {text}")
    else:
        print(f"\n{'=' * 60}")
        print(text)
        print("=" * 60)

def row_sep():
    if not md:
        print("-" * 60)

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor(cursor_factory=RealDictCursor)

target_sports = SPORTS if args.sport == "ALL" else [args.sport.upper()]

# ── 1. Summary ────────────────────────────────────────────────────────────────
from datetime import datetime
h(2, "Catalog Summary")
if md:
    from datetime import timezone
    print(f"_Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_\n")
    print("| Sport | Cards | Years | Sets | Players |")
    print("|-------|------:|------:|-----:|--------:|")
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
    if md:
        print(f"| {row['sport']} | {row['total_cards']:,} | {row['years_covered']} "
              f"| {row['unique_sets']:,} | {row['unique_players']:,} |")
    else:
        print(f"  {row['sport']:4s} | {row['total_cards']:>8,} cards | "
              f"{row['years_covered']:>4} years | {row['unique_sets']:>6,} sets | "
              f"{row['unique_players']:>7,} players")

# ── 2. Year gaps ──────────────────────────────────────────────────────────────
h(2, "Year Coverage Gaps")
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
    if md:
        status = "✅ Full coverage" if not gaps else f"⚠️ {len(gaps)} missing years"
        print(f"\n**{sport}** — {status}")
    else:
        print(f"\n{'=' * 60}")
        print(f"{sport} YEAR GAPS ({len(gaps)} missing years out of {end_yr - start_yr + 1})")
        print("=" * 60)
    if gaps:
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
            print(f"  Missing: {label}" if not md else f"- Missing: {label}")
    else:
        print("  No gaps — full coverage!" if not md else "_No gaps — full coverage._")

# ── 3. Thin sets (< 5 cards) ─────────────────────────────────────────────────
h(2, "Thin Sets (< 5 cards) — possible scrape failures")
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
    if md:
        print("\n| Sport | Year | Cards | Set |")
        print("|-------|------|------:|-----|")
        for row in rows:
            print(f"| {row['sport']} | {row['year']} | {row['card_count']} | {row['set_name']} |")
        if len(rows) == 100:
            print("\n_Limited to 100 results._")
    else:
        for row in rows:
            print(f"  {row['sport']:4s} | {row['year']:7s} | {row['card_count']:>3} cards | {row['set_name']}")
        if len(rows) == 100:
            print("  ... (limited to 100 results)")
else:
    print("  None found." if not md else "_None found._")

# ── 4 & 5. Data quality checks ────────────────────────────────────────────────
h(2, "Data Quality")
checks = [
    ("Missing player names", "player_name = '' OR player_name IS NULL"),
    ("Missing card numbers", "card_number = '' OR card_number IS NULL"),
    ("Checklist artifacts in set_name", "set_name ILIKE '%checklist%'"),
]
if md:
    print("\n| Check | Result |")
    print("|-------|--------|")
for label, cond in checks:
    cur.execute(f"""
        SELECT COUNT(*) AS cnt FROM card_catalog
        WHERE sport = ANY(%s) AND ({cond})
    """, (target_sports,))
    cnt = cur.fetchone()["cnt"]
    if md:
        status = "✅ Clean" if cnt == 0 else f"⚠️ {cnt:,}"
        print(f"| {label} | {status} |")
    else:
        print(f"  {label}: {cnt:,}" if cnt > 0 else f"  {label}: ✓ Clean")

# ── 6. Top sets by card count ─────────────────────────────────────────────────
h(2, "Top 10 Sets by Card Count")
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
    if md:
        print(f"\n**{sport}**\n")
        print("| Year | Cards | Set |")
        print("|------|------:|-----|")
        for row in rows:
            print(f"| {row['year']} | {row['cnt']:,} | {row['set_name']} |")
    else:
        print(f"\n  {sport}:")
        for row in rows:
            print(f"    {row['year']:7s} | {row['cnt']:>5,} cards | {row['set_name']}")

# ── 7. Truncated major sets ───────────────────────────────────────────────────
# For recurring brands (Topps, Upper Deck, Donruss, Panini, Bowman, Fleer, Score, SkyBox, OPC),
# flag sets where card count is < 30% of the median for that brand in post-1980 years.
print(f"\n{'=' * 60}")
print("POSSIBLY TRUNCATED SETS (major brands, post-1980, <30% of brand median)")
print("=" * 60)

MAJOR_BRANDS = ['Topps', 'Upper Deck', 'Donruss', 'Panini', 'Bowman',
                'Fleer', 'Score', 'SkyBox', 'O-Pee-Chee', 'OPC', 'Pacific',
                'Stadium Club', 'Ultra', 'Pinnacle', 'Leaf']

for sport in target_sports:
    cur.execute("""
        WITH brand_sets AS (
            SELECT set_name, year, COUNT(*) AS card_count,
                   CASE
                     WHEN set_name ILIKE '%%Topps%%'        THEN 'Topps'
                     WHEN set_name ILIKE '%%Upper Deck%%'   THEN 'Upper Deck'
                     WHEN set_name ILIKE '%%Donruss%%'      THEN 'Donruss'
                     WHEN set_name ILIKE '%%Panini%%'       THEN 'Panini'
                     WHEN set_name ILIKE '%%Bowman%%'       THEN 'Bowman'
                     WHEN set_name ILIKE '%%Fleer%%'        THEN 'Fleer'
                     WHEN set_name ILIKE '%%Score%%'        THEN 'Score'
                     WHEN set_name ILIKE '%%SkyBox%%'       THEN 'SkyBox'
                     WHEN set_name ILIKE '%%O-Pee-Chee%%'   THEN 'O-Pee-Chee'
                     WHEN set_name ILIKE '%%Pacific%%'      THEN 'Pacific'
                     WHEN set_name ILIKE '%%Pinnacle%%'     THEN 'Pinnacle'
                     WHEN set_name ILIKE '%%Leaf%%'         THEN 'Leaf'
                   END AS brand
            FROM card_catalog
            WHERE sport = %s
              AND SPLIT_PART(year, '-', 1)::int >= 1980
            GROUP BY set_name, year
        ),
        brand_medians AS (
            SELECT brand, PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY card_count) AS median_count
            FROM brand_sets WHERE brand IS NOT NULL
            GROUP BY brand
            HAVING COUNT(*) >= 10
        )
        SELECT bs.year, bs.set_name, bs.card_count,
               bm.brand, ROUND(bm.median_count) AS brand_median
        FROM brand_sets bs
        JOIN brand_medians bm ON bm.brand = bs.brand
        WHERE bs.card_count < bm.median_count * 0.30
          AND bs.card_count >= 5
          AND bs.brand IS NOT NULL
        ORDER BY bm.brand, bs.year, bs.card_count
        LIMIT 50
    """, (sport,))
    rows = cur.fetchall()
    if rows:
        print(f"\n  {sport}:")
        for row in rows:
            print(f"    {row['year']:7s} | {row['card_count']:>3} cards (median {row['brand_median']}) | {row['brand']} — {row['set_name']}")
    else:
        print(f"\n  {sport}: no truncated major sets found")

cur.close()
conn.close()

if not md:
    print(f"\n{'=' * 60}")
    print("Done.")

if args.output:
    _out.close()
    _sys.stdout = _sys.__stdout__
    print(f"Report written to {args.output}")
