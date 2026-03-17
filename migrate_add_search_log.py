"""
Migration: add search_log table for trending + analytics.
Idempotent — safe to re-run.
"""
import os, sys
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from db import get_db

def run():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS search_log (
                    id          BIGSERIAL PRIMARY KEY,
                    query       TEXT        NOT NULL,
                    result_count INT,
                    searched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_search_log_searched_at
                    ON search_log (searched_at DESC)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_search_log_query
                    ON search_log (lower(query))
            """)
        conn.commit()
    print("search_log migration complete")

if __name__ == '__main__':
    run()
