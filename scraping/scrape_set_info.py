#!/usr/bin/env python3
"""
Scrape set/product information from cardboardconnection.com (no login required).

Captures per set:
  - Product types: Hobby Box, Blaster Box, Hanger Box, Retail Pack, Mega Box, etc.
  - MSRP per product type
  - Pack configuration: cards per pack, packs per box
  - Release date
  - Pack odds for key card types (Autograph, Relic, Rookie, Parallel, etc.)

Data is upserted into sealed_products + sealed_product_odds tables.

Usage:
    python scrape_set_info.py                          # NHL, last 3 years
    python scrape_set_info.py --sport NBA --year 2024-25
    python scrape_set_info.py --sport NFL --year-from 2022
    python scrape_set_info.py --all-sports --year-from 2023
    python scrape_set_info.py --dry-run --debug        # inspect without DB writes
"""

import os
import re
import sys
import time
import random
import logging
import argparse
from datetime import datetime, date
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("set_info")

# ── Constants ─────────────────────────────────────────────────────────────────

CBC_BASE = "https://www.cardboardconnection.com"

SPORT_PATH_CBC = {
    "NHL": "nhl-hockey-cards",
    "NBA": "nba-basketball-cards",
    "NFL": "nfl-football-cards",
    "MLB": "mlb-baseball-cards",
}
SPORT_SUFFIX_CBC = {
    "NHL": "hockey-cards",
    "NBA": "basketball-cards",
    "NFL": "football-cards",
    "MLB": "baseball-cards",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Known product type keywords (order matters — more specific first)
PRODUCT_TYPES = [
    "Hobby Jumbo Box",
    "Jumbo Hobby Box",
    "Jumbo Box",
    "Hobby Box",
    "Mega Box",
    "Blaster Box",
    "Hanger Box",
    "Hanger Pack",
    "Fat Pack",
    "Value Pack",
    "Retail Pack",
    "Retail Box",
    "Cello Pack",
    "Gravity Feed Box",
    "Collector Pack",
    "Collector Box",
    "Rack Pack",
    "Rack Box",
]

# Canonical name normalization (what we store)
PRODUCT_CANONICAL = {
    "Jumbo Hobby Box": "Hobby Jumbo Box",
}

# Odds keywords to look for in odds tables
ODDS_KEYWORDS = [
    "Autograph", "Auto", "Relic", "Memorabilia", "Patch",
    "Rookie", "Young Guns", "Prizm", "Refractor",
    "Numbered", "Serial", "Parallel", "Insert",
    "Short Print", "SP", "SSP", "1/1",
]

DEBUG_DIR = Path("set_info_debug")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _save_debug(text: str, name: str):
    DEBUG_DIR.mkdir(exist_ok=True)
    path = DEBUG_DIR / f"{name}_{datetime.now().strftime('%H%M%S')}.html"
    path.write_text(text, encoding="utf-8")
    log.debug(f"  Saved debug HTML -> {path}")


def cbc_expand_year(year: str) -> str:
    """'2024-25' -> '2024-2025', '2024' -> '2024'."""
    if "-" not in year:
        return year
    start, end = year.split("-")
    return f"{start}-{start[:2]}{end}"


# Sport signals: words that clearly indicate a specific sport regardless of which
# page the set was discovered from (catches cross-listed products on CBC)
_SPORT_SIGNALS: dict[str, list[str]] = {
    "NHL": [" hockey", "nhl "],
    "NBA": [" basketball", "nba "],
    "NFL": [" football", "nfl ", "gridiron"],
    "MLB": [" baseball", "mlb ", " bowman"],  # Bowman is always MLB
}


def infer_sport_from_name(set_name: str) -> str | None:
    """Return sport code if set_name contains clear sport-specific keywords."""
    sl = " " + set_name.lower() + " "
    for sport, signals in _SPORT_SIGNALS.items():
        if any(sig in sl for sig in signals):
            return sport
    return None


def infer_brand(set_name: str) -> str:
    sl = set_name.lower()
    if any(x in sl for x in ("upper deck", "o-pee-chee", "opc", "parkhurst",
                               "sp ", "spx", "ultimate", "fleer", "skybox")):
        return "Upper Deck"
    if any(x in sl for x in ("topps", "chrome", "bowman")):
        return "Topps"
    if any(x in sl for x in ("panini", "prizm", "donruss", "contenders",
                               "select", "optic")):
        return "Panini"
    if "leaf" in sl:
        return "Leaf"
    return ""


def normalize_product_type(raw: str) -> str | None:
    """Return canonical product type name, or None if not recognized."""
    raw_lower = raw.lower().strip()
    for pt in PRODUCT_TYPES:
        if pt.lower() in raw_lower:
            return PRODUCT_CANONICAL.get(pt, pt)
    return None


def parse_price(text: str) -> float | None:
    """Extract first dollar amount from text. Returns None if not found.
    Handles comma-thousands like $1,499.99 and $1,000.
    """
    m = re.search(r'\$\s*([\d,]+(?:\.\d{2})?)', text)
    if m:
        return float(m.group(1).replace(',', ''))
    return None


def parse_pack_config(text: str) -> tuple[int | None, int | None]:
    """
    Extract (cards_per_pack, packs_per_box) from text like:
      '8 cards per pack, 24 packs per box'
      '7 Cards/Pack, 20 Packs/Box'
      '24 packs, 8 cards'
    Returns (None, None) if not found.
    """
    text_lower = text.lower()
    cpp = None
    ppb = None

    m = re.search(r'(\d+)\s*cards?\s*(?:per\s*|/\s*)pack', text_lower)
    if m:
        cpp = int(m.group(1))

    m = re.search(r'(\d+)\s*packs?\s*(?:per\s*|/\s*)box', text_lower)
    if m:
        ppb = int(m.group(1))

    return cpp, ppb


def parse_release_date(text: str) -> date | None:
    """Extract release date from text. Tries common formats."""
    patterns = [
        r'(\w+ \d{1,2},?\s*\d{4})',   # October 2, 2024
        r'(\d{1,2}/\d{1,2}/\d{4})',   # 10/02/2024
        r'(\d{4}-\d{2}-\d{2})',        # 2024-10-02
    ]
    fmts = [
        ["%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y"],
        ["%m/%d/%Y"],
        ["%Y-%m-%d"],
    ]
    for pat, fmt_list in zip(patterns, fmts):
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            raw = m.group(1).strip().rstrip(",")
            for fmt in fmt_list:
                try:
                    return datetime.strptime(raw, fmt).date()
                except ValueError:
                    continue
    return None


def parse_odds_ratio(text: str) -> str | None:
    """Extract odds ratio like '1:24' or '1:288' from text."""
    m = re.search(r'1\s*:\s*(\d+(?:\.\d+)?)', text)
    if m:
        return f"1:{m.group(1)}"
    return None


# ── CBC discovery ─────────────────────────────────────────────────────────────

def cbc_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def cbc_get_set_urls(session: requests.Session, sport: str, year: str,
                     debug: bool) -> list[dict]:
    """Return list of {set_name, url} for the given sport+year from CBC."""
    slug      = SPORT_PATH_CBC.get(sport, "nhl-hockey-cards")
    suffix    = SPORT_SUFFIX_CBC.get(sport, "hockey-cards")
    full_year = cbc_expand_year(year)
    url       = f"{CBC_BASE}/sports-cards-sets/{slug}/{full_year}-{suffix}"

    resp = session.get(url, timeout=15)
    if resp.status_code != 200:
        log.warning(f"  CBC {sport} {year}: HTTP {resp.status_code} — {url}")
        return []

    if debug:
        _save_debug(resp.text, f"cbc_year_{sport}_{year}")

    soup = BeautifulSoup(resp.text, "html.parser")
    sets = []
    seen = set()

    year_prefix = year.split("-")[0]
    pattern = re.compile(rf'{re.escape(CBC_BASE)}/{year_prefix}', re.IGNORECASE)

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("http"):
            href = CBC_BASE + href
        name = a.get_text(strip=True)
        if pattern.search(href) and name and href not in seen:
            path_parts = href.replace(CBC_BASE, "").strip("/").split("/")
            if len(path_parts) == 1:
                seen.add(href)
                sets.append({"set_name": name, "url": href})

    # Filter out cross-listed sets whose names clearly belong to a different sport
    filtered = []
    for s in sets:
        inferred = infer_sport_from_name(s["set_name"])
        if inferred and inferred != sport:
            log.info(f"  Skipping cross-listed set (expected {sport}, inferred {inferred}): {s['set_name']}")
            continue
        filtered.append(s)
    if len(filtered) != len(sets):
        log.info(f"  CBC {sport} {year}: {len(filtered)} sets after removing {len(sets) - len(filtered)} cross-listed")
    else:
        log.info(f"  CBC {sport} {year}: {len(sets)} sets found")
    return filtered


# ── CBC set page parser ───────────────────────────────────────────────────────

def parse_set_page(html: str, set_name: str, sport: str, year: str,
                   source_url: str) -> dict:
    """
    Parse a CBC set page for product info.

    Returns:
        {
          "products": [
            {
              "product_type": "Hobby Box",
              "msrp": 149.99,
              "cards_per_pack": 8,
              "packs_per_box": 24,
            }, ...
          ],
          "release_date": date(2024, 10, 2),
          "odds": [
            {"card_type": "Autograph", "odds_ratio": "1:24"},
            ...
          ]
        }
    """
    soup = BeautifulSoup(html, "html.parser")
    brand = infer_brand(set_name)

    products: dict[str, dict] = {}  # keyed by canonical product_type
    release_date: date | None = None
    odds_list: list[dict] = []

    full_text = soup.get_text(" ", strip=True)

    # ── Strategy 1: look for structured product tables or dl/dt/dd ─────────
    # CBC often renders product info as a <table> or definition list.
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows:
            cells = [td.get_text(" ", strip=True) for td in row.find_all(["td", "th"])]
            row_text = " ".join(cells)
            pt = normalize_product_type(row_text)
            if not pt:
                continue
            price = None
            for cell in cells:
                price = parse_price(cell)
                if price:
                    break
            cpp, ppb = parse_pack_config(row_text)
            if pt not in products:
                products[pt] = {"product_type": pt, "msrp": price,
                                 "cards_per_pack": cpp, "packs_per_box": ppb}
            else:
                if price and not products[pt]["msrp"]:
                    products[pt]["msrp"] = price
                if cpp and not products[pt]["cards_per_pack"]:
                    products[pt]["cards_per_pack"] = cpp
                if ppb and not products[pt]["packs_per_box"]:
                    products[pt]["packs_per_box"] = ppb

    # ── Strategy 2: scan paragraph / list items for product type + price ────
    for el in soup.find_all(["p", "li", "div", "td", "dt", "dd", "span", "h3", "h4"]):
        text = el.get_text(" ", strip=True)
        if len(text) > 300:
            continue  # skip large blocks, too noisy
        pt = normalize_product_type(text)
        if not pt:
            continue
        price = parse_price(text)
        cpp, ppb = parse_pack_config(text)
        if pt not in products:
            products[pt] = {"product_type": pt, "msrp": price,
                             "cards_per_pack": cpp, "packs_per_box": ppb}
        else:
            if price and not products[pt]["msrp"]:
                products[pt]["msrp"] = price
            if cpp and not products[pt]["cards_per_pack"]:
                products[pt]["cards_per_pack"] = cpp
            if ppb and not products[pt]["packs_per_box"]:
                products[pt]["packs_per_box"] = ppb

    # ── Strategy 3: scan full text for pack config near product mentions ────
    # e.g. "Hobby Box – 8 cards per pack, 24 packs per box, MSRP $149.99"
    for pt_name in PRODUCT_TYPES:
        canonical = PRODUCT_CANONICAL.get(pt_name, pt_name)
        pattern = re.compile(
            rf'{re.escape(pt_name)}.{{0,200}}',
            re.IGNORECASE | re.DOTALL
        )
        for m in pattern.finditer(full_text):
            snippet = m.group(0)
            price = parse_price(snippet) if canonical not in products or not products.get(canonical, {}).get("msrp") else None
            cpp, ppb = parse_pack_config(snippet)
            if canonical not in products:
                products[canonical] = {"product_type": canonical, "msrp": price,
                                        "cards_per_pack": cpp, "packs_per_box": ppb}
            else:
                if price and not products[canonical].get("msrp"):
                    products[canonical]["msrp"] = price
                if cpp and not products[canonical].get("cards_per_pack"):
                    products[canonical]["cards_per_pack"] = cpp
                if ppb and not products[canonical].get("packs_per_box"):
                    products[canonical]["packs_per_box"] = ppb

    # ── Release date ─────────────────────────────────────────────────────────
    for marker in ["release date", "available", "on sale", "ships"]:
        idx = full_text.lower().find(marker)
        if idx >= 0:
            snippet = full_text[idx:idx + 80]
            release_date = parse_release_date(snippet)
            if release_date:
                break
    if not release_date:
        release_date = parse_release_date(full_text[:500])

    # ── Odds ─────────────────────────────────────────────────────────────────
    # Look for odds tables (CBC has them as <table> with "Odds" column header)
    odds_seen: set[str] = set()
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        has_odds_col = any("odd" in h or "ratio" in h or "per" in h for h in headers)
        if not has_odds_col:
            continue
        for row in table.find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in row.find_all("td")]
            if len(cells) < 2:
                continue
            row_text = " ".join(cells)
            ratio = parse_odds_ratio(row_text)
            if not ratio:
                continue
            # Find the best matching card type label
            for kw in ODDS_KEYWORDS:
                if kw.lower() in row_text.lower() and kw not in odds_seen:
                    odds_list.append({"card_type": kw, "odds_ratio": ratio})
                    odds_seen.add(kw)
                    break

    # Fallback: scan paragraphs for "1:N" odds near known card type keywords
    for el in soup.find_all(["p", "li", "td"]):
        text = el.get_text(" ", strip=True)
        ratio = parse_odds_ratio(text)
        if not ratio:
            continue
        for kw in ODDS_KEYWORDS:
            if kw.lower() in text.lower() and kw not in odds_seen:
                odds_list.append({"card_type": kw, "odds_ratio": ratio})
                odds_seen.add(kw)
                break

    result = {
        "set_name":     set_name,
        "sport":        sport,
        "year":         year,
        "brand":        brand,
        "source_url":   source_url,
        "release_date": release_date,
        "products":     list(products.values()),
        "odds":         odds_list,
    }

    log.info(
        f"    {set_name}: {len(result['products'])} product types, "
        f"{len(result['odds'])} odds entries"
        + (f", release {release_date}" if release_date else "")
    )
    return result


