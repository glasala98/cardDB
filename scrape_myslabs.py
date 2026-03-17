"""scrape_myslabs.py — Fetch completed graded-card sales from MySlabs JSON API.

Source key : myslabs
Schedule   : weekly (GitHub Actions)
Premium    : none (direct sales, is_auction=False)

Usage:
    python scrape_myslabs.py
    python scrape_myslabs.py --since-date 2024-11-01
    python scrape_myslabs.py --max-pages 10 --dry-run
"""

import argparse
import logging
import time
from datetime import date, datetime, timedelta

import requests

from auction_match import CatalogMatcher
from db import get_db

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SOURCE        = "myslabs"
API_BASE      = "https://myslabs.com/api/sales"
PER_PAGE      = 100
SLEEP_BETWEEN = 1.5  # seconds between page fetches

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------

def _fetch_page(session: requests.Session, page: int) -> dict | None:
    """Fetch one page from the MySlabs sales API. Returns parsed JSON or None."""
    url = API_BASE
    params = {"page": page, "per_page": PER_PAGE}
    try:
        resp = session.get(url, params=params, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as exc:
        log.warning("HTTP %s on page %d — skipping", exc.response.status_code, page)
        return None
    except Exception as exc:
        log.warning("Error fetching page %d: %s — skipping", page, exc)
        return None


def _parse_sold_date(raw: str | None) -> str | None:
    """Normalize sale_date to YYYY-MM-DD string, or None if unparseable."""
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(raw[:19], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _sale_from_item(item: dict) -> dict:
    """Map one MySlabs API sale object to the canonical sale dict."""
    price_raw = item.get("sale_price") or item.get("price") or 0
    price_val = float(price_raw)

    sold_date = _parse_sold_date(
        item.get("sale_date") or item.get("sold_date") or item.get("date")  # SELECTOR: may need tuning
    )

    lot_url = item.get("listing_url") or item.get("url") or ""         # SELECTOR: may need tuning
    lot_id  = str(item.get("listing_id") or item.get("id") or "")      # SELECTOR: may need tuning

    grade          = item.get("grade")                                  # SELECTOR: may need tuning
    grade_company  = item.get("grade_company") or item.get("grader")    # SELECTOR: may need tuning
    raw_grade_num  = item.get("grade_value") or item.get("grade_numeric")
    grade_numeric  = float(raw_grade_num) if raw_grade_num is not None else None

    return {
        "title":             (item.get("title") or item.get("card_name") or "").strip(),
        "price_val":         price_val,
        "sold_date":         sold_date,
        "source":            SOURCE,
        "lot_url":           lot_url,
        "lot_id":            lot_id,
        "is_auction":        False,
        "hammer_price":      None,
        "buyer_premium_pct": None,
        "grade":             grade,
        "grade_company":     grade_company,
        "grade_numeric":     grade_numeric,
        "raw_metadata":      item,   # full original JSON object
    }

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape MySlabs completed sales")
    parser.add_argument("--since-date", metavar="YYYY-MM-DD", default=None,
                        help="Skip sales older than this date (default: no cutoff)")
    parser.add_argument("--max-pages", type=int, default=50,
                        help="Maximum pages to fetch (default: 50)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse and match but do not write to DB")
    args = parser.parse_args()

    since_date: date | None = None
    if args.since_date:
        since_date = datetime.strptime(args.since_date, "%Y-%m-%d").date()

    log.info("=== MySlabs scraper starting ===")
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
            data = _fetch_page(session, page)

            if data is None:
                log.warning("No data on page %d — stopping", page)
                break

            items = data.get("data") or data.get("results") or []  # SELECTOR: may need tuning
            if not items:
                log.info("Empty results on page %d — done", page)
                break

            for item in items:
                sale = _sale_from_item(item)

                if not sale["title"]:
                    log.debug("Skipping item with no title: %s", item)
                    continue

                if since_date and sale["sold_date"]:
                    try:
                        if datetime.strptime(sale["sold_date"], "%Y-%m-%d").date() < since_date:
                            log.info("Reached since_date cutoff on page %d — stopping early", page)
                            stop_early = True
                            break
                    except ValueError:
                        pass

                matcher.process_sale(sale)
                total_fetched += 1

            log.info("  Page %d: %d items (total so far: %d)", page, len(items), total_fetched)

            # Check if we've hit the last page
            total_available = data.get("total") or data.get("count") or 0
            if total_available and total_fetched >= total_available:
                log.info("Fetched all %d available sales", total_available)
                break

            time.sleep(SLEEP_BETWEEN)

        matcher.flush()

    print("\n=== MySlabs scrape complete ===")
    print(f"  Pages fetched : up to {args.max_pages}")
    print(f"  Sales fetched : {total_fetched:,}")
    matcher.print_stats()
    total = matcher.stats["matched"] + matcher.stats["unmatched"]
    match_pct = round(matcher.stats["matched"] / total * 100, 1) if total else 0
    print(f"  Match rate    : {match_pct}%")
    if args.dry_run:
        print("  [DRY RUN] — no rows written to database")


if __name__ == "__main__":
    main()
