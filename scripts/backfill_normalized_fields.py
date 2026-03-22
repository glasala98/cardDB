"""Backfill normalized fields on existing market_raw_sales rows.

Parses titles of rows where grade/serial_number/print_run are all NULL
and updates them in batches. Safe to re-run — only touches NULL rows.
"""
import os
import sys
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "scraping"))  # auction_title_parser lives here
import psycopg2
import psycopg2.extras
from auction_title_parser import parse_title

DATABASE_URL = os.environ["DATABASE_URL"]
BATCH_SIZE = 5000


def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cur.execute("""
        SELECT COUNT(*) FROM market_raw_sales
        WHERE grade IS NULL AND serial_number IS NULL AND print_run IS NULL
          AND title IS NOT NULL AND title != ''
    """)
    total = cur.fetchone()[0]
    print(f"Rows to backfill: {total:,}")

    if total == 0:
        print("Nothing to do.")
        return

    processed = 0
    offset = 0

    while True:
        cur.execute("""
            SELECT id, title FROM market_raw_sales
            WHERE grade IS NULL AND serial_number IS NULL AND print_run IS NULL
              AND title IS NOT NULL AND title != ''
            ORDER BY id
            LIMIT %s OFFSET %s
        """, (BATCH_SIZE, offset))
        rows = cur.fetchall()
        if not rows:
            break

        updates = []
        for row in rows:
            p = parse_title(row['title'])
            updates.append((
                p['grade'], p['grade_company'], p['grade_numeric'],
                p['serial_number'], p['print_run'],
                row['id']
            ))

        psycopg2.extras.execute_batch(cur, """
            UPDATE market_raw_sales SET
                grade         = %s,
                grade_company = %s,
                grade_numeric = %s,
                serial_number = %s,
                print_run     = %s
            WHERE id = %s
        """, updates)
        conn.commit()

        processed += len(rows)
        offset += BATCH_SIZE
        print(f"  [{processed:,}/{total:,}] backfilled")

    print(f"Done. {processed:,} rows updated.")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
