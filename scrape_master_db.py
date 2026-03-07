#!/usr/bin/env python3 -u
"""
Bulk scraper for card_catalog — scrapes eBay sold prices for all cards.
Reads from card_catalog, writes to market_prices + market_price_history.

Usage:
    python -u scrape_master_db.py                       # Scrape unscraped/stale cards
    python -u scrape_master_db.py --workers 5           # 5 parallel Chrome instances
    python -u scrape_master_db.py --sport NHL           # NHL cards only
    python -u scrape_master_db.py --year 2024-25        # One year only
    python -u scrape_master_db.py --rookies             # is_rookie=true only
    python -u scrape_master_db.py --force               # Re-scrape already-scraped cards
    python -u scrape_master_db.py --stale-days 30       # Only re-scrape cards older than 30 days
    python -u scrape_master_db.py --limit 500           # Cap at N cards per run
    python -u scrape_master_db.py --graded              # Scrape PSA/BGS graded prices
    python -u scrape_master_db.py --min-raw-value 5.0   # Min raw value for graded scraping
"""

import sys
import os
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)

import argparse
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, '.env'))
except ImportError:
    pass

from db import get_db
from scrape_card_prices import process_card
import scrape_card_prices

# Graded variants — probe highest first, skip lower if no sales
PSA_PROBE_ORDER = ['PSA 10', 'PSA 9', 'PSA 8']
BGS_PROBE_ORDER = ['BGS 10', 'BGS 9.5', 'BGS 9']
ALL_GRADES = PSA_PROBE_ORDER + BGS_PROBE_ORDER

# Thread-local Chrome drivers + shared progress counters
_thread_local = threading.local()
_lock = threading.Lock()
_progress = {"done": 0, "found": 0, "not_found": 0, "errors": 0, "deltas": 0}


# ── Chrome driver ─────────────────────────────────────────────────────────────

