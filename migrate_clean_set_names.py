"""
migrate_clean_set_names.py — Strip ' Checklist Guide' / ' Guide' / ' Cards'
suffixes from card_catalog.set_name rows that were scraped from CLI/CBC sources.

Safe to re-run (UPDATE is a no-op once rows are already clean).
"""
import os
import re
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]


def clean_set_name(name: str) -> str:
    name = re.sub(r'\s+checklist\s+guide\s*$', '', name, flags=re.IGNORECASE).strip()
    name = re.sub(r'\s+guide\s*$',             '', name, flags=re.IGNORECASE).strip()
    name = re.sub(r'\s+cards?\s*$',            '', name, flags=re.IGNORECASE).strip()
    return name


def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur  = conn.cursor()

    print("Fetching distinct set names with artifacts...")
    cur.execute("""
        SELECT DISTINCT set_name
        FROM card_catalog
        WHERE set_name ILIKE '% checklist guide'
           OR set_name ILIKE '% guide'
           OR set_name ILIKE '% cards'
        ORDER BY set_name
    """)
    dirty = cur.fetchall()
    print(f"  Found {len(dirty)} distinct set names to clean")

    updated_total = 0
    for (raw_name,) in dirty:
        cleaned = clean_set_name(raw_name)
        if cleaned == raw_name:
            continue
        cur.execute("""
            UPDATE card_catalog SET set_name = %s WHERE set_name = %s
        """, (cleaned, raw_name))
        n = cur.rowcount
        updated_total += n
        if n:
            print(f"  {n:>6} rows: '{raw_name}' → '{cleaned}'")

    conn.commit()
    cur.close()
    conn.close()
    print(f"\nDone — {updated_total} rows updated.")


if __name__ == "__main__":
    main()
