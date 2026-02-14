#!/usr/bin/env python3
"""Daily scrape job — rescrapes all cards in the existing database,
updates prices, and appends fair-value deltas to price_history.json.

Usage:
    python daily_scrape.py          # scrape all cards
    python daily_scrape.py --workers 3   # limit parallel browsers

Set up as a cron job on the server:
    0 6 * * * cd /opt/card-dashboard && /usr/bin/python3 daily_scrape.py >> /var/log/daily_scrape.log 2>&1
"""

import os
import sys
import csv
import json
import argparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

from scrape_card_prices import process_card
from dashboard_utils import (
    load_data, save_data, backup_data, append_price_history,
    CSV_PATH, RESULTS_JSON_PATH
)


def daily_scrape(max_workers=3):
    start = datetime.now()
    print(f"[{start.strftime('%Y-%m-%d %H:%M:%S')}] Daily scrape starting")

    # Backup before scraping
    ts = backup_data(label="daily")
    print(f"Backup saved: {ts}")

    # Load current card list from the summary CSV
    df = load_data()
    card_names = df['Card Name'].tolist()
    print(f"Scraping {len(card_names)} cards with {max_workers} workers")

    # Load existing results JSON to merge into
    results = {}
    if os.path.exists(RESULTS_JSON_PATH):
        try:
            with open(RESULTS_JSON_PATH, 'r', encoding='utf-8') as f:
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
                        append_price_history(card_name, fair_price, num_sales)
                        updated += 1

                    status = f"${fair_price:.2f} ({num_sales} sales)" if num_sales > 0 else "no sales"
                    print(f"  [{completed}/{total}] {card_name[:60]}... {status}")

            except Exception as e:
                failed += 1
                print(f"  [{completed}/{total}] {card[:60]}... ERROR: {e}")

    # Save updated CSV
    save_data(df)

    # Save updated results JSON
    with open(RESULTS_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    elapsed = (datetime.now() - start).total_seconds()
    print(f"\nDaily scrape complete in {elapsed:.0f}s")
    print(f"  Updated: {updated} | No sales: {total - updated - failed} | Failed: {failed}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Daily card price scraper")
    parser.add_argument('--workers', type=int, default=3, help="Parallel browser instances (default: 3)")
    args = parser.parse_args()
    daily_scrape(max_workers=args.workers)
