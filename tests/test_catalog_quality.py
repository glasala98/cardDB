"""
Data quality tests for card_catalog, market_prices, and market_price_history.

Run:
    pytest tests/test_catalog_quality.py -v
"""
import pytest

SPORTS = ["NHL", "MLB", "NFL", "NBA"]

# Minimum acceptable card counts per sport
MIN_CARDS = {
    "NHL": 300_000,
    "MLB": 1_000_000,
    "NFL": 600_000,
    "NBA": 250_000,
}

# Earliest year we expect full modern-era coverage from
MODERN_ERA_START = {
    "NHL": 1951,
    "MLB": 1952,
    "NFL": 1948,
    "NBA": 1967,
}


# ── Catalog size ───────────────────────────────────────────────────────────────

def test_total_catalog_exceeds_2m(db):
    db.execute("SELECT COUNT(*) AS cnt FROM card_catalog")
    assert db.fetchone()["cnt"] >= 2_000_000


@pytest.mark.parametrize("sport", SPORTS)
def test_card_count_per_sport(db, sport):
    db.execute("SELECT COUNT(*) AS cnt FROM card_catalog WHERE sport = %s", (sport,))
    count = db.fetchone()["cnt"]
    assert count >= MIN_CARDS[sport], f"{sport}: {count:,} cards, expected >= {MIN_CARDS[sport]:,}"


# ── Year coverage ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sport", SPORTS)
def test_modern_era_year_coverage(db, sport):
    """No completely missing years within the modern card era."""
    db.execute("""
        SELECT DISTINCT SPLIT_PART(year, '-', 1)::int AS yr
        FROM card_catalog WHERE sport = %s AND year ~ '^[0-9]{4}'
    """, (sport,))
    covered = {r["yr"] for r in db.fetchall()}
    start = MODERN_ERA_START[sport]
    missing = [y for y in range(start, 2025) if y not in covered]
    assert not missing, f"{sport} missing years in modern era: {missing}"


# ── Data quality ───────────────────────────────────────────────────────────────

def test_no_empty_player_names(db):
    db.execute("""
        SELECT COUNT(*) AS cnt FROM card_catalog
        WHERE player_name IS NULL OR player_name = ''
    """)
    assert db.fetchone()["cnt"] == 0, "Cards with empty player_name found"


def test_no_empty_set_names(db):
    db.execute("""
        SELECT COUNT(*) AS cnt FROM card_catalog
        WHERE set_name IS NULL OR set_name = ''
    """)
    assert db.fetchone()["cnt"] == 0, "Cards with empty set_name found"


def test_no_checklist_artifacts(db):
    """set_name cleanup removed CLI/CBC 'Checklist Guide' suffixes."""
    db.execute("""
        SELECT COUNT(*) AS cnt FROM card_catalog
        WHERE set_name ILIKE '%checklist%'
    """)
    count = db.fetchone()["cnt"]
    assert count < 5_000, f"{count:,} set names still contain 'checklist' — cleanup may be needed"


@pytest.mark.parametrize("sport", SPORTS)
def test_no_duplicate_cards_within_set(db, sport):
    """No exact duplicate (set, card_number, player, variant) within a sport."""
    db.execute("""
        SELECT COUNT(*) AS cnt FROM (
            SELECT year, set_name, card_number, player_name, variant, COUNT(*) AS n
            FROM card_catalog WHERE sport = %s
            GROUP BY year, set_name, card_number, player_name, variant
            HAVING COUNT(*) > 1
        ) dups
    """, (sport,))
    count = db.fetchone()["cnt"]
    assert count == 0, f"{sport}: {count:,} duplicate card entries found"


# ── Market prices ──────────────────────────────────────────────────────────────

def test_market_prices_exist(db):
    db.execute("SELECT COUNT(*) AS cnt FROM market_prices")
    assert db.fetchone()["cnt"] > 0, "market_prices table is empty — scraper has not run"


def test_market_prices_no_zero_values(db):
    """All rows in market_prices should have a positive fair_value."""
    db.execute("SELECT COUNT(*) AS cnt FROM market_prices WHERE fair_value <= 0")
    assert db.fetchone()["cnt"] == 0, "market_prices rows with fair_value <= 0 found"


def test_market_prices_all_linked_to_catalog(db):
    """Every market_prices row must link to a valid card_catalog entry."""
    db.execute("""
        SELECT COUNT(*) AS cnt FROM market_prices mp
        LEFT JOIN card_catalog cc ON cc.id = mp.card_catalog_id
        WHERE cc.id IS NULL
    """)
    assert db.fetchone()["cnt"] == 0, "Orphaned market_prices rows (no matching card_catalog entry)"


# ── SCD Type 2 history ─────────────────────────────────────────────────────────

def test_history_exists(db):
    db.execute("SELECT COUNT(*) AS cnt FROM market_price_history")
    assert db.fetchone()["cnt"] > 0, "market_price_history is empty"


def test_scd_type2_no_consecutive_duplicate_prices(db):
    """SCD Type 2: consecutive history rows for the same card must not share fair_value."""
    db.execute("""
        WITH ordered AS (
            SELECT card_catalog_id, fair_value,
                   LAG(fair_value) OVER (
                       PARTITION BY card_catalog_id ORDER BY scraped_at
                   ) AS prev_fair_value
            FROM market_price_history
        )
        SELECT COUNT(*) AS cnt FROM ordered
        WHERE fair_value = prev_fair_value AND prev_fair_value IS NOT NULL
    """)
    count = db.fetchone()["cnt"]
    assert count == 0, f"{count:,} consecutive history rows with identical fair_value — SCD Type 2 not enforced"


def test_history_linked_to_catalog(db):
    db.execute("""
        SELECT COUNT(*) AS cnt FROM market_price_history mph
        LEFT JOIN card_catalog cc ON cc.id = mph.card_catalog_id
        WHERE cc.id IS NULL
    """)
    assert db.fetchone()["cnt"] == 0, "Orphaned market_price_history rows"


def test_history_prices_positive(db):
    db.execute("SELECT COUNT(*) AS cnt FROM market_price_history WHERE fair_value <= 0")
    assert db.fetchone()["cnt"] == 0
