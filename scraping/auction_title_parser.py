"""Shared listing title parser for all scraped sale sources.

Extracts structured fields from raw auction/listing titles so every row in
market_raw_sales is fully normalized for ML training and analytics.

Works for eBay titles, Goldin lot titles, Heritage descriptions, PWCC titles, etc.

Usage:
    from auction_title_parser import parse_title

    fields = parse_title("2019-20 Panini Prizm LeBron James Silver PSA 10 #13 /25")
    # {
    #   "grade":             "PSA 10",
    #   "grade_company":     "PSA",
    #   "grade_numeric":     10.0,
    #   "serial_number":     None,   # individual copy number not in this title
    #   "print_run":         25,
    #   "is_auction":        False,  # caller sets this based on source
    # }
"""

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Grade patterns — ordered most-specific first (BGS before PSA to catch 9.5)
# ---------------------------------------------------------------------------

_GRADE_PATTERNS: list[tuple[str, str]] = [
    # BGS / Beckett
    (r'\bBGS\s*9\.5\b',  'BGS 9.5',  'BGS',  9.5),
    (r'\bBGS\s*10\b',    'BGS 10',   'BGS',  10.0),
    (r'\bBGS\s*9\b',     'BGS 9',    'BGS',  9.0),
    (r'\bBGS\s*8\.5\b',  'BGS 8.5',  'BGS',  8.5),
    (r'\bBGS\s*8\b',     'BGS 8',    'BGS',  8.0),
    # PSA
    (r'\bPSA\s*10\b',    'PSA 10',   'PSA',  10.0),
    (r'\bPSA\s*9\.5\b',  'PSA 9.5',  'PSA',  9.5),
    (r'\bPSA\s*9\b',     'PSA 9',    'PSA',  9.0),
    (r'\bPSA\s*8\.5\b',  'PSA 8.5',  'PSA',  8.5),
    (r'\bPSA\s*8\b',     'PSA 8',    'PSA',  8.0),
    (r'\bPSA\s*7\b',     'PSA 7',    'PSA',  7.0),
    (r'\bPSA\s*6\b',     'PSA 6',    'PSA',  6.0),
    (r'\bPSA\s*5\b',     'PSA 5',    'PSA',  5.0),
    # SGC
    (r'\bSGC\s*10\b',    'SGC 10',   'SGC',  10.0),
    (r'\bSGC\s*9\.5\b',  'SGC 9.5',  'SGC',  9.5),
    (r'\bSGC\s*9\b',     'SGC 9',    'SGC',  9.0),
    (r'\bSGC\s*8\.5\b',  'SGC 8.5',  'SGC',  8.5),
    (r'\bSGC\s*8\b',     'SGC 8',    'SGC',  8.0),
    # CGC (trading cards)
    (r'\bCGC\s*10\b',    'CGC 10',   'CGC',  10.0),
    (r'\bCGC\s*9\.5\b',  'CGC 9.5',  'CGC',  9.5),
    (r'\bCGC\s*9\b',     'CGC 9',    'CGC',  9.0),
    # HGA
    (r'\bHGA\s*10\b',    'HGA 10',   'HGA',  10.0),
    (r'\bHGA\s*9\.5\b',  'HGA 9.5',  'HGA',  9.5),
    # CSG
    (r'\bCSG\s*10\b',    'CSG 10',   'CSG',  10.0),
    (r'\bCSG\s*9\.5\b',  'CSG 9.5',  'CSG',  9.5),
    # Generic graded marker — company unknown
    (r'\bGEM\s*MT?\s*10\b', 'GEM MT 10', None, 10.0),
    (r'\bGEM\s*MINT\b',     'GEM MINT',  None, 10.0),
]

# ---------------------------------------------------------------------------
# Serial / print run
# ---------------------------------------------------------------------------

# Matches: /25, /99, /10, #7/25, 07/99, etc.
_SERIAL_RE  = re.compile(r'(?:^|#|\s|/)(\d{1,3})\s*/\s*(\d+)', re.IGNORECASE)
_PRINT_ONLY = re.compile(r'/(\d+)', re.IGNORECASE)   # fallback: just /NNN


