"""Tests for api/routers/search.py — Phase 2 & 3.

Covers:
 - _detect_grade / _strip_grade pure helpers
 - _build_sales_where parameterisation
 - GET /api/search (mocked DB)
 - GET /api/search/suggest (mocked DB)
 - GET /api/search/sources (mocked DB)
 - GET /api/search/trending (mocked DB)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from contextlib import contextmanager
from datetime import date

from fastapi.testclient import TestClient
from datetime import date as _date


# ---------------------------------------------------------------------------
# Pure helpers — no DB
# ---------------------------------------------------------------------------

from api.routers.search import _detect_grade, _strip_grade, _build_sales_where


class TestDetectGrade:
    @pytest.mark.parametrize("q,expected", [
        ("Connor McDavid PSA 10",          "PSA 10"),
        ("leBron James psa 9",             "PSA 9"),
        ("Bedard BGS 9.5 Young Guns",      "BGS 9.5"),
        ("Mahomes SGC 10 RC",              "SGC 10"),
        ("Wembanyama CGC 9.5",             "CGC 9.5"),
        ("LeBron gem mt 10",               "GEM MT 10"),
        ("LeBron gem mint",                "GEM MINT"),
        ("Connor McDavid Young Guns",      None),
        ("",                               None),
    ])
    def test_detect_grade(self, q, expected):
        assert _detect_grade(q) == expected

    def test_returns_uppercase_company(self):
        assert _detect_grade("card psa 10").startswith("PSA")

    def test_returns_none_for_no_grade(self):
        assert _detect_grade("random card name") is None


class TestStripGrade:
    def test_strips_psa(self):
        result = _strip_grade("Connor McDavid PSA 10")
        assert "PSA" not in result
        assert "Connor" in result
        assert "McDavid" in result

    def test_strips_bgs(self):
        result = _strip_grade("Bedard BGS 9.5 YG")
        assert "BGS" not in result

    def test_strips_gem_mint(self):
        result = _strip_grade("LeBron gem mint Silver")
        assert "gem" not in result.lower()

    def test_cleans_whitespace(self):
        result = _strip_grade("Card  PSA  10  Title")
        assert "  " not in result

    def test_no_grade_unchanged(self):
        result = _strip_grade("Connor McDavid Young Guns")
        assert result == "Connor McDavid Young Guns"


class TestBuildSalesWhere:
    def test_with_catalog_ids(self):
        where, params = _build_sales_where([1, 2, 3], [], None, None, None, None, None, False, "q")
        assert "card_catalog_id = ANY(%s)" in where
        assert [1, 2, 3] in params

    def test_empty_catalog_ids_falls_back_to_title(self):
        where, params = _build_sales_where([], [], None, None, None, None, None, False, "LeBron")
        assert "mrs.title ILIKE %s" in where
        assert "%LeBron%" in params

    def test_source_filter(self):
        where, params = _build_sales_where([1], ["goldin", "pwcc"], None, None, None, None, None, False, "q")
        assert "mrs.source = ANY(%s)" in where
        assert ["goldin", "pwcc"] in params

    def test_price_range(self):
        where, params = _build_sales_where([1], [], None, None, 50.0, 200.0, None, False, "q")
        assert "mrs.price_val >= %s" in where
        assert "mrs.price_val <= %s" in where
        assert 50.0 in params
        assert 200.0 in params

    def test_date_range(self):
        d1, d2 = date(2024, 1, 1), date(2024, 12, 31)
        where, params = _build_sales_where([1], [], d1, d2, None, None, None, False, "q")
        assert "mrs.sold_date >= %s" in where
        assert "mrs.sold_date <= %s" in where
        assert d1 in params
        assert d2 in params

    def test_grade_filter(self):
        where, params = _build_sales_where([1], [], None, None, None, None, "PSA 10", False, "q")
        assert "mrs.grade ILIKE %s" in where

    def test_graded_only(self):
        where, params = _build_sales_where([1], [], None, None, None, None, None, True, "q")
        assert "mrs.grade IS NOT NULL" in where

    def test_no_conditions_returns_true(self):
        where, params = _build_sales_where([], [], None, None, None, None, None, False, "")
        # Falls back to title ILIKE with empty raw_query
        assert "ILIKE" in where or where == "1=1"


# ---------------------------------------------------------------------------
# API endpoint tests (mocked DB)
# ---------------------------------------------------------------------------

def _mock_db_factory(count_result=0, query_results=None, source_results=None,
                     suggest_results=None, trending_results=None):
    """Return a context-manager mock for get_db() that returns canned cursor data."""
    conn = MagicMock()
    cur = MagicMock()

    call_seq = {"n": 0}
    results = []

    # For search endpoint: count then rows
    if query_results is not None:
        results.append((count_result,))     # COUNT(*) fetchone
        results.append(query_results)       # main query fetchall
    if source_results is not None:
        results.append(source_results)
    if suggest_results is not None:
        results.append(suggest_results)
    if trending_results is not None:
        results.append(trending_results)

    fetchone_calls = {"n": 0}
    fetchall_calls = {"n": 0}

    def fetchone():
        idx = fetchone_calls["n"]
        fetchone_calls["n"] += 1
        if idx < len(results) and not isinstance(results[idx], list):
            return results[idx]
        return (0,)

    def fetchall():
        idx = fetchall_calls["n"]
        fetchall_calls["n"] += 1
        for i, r in enumerate(results):
            if isinstance(r, list):
                fetchall_calls["n"] = i + 1
                return r
        return []

    cur.fetchone = fetchone
    cur.fetchall = fetchall
    cur.description = [
        ("id",), ("card_catalog_id",), ("sold_date",), ("price_val",),
        ("title",), ("source",), ("grade",), ("grade_company",),
        ("grade_numeric",), ("serial_number",), ("print_run",), ("lot_url",),
        ("image_url",), ("hammer_price",), ("buyer_premium_pct",), ("is_auction",),
        ("player_name",), ("year",), ("set_name",), ("variant",),
        ("sport",), ("is_rookie",),
    ]
    cur.execute = MagicMock()

    cursor_ctx = MagicMock()
    cursor_ctx.__enter__ = lambda s: cur
    cursor_ctx.__exit__ = MagicMock(return_value=False)
    conn.cursor = MagicMock(return_value=cursor_ctx)
    conn.autocommit = False

    @contextmanager
    def mock_get_db():
        yield conn

    return mock_get_db


@pytest.fixture
def api_client():
    """FastAPI TestClient with all DB calls patched out."""
    from api.main import app
    # Clear all TTL caches before each test
    import api.routers.search as sr
    sr._search_cache.clear()
    sr._suggest_cache.clear()
    sr._sources_cache.clear()
    sr._trending_cache.clear()
    return TestClient(app, raise_server_exceptions=True)


class TestSearchEndpoint:

    def test_search_requires_q(self, api_client):
        resp = api_client.get("/api/search")
        assert resp.status_code == 422  # missing required param

    def test_search_q_too_short(self, api_client):
        resp = api_client.get("/api/search?q=a")
        assert resp.status_code == 422

    def test_search_no_results(self, api_client):
        mock_db = _mock_db_factory(count_result=0, query_results=[])
        with patch("api.routers.search.get_db", mock_db):
            resp = api_client.get("/api/search?q=McDavid")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"]   == 0
        assert data["results"] == []
        assert data["query"]   == "McDavid"

    def test_search_returns_results(self, api_client):
        row = (
            1, 42, _date(2024, 1, 15), 150.0, "Connor McDavid PSA 10",
            "ebay", "PSA 10", "PSA", 10.0, None, None,
            "https://ebay.com/item/1", None, None, None, False,
            "Connor McDavid", "2015-16", "Upper Deck", "Young Guns", "NHL", False,
        )
        mock_db = _mock_db_factory(count_result=1, query_results=[row])
        # Patch phase-1 catalog resolver so we skip that DB call
        with patch("api.routers.search._resolve_catalog_ids", return_value=([42], [])):
            with patch("api.routers.search.get_db", mock_db):
                resp = api_client.get("/api/search?q=McDavid")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["results"]) == 1
        r = data["results"][0]
        assert r["player_name"] == "Connor McDavid"
        assert r["grade"]       == "PSA 10"
        assert r["price_val"]   == 150.0

    def test_search_detects_grade_in_query(self, api_client):
        mock_db = _mock_db_factory(count_result=0, query_results=[])
        with patch("api.routers.search.get_db", mock_db):
            resp = api_client.get("/api/search?q=McDavid+PSA+10")
        data = resp.json()
        assert data["detected_grade"] == "PSA 10"

    def test_search_sort_price_desc(self, api_client):
        mock_db = _mock_db_factory(count_result=0, query_results=[])
        with patch("api.routers.search.get_db", mock_db):
            resp = api_client.get("/api/search?q=LeBron&sort=price_desc")
        assert resp.status_code == 200

    def test_search_pagination_params(self, api_client):
        mock_db = _mock_db_factory(count_result=100, query_results=[])
        with patch("api.routers.search.get_db", mock_db):
            resp = api_client.get("/api/search?q=LeBron&limit=10&offset=20")
        assert resp.status_code == 200
        data = resp.json()
        assert data["limit"]  == 10
        assert data["offset"] == 20

    def test_search_multiple_sources(self, api_client):
        mock_db = _mock_db_factory(count_result=0, query_results=[])
        with patch("api.routers.search.get_db", mock_db):
            resp = api_client.get("/api/search?q=LeBron&source=goldin&source=pwcc")
        assert resp.status_code == 200


class TestSuggestEndpoint:

    def test_suggest_requires_q(self, api_client):
        resp = api_client.get("/api/search/suggest")
        assert resp.status_code == 422

    def test_suggest_q_too_short(self, api_client):
        resp = api_client.get("/api/search/suggest?q=a")
        assert resp.status_code == 422

    def test_suggest_returns_list(self, api_client):
        rows = [("Connor McDavid", "2015-16", "Upper Deck", "NHL", 500)]
        mock_db = _mock_db_factory(suggest_results=rows)
        with patch("api.routers.search.get_db", mock_db):
            resp = api_client.get("/api/search/suggest?q=McDavid")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["display_name"] == "Connor McDavid 2015-16"
        assert data[0]["player_name"]  == "Connor McDavid"

    def test_suggest_empty_db_returns_empty_list(self, api_client):
        mock_db = _mock_db_factory(suggest_results=[])
        with patch("api.routers.search.get_db", mock_db):
            resp = api_client.get("/api/search/suggest?q=Unknown")
        assert resp.status_code == 200
        assert resp.json() == []


class TestSourcesEndpoint:

    def test_sources_returns_list(self, api_client):
        rows = [("ebay", 50000, None), ("goldin", 1500, None)]
        mock_db = _mock_db_factory(source_results=rows)
        with patch("api.routers.search.get_db", mock_db):
            resp = api_client.get("/api/search/sources")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["key"]        == "ebay"
        assert data[0]["label"]      == "eBay"
        assert data[0]["sale_count"] == 50000

    def test_sources_known_labels(self, api_client):
        known = [("ebay",1,None), ("goldin",1,None), ("heritage",1,None), ("pwcc",1,None),
                 ("fanatics",1,None), ("pristine",1,None), ("myslabs",1,None)]
        mock_db = _mock_db_factory(source_results=known)
        with patch("api.routers.search.get_db", mock_db):
            resp = api_client.get("/api/search/sources")
        labels = {r["key"]: r["label"] for r in resp.json()}
        assert labels["ebay"]     == "eBay"
        assert labels["goldin"]   == "Goldin"
        assert labels["heritage"] == "Heritage"
        assert labels["pwcc"]     == "PWCC"
        assert labels["fanatics"] == "Fanatics"
        assert labels["pristine"] == "Pristine"
        assert labels["myslabs"]  == "MySlabs"


class TestTrendingEndpoint:

    def test_trending_returns_list(self, api_client):
        rows = [("connor mcdavid", 42), ("lebron james", 31), ("mike trout", 18)]
        mock_db = _mock_db_factory(trending_results=rows)
        with patch("api.routers.search.get_db", mock_db):
            resp = api_client.get("/api/search/trending")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["query"]   == "connor mcdavid"
        assert data[0]["searches"] == 42

    def test_trending_empty_is_ok(self, api_client):
        mock_db = _mock_db_factory(trending_results=[])
        with patch("api.routers.search.get_db", mock_db):
            resp = api_client.get("/api/search/trending")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_trending_limit_param(self, api_client):
        rows = [("card", i) for i in range(20)]
        mock_db = _mock_db_factory(trending_results=rows)
        with patch("api.routers.search.get_db", mock_db):
            resp = api_client.get("/api/search/trending?limit=5")
        assert resp.status_code == 200
