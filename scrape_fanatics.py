"""scrape_fanatics.py — Fetch sold marketplace listings from Fanatics Collect.

Source key : fanatics
Schedule   : weekly (GitHub Actions)
Premium    : none (fixed-price sales, is_auction=False)

Fanatics Collect is JavaScript-rendered. This scraper first attempts to fetch
via curl_cffi (Chrome TLS impersonation). If the response body is empty or
contains no listing data, a warning is logged noting that a Selenium/Playwright
approach may be required.

Usage:
    python scrape_fanatics.py
    python scrape_fanatics.py --since-date 2024-11-01
    python scrape_fanatics.py --max-pages 10 --dry-run
"""

import argparse
import logging
import re
import time
from datetime import date, datetime, timedelta

try:
    from curl_cffi import requests as cffi_requests
    _CURL_AVAILABLE = True
except ImportError:
    import requests as cffi_requests   # type: ignore[assignment]
    _CURL_AVAILABLE = False

from bs4 import BeautifulSoup

from auction_match import CatalogMatcher
from db import get_db

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SOURCE        = "fanatics"
SOLD_URL      = "https://collector.fanatics.com/marketplace/sold"
SLEEP_BETWEEN = 1.5   # seconds between page fetches

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

if not _CURL_AVAILABLE:
    log.warning(
        "curl_cffi not installed — falling back to requests (JS rendering will fail). "
        "Install with: pip install curl-cffi"
    )

# ---------------------------------------------------------------------------
# Fetch helper
# ---------------------------------------------------------------------------

def _fetch_page(page: int) -> BeautifulSoup | None:
    """
    Fetch one sold-listings page via curl_cffi Chrome impersonation.
    Returns a BeautifulSoup object, or None on error.
    If the parsed page contains no listing data, logs a Selenium warning.
    """
    params = {"page": page}
    try:
        if _CURL_AVAILABLE:
            resp = cffi_requests.get(
                SOLD_URL,
                params=params,
                headers=HEADERS,
                impersonate="chrome110",
                timeout=30,
            )
        else:
            resp = cffi_requests.get(SOLD_URL, params=params, headers=HEADERS, timeout=30)

        resp.raise_for_status()
        html = resp.text

    except Exception as exc:
        # curl_cffi raises its own error types; catch broadly
        status = getattr(getattr(exc, "response", None), "status_code", "?")
        log.warning("HTTP %s on page %d — skipping (%s)", status, page, exc)
        return None

    if not html or len(html.strip()) < 500:
        log.warning(
            "Page %d returned near-empty body (%d bytes). "
            "The site may require full JS execution. "
            "Consider switching to Selenium or Playwright for this scraper.",
            page, len(html or ""),
        )
        return None

    soup = BeautifulSoup(html, "html.parser")

    # Heuristic: if body text is tiny the JS bundle hasn't rendered
    body_text = soup.get_text(strip=True)
    if len(body_text) < 200:
        log.warning(
            "Page %d body text is only %d chars — JS may not have rendered. "
            "Selenium/Playwright may be required for Fanatics Collect.",
            page, len(body_text),
        )
        return None

    return soup


# ---------------------------------------------------------------------------
# HTML parse helpers
# ---------------------------------------------------------------------------

_PRICE_RE = re.compile(r"[\$,]")


