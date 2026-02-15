#!/usr/bin/env python3 -u
"""
Bulk scraper for Master DB — scrapes eBay sold prices for all Young Guns cards.
Uses the existing scraper infrastructure with multiple parallel Chrome instances.

Usage:
    python -u scrape_master_db.py                       # Scrape all un-scraped cards, 15 workers
    python -u scrape_master_db.py --workers 5           # Use 5 workers
    python -u scrape_master_db.py --season "2024-25"    # Scrape only one season
    python -u scrape_master_db.py --force               # Re-scrape already-scraped cards
    python -u scrape_master_db.py --limit 50            # Scrape only first 50 cards

    # Graded scraping (PSA/BGS prices)
    python -u scrape_master_db.py --graded              # Scrape graded prices for cards worth $5+
    python -u scrape_master_db.py --graded --grades "PSA 10,BGS 9.5"  # Only specific grades
    python -u scrape_master_db.py --graded --min-raw-value 2.0        # Lower the threshold
"""

import sys
import os
# Force unbuffered output
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)

import argparse
import time
import threading
import csv
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pandas as pd

# Add script dir to path for imports
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from scrape_card_prices import (
    process_card,
)
from dashboard_utils import (
    append_yg_portfolio_snapshot,
    batch_save_yg_raw_sales, batch_append_yg_price_history,
)

MASTER_DB_PATH = os.path.join(SCRIPT_DIR, "data", "master_db", "young_guns.csv")

# Grade column mappings: grade_key -> (value_col, sales_col)
GRADE_COLUMNS = {
    'PSA 8':   ('PSA8_Value',  'PSA8_Sales'),
    'PSA 9':   ('PSA9_Value',  'PSA9_Sales'),
    'PSA 10':  ('PSA10_Value', 'PSA10_Sales'),
    'BGS 9':   ('BGS9_Value',  'BGS9_Sales'),
    'BGS 9.5': ('BGS9_5_Value', 'BGS9_5_Sales'),
    'BGS 10':  ('BGS10_Value', 'BGS10_Sales'),
}

# All graded CSV columns (flat list)
GRADED_CSV_COLUMNS = []
for _vcol, _scol in GRADE_COLUMNS.values():
    GRADED_CSV_COLUMNS.extend([_vcol, _scol])
GRADED_CSV_COLUMNS.append('GradedLastScraped')

# Smart probe order: try highest grade first, skip lower if no sales
PSA_PROBE_ORDER = ['PSA 10', 'PSA 9', 'PSA 8']
BGS_PROBE_ORDER = ['BGS 10', 'BGS 9.5', 'BGS 9']

# Thread-local storage for Chrome drivers (reused by process_card via get_driver)
_thread_local = threading.local()
_lock = threading.Lock()
_progress = {"done": 0, "found": 0, "not_found": 0, "errors": 0}


def build_card_name(row):
    """Convert a master DB row into the standard card name format used by the scraper.

    Format: "SEASON Upper Deck - Young Guns #CARDNUM - PLAYER"
    Example: "2023-24 Upper Deck - Young Guns #201 - Connor Bedard"
    """
    season = row['Season']
    card_num = int(row['CardNumber'])
    player = row['PlayerName']
    return f"{season} Upper Deck - Young Guns #{card_num} - {player}"


def _create_fast_driver():
    """Create a lean Chrome driver optimized for bulk scraping."""
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    opts = ChromeOptions()
    opts.add_argument('--headless')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--window-size=1280,720')
    opts.add_argument('--disable-extensions')
    opts.add_argument('--disable-images')
    opts.add_argument('--blink-settings=imagesEnabled=false')
    opts.add_argument('--ignore-certificate-errors')
    opts.add_argument('--disable-blink-features=AutomationControlled')
    opts.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    opts.add_experimental_option('excludeSwitches', ['enable-automation'])
    opts.page_load_strategy = 'eager'  # Don't wait for images/subresources
    from selenium import webdriver
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(15)
    driver.set_script_timeout(10)
    return driver


def get_fast_driver():
    """Get or create a Chrome driver for the current thread.
    Automatically recreates if the previous one crashed."""
    if hasattr(_thread_local, 'driver'):
        try:
            _thread_local.driver.title  # quick health check
        except Exception:
            try:
                _thread_local.driver.quit()
            except Exception:
                pass
            del _thread_local.driver
    if not hasattr(_thread_local, 'driver'):
        _thread_local.driver = _create_fast_driver()
    return _thread_local.driver


