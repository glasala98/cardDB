"""scrape_pristine.py — Fetch closed auction lots from Pristine Auction.

Source key : pristine
Schedule   : weekly (GitHub Actions)
Premium    : 18% buyer's premium applied to hammer price

Usage:
    python scrape_pristine.py
    python scrape_pristine.py --since-date 2024-11-01
    python scrape_pristine.py --max-pages 5 --dry-run
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

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SOURCE            = "pristine"
CLOSED_URL        = "https://www.pristineauction.com/closed-auctions"
BUYER_PREMIUM_PCT = 18.0
SLEEP_BETWEEN     = 1.5   # seconds between page fetches

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HTML parse helpers
# ---------------------------------------------------------------------------

_PRICE_RE = re.compile(r"[\$,]")
_DATE_RE  = re.compile(r"(\w+ \d{1,2},?\s*\d{4})")


def _parse_price(raw: str) -> float | None:
    """Strip currency symbols and commas, return float or None."""
    cleaned = _PRICE_RE.sub("", (raw or "").strip())
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_date(raw: str) -> str | None:
    """Try common date formats found on Pristine, return YYYY-MM-DD or None."""
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y",
                "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Try extracting a date-like substring
    m = _DATE_RE.search(raw)
    if m:
        return _parse_date(m.group(1))
    return None


def _fetch_page(session: requests.Session, page: int) -> BeautifulSoup | None:
    """Fetch one closed-auctions page and return a BeautifulSoup object."""
    params = {"page": page}
    try:
        resp = session.get(CLOSED_URL, params=params, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except requests.HTTPError as exc:
        log.warning("HTTP %s on page %d — skipping", exc.response.status_code, page)
        return None
    except Exception as exc:
        log.warning("Error fetching page %d: %s — skipping", page, exc)
        return None


def _extract_lots(soup: BeautifulSoup) -> list[dict]:
    """
    Extract auction lots from a closed-auctions page.
    Pristine renders lots as repeated item cards — selectors here target the
    most common markup patterns observed; add fallbacks as the site evolves.
    """
    lots = []

    # Primary container selector                                SELECTOR: may need tuning
    containers = soup.select("div.lot-item, div.auction-item, div.item-card, li.auction-lot")
    if not containers:
        # Fallback: any article or li with a price element      SELECTOR: may need tuning
        containers = soup.select("article, li.item")

    for container in containers:
        # Title                                                  SELECTOR: may need tuning
        title_tag = (
            container.select_one("h2.lot-title")
            or container.select_one("h3.lot-title")
            or container.select_one("a.lot-title")
            or container.select_one(".item-title")
            or container.select_one("h2")
            or container.select_one("h3")
        )
        title = title_tag.get_text(strip=True) if title_tag else ""

        # Hammer price                                           SELECTOR: may need tuning
        price_tag = (
            container.select_one(".hammer-price")
            or container.select_one(".final-price")
            or container.select_one(".winning-bid")
            or container.select_one(".price")
            or container.select_one("[class*='price']")
        )
        hammer_raw = price_tag.get_text(strip=True) if price_tag else ""
        hammer_price = _parse_price(hammer_raw)

        # Close / sold date                                      SELECTOR: may need tuning
        date_tag = (
            container.select_one(".close-date")
            or container.select_one(".sold-date")
            or container.select_one(".end-date")
            or container.select_one("[class*='date']")
        )
        date_raw = date_tag.get_text(strip=True) if date_tag else ""
        sold_date = _parse_date(date_raw)

        # Lot URL                                                SELECTOR: may need tuning
        link_tag = container.select_one("a[href*='/lot/'], a[href*='/item/'], a.lot-link")
        if not link_tag:
            link_tag = container.select_one("a[href]")
        lot_url = ""
        if link_tag and link_tag.get("href"):
            href = link_tag["href"]
            lot_url = href if href.startswith("http") else f"https://www.pristineauction.com{href}"

        # Lot ID from URL or data attribute                      SELECTOR: may need tuning
        lot_id = container.get("data-lot-id") or container.get("data-id") or ""
        if not lot_id and lot_url:
            m = re.search(r"/(?:lot|item)[/-](\w+)", lot_url)
            lot_id = m.group(1) if m else ""

        # Optional category                                      SELECTOR: may need tuning
        category_tag = container.select_one(".category, .sport, [class*='category']")
        category = category_tag.get_text(strip=True) if category_tag else ""

        if not title or hammer_price is None:
            continue

        price_val = round(hammer_price * (1 + BUYER_PREMIUM_PCT / 100), 2)

        lots.append({
            "title":             title,
            "price_val":         price_val,
            "sold_date":         sold_date,
            "source":            SOURCE,
            "lot_url":           lot_url,
            "lot_id":            lot_id,
            "is_auction":        True,
            "hammer_price":      hammer_price,
            "buyer_premium_pct": BUYER_PREMIUM_PCT,
            "raw_metadata":      {"lot_id": lot_id, "category": category},
        })

    return lots


def _is_last_page(soup: BeautifulSoup) -> bool:
    """Return True if pagination indicates no further pages."""
    # Common "next page" button / link patterns                  SELECTOR: may need tuning
    next_btn = (
        soup.select_one("a[rel='next']")
        or soup.select_one("a.next-page")
        or soup.select_one("li.next a")
        or soup.select_one(".pagination .next:not(.disabled)")
    )
    return next_btn is None

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    default_since = (datetime.utcnow().date() - timedelta(days=7)).isoformat()

    parser = argparse.ArgumentParser(description="Scrape Pristine Auction closed lots")
    parser.add_argument("--since-date", metavar="YYYY-MM-DD", default=default_since,
                        help=f"Skip lots older than this date (default: {default_since})")
    parser.add_argument("--max-pages", type=int, default=10,
                        help="Maximum pages to fetch (default: 10)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse and match but do not write to DB")
    args = parser.parse_args()

    since_date: date | None = None
    if args.since_date:
        since_date = datetime.strptime(args.since_date, "%Y-%m-%d").date()

    log.info("=== Pristine Auction scraper starting ===")
    log.info("since_date=%s  max_pages=%d  dry_run=%s",
             since_date, args.max_pages, args.dry_run)

    session = requests.Session()
    total_fetched = 0
    stop_early    = False

    with get_db() as conn:
        matcher = CatalogMatcher(conn, dry_run=args.dry_run)

        for page in range(1, args.max_pages + 1):
            if stop_early:
                break

            log.info("Fetching page %d/%d …", page, args.max_pages)
            soup = _fetch_page(session, page)

            if soup is None:
                log.warning("No content on page %d — stopping", page)
                break

            lots = _extract_lots(soup)
            if not lots:
                log.info("No lots found on page %d — done", page)
                break

            for lot in lots:
                if since_date and lot["sold_date"]:
                    try:
                        if datetime.strptime(lot["sold_date"], "%Y-%m-%d").date() < since_date:
                            log.info("Reached since_date cutoff on page %d — stopping early", page)
                            stop_early = True
                            break
                    except ValueError:
                        pass

                matcher.process_sale(lot)
                total_fetched += 1

            log.info("  Page %d: %d lots (total so far: %d)", page, len(lots), total_fetched)

            if _is_last_page(soup):
                log.info("Last page detected — stopping")
                break

            time.sleep(SLEEP_BETWEEN)

        matcher.flush()

    print("\n=== Pristine Auction scrape complete ===")
    print(f"  Pages fetched : up to {args.max_pages}")
    print(f"  Lots fetched  : {total_fetched:,}")
    matcher.print_stats()
    total = matcher.stats["matched"] + matcher.stats["unmatched"]
    match_pct = round(matcher.stats["matched"] / total * 100, 1) if total else 0
    print(f"  Match rate    : {match_pct}%")
    if args.dry_run:
        print("  [DRY RUN] — no rows written to database")


if __name__ == "__main__":
    main()
