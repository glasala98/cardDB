"""Migration: delete market_raw_sales rows with eBay boilerplate titles.

'Opens in a new window or tab' was a known scraping artifact from early
eBay scrapes. Safe to re-run (deletes 0 rows if already clean).
"""
import os
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]


def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM market_raw_sales
        WHERE title ILIKE '%opens in a new window%'
           OR title ILIKE '%new window or tab%'
    """)
    print(f"Deleted {cur.rowcount} boilerplate title rows from market_raw_sales")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
