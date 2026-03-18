"""
catalog_gap_analysis.py — Card catalog coverage + quality checks.

Usage:
    python -X utf8 catalog_gap_analysis.py [--sport NHL|NBA|NFL|MLB|ALL]

Checks:
  1. Summary: cards / sets / years per sport
  2. Years with zero cards (gaps in coverage)
  3. Sets with suspiciously low card counts (< 5 cards) — likely scrape failures
  4. Cards with missing player names or card numbers
  5. NEW: Missing major set families (the critical check — detects entirely absent sets)
  6. Possibly truncated major sets (brand median comparison)
"""

import os
import sys
import re
import argparse
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv()

SPORTS = ["NHL", "NBA", "NFL", "MLB"]

# Expected year ranges per sport (for gap detection)
SPORT_YEAR_RANGES = {
    "NHL": (1990, 2026),
    "NBA": (1990, 2026),
    "NFL": (1990, 2026),
    "MLB": (1990, 2026),
}

# -------------------------------------------------------------------
# ANCHOR SET FAMILIES
# For each sport, define major set families that should appear every
# year within their active range.  Each entry:
#   (label, sql_ilike_pattern, exclude_ilike_patterns, year_from, year_to)
#
# The check asks: for each year in [year_from, year_to], does the
# catalog contain at least one set whose name ILIKE the pattern AND
# does NOT ILIKE any of the exclude patterns?
# -------------------------------------------------------------------
ANCHOR_SETS = {
    "NHL": [
        # Base Upper Deck set — Series 1 or Series 2.  Exclude sub-products
        # (Artifacts, The Cup, Ice, Trilogy, etc.)
        (
            "Upper Deck (base / Series 1 or 2)",
            "%upper deck%",
            ["%artifacts%", "%the cup%", "%ice%", "%trilogy%", "%overtime%",
             "%premier%", "%collection%", "%credentials%", "%star rookies%",
             "%full force%", "%spx%", "%mvp%", "%bee hive%", "%exclusives%",
             "%portraits%", "%update%", "%clear cut%", "%retro%", "%milestone%",
             "%black diamond%", "%spectrum%", "%superstar spotlight%"],
            1990, 2026,
        ),
        (
            "O-Pee-Chee (base)",
            "%o-pee-chee%",
            ["%platinum%", "%retro%", "%premier%"],
            1990, 2026,
        ),
    ],
    "NBA": [
        (
            "Topps / Bowman (base)",
            "%topps%",
            ["%chrome%", "%finest%", "%stadium club%", "%gold label%",
             "%heritage%", "%archives%", "%bowman%"],
            1990, 2010,
        ),
        (
            "Panini Prizm",
            "%panini prizm%",
            [],
            2012, 2026,
        ),
        (
            "Hoops / NBA Hoops",
            "%hoops%",
            [],
            1990, 2026,
        ),
    ],
    "NFL": [
        (
            "Topps (base)",
            "%topps%",
            ["%chrome%", "%finest%", "%stadium club%", "%gold label%",
             "%heritage%", "%archives%", "%bowman%", "%platinum%"],
            1990, 2022,
        ),
        (
            "Panini Prizm",
            "%panini prizm%",
            [],
            2012, 2026,
        ),
        (
            "Donruss / Panini Donruss",
            "%donruss%",
            [],
            1990, 2026,
        ),
    ],
    "MLB": [
        (
            "Topps (base / Series 1 or 2)",
            "%topps%",
            ["%chrome%", "%finest%", "%stadium club%", "%gold label%",
             "%heritage%", "%archives%", "%bowman%", "%platinum%",
             "%update%", "%now%", "%gallery%"],
            1990, 2026,
        ),
        (
            "Bowman (base)",
            "%bowman%",
            ["%chrome%", "%draft%", "%platinum%", "%best%"],
            1990, 2026,
        ),
    ],
}


parser = argparse.ArgumentParser()
parser.add_argument("--sport",    default="ALL", help="Sport to analyze (or ALL)")
parser.add_argument("--markdown", action="store_true", help="Output GitHub-flavoured Markdown")
parser.add_argument("--output",   default=None, help="Write output to file instead of stdout")
parser.add_argument("--year-from", type=int, default=None, dest="year_from",
                    help="Only check from this year onwards (default: sport minimum)")
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
        print(f"\n{'=' * 70}")
        print(f"  {text}")
        print("=" * 70)

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor(cursor_factory=RealDictCursor)

target_sports = SPORTS if args.sport == "ALL" else [args.sport.upper()]

# ── 1. Summary ────────────────────────────────────────────────────────────────
h(2, "Catalog Summary")
if md:
    from datetime import datetime, timezone
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
    raw_start, end_yr = SPORT_YEAR_RANGES[sport]
    start_yr = args.year_from if args.year_from else raw_start
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
        print(f"\n  {sport} ({start_yr}–{end_yr}): {len(gaps)} missing years")
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
            print(f"    Missing: {label}" if not md else f"- Missing: {label}")
    else:
        print("    No gaps — full coverage!" if not md else "_No gaps — full coverage._")

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

