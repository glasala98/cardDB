#!/usr/bin/env python3 -u
"""
Classifies every card in card_catalog into a scrape_tier:

  staple   — iconic rookie sets per sport (Young Guns, Prizm RC, Topps Chrome RC, etc.)
             These are scraped daily.
  premium  — autographs, patches, memorabilia, serialised (/print_run set)
             These are scraped weekly.
  stars    — rookie cards in major-league sets not already staple/premium
             These are scraped monthly.
  base     — everything else; scraped on-demand only.

After the initial assignment the scraper bumps cards DOWN a tier when
actual sales data is weak (e.g. a staple card with 0 sales moves to premium).
This script only does the upfront rule-based assignment.

Usage:
    python assign_catalog_tiers.py              # classify all unclassified (tier='base')
    python assign_catalog_tiers.py --all        # reclassify everything from scratch
    python assign_catalog_tiers.py --dry-run    # print counts without writing
"""

import sys, os, argparse
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, '.env'))
except ImportError:
    pass

from db import get_db

# ── Tier rules ────────────────────────────────────────────────────────────────
# Applied in order: first match wins (staple > premium > stars > base).
# Each rule is (tier, sql_where_fragment, description).
# Placeholders: %(year_from)s is the modern-era cutoff year.
# All conditions implicitly AND with "year integer >= year_from" for staple/premium/stars.

STAPLE_CONDITIONS = [
    # NHL — Young Guns are stored in variant, not set_name
    ("NHL", "variant ILIKE '%Young Guns%'",
     "NHL Young Guns (all eras)"),
    ("NHL", "set_name ILIKE '%SP Authentic%' AND variant ILIKE '%Future Watch%'",
     "NHL SP Authentic Future Watch"),

    # NBA — Prizm/Select/Mosaic/Contenders rookies
    ("NBA", "set_name ILIKE '%Prizm%' AND is_rookie = TRUE",
     "NBA Prizm Rookies"),
    ("NBA", "set_name ILIKE '%Select%' AND is_rookie = TRUE",
     "NBA Select Rookies"),
    ("NBA", "set_name ILIKE '%Mosaic%' AND is_rookie = TRUE",
     "NBA Mosaic Rookies"),
    ("NBA", "set_name ILIKE '%Contenders%' AND is_rookie = TRUE",
     "NBA Contenders Rookie Tickets"),
    ("NBA", "set_name ILIKE '%National Treasures%' AND is_rookie = TRUE",
     "NBA National Treasures Rookies"),

    # NFL — Prizm/Topps Chrome/Select/Contenders rookies
    ("NFL", "set_name ILIKE '%Prizm%' AND is_rookie = TRUE",
     "NFL Prizm Rookies"),
    ("NFL", "set_name ILIKE '%Topps Chrome%' AND is_rookie = TRUE",
     "NFL Topps Chrome Rookies"),
    ("NFL", "set_name ILIKE '%Select%' AND is_rookie = TRUE",
     "NFL Select Rookies"),
    ("NFL", "set_name ILIKE '%Contenders%' AND is_rookie = TRUE",
     "NFL Contenders Rookie Tickets"),

    # MLB — Topps Chrome / Bowman Chrome rookies
    ("MLB", "set_name ILIKE '%Topps Chrome%' AND is_rookie = TRUE",
     "MLB Topps Chrome Rookies"),
    ("MLB", "set_name ILIKE '%Bowman Chrome%' AND is_rookie = TRUE",
     "MLB Bowman Chrome Prospects/Rookies"),
    ("MLB", "set_name ILIKE '%Bowman%' AND variant ILIKE '%1st%'",
     "MLB Bowman 1st Edition"),
    ("MLB", "set_name ILIKE '%Topps%' AND variant ILIKE '%Chrome%' AND is_rookie = TRUE",
     "MLB Topps Chrome Rookie Variations"),
]

PREMIUM_CONDITIONS = [
    # Autographs — any sport, any set
    ("ALL", "variant ILIKE '%auto%'",
     "Autographs (any sport/set)"),
    ("ALL", "variant ILIKE '%autograph%'",
     "Autographs (any sport/set)"),
    # Patches / memorabilia
    ("ALL", "variant ILIKE '%patch%'",
     "Patches (any sport/set)"),
    ("ALL", "variant ILIKE '%relic%'",
     "Relics/Memorabilia (any sport/set)"),
    ("ALL", "variant ILIKE '%jersey%'",
     "Jersey cards (any sport/set)"),
    # Serialised parallels (any print run)
    ("ALL", "print_run IS NOT NULL",
     "Serialised (any /print_run)"),
    # Known premium parallel brands regardless of is_rookie
    ("NHL", "set_name ILIKE '%The Cup%'",
     "NHL The Cup"),
    ("NHL", "set_name ILIKE '%Ultimate Collection%'",
     "NHL Ultimate Collection"),
    ("NBA", "set_name ILIKE '%National Treasures%'",
     "NBA National Treasures (non-rookie)"),
    ("NBA", "set_name ILIKE '%Immaculate%'",
     "NBA Immaculate Collection"),
    ("NFL", "set_name ILIKE '%National Treasures%'",
     "NFL National Treasures"),
    ("NFL", "set_name ILIKE '%Immaculate%'",
     "NFL Immaculate Collection"),
    ("MLB", "set_name ILIKE '%Topps Finest%' AND is_rookie = TRUE",
     "MLB Topps Finest Rookies"),
    ("MLB", "set_name ILIKE '%National Treasures%'",
     "MLB National Treasures"),
]

