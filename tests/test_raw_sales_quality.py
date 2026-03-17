"""DB quality tests for market_raw_sales — Phase 0/1/2.

Requires DATABASE_URL. Run with:
    pytest tests/test_raw_sales_quality.py -v -m db

Checks:
 - Table exists and has data
 - Normalized columns exist
 - Source values are all known
 - Prices are positive
 - No boilerplate titles
 - SCD Type 2: every row is unique by listing_hash
 - Search indexes exist (pg_trgm, search_vector)
"""
import pytest

pytestmark = pytest.mark.db

KNOWN_SOURCES = {"ebay", "goldin", "heritage", "pwcc", "fanatics", "pristine", "myslabs"}


class TestRawSalesExists:

    def test_table_has_data(self, db):
        db.execute("SELECT COUNT(*) AS cnt FROM market_raw_sales")
        assert db.fetchone()["cnt"] > 0, "market_raw_sales is empty — no scrapes have run"

    def test_normalized_columns_exist(self, db):
        db.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'market_raw_sales'
        """)
        cols = {r["column_name"] for r in db.fetchall()}
        required = {"grade", "grade_company", "grade_numeric", "serial_number",
                    "print_run", "source", "lot_url", "lot_id",
                    "hammer_price", "buyer_premium_pct", "is_auction", "raw_metadata"}
        missing = required - cols
        assert not missing, f"Missing columns: {missing}"

    def test_source_column_has_no_nulls(self, db):
        db.execute("SELECT COUNT(*) AS cnt FROM market_raw_sales WHERE source IS NULL")
        assert db.fetchone()["cnt"] == 0, "Rows with NULL source found"

    def test_all_sources_are_known(self, db):
        db.execute("SELECT DISTINCT source FROM market_raw_sales")
        found = {r["source"] for r in db.fetchall()}
        unknown = found - KNOWN_SOURCES
        assert not unknown, f"Unknown source values: {unknown}"


class TestRawSalesPriceQuality:

    def test_no_negative_prices(self, db):
        db.execute("SELECT COUNT(*) AS cnt FROM market_raw_sales WHERE price_val < 0")
        assert db.fetchone()["cnt"] == 0

    def test_no_zero_prices(self, db):
        db.execute("SELECT COUNT(*) AS cnt FROM market_raw_sales WHERE price_val = 0")
        assert db.fetchone()["cnt"] == 0, "Zero-price rows found — scraper may have a parsing bug"

    def test_suspiciously_high_price_rate(self, db):
        """Less than 0.1% of sales should be over $50,000 (catches malformed prices)."""
        db.execute("SELECT COUNT(*) AS total FROM market_raw_sales")
        total = db.fetchone()["total"]
        db.execute("SELECT COUNT(*) AS cnt FROM market_raw_sales WHERE price_val > 50000")
        high = db.fetchone()["cnt"]
        if total > 1000:
            rate = high / total
            assert rate < 0.001, f"{rate:.4%} of sales are over $50k — possible price parsing issue"


class TestRawSalesTitleQuality:

    def test_no_ebay_boilerplate(self, db):
        """'Opens in a new window or tab' was a known eBay scraping artifact."""
        db.execute("""
            SELECT COUNT(*) AS cnt FROM market_raw_sales
            WHERE title ILIKE '%opens in a new window%'
               OR title ILIKE '%new window or tab%'
        """)
        assert db.fetchone()["cnt"] == 0, "eBay boilerplate text found in titles"

    def test_no_empty_titles(self, db):
        db.execute("""
            SELECT COUNT(*) AS cnt FROM market_raw_sales
            WHERE title IS NULL OR trim(title) = ''
        """)
        assert db.fetchone()["cnt"] == 0


class TestRawSalesSCDType2:

    def test_no_duplicate_listing_hash(self, db):
        """listing_hash must be unique — SCD Type 2 append-only integrity."""
        db.execute("""
            SELECT COUNT(*) AS cnt FROM (
                SELECT listing_hash, COUNT(*) AS n
                FROM market_raw_sales
                WHERE listing_hash IS NOT NULL
                GROUP BY listing_hash HAVING COUNT(*) > 1
            ) dups
        """)
        assert db.fetchone()["cnt"] == 0, "Duplicate listing_hash values found — deduplication broken"

    def test_all_sales_linked_to_catalog(self, db):
        db.execute("""
            SELECT COUNT(*) AS cnt FROM market_raw_sales mrs
            LEFT JOIN card_catalog cc ON cc.id = mrs.card_catalog_id
            WHERE cc.id IS NULL
        """)
        assert db.fetchone()["cnt"] == 0, "Orphaned market_raw_sales rows (no matching card_catalog entry)"


class TestSearchIndexes:

    def test_pg_trgm_extension_enabled(self, db):
        db.execute("SELECT extname FROM pg_extension WHERE extname = 'pg_trgm'")
        assert db.fetchone() is not None, "pg_trgm extension not enabled"

    def test_search_vector_column_exists(self, db):
        db.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'card_catalog' AND column_name = 'search_vector'
        """)
        assert db.fetchone() is not None, "search_vector column missing on card_catalog"

    def test_gin_index_on_search_vector(self, db):
        db.execute("""
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'card_catalog'
              AND indexname = 'idx_cc_search_vector'
        """)
        assert db.fetchone() is not None, "GIN index idx_cc_search_vector missing"

    def test_search_log_table_exists(self, db):
        db.execute("""
            SELECT COUNT(*) AS cnt FROM information_schema.tables
            WHERE table_name = 'search_log'
        """)
        assert db.fetchone()["cnt"] == 1, "search_log table missing"

    def test_auction_unmatched_table_exists(self, db):
        db.execute("""
            SELECT COUNT(*) AS cnt FROM information_schema.tables
            WHERE table_name = 'auction_unmatched'
        """)
        assert db.fetchone()["cnt"] == 1, "auction_unmatched table missing"
