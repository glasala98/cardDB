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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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

    # MLB — Topps chrome and flagship rookies
    ("MLB", "set_name ILIKE '%Topps Chrome%' AND is_rookie = TRUE",
     "MLB Topps Chrome Rookies"),
    ("MLB", "set_name ILIKE '%Topps%' AND variant ILIKE '%Chrome%' AND is_rookie = TRUE",
     "MLB Topps Chrome Rookie Variations"),
    # Topps Update Series — many iconic RCs (Trout 2011, etc.)
    ("MLB", "set_name ILIKE '%Topps Update%' AND is_rookie = TRUE",
     "MLB Topps Update Series Rookies"),
    # Topps Series 1 & 2 (includes 1st Edition variants like "2022 Topps Series 1 Baseball 1st Edition")
    ("MLB", "set_name ILIKE '%Topps Series%' AND is_rookie = TRUE",
     "MLB Topps Series 1/2 Rookies"),
    # Topps flagship base set RCs ("2022 Topps", "2022 Topps Baseball")
    ("MLB", "set_name ~ '^[0-9]{4} Topps( Baseball)?$' AND is_rookie = TRUE",
     "MLB Topps Flagship Rookies"),
    # Topps Heritage — vintage-style, widely collected
    ("MLB", "set_name ILIKE '%Topps Heritage%' AND is_rookie = TRUE",
     "MLB Topps Heritage Rookies"),

    # MLB — Bowman rookies and prospects
    ("MLB", "set_name ILIKE '%Bowman Chrome%' AND is_rookie = TRUE",
     "MLB Bowman Chrome Prospects/Rookies"),
    # Bowman 1st Edition / Bowman Draft 1st Edition — most valuable prospect cards.
    # '1st' is in the set_name (e.g. '2022 Bowman Draft 1st Edition Baseball'),
    # NOT in variant — previous rule was checking the wrong column.
    ("MLB", "set_name ILIKE '%Bowman%' AND set_name ILIKE '%1st%'",
     "MLB Bowman 1st Edition / Draft 1st Edition"),
    # All other Bowman rookies (Bowman base prospects)
    ("MLB", "set_name ILIKE '%Bowman%' AND is_rookie = TRUE",
     "MLB Bowman Rookies"),

    # MLB — Panini brands (parallel to NBA/NFL staple structure)
    ("MLB", "set_name ILIKE '%Prizm%' AND is_rookie = TRUE",
     "MLB Prizm Rookies"),
    ("MLB", "set_name ILIKE '%Select%' AND is_rookie = TRUE",
     "MLB Select Rookies"),
    ("MLB", "set_name ILIKE '%Mosaic%' AND is_rookie = TRUE",
     "MLB Mosaic Rookies"),
    ("MLB", "set_name ILIKE '%Contenders%' AND is_rookie = TRUE",
     "MLB Contenders Rookies"),
    ("MLB", "set_name ILIKE '%Donruss Optic%' AND is_rookie = TRUE",
     "MLB Donruss Optic Rookies"),
]