def scrape_set_page(session: requests.Session, set_info: dict,
                    sport: str, year: str, debug: bool) -> dict | None:
    """Fetch and parse one CBC set page."""
    try:
        resp = session.get(set_info["url"], timeout=15)
    except requests.RequestException as e:
        log.warning(f"    Request error for {set_info['set_name']}: {e}")
        return None

    if resp.status_code != 200:
        log.warning(f"    HTTP {resp.status_code} — {set_info['url']}")
        return None

    if debug:
        safe = re.sub(r'[^a-z0-9]', '_', set_info["set_name"].lower())[:40]
        _save_debug(resp.text, f"cbc_set_{safe}")

    return parse_set_page(resp.text, set_info["set_name"], sport, year, set_info["url"])


# ── DB upsert ─────────────────────────────────────────────────────────────────

def upsert_set_info(result: dict, dry_run: bool) -> int:
    """Upsert one set's product info. Returns number of product rows written."""
    if not result["products"]:
        return 0

    if dry_run:
        log.info(f"  [dry-run] {result['set_name']} ({result['sport']} {result['year']})")
        for p in result["products"]:
            log.info(
                f"    {p['product_type']}: MSRP=${p['msrp']} "
                f"  {p['cards_per_pack']}c/{p['packs_per_box']}p"
            )
        for o in result["odds"]:
            log.info(f"    Odds: {o['card_type']} {o['odds_ratio']}")
        return len(result["products"])

    from db import get_db

    with get_db() as conn:
        cur = conn.cursor()
        written = 0

        for p in result["products"]:
            cur.execute("""
                INSERT INTO sealed_products
                    (sport, year, set_name, brand, product_type, msrp,
                     cards_per_pack, packs_per_box, release_date,
                     source, source_url, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'cardboardconnection', %s, NOW())
                ON CONFLICT (sport, year, set_name, product_type) DO UPDATE SET
                    brand          = EXCLUDED.brand,
                    msrp           = COALESCE(EXCLUDED.msrp, sealed_products.msrp),
                    cards_per_pack = COALESCE(EXCLUDED.cards_per_pack, sealed_products.cards_per_pack),
                    packs_per_box  = COALESCE(EXCLUDED.packs_per_box,  sealed_products.packs_per_box),
                    release_date   = COALESCE(EXCLUDED.release_date,   sealed_products.release_date),
                    source_url     = EXCLUDED.source_url,
                    updated_at     = NOW()
                RETURNING id
            """, [
                result["sport"], result["year"], result["set_name"],
                result["brand"], p["product_type"], p["msrp"],
                p["cards_per_pack"], p["packs_per_box"],
                result["release_date"], result["source_url"],
            ])
            row = cur.fetchone()
            if not row:
                continue
            product_id = row[0]
            written += 1

            # Upsert odds for this product
            for o in result["odds"]:
                cur.execute("""
                    INSERT INTO sealed_product_odds
                        (sealed_product_id, card_type, odds_ratio)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (sealed_product_id, card_type) DO UPDATE SET
                        odds_ratio = EXCLUDED.odds_ratio
                """, [product_id, o["card_type"], o["odds_ratio"]])

        conn.commit()
    return written


