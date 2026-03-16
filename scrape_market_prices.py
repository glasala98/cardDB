#!/usr/bin/env python3
"""
Batch price scraper for the global card catalog.

Reads cards from card_catalog, scrapes eBay sold prices using the existing
scrape_card_prices.process_card() engine, then writes results to:
  - market_price_history  (append-only snapshot per card per day)
  - market_prices         (upsert current/latest price + trend)

Usage:
    python scrape_market_prices.py                        # all un-scraped cards
    python scrape_market_prices.py --sport NHL            # NHL only
    python scrape_market_prices.py --sport NHL --year 2024-25
    python scrape_market_prices.py --force                # re-scrape all (even today's)
    python scrape_market_prices.py --limit 100            # cap at 100 cards
    python scrape_market_prices.py --workers 10           # parallel Chrome instances
    python scrape_market_prices.py --confidence low       # only re-scrape low confidence
    python scrape_market_prices.py --min-value 5          # skip cards worth < $5

The scraper prioritises:
  1. Cards never priced (no row in market_prices)
  2. Cards not scraped in the last 7 days
  3. Low-confidence cards
"""

import os, sys, time, argparse, logging
from datetime import datetime, date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("market_prices")

from db import get_db, save_raw_sales
from scrape_card_prices import process_card

# Priority order for confidence — lower = needs re-scraping sooner
CONF_RANK = {"none": 0, "error": 0, "low": 1, "estimated": 2, "manual": 3,
             "medium": 4, "high": 5}

TREND_THRESHOLDS = (0.05, 0.15)  # < 5% = stable, 5-15% = up/down, > 15% = spike/drop


def calc_trend(new_val: float, old_val: float) -> str:
    if not old_val or old_val == 0:
        return "no data"
    change = (new_val - old_val) / old_val
    lo, hi = TREND_THRESHOLDS
    if abs(change) < lo:
        return "stable"
    if change >  hi: return "spike"
    if change >  lo: return "up"
    if change < -hi: return "drop"
    return "down"


def get_cards_to_scrape(sport=None, year=None, force=False,
                         limit=None, confidence=None, min_value=None) -> list[dict]:
    """
    Returns list of {id, search_query, sport, year, set_name, player_name, ...}
    ordered by priority (never scraped first, then oldest scrape date).
    """
    where_clauses = ["1=1"]
    params: list = []

    if sport:
        where_clauses.append("c.sport = %s"); params.append(sport)
    if year:
        where_clauses.append("c.year = %s"); params.append(year)
    if confidence:
        where_clauses.append("mp.confidence = %s"); params.append(confidence)
    if min_value:
        where_clauses.append("(mp.fair_value IS NULL OR mp.fair_value >= %s)")
        params.append(min_value)

    stale_cutoff = (date.today() - timedelta(days=7)).isoformat()
    if not force:
        # Only cards not yet scraped today OR not scraped in 7 days
        where_clauses.append(
            "(mp.scraped_at IS NULL OR mp.scraped_at < %s)"
        )
        params.append(stale_cutoff)

    where = " AND ".join(where_clauses)
    limit_sql = f"LIMIT {int(limit)}" if limit else ""

    sql = f"""
        SELECT
            c.id,
            c.search_query,
            c.sport,
            c.year,
            c.brand,
            c.set_name,
            c.card_number,
            c.player_name,
            c.variant,
            COALESCE(mp.fair_value, 0)  AS prev_value,
            COALESCE(mp.confidence, '') AS prev_confidence,
            mp.scraped_at               AS last_scraped
        FROM card_catalog c
        LEFT JOIN market_prices mp ON mp.card_catalog_id = c.id
        WHERE {where}
        ORDER BY
            mp.scraped_at NULLS FIRST,          -- never scraped first
            COALESCE(mp.confidence, '') ASC,     -- lowest confidence next
            mp.scraped_at ASC                    -- then oldest scrape
        {limit_sql}
    """
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def save_price_result(card: dict, result: dict):
    """
    Write one scrape result to market_price_history (INSERT),
    market_prices (UPSERT with trend), and market_raw_sales (individual sales).
    """
    stats = result.get("stats", {})
    fair  = float(stats.get("fair_price") or result.get("estimated_value") or 0)
    conf  = result.get("confidence", "none")
    sales = int(stats.get("num_sales") or 0)
    top3  = ", ".join(f"${p:.2f}" for p in (stats.get("top_3_prices") or []))
    lo    = float(stats.get("min") or 0)
    hi    = float(stats.get("max") or 0)
    trend = calc_trend(fair, float(card["prev_value"]))

    with get_db() as conn:
        cur = conn.cursor()

        # 1. Append to history (ignore duplicate for same day)
        cur.execute("""
            INSERT INTO market_price_history
                (card_catalog_id, scraped_at, fair_value, confidence,
                 num_sales, top_3_prices, min_price, max_price, source)
            VALUES (%s, CURRENT_DATE, %s, %s, %s, %s, %s, %s, 'ebay')
            ON CONFLICT (card_catalog_id, scraped_at) DO UPDATE SET
                fair_value   = EXCLUDED.fair_value,
                confidence   = EXCLUDED.confidence,
                num_sales    = EXCLUDED.num_sales,
                top_3_prices = EXCLUDED.top_3_prices,
                min_price    = EXCLUDED.min_price,
                max_price    = EXCLUDED.max_price
        """, (card["id"], fair, conf, sales, top3, lo, hi))

        # 2. Upsert current price + trend
        cur.execute("""
            INSERT INTO market_prices
                (card_catalog_id, fair_value, prev_value, trend,
                 confidence, num_sales, scraped_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
            ON CONFLICT (card_catalog_id) DO UPDATE SET
                prev_value  = market_prices.fair_value,
                fair_value  = EXCLUDED.fair_value,
                trend       = EXCLUDED.trend,
                confidence  = EXCLUDED.confidence,
                num_sales   = EXCLUDED.num_sales,
                scraped_at  = EXCLUDED.scraped_at,
                updated_at  = NOW()
        """, (card["id"], fair, card["prev_value"], trend, conf, sales))

        # Persist every individual eBay sale — deduped on (card_catalog_id, sold_date, title)
        save_raw_sales(card["id"], result.get("raw_sales") or [], conn=conn)

        conn.commit()


