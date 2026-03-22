"""Unit tests for export_ml_dataset.py — Phase 3.

Tests the pure helper functions and CSV output structure.
No database required.
"""
import sys, os, csv, tempfile
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "scripts"))
sys.path.insert(0, _ROOT)  # db.py lives at root

import pytest
from unittest.mock import patch, MagicMock
from contextlib import contextmanager
from datetime import date

from export_ml_dataset import _zscore, COLUMNS, export


class TestZscore:
    def test_above_mean(self):
        z = _zscore(130.0, 100.0, 15.0)
        assert z == pytest.approx(2.0)

    def test_below_mean(self):
        z = _zscore(85.0, 100.0, 15.0)
        assert z == pytest.approx(-1.0)

    def test_at_mean(self):
        assert _zscore(100.0, 100.0, 15.0) == pytest.approx(0.0)

    def test_zero_std_returns_none(self):
        assert _zscore(100.0, 100.0, 0.0) is None

    def test_none_value_returns_none(self):
        assert _zscore(None, 100.0, 15.0) is None


class TestColumns:
    def test_all_required_columns_present(self):
        required = {
            "sale_id", "sold_date", "price_val", "source", "is_auction",
            "grade", "grade_company", "grade_numeric",
            "serial_number", "print_run",
            "player_name", "year", "set_name", "variant", "sport", "is_rookie",
            "scrape_tier", "days_since_sold", "price_zscore_player",
        }
        assert required == set(COLUMNS)

    def test_column_count(self):
        assert len(COLUMNS) == 19


class TestExportFunction:
    """Integration-style tests using mocked DB."""

    def _make_rows(self, n=5, player="Connor McDavid", price=100.0):
        sold = date(2024, 1, 15)
        return [
            (i, sold, price + i, "ebay", False, "PSA 10", "PSA", 10.0,
             None, None, player, "2015-16", "Upper Deck", "Young Guns", "NHL", False, "staple")
            for i in range(n)
        ]

    @contextmanager
    def _mock_db(self, rows):
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchall.return_value = rows
        # export_ml_dataset.py uses `cur = conn.cursor()` directly (not a context manager)
        conn.cursor.return_value = cur

        @contextmanager
        def fake_get_db():
            yield conn
        with patch("export_ml_dataset.get_db", fake_get_db):
            yield

    def test_export_produces_csv(self):
        rows = self._make_rows(5)
        with tempfile.NamedTemporaryFile(suffix=".csv", mode='w', delete=False) as f:
            out = f.name
        with self._mock_db(rows):
            export(out, days=365, min_sales=2)
        with open(out, newline='') as f:
            reader = csv.DictReader(f)
            written = list(reader)
        os.unlink(out)
        assert len(written) == 5

    def test_export_csv_has_all_columns(self):
        rows = self._make_rows(3)
        with tempfile.NamedTemporaryFile(suffix=".csv", mode='w', delete=False) as f:
            out = f.name
        with self._mock_db(rows):
            export(out, days=365, min_sales=2)
        with open(out, newline='') as f:
            reader = csv.DictReader(f)
            header = reader.fieldnames
        os.unlink(out)
        assert set(header) == set(COLUMNS)

    def test_export_skips_players_below_min_sales(self):
        rows = self._make_rows(2, player="Rare Player", price=500.0)
        with tempfile.NamedTemporaryFile(suffix=".csv", mode='w', delete=False) as f:
            out = f.name
        with self._mock_db(rows):
            # min_sales=3, but only 2 rows — should be skipped
            export(out, days=365, min_sales=3)
        with open(out, newline='') as f:
            written = list(csv.DictReader(f))
        os.unlink(out)
        assert len(written) == 0

    def test_export_includes_players_meeting_min_sales(self):
        rows = self._make_rows(4, player="LeBron James", price=200.0)
        with tempfile.NamedTemporaryFile(suffix=".csv", mode='w', delete=False) as f:
            out = f.name
        with self._mock_db(rows):
            export(out, days=365, min_sales=3)
        with open(out, newline='') as f:
            written = list(csv.DictReader(f))
        os.unlink(out)
        assert len(written) == 4

    def test_zscore_is_numeric_in_output(self):
        rows = self._make_rows(5, price=100.0)
        with tempfile.NamedTemporaryFile(suffix=".csv", mode='w', delete=False) as f:
            out = f.name
        with self._mock_db(rows):
            export(out, days=365, min_sales=2)
        with open(out, newline='') as f:
            first_row = next(csv.DictReader(f))
        os.unlink(out)
        z = first_row["price_zscore_player"]
        assert z != ""
        assert float(z) is not None

    def test_days_since_sold_computed(self):
        rows = self._make_rows(3, price=100.0)
        with tempfile.NamedTemporaryFile(suffix=".csv", mode='w', delete=False) as f:
            out = f.name
        with self._mock_db(rows):
            export(out, days=365, min_sales=2)
        with open(out, newline='') as f:
            first_row = next(csv.DictReader(f))
        os.unlink(out)
        days = first_row["days_since_sold"]
        assert days != ""
        assert int(days) >= 0

    def test_empty_db_produces_header_only(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", mode='w', delete=False) as f:
            out = f.name
        with self._mock_db([]):
            export(out, days=365, min_sales=1)
        with open(out, newline='') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        os.unlink(out)
        assert rows == []