# ── Main ──────────────────────────────────────────────────────────────────────

def build_year_list(sport: str, year_arg: str | None,
                    year_from: int | None) -> list[str]:
    CALENDAR_YEAR_SPORTS = {"NFL", "MLB"}
    if year_arg:
        return [year_arg]
    cur = datetime.now().year
    start = year_from or (cur - 3)
    if sport in CALENDAR_YEAR_SPORTS:
        return [str(y) for y in range(start, cur + 1)]
    return [f"{y}-{str(y+1)[-2:]}" for y in range(start, cur + 1)]


def main():
    ap = argparse.ArgumentParser(
        description="Scrape set/box product info from cardboardconnection.com"
    )
    ap.add_argument("--sport",      default="NHL",
                    choices=["NHL", "NBA", "NFL", "MLB"],
                    help="Sport to scrape (default: NHL)")
    ap.add_argument("--all-sports", action="store_true",
                    help="Scrape all four sports")
    ap.add_argument("--year",       help="Single year e.g. 2024-25")
    ap.add_argument("--year-from",  type=int,
                    help="Start year (default: 3 years ago)")
    ap.add_argument("--dry-run",    action="store_true",
                    help="Print results without writing to DB")
    ap.add_argument("--debug",      action="store_true",
                    help="Save raw HTML to set_info_debug/")
    args = ap.parse_args()

    sports = ["NHL", "NBA", "NFL", "MLB"] if args.all_sports else [args.sport]
    session = cbc_session()
    total = 0

    for sport in sports:
        years = build_year_list(sport, args.year, args.year_from)
        log.info(f"Sport: {sport}  |  Years: {years}")

        for year in years:
            sets = cbc_get_set_urls(session, sport, year, args.debug)
            for set_info in sets:
                result = scrape_set_page(session, set_info, sport, year, args.debug)
                if result:
                    n = upsert_set_info(result, dry_run=args.dry_run)
                    total += n
                time.sleep(random.uniform(0.3, 0.8))

    log.info(
        f"\nDone — {total:,} product rows "
        f"{'(dry-run, not saved)' if args.dry_run else 'upserted into sealed_products'}"
    )


if __name__ == "__main__":
    main()
