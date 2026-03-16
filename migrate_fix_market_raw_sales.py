"""Migration: fix market_raw_sales dedup key + add shipping_val.

Problems fixed:
  1. UNIQUE (card_catalog_id, sold_date, title) breaks on NULL sold_date —
     PostgreSQL treats NULL != NULL so the same undated sale inserts twice
     on every re-scrape, silently building duplicates.
  2. shipping_val was baked into price_val, losing the split forever.

Fix:
  - Add listing_hash TEXT — md5 of (card_catalog_id, sold_date, title, price_val)
    computed in Python before insert, NULL-safe, unique index on this column.
  - Drop the old broken UNIQUE constraint.
  - Add shipping_val NUMERIC DEFAULT 0 — card price and shipping stored separately.

The table is still new/empty so no data migration is needed.
Runs automatically on every Railway deploy (idempotent — safe to re-run).
"""
import os
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]


def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    # Add listing_hash column (idempotent)
    cur.execute("""
        ALTER TABLE market_raw_sales
        ADD COLUMN IF NOT EXISTS listing_hash TEXT;
    """)
    print("market_raw_sales.listing_hash column added (or already existed)")

    # Add shipping_val column (idempotent)
    cur.execute("""
        ALTER TABLE market_raw_sales
        ADD COLUMN IF NOT EXISTS shipping_val NUMERIC NOT NULL DEFAULT 0;
    """)
    print("market_raw_sales.shipping_val column added (or already existed)")

    # Drop the old NULL-unsafe unique constraint if it exists
    cur.execute("""
        ALTER TABLE market_raw_sales
        DROP CONSTRAINT IF EXISTS market_raw_sales_card_catalog_id_sold_date_title_key;
    """)
    print("old UNIQUE (card_catalog_id, sold_date, title) constraint dropped (or didn't exist)")

    # Create unique index on listing_hash (idempotent)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_market_raw_sales_hash
            ON market_raw_sales (listing_hash)
            WHERE listing_hash IS NOT NULL;
    """)
    print("idx_market_raw_sales_hash unique index created (or already existed)")

    cur.close()
    conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"migrate_fix_market_raw_sales: ERROR — {e}")
