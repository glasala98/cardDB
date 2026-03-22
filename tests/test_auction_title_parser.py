"""Unit tests for auction_title_parser.py — Phase 0/1.

Tests every grade company, serial/print-run patterns, and edge cases.
No database or network access required.
"""
import sys, os
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "scraping"))

import pytest
from auction_title_parser import parse_title, is_graded, _parse_serial_print


# ---------------------------------------------------------------------------
# parse_title — grade detection
# ---------------------------------------------------------------------------

class TestGradeDetection:

    @pytest.mark.parametrize("title,expected_grade,expected_company,expected_numeric", [
        # PSA
        ("Connor McDavid 2015-16 UD YG PSA 10",        "PSA 10",  "PSA",  10.0),
        ("LeBron James 2003-04 Chrome RC PSA 9",        "PSA 9",   "PSA",   9.0),
        ("Mike Trout Topps Auto PSA 9.5",               "PSA 9.5", "PSA",   9.5),
        ("Charizard 1st Edition PSA 8.5",               "PSA 8.5", "PSA",   8.5),
        ("Wayne Gretzky 1979 OPC PSA 7",                "PSA 7",   "PSA",   7.0),
        ("Mickey Mantle 1952 Topps PSA 5",              "PSA 5",   "PSA",   5.0),
        # BGS (most-specific first — 9.5 before 9)
        ("Connor Bedard Young Guns BGS 9.5",            "BGS 9.5", "BGS",   9.5),
        ("Auston Matthews BGS 10",                      "BGS 10",  "BGS",  10.0),
        ("Cale Makar BGS 9",                            "BGS 9",   "BGS",   9.0),
        ("Nathan MacKinnon BGS 8.5",                    "BGS 8.5", "BGS",   8.5),
        # SGC
        ("LeBron James 2003 Topps SGC 10",              "SGC 10",  "SGC",  10.0),
        ("Kobe Bryant Finest SGC 9.5",                  "SGC 9.5", "SGC",   9.5),
        ("Michael Jordan Fleer SGC 9",                  "SGC 9",   "SGC",   9.0),
        # CGC
        ("Patrick Mahomes Prizm RC CGC 10",             "CGC 10",  "CGC",  10.0),
        ("Josh Allen Mosaic CGC 9.5",                   "CGC 9.5", "CGC",   9.5),
        # HGA
        ("Ja Morant Select HGA 10",                     "HGA 10",  "HGA",  10.0),
        ("Trae Young Optic HGA 9.5",                    "HGA 9.5", "HGA",   9.5),
        # CSG
        ("Luka Doncic Prizm CSG 10",                    "CSG 10",  "CSG",  10.0),
        # GEM MINT generic
        ("Victor Wembanyama Prizm GEM MT 10",           "GEM MT 10", None, 10.0),
        ("Zion Williamson Select GEM MINT",             "GEM MINT",  None, 10.0),
        # Ungraded
        ("Connor McDavid 2015-16 UD Young Guns #201",   None,       None,  None),
        ("LeBron James 2003 Topps Chrome RC",           None,       None,  None),
        ("",                                            None,       None,  None),
    ])
    def test_grade_parsing(self, title, expected_grade, expected_company, expected_numeric):
        r = parse_title(title)
        assert r["grade"]         == expected_grade,   f"grade mismatch for: {title!r}"
        assert r["grade_company"] == expected_company, f"company mismatch for: {title!r}"
        assert r["grade_numeric"] == expected_numeric, f"numeric mismatch for: {title!r}"

    def test_psa10_not_matched_as_psa_100(self):
        """PSA 100 should not match PSA 10 — word-boundary check."""
        r = parse_title("Card PSA100 Fake")
        # \bPSA\s*10\b requires word boundary after 10 — "100" has no boundary there
        # The regex is \bPSA\s*10\b so PSA100 should NOT match PSA 10
        assert r["grade"] is None or r["grade"] != "PSA 10"

    def test_bgs_95_takes_priority_over_bgs_9(self):
        """BGS 9.5 pattern must match before BGS 9 pattern."""
        r = parse_title("Card BGS 9.5 Gem Mint")
        assert r["grade"] == "BGS 9.5"
        assert r["grade_numeric"] == 9.5


# ---------------------------------------------------------------------------
# parse_title — serial / print run
# ---------------------------------------------------------------------------

class TestSerialPrintRun:

    @pytest.mark.parametrize("title,expected_serial,expected_run", [
        ("#7/25 Ja Morant Silver",              7,    25),
        ("LeBron James Prizm /99 Gold",         None, 99),
        ("Wembanyama RC 01/50",                 1,    50),
        ("Patrick Mahomes Auto 007/199",        7,    199),
        ("No serial here at all",               None, None),
        ("Connor Bedard /1 Superfractor",       None, 1),
        # print_run from bare /NNN
        ("Luka Doncic Prizm Gold /10",          None, 10),
    ])
    def test_serial_print(self, title, expected_serial, expected_run):
        serial, run = _parse_serial_print(title)
        assert serial == expected_serial, f"serial mismatch for: {title!r}"
        assert run    == expected_run,    f"run mismatch for: {title!r}"

    def test_serial_with_grade_in_title(self):
        """Both grade and serial/print_run parsed from same title."""
        r = parse_title("2023 Topps Chrome Mike Trout Auto /99 PSA 9")
        assert r["grade"]      == "PSA 9"
        assert r["print_run"]  == 99
        assert r["grade_numeric"] == 9.0

    def test_full_serial_and_run(self):
        r = parse_title("McDavid 2015-16 OPC #201 BGS 9.5 7/25")
        assert r["grade"]         == "BGS 9.5"
        assert r["serial_number"] == 7
        assert r["print_run"]     == 25

    def test_sanity_serial_exceeds_run_returns_none_serial(self):
        """If extracted serial > run, serial should be None (bad parse)."""
        serial, run = _parse_serial_print("Card 99/25")
        # 99 > 25, so serial must be None
        assert serial is None

    def test_run_over_9999_via_print_only_not_captured(self):
        """_PRINT_ONLY fallback does not capture runs over 9999."""
        # No serial pattern (no digit before slash), just /99999 bare
        _, run = _parse_serial_print("No serial /99999")
        assert run is None


# ---------------------------------------------------------------------------
# is_graded helper
# ---------------------------------------------------------------------------

class TestIsGraded:
    def test_graded_titles(self):
        assert is_graded("Card PSA 10") is True
        assert is_graded("Card BGS 9.5") is True
        assert is_graded("Card SGC 9") is True
        assert is_graded("Card GEM MT 10") is True

    def test_raw_titles(self):
        assert is_graded("Connor McDavid Young Guns") is False
        assert is_graded("LeBron James RC") is False
        assert is_graded("") is False


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_none_title_returns_empty(self):
        r = parse_title(None)
        assert all(v is None for v in r.values())

    def test_whitespace_only(self):
        r = parse_title("   ")
        assert r["grade"] is None

    def test_all_fields_present(self):
        r = parse_title("anything")
        assert set(r.keys()) == {"grade", "grade_company", "grade_numeric", "serial_number", "print_run"}

    def test_grade_case_insensitive(self):
        r1 = parse_title("Card psa 10")
        r2 = parse_title("Card PSA 10")
        assert r1["grade"] == r2["grade"]
