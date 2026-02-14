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
    load_data, save_data, backup_data, append_price_history,
    get_user_paths, load_users,
    CSV_PATH, RESULTS_JSON_PATH
)


def daily_scrape_user(csv_path, results_path, history_path, backup_dir, max_workers=3):
    """Scrape all cards for a single user's data paths."""
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

                # Update results JSON (merge, don't replace entire file)
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

    elapsed = (datetime.now() - start).total_seconds()
    print(f"Scrape complete in {elapsed:.0f}s")
    print(f"  Updated: {updated} | No sales: {total - updated - failed} | Failed: {failed}")


def daily_scrape(max_workers=3, user=None):
    """Main entry point. Scrapes one user or all users."""
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