def scrape_one(card: dict) -> tuple[dict, dict | None, str | None]:
    """Scrape a single card. Returns (card, result_or_None, error_or_None)."""
    query = card["search_query"]
    if not query:
        # Build fallback query from fields
        parts = [card["year"], card["brand"], card["set_name"],
                 card["card_number"], card["player_name"]]
        query = " ".join(p for p in parts if p)

    try:
        _, result = process_card(query)
        return card, result, None
    except Exception as e:
        return card, None, str(e)


def main():
    ap = argparse.ArgumentParser(description="Scrape market prices for card catalog")
    ap.add_argument("--sport",      default=None, help="Filter by sport (NHL, NBA, ...)")
    ap.add_argument("--year",       default=None, help="Filter by year (2024-25)")
    ap.add_argument("--force",      action="store_true", help="Re-scrape even if recent")
    ap.add_argument("--limit",      type=int, default=None, help="Max cards to scrape")
    ap.add_argument("--workers",    type=int, default=10,   help="Parallel Chrome workers")
    ap.add_argument("--confidence", default=None, help="Only re-scrape this confidence tier")
    ap.add_argument("--min-value",  type=float, default=None, help="Skip cards below $N")
    args = ap.parse_args()

    log.info("Loading cards from card_catalog...")
    cards = get_cards_to_scrape(
        sport=args.sport, year=args.year, force=args.force,
        limit=args.limit, confidence=args.confidence, min_value=args.min_value
    )

    if not cards:
        log.info("No cards to scrape — all up to date.")
        return

    log.info(f"Scraping {len(cards):,} cards with {args.workers} workers...")
    ok = err = 0
    start = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(scrape_one, c): c for c in cards}
        for i, fut in enumerate(as_completed(futures), 1):
            card, result, error = fut.result()
            label = f"{card['player_name']} {card['year']} {card['set_name']}"

            if error:
                log.warning(f"  [{i}/{len(cards)}] ERROR  {label}: {error}")
                err += 1
                continue

            if result:
                save_price_result(card, result)
                fair = result.get("stats", {}).get("fair_price") or \
                       result.get("estimated_value") or 0
                conf = result.get("confidence", "?")
                log.info(f"  [{i}/{len(cards)}] {conf:10s} ${float(fair):7.2f}  {label}")
                ok += 1
            else:
                log.warning(f"  [{i}/{len(cards)}] NO DATA  {label}")
                err += 1

    elapsed = time.time() - start
    log.info(
        f"\nDone in {elapsed/60:.1f}min — "
        f"{ok:,} priced, {err:,} errors, "
        f"{len(cards):,} total"
    )


if __name__ == "__main__":
    main()
