"""Migration: add created_at to market_raw_sales for delta backup support.

Adds an ingestion timestamp so delta backups can export only rows inserted
since the last scrape run, rather than re-exporting the entire table.

Idempotent — safe to re-run on every Railway deploy.
"""
import os
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]


def run():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    # Add column — DEFAULT NOW() backfills NULL for existing rows but we
    # set it as NOT NULL with default so new rows are stamped automatically.
    # Existing rows get NULL (acceptable — they predate delta backups).
    cur.execute("""
        ALTER TABLE market_raw_sales
        ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();
    """)
    print("market_raw_sales.created_at — added (or already existed)")

    # Index for the delta backup WHERE clause
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_market_raw_sales_created_at
        ON market_raw_sales (created_at);
    """)
    print("idx_market_raw_sales_created_at — created (or already existed)")

    cur.close()
    conn.close()


if __name__ == "__main__":
    run()
