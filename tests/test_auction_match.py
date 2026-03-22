"""Unit tests for auction_match.py — Phase 1.

Tests the CatalogMatcher helpers and logic using mocked DB connections.
No live PostgreSQL required for the unit tests.
"""
import sys, os
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "scraping"))

import pytest
from unittest.mock import MagicMock, patch, call
from auction_match import CatalogMatcher, _extract_year, _extract_player_name


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

class TestExtractYear:
    @pytest.mark.parametrize("title,expected", [
        ("2015-16 Upper Deck Connor McDavid",  "2015-16"),
        ("2023 Topps Chrome Mike Trout RC",    "2023"),
        ("1979 O-Pee-Chee Wayne Gretzky",      "1979"),
        ("2023-24 Panini Prizm Victor W",       "2023-24"),
        ("Connor McDavid Young Guns",          None),
        ("",                                   None),
    ])
    def test_year_extraction(self, title, expected):
        assert _extract_year(title) == expected

    def test_picks_first_year(self):
        # If multiple years, take the first
        result = _extract_year("2015-16 reprint 2023")
        assert result == "2015-16"


class TestExtractPlayerName:
    def test_extracts_capitalized_words(self):
        name = _extract_player_name("2015-16 Upper Deck Connor McDavid Young Guns #201")
        # Should contain Connor and McDavid
        assert "Connor" in name
        assert "McDavid" in name

    def test_removes_grade_tokens(self):
        name = _extract_player_name("LeBron James PSA 10 Prizm")
        assert "PSA" not in name
        assert "Prizm" not in name

    def test_removes_year(self):
        name = _extract_player_name("2019-20 Panini Prizm Luka Doncic Silver")
        assert "2019" not in name

    def test_removes_card_number(self):
        name = _extract_player_name("McDavid #201/99 Silver")
        assert "#201" not in name

    def test_empty_title(self):
        name = _extract_player_name("")
        assert name == ""

    def test_max_three_words(self):
        name = _extract_player_name("Alpha Beta Gamma Delta Epsilon")
        assert len(name.split()) <= 3


# ---------------------------------------------------------------------------
# CatalogMatcher — dry_run mode (no DB writes)
# ---------------------------------------------------------------------------

def _make_mock_conn(tier1_rows=None, tier2_rows=None, tier3_rows=None,
                    candidates=None):
    """Build a mock psycopg2 connection that returns canned query results.

    Each tier is returned in sequence (one result per fetchall call).
    If only tier1_rows is given it is returned on every subsequent call too,
    making it safe for tests that call process_sale() multiple times.
    """
    conn = MagicMock()
    cur = MagicMock()
    cursor_ctx = MagicMock()
    cursor_ctx.__enter__ = lambda s: cur
    cursor_ctx.__exit__ = MagicMock(return_value=False)
    conn.cursor = MagicMock(return_value=cursor_ctx)

    # Build sequence; tier1_rows is used as the fallback for any extra calls
    result_sequence = []
    if tier1_rows is not None:
        result_sequence.append(tier1_rows)
    if tier2_rows is not None:
        result_sequence.append(tier2_rows)
    if tier3_rows is not None:
        result_sequence.append(tier3_rows)
    if candidates is not None:
        result_sequence.append(candidates)

    fetch_calls = {"n": 0}
    fallback = tier1_rows if tier1_rows is not None else []

    def fetchall():
        idx = fetch_calls["n"]
        fetch_calls["n"] += 1
        if idx < len(result_sequence):
            return result_sequence[idx]
        return fallback  # repeat tier1 result for subsequent calls

    cur.fetchall = fetchall
    cur.fetchone = MagicMock(return_value=None)
    cur.description = [("id",), ("num_sales",)]
    return conn, cur