# Monkey-patch the scraper's get_driver to use our fast version
import scrape_card_prices
scrape_card_prices._thread_local = _thread_local
scrape_card_prices.get_driver = get_fast_driver

# Reduce the delay inside process_card by patching time.sleep for the scraper module
_original_sleep = time.sleep
def _fast_sleep(seconds):
    """Cap sleep to 0.3s max during bulk scraping."""
    _original_sleep(min(seconds, 0.3))
scrape_card_prices.time = type(time)('time')
scrape_card_prices.time.sleep = _fast_sleep
scrape_card_prices.time.time = time.time


def scrape_one_card(card_name):
    """Scrape a single card with retry on driver crash.
    Returns (card_name, result_dict).
    """
    for attempt in range(2):
        try:
            name, result = process_card(card_name)
            stats = result.get('stats', {})
            if stats.get('num_sales', 0) > 0:
                with _lock:
                    _progress['found'] += 1
            else:
                with _lock:
                    _progress['not_found'] += 1
            return (name, result)
        except Exception as e:
            if attempt == 0:
                # Kill dead driver so get_fast_driver recreates it
                try:
                    if hasattr(_thread_local, 'driver'):
                        _thread_local.driver.quit()
                except Exception:
                    pass
                if hasattr(_thread_local, 'driver'):
                    del _thread_local.driver
                continue
            with _lock:
                _progress['errors'] += 1
            return (card_name, {'estimated_value': None, 'stats': {}, 'raw_sales': [], 'search_url': None})
        finally:
            with _lock:
                _progress['done'] += 1


def scrape_one_graded_card(card_name, grades_to_scrape):
    """Scrape graded prices for a single card across multiple grades.
    Uses smart probing: if PSA 10 has 0 sales, skip PSA 9 and 8.

    Args:
        card_name: Base card name (no grade suffix)
        grades_to_scrape: List of grade keys like ['PSA 10', 'PSA 9', 'BGS 9.5']

    Returns:
        dict of {grade_key: {'fair_value': float, 'num_sales': int, 'raw_sales': list}} for grades with data
    """
    results = {}

    # Split into PSA and BGS groups for smart probing
    psa_grades = [g for g in PSA_PROBE_ORDER if g in grades_to_scrape]
    bgs_grades = [g for g in BGS_PROBE_ORDER if g in grades_to_scrape]

    for probe_group in [psa_grades, bgs_grades]:
        skip_rest = False
        for grade_key in probe_group:
            if skip_rest:
                results[grade_key] = {'fair_value': 0, 'num_sales': 0}
                continue

            # Build graded card name: append [PSA 10] or [BGS 9.5] to the card name
            graded_name = f"{card_name} [{grade_key}]"

            for attempt in range(2):
                try:
                    _, result = process_card(graded_name)
                    stats = result.get('stats', {})
                    num_sales = stats.get('num_sales', 0)
                    fair_price = stats.get('fair_price', 0)

                    results[grade_key] = {
                        'fair_value': round(fair_price, 2) if num_sales > 0 else 0,
                        'num_sales': num_sales,
                        'raw_sales': result.get('raw_sales', []),
                    }

                    # Smart probing: if top grade has 0 sales, skip lower grades
                    if num_sales == 0 and grade_key == probe_group[0]:
                        skip_rest = True

                    with _lock:
                        _progress['done'] += 1
                        if num_sales > 0:
                            _progress['found'] += 1
                        else:
                            _progress['not_found'] += 1
                    break
                except Exception:
                    if attempt == 0:
                        try:
                            if hasattr(_thread_local, 'driver'):
                                _thread_local.driver.quit()
                        except Exception:
                            pass
                        if hasattr(_thread_local, 'driver'):
                            del _thread_local.driver
                        continue
                    with _lock:
                        _progress['done'] += 1
                        _progress['errors'] += 1
                    results[grade_key] = {'fair_value': 0, 'num_sales': 0}

    return results