def _parse_price(raw: str) -> float | None:
    cleaned = _PRICE_RE.sub("", (raw or "").strip())
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_date(raw: str) -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(raw[:19], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _extract_listings(soup: BeautifulSoup) -> list[dict]:
    """
    Extract sold card listings from a Fanatics Collect sold page.
    Fanatics renders listings as product cards; selectors target patterns
    observed in static/SSR markup — adjust as the live DOM evolves.
    """
    listings = []

    # Primary listing container                                  SELECTOR: may need tuning
    containers = soup.select(
        "div[data-testid='product-card'], "
        "div.product-card, "
        "div.listing-card, "
        "div.sold-listing, "
        "li.product-item"
    )
    if not containers:
        # Fallback: any card-like div with a price child          SELECTOR: may need tuning
        containers = soup.select("div.card, article.product")

    for container in containers:
        # Title / card name                                       SELECTOR: may need tuning
        title_tag = (
            container.select_one("[data-testid='product-title']")
            or container.select_one("h2.product-title")
            or container.select_one("h3.product-title")
            or container.select_one("p.product-name")
            or container.select_one(".listing-title")
            or container.select_one("h2")
            or container.select_one("h3")
        )
        title = title_tag.get_text(strip=True) if title_tag else ""

        # Sale price                                              SELECTOR: may need tuning
        price_tag = (
            container.select_one("[data-testid='sale-price']")
            or container.select_one(".sale-price")
            or container.select_one(".sold-price")
            or container.select_one(".price-sold")
            or container.select_one("[class*='price']")
        )
        price_raw  = price_tag.get_text(strip=True) if price_tag else ""
        price_val  = _parse_price(price_raw)

        # Sale / close date                                       SELECTOR: may need tuning
        date_tag = (
            container.select_one("[data-testid='sold-date']")
            or container.select_one(".sold-date")
            or container.select_one(".sale-date")
            or container.select_one("time")
            or container.select_one("[datetime]")
            or container.select_one("[class*='date']")
        )
        if date_tag:
            date_raw = date_tag.get("datetime") or date_tag.get_text(strip=True)
        else:
            date_raw = ""
        sold_date = _parse_date(date_raw)

        # Listing URL                                             SELECTOR: may need tuning
        link_tag = (
            container.select_one("a[href*='/product/']")
            or container.select_one("a[href*='/listing/']")
            or container.select_one("a[href*='/item/']")
            or container.select_one("a[href]")
        )
        lot_url = ""
        if link_tag and link_tag.get("href"):
            href = link_tag["href"]
            lot_url = href if href.startswith("http") else f"https://collector.fanatics.com{href}"

        # Product / listing ID                                    SELECTOR: may need tuning
        lot_id = (
            container.get("data-product-id")
            or container.get("data-listing-id")
            or container.get("data-id")
            or ""
        )
        if not lot_id and lot_url:
            m = re.search(r"/(?:product|listing|item)[/-](\w+)", lot_url)
            lot_id = m.group(1) if m else ""

        # Optional enrichment fields                              SELECTOR: may need tuning
        sport_tag = (
            container.select_one("[data-testid='sport']")
            or container.select_one(".sport-tag")
            or container.select_one("[class*='sport']")
        )
        sport = sport_tag.get_text(strip=True) if sport_tag else ""

        condition_tag = (
            container.select_one("[data-testid='condition']")
            or container.select_one(".condition")
            or container.select_one("[class*='condition']")
        )
        condition = condition_tag.get_text(strip=True) if condition_tag else ""

        if not title or price_val is None:
            continue

        listings.append({
            "title":             title,
            "price_val":         price_val,
            "sold_date":         sold_date,
            "source":            SOURCE,
            "lot_url":           lot_url,
            "lot_id":            lot_id,
            "is_auction":        False,
            "hammer_price":      None,
            "buyer_premium_pct": None,
            "raw_metadata":      {
                "product_id": lot_id,
                "sport":      sport,
                "condition":  condition,
            },
        })

    return listings


def _is_last_page(soup: BeautifulSoup) -> bool:
    """Return True if pagination shows no further pages."""
    # SELECTOR: may need tuning
    next_btn = (
        soup.select_one("a[rel='next']")
        or soup.select_one("button[aria-label*='next' i]:not([disabled])")
        or soup.select_one("a.next-page")
        or soup.select_one("li.next a")
        or soup.select_one("[data-testid='pagination-next']:not([disabled])")
    )
    return next_btn is None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    default_since = (datetime.utcnow().date() - timedelta(days=7)).isoformat()

    parser = argparse.ArgumentParser(description="Scrape Fanatics Collect sold listings")
    parser.add_argument("--since-date", metavar="YYYY-MM-DD", default=default_since,
                        help=f"Skip listings older than this date (default: {default_since})")
    parser.add_argument("--max-pages", type=int, default=20,
                        help="Maximum pages to fetch (default: 20)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse and match but do not write to DB")
    args = parser.parse_args()

    since_date: date | None = None
    if args.since_date:
        since_date = datetime.strptime(args.since_date, "%Y-%m-%d").date()

    log.info("=== Fanatics Collect scraper starting ===")
    log.info("curl_cffi available: %s", _CURL_AVAILABLE)
    log.info("since_date=%s  max_pages=%d  dry_run=%s",
             since_date, args.max_pages, args.dry_run)

    total_fetched = 0
    stop_early    = False

    with get_db() as conn:
        matcher = CatalogMatcher(conn, dry_run=args.dry_run)

        for page in range(1, args.max_pages + 1):
            if stop_early:
                break

            log.info("Fetching page %d/%d …", page, args.max_pages)
            soup = _fetch_page(page)

            if soup is None:
                log.warning("No usable content on page %d — stopping", page)
                break

            listings = _extract_listings(soup)
            if not listings:
                log.info("No listings found on page %d — done", page)
                break

            for listing in listings:
                if since_date and listing["sold_date"]:
                    try:
                        if datetime.strptime(listing["sold_date"], "%Y-%m-%d").date() < since_date:
                            log.info(
                                "Reached since_date cutoff on page %d — stopping early", page
                            )
                            stop_early = True
                            break
                    except ValueError:
                        pass

                matcher.process_sale(listing)
                total_fetched += 1

            log.info("  Page %d: %d listings (total so far: %d)",
                     page, len(listings), total_fetched)

            if _is_last_page(soup):
                log.info("Last page detected — stopping")
                break

            time.sleep(SLEEP_BETWEEN)

        matcher.flush()

    print("\n=== Fanatics Collect scrape complete ===")
    print(f"  Pages fetched : up to {args.max_pages}")
    print(f"  Listings fetched : {total_fetched:,}")
    matcher.print_stats()
    total = matcher.stats["matched"] + matcher.stats["unmatched"]
    match_pct = round(matcher.stats["matched"] / total * 100, 1) if total else 0
    print(f"  Match rate    : {match_pct}%")
    if args.dry_run:
        print("  [DRY RUN] — no rows written to database")


if __name__ == "__main__":
    main()
