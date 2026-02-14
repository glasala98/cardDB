import time
import random
import csv
import logging
import re
import urllib.parse
import statistics
import json
from datetime import datetime

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except ImportError:
    logging.info("Installing selenium...")
    import subprocess
    subprocess.check_call(['pip', 'install', 'selenium'])
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC


# --- Helper Functions ---

def is_graded_card(card_name):
    """Check if the card name indicates it's a graded card."""
    return bool(re.search(r'\bPSA\s+\d+', card_name, re.IGNORECASE))


def get_grade_info(card_name):
    """Extract grading details from card name. Returns (grade_str, grade_num) or (None, None)."""
    # Check for bracketed format first: [PSA 10]
    psa_match = re.search(r'\[PSA (\d+)', card_name, re.IGNORECASE)
    if psa_match:
        grade_num = int(psa_match.group(1))
        return f"PSA {grade_num}", grade_num
    # Also check for unbracketed format: PSA 10 (from manual entry)
    psa_match = re.search(r'\bPSA\s+(\d+)\b', card_name, re.IGNORECASE)
    if psa_match:
        grade_num = int(psa_match.group(1))
        return f"PSA {grade_num}", grade_num
    return None, None


def clean_card_name_for_search(card_name):
    """Build a focused eBay search query from card name components.

    Priority order: player name, card number, set/year.
    Keeps queries short so eBay finds more matches.
    """

    grade_str, grade_num = get_grade_info(card_name)

    # Work on a copy without grade/condition brackets
    clean = re.sub(r'\[PSA [^\]]*\]', '', card_name)
    clean = re.sub(r'\[Passed Pre[^\]]*\]', '', clean)
    clean = re.sub(r'\[Poor to Fair\]', '', clean)
    # Also strip unbracketed PSA grades (from manual entry)
    clean = re.sub(r'\bPSA\s+\d+\b', '', clean, flags=re.IGNORECASE)

    # Split on " - " to get the segments
    parts = [p.strip() for p in clean.split(' - ')]

    # --- Extract player name (last meaningful segment) - HIGHEST PRIORITY ---
    player = ""
    if parts:
        last = parts[-1]
        last = re.sub(r'#\d+/\d+', '', last).strip()
        last = re.sub(r'\(.*?\)', '', last).strip()
        if last and not last.startswith('['):
            player = last

    # --- Extract card number - HIGH PRIORITY ---
    card_num = ""
    num_match = re.search(r'#(\S+)', clean)
    if num_match:
        card_num_raw = num_match.group(1)
        if '/' not in card_num_raw:
            card_num = '#' + card_num_raw

    # --- Extract year ---
    year = ""
    year_match = re.search(r'(\d{4}(?:-\d{2})?)', parts[0] if parts else '')
    if year_match:
        year = year_match.group(1)

    # --- Extract short brand/set name ---
    # Shorten verbose brand names for better eBay matching
    brand = parts[0] if parts else ""
    brand = re.sub(r'^\d{4}(?:-\d{2})?\s*', '', brand).strip()
    # Common abbreviations sellers use
    brand_map = {
        'O-Pee-Chee Platinum': 'OPC Platinum',
        'O-Pee-Chee': 'OPC',
        'Upper Deck Extended Series': 'UD Extended',
        'Upper Deck Series 1': 'Upper Deck Series 1',
        'Upper Deck Series 2': 'Upper Deck Series 2',
        'Upper Deck UD Rookie Debut': 'UD Rookie Debut',
    }
    for full, short in brand_map.items():
        if brand == full:
            brand = short
            break

    # --- Extract variant/parallel that affects value ---
    variant = ""
    for part in parts[1:]:
        part_clean = re.sub(r'\[Base\]', '', part).strip()
        part_clean = re.sub(r'#\S+', '', part_clean).strip()
        if part_clean.lower() in ['', 'rookies', 'marquee rookies']:
            continue
        # Keep value-relevant variants
        for v in ['Red Prism', 'Arctic Freeze', 'Violet Pixels', 'Emerald Surge',
                   'Seismic Gold', 'Rainbow', 'Pond Hockey', 'NHL Shield',
                   'Outburst', 'Silver Foil', 'Deluxe', 'Exclusives',
                   'Blue Foil', 'Photo Variation', 'Photo Driven',
                   'Color Flow', 'Orange Yellow Spectrum', 'Blue Luster',
                   'Gold', 'Purple Parallax', 'Hypnosis']:
            if v.lower() in part_clean.lower():
                variant = v
                break
        if variant:
            break

    # --- Extract subset that matters ---
    subset = ""
    for kw in ['Young Guns', 'UD Canvas', 'Prominent Prospects', 'Young Guns Renewed',
               'Young Guns Checklist', 'Dazzlers', 'Day with the Cup',
               'Bootlegs', 'Holoview', 'Finite Rookies', 'Rookie Autographs',
               'UD Portraits', 'Auto Patch', 'Auto Jersey', 'Signature Fabrics',
               'License to Ice', 'GR8 Moments', 'Cranked Up']:
        if kw.lower() in clean.lower():
            subset = kw
            break

    # --- Build search query: player + card# + variant + set + year ---
    query_parts = []

    # Player name is the anchor - always first
    if player:
        query_parts.append(player)

    # Card number narrows it down precisely
    if card_num:
        query_parts.append(card_num)

    # Variant is critical for parallels (Red Prism vs base are very different values)
    if variant:
        query_parts.append(variant)

    # Subset matters (Young Guns vs base)
    if subset and subset.lower() not in (variant or '').lower():
        query_parts.append(subset)

    # Year + short brand for context
    if year:
        query_parts.append(year)
    if brand:
        query_parts.append(brand)

    search_term = ' '.join(query_parts)
    search_term = ' '.join(search_term.split())

    # Add grade filtering
    if grade_str:
        search_term = f"{search_term} \"{grade_str}\""
        other_grades = [g for g in range(1, 11) if g != grade_num]
        for g in other_grades:
            search_term += f" -\"PSA {g} \""
    else:
        search_term = f"{search_term} -PSA -BGS -SGC -graded"

    return search_term.strip()


