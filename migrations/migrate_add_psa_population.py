#!/usr/bin/env python3
"""
Migration: add psa_population table.

Stores PSA graded card population counts per grade, linked to card_catalog.
Used as a supply-side signal for price prediction.

Schema:
    psa_population(id, card_catalog_id, psa_spec_id, psa_title, grade,
                   pop_count, pop_higher, scraped_at)

Idempotent — safe to run multiple times.
"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from db import get_db

def main():
    with get_db() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                CREATE TABLE IF NOT EXISTS psa_population (
                    id              BIGSERIAL   PRIMARY KEY,
                    card_catalog_id BIGINT      REFERENCES card_catalog(id) ON DELETE CASCADE,
                    psa_spec_id     INTEGER,
                    psa_title       TEXT        NOT NULL DEFAULT '',
                    grade           TEXT        NOT NULL,
                    pop_count       INTEGER     NOT NULL DEFAULT 0,
                    pop_higher      INTEGER     NOT NULL DEFAULT 0,
                    scraped_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (card_catalog_id, grade)
                );
            """)
            print("psa_population table created (or already existed)")

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_psa_pop_card
                    ON psa_population (card_catalog_id);
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_psa_pop_spec
                    ON psa_population (psa_spec_id);
            """)
            print("psa_population indexes created (or already existed)")

    print("migrate_add_psa_population: OK")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"migrate_add_psa_population: ERROR — {e}")
        raise
