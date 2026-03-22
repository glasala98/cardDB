"""Migration: create auction_unmatched table.

Stores auction house sales that could not be matched to a card_catalog row.
Used to audit match quality and surface cards missing from the catalog.

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
            CREATE TABLE IF NOT EXISTS auction_unmatched (
                id         BIGSERIAL    PRIMARY KEY,
                source     TEXT         NOT NULL,
                title      TEXT         NOT NULL,
                price_val  NUMERIC      NOT NULL,
                sold_date  DATE,
                raw_url    TEXT         NOT NULL DEFAULT '',
                reason     TEXT         NOT NULL DEFAULT '',
                scraped_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                reviewed   BOOLEAN      NOT NULL DEFAULT FALSE
            );
        """)
        print("auction_unmatched table created (or already existed)")

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_auction_unmatched_source
                ON auction_unmatched (source, scraped_at DESC);
        """)
        print("idx_auction_unmatched_source index created (or already existed)")

    except Exception as e:
        print(f"  WARNING: migrate_add_auction_unmatched failed (non-fatal): {e}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"migrate_add_auction_unmatched: ERROR — {e}")