def title_matches_grade(title, grade_str, grade_num):
    """Check that a listing title matches the expected grade exactly."""
    title_upper = title.upper()

    if grade_str:
        # Graded card - title must mention the exact grade
        # Check for "PSA 10" but NOT "PSA 10" matching inside "PSA 100" etc.
        pattern = rf'PSA\s*{grade_num}(?:\s|$|[^0-9])'
        if not re.search(pattern, title_upper):
            return False
        # Also reject if title mentions a different PSA grade
        other_psa = re.findall(r'PSA\s*(\d+)', title_upper)
        for g in other_psa:
            if int(g) != grade_num:
                return False
        return True
    else:
        # Raw card - reject if title mentions any grading service
        if re.search(r'\bPSA\b|\bBGS\b|\bSGC\b|\bGRADED\b', title_upper):
            return False
        return True


def build_simplified_query(card_name):
    """Build a simpler fallback query: just player + card number + year."""
    grade_str, grade_num = get_grade_info(card_name)

    clean = re.sub(r'\[.*?\]', '', card_name)
    clean = re.sub(r'\bPSA\s+\d+\b', '', clean, flags=re.IGNORECASE)
    parts = [p.strip() for p in clean.split(' - ')]

    # Year
    year = ""
    year_match = re.search(r'(\d{4}(?:-\d{2})?)', parts[0] if parts else '')
    if year_match:
        year = year_match.group(1)

    # Card number
    card_num = ""
    num_match = re.search(r'#(\S+)', clean)
    if num_match:
        raw = num_match.group(1)
        if '/' not in raw:
            card_num = '#' + raw

    # Player (last segment)
    player = ""
    if parts:
        last = parts[-1]
        last = re.sub(r'#\d+/\d+', '', last).strip()
        last = re.sub(r'\(.*?\)', '', last).strip()
        if last:
            player = last

    # Player + card# + year only - minimal query
    query_parts = [p for p in [player, card_num, year] if p]
    search_term = ' '.join(query_parts)

    if grade_str:
        search_term = f"{search_term} \"{grade_str}\""
    else:
        search_term = f"{search_term} -PSA -BGS -SGC -graded"

    return search_term.strip()


