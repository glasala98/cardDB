"""Goldin Auctions scraper — fetches closed lot results and saves to market_raw_sales.

Source: goldinauctions.com
Buyer's premium: 20%
Schedule: monthly (catalog_tier_goldin.yml or manual)
Source key: "goldin"

Run via GitHub Actions only — never locally.
"""

import argparse
import logging
import re
import time
from datetime import date, datetime, timedelta

import requests
from bs4 import BeautifulSoup

from auction_match import CatalogMatcher
import os as _os, sys as _sys
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)
from db import get_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL        = "https://goldinauctions.com/lots"
SOURCE          = "goldin"
BUYER_PREMIUM   = 20.0
SLEEP_BETWEEN   = 1.5   # seconds between page requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Goldin close-date text: "Closed: March 15, 2025" or "Closed: Mar 15, 2025"
_CLOSE_DATE_RE = re.compile(
    r'Closed[:\s]+([A-Za-z]+\.?\s+\d{1,2},?\s+\d{4})', re.IGNORECASE
)
# Lot number extracted from URL or lot text
_LOT_NUM_RE = re.compile(r'/lot[s]?/([^/?#]+)', re.IGNORECASE)
# Strip currency symbols and commas from price strings
_PRICE_RE   = re.compile(r'[\d,]+(?:\.\d+)?')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_close_date(text: str) -> str | None:
    """Parse 'Closed: March 15, 2025' → '2025-03-15'. Returns None on failure."""
    m = _CLOSE_DATE_RE.search(text)
    if not m:
        return None
    raw = m.group(1).strip().rstrip(',')
    for fmt in ("%B %d %Y", "%b %d %Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _parse_price(text: str) -> float | None:
    """Parse '$1,234.00' or '1234' → float. Returns None if unparseable."""
    m = _PRICE_RE.search(text.replace(',', ''))
    if m:
        try:
            return float(m.group())
        except ValueError:
            pass
    return None


def _lot_id_from_url(url: str) -> str:
    """Extract lot identifier from a Goldin lot URL."""
    m = _LOT_NUM_RE.search(url)
    return m.group(1) if m else url.split('/')[-1]


# ---------------------------------------------------------------------------
# Page fetching
# ---------------------------------------------------------------------------

def fetch_page(session: requests.Session, page: int) -> BeautifulSoup | None:
    """Fetch one closed-lots page. Returns BeautifulSoup or None on error."""
    url = f"{BASE_URL}?status=closed&page={page}"
    try:
        resp = session.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except requests.HTTPError as exc:
        log.warning("HTTP %s fetching page %d: %s", exc.response.status_code, page, url)
    except requests.RequestException as exc:
        log.warning("Request error on page %d: %s", page, exc)
    return None


def parse_lots(soup: BeautifulSoup) -> list[dict]:
    """Extract raw lot data from a closed-lots page.

    Goldin renders lot cards as <div class="lot-card"> (or similar).
    We fall back to broad heuristics if the markup changes.
    Returns list of raw dicts with title, hammer_price, sold_date, lot_url.
    """
    lots = []

    # Primary selector — adapt if Goldin ever changes their markup
    cards = soup.select("div.lot-card, div.lot-item, article.lot")
    if not cards:
        # Broader fallback: any anchor containing a price and a date
        cards = soup.select("div[class*='lot']")

    for card in cards:
        # --- title ---
        title_el = card.select_one("h2, h3, .lot-title, .title, a[href*='/lot']")
        title = title_el.get_text(strip=True) if title_el else None
        if not title:
            continue

        # --- price ---
        price_el = card.select_one(".hammer-price, .sold-price, .price, [class*='price']")
        price_text = price_el.get_text(strip=True) if price_el else ""
        hammer = _parse_price(price_text)
        if hammer is None:
            log.debug("No price found for lot: %s", title[:60])
            continue

        # --- close date ---
        date_el = card.select_one(".close-date, .lot-date, .sold-date, [class*='date']")
        date_text = date_el.get_text(strip=True) if date_el else card.get_text()
        sold_date = _parse_close_date(date_text)

        # --- lot URL + lot_id ---
        link_el = card.select_one("a[href*='/lot']")
        lot_url = link_el["href"] if link_el else ""
        if lot_url and not lot_url.startswith("http"):
            lot_url = "https://goldinauctions.com" + lot_url
        lot_id = _lot_id_from_url(lot_url)

        # --- auction name (shown in breadcrumb or card header) ---
        auction_el = card.select_one(".auction-name, .event-name, [class*='auction']")
        auction_name = auction_el.get_text(strip=True) if auction_el else None

        # --- lot number (sometimes shown as "Lot #1234") ---
        lot_num_text = card.get_text()
        lot_num_m = re.search(r'Lot\s*#?\s*(\d+)', lot_num_text, re.IGNORECASE)
        lot_number = lot_num_m.group(1) if lot_num_m else None

        lots.append({
            "title":      title,
            "hammer":     hammer,
            "sold_date":  sold_date,
            "lot_url":    lot_url,
            "lot_id":     lot_id,
            "lot_number": lot_number,
            "auction_name": auction_name,
        })

    return lots


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Scrape Goldin Auctions closed lots")
    parser.add_argument(
        "--since-date",
        default=(date.today() - timedelta(days=30)).isoformat(),
        help="Skip lots closed before this date (YYYY-MM-DD, default: 30 days ago)",
    )
    parser.add_argument(
        "--max-pages", type=int, default=20,
        help="Maximum number of result pages to fetch (default: 20)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print matched lots without writing to the database",
    )
    args = parser.parse_args()

    since = date.fromisoformat(args.since_date)
    log.info("Goldin scraper — since=%s, max_pages=%d, dry_run=%s",
             since, args.max_pages, args.dry_run)

    session = requests.Session()
    total_fetched = 0
    stop_early    = False

    with get_db() as conn:
        matcher = CatalogMatcher(conn, dry_run=args.dry_run)

        for page_num in range(1, args.max_pages + 1):
            if stop_early:
                break

            log.info("Fetching page %d …", page_num)
            soup = fetch_page(session, page_num)
            if soup is None:
                log.warning("Skipping page %d — fetch failed", page_num)
                time.sleep(SLEEP_BETWEEN)
                continue

            lots = parse_lots(soup)
            if not lots:
                log.info("No lots found on page %d — stopping", page_num)
                break

            for lot in lots:
                sold_date_str = lot["sold_date"]

                # Stop paginating once we're past our date window
                if sold_date_str:
                    sold_d = date.fromisoformat(sold_date_str)
                    if sold_d < since:
                        log.info("Lot date %s < since_date %s — stopping", sold_d, since)
                        stop_early = True
                        break

                hammer   = lot["hammer"]
                price_val = round(hammer * (1 + BUYER_PREMIUM / 100), 2)

                sale = {
                    "title":             lot["title"],
                    "price_val":         price_val,
                    "sold_date":         sold_date_str,
                    "source":            SOURCE,
                    "lot_url":           lot["lot_url"],
                    "lot_id":            lot["lot_id"],
                    "is_auction":        True,
                    "hammer_price":      hammer,
                    "buyer_premium_pct": BUYER_PREMIUM,
                    "raw_metadata": {
                        "lot_number":   lot["lot_number"],
                        "auction_name": lot["auction_name"],
                    },
                }

                matcher.process_sale(sale)
                total_fetched += 1

            log.info("Page %d: %d lots processed (running total: %d)",
                     page_num, len(lots), total_fetched)
            time.sleep(SLEEP_BETWEEN)

        matcher.flush()

    # Summary
    print("\n--- Goldin scrape complete ---")
    print(f"  Total fetched: {total_fetched:,}")
    matcher.print_stats()
    total = matcher.stats["matched"] + matcher.stats["unmatched"]
    if total:
        match_pct = round(matcher.stats["matched"] / total * 100, 1)
        print(f"  Match rate:    {match_pct}%")
        print(f"  Unmatched:     {matcher.stats['unmatched']:,}")


if __name__ == "__main__":
    main()
