"""Migration: fix market_raw_sales unique constraint for ON CONFLICT support.

The partial index (WHERE listing_hash IS NOT NULL) created by
migrate_fix_market_raw_sales.py does NOT satisfy PostgreSQL's
ON CONFLICT (listing_hash) clause — that requires a non-partial
unique constraint.  This migration drops the partial index and
creates a full unique constraint instead.

Runs automatically on every Railway deploy (idempotent).
"""
import os
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]


def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    # Drop the partial index that doesn't work with ON CONFLICT
    cur.execute("DROP INDEX IF EXISTS idx_market_raw_sales_hash;")
    print("dropped partial idx_market_raw_sales_hash (if existed)")

    # Backfill any NULL listing_hash values before adding constraint
    cur.execute("""
        UPDATE market_raw_sales
        SET listing_hash = md5(
            card_catalog_id::text || '|' ||
            COALESCE(sold_date::text, '') || '|' ||
            LOWER(TRIM(COALESCE(title, '')))
        )
        WHERE listing_hash IS NULL;
    """)
    print(f"backfilled NULL listing_hash values")

    # Add a proper non-partial unique constraint
    cur.execute("""
        ALTER TABLE market_raw_sales
        ADD CONSTRAINT market_raw_sales_listing_hash_key
        UNIQUE (listing_hash);
    """)
    print("added UNIQUE constraint on listing_hash")

    cur.close()
    conn.close()


if __name__ == "__main__":
    try:
        main()
        print("migrate_fix_raw_sales_constraint: done")
    except Exception as e:
        print(f"migrate_fix_raw_sales_constraint: ERROR — {e}")
