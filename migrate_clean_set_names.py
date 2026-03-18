"""
migrate_clean_set_names.py — Strip ' Checklist Guide' / ' Guide' / ' Cards'
suffixes from card_catalog.set_name rows that were scraped from CLI/CBC sources.

When the cleaned name already exists (duplicate constraint), the dirty rows are
deleted atomically in a single SQL statement (no TOCTOU). Remaining dirty rows
are then updated in a single batch.

Safe to re-run.
"""
import os
import sys
import re
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]

# Single regex that strips all known scraper suffixes in one pass
_SUFFIX_RE = re.compile(
    r'\s+(?:checklist\s+guide|guide|cards?)\s*$',
    flags=re.IGNORECASE,
)


def clean_set_name(name: str) -> str:
    return _SUFFIX_RE.sub('', name).strip()


def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur  = conn.cursor()

    try:
        cur.execute("""
            SELECT COUNT(*) FROM card_catalog
            WHERE set_name ~* '\\s+(checklist\\s+guide|guide|cards?)\\s*$'
        """)
        count = cur.fetchone()[0]
        print(f"Rows matching dirty pattern: {count:,}")

        if count == 0:
            print("Nothing to fix.")
            return

        # Step 1 — fetch distinct dirty names (small set, all in memory)
        cur.execute("""
            SELECT DISTINCT set_name FROM card_catalog
            WHERE set_name ~* '\\s+(checklist\\s+guide|guide|cards?)\\s*$'
            ORDER BY set_name
        """)
        dirty_names = [row[0] for row in cur.fetchall()]
        print(f"  {len(dirty_names)} distinct dirty set names")

        updated_total = 0
        deleted_total = 0

        for raw_name in dirty_names:
            cleaned = clean_set_name(raw_name)
            if cleaned == raw_name:
                continue

            # Atomic delete: remove dirty rows only if the clean name already exists.
            # Single SQL — no TOCTOU.
            cur.execute("""
                DELETE FROM card_catalog
                WHERE set_name = %s
                  AND EXISTS (SELECT 1 FROM card_catalog WHERE set_name = %s LIMIT 1)
            """, (raw_name, cleaned))
            n_del = cur.rowcount

            if n_del:
                deleted_total += n_del
                print(f"  DELETE {n_del:>6} rows (clean exists): '{raw_name}'")
            else:
                # Clean name doesn't exist — update atomically, skip if constraint fires.
                cur.execute("""
                    UPDATE card_catalog SET set_name = %s
                    WHERE set_name = %s
                      AND NOT EXISTS (SELECT 1 FROM card_catalog WHERE set_name = %s LIMIT 1)
                """, (cleaned, raw_name, cleaned))
                n_upd = cur.rowcount
                updated_total += n_upd
                if n_upd:
                    print(f"  UPDATE {n_upd:>6} rows: '{raw_name}' → '{cleaned}'")

            conn.commit()

        print(f"\nDone — {updated_total} rows updated, {deleted_total} duplicate rows deleted.")

    except Exception as e:
        conn.rollback()
        print(f"Error: {e}", file=sys.stderr)
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
