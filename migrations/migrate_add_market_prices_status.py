"""Migration: create market_prices_status view.

Adds a stable view over market_prices that exposes:
  - is_stale  BOOLEAN  — scraped_at is NULL or older than 90 days
  - is_fresh  BOOLEAN  — scraped_at is within the last 90 days
  - days_since_scraped INT — days elapsed since last scrape (NULL if never scraped)

The view is always in sync with the underlying scraped_at column — no scraper
changes required, no maintenance burden.

Runs automatically on every Railway deploy (idempotent — safe to re-run).
"""
import os
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]


def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("""
        CREATE OR REPLACE VIEW market_prices_status AS
        SELECT
            mp.*,
            (mp.scraped_at IS NULL OR mp.scraped_at < NOW() - INTERVAL '90 days') AS is_stale,
            (mp.scraped_at IS NOT NULL AND mp.scraped_at >= NOW() - INTERVAL '90 days') AS is_fresh,
            EXTRACT(DAYS FROM NOW() - mp.scraped_at)::INT AS days_since_scraped
        FROM market_prices mp;
    """)
    print("market_prices_status view created (or replaced)")

    cur.close()
    conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"migrate_add_market_prices_status: ERROR — {e}")