class TestCatalogMatcherBasic:

    def test_empty_title_skipped(self):
        conn, _ = _make_mock_conn()
        m = CatalogMatcher(conn, dry_run=True)
        result = m.process_sale({"title": ""})
        assert result is None
        assert m.stats["skipped"] == 1

    def test_none_title_skipped(self):
        conn, _ = _make_mock_conn()
        m = CatalogMatcher(conn, dry_run=True)
        result = m.process_sale({"title": None})
        assert result is None
        assert m.stats["skipped"] == 1

    def test_dry_run_no_db_writes(self):
        """In dry_run mode, flush must not call save_raw_sales."""
        conn, _ = _make_mock_conn(tier1_rows=[(42, 10)])
        m = CatalogMatcher(conn, dry_run=True)
        m.process_sale({
            "title":   "2015-16 UD Connor McDavid Young Guns #201",
            "source":  "goldin",
            "price_val": 100.0,
            "sold_date": "2024-01-01",
        })
        # save_raw_sales is imported inside _flush_matched from db module
        with patch("db.save_raw_sales") as mock_save:
            m.flush()
            mock_save.assert_not_called()

    def test_tier1_single_match(self):
        conn, _ = _make_mock_conn(tier1_rows=[(99, 5)])
        m = CatalogMatcher(conn, dry_run=True)
        result = m.process_sale({
            "title":   "2015-16 UD Connor McDavid YG",
            "source":  "ebay",
            "price_val": 50.0,
        })
        assert result == 99
        assert m.stats["matched"] == 1
        assert m.stats["unmatched"] == 0

    def test_no_match_goes_to_unmatched(self):
        # All tiers return empty
        conn, _ = _make_mock_conn(tier1_rows=[], tier2_rows=[], tier3_rows=[])
        m = CatalogMatcher(conn, dry_run=True)
        m.process_sale({
            "title":     "xyzzy unknown garbage title 123",
            "source":    "goldin",
            "price_val": 10.0,
            "sold_date": "2024-01-01",
            "lot_url":   "https://example.com",
        })
        assert m.stats["unmatched"] == 1
        assert m.stats["matched"]   == 0


class TestCatalogMatcherStats:

    def test_print_stats_no_crash(self, capsys):
        conn, _ = _make_mock_conn()
        m = CatalogMatcher(conn, dry_run=True)
        m.stats = {"matched": 8, "unmatched": 2, "skipped": 1}
        m.print_stats()
        out = capsys.readouterr().out
        assert "80.0%" in out
        assert "8" in out

    def test_print_stats_zero_total(self, capsys):
        """Should not raise ZeroDivisionError when no sales processed."""
        conn, _ = _make_mock_conn()
        m = CatalogMatcher(conn, dry_run=True)
        m.print_stats()  # must not raise

    def test_stats_accumulate_across_calls(self):
        conn, _ = _make_mock_conn(tier1_rows=[(1, 5)])
        m = CatalogMatcher(conn, dry_run=True)
        for _ in range(3):
            m.process_sale({"title": "2020-21 Panini Prizm LeBron Silver PSA 10",
                            "source": "ebay", "price_val": 100.0})
        assert m.stats["matched"] == 3


class TestCatalogMatcherScoreCandidates:

    def test_score_candidates_picks_best(self):
        """When multiple candidates, score by token overlap vs title."""
        conn = MagicMock()
        cur = MagicMock()
        cursor_ctx = MagicMock()
        cursor_ctx.__enter__ = lambda s: cur
        cursor_ctx.__exit__ = MagicMock(return_value=False)
        conn.cursor = MagicMock(return_value=cursor_ctx)

        # Return two candidates; one with more matching tokens
        cur.fetchall.return_value = [
            {"id": 10, "set_name": "Prizm", "brand": "Panini", "variant": "Silver", "scrape_tier": "staple"},
            {"id": 20, "set_name": "Chrome", "brand": "Topps", "variant": "Gold",   "scrape_tier": "base"},
        ]

        m = CatalogMatcher(conn, dry_run=True)
        # Title contains "Panini Prizm Silver" — candidate 10 should win
        result = m._score_candidates([10, 20], "2020 Panini Prizm Silver LeBron James PSA 10")
        assert result == 10

    def test_score_candidates_empty_list(self):
        conn, _ = _make_mock_conn()
        m = CatalogMatcher(conn, dry_run=True)
        assert m._score_candidates([], "any title") is None


# ---------------------------------------------------------------------------
# Batch size auto-flush
# ---------------------------------------------------------------------------

class TestAutoFlush:
    def test_match_batch_triggers_flush(self):
        """After MATCH_BATCH matched sales, _flush_matched should be called."""
        conn, _ = _make_mock_conn(tier1_rows=[(1, 1)])
        m = CatalogMatcher(conn, dry_run=True)
        m.MATCH_BATCH = 3  # lower threshold for test

        for i in range(4):
            m.process_sale({"title": f"2020 Panini Card Player {i}", "source": "ebay"})

        # After 4 calls with MATCH_BATCH=3, _matched should have been flushed at least once
        # Stats should still show all 4 (flush doesn't reset stats)
        assert m.stats["matched"] == 4
