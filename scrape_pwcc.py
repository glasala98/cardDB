"""PWCC Marketplace scraper — fetches completed weekly auction results.

Source: pwccmarketplace.com
Buyer's premium: 15%
Schedule: weekly (catalog_tier_pwcc.yml or manual)
Source key: "pwcc"

Uses curl_cffi with Chrome impersonation to bypass Cloudflare/bot protection.
Run via GitHub Actions only — never locally.
"""

import argparse
import logging
import re
import time
from datetime import date, datetime, timedelta

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

from auction_match import CatalogMatcher
from db import get_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RESULTS_URL   = "https://www.pwccmarketplace.com/results"
SOURCE        = "pwcc"
BUYER_PREMIUM = 15.0
SLEEP_BETWEEN = 1.5   # seconds between requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Price: "$1,234" or "1234.00"
_PRICE_RE = re.compile(r'[\d,]+(?:\.\d+)?')
# Date patterns: "March 15, 2025" or "2025-03-15" or "Mar 15, 2025"
_DATE_PATTERNS = [
    re.compile(r'\b(\d{4}-\d{2}-\d{2})\b'),
    re.compile(r'\b([A-Za-z]+\.?\s+\d{1,2},?\s+\d{4})\b'),
]
# Lot ID from PWCC URL: /market/…/12345 or /auction-results/…/12345
_LOT_ID_RE = re.compile(r'/(\d{4,})(?:[/?]|$)')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_price(text: str) -> float | None:
    """Parse a price string like '$1,234.00' → 1234.0."""
    cleaned = text.replace(',', '').replace('$', '').strip()
    m = _PRICE_RE.match(cleaned)
    if m:
        try:
            return float(m.group())
        except ValueError:
            pass
    return None


def _parse_date(text: str) -> str | None:
    """Parse a human-readable date in text → 'YYYY-MM-DD', or None."""
    # ISO format first
    m = _DATE_PATTERNS[0].search(text)
    if m:
        return m.group(1)

    # Named month format
    m = _DATE_PATTERNS[1].search(text)
    if m:
        raw = m.group(1).strip().rstrip(',')
        for fmt in ("%B %d %Y", "%b %d %Y", "%B %d, %Y", "%b %d, %Y"):
            try:
                return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
    return None


def _lot_id_from_url(url: str) -> str:
    """Extract a numeric lot ID from a PWCC URL."""
    m = _LOT_ID_RE.search(url)
    return m.group(1) if m else url.split('/')[-1].split('?')[0]


# ---------------------------------------------------------------------------
# HTTP fetching (curl_cffi with Chrome impersonation)
# ---------------------------------------------------------------------------

def _get(session, url: str) -> BeautifulSoup | None:
    """Fetch URL with curl_cffi Chrome impersonation. Returns soup or None."""
    try:
        resp = session.get(url, headers=HEADERS, timeout=30, impersonate="chrome110")
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as exc:
        log.warning("Fetch error for %s: %s", url, exc)
        return None


# ---------------------------------------------------------------------------
# Page parsers
# ---------------------------------------------------------------------------

def get_auction_result_links(session, since: date) -> list[dict]:
    """Fetch the PWCC results landing page and return recent auction links.

    Returns list of dicts: {"url": ..., "label": ..., "auction_date": ...}
    """
    log.info("Fetching PWCC results index: %s", RESULTS_URL)
    soup = _get(session, RESULTS_URL)
    if soup is None:
        log.warning("Could not load PWCC results page")
        return []

    auctions = []

    # PWCC lists completed auctions as links — they typically look like:
    # <a href="/results/weekly-auction-2025-03-10">Weekly Auction — March 10, 2025</a>
    for link in soup.select("a[href*='/results/'], a[href*='/auction-results/']"):
        href  = link.get("href", "")
        label = link.get_text(strip=True)

        if not href or not label:
            continue

        full_url = href if href.startswith("http") else "https://www.pwccmarketplace.com" + href

        # Try to extract a date from the URL slug or link text
        auction_date_str = _parse_date(label) or _parse_date(href)
        if auction_date_str:
            try:
                auction_date = date.fromisoformat(auction_date_str)
                if auction_date < since:
                    continue   # too old — skip
            except ValueError:
                pass   # keep it if we can't parse, let lot-level filtering catch it

        auctions.append({
            "url":          full_url,
            "label":        label,
            "auction_date": auction_date_str,
        })

    log.info("Found %d recent PWCC auction result pages", len(auctions))
    return auctions


