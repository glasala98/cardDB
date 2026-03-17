"""Migration: strip eBay boilerplate text from market_raw_sales titles.

Removes '\nOpens in a new window or tab' and similar suffixes that were
scraped from eBay's HTML before the fix was applied.

Idempotent — safe to re-run.
"""
import os, psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]

def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("""
        UPDATE market_raw_sales
        SET title = TRIM(SPLIT_PART(title, E'\\n', 1))
        WHERE title LIKE E'%\\n%'
    """)
    print(f"Cleaned {cur.rowcount} titles with newline boilerplate")

    cur.close()
    conn.close()

if __name__ == "__main__":
    try:
        main()
        print("migrate_clean_raw_sales_titles: done")
    except Exception as e:
        print(f"migrate_clean_raw_sales_titles: ERROR — {e}")
