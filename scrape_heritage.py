"""Heritage Auctions scraper — fetches closed sports card lot results.

Source: ha.com (Heritage Auctions)
Buyer's premium: 20%
Schedule: monthly (catalog_tier_heritage.yml or manual)
Source key: "heritage"

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
from db import get_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Heritage closed sports card search — type=3000 (Sports), N= facets for sports cards
BASE_SEARCH_URL = (
    "https://www.ha.com/c/search-results.zx"
    "?type=3000&N=790+231+4294967179&ic=R&pg={page}"
)
LOT_BASE_URL  = "https://www.ha.com/itm/{lot_id}"
SOURCE        = "heritage"
BUYER_PREMIUM = 20.0
SLEEP_BETWEEN = 1.5   # seconds between page fetches

# Sport → Heritage category facet override appended to N parameter
SPORT_FACETS: dict[str, str] = {
    "NHL":  "792",   # Hockey
    "NBA":  "795",   # Basketball
    "NFL":  "793",   # Football
    "MLB":  "791",   # Baseball
    "ALL":  "",      # No additional facet
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Heritage lot URLs contain a numeric lot ID, e.g. /itm/12345678 or ?id=12345678
_LOT_ID_RE     = re.compile(r'/itm/(\d+)', re.IGNORECASE)
_LOT_ID_QS_RE  = re.compile(r'[?&]id=(\d+)', re.IGNORECASE)
# Auction number from lot detail: "Auction #12345"
_AUCTION_NUM_RE = re.compile(r'Auction\s*#?\s*(\d+)', re.IGNORECASE)
# Lot number: "Lot #12345" or "Lot 12345"
_LOT_NUM_RE    = re.compile(r'Lot\s*#?\s*(\d+)', re.IGNORECASE)
# Price: "$12,345" or "12,345"
_PRICE_RE      = re.compile(r'[\d,]+(?:\.\d+)?')
# Close date: "March 15, 2025" / "Mar 15, 2025" / ISO
_DATE_ISO_RE   = re.compile(r'\b(\d{4}-\d{2}-\d{2})\b')
_DATE_NAMED_RE = re.compile(r'\b([A-Za-z]+\.?\s+\d{1,2},?\s+\d{4})\b')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_price(text: str) -> float | None:
    """Parse '$12,345' → 12345.0."""
    cleaned = text.replace(',', '').replace('$', '').strip()
    m = _PRICE_RE.match(cleaned)
    if m:
        try:
            return float(m.group())
        except ValueError:
            pass
    return None


def _parse_date(text: str) -> str | None:
    """Parse date from arbitrary text → 'YYYY-MM-DD' or None."""
    m = _DATE_ISO_RE.search(text)
    if m:
        return m.group(1)

    m = _DATE_NAMED_RE.search(text)
    if m:
        raw = m.group(1).strip().rstrip(',')
        for fmt in ("%B %d %Y", "%b %d %Y", "%B %d, %Y", "%b %d, %Y"):
            try:
                return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
    return None


def _extract_lot_id(url: str) -> str:
    """Extract the Heritage lot ID from a /itm/... URL or ?id= query param."""
    m = _LOT_ID_RE.search(url)
    if m:
        return m.group(1)
    m = _LOT_ID_QS_RE.search(url)
    if m:
        return m.group(1)
    return url.split('/')[-1].split('?')[0]


def _build_search_url(page: int, sport: str) -> str:
    """Build the Heritage search URL for the given page and sport filter."""
    facet = SPORT_FACETS.get(sport.upper(), "")
    n_param = "790+231+4294967179"
    if facet:
        n_param = f"{n_param}+{facet}"
    return (
        f"https://www.ha.com/c/search-results.zx"
        f"?type=3000&N={n_param}&ic=R&pg={page}"
    )


# ---------------------------------------------------------------------------
# Page fetching
# ---------------------------------------------------------------------------

def fetch_page(session: requests.Session, url: str) -> BeautifulSoup | None:
    """Fetch a Heritage search results page. Returns BeautifulSoup or None."""
    try:
        resp = session.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except requests.HTTPError as exc:
        log.warning("HTTP %s fetching %s", exc.response.status_code, url)
    except requests.RequestException as exc:
        log.warning("Request error: %s — %s", url, exc)
    return None


# ---------------------------------------------------------------------------
# Lot parsing
# ---------------------------------------------------------------------------

def parse_lots(soup: BeautifulSoup) -> list[dict]:
    """Extract lot data from a Heritage search results page.

    Heritage renders results as list items or article cards inside
    a results container.  We try multiple selectors in order.
    """
    lots = []

    # Primary selectors observed on Heritage search pages
    items = (
        soup.select("li.result-item, li[class*='lot'], article[class*='lot']")
        or soup.select("div.search-result, div[class*='result-item']")
        or soup.select("div[class*='lot-item'], div[class*='lot-card']")
    )

    for item in items:
        # --- title ---
        title_el = item.select_one(
            "h3.item-title, h2.item-title, .lot-title, .title, "
            "a[href*='/itm/'], a[href*='?id=']"
        )
        title = title_el.get_text(strip=True) if title_el else None
        if not title:
            continue

        # --- hammer price ---
        price_el = item.select_one(
            ".sold-price, .hammer-price, .current-bid, "
            "[class*='sold'], [class*='price']"
        )
        price_text = price_el.get_text(strip=True) if price_el else ""
        hammer = _parse_price(price_text)
        if hammer is None:
            log.debug("No price for: %s", title[:60])
            continue

        # --- lot URL and lot ID ---
        link_el = item.select_one("a[href*='/itm/'], a[href*='?id=']")
        lot_url = ""
        if link_el:
            href = link_el.get("href", "")
            lot_url = href if href.startswith("http") else "https://www.ha.com" + href
        lot_id = _extract_lot_id(lot_url)
        # Canonical lot URL: ha.com/itm/{lot_id}
        if lot_id and not lot_url:
            lot_url = LOT_BASE_URL.format(lot_id=lot_id)

        # --- close / sold date ---
        date_el = item.select_one(".close-date, .end-date, .sale-date, [class*='date']")
        date_text = date_el.get_text(strip=True) if date_el else item.get_text()
        sold_date = _parse_date(date_text)

        # --- lot number and auction number ---
        full_text   = item.get_text()
        lot_num_m   = _LOT_NUM_RE.search(full_text)
        auction_m   = _AUCTION_NUM_RE.search(full_text)
        lot_number  = lot_num_m.group(1)  if lot_num_m  else None
        auction_num = auction_m.group(1)  if auction_m  else None

        lots.append({
            "title":        title,
            "hammer":       hammer,
            "sold_date":    sold_date,
            "lot_url":      lot_url,
            "lot_id":       lot_id,
            "lot_number":   lot_number,
            "auction_number": auction_num,
        })

    return lots


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Scrape Heritage Auctions closed sports card lots")
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
        "--sport",
        default="ALL",
        choices=["ALL", "NHL", "NBA", "NFL", "MLB"],
        help="Filter by sport (default: ALL)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print matched lots without writing to the database",
    )
    args = parser.parse_args()

    since = date.fromisoformat(args.since_date)
    log.info(
        "Heritage scraper — since=%s, max_pages=%d, sport=%s, dry_run=%s",
        since, args.max_pages, args.sport, args.dry_run,
    )

    session = requests.Session()
    total_fetched = 0
    stop_early    = False

    with get_db() as conn:
        matcher = CatalogMatcher(conn, dry_run=args.dry_run)

        for page_num in range(1, args.max_pages + 1):
            if stop_early:
                break

            url = _build_search_url(page_num, args.sport)
            log.info("Fetching page %d: %s", page_num, url)

            soup = fetch_page(session, url)
            if soup is None:
                log.warning("Skipping page %d — fetch failed", page_num)
                time.sleep(SLEEP_BETWEEN)
                continue

            lots = parse_lots(soup)
            if not lots:
                log.info("No lots on page %d — stopping", page_num)
                break

            for lot in lots:
                sold_date_str = lot["sold_date"]

                # Stop paginating once results are older than our window
                if sold_date_str:
                    try:
                        sold_d = date.fromisoformat(sold_date_str)
                        if sold_d < since:
                            log.info("Lot date %s < since_date %s — stopping", sold_d, since)
                            stop_early = True
                            break
                    except ValueError:
                        pass   # date unparseable — keep processing

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
                        "lot_number":     lot["lot_number"],
                        "auction_number": lot["auction_number"],
                    },
                }

                matcher.process_sale(sale)
                total_fetched += 1

            log.info("Page %d: %d lots processed (running total: %d)",
                     page_num, len(lots), total_fetched)
            time.sleep(SLEEP_BETWEEN)

        matcher.flush()

    # Summary
    print("\n--- Heritage scrape complete ---")
    print(f"  Total fetched: {total_fetched:,}")
    matcher.print_stats()
    total = matcher.stats["matched"] + matcher.stats["unmatched"]
    if total:
        match_pct = round(matcher.stats["matched"] / total * 100, 1)
        print(f"  Match rate:    {match_pct}%")
        print(f"  Unmatched:     {matcher.stats['unmatched']:,}")


if __name__ == "__main__":
    main()
