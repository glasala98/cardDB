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
from dashboard_utils import append_yg_price_history, append_yg_portfolio_snapshot

MASTER_DB_PATH = os.path.join(SCRIPT_DIR, "data", "master_db", "young_guns.csv")

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


def main():
    parser = argparse.ArgumentParser(description="Bulk scrape Master DB cards on eBay")
    parser.add_argument('--workers', type=int, default=15, help="Number of parallel Chrome instances (default: 15)")
    parser.add_argument('--season', type=str, default=None, help="Scrape only this season (e.g. '2024-25')")
    parser.add_argument('--force', action='store_true', help="Re-scrape already-scraped cards")
    parser.add_argument('--limit', type=int, default=0, help="Max cards to scrape (0 = all)")
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
        # Still save in case CardName column was added
        df.to_csv(MASTER_DB_PATH, index=False)
        sys.exit(0)

    print(f"\nScraping {total} cards with {args.workers} workers...")
    print(f"Estimated time: ~{total * 5 / args.workers / 60:.0f} minutes\n")

    # Save CSV first to persist CardName column
    df.to_csv(MASTER_DB_PATH, index=False)

    start_time = time.time()
    checkpoint_counter = 0

    # Build card name list with original indices
    work_items = list(to_scrape[['CardName']].itertuples())

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {}
        for item in work_items:
            future = executor.submit(scrape_one_card, item.CardName)
            futures[future] = item.Index  # original df index

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

                # Append to price history (thread-safe: writes are serialized here)
                try:
                    append_yg_price_history(card_name, stats.get('fair_price', 0), stats.get('num_sales', 0))
                except Exception:
                    pass  # Don't let history logging break the scrape

            # Progress update every 10 cards
            done = _progress['done']
            if done % 10 == 0 or done == total:
                elapsed = time.time() - start_time
                rate = done / elapsed if elapsed > 0 else 0
                remaining = (total - done) / rate / 60 if rate > 0 else 0
                print(f"  [{done}/{total}] Found: {_progress['found']} | "
                      f"Not found: {_progress['not_found']} | "
                      f"Errors: {_progress['errors']} | "
                      f"~{remaining:.1f}m remaining", flush=True)

            # Checkpoint save every 50 cards
            if checkpoint_counter >= 50:
                checkpoint_counter = 0
                df.to_csv(MASTER_DB_PATH, index=False)
                print(f"  ** Checkpoint saved ({done} cards done)", flush=True)

    # Final save
    df.to_csv(MASTER_DB_PATH, index=False)
    elapsed = time.time() - start_time

    # Summary
    scraped_count = len(df[df['LastScraped'].notna() & (df['LastScraped'] != '')])
    total_value = df['FairValue'].sum() if df['FairValue'].notna().any() else 0

    # Append portfolio snapshot for historical tracking
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


if __name__ == '__main__':
    main()