def _create_fast_driver():
    from selenium.webdriver.chrome.options import Options
    opts = Options()
    for arg in [
        '--headless', '--disable-gpu', '--no-sandbox', '--disable-dev-shm-usage',
        '--window-size=1280,720', '--disable-extensions',
        '--blink-settings=imagesEnabled=false', '--ignore-certificate-errors',
        '--disable-blink-features=AutomationControlled',
        '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    ]:
        opts.add_argument(arg)
    opts.add_experimental_option('excludeSwitches', ['enable-automation'])
    opts.page_load_strategy = 'eager'
    from selenium import webdriver
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        from selenium.webdriver.chrome.service import Service
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    except Exception:
        driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(15)
    driver.set_script_timeout(10)
    return driver


def _get_fast_driver():
    if hasattr(_thread_local, 'driver'):
        try:
            _thread_local.driver.title
        except Exception:
            try: _thread_local.driver.quit()
            except Exception: pass
            del _thread_local.driver
    if not hasattr(_thread_local, 'driver'):
        _thread_local.driver = _create_fast_driver()
    return _thread_local.driver


# Patch scraper to use fast driver + minimal delays
scrape_card_prices._thread_local = _thread_local
scrape_card_prices.get_driver = _get_fast_driver
_orig_sleep = time.sleep
scrape_card_prices.time = type(time)('time')
scrape_card_prices.time.sleep = lambda s: _orig_sleep(min(s, 0.3))
scrape_card_prices.time.time = time.time


# ── Card name builder ─────────────────────────────────────────────────────────

def build_card_name(row: dict) -> str:
    """Build a card name string from card_catalog row compatible with process_card()."""
    name = f"{row['year']} {row['brand']} - {row['set_name']}"
    if row['card_number']:
        name += f" #{row['card_number']}"
    name += f" - {row['player_name']}"
    variant = (row.get('variant') or '').strip()
    if variant and variant.lower() not in ('base', ''):
        if row.get('print_run'):
            name += f" /{row['print_run']}"
        else:
            name += f" {variant}"
    return name.strip()


# ── DB helpers ────────────────────────────────────────────────────────────────

def load_cards(args) -> list:
    """Query card_catalog for cards to scrape, prioritising unscraped + rookies.

    SCD Type 2 delta strategy:
      - Never-scraped cards are always included.
      - Previously-scraped cards are only included when their price is stale
        (older than --stale-days, default 7).  This avoids firing up Chrome for
        cards whose price hasn't had time to meaningfully change.
      - The existing fair_value is returned alongside each card so callers can
        log or compare against the newly scraped result.
    """
    conditions = ["cc.player_name != ''", "cc.set_name != ''"]
    params = []

    if args.sport:
        conditions.append("cc.sport = %s")
        params.append(args.sport.upper())
    if args.year:
        conditions.append("cc.year = %s")
        params.append(args.year)

    # --tier shorthand (legacy)
    tier = getattr(args, 'tier', None)
    if tier == 'rookies':
        conditions.append("cc.is_rookie = TRUE")
    elif tier == 'recent':
        conditions.append("SPLIT_PART(cc.year,'-',1) ~ '^[0-9]{4}$'")
        conditions.append("SPLIT_PART(cc.year,'-',1)::int >= 2015")
    elif tier == 'rookie_recent':
        conditions.append("cc.is_rookie = TRUE")
        conditions.append("SPLIT_PART(cc.year,'-',1) ~ '^[0-9]{4}$'")
        conditions.append("SPLIT_PART(cc.year,'-',1)::int >= 2015")
    elif tier == 'serialized':
        conditions.append("cc.print_run IS NOT NULL")

    # --catalog-tier: filter by assigned scrape_tier column
    catalog_tier = getattr(args, 'catalog_tier', None)
    if catalog_tier:
        conditions.append("cc.scrape_tier = %s")
        params.append(catalog_tier)

    # --year-from / --year-to for range scraping
    if getattr(args, 'year_from', None):
        conditions.append("SPLIT_PART(cc.year,'-',1) ~ '^[0-9]{4}$'")
        conditions.append("SPLIT_PART(cc.year,'-',1)::int >= %s")
        params.append(args.year_from)
    if getattr(args, 'year_to', None):
        conditions.append("SPLIT_PART(cc.year,'-',1) ~ '^[0-9]{4}$'")
        conditions.append("SPLIT_PART(cc.year,'-',1)::int <= %s")
        params.append(args.year_to)

    if getattr(args, 'rookies', False):
        conditions.append("cc.is_rookie = TRUE")

    where = " AND ".join(conditions)
    limit_clause = f"LIMIT {args.limit}" if args.limit > 0 else ""

    if args.force:
        join_clause = ""
        select_extra = "NULL::numeric AS existing_price, NULL::timestamptz AS last_scraped"
        order_clause = "cc.is_rookie DESC, cc.year DESC, cc.player_name"
    else:
        # Delta gate: only pick up cards whose price is stale (or never scraped).
        # --stale-days controls the recency window (default 7 days).
        stale_days = getattr(args, 'stale_days', 7)
        join_clause = "LEFT JOIN market_prices mp ON mp.card_catalog_id = cc.id"
        conditions.append(f"(mp.scraped_at IS NULL OR mp.scraped_at < NOW() - INTERVAL '{stale_days} days')")
        where = " AND ".join(conditions)
        select_extra = "mp.fair_value AS existing_price, mp.scraped_at AS last_scraped"
        order_clause = "mp.scraped_at NULLS FIRST, cc.is_rookie DESC, cc.year DESC"

    sql = f"""
        SELECT cc.id, cc.sport, cc.year, cc.brand, cc.set_name,
               cc.card_number, cc.player_name, cc.team,
               cc.variant, cc.print_run, cc.is_rookie, cc.search_query,
               {select_extra}
        FROM card_catalog cc
        {join_clause}
        WHERE {where}
        ORDER BY {order_clause}
        {limit_clause}
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]

    never_scraped = sum(1 for r in rows if r['last_scraped'] is None)
    stale         = len(rows) - never_scraped
    print(f"  Delta check: {never_scraped:,} never scraped, {stale:,} stale — {len(rows):,} total to scrape")
    return rows


def bump_tiers_by_sales(catalog_ids: list):
    """After scraping, demote cards whose actual sales don't support their tier.

    Thresholds (30-day sales window):
      >= 10 sales  → stay/become staple
       3–9 sales   → premium
       1–2 sales   → stars
         0 sales   → base (on-demand only)

    Cards are only ever moved DOWN, never promoted by this function.
    Promotion (e.g. a base card that suddenly has 15 sales) can be done
    by re-running assign_catalog_tiers.py --all.
    """
    if not catalog_ids:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE card_catalog cc
                SET scrape_tier = CASE
                    WHEN mp.num_sales >= 10 THEN 'staple'
                    WHEN mp.num_sales >= 3  THEN 'premium'
                    WHEN mp.num_sales >= 1  THEN 'stars'
                    ELSE 'base'
                END
                FROM market_prices mp
                WHERE mp.card_catalog_id = cc.id
                  AND cc.id = ANY(%s)
                  AND CASE
                        WHEN mp.num_sales >= 10 THEN 'staple'
                        WHEN mp.num_sales >= 3  THEN 'premium'
                        WHEN mp.num_sales >= 1  THEN 'stars'
                        ELSE 'base'
                      END < cc.scrape_tier  -- only demote, never promote
            """, (catalog_ids,))
            bumped = cur.rowcount
        conn.commit()
    if bumped:
        print(f"  Tier bumps: {bumped} card(s) demoted based on sales data")


