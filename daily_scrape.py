#!/usr/bin/env python3
"""Daily scrape job — rescrapes all cards in the existing database,
updates prices, and appends fair-value deltas to price_history.json.

Usage:
    python daily_scrape.py                  # scrape all users
    python daily_scrape.py --user admin     # scrape one user
    python daily_scrape.py --workers 3      # limit parallel browsers

Set up as a cron job on the server:
    0 6 * * * cd /opt/card-dashboard && /usr/bin/python3 daily_scrape.py >> /var/log/daily_scrape.log 2>&1
"""

import os
import sys
import json
import argparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

from scrape_card_prices import process_card
from dashboard_utils import (
    load_data, save_data, backup_data, append_price_history, append_portfolio_snapshot,
    get_user_paths, load_users,
    CSV_PATH, RESULTS_JSON_PATH
)


def daily_scrape_user(csv_path, results_path, history_path, backup_dir, max_workers=3):
    """Scrape and update prices for all cards belonging to one user.

    Workflow:
      1. Creates a timestamped backup of the user's CSV and results JSON.
      2. Loads all card names from the CSV via load_data().
      3. Scrapes each card in parallel using process_card() across up to
         max_workers Chrome instances.
      4. Merges new eBay sales with the existing raw_sales list in the results
         JSON (deduplicates by sold_date + title, sorts most-recent-first).
      5. Updates Fair Value, Trend, Median, Min, Max, Num Sales, and Top 3
         Prices columns in the DataFrame for any card with sales found.
      6. Appends a per-card price-history entry to price_history.json.
      7. Saves the updated CSV and results JSON.
      8. Appends a portfolio snapshot (total value, card count, average value)
         to portfolio_history.json.

    Args:
        csv_path: Absolute path to the user's cards CSV file.
        results_path: Absolute path to the user's results JSON file.
        history_path: Absolute path to the user's price_history.json file.
        backup_dir: Directory where timestamped backups are written.
        max_workers: Number of parallel Chrome browser instances to use.
            Defaults to 3.
    """
    start = datetime.now()
    print(f"[{start.strftime('%Y-%m-%d %H:%M:%S')}] Scrape starting")

    # Backup before scraping
    ts = backup_data(label="daily", csv_path=csv_path, results_path=results_path, backup_dir=backup_dir)
    print(f"Backup saved: {ts}")

    # Load current card list
    df = load_data(csv_path, results_path)
    card_names = df['Card Name'].tolist()
    if not card_names:
        print("  No cards to scrape.")
        return
    print(f"Scraping {len(card_names)} cards with {max_workers} workers")

    # Load existing results JSON to merge into
    results = {}
    if os.path.exists(results_path):
        try:
            with open(results_path, 'r', encoding='utf-8') as f:
                results = json.load(f)
        except Exception:
            results = {}

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
                existing_sales = results.get(card_name, {}).get('raw_sales', [])
                new_sales = result.get('raw_sales', [])
                seen = set()
                merged = []
                for sale in new_sales + existing_sales:
                    key = (sale.get('sold_date', ''), sale.get('title', ''))
                    if key not in seen:
                        seen.add(key)
                        merged.append(sale)
                merged.sort(key=lambda s: s.get('sold_date') or '0000-00-00', reverse=True)
                result['raw_sales'] = merged
                result['scraped_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                # Preserve existing image_url — only fetch once (first scrape that finds one)
                if not result.get('image_url'):
                    result['image_url'] = results.get(card_name, {}).get('image_url')
                results[card_name] = result

                # Update the dataframe row
                idx = df[df['Card Name'] == card_name].index
                if len(idx) > 0:
                    i = idx[0]
                    if num_sales > 0:
                        trend = stats.get('trend', 'no data')
                        if trend in ('insufficient data', 'unknown'):
                            trend = 'no data'
                        df.at[i, 'Fair Value'] = fair_price
                        df.at[i, 'Trend'] = trend
                        df.at[i, 'Median (All)'] = stats.get('median_all', 0)
                        df.at[i, 'Min'] = stats.get('min', 0)
                        df.at[i, 'Max'] = stats.get('max', 0)
                        df.at[i, 'Num Sales'] = num_sales
                        df.at[i, 'Top 3 Prices'] = ' | '.join(stats.get('top_3_prices', []))

                        # Append to price history
                        append_price_history(card_name, fair_price, num_sales, history_path=history_path)
                        updated += 1

                    status = f"${fair_price:.2f} ({num_sales} sales)" if num_sales > 0 else "no sales"
                    print(f"  [{completed}/{total}] {card_name[:60]}... {status}")

            except Exception as e:
                failed += 1
                print(f"  [{completed}/{total}] {card[:60]}... ERROR: {e}")

    # Save updated CSV
    save_data(df, csv_path)

    # Save updated results JSON
    with open(results_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # Append portfolio snapshot
    found = df[df['Num Sales'] > 0]
    total_value = found['Fair Value'].sum()
    total_cards = len(df)
    avg_value = total_value / total_cards if total_cards > 0 else 0
    portfolio_path = os.path.join(os.path.dirname(history_path), "portfolio_history.json")
    append_portfolio_snapshot(total_value, total_cards, avg_value, portfolio_path=portfolio_path)
    print(f"  Portfolio snapshot: ${total_value:,.2f} ({total_cards} cards)")

    elapsed = (datetime.now() - start).total_seconds()
    print(f"Scrape complete in {elapsed:.0f}s")
    print(f"  Updated: {updated} | No sales: {total - updated - failed} | Failed: {failed}")


def daily_scrape(max_workers=3, user=None):
    """Scrape price data for one user or all users defined in users.yaml.

    Loads users.yaml to discover per-user data paths. If users.yaml is absent
    (legacy single-user mode), falls back to the global CSV_PATH and
    RESULTS_JSON_PATH constants. When a specific user is requested but not
    found in users.yaml, the process exits with a non-zero status.

    Args:
        max_workers: Number of parallel Chrome browser instances per user.
            Defaults to 3.
        user: Username to scrape exclusively, or None to scrape all users.
            Defaults to None.
    """
    users = load_users()

    if not users:
        # Legacy mode: no users.yaml, use global paths
        print("=== Daily scrape (legacy single-user mode) ===")
        daily_scrape_user(CSV_PATH, RESULTS_JSON_PATH,
                          os.path.join(SCRIPT_DIR, "price_history.json"),
                          os.path.join(SCRIPT_DIR, "backups"),
                          max_workers)
        return

    if user:
        # Scrape a single user
        if user not in users:
            print(f"Error: user '{user}' not found in users.yaml")
            sys.exit(1)
        targets = [user]
    else:
        # Scrape all users
        targets = list(users.keys())

    for username in targets:
        paths = get_user_paths(username)
        if not os.path.exists(paths['csv']):
            print(f"\n=== Skipping {username} (no data) ===")
            continue
        print(f"\n=== Scraping {username}'s collection ===")
        daily_scrape_user(paths['csv'], paths['results'], paths['history'],
                          paths['backup_dir'], max_workers)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Daily card price scraper")
    parser.add_argument('--workers', type=int, default=3, help="Parallel browser instances (default: 3)")
    parser.add_argument('--user', type=str, default=None, help="Scrape only this user (default: all users)")
    args = parser.parse_args()
    daily_scrape(max_workers=args.workers, user=args.user)
