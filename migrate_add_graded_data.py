"""Migration: add graded_data JSONB column to market_prices.

Run once via GitHub Actions workflow.
"""
import os, sys
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]


def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    # Add column if it doesn't exist
    cur.execute("""
        ALTER TABLE market_prices
        ADD COLUMN IF NOT EXISTS graded_data JSONB NOT NULL DEFAULT '{}';
    """)
    print("market_prices.graded_data column added (or already existed)")

    # Migrate any existing graded data from rookie_price_history into
    # market_prices for cards that have a matching card_catalog entry.
    # rookie_price_history uses player name as key; we match on player_name ILIKE.
    cur.execute("""
        UPDATE market_prices mp
        SET graded_data = rph.graded_data
        FROM rookie_price_history rph
        JOIN card_catalog cc ON cc.id = mp.card_catalog_id
        WHERE rph.graded_data != '{}'
          AND rph.player ILIKE cc.player_name
          AND mp.graded_data = '{}'
          AND rph.date = (
              SELECT MAX(date) FROM rookie_price_history r2
              WHERE r2.player = rph.player
          )
    """)
    migrated = cur.rowcount
    print(f"Migrated {migrated} graded_data rows from rookie_price_history → market_prices")

    cur.close()
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