# Stars = any major-league rookie card from a recognised brand, modern era
STARS_CONDITIONS = [
    ("ALL", "is_rookie = TRUE AND brand IN ('Upper Deck','Topps','Panini','Donruss','Fleer','O-Pee-Chee','Score','Bowman','Stadium Club')",
     "Rookies from major brands"),
]


def _year_condition(year_from: int) -> str:
    return f"(SPLIT_PART(year,'-',1) ~ '^[0-9]{{4}}$' AND SPLIT_PART(year,'-',1)::int >= {year_from})"


def classify(dry_run: bool, reclassify_all: bool, year_from: int):
    counts = {'staple': 0, 'premium': 0, 'stars': 0}

    scope = "" if reclassify_all else "AND scrape_tier = 'base'"

    with get_db() as conn:
        with conn.cursor() as cur:

            # ── Staple ──
            for sport, cond, desc in STAPLE_CONDITIONS:
                sport_cond = "" if sport == "ALL" else f"AND sport = '{sport}'"
                sql = f"""
                    UPDATE card_catalog
                    SET scrape_tier = 'staple'
                    WHERE {cond}
                      {sport_cond}
                      {scope}
                """
                if dry_run:
                    count_sql = f"SELECT COUNT(*) FROM card_catalog WHERE {cond} {sport_cond} {scope}"
                    cur.execute(count_sql)
                    n = cur.fetchone()[0]
                    if n: print(f"  [staple] {desc}: {n:,}")
                    counts['staple'] += n
                else:
                    cur.execute(sql)
                    counts['staple'] += cur.rowcount

            # ── Premium — only cards NOT already staple ──
            scope_premium = scope + " AND scrape_tier != 'staple'" if scope else "AND scrape_tier != 'staple'"
            if reclassify_all:
                scope_premium = "AND scrape_tier != 'staple'"

            for sport, cond, desc in PREMIUM_CONDITIONS:
                sport_cond = "" if sport == "ALL" else f"AND sport = '{sport}'"
                sql = f"""
                    UPDATE card_catalog
                    SET scrape_tier = 'premium'
                    WHERE {cond}
                      {sport_cond}
                      AND scrape_tier != 'staple'
                """
                if dry_run:
                    count_sql = f"SELECT COUNT(*) FROM card_catalog WHERE {cond} {sport_cond} AND scrape_tier != 'staple'"
                    cur.execute(count_sql)
                    n = cur.fetchone()[0]
                    if n: print(f"  [premium] {desc}: {n:,}")
                    counts['premium'] += n
                else:
                    cur.execute(sql)
                    counts['premium'] += cur.rowcount

            # ── Stars — rookies from major brands, not already staple/premium ──
            for sport, cond, desc in STARS_CONDITIONS:
                sport_cond = "" if sport == "ALL" else f"AND sport = '{sport}'"
                sql = f"""
                    UPDATE card_catalog
                    SET scrape_tier = 'stars'
                    WHERE {cond}
                      {sport_cond}
                      AND scrape_tier NOT IN ('staple', 'premium')
                """
                if dry_run:
                    count_sql = f"SELECT COUNT(*) FROM card_catalog WHERE {cond} {sport_cond} AND scrape_tier NOT IN ('staple','premium')"
                    cur.execute(count_sql)
                    n = cur.fetchone()[0]
                    if n: print(f"  [stars]   {desc}: {n:,}")
                    counts['stars'] += n
                else:
                    cur.execute(sql)
                    counts['stars'] += cur.rowcount

        if not dry_run:
            conn.commit()

    return counts


def main():
    parser = argparse.ArgumentParser(description="Assign scrape tiers to card_catalog")
    parser.add_argument('--all',      action='store_true', dest='reclassify_all',
                        help="Reclassify all cards (default: only unclassified base cards)")
    parser.add_argument('--dry-run',  action='store_true',
                        help="Print counts without writing")
    parser.add_argument('--year-from', type=int, default=2000, dest='year_from',
                        help="Modern era cutoff for stars tier (default: 2000)")
    args = parser.parse_args()

    print(f"{'DRY RUN — ' if args.dry_run else ''}Assigning catalog tiers (year >= {args.year_from} for stars)...")
    if args.reclassify_all:
        print("  Mode: reclassify ALL cards")
    else:
        print("  Mode: classify untiered (base) cards only")

    counts = classify(args.dry_run, args.reclassify_all, args.year_from)

    print(f"\nResults:")
    print(f"  staple:  {counts['staple']:,}")
    print(f"  premium: {counts['premium']:,}")
    print(f"  stars:   {counts['stars']:,}")
    if not args.dry_run:
        print(f"\nTier assignment written to card_catalog.scrape_tier")
        print(f"Run scrape_master_db.py --catalog-tier staple to start scraping.")


if __name__ == '__main__':
    main()
