"""
Migration: add sealed_products and sealed_product_odds tables.
Safe to re-run (all IF NOT EXISTS).

sealed_products  — one row per (sport, year, set_name, product_type).
                   Stores MSRP, pack config, release date, and source URL.
sealed_product_odds — one row per (sealed_product_id, card_type).
                      Stores insertion odds per product type (e.g. 1:24 packs).
"""

import os
import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("migrate_add_sealed_products: DATABASE_URL not set, skipping")
    raise SystemExit(0)


def run():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    steps = [
        ("sealed_products table", """
            CREATE TABLE IF NOT EXISTS sealed_products (
                id             BIGSERIAL    PRIMARY KEY,
                sport          TEXT         NOT NULL,
                year           TEXT         NOT NULL,
                set_name       TEXT         NOT NULL,
                brand          TEXT         NOT NULL DEFAULT '',
                product_type   TEXT         NOT NULL,
                msrp           NUMERIC,
                cards_per_pack INT,
                packs_per_box  INT,
                release_date   DATE,
                source         TEXT         NOT NULL DEFAULT 'cardboardconnection',
                source_url     TEXT         NOT NULL DEFAULT '',
                created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                updated_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                UNIQUE (sport, year, set_name, product_type)
            )
        """),

        ("sealed_product_odds table", """
            CREATE TABLE IF NOT EXISTS sealed_product_odds (
                id                BIGSERIAL    PRIMARY KEY,
                sealed_product_id BIGINT       NOT NULL REFERENCES sealed_products(id) ON DELETE CASCADE,
                card_type         TEXT         NOT NULL,
                odds_ratio        TEXT         NOT NULL DEFAULT '',
                created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                UNIQUE (sealed_product_id, card_type)
            )
        """),

        ("index on sealed_products (sport, year, set_name)",
         "CREATE INDEX IF NOT EXISTS idx_sealed_products_set "
         "ON sealed_products (sport, year, set_name)"),
    ]

    for label, sql in steps:
        try:
            print(f"  -> {label}...", end=" ", flush=True)
            cur.execute(sql)
            print("ok")
        except Exception as e:
            print(f"SKIPPED ({e})")

    cur.close()
    conn.close()
    print("migrate_add_sealed_products: done")


if __name__ == "__main__":
    run()