def main():
    parser = argparse.ArgumentParser(description="Bulk scrape Master DB cards on eBay")
    parser.add_argument('--workers', type=int, default=15, help="Number of parallel Chrome instances (default: 15)")
    parser.add_argument('--season', type=str, default=None, help="Scrape only this season (e.g. '2024-25')")
    parser.add_argument('--force', action='store_true', help="Re-scrape already-scraped cards")
    parser.add_argument('--limit', type=int, default=0, help="Max cards to scrape (0 = all)")
    parser.add_argument('--graded', action='store_true', help="Scrape graded prices (PSA 8/9/10, BGS 9/9.5/10)")
    parser.add_argument('--grades', type=str, default=None,
                        help="Comma-separated grades to scrape (e.g. 'PSA 10,BGS 9.5'). Default: all 6")
    parser.add_argument('--min-raw-value', type=float, default=5.0,
                        help="Skip graded scraping for cards with raw value below this (default: $5)")
    args = parser.parse_args()

    # Load master DB
    if not os.path.exists(MASTER_DB_PATH):
        print(f"ERROR: Master DB not found at {MASTER_DB_PATH}")
        sys.exit(1)

    df = pd.read_csv(MASTER_DB_PATH)
    print(f"Loaded {len(df)} cards from Master DB")

    # Add price columns if missing
    for col in ['CardName', 'FairValue', 'NumSales', 'Min', 'Max', 'Trend', 'Top3Prices', 'LastScraped']:
        if col not in df.columns:
            if col in ('FairValue', 'NumSales', 'Min', 'Max'):
                df[col] = pd.NA
            else:
                df[col] = ''

    # Add graded columns if missing
    for col in GRADED_CSV_COLUMNS:
        if col not in df.columns:
            if col == 'GradedLastScraped':
                df[col] = ''
            else:
                df[col] = pd.NA

    # Build CardName for all rows (always refresh in case format changes)
    df['CardName'] = df.apply(build_card_name, axis=1)

    # Filter by season
    if args.season:
        season_mask = df['Season'] == args.season
        if season_mask.sum() == 0:
            print(f"ERROR: No cards found for season '{args.season}'")
            print(f"Available seasons: {sorted(df['Season'].unique().tolist())}")
            sys.exit(1)
        print(f"Filtering to season {args.season}: {season_mask.sum()} cards")

    # Parse grade list if provided
    if args.grades:
        grades_to_scrape = [g.strip() for g in args.grades.split(',')]
        invalid = [g for g in grades_to_scrape if g not in GRADE_COLUMNS]
        if invalid:
            print(f"ERROR: Invalid grades: {invalid}")
            print(f"Valid grades: {list(GRADE_COLUMNS.keys())}")
            sys.exit(1)
    else:
        grades_to_scrape = list(GRADE_COLUMNS.keys())

    if args.graded:
        # ── GRADED SCRAPING MODE ──
        _run_graded_scrape(df, args, grades_to_scrape)
    else:
        # ── RAW SCRAPING MODE (existing behavior) ──
        _run_raw_scrape(df, args)


