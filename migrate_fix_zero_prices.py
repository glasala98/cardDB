"""
migrate_fix_zero_prices.py — Null out market_prices.fair_value where it's <= 0.

A fair_value of 0 means no real sales data was found; it should be NULL
so the frontend correctly shows 'No price data' instead of '$0.00'.
Safe to re-run.
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
        return

    cur.execute("""
        UPDATE market_prices
        SET fair_value = NULL
        WHERE fair_value <= 0
    """)
    print(f"Nulled out {cur.rowcount:,} rows")
    conn.commit()
    cur.close()
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
