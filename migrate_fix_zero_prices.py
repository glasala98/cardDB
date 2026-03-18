"""
migrate_fix_zero_prices.py — Delete market_prices rows where fair_value <= 0.

A fair_value of 0 means no real sales data was found. These rows are noise;
deleting them lets the frontend correctly show 'No price data' for unpriced cards
(via the LEFT JOIN in browse_catalog returning NULL for mp.fair_value).

fair_value has a NOT NULL constraint so we delete instead of nulling.
Safe to re-run (no rows to delete = no-op).
"""
import os
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]


def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur  = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM market_prices WHERE fair_value <= 0")
    count = cur.fetchone()[0]
    print(f"Rows with fair_value <= 0: {count:,}")

    if count == 0:
        print("Nothing to fix.")
        conn.close()
        return

    cur.execute("DELETE FROM market_prices WHERE fair_value <= 0")
    print(f"Deleted {cur.rowcount:,} rows")
    conn.commit()
    cur.close()
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
