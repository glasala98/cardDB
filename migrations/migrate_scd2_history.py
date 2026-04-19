#!/usr/bin/env python3
"""
Migration: SCD Type 2 — add effective_to + is_current to market_price_history.

Before:  single scraped_at timestamp per row, current row inferred by MAX(scraped_at)
After:   effective_to = scraped_at of the next row (NULL = still active)
         is_current   = TRUE on the latest row per card

This makes point-in-time queries trivial:
  WHERE is_current = TRUE                   → current prices
  WHERE %s BETWEEN scraped_at AND effective_to  → price on a given date
  WHERE effective_to IS NULL                → same as is_current

Backfill: one UPDATE using a window function — safe to re-run (idempotent).
Runtime:  proportional to rows in market_price_history. On ~1M rows, expect 30-90s.
"""

import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, '.env'))
except ImportError:
    pass
from db import get_db


DDL = """
ALTER TABLE market_price_history
    ADD COLUMN IF NOT EXISTS effective_to TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS is_current   BOOLEAN NOT NULL DEFAULT FALSE;

-- Index: querying current rows is the hot path
CREATE INDEX IF NOT EXISTS idx_mph_is_current
    ON market_price_history (card_catalog_id)
    WHERE is_current = TRUE;
"""

BACKFILL = """
WITH ordered AS (
    SELECT
        card_catalog_id,
        scraped_at,
        LEAD(scraped_at::TIMESTAMPTZ) OVER (
            PARTITION BY card_catalog_id ORDER BY scraped_at
        ) AS next_at,
        ROW_NUMBER() OVER (
            PARTITION BY card_catalog_id ORDER BY scraped_at DESC
        ) AS rn
    FROM market_price_history
)
UPDATE market_price_history mph
SET effective_to = ordered.next_at,
    is_current   = (ordered.rn = 1)
FROM ordered
WHERE mph.card_catalog_id = ordered.card_catalog_id
  AND mph.scraped_at      = ordered.scraped_at;
"""


def run():
    print("Running migration: SCD Type 2 history columns...")
    with get_db() as conn:
        with conn.cursor() as cur:
            print("  Adding effective_to + is_current columns...")
            cur.execute(DDL)
        conn.commit()

    print("  Backfilling effective_to + is_current (may take 1-2 min on large tables)...")
    # Backfill runs outside the DDL transaction so it can be long without
    # holding a schema lock. Uses a single window-function UPDATE — no loops.
    import psycopg2
    raw = psycopg2.connect(os.environ["DATABASE_URL"])
    raw.autocommit = False
    try:
        with raw.cursor() as cur:
            cur.execute("SET statement_timeout = '300s'")
            cur.execute(BACKFILL)
            updated = cur.rowcount
        raw.commit()
        print(f"  ✓ Updated {updated:,} rows")
    finally:
        raw.close()

    print("Migration complete.")
    print("Next step: trigger run_migration.yml with 'migrate_scd2_history'")


if __name__ == '__main__':
    run()
