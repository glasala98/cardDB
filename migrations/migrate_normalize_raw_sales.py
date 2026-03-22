"""Migration: normalize market_raw_sales with full structured fields.

Adds all columns needed for ML training, multi-source analytics, and SCD Type 2
historical completeness. No data is ever dropped — source-specific extras go into
raw_metadata JSONB.

New columns:
  grade            TEXT     — "PSA 10", "BGS 9.5", "Raw", etc.
  grade_company    TEXT     — "PSA", "BGS", "SGC", "CGC", "HGA", "CSG"
  grade_numeric    NUMERIC  — 10.0, 9.5, 9.0, etc. (NULL for raw/ungraded)
  serial_number    INTEGER  — e.g. 7 for a card numbered 7/25
  print_run        INTEGER  — e.g. 25 for a card numbered 7/25
  lot_url          TEXT     — link back to original listing/auction page
  lot_id           TEXT     — source's own listing/lot identifier
  hammer_price     NUMERIC  — pre-buyer's-premium price (auction houses only)
  buyer_premium_pct NUMERIC — buyer's premium % (e.g. 20.0 for 20%)
  image_url        TEXT     — card image from the listing
  is_auction       BOOLEAN  — TRUE for auction, FALSE for fixed-price (eBay BIN)
  raw_metadata     JSONB    — catch-all for source-specific fields, never dropped

Runs automatically on every Railway deploy (idempotent — safe to re-run).
"""
import os
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]

COLUMNS = [
    ("grade",             "TEXT"),
    ("grade_company",     "TEXT"),
    ("grade_numeric",     "NUMERIC"),
    ("serial_number",     "INTEGER"),
    ("print_run",         "INTEGER"),
    ("lot_url",           "TEXT     NOT NULL DEFAULT ''"),
    ("lot_id",            "TEXT     NOT NULL DEFAULT ''"),
    ("hammer_price",      "NUMERIC"),
    ("buyer_premium_pct", "NUMERIC"),
    ("image_url",         "TEXT"),
    ("is_auction",        "BOOLEAN  NOT NULL DEFAULT FALSE"),
    ("raw_metadata",      "JSONB    NOT NULL DEFAULT '{}'"),
]

INDEXES = [
    ("idx_mrs_grade",         "market_raw_sales (grade)"),
    ("idx_mrs_grade_numeric", "market_raw_sales (grade_numeric) WHERE grade_numeric IS NOT NULL"),
    ("idx_mrs_print_run",     "market_raw_sales (print_run)     WHERE print_run IS NOT NULL"),
    ("idx_mrs_is_auction",    "market_raw_sales (is_auction)"),
]


def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    try:
        for col, col_type in COLUMNS:
            cur.execute(f"""
                ALTER TABLE market_raw_sales
                ADD COLUMN IF NOT EXISTS {col} {col_type};
            """)
            print(f"  market_raw_sales.{col} — added (or already existed)")

        for idx_name, idx_target in INDEXES:
            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_target};
            """)
            print(f"  {idx_name} — created (or already existed)")

        print("migrate_normalize_raw_sales: complete.")

    except Exception as e:
        print(f"  WARNING: migrate_normalize_raw_sales failed (non-fatal): {e}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"migrate_normalize_raw_sales: ERROR — {e}")
