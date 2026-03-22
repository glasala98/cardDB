"""One-time cleanup: remove sealed_products rows with obvious sport mismatches.

Cardboardconnection.com cross-lists some products (e.g. Panini multi-sport
sets, football products on the hockey page) which the scraper ingested with
the wrong sport tag.  This script deletes rows where the set name clearly
signals a different sport than the stored one, then logs what was removed.

Safe to re-run — deletes only rows whose set name contains explicit sport
keywords that contradict the stored sport column.
"""
from db import get_db

MISMATCH_RULES = [
    # (stored_sport_not_in, name_ilike_pattern, correct_sport_note)
    ("NFL", "%football%",    "football keyword → should be NFL"),
    ("NFL", "%gridiron%",    "gridiron keyword → should be NFL"),
    ("MLB", "%baseball%",    "baseball keyword → should be MLB"),
    ("NBA", "%basketball%",  "basketball keyword → should be NBA"),
    ("NHL", "%hockey%",      "hockey keyword → should be NHL"),
]


def main():
    total_deleted = 0
    with get_db() as conn:
        with conn.cursor() as cur:
            for correct_sport, pattern, note in MISMATCH_RULES:
                cur.execute(
                    """
                    DELETE FROM sealed_products
                    WHERE sport != %s
                      AND set_name ILIKE %s
                    """,
                    (correct_sport, pattern),
                )
                n = cur.rowcount
                if n:
                    print(f"  Deleted {n:>4} rows: {note}")
                    total_deleted += n

            # Also delete Bowman sets not filed under MLB (always MLB)
            cur.execute(
                """
                DELETE FROM sealed_products
                WHERE sport != 'MLB'
                  AND set_name ILIKE '%bowman%'
                """,
            )
            n = cur.rowcount
            if n:
                print(f"  Deleted {n:>4} rows: Bowman → should be MLB")
                total_deleted += n

        conn.commit()

    if total_deleted:
        print(f"\nTotal: {total_deleted} mismatched rows removed.")
        print("Re-run the scrape_set_info workflow per sport to rebuild correct data.")
    else:
        print("No mismatched rows found — data looks clean.")


if __name__ == "__main__":
    main()