# ── 4. Data quality checks ─────────────────────────────────────────────────────
h(2, "Data Quality")
checks = [
    ("Missing player names",          "player_name = '' OR player_name IS NULL"),
    ("Missing card numbers",          "card_number = '' OR card_number IS NULL"),
    ("Checklist artifacts in set_name","set_name ILIKE '%%checklist%%'"),
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

# ── 5. MISSING MAJOR SET FAMILIES ─────────────────────────────────────────────
# This is the critical check: for each year a sport is active, verify that
# expected major brands appear in the catalog.  A missing entry here means
# an entire product line was never scraped — not just sparse, but totally absent.
h(2, "Missing Major Set Families (CRITICAL)")

total_missing = 0
for sport in target_sports:
    anchors = ANCHOR_SETS.get(sport, [])
    if not anchors:
        continue

    raw_start, end_yr = SPORT_YEAR_RANGES.get(sport, (1990, 2026))
    start_yr = args.year_from if args.year_from else raw_start

    # Pull all set names for this sport in one shot (fast)
    cur.execute("""
        SELECT DISTINCT year, set_name
        FROM card_catalog
        WHERE sport = %s
          AND year ~ '^[0-9]{4}'
    """, (sport,))
    all_sets = cur.fetchall()

    # Build lookup: year_prefix (int) → list of lower-cased set names
    from collections import defaultdict
    sets_by_year = defaultdict(list)
    for row in all_sets:
        yr_prefix = int(row["year"].split("-")[0])
        sets_by_year[yr_prefix].append(row["set_name"].lower())

    sport_missing = []
    for (label, include_pat, exclude_pats, anchor_from, anchor_to) in anchors:
        check_from = max(start_yr, anchor_from)
        check_to   = min(end_yr,   anchor_to)

        inc = include_pat.replace("%", "").lower()
        excs = [p.replace("%", "").lower() for p in exclude_pats]

        for yr in range(check_from, check_to + 1):
            year_sets = sets_by_year.get(yr, [])
            # Does any set match the include pattern and none of the exclude patterns?
            found = any(
                inc in s and not any(ex in s for ex in excs)
                for s in year_sets
            )
            if not found and year_sets:
                # Only flag if we have OTHER cards for this year (proof the year was scraped)
                sport_missing.append((yr, label))

    if sport_missing:
        total_missing += len(sport_missing)
        if md:
            print(f"\n**{sport}** — ⚠️ {len(sport_missing)} missing set families\n")
            print("| Year | Missing Family |")
            print("|------|----------------|")
            for yr, label in sorted(sport_missing):
                print(f"| {yr} | {label} |")
        else:
            print(f"\n  {sport}: ⚠️  {len(sport_missing)} MISSING set families")
            for yr, label in sorted(sport_missing):
                print(f"    {yr}: MISSING — {label}")
    else:
        msg = f"\n  {sport}: ✓ All major set families present"
        print(msg if not md else f"\n**{sport}** — ✅ All major set families present")

if total_missing == 0:
    print("\n  All major set families accounted for across all sports." if not md
          else "\n✅ **All major set families accounted for.**")
else:
    print(f"\n  TOTAL: {total_missing} year/family combinations missing from catalog." if not md
          else f"\n⚠️ **Total: {total_missing} year/family combinations missing.**")

# ── 6. Possibly truncated major sets ─────────────────────────────────────────
h(2, "Possibly Truncated Sets (major brands, <30% of brand median)")

MAJOR_BRANDS = ['Topps', 'Upper Deck', 'Donruss', 'Panini', 'Bowman',
                'Fleer', 'Score', 'SkyBox', 'O-Pee-Chee', 'OPC', 'Pacific',
                'Stadium Club', 'Ultra', 'Pinnacle', 'Leaf']

for sport in target_sports:
    raw_start, _ = SPORT_YEAR_RANGES.get(sport, (1990, 2026))
    start_yr = args.year_from if args.year_from else raw_start
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
              AND SPLIT_PART(year, '-', 1)::int >= %s
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
    """, (sport, start_yr))
    rows = cur.fetchall()
    if rows:
        print(f"\n  {sport}:")
        for row in rows:
            print(f"    {row['year']:7s} | {row['card_count']:>3} cards "
                  f"(median {row['brand_median']}) | {row['brand']} — {row['set_name']}")
    else:
        print(f"\n  {sport}: no truncated major sets found")

cur.close()
conn.close()

if not md:
    print(f"\n{'=' * 70}")
    print("  Done.")
    print("=" * 70)

if args.output:
    _out.close()
    _sys.stdout = _sys.__stdout__
    print(f"Report written to {args.output}")
