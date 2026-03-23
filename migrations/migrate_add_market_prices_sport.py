"""Migration: add sport/scrape_tier/year columns to market_prices.

Denormalizes card_catalog fields into market_prices so progress queries
never need an expensive JOIN. Safe to re-run (all IF NOT EXISTS).

NOTE: The backfill (UPDATE) and index creation run separately via GH Actions
because they are too slow to block a Railway deploy.
"""
import os
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]


def main():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        cur = conn.cursor()

        cur.execute("""
            ALTER TABLE market_prices
            ADD COLUMN IF NOT EXISTS sport TEXT,
            ADD COLUMN IF NOT EXISTS scrape_tier TEXT,
            ADD COLUMN IF NOT EXISTS year TEXT;
        """)
        print("market_prices: sport/scrape_tier/year columns added (or already existed)")

        cur.close()
        conn.close()
        print("Migration complete.")
    except Exception as e:
        print(f"migrate_add_market_prices_sport: WARNING — {e} (non-fatal, skipping)")


if __name__ == "__main__":
    main()
