"""Migration: add scrape_error_log table.

Stores per-card scrape failures linked to a scrape_run so admins
can see which cards are consistently failing and why.
"""
import os
import sys

import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("migrate_add_scrape_error_log: DATABASE_URL not set, skipping")
    sys.exit(0)

steps = [
    ("scrape_error_log table", """
        CREATE TABLE IF NOT EXISTS scrape_error_log (
            id              BIGSERIAL    PRIMARY KEY,
            run_id          BIGINT       REFERENCES scrape_runs(id) ON DELETE SET NULL,
            card_catalog_id BIGINT       REFERENCES card_catalog(id) ON DELETE SET NULL,
            card_name       TEXT         NOT NULL DEFAULT '',
            error_type      TEXT         NOT NULL DEFAULT 'unknown',
            error_msg       TEXT         NOT NULL DEFAULT '',
            occurred_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """),
    ("index scrape_error_log(run_id)",
     "CREATE INDEX IF NOT EXISTS idx_scrape_error_log_run ON scrape_error_log (run_id)"),
    ("index scrape_error_log(card_catalog_id)",
     "CREATE INDEX IF NOT EXISTS idx_scrape_error_log_card ON scrape_error_log (card_catalog_id)"),
]

conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cur = conn.cursor()

for label, sql in steps:
    try:
        cur.execute(sql)
        print(f"  OK: {label}")
    except Exception as e:
        print(f"  SKIP ({label}): {e}")

cur.close()
conn.close()
print("migrate_add_scrape_error_log: done")