def parse_lots_from_results_page(soup: BeautifulSoup, auction_meta: dict) -> list[dict]:
    """Extract individual lot records from a PWCC auction results page.

    PWCC renders results as rows in a table or card grid.  We try the table
    selector first, then fall back to card/grid layouts.
    """
    lots = []
    auction_date = auction_meta.get("auction_date")
    auction_label = auction_meta.get("label", "")

    # --- Table layout ---
    rows = soup.select("table tr, tbody tr")
    for row in rows:
        cells = row.select("td")
        if len(cells) < 2:
            continue

        # Try to find title and price among cells
        title_cell = cells[0].get_text(strip=True)
        price_cell = ""
        for cell in cells[1:]:
            text = cell.get_text(strip=True)
            if '$' in text or re.search(r'\d{2,}', text):
                price_cell = text
                break

        if not title_cell or not price_cell:
            continue

        hammer = _parse_price(price_cell)
        if hammer is None:
            continue

        # Date may be in a cell or inherited from the auction
        date_str = auction_date
        for cell in cells:
            parsed = _parse_date(cell.get_text(strip=True))
            if parsed:
                date_str = parsed
                break

        # Lot URL
        link_el = row.select_one("a[href]")
        lot_url = ""
        if link_el:
            href = link_el.get("href", "")
            lot_url = href if href.startswith("http") else "https://www.pwccmarketplace.com" + href
        lot_id = _lot_id_from_url(lot_url)

        lots.append({
            "title":        title_cell,
            "hammer":       hammer,
            "sold_date":    date_str,
            "lot_url":      lot_url,
            "lot_id":       lot_id,
            "auction_name": auction_label,
        })

    # --- Card / grid layout fallback ---
    if not lots:
        for card in soup.select("div[class*='lot'], div[class*='card'], div[class*='item']"):
            title_el = card.select_one("h2, h3, .title, .lot-title, a")
            price_el = card.select_one(".price, .sold-price, .final-price, [class*='price']")
            if not title_el or not price_el:
                continue

            title  = title_el.get_text(strip=True)
            hammer = _parse_price(price_el.get_text(strip=True))
            if not title or hammer is None:
                continue

            date_str = auction_date
            date_el  = card.select_one(".date, [class*='date']")
            if date_el:
                date_str = _parse_date(date_el.get_text(strip=True)) or auction_date

            link_el = card.select_one("a[href]")
            lot_url = ""
            if link_el:
                href = link_el.get("href", "")
                lot_url = href if href.startswith("http") else "https://www.pwccmarketplace.com" + href
            lot_id = _lot_id_from_url(lot_url)

            lots.append({
                "title":        title,
                "hammer":       hammer,
                "sold_date":    date_str,
                "lot_url":      lot_url,
                "lot_id":       lot_id,
                "auction_name": auction_label,
            })

    return lots


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Scrape PWCC Marketplace auction results")
    parser.add_argument(
        "--since-date",
        default=(date.today() - timedelta(days=7)).isoformat(),
        help="Skip lots sold before this date (YYYY-MM-DD, default: 7 days ago)",
    )
    parser.add_argument(
        "--max-auctions", type=int, default=3,
        help="Maximum number of auction result pages to process (default: 3)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print matched lots without writing to the database",
    )
    args = parser.parse_args()

    since = date.fromisoformat(args.since_date)
    log.info("PWCC scraper — since=%s, max_auctions=%d, dry_run=%s",
             since, args.max_auctions, args.dry_run)

    # curl_cffi session with Chrome impersonation
    session = cffi_requests.Session()
    total_fetched = 0

    with get_db() as conn:
        matcher = CatalogMatcher(conn, dry_run=args.dry_run)

        # 1. Get list of recent completed auction pages
        auction_links = get_auction_result_links(session, since)
        auction_links = auction_links[: args.max_auctions]

        if not auction_links:
            log.warning("No recent PWCC auction result pages found")

        for auction in auction_links:
            url   = auction["url"]
            label = auction["label"]
            log.info("Processing auction: %s (%s)", label, url)
            time.sleep(SLEEP_BETWEEN)

            soup = _get(session, url)
            if soup is None:
                log.warning("Skipping auction '%s' — fetch failed", label)
                continue

            lots = parse_lots_from_results_page(soup, auction)
            log.info("  Found %d lots in '%s'", len(lots), label)

            for lot in lots:
                sold_date_str = lot["sold_date"]

                # Skip lots older than our since_date
                if sold_date_str:
                    try:
                        if date.fromisoformat(sold_date_str) < since:
                            continue
                    except ValueError:
                        pass

                hammer    = lot["hammer"]
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
                        "auction_name": lot["auction_name"],
                    },
                }

                matcher.process_sale(sale)
                total_fetched += 1

            time.sleep(SLEEP_BETWEEN)

        matcher.flush()

    # Summary
    print("\n--- PWCC scrape complete ---")
    print(f"  Total fetched: {total_fetched:,}")
    matcher.print_stats()
    total = matcher.stats["matched"] + matcher.stats["unmatched"]
    if total:
        match_pct = round(matcher.stats["matched"] / total * 100, 1)
        print(f"  Match rate:    {match_pct}%")
        print(f"  Unmatched:     {matcher.stats['unmatched']:,}")


if __name__ == "__main__":
    main()
