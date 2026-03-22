"""Migration: strip eBay boilerplate from existing market_raw_sales titles.

Runs automatically on every Railway deploy (idempotent — safe to re-run).
Removes 'Opens in a new window or tab' and other eBay UI artifacts that were
scraped before the title-strip fix was deployed.
"""
import os
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]

BOILERPLATE = [
    "\nOpens in a new window or tab",
    "Opens in a new window or tab",
]


def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    try:
        for phrase in BOILERPLATE:
            cur.execute(
                "UPDATE market_raw_sales SET title = TRIM(REPLACE(title, %s, '')) WHERE title LIKE %s",
                (phrase, f"%{phrase}%")
            )
            rows = cur.rowcount
            if rows:
                print(f"  Cleaned {rows:,} rows — stripped: {phrase!r}")

        print("  Title cleanup complete.")

    except Exception as e:
        print(f"  WARNING: Title cleanup failed (non-fatal): {e}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
