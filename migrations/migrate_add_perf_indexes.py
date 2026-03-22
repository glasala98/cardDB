"""
Performance index migration — safe to re-run (all IF NOT EXISTS).

Adds:
  1. pg_trgm extension — enables fast ILIKE/fuzzy search
  2. Trigram GIN indexes on player_name + set_name (ILIKE '%search%')
  3. Expression index on CAST(SUBSTRING(year FROM '^\d+') AS INTEGER)
     — used in /catalog/releases ORDER BY, avoids computing per-row
  4. Composite partial index on market_prices for the most common filter
     (NOT ignored AND fair_value > 0) — powers catalog browse + outlier queries
  5. scrape_tier index on card_catalog — used in releases FILTER aggregates
  6. scraped_at index on market_prices — used in freshness/quality queries
"""

import os
import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("migrate_add_perf_indexes: DATABASE_URL not set, skipping")
    raise SystemExit(0)


def run():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    steps = [
        # 1. Trigram extension
        ("pg_trgm extension",
         "CREATE EXTENSION IF NOT EXISTS pg_trgm"),

        # 2. Trigram indexes for ILIKE search
        ("trigram index on player_name",
         "CREATE INDEX IF NOT EXISTS idx_cc_player_name_trgm "
         "ON card_catalog USING GIN (player_name gin_trgm_ops)"),

        ("trigram index on set_name",
         "CREATE INDEX IF NOT EXISTS idx_cc_set_name_trgm "
         "ON card_catalog USING GIN (set_name gin_trgm_ops)"),

        # 3. Expression index for year_num cast (releases endpoint ORDER BY)
        ("expression index on year_num",
         r"CREATE INDEX IF NOT EXISTS idx_cc_year_num "
         r"ON card_catalog (CAST(SUBSTRING(year FROM '^\d+') AS INTEGER))"),

        # 4. scrape_tier index (releases FILTER aggregates)
        ("index on scrape_tier",
         "CREATE INDEX IF NOT EXISTS idx_cc_scrape_tier "
         "ON card_catalog (scrape_tier)"),

        # 5. Composite partial index for catalog browse (most common hot path)
        #    Covers: WHERE NOT ignored AND fair_value > 0 ORDER BY fair_value DESC
        ("partial index on market_prices fair_value",
         "CREATE INDEX IF NOT EXISTS idx_mp_priced "
         "ON market_prices (fair_value DESC) "
         "WHERE NOT ignored AND fair_value > 0"),

        # 6. scraped_at index for freshness/quality dashboard queries
        ("index on market_prices scraped_at",
         "CREATE INDEX IF NOT EXISTS idx_mp_scraped_at "
         "ON market_prices (scraped_at)"),

        # 7. Composite for the common JOIN pattern: catalog_id + ignored + fair_value
        ("composite index on market_prices catalog+fair_value",
         "CREATE INDEX IF NOT EXISTS idx_mp_catalog_fair "
         "ON market_prices (card_catalog_id, fair_value DESC) "
         "WHERE NOT ignored"),
    ]

    for label, sql in steps:
        try:
            print(f"  → {label}...", end=" ", flush=True)
            cur.execute(sql)
            print("ok")
        except Exception as e:
            print(f"SKIPPED ({e})")

    cur.close()
    conn.close()
    print("migrate_add_perf_indexes: done")


if __name__ == "__main__":
    run()
