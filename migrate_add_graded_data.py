"""Migration: add graded_data JSONB column to market_prices.

Runs automatically on every Railway deploy (idempotent — safe to re-run).
Errors are caught and logged so a failure never prevents the server starting.
"""
import os
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]


def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    # Add columns if they don't exist
    cur.execute("""
        ALTER TABLE market_prices
        ADD COLUMN IF NOT EXISTS graded_data JSONB NOT NULL DEFAULT '{}';
    """)
    print("market_prices.graded_data column added (or already existed)")

    cur.execute("""
        ALTER TABLE market_prices
        ADD COLUMN IF NOT EXISTS image_url TEXT NOT NULL DEFAULT '';
    """)
    print("market_prices.image_url column added (or already existed)")

    cur.execute("""
        ALTER TABLE market_prices
        ADD COLUMN IF NOT EXISTS ignored BOOLEAN NOT NULL DEFAULT FALSE;
    """)
    print("market_prices.ignored column added (or already existed)")

    # Migrate existing graded data from rookie_price_history into market_prices.
    # In PostgreSQL UPDATE...FROM, the target table must NOT be aliased —
    # reference it directly; JOIN condition uses market_prices.card_catalog_id.
    cur.execute("""
        UPDATE market_prices
        SET graded_data = rph.graded_data
        FROM rookie_price_history rph
        JOIN card_catalog cc ON cc.id = market_prices.card_catalog_id
        WHERE rph.graded_data != '{}'
          AND rph.player ILIKE cc.player_name
          AND market_prices.graded_data = '{}'
          AND rph.date = (
              SELECT MAX(r2.date) FROM rookie_price_history r2
              WHERE r2.player = rph.player
          )
    """)
    print(f"Migrated {cur.rowcount} graded_data rows from rookie_price_history → market_prices")

    cur.close()
    conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Migration error (non-fatal): {e}")
