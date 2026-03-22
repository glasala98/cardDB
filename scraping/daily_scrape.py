#!/usr/bin/env python3
"""Daily scrape job — rescrapes all cards in the existing database,
updates prices, and appends fair-value snapshots to PostgreSQL.

Usage:
    python daily_scrape.py                  # scrape all users
    python daily_scrape.py --user admin     # scrape one user
    python daily_scrape.py --workers 3      # limit parallel browsers
"""

import os
import sys
import argparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

from dotenv import load_dotenv
load_dotenv()

import os as _os, sys as _sys
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)
from scrape_card_prices import process_card
from dashboard_utils import (
    load_data, save_data,
    load_all_card_results, save_card_results,
    append_price_history, append_portfolio_snapshot,
    load_users,
)


def daily_scrape_user(username: str, max_workers: int = 3) -> None:
    """Scrape and update prices for all cards belonging to one user.

    Workflow:
      1. Loads all card names from Supabase via load_data().
      2. Pre-loads all existing card results (raw_sales, image_url, etc.)
         in a single bulk query.
      3. Scrapes each card in parallel using process_card() across up to
         max_workers Chrome instances.
      4. Merges new eBay sales with the existing raw_sales list
         (deduplicates by sold_date + title, sorts most-recent-first).
      5. Updates Fair Value, Trend, Median, Min, Max, Num Sales, and Top 3
         Prices columns in the DataFrame for any card with sales found.
      6. Upserts updated card stats and results back to PostgreSQL.
      7. Appends a portfolio snapshot (total value, card count, avg value)
         to PostgreSQL.

    Args:
        username: Username whose collection to scrape.
        max_workers: Number of parallel Chrome browser instances to use.
    """
    start = datetime.now()
    print(f"[{start.strftime('%Y-%m-%d %H:%M:%S')}] Scrape starting for {username}")

    df = load_data(username)
    card_names = df['Card Name'].tolist()
    if not card_names:
        print("  No cards to scrape.")
        return
    print(f"Scraping {len(card_names)} cards with {max_workers} workers")

    # Bulk-load existing results (single Supabase query)
    existing_results = load_all_card_results(username)

    completed = 0
    total = len(card_names)
    updated = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_card, card): card for card in card_names}

        for future in as_completed(futures):
            card = futures[future]
            completed += 1
            try:
                card_name, result = future.result()
                stats = result.get('stats', {})
                num_sales = stats.get('num_sales', 0)
                fair_price = stats.get('fair_price', 0)

                # Merge new sales with existing (accumulate history)
                existing = existing_results.get(card_name, {})
                existing_sales = existing.get('raw_sales', []) or []
                new_sales = result.get('raw_sales', [])
                seen = set()
                merged = []
                for sale in new_sales + existing_sales:
                    key = (sale.get('sold_date', ''), sale.get('title', ''))
                    if key not in seen:
                        seen.add(key)
                        merged.append(sale)
                merged.sort(key=lambda s: s.get('sold_date') or '0000-00-00', reverse=True)

                scraped_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                # Preserve existing image_url — only fetch once (first scrape that finds one)
                image_url = result.get('image_url') or existing.get('image_url') or ''

                save_card_results(
                    username, card_name,
                    raw_sales=merged,
                    scraped_at=scraped_at,
                    confidence=stats.get('confidence', ''),
                    image_url=image_url,
                    image_hash=existing.get('image_hash') or '',
                    image_url_back=existing.get('image_url_back') or '',
                    search_url=existing.get('search_url') or '',
                    is_estimated=stats.get('is_estimated', False),
                    price_source=stats.get('price_source', 'direct'),
                )

                # Update the dataframe row
                idx = df[df['Card Name'] == card_name].index
                if len(idx) > 0:
                    i = idx[0]
                    if num_sales > 0:
                        trend = stats.get('trend', 'no data')
                        if trend in ('insufficient data', 'unknown'):
                            trend = 'no data'
                        df.at[i, 'Fair Value']   = fair_price
                        df.at[i, 'Trend']        = trend
                        df.at[i, 'Median (All)'] = stats.get('median_all', 0)
                        df.at[i, 'Min']          = stats.get('min', 0)
                        df.at[i, 'Max']          = stats.get('max', 0)
                        df.at[i, 'Num Sales']    = num_sales
                        df.at[i, 'Top 3 Prices'] = ' | '.join(stats.get('top_3_prices', []))

                        append_price_history(username, card_name, fair_price, num_sales)
                        updated += 1

                    status = f"${fair_price:.2f} ({num_sales} sales)" if num_sales > 0 else "no sales"
                    print(f"  [{completed}/{total}] {card_name[:60]}... {status}")

            except Exception as e:
                failed += 1
                print(f"  [{completed}/{total}] {card[:60]}... ERROR: {e}")

    # Save updated card collection
    save_data(df, username)

    # Append portfolio snapshot
    found = df[df['Num Sales'] > 0]
    total_value = found['Fair Value'].sum()
    total_cards = len(df)
    avg_value = total_value / total_cards if total_cards > 0 else 0
    append_portfolio_snapshot(username, total_value, total_cards, avg_value)
    print(f"  Portfolio snapshot: ${total_value:,.2f} ({total_cards} cards)")

    elapsed = (datetime.now() - start).total_seconds()
    print(f"Scrape complete in {elapsed:.0f}s")
    print(f"  Updated: {updated} | No sales: {total - updated - failed} | Failed: {failed}")


def daily_scrape(max_workers: int = 3, user: str = None) -> None:
    """Scrape price data for one user or all users defined in users.yaml.

    Loads users.yaml to discover usernames. If users.yaml is absent
    (legacy single-user mode), falls back to 'admin'. When a specific user
    is requested but not found, the process exits with a non-zero status.

    Args:
        max_workers: Number of parallel Chrome browser instances per user.
        user: Username to scrape exclusively, or None to scrape all users.
    """
    users = load_users()

    if not users:
        # No users.yaml — default to admin
        print("=== Daily scrape (admin) ===")
        daily_scrape_user("admin", max_workers)
        return

    if user:
        if user not in users:
            print(f"Error: user '{user}' not found in users.yaml")
            sys.exit(1)
        targets = [user]
    else:
        targets = list(users.keys())

    for username in targets:
        print(f"\n=== Scraping {username}'s collection ===")
        daily_scrape_user(username, max_workers)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Daily card price scraper")
    parser.add_argument('--workers', type=int, default=3, help="Parallel browser instances (default: 3)")
    parser.add_argument('--user', type=str, default=None, help="Scrape only this user (default: all users)")
    args = parser.parse_args()
    daily_scrape(max_workers=args.workers, user=args.user)
