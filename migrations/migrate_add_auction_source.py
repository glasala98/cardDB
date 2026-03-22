"""Migration: add source column to market_raw_sales.

Tracks which platform each sale came from (ebay, goldin, heritage, pwcc, etc.)
so the ML model can weight sales by source and analysts can filter by platform.

Runs automatically on every Railway deploy (idempotent — safe to re-run).
"""
import os
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]


def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    try:
        cur.execute("""
            ALTER TABLE market_raw_sales
            ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'ebay';
        """)
        print("market_raw_sales.source column added (or already existed)")

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_market_raw_sales_source
                ON market_raw_sales (source);
        """)
        print("idx_market_raw_sales_source index created (or already existed)")

    except Exception as e:
        print(f"  WARNING: migrate_add_auction_source failed (non-fatal): {e}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"migrate_add_auction_source: ERROR — {e}")