def _parse_serial_print(title: str) -> tuple[Optional[int], Optional[int]]:
    """Return (serial_number, print_run) from a title, or (None, None)."""
    m = _SERIAL_RE.search(title)
    if m:
        serial = int(m.group(1))
        run    = int(m.group(2))
        # sanity: serial <= run, and both look like reasonable card numbers
        if serial <= run and run <= 9999 and serial >= 1:
            return serial, run
        return None, run  # couldn't parse serial cleanly, but we have the run

    m2 = _PRINT_ONLY.search(title)
    if m2:
        run = int(m2.group(1))
        if 1 <= run <= 9999:
            return None, run

    return None, None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_title(title: str) -> dict:
    """Parse a raw listing title into normalized structured fields.

    Returns a dict with keys:
        grade            str | None  — "PSA 10", "BGS 9.5", "Raw", etc.
        grade_company    str | None  — "PSA", "BGS", "SGC", "CGC", "HGA", "CSG"
        grade_numeric    float | None — 10.0, 9.5, etc.
        serial_number    int | None  — individual copy (e.g. 7 for 7/25)
        print_run        int | None  — total copies (e.g. 25 for 7/25)

    All fields are None if not found. Caller is responsible for setting
    is_auction, source, hammer_price, buyer_premium_pct, lot_url, lot_id.
    """
    if not title:
        return _empty()

    t = title.strip()

    # --- Grade detection ---
    grade = grade_company = None
    grade_numeric = None
    for pattern, label, company, numeric in _GRADE_PATTERNS:
        if re.search(pattern, t, re.IGNORECASE):
            grade         = label
            grade_company = company
            grade_numeric = numeric
            break

    # --- Serial / print run ---
    serial_number, print_run = _parse_serial_print(t)

    return {
        "grade":         grade,
        "grade_company": grade_company,
        "grade_numeric": grade_numeric,
        "serial_number": serial_number,
        "print_run":     print_run,
    }


def _empty() -> dict:
    return {
        "grade":         None,
        "grade_company": None,
        "grade_numeric": None,
        "serial_number": None,
        "print_run":     None,
    }


def is_graded(title: str) -> bool:
    """Return True if the title contains any grading company marker."""
    return parse_title(title)["grade"] is not None


# ---------------------------------------------------------------------------
# Quick self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        ("2019-20 Panini Prizm LeBron James Silver PSA 10",           "PSA 10", "PSA", 10.0, None, None),
        ("Connor Bedard Young Guns BGS 9.5 /199",                      "BGS 9.5","BGS",  9.5, None,  199),
        ("Ja Morant 2019 Prizm Silver RC #13 7/25",                    None,      None, None,    7,   25),
        ("McDavid 2015-16 UD YG #201",                                 None,      None, None, None, None),
        ("2023 Topps Chrome Mike Trout Auto /99 PSA 9",               "PSA 9",  "PSA",  9.0, None,   99),
        ("Charizard Pokemon 1st Edition PSA 10 #4",                   "PSA 10", "PSA", 10.0, None, None),
        ("LeBron James 2003-04 Topps Chrome RC SGC 9.5",              "SGC 9.5","SGC",  9.5, None, None),
    ]
    print(f"{'Title':<60} {'Grade':<10} {'Co':<5} {'Num':>5} {'Ser':>5} {'Run':>5}")
    print("-" * 90)
    for title, exp_grade, exp_co, exp_num, exp_ser, exp_run in tests:
        r = parse_title(title)
        ok = (r["grade"] == exp_grade and r["grade_numeric"] == exp_num
              and r["serial_number"] == exp_ser and r["print_run"] == exp_run)
        flag = "✓" if ok else "✗"
        print(f"{flag} {title[:58]:<58} {str(r['grade']):<10} {str(r['grade_company'] or ''):<5} "
              f"{str(r['grade_numeric'] or '')!s:>5} {str(r['serial_number'] or '')!s:>5} "
              f"{str(r['print_run'] or '')!s:>5}")
