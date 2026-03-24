"""Migration: create catalog_sets table for set-level metadata (box images, TCDB IDs).

Keyed on (year, set_name, sport). Box image URL is derived from tcdb_sid.
Safe to re-run (IF NOT EXISTS).
"""
import os
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]


def run():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS catalog_sets (
            year          TEXT        NOT NULL,
            set_name      TEXT        NOT NULL,
            sport         TEXT        NOT NULL,
            tcdb_sid      TEXT,
            box_image_url TEXT,
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (year, set_name, sport)
        );
    """)
    print("catalog_sets table created (or already existed)")

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_catalog_sets_sport_year
            ON catalog_sets (sport, year);
    """)
    print("idx_catalog_sets_sport_year index created (or already existed)")

    cur.close()
    conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        print(f"migrate_add_catalog_sets: WARNING — {e} (non-fatal)")
