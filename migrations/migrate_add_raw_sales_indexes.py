"""Migration: add indexes on market_raw_sales for fast lookup by card and date.

Runs automatically on every Railway deploy (idempotent — safe to re-run).
CREATE INDEX IF NOT EXISTS is a no-op when the index already exists.
"""
import os
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]


def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_market_raw_sales_catalog
        ON market_raw_sales (card_catalog_id);
    """)
    print("  idx_market_raw_sales_catalog: ok")

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_market_raw_sales_sold_date
        ON market_raw_sales (sold_date);
    """)
    print("  idx_market_raw_sales_sold_date: ok")

    cur.close()
    conn.close()


if __name__ == "__main__":
    try:
        main()
        print("migrate_add_raw_sales_indexes: done")
    except Exception as e:
        print(f"migrate_add_raw_sales_indexes: ERROR — {e}")