def save_prices_batch(results: list):
    """Write a batch of scrape results to market_prices + market_price_history.

    Args:
        results: list of (catalog_id, stats_dict) tuples with num_sales > 0
    """
    if not results:
        return
    today = date.today()
    now = datetime.utcnow()

    mp_rows = []
    hist_rows = []
    for catalog_id, stats in results:
        fair_value = round(stats.get('fair_price', 0), 2)
        num_sales  = stats.get('num_sales', 0)
        confidence = stats.get('confidence', 'none')
        min_price  = stats.get('min', 0) or 0
        max_price  = stats.get('max', 0) or 0
        top_3      = ' | '.join(str(p) for p in stats.get('top_3_prices', []))
        trend      = stats.get('trend', 'no data')

        mp_rows.append((catalog_id, fair_value, trend, confidence, num_sales, now))
        hist_rows.append((catalog_id, today, fair_value, confidence, num_sales,
                          top_3, min_price, max_price))

    with get_db() as conn:
        with conn.cursor() as cur:
            from psycopg2.extras import execute_values
            execute_values(cur, """
                INSERT INTO market_prices
                    (card_catalog_id, fair_value, trend, confidence, num_sales, scraped_at)
                VALUES %s
                ON CONFLICT (card_catalog_id) DO UPDATE SET
                    prev_value = market_prices.fair_value,
                    fair_value = EXCLUDED.fair_value,
                    trend      = EXCLUDED.trend,
                    confidence = EXCLUDED.confidence,
                    num_sales  = EXCLUDED.num_sales,
                    scraped_at = EXCLUDED.scraped_at,
                    updated_at = NOW()
            """, mp_rows)

            # SCD Type 2: only insert history row when fair_value changed
            execute_values(cur, """
                INSERT INTO market_price_history
                    (card_catalog_id, scraped_at, fair_value, confidence, num_sales,
                     top_3_prices, min_price, max_price, source)
                SELECT i.card_catalog_id, i.scraped_at, i.fair_value, i.confidence,
                       i.num_sales, i.top_3_prices, i.min_price, i.max_price, i.source
                FROM (VALUES %s) AS i(card_catalog_id, scraped_at, fair_value, confidence,
                                      num_sales, top_3_prices, min_price, max_price, source)
                WHERE NOT EXISTS (
                    SELECT 1 FROM market_price_history h
                    WHERE h.card_catalog_id = i.card_catalog_id
                      AND h.fair_value = i.fair_value
                      AND h.scraped_at = (
                          SELECT MAX(scraped_at) FROM market_price_history
                          WHERE card_catalog_id = i.card_catalog_id
                      )
                )
                ON CONFLICT (card_catalog_id, scraped_at) DO NOTHING
            """, [(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], 'ebay')
                  for r in hist_rows])
        conn.commit()


