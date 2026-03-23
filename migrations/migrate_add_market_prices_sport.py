"""Migration: add sport/scrape_tier/year columns to market_prices.

Denormalizes card_catalog fields into market_prices so progress queries
never need an expensive JOIN. Safe to re-run (all IF NOT EXISTS).
"""
import os
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]


def main():
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

    # NOTE: backfill (UPDATE market_prices SET sport=...) is run separately
    # via GH Actions workflow backfill_market_prices_sport.yml — not here,
    # because it is too slow to block a Railway deploy.

    # Indexes for fast filtering
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_mp_sport_tier_year
        ON market_prices (sport, scrape_tier, year)
        WHERE fair_value > 0;
    """)
    print("market_prices: index on (sport, scrape_tier, year) created (or already existed)")

    cur.close()
    conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    main()