def _run_raw_scrape(df, args):
    """Original raw/ungraded scraping pass."""
    # Determine which cards to scrape
    if args.force:
        to_scrape = df.copy()
    else:
        to_scrape = df[df['LastScraped'].isna() | (df['LastScraped'] == '')].copy()

    if args.season:
        to_scrape = to_scrape[to_scrape['Season'] == args.season]

    if args.limit > 0:
        to_scrape = to_scrape.head(args.limit)

    total = len(to_scrape)
    if total == 0:
        print("No cards to scrape. Use --force to re-scrape.")
        df.to_csv(MASTER_DB_PATH, index=False)
        sys.exit(0)

    print(f"\nScraping {total} cards with {args.workers} workers...")
    print(f"Estimated time: ~{total * 5 / args.workers / 60:.0f} minutes\n")

    df.to_csv(MASTER_DB_PATH, index=False)

    start_time = time.time()
    checkpoint_counter = 0

    # Batch accumulators — write to disk at checkpoints instead of per-card
    pending_history = {}
    pending_raw_sales = {}

    work_items = list(to_scrape[['CardName']].itertuples())

    def _flush_pending():
        """Write accumulated JSON data to disk."""
        nonlocal pending_history, pending_raw_sales
        if pending_history:
            try:
                batch_append_yg_price_history(pending_history)
            except Exception:
                pass
            pending_history = {}
        if pending_raw_sales:
            try:
                batch_save_yg_raw_sales(pending_raw_sales)
            except Exception:
                pass
            pending_raw_sales = {}

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {}
        for item in work_items:
            future = executor.submit(scrape_one_card, item.CardName)
            futures[future] = item.Index

        for future in as_completed(futures):
            idx = futures[future]
            card_name, result = future.result()
            checkpoint_counter += 1

            stats = result.get('stats', {})
            if stats.get('num_sales', 0) > 0:
                df.at[idx, 'FairValue'] = round(stats.get('fair_price', 0), 2)
                df.at[idx, 'NumSales'] = stats.get('num_sales', 0)
                df.at[idx, 'Min'] = stats.get('min', 0)
                df.at[idx, 'Max'] = stats.get('max', 0)
                df.at[idx, 'Trend'] = stats.get('trend', 'no data')
                df.at[idx, 'Top3Prices'] = ' | '.join(stats.get('top_3_prices', []))
                df.at[idx, 'LastScraped'] = datetime.now().strftime('%Y-%m-%d %H:%M')

                # Accumulate for batch write
                pending_history[card_name] = {
                    'fair_value': stats.get('fair_price', 0),
                    'num_sales': stats.get('num_sales', 0),
                }

                raw_sales = result.get('raw_sales', [])
                if raw_sales:
                    pending_raw_sales[card_name] = raw_sales

            done = checkpoint_counter
            if done % 10 == 0 or done == total:
                elapsed = time.time() - start_time
                rate = done / elapsed if elapsed > 0 else 0
                remaining = (total - done) / rate / 60 if rate > 0 else 0
                print(f"  [{done}/{total}] Found: {_progress['found']} | "
                      f"Not found: {_progress['not_found']} | "
                      f"Errors: {_progress['errors']} | "
                      f"~{remaining:.1f}m remaining", flush=True)

            if checkpoint_counter >= 50:
                checkpoint_counter = 0
                df.to_csv(MASTER_DB_PATH, index=False)
                _flush_pending()
                print(f"  ** Checkpoint saved ({done} cards done)", flush=True)

    # Final flush
    _flush_pending()

    df.to_csv(MASTER_DB_PATH, index=False)
    elapsed = time.time() - start_time

    scraped_count = len(df[df['LastScraped'].notna() & (df['LastScraped'] != '')])
    total_value = df['FairValue'].sum() if df['FairValue'].notna().any() else 0

    avg_value = total_value / scraped_count if scraped_count > 0 else 0
    try:
        append_yg_portfolio_snapshot(total_value, len(df), avg_value, scraped_count)
        print(f"  Portfolio snapshot saved for {datetime.now().strftime('%Y-%m-%d')}", flush=True)
    except Exception as e:
        print(f"  Warning: Could not save portfolio snapshot: {e}", flush=True)

    print(f"\n{'='*60}")
    print(f"DONE in {elapsed/60:.1f} minutes")
    print(f"  Cards scraped:    {_progress['done']}")
    print(f"  Prices found:     {_progress['found']}")
    print(f"  Not found:        {_progress['not_found']}")
    print(f"  Errors:           {_progress['errors']}")
    print(f"  Total DB scraped: {scraped_count}/{len(df)}")
    print(f"  Total value:      ${total_value:,.2f}")
    print(f"  Saved to:         {MASTER_DB_PATH}")
    print(f"{'='*60}")


