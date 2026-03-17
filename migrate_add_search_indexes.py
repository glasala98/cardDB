"""Migration: add full-text search infrastructure for the card sales search engine.

Adds:
  - search_vector GENERATED column on card_catalog (tsvector for fast FTS)
  - GIN index on search_vector
  - Trigram GIN index on market_raw_sales.title
  - Composite index on market_raw_sales (card_catalog_id, sold_date DESC)

Runs automatically on every Railway deploy (idempotent — safe to re-run).
Building GIN indexes on large tables takes 3-5 minutes on first deploy — this
is expected and Railway will show a startup delay once.
"""
import os
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]


def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    try:
        # Ensure pg_trgm extension is available
        cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
        print("  pg_trgm extension — enabled (or already existed)")

        # Add search_vector generated column to card_catalog
        cur.execute("""
            ALTER TABLE card_catalog
            ADD COLUMN IF NOT EXISTS search_vector tsvector
            GENERATED ALWAYS AS (
                setweight(to_tsvector('english', coalesce(player_name, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(set_name,    '')), 'B') ||
                setweight(to_tsvector('english', coalesce(brand,       '')), 'C') ||
                setweight(to_tsvector('english', coalesce(year,        '')), 'C') ||
                setweight(to_tsvector('english', coalesce(variant,     '')), 'D')
            ) STORED;
        """)
        print("  card_catalog.search_vector — added (or already existed)")

        # GIN index on search_vector (primary FTS index)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_cc_search_vector
                ON card_catalog USING GIN (search_vector);
        """)
        print("  idx_cc_search_vector — created (or already existed)")

        # Trigram index on player_name (fuzzy name matching)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_cc_player_trgm
                ON card_catalog USING GIN (player_name gin_trgm_ops);
        """)
        print("  idx_cc_player_trgm — created (or already existed)")

        # Trigram index on market_raw_sales.title (direct title search)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_mrs_title_trgm
                ON market_raw_sales USING GIN (title gin_trgm_ops);
        """)
        print("  idx_mrs_title_trgm — created (or already existed)")

        # Composite index: primary search result fetch pattern
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_mrs_search_result
                ON market_raw_sales (card_catalog_id, sold_date DESC NULLS LAST, price_val);
        """)
        print("  idx_mrs_search_result — created (or already existed)")

        # Source + date index for source-filtered queries
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_mrs_source_date
                ON market_raw_sales (source, sold_date DESC NULLS LAST);
        """)
        print("  idx_mrs_source_date — created (or already existed)")

        print("migrate_add_search_indexes: complete.")

    except Exception as e:
        print(f"  WARNING: migrate_add_search_indexes failed (non-fatal): {e}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"migrate_add_search_indexes: ERROR — {e}")
