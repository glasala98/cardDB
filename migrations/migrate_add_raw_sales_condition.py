"""Migration: add condition column to market_raw_sales + create ebay_item_specifics table.

condition — eBay listing condition string (e.g. 'Pre-Owned', 'Near Mint or Better').
ebay_item_specifics — separate enrichment table keyed on listing_hash for joining
                      structured eBay item specifics (grade, year, set, player, etc.)
                      without bloating market_raw_sales. Populate via a separate
                      enrichment scrape workflow after backfill completes.
"""
import os
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]


def run():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("""
        ALTER TABLE market_raw_sales
        ADD COLUMN IF NOT EXISTS condition TEXT;
    """)
    print("market_raw_sales.condition column added (or already existed)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ebay_item_specifics (
            listing_hash    TEXT        PRIMARY KEY REFERENCES market_raw_sales(listing_hash) ON DELETE CASCADE,
            fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            item_specifics  JSONB       NOT NULL DEFAULT '{}'
        );
    """)
    print("ebay_item_specifics table created (or already existed)")

    cur.close()
    conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        print(f"migrate_add_raw_sales_condition: WARNING — {e} (non-fatal)")
