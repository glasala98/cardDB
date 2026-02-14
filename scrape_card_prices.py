import csv
import json
import time
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# Import from the new module
from card_scraper import (
    CardScraper,
    is_graded_card,
    get_grade_info,
    clean_card_name_for_search,
    title_matches_grade,
    build_simplified_query,
    calculate_fair_price
)

NUM_WORKERS = 10  # Number of parallel Chrome instances
DEFAULT_PRICE = 5.00

# Thread-local storage for Scraper instances
_thread_local = threading.local()


def get_scraper():
    """Get or create a CardScraper instance for the current thread."""
    if not hasattr(_thread_local, 'scraper'):
        _thread_local.scraper = CardScraper(headless=True)
    return _thread_local.scraper


def process_card(card):
    """Search and price a single card using the thread-local scraper."""
    scraper = get_scraper()

    # Small random delay to stagger requests across workers
    # (CardScraper also has random_sleep but this is extra safety for parallel starts)
    time.sleep(random.uniform(0.5, 1.5))

    return scraper.scrape_card(card)


# Exported for backward compatibility if needed, though mostly unused now
def create_driver():
    """Create a headless Chrome driver (Wrapper for CardScraper)."""
    # Note: This creates a scraper and returns its driver.
    # The scraper instance might be GC'd but the driver object persists?
    # Actually Selenium driver .quit() must be called.
    # This is risky. Better to warn or use CardScraper directly.
    # But for dashboard_utils.py legacy support (until updated):
    scraper = CardScraper(headless=True)
    # We detach the driver from the scraper so scraper.__del__ (if existed) wouldn't kill it
    # But CardScraper doesn't have __del__.
    return scraper.driver


def search_ebay_sold(driver, card_name, max_results=50):
    """Legacy wrapper for search_ebay_sold."""
    # This is tricky because CardScraper methods use self.driver.
    # We can't easily use a passed-in driver with CardScraper methods.
    # If this is called, it's likely from code that hasn't been updated to use CardScraper.
    # We'll need to reimplement it using the passed driver or just fail.
    # Since I'm updating dashboard_utils.py, this might not be needed.
    # But for tests... tests pass a driver mock usually?
    # Realistically, if I update dashboard_utils.py, I can remove this.
    # For now, I will leave a stub or simple implementation if needed, but
    # since I am updating all consumers, I will omit it to encourage using CardScraper.
    raise NotImplementedError("Use CardScraper class instead.")


def main():
    # Backup existing data before full scrape
    try:
        from dashboard_utils import backup_data
        ts = backup_data(label="full-scrape")
        print(f"Backup saved: {ts}")
    except Exception:
        pass

    # Read cards from CSV
    cards = []
    try:
        with open('hockey_cards.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                cards.append(row['card_name'])
    except FileNotFoundError:
        print("hockey_cards.csv not found.")
        return

    # Remove duplicates while preserving order
    unique_cards = list(dict.fromkeys(cards))

    print(f"Found {len(cards)} cards ({len(unique_cards)} unique)")
    print(f"Running {NUM_WORKERS} parallel Chrome instances")
    print("=" * 60)

    card_prices = {}
    completed = 0
    total = len(unique_cards)

    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
        futures = {executor.submit(process_card, card): card for card in unique_cards}

        for future in as_completed(futures):
            card = futures[future]
            completed += 1
            try:
                card_name, result = future.result()
                card_prices[card_name] = result

                stats = result.get('stats', {})
                if stats.get('num_sales', 0) > 0:
                    print(f"[{completed}/{total}] {card_name[:60]}...")
                    print(f"  Fair value: {result['estimated_value']} | "
                          f"Trend: {stats['trend']} | "
                          f"Top 3: {', '.join(stats['top_3_prices'])} | "
                          f"Range: ${stats['min']}-${stats['max']}")
                else:
                    print(f"[{completed}/{total}] {card_name[:60]}...")
                    print(f"  No sales found - defaulting to ${DEFAULT_PRICE}")
            except Exception as e:
                print(f"[{completed}/{total}] {card[:60]}... ERROR: {e}")
                card_prices[card] = {
                    'estimated_value': None,
                    'stats': {},
                    'raw_sales': [],
                    'search_url': None
                }

    # Save full results to JSON
    output_file = 'card_prices_results.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(card_prices, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 60}")
    print(f"Full results saved to {output_file}")

    # Create summary CSV
    csv_output = 'card_prices_summary.csv'
    with open(csv_output, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Card Name', 'Fair Value', 'Trend', 'Top 3 Prices',
                         'Median (All)', 'Min', 'Max', 'Num Sales'])
        for card, data in card_prices.items():
            stats = data.get('stats', {})
            writer.writerow([
                card,
                data.get('estimated_value', ''),
                stats.get('trend', ''),
                ' | '.join(stats.get('top_3_prices', [])),
                f"${stats['median_all']}" if stats.get('median_all') else '',
                f"${stats['min']}" if stats.get('min') else '',
                f"${stats['max']}" if stats.get('max') else '',
                stats.get('num_sales', 0),
            ])

    print(f"Summary saved to {csv_output}")

    # Print summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    cards_with_prices = sum(1 for d in card_prices.values() if d['estimated_value'])
    print(f"Cards with prices found: {cards_with_prices}/{len(unique_cards)}")

    total_value = sum(
        d['stats']['fair_price']
        for d in card_prices.values()
        if d.get('stats', {}).get('fair_price')
    )
    print(f"Total estimated collection value: ${total_value:.2f}")

    return card_prices


if __name__ == "__main__":
    main()