PREMIUM_CONDITIONS = [
    # Autographs — any sport, any set
    ("ALL", "variant ILIKE '%auto%'",
     "Autographs (any sport/set)"),
    ("ALL", "variant ILIKE '%autograph%'",
     "Autographs (any sport/set)"),
    ("ALL", "variant ILIKE '%signature%'",
     "Signatures (any sport/set)"),
    ("ALL", "variant ILIKE '%signed%'",
     "Signed cards (any sport/set)"),
    ("ALL", "variant ILIKE '%RPA%'",
     "Rookie Patch Autos (any sport/set)"),
    # Patches / memorabilia
    ("ALL", "variant ILIKE '%patch%'",
     "Patches (any sport/set)"),
    ("ALL", "variant ILIKE '%relic%'",
     "Relics/Memorabilia (any sport/set)"),
    ("ALL", "variant ILIKE '%jersey%'",
     "Jersey cards (any sport/set)"),
    ("ALL", "variant ILIKE '%game used%'",
     "Game-used memorabilia (any sport/set)"),
    ("ALL", "variant ILIKE '% GU %' OR variant ILIKE '%-GU%'",
     "GU memorabilia (any sport/set)"),
    ("ALL", "variant ILIKE '%logoman%'",
     "Logoman 1/1 (any sport/set)"),
    ("ALL", "variant ILIKE '%booklet%'",
     "Booklets (any sport/set)"),
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

# Stars = rookie cards from recognised brands, modern era only (1990+).
# Pre-1990 vintage cards are left as 'base' — they trade sporadically and
# don't benefit from monthly scraping cycles.
STARS_CONDITIONS = [
    ("ALL", "is_rookie = TRUE AND brand IN ('Upper Deck','Topps','Panini','Donruss','Fleer','O-Pee-Chee','Score','Bowman','Stadium Club','Leaf','Pacific','Press Pass','SP')",
     "Rookies from major brands (1990+)"),
]

# Year floor applied to stars (but not staple — staple sets like Young Guns
# are valuable across all eras and handled by explicit rules above).
STARS_YEAR_FROM = 1990


def _year_condition(year_from: int) -> str:
    return f"(SPLIT_PART(year,'-',1) ~ '^[0-9]{{4}}$' AND SPLIT_PART(year,'-',1)::int >= {year_from})"


def classify(dry_run: bool, reclassify_all: bool, year_from: int):
    counts = {'staple': 0, 'premium': 0, 'stars': 0}

    scope = "" if reclassify_all else "AND scrape_tier = 'base'"

    with get_db() as conn:
        with conn.cursor() as cur:
            # Disable the per-row scoring trigger — it fires on every UPDATE row
            # and does a players SELECT, causing deadlocks on bulk classify runs.
            cur.execute("ALTER TABLE card_catalog DISABLE TRIGGER trg_score_on_insert")

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

            # ── Stars — rookies from major brands, 1990+, not already staple/premium ──
            year_cond = _year_condition(STARS_YEAR_FROM)
            for sport, cond, desc in STARS_CONDITIONS:
                sport_cond = "" if sport == "ALL" else f"AND sport = '{sport}'"
                sql = f"""
                    UPDATE card_catalog
                    SET scrape_tier = 'stars'
                    WHERE {cond}
                      AND {year_cond}
                      {sport_cond}
                      AND scrape_tier NOT IN ('staple', 'premium')
                """
                if dry_run:
                    count_sql = f"SELECT COUNT(*) FROM card_catalog WHERE {cond} AND {year_cond} {sport_cond} AND scrape_tier NOT IN ('staple','premium')"
                    cur.execute(count_sql)
                    n = cur.fetchone()[0]
                    if n: print(f"  [stars]   {desc}: {n:,}")
                    counts['stars'] += n
                else:
                    cur.execute(sql)
                    counts['stars'] += cur.rowcount

        if not dry_run:
            cur.execute("ALTER TABLE card_catalog ENABLE TRIGGER trg_score_on_insert")
            conn.commit()

    return counts


def score_all_cards():
    """
    Batch-score every card in card_catalog using fn_score_card() (installed by
    migrate_volatility_scoring.py).  Called after the migration + player seed to
    backfill scores on existing rows — new inserts are handled automatically by
    the DB trigger.

    Runs in batches of 10,000 to avoid long-running transactions.
    """
    print("Scoring all cards via volatility scoring system...")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM card_catalog")
            total = cur.fetchone()[0]
            print(f"  Total cards: {total:,}")

            # Disable the per-row scoring trigger during the batch update.
            # The trigger fires on every UPDATE row and does a players lookup,
            # which creates row-lock contention with the app's connections and
            # can deadlock on a 3.6M-row table.  We're computing the same scores
            # manually below, so the trigger would be redundant and harmful here.
            cur.execute("ALTER TABLE card_catalog DISABLE TRIGGER trg_score_on_insert")

            # Batch UPDATE using the same logic as the trigger (avoids 2M fn calls)
            cur.execute("""
                UPDATE card_catalog cc
                SET
                    player_score = COALESCE((
                        SELECT CASE p.player_tier
                            WHEN 'S' THEN 50 WHEN 'A' THEN 30 WHEN 'B' THEN 10 ELSE 0
                        END
                        FROM players p
                        WHERE LOWER(p.player_name) = LOWER(cc.player_name)
                          AND (p.sport = cc.sport OR p.sport = 'ALL')
                        ORDER BY p.player_tier
                        LIMIT 1
                    ), 0),
                    attr_score = CASE
                        WHEN cc.print_run = 1 THEN 50
                        WHEN cc.variant ILIKE '%logoman%' THEN 50
                        WHEN cc.is_rookie
                             AND (cc.variant ILIKE '%auto%' OR cc.variant ILIKE '%rpa%')
                             AND cc.variant ILIKE '%patch%' THEN 50
                        WHEN cc.print_run IS NOT NULL AND cc.print_run <= 99 THEN 30
                        WHEN cc.variant ILIKE '%auto%'
                          OR cc.variant ILIKE '%autograph%'
                          OR cc.variant ILIKE '%rpa%'
                          OR cc.variant ILIKE '%patch%'
                          OR cc.variant ILIKE '%relic%'
                          OR cc.variant ILIKE '%jersey%'
                          OR cc.variant ILIKE '%signature%'
                          OR cc.variant ILIKE '%signed%'
                          OR cc.variant ILIKE '%booklet%' THEN 30
                        WHEN cc.print_run IS NOT NULL AND cc.print_run <= 499 THEN 10
                        WHEN cc.is_rookie   THEN 10
                        WHEN cc.is_parallel THEN 10
                        ELSE 0
                    END,
                    set_score = CASE
                        WHEN cc.set_name ILIKE '%National Treasures%'
                          OR cc.set_name ILIKE '%Flawless%'
                          OR cc.set_name ILIKE '%Prizm%'
                          OR cc.set_name ILIKE '%Topps Chrome%'
                          OR cc.set_name ILIKE '%Bowman Chrome%'
                          OR cc.set_name ILIKE '%Topps Chrome Black%'
                          OR cc.variant  ILIKE '%Young Guns%'
                          OR cc.set_name ILIKE '%The Cup%'
                          OR cc.set_name ILIKE '%Ultimate Collection%'
                          OR cc.set_name ILIKE '%Immaculate%'
                          OR cc.set_name ILIKE '%SP Authentic%' THEN 20
                        WHEN cc.set_name ILIKE '%Select%'
                          OR cc.set_name ILIKE '%Mosaic%'
                          OR cc.set_name ILIKE '%Optic%'
                          OR cc.set_name ILIKE '%Contenders%'
                          OR cc.set_name ILIKE '%Bowman Draft%'
                          OR cc.set_name ILIKE '%Bowman 1st%'
                          OR cc.set_name ILIKE '%Bowman%'
                          OR cc.set_name ILIKE '%Topps Update%'
                          OR cc.set_name ILIKE '%Topps Series%'
                          OR cc.set_name ILIKE '%Topps Finest%'
                          OR cc.set_name ILIKE '%Stadium Club%'
                          OR cc.set_name ILIKE '%Heritage%'
                          OR cc.set_name ILIKE '%Donruss Optic%' THEN 10
                        ELSE 0
                    END
            """)
            print(f"  Scores updated: {cur.rowcount:,} cards")

            # Derive volatility_score and scrape_tier from the three components
            cur.execute("""
                UPDATE card_catalog
                SET volatility_score = player_score + attr_score + set_score,
                    scrape_tier = CASE
                        WHEN (player_score + attr_score + set_score) >= 100 THEN 'elite'
                        WHEN (player_score + attr_score + set_score) >= 70  THEN 'staple'
                        WHEN (player_score + attr_score + set_score) >= 40  THEN 'premium'
                        WHEN (player_score + attr_score + set_score) >= 10  THEN 'stars'
                        ELSE 'base'
                    END
            """)
            print(f"  Tiers assigned: {cur.rowcount:,} cards")

            # Re-enable trigger now that batch scoring is done
            cur.execute("ALTER TABLE card_catalog ENABLE TRIGGER trg_score_on_insert")

            # Print distribution
            cur.execute("""
                SELECT scrape_tier, COUNT(*) FROM card_catalog
                GROUP BY scrape_tier ORDER BY scrape_tier
            """)
            print("\n  Tier distribution:")
            for tier, count in cur.fetchall():
                print(f"    {tier:<10} {count:>10,}")

        conn.commit()


def main():
    parser = argparse.ArgumentParser(description="Assign scrape tiers to card_catalog")
    parser.add_argument('--all',      action='store_true', dest='reclassify_all',
                        help="Reclassify all cards (default: only unclassified base cards)")
    parser.add_argument('--dry-run',  action='store_true',
                        help="Print counts without writing")
    parser.add_argument('--score-mode', action='store_true', dest='score_mode',
                        help="Use volatility scoring system instead of rule-based (requires migration_volatility_scoring to have run)")
    parser.add_argument('--year-from', type=int, default=2000, dest='year_from',
                        help="Modern era cutoff for stars tier (default: 2000)")
    args = parser.parse_args()

    if args.score_mode:
        # New volatility scoring path — requires migrate_volatility_scoring.py to have run
        score_all_cards()
        return

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