# ── Scrape workers ────────────────────────────────────────────────────────────

def scrape_one(card: dict) -> tuple:
    """Scrape a single raw (ungraded) card. Returns (catalog_id, result_dict).

    After fetching from eBay, compares new fair_value against the card's
    existing_price (loaded from market_prices).  A 'delta' is recorded in
    _progress only when the price actually changed — confirming the SCD Type 2
    history row will be written.
    """
    card_name = build_card_name(card)
    for attempt in range(2):
        try:
            _, result = process_card(card_name)
            stats = result.get('stats', {})
            new_price = round(stats.get('fair_price', 0), 2)
            old_price = card.get('existing_price')
            with _lock:
                _progress['done'] += 1
                if stats.get('num_sales', 0) > 0:
                    _progress['found'] += 1
                    if old_price is None or abs(float(old_price) - new_price) > 0.01:
                        _progress['deltas'] += 1
                else:
                    _progress['not_found'] += 1
            return card['id'], result
        except Exception:
            if attempt == 0:
                try:
                    if hasattr(_thread_local, 'driver'): _thread_local.driver.quit()
                except Exception: pass
                if hasattr(_thread_local, 'driver'): del _thread_local.driver
                continue
            with _lock:
                _progress['done'] += 1
                _progress['errors'] += 1
            return card['id'], {'stats': {}, 'raw_sales': []}