def calculate_fair_price(sales):
    """Pick the most representative price from the 3 most recent sales, considering trend."""

    if not sales:
        return None, {}

    all_prices = [s['price_val'] for s in sales]

    # --- Light outlier removal ---
    # Drop sales that are wildly off from the median (>3x or <1/3 of median)
    # This catches $0.99 "pick from list" auctions and lot sales
    median_price = statistics.median(all_prices)
    if median_price > 0 and len(sales) >= 3:
        lower_cutoff = median_price / 3
        upper_cutoff = median_price * 3
        filtered_sales = [s for s in sales if lower_cutoff <= s['price_val'] <= upper_cutoff]
        outliers_removed = len(sales) - len(filtered_sales)
        # Fall back to all sales if filtering removed everything
        if not filtered_sales:
            filtered_sales = sales
            outliers_removed = 0
    else:
        filtered_sales = sales
        outliers_removed = 0

    all_prices = [s['price_val'] for s in filtered_sales]

    # Sort by date (most recent first) - sales with dates first, then undated
    dated_sales = [s for s in filtered_sales if s['days_ago'] is not None]
    undated_sales = [s for s in filtered_sales if s['days_ago'] is None]
    sorted_sales = sorted(dated_sales, key=lambda s: s['days_ago']) + undated_sales

    # Get the 3 most recent sales
    top3 = sorted_sales[:3]

    if len(top3) == 1:
        chosen = top3[0]
        trend = 'insufficient data'
    else:
        # Determine trend from all sales data
        # Compare average of the older half vs newer half
        if len(sorted_sales) >= 4:
            mid = len(sorted_sales) // 2
            recent_half = sorted_sales[:mid]
            older_half = sorted_sales[mid:]
            recent_avg = statistics.mean([s['price_val'] for s in recent_half])
            older_avg = statistics.mean([s['price_val'] for s in older_half])

            pct_change = ((recent_avg - older_avg) / older_avg) * 100 if older_avg > 0 else 0

            if pct_change > 10:
                trend = 'up'
            elif pct_change < -10:
                trend = 'down'
            else:
                trend = 'stable'
        else:
            # With few sales, just compare most recent to oldest
            if sorted_sales[0]['price_val'] > sorted_sales[-1]['price_val'] * 1.1:
                trend = 'up'
            elif sorted_sales[0]['price_val'] < sorted_sales[-1]['price_val'] * 0.9:
                trend = 'down'
            else:
                trend = 'stable'

        # Pick the best representative from the top 3
        top3_sorted_by_price = sorted(top3, key=lambda s: s['price_val'])

        if trend == 'up':
            # Trending up - pick the highest of the 3 (favor current market)
            chosen = top3_sorted_by_price[-1]
        elif trend == 'down':
            # Trending down - pick the lowest of the 3 (favor current market)
            chosen = top3_sorted_by_price[0]
        else:
            # Stable - pick the middle value
            chosen = top3_sorted_by_price[len(top3_sorted_by_price) // 2]

    fair_price = round(chosen['price_val'], 2)

    stats = {
        'fair_price': fair_price,
        'chosen_sale': chosen['title'][:80],
        'chosen_date': chosen.get('sold_date', 'unknown'),
        'trend': trend,
        'top_3_prices': [f"${s['price_val']}" for s in top3],
        'median_all': round(statistics.median(all_prices), 2),
        'num_sales': len(filtered_sales),
        'outliers_removed': outliers_removed,
        'min': round(min(all_prices), 2),
        'max': round(max(all_prices), 2),
    }

    return fair_price, stats


class CardScraper:
    def __init__(self, headless=True):
        self.driver = self._setup_driver(headless)
        self.default_price = 5.00

    def _setup_driver(self, headless):
        """Sets up Chrome driver with stealth options."""
        options = Options()
        if headless:
            options.add_argument("--headless=new")

        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--disable-extensions')
        options.add_argument('--ignore-certificate-errors')
        options.add_argument('--allow-running-insecure-content')

        # Anti-detection: Disable automation flags
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)

        # Randomize User-Agent (In prod, rotate this list)
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        ]
        options.add_argument(f"user-agent={random.choice(user_agents)}")

        driver = webdriver.Chrome(options=options)

        # Obfuscate navigator.webdriver
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        return driver

    def random_sleep(self, min_s=0.5, max_s=1.5):
        """Human-like delay."""
        time.sleep(random.uniform(min_s, max_s))

    def quit(self):
        if self.driver:
            self.driver.quit()

    def search_ebay_sold(self, card_name, max_results=50):
        """Search eBay sold listings for a card and return recent sale prices with dates."""

        search_query = clean_card_name_for_search(card_name)
        grade_str, grade_num = get_grade_info(card_name)
        encoded_query = urllib.parse.quote(search_query)

        # eBay sold listings URL, sorted by most recent
        url = f"https://www.ebay.com/sch/i.html?_nkw={encoded_query}&_sacat=0&LH_Complete=1&LH_Sold=1&_sop=13&_ipg=240"

        try:
            self.driver.get(url)

            # Wait for card-based results to load
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '.s-card'))
                )
            except Exception:
                # If wait times out, return empty list (no results loaded)
                return []

            sales = []
            items = self.driver.find_elements(By.CSS_SELECTOR, '.s-card')

            for item in items:
                try:
                    title_elem = item.find_element(By.CSS_SELECTOR, '.s-card__title')
                    title = title_elem.text.strip()

                    # Skip empty placeholders
                    if not title:
                        continue

                    # Filter: must match the exact grade (or be raw if ungraded)
                    if not title_matches_grade(title, grade_str, grade_num):
                        continue

                    # Get listing URL — use the title's parent anchor (s-card__link)
                    listing_url = ''
                    try:
                        link_elem = title_elem.find_element(By.XPATH, './ancestor::a[@class="s-card__link"]')
                        listing_url = link_elem.get_attribute('href') or ''
                    except Exception:
                        try:
                            link_elem = item.find_element(By.CSS_SELECTOR, 'a.s-card__link[href*="/itm/"]')
                            listing_url = link_elem.get_attribute('href') or ''
                        except Exception:
                            pass
                    # Strip params that cause eBay to redirect to product catalog page
                    if listing_url:
                        for param in ['epid', 'itmprp', '_skw']:
                            listing_url = re.sub(rf'[&?]{param}=[^&]*', '', listing_url)

                    price_elem = item.find_element(By.CSS_SELECTOR, '.s-card__price')
                    price_text = price_elem.text.strip()

                    # Clean price - keep just the dollar amount
                    price_text = price_text.replace('Opens in a new window', '').strip()
                    price_match = re.search(r'\$([\d,]+\.?\d*)', price_text)
                    if not price_match:
                        continue

                    price_str = price_match.group(0)
                    price_val = float(price_match.group(1).replace(',', ''))

                    # Get shipping cost and add to total
                    shipping_val = 0.0
                    try:
                        shipping_elems = item.find_elements(By.XPATH,
                            './/*[contains(text(),"delivery") or contains(text(),"shipping")]')
                        for se in shipping_elems:
                            se_text = se.text.strip().lower()
                            if 'free' in se_text:
                                shipping_val = 0.0
                                break
                            ship_match = re.search(r'\$([\d,]+\.?\d*)', se_text)
                            if ship_match:
                                shipping_val = float(ship_match.group(1).replace(',', ''))
                                break
                    except Exception:
                        pass

                    total_val = round(price_val + shipping_val, 2)

                    # Get sold date from caption
                    sold_date = None
                    try:
                        caption = item.find_element(By.CSS_SELECTOR, '.s-card__caption')
                        caption_text = caption.text.strip()
                        date_match = re.search(r'Sold\s+(\w+\s+\d+,?\s*\d*)', caption_text)
                        if date_match:
                            date_str = date_match.group(1)
                            # Try parsing with year
                            try:
                                sold_date = datetime.strptime(date_str, '%b %d, %Y')
                            except ValueError:
                                # If no year, assume current year
                                try:
                                    sold_date = datetime.strptime(date_str + f', {datetime.now().year}', '%b %d, %Y')
                                except ValueError:
                                    pass
                    except Exception:
                        pass

                    sales.append({
                        'title': title,
                        'item_price': price_str,
                        'shipping': f"${shipping_val}" if shipping_val > 0 else 'Free',
                        'price_val': total_val,  # item + shipping
                        'sold_date': sold_date.strftime('%Y-%m-%d') if sold_date else None,
                        'days_ago': (datetime.now() - sold_date).days if sold_date else None,
                        'listing_url': listing_url,
                        'search_url': url
                    })

                    if len(sales) >= max_results:
                        break
                except Exception:
                    continue

            return sales

        except Exception as e:
            logging.error(f"Error fetching data: {e}")
            return []

    def scrape_card(self, card_name, max_results=50):
        """Search and price a single card. Retries with simplified query if needed."""
        self.random_sleep()

        sales = self.search_ebay_sold(card_name, max_results=max_results)

        # Retry with simplified query if no results
        if not sales:
            self.random_sleep(0.5, 1.0)
            simplified = build_simplified_query(card_name)
            grade_str, grade_num = get_grade_info(card_name)
            encoded = urllib.parse.quote(simplified)
            url = f"https://www.ebay.com/sch/i.html?_nkw={encoded}&_sacat=0&LH_Complete=1&LH_Sold=1&_sop=13&_ipg=240"

            try:
                self.driver.get(url)
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '.s-card'))
                )
                items = self.driver.find_elements(By.CSS_SELECTOR, '.s-card')
                for item in items:
                    try:
                        title_elem = item.find_element(By.CSS_SELECTOR, '.s-card__title')
                        title = title_elem.text.strip()
                        if not title:
                            continue
                        if not title_matches_grade(title, grade_str, grade_num):
                            continue

                        listing_url = ''
                        try:
                            link_elem = title_elem.find_element(By.XPATH, './ancestor::a[@class="s-card__link"]')
                            listing_url = link_elem.get_attribute('href') or ''
                        except Exception:
                            try:
                                link_elem = item.find_element(By.CSS_SELECTOR, 'a.s-card__link[href*="/itm/"]')
                                listing_url = link_elem.get_attribute('href') or ''
                            except Exception:
                                pass
                        if listing_url:
                            for param in ['epid', 'itmprp', '_skw']:
                                listing_url = re.sub(rf'[&?]{param}=[^&]*', '', listing_url)

                        price_elem = item.find_element(By.CSS_SELECTOR, '.s-card__price')
                        price_text = price_elem.text.strip().replace('Opens in a new window', '')
                        price_match = re.search(r'\$([\d,]+\.?\d*)', price_text)
                        if not price_match:
                            continue

                        price_val = float(price_match.group(1).replace(',', ''))
                        shipping_val = 0.0
                        try:
                            ship_elems = item.find_elements(By.XPATH,
                                './/*[contains(text(),"delivery") or contains(text(),"shipping")]')
                            for se in ship_elems:
                                se_text = se.text.strip().lower()
                                if 'free' in se_text:
                                    break
                                sm = re.search(r'\$([\d,]+\.?\d*)', se_text)
                                if sm:
                                    shipping_val = float(sm.group(1).replace(',', ''))
                                    break
                        except Exception:
                            pass

                        sold_date = None
                        try:
                            caption = item.find_element(By.CSS_SELECTOR, '.s-card__caption')
                            dm = re.search(r'Sold\s+(\w+\s+\d+,?\s*\d*)', caption.text.strip())
                            if dm:
                                try:
                                    sold_date = datetime.strptime(dm.group(1), '%b %d, %Y')
                                except ValueError:
                                    try:
                                        sold_date = datetime.strptime(dm.group(1) + f', {datetime.now().year}', '%b %d, %Y')
                                    except ValueError:
                                        pass
                        except Exception:
                            pass

                        sales.append({
                            'title': title,
                            'item_price': price_match.group(0),
                            'shipping': f"${shipping_val}" if shipping_val > 0 else 'Free',
                            'price_val': round(price_val + shipping_val, 2),
                            'sold_date': sold_date.strftime('%Y-%m-%d') if sold_date else None,
                            'days_ago': (datetime.now() - sold_date).days if sold_date else None,
                            'listing_url': listing_url,
                            'search_url': url
                        })
                        if len(sales) >= 50:
                            break
                    except Exception:
                        continue
            except Exception:
                pass

        if sales:
            fair_price, stats = calculate_fair_price(sales)
            return card_name, {
                'estimated_value': f"${fair_price}",
                'stats': stats,
                'raw_sales': sales,
                'search_url': sales[0]['search_url']
            }
        else:
            # Default to default_price if no sales found anywhere
            return card_name, {
                'estimated_value': f"${self.default_price}",
                'stats': {
                    'fair_price': self.default_price,
                    'chosen_sale': 'No sales found - default estimate',
                    'chosen_date': 'N/A',
                    'trend': 'unknown',
                    'top_3_prices': [],
                    'median_all': self.default_price,
                    'num_sales': 0,
                    'outliers_removed': 0,
                    'min': self.default_price,
                    'max': self.default_price,
                },
                'raw_sales': [],
                'search_url': None
            }

if __name__ == "__main__":
    scraper = CardScraper(headless=True)
    name, result = scraper.scrape_card("Connor McDavid Young Guns")
    print(json.dumps(result, indent=2))
    scraper.quit()
