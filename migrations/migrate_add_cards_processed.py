"""Idempotent migration: add cards_processed column to scrape_runs.

This column tracks how many cards have been processed (attempted) so far
during a live scrape run, updated every 50-card batch. Enables real-time
progress bars in the Admin dashboard without waiting for finish_scrape_run.
"""
import sys
from db import get_db

def main():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                ALTER TABLE scrape_runs
                ADD COLUMN IF NOT EXISTS cards_processed INT DEFAULT 0
            """)
        conn.commit()
    print("Migration complete: scrape_runs.cards_processed column ensured.")

if __name__ == "__main__":
    main()
