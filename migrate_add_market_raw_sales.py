"""Migration: create market_raw_sales table.

Stores every individual eBay sold listing ever captured for a catalog card.
This is the ground-truth record — aggregated prices in market_prices and
market_price_history can always be recomputed from this table.

Schema:
  - card_catalog_id  FK to card_catalog
  - sold_date        date the listing closed on eBay (NULL if unparseable)
  - price_val        final sale price in USD
  - title            full eBay listing title (used for dedup + variant filtering)
  - scraped_at       when our scraper captured this sale

Dedup key: (card_catalog_id, sold_date, title) — re-scraping the same card
won't insert duplicate rows for listings we've already recorded.

Runs automatically on every Railway deploy (idempotent — safe to re-run).
"""
import os
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]


def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS market_raw_sales (
            id              BIGSERIAL    PRIMARY KEY,
            card_catalog_id BIGINT       NOT NULL REFERENCES card_catalog(id) ON DELETE CASCADE,
            sold_date       DATE,
            price_val       NUMERIC      NOT NULL,
            title           TEXT         NOT NULL DEFAULT '',
            scraped_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            UNIQUE (card_catalog_id, sold_date, title)
        );
    """)
    print("market_raw_sales table created (or already existed)")

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_market_raw_sales_card
            ON market_raw_sales (card_catalog_id, sold_date DESC);
    """)
    print("idx_market_raw_sales_card index created (or already existed)")

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_market_raw_sales_date
            ON market_raw_sales (sold_date DESC);
    """)
    print("idx_market_raw_sales_date index created (or already existed)")

    cur.close()
    conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"migrate_add_market_raw_sales: ERROR — {e}")