def _run_graded_scrape(df, args, grades_to_scrape):
    """Graded scraping pass — scrapes PSA/BGS prices for cards above min raw value."""
    min_val = args.min_raw_value

    # Filter to cards that have been raw-scraped and meet minimum value
    # Always scrape all eligible cards so new graded listings are discovered
    has_raw = df['FairValue'].notna() & (df['FairValue'] >= min_val)
    to_scrape = df[has_raw].copy()

    if args.season:
        to_scrape = to_scrape[to_scrape['Season'] == args.season]

    if args.limit > 0:
        to_scrape = to_scrape.head(args.limit)

    total_cards = len(to_scrape)
    if total_cards == 0:
        print(f"No cards to graded-scrape (min raw value: ${min_val:.2f}). Use --force to re-scrape.")
        df.to_csv(MASTER_DB_PATH, index=False)
        sys.exit(0)

    # Each card gets up to len(grades_to_scrape) scrapes, but smart probing reduces this
    max_scrapes = total_cards * len(grades_to_scrape)
    print(f"\n{'='*60}")
    print(f"GRADED SCRAPING MODE")
    print(f"  Cards to scrape:  {total_cards} (raw value >= ${min_val:.2f})")
    print(f"  Grades:           {', '.join(grades_to_scrape)}")
    print(f"  Max scrapes:      {max_scrapes} (smart probing will reduce this)")
    print(f"  Workers:          {args.workers}")
    print(f"{'='*60}\n")

    df.to_csv(MASTER_DB_PATH, index=False)

    start_time = time.time()
    checkpoint_counter = 0

    # Batch accumulators — write to disk at checkpoints instead of per-card
    pending_history = {}
    pending_raw_sales = {}

    work_items = list(to_scrape[['CardName']].itertuples())

    def _flush_pending():
        """Write accumulated JSON data to disk."""
        nonlocal pending_history, pending_raw_sales
        if pending_history:
            try:
                batch_append_yg_price_history(pending_history)
            except Exception:
                pass
            pending_history = {}
        if pending_raw_sales:
            try:
                batch_save_yg_raw_sales(pending_raw_sales)
            except Exception:
                pass
            pending_raw_sales = {}

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {}
        for item in work_items:
            future = executor.submit(scrape_one_graded_card, item.CardName, grades_to_scrape)
            futures[future] = item.Index

        for future in as_completed(futures):
            idx = futures[future]
            graded_results = future.result()
            checkpoint_counter += 1
            card_name = df.at[idx, 'CardName']

            # Write graded results to CSV columns
            graded_prices_for_history = {}
            for grade_key, data in graded_results.items():
                val_col, sales_col = GRADE_COLUMNS[grade_key]
                df.at[idx, val_col] = data['fair_value']
                df.at[idx, sales_col] = data['num_sales']
                if data['num_sales'] > 0:
                    graded_prices_for_history[grade_key] = {
                        'fair_value': data['fair_value'],
                        'num_sales': data['num_sales'],
                    }

            df.at[idx, 'GradedLastScraped'] = datetime.now().strftime('%Y-%m-%d %H:%M')

            # Accumulate for batch write
            if graded_prices_for_history:
                raw_val = df.at[idx, 'FairValue']
                raw_sales_count = df.at[idx, 'NumSales']
                pending_history[card_name] = {
                    'fair_value': float(raw_val) if pd.notna(raw_val) else 0,
                    'num_sales': int(raw_sales_count) if pd.notna(raw_sales_count) else 0,
                    'graded_prices': graded_prices_for_history,
                }

            # Accumulate graded raw sales
            for grade_key, data in graded_results.items():
                graded_raw = data.get('raw_sales', [])
                if graded_raw:
                    graded_card_key = f"{card_name} [{grade_key}]"
                    pending_raw_sales[graded_card_key] = graded_raw

            # Progress
            cards_done = checkpoint_counter
            done = _progress['done']
            elapsed = time.time() - start_time
            if cards_done % 5 == 0 or cards_done == total_cards:
                rate = cards_done / elapsed if elapsed > 0 else 0
                remaining = (total_cards - cards_done) / rate / 60 if rate > 0 else 0
                print(f"  [{cards_done}/{total_cards} cards] Scrapes: {done} | "
                      f"Found: {_progress['found']} | "
                      f"Errors: {_progress['errors']} | "
                      f"~{remaining:.1f}m remaining", flush=True)

            if cards_done % 50 == 0:
                df.to_csv(MASTER_DB_PATH, index=False)
                _flush_pending()
                print(f"  ** Checkpoint saved ({cards_done} cards done)", flush=True)

    # Final flush
    _flush_pending()
    df.to_csv(MASTER_DB_PATH, index=False)
    elapsed = time.time() - start_time

    # Count cards with at least one graded price
    graded_with_data = 0
    for _, row in df.iterrows():
        for grade_key in grades_to_scrape:
            val_col, sales_col = GRADE_COLUMNS[grade_key]
            if pd.notna(row.get(val_col)) and row.get(val_col, 0) > 0:
                graded_with_data += 1
                break

    print(f"\n{'='*60}")
    print(f"GRADED SCRAPE DONE in {elapsed/60:.1f} minutes")
    print(f"  Total scrapes:      {_progress['done']}")
    print(f"  Prices found:       {_progress['found']}")
    print(f"  Not found:          {_progress['not_found']}")
    print(f"  Errors:             {_progress['errors']}")
    print(f"  Cards with graded:  {graded_with_data}/{total_cards}")
    print(f"  Saved to:           {MASTER_DB_PATH}")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