def scrape_one_graded(card: dict, grades: list) -> tuple:
    """Scrape graded prices for a single card across multiple grade variants."""
    base_name = build_card_name(card)
    results = {}

    psa = [g for g in PSA_PROBE_ORDER if g in grades]
    bgs = [g for g in BGS_PROBE_ORDER if g in grades]

    for group in [psa, bgs]:
        skip_rest = False
        for grade in group:
            if skip_rest:
                results[grade] = {'fair_value': 0, 'num_sales': 0, 'stats': {}}
                continue
            graded_name = f"{base_name} [{grade}]"
            for attempt in range(2):
                try:
                    _, result = process_card(graded_name)
                    stats = result.get('stats', {})
                    num_sales = stats.get('num_sales', 0)
                    results[grade] = {
                        'fair_value': round(stats.get('fair_price', 0), 2) if num_sales > 0 else 0,
                        'num_sales': num_sales,
                        'stats': stats,
                    }
                    if num_sales == 0 and grade == group[0]:
                        skip_rest = True
                    with _lock:
                        _progress['done'] += 1
                        if num_sales > 0: _progress['found'] += 1
                        else: _progress['not_found'] += 1
                    break
                except Exception:
                    if attempt == 0:
                        try:
                            if hasattr(_thread_local, 'driver'): _thread_local.driver.quit()
                        except Exception: pass
                        if hasattr(_thread_local, 'driver'): del _thread_local.driver
                        continue
                    with _lock:
                        _progress['done'] += 1
                        _progress['errors'] += 1
                    results[grade] = {'fair_value': 0, 'num_sales': 0, 'stats': {}}

    return card['id'], results


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Scrape eBay prices for card_catalog")
    parser.add_argument('--workers',       type=int,   default=5,    help="Parallel Chrome instances")
    parser.add_argument('--sport',         type=str,   default=None, help="NHL|NBA|NFL|MLB")
    parser.add_argument('--year',          type=str,   default=None, help="Exact year e.g. 2024-25")
    parser.add_argument('--year-from',     type=int,   default=None, dest='year_from', help="Start year e.g. 2015")
    parser.add_argument('--year-to',       type=int,   default=None, dest='year_to',   help="End year e.g. 2024")
    parser.add_argument('--tier',          type=str,   default=None,
                        choices=['rookies','recent','rookie_recent','serialized'],
                        help="Scrape tier: rookies=RC only, recent=2015+, rookie_recent=RC 2015+, serialized=print_run set")
    parser.add_argument('--catalog-tier', type=str,   default=None, dest='catalog_tier',
                        choices=['staple','premium','stars','base'],
                        help="Filter by assigned scrape_tier (set by assign_catalog_tiers.py)")
    parser.add_argument('--rookies',       action='store_true',      help="Rookies only (alias for --tier rookies)")
    parser.add_argument('--force',         action='store_true',      help="Re-scrape already-scraped cards")
    parser.add_argument('--limit',         type=int,   default=0,    help="Max cards per run (0=all)")
    parser.add_argument('--graded',        action='store_true',      help="Scrape PSA/BGS graded prices")
    parser.add_argument('--grades',        type=str,   default=None, help="Grades e.g. 'PSA 10,BGS 9.5'")
    parser.add_argument('--min-raw-value', type=float, default=5.0,  help="Min raw value for graded")
    parser.add_argument('--stale-days',    type=int,   default=7,    dest='stale_days',
                        help="Re-scrape cards not updated in this many days (default 7). "
                             "Use --force to ignore entirely.")
    args = parser.parse_args()

    if args.graded:
        grades = [g.strip() for g in args.grades.split(',')] if args.grades else ALL_GRADES
        invalid = [g for g in grades if g not in ALL_GRADES]
        if invalid:
            print(f"ERROR: Unknown grades: {invalid}. Valid: {ALL_GRADES}")
            sys.exit(1)

    print("Loading cards from catalog...")
    cards = load_cards(args)

    if not cards:
        print("No cards to scrape. Use --force to re-scrape already-scraped cards.")
        return

    total = len(cards)
    mode = "GRADED" if args.graded else "RAW"
    print(f"\n{'='*60}")
    print(f"{mode} SCRAPE — {total:,} cards | {args.workers} workers")
    if args.sport:      print(f"  Sport:      {args.sport}")
    if args.year:       print(f"  Year:       {args.year}")
    if args.year_from:  print(f"  Year from:  {args.year_from}")
    if args.year_to:    print(f"  Year to:    {args.year_to}")
    if args.catalog_tier: print(f"  Catalog tier: {args.catalog_tier}")
    elif args.tier:       print(f"  Tier:         {args.tier}")
    elif args.rookies:    print(f"  Rookies only")
    if not args.force:  print(f"  Stale days: {args.stale_days} (skip cards priced within {args.stale_days}d)")
    if args.graded:     print(f"  Grades:     {grades}")
    print(f"  Est. time:  ~{total * 5 / args.workers / 60:.0f} min")
    print(f"{'='*60}\n")

    start = time.time()
    batch: list = []
    BATCH_SIZE = 50

    def _flush_batch():
        nonlocal batch
        if batch:
            try:
                save_prices_batch(batch)
                if args.catalog_tier:
                    bump_tiers_by_sales([cid for cid, _ in batch])
            except Exception as e:
                print(f"  WARNING: DB write error: {e}")
            batch = []

    if args.graded:
        # ── Graded mode: filter to cards worth >= min_raw_value ──
        with get_db() as conn:
            with conn.cursor() as cur:
                ids = tuple(c['id'] for c in cards)
                cur.execute(
                    "SELECT card_catalog_id, fair_value FROM market_prices "
                    "WHERE card_catalog_id = ANY(%s) AND fair_value >= %s",
                    (list(ids), args.min_raw_value)
                )
                eligible_ids = {row[0] for row in cur.fetchall()}

        cards = [c for c in cards if c['id'] in eligible_ids]
        total = len(cards)
        print(f"Eligible for graded scrape (>= ${args.min_raw_value:.2f}): {total:,} cards\n")

        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            graded_batch = {}   # catalog_id -> {grade: {fair_value, num_sales}}
            futures = {executor.submit(scrape_one_graded, card, grades): card for card in cards}
            done_count = 0
            for future in as_completed(futures):
                catalog_id, graded_results = future.result()
                done_count += 1

                # Accumulate graded prices for this card into graded_data JSONB
                gd = {}
                for grade, data in graded_results.items():
                    if data and data.get('num_sales', 0) > 0:
                        stats = data.get('stats', {})
                        gd[grade] = {
                            'fair_value': round(stats.get('fair_price', 0), 2),
                            'num_sales':  stats.get('num_sales', 0),
                            'min':        round(stats.get('min', 0) or 0, 2),
                            'max':        round(stats.get('max', 0) or 0, 2),
                        }
                if gd:
                    graded_batch[catalog_id] = gd
                    _progress['found'] += 1

                if done_count % BATCH_SIZE == 0 or done_count == total:
                    # Flush graded_data updates into market_prices.graded_data
                    if graded_batch:
                        import json as _json
                        with get_db() as conn:
                            with conn.cursor() as cur:
                                from psycopg2.extras import execute_values
                                execute_values(cur, """
                                    INSERT INTO market_prices (card_catalog_id, graded_data)
                                    VALUES %s
                                    ON CONFLICT (card_catalog_id) DO UPDATE SET
                                        graded_data = market_prices.graded_data || EXCLUDED.graded_data,
                                        updated_at  = NOW()
                                """, [(cid, _json.dumps(gdata))
                                      for cid, gdata in graded_batch.items()])
                            conn.commit()
                        graded_batch.clear()
                    elapsed = time.time() - start
                    rate = done_count / elapsed if elapsed > 0 else 0
                    remaining = (total - done_count) / rate / 60 if rate > 0 else 0
                    print(f"  [{done_count}/{total}] Found: {_progress['found']} | "
                          f"Errors: {_progress['errors']} | ~{remaining:.1f}m remaining", flush=True)

    else:
        # ── Raw mode ──
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(scrape_one, card): card for card in cards}
            done_count = 0
            for future in as_completed(futures):
                catalog_id, result = future.result()
                done_count += 1
                stats = result.get('stats', {})

                if stats.get('num_sales', 0) > 0:
                    batch.append((catalog_id, stats))

                if done_count % BATCH_SIZE == 0 or done_count == total:
                    _flush_batch()
                    elapsed = time.time() - start
                    rate = done_count / elapsed if elapsed > 0 else 0
                    remaining = (total - done_count) / rate / 60 if rate > 0 else 0
                    print(f"  [{done_count}/{total}] Found: {_progress['found']} | "
                          f"Deltas: {_progress['deltas']} | "
                          f"Not found: {_progress['not_found']} | "
                          f"Errors: {_progress['errors']} | "
                          f"~{remaining:.1f}m remaining", flush=True)

    _flush_batch()
    elapsed = time.time() - start

    print(f"\n{'='*60}")
    print(f"DONE in {elapsed/60:.1f} minutes")
    print(f"  Scraped:    {_progress['done']:,}")
    print(f"  Found:      {_progress['found']:,}")
    print(f"  Deltas:     {_progress['deltas']:,}  (price changed → history row written)")
    print(f"  Not found:  {_progress['not_found']:,}")
    print(f"  Errors:     {_progress['errors']:,}")
    print(f"  Written to: market_prices + market_price_history (PostgreSQL)")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
