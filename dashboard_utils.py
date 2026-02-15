import os
import base64
import json
import re
import shutil
from datetime import datetime
import urllib.parse
import pandas as pd
import yaml
try:
    import bcrypt
except ImportError:
    bcrypt = None
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Import scraper functions
try:
    from scrape_card_prices import (
        create_driver, search_ebay_sold, calculate_fair_price,
        build_simplified_query, get_grade_info, title_matches_grade
    )
except ImportError:
    pass

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_ROOT = os.path.join(SCRIPT_DIR, "data")
USERS_YAML = os.path.join(SCRIPT_DIR, "users.yaml")

# Legacy global paths (used by daily_scrape.py as defaults)
CSV_PATH = os.path.join(SCRIPT_DIR, "card_prices_summary.csv")
RESULTS_JSON_PATH = os.path.join(SCRIPT_DIR, "card_prices_results.json")
HISTORY_PATH = os.path.join(SCRIPT_DIR, "price_history.json")
BACKUP_DIR = os.path.join(SCRIPT_DIR, "backups")
ARCHIVE_PATH = os.path.join(SCRIPT_DIR, "card_archive.csv")
MONEY_COLS = ['Fair Value', 'Median (All)', 'Min', 'Max']

# Master DB paths (shared across all users)
MASTER_DB_DIR = os.path.join(SCRIPT_DIR, "data", "master_db")
MASTER_DB_PATH = os.path.join(MASTER_DB_DIR, "young_guns.csv")

# Empty CSV columns for new users
EMPTY_CSV_COLS = ['Card Name', 'Fair Value', 'Trend', 'Top 3 Prices', 'Median (All)', 'Min', 'Max', 'Num Sales', 'Tags']


# ── User management ──────────────────────────────────────────────

def get_user_paths(username):
    """Return file paths for a specific user's data directory."""
    user_dir = os.path.join(DATA_ROOT, username)
    os.makedirs(user_dir, exist_ok=True)
    os.makedirs(os.path.join(user_dir, "backups"), exist_ok=True)
    return {
        'csv': os.path.join(user_dir, "card_prices_summary.csv"),
        'results': os.path.join(user_dir, "card_prices_results.json"),
        'history': os.path.join(user_dir, "price_history.json"),
        'portfolio': os.path.join(user_dir, "portfolio_history.json"),
        'archive': os.path.join(user_dir, "card_archive.csv"),
        'backup_dir': os.path.join(user_dir, "backups"),
    }


def load_users():
    """Load user config from users.yaml."""
    if not os.path.exists(USERS_YAML):
        return {}
    with open(USERS_YAML, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f) or {}
    return config.get('users', {})


def verify_password(username, password):
    """Verify a username/password against users.yaml. Returns True if valid."""
    users = load_users()
    if username not in users:
        return False
    pw_hash = users[username].get('password_hash', '')
    try:
        return bcrypt.checkpw(password.encode('utf-8'), pw_hash.encode('utf-8'))
    except Exception:
        return False


def init_user_data(csv_path):
    """Create an empty CSV for a new user if it doesn't exist."""
    if not os.path.exists(csv_path):
        pd.DataFrame(columns=EMPTY_CSV_COLS).to_csv(csv_path, index=False)

def analyze_card_images(front_image_bytes, back_image_bytes=None):
    """Use Claude vision to extract card details from front/back photos."""
    if not HAS_ANTHROPIC:
        return None, "anthropic package not installed. Run: pip install anthropic"

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None, "ANTHROPIC_API_KEY not set. Add it to your environment."

    client = anthropic.Anthropic(api_key=api_key)

    def _detect_media_type(image_bytes):
        if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
            return "image/png"
        if image_bytes[:2] == b'\xff\xd8':
            return "image/jpeg"
        if image_bytes[:4] == b'RIFF' and image_bytes[8:12] == b'WEBP':
            return "image/webp"
        return "image/jpeg"

    content = []

    # Add front image
    front_b64 = base64.standard_b64encode(front_image_bytes).decode("utf-8")
    front_media = _detect_media_type(front_image_bytes)
    content.append({"type": "text", "text": "FRONT OF CARD:"})
    content.append({
        "type": "image",
        "source": {"type": "base64", "media_type": front_media, "data": front_b64}
    })

    # Add back image if provided
    if back_image_bytes:
        back_b64 = base64.standard_b64encode(back_image_bytes).decode("utf-8")
        back_media = _detect_media_type(back_image_bytes)
        content.append({"type": "text", "text": "BACK OF CARD:"})
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": back_media, "data": back_b64}
        })

    content.append({
        "type": "text",
        "text": """Analyze this hockey/sports card and extract the following details.
Look at BOTH the front and back of the card carefully.

The back typically has: card number, set name, year, manufacturer info.
The front typically has: player name, team, photo.

Return ONLY valid JSON with these exact keys:
{
    "player_name": "Full player name",
    "card_number": "Just the number (e.g. 201, not #201)",
    "card_set": "Set name with subset (e.g. Upper Deck Series 1 Young Guns)",
    "year": "Card year or season (e.g. 2023-24)",
    "variant": "Parallel or variant name if any, empty string if base card",
    "grade": "Grade if in a graded slab (e.g. PSA 10), empty string if raw",
    "confidence": "high, medium, or low",
    "is_sports_card": true,
    "validation_reason": "Explain why this is or isn't a valid sports card"
}

Be precise. If the image is not a sports card, set "is_sports_card" to false and explain why in "validation_reason".
If you can't determine a field, use your best guess based on card design, logos, and text visible."""
    })

    try:
        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=500,
            messages=[{"role": "user", "content": content}]
        )

        response_text = response.content[0].text.strip()
        # Extract JSON from response (handle markdown code blocks)
        json_match = re.search(r'\{[^{}]*\}', response_text, re.DOTALL)
        if json_match:
            card_info = json.loads(json_match.group())
            return card_info, None
        else:
            return None, f"Could not parse response: {response_text[:200]}"
    except Exception as e:
        return None, str(e)


def _merge_sales(new_sales, existing_sales, max_sales=100):
    """Merge new sales with existing, deduplicating by (sold_date, title). Cap at max_sales."""
    seen = set()
    merged = []
    for sale in new_sales + existing_sales:
        key = (sale.get('sold_date', ''), sale.get('title', ''))
        if key not in seen:
            seen.add(key)
            merged.append(sale)
    # Sort by date descending (newest first), undated last
    merged.sort(key=lambda s: s.get('sold_date') or '0000-00-00', reverse=True)
    return merged[:max_sales]


def scrape_single_card(card_name, results_json_path=None):
    """Scrape eBay for a single card and return result dict."""
    if results_json_path is None:
        results_json_path = RESULTS_JSON_PATH
    driver = create_driver()
    try:
        sales = search_ebay_sold(driver, card_name, max_results=50)

        # Retry with simplified query if no results
        if not sales:
            simplified = build_simplified_query(card_name)
            grade_str, grade_num = get_grade_info(card_name)
            encoded = urllib.parse.quote(simplified)
            url = f"https://www.ebay.com/sch/i.html?_nkw={encoded}&_sacat=0&LH_Complete=1&LH_Sold=1&_sop=13&_ipg=240"
            try:
                driver.get(url)
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '.s-card'))
                )
                items = driver.find_elements(By.CSS_SELECTOR, '.s-card')
                for item in items:
                    try:
                        title_elem = item.find_element(By.CSS_SELECTOR, '.s-card__title')
                        title = title_elem.text.strip()
                        if not title or not title_matches_grade(title, grade_str, grade_num):
                            continue
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
                            'search_url': url
                        })
                        if len(sales) >= 50:
                            break
                    except Exception:
                        continue
            except Exception:
                pass

        if sales:
            from scrape_card_prices import extract_serial_run
            target_serial = extract_serial_run(card_name)
            fair_price, stats = calculate_fair_price(sales, target_serial=target_serial)
            # Save raw sales to results JSON
            results = {}
            if os.path.exists(results_json_path):
                try:
                    with open(results_json_path, 'r', encoding='utf-8') as f:
                        results = json.load(f)
                except Exception:
                    results = {}
            # Merge new sales with existing ones (accumulate history)
            existing_sales = results.get(card_name, {}).get('raw_sales', [])
            merged = _merge_sales(sales, existing_sales)
            results[card_name] = {
                'raw_sales': merged,
                'fair_price': stats.get('fair_price'),
                'num_sales': stats.get('num_sales'),
                'scraped_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            with open(results_json_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            return stats
        return None
    finally:
        driver.quit()

def parse_card_name(card_name):
    """Parse a card name string into Player, Year, Set, Card #, Grade components."""
    result = {'Player': '', 'Year': '', 'Set': '', 'Subset': '', 'Card #': '', 'Serial': '', 'Grade': ''}

    if not card_name or not isinstance(card_name, str):
        return result

    # Extract serial number (e.g. #70/99, /250, #1/250)
    serial_match = re.search(r'#?(\d+)\s*/\s*(\d+)', card_name)
    if serial_match:
        result['Serial'] = f"{serial_match.group(1)}/{serial_match.group(2)}"

    # Extract grade (bracketed or unbracketed)
    grade_match = re.search(r'\[([^\]]*PSA[^\]]*)\]', card_name, re.IGNORECASE)
    if grade_match:
        result['Grade'] = grade_match.group(1).strip()
    else:
        grade_match = re.search(r'\b(PSA\s+\d+)\b', card_name, re.IGNORECASE)
        if grade_match:
            result['Grade'] = grade_match.group(1).strip()

    # Check if structured format (has " - " delimiters)
    if ' - ' in card_name:
        parts = [p.strip() for p in card_name.split(' - ')]

        # Year: from first segment
        year_match = re.search(r'(\d{4}(?:-\d{2,4})?)', parts[0])
        if year_match:
            result['Year'] = year_match.group(1)

        # Set: just the base set name (first segment)
        result['Set'] = ' '.join(parts[0].split()).strip()

        # Card #: find #NNN or #CU-SC pattern (not serial numbered #70/99)
        num_match = re.search(r'#([\w-]+)(?!\s*/)', card_name)
        if num_match:
            raw_num = num_match.group(1)
            # Skip serial numbers like 70/99, 1/250
            if not re.search(r'#' + re.escape(raw_num) + r'\s*/\s*\d+', card_name):
                result['Card #'] = raw_num

        # Separate middle segments into subset vs player.
        # A segment is "metadata" if it's just a card #, grade, or serial.
        # The last non-metadata middle segment is the Player; the rest are Subset.
        middle_parts = parts[1:]  # everything after Set
        cleaned_middle = []
        for part in middle_parts:
            clean = re.sub(r'\[.*?\]', '', part).strip()
            clean = re.sub(r'#\d+/\d+', '', clean).strip()
            clean = re.sub(r'\bPSA\s+\d+\b', '', clean, flags=re.IGNORECASE).strip()
            # Skip segments that are only a card number like "#12" or empty
            clean = re.sub(r'^#\S+$', '', clean).strip()
            if clean:
                cleaned_middle.append(clean)

        if cleaned_middle:
            result['Player'] = cleaned_middle[-1]
            result['Subset'] = ' '.join(cleaned_middle[:-1])
        else:
            result['Player'] = ''
    else:
        # Freeform format - put the whole name as Player, stripping grade and serial
        player = card_name
        player = re.sub(r'\[.*?\]', '', player).strip()
        player = re.sub(r'#?\d+\s*/\s*\d+', '', player).strip()
        player = re.sub(r'\bPSA\s+\d+\b', '', player, flags=re.IGNORECASE).strip()
        result['Player'] = player
        # Try to extract year
        year_match = re.search(r'(\d{4}(?:-\d{2,4})?)', card_name)
        if year_match:
            result['Year'] = year_match.group(1)

    return result


def load_data(csv_path=CSV_PATH, results_json_path=None):
    if results_json_path is None:
        results_json_path = RESULTS_JSON_PATH
    df = pd.read_csv(csv_path)
    for col in MONEY_COLS:
        df[col] = df[col].astype(str).str.replace('$', '', regex=False).str.replace(',', '', regex=False)
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    df['Num Sales'] = pd.to_numeric(df['Num Sales'], errors='coerce').fillna(0).astype(int)
    df['Trend'] = df['Trend'].replace({'insufficient data': 'no data', 'unknown': 'no data'})

    # Parse Card Name into display columns
    parse_cols = ['Player', 'Year', 'Set', 'Subset', 'Card #', 'Serial', 'Grade']
    if len(df) > 0:
        parsed = df['Card Name'].apply(parse_card_name).apply(pd.Series)
        for col in parse_cols:
            df[col] = parsed[col] if col in parsed.columns else ''
    else:
        for col in parse_cols:
            df[col] = pd.Series(dtype='object')

    # Add Last Scraped from results JSON
    if os.path.exists(results_json_path):
        try:
            with open(results_json_path, 'r', encoding='utf-8') as f:
                results = json.load(f)
            df['Last Scraped'] = df['Card Name'].apply(
                lambda name: results.get(name, {}).get('scraped_at', '')
            )
            df['Last Scraped'] = df['Last Scraped'].apply(
                lambda x: x.split(' ')[0] if isinstance(x, str) and x else ''
            )
        except Exception:
            df['Last Scraped'] = ''
    else:
        df['Last Scraped'] = ''

    # Ensure Tags column exists (backward compat for existing CSVs)
    if 'Tags' not in df.columns:
        df['Tags'] = ''
    df['Tags'] = df['Tags'].fillna('')

    return df

PARSED_COLS = ['Player', 'Year', 'Set', 'Subset', 'Card #', 'Serial', 'Grade', 'Last Scraped']

def save_data(df, csv_path=CSV_PATH):
    save_df = df.copy()
    # Drop display-only parsed columns before saving
    save_df = save_df.drop(columns=[c for c in PARSED_COLS if c in save_df.columns], errors='ignore')
    for col in MONEY_COLS:
        save_df[col] = save_df[col].apply(lambda x: f"${x:.2f}" if pd.notna(x) else "$0.00")
    save_df.to_csv(csv_path, index=False)


def backup_data(label="scrape", csv_path=None, results_path=None, backup_dir=None):
    """Save a timestamped backup of the CSV and results JSON to backups/."""
    csv_path = csv_path or CSV_PATH
    results_path = results_path or RESULTS_JSON_PATH
    backup_dir = backup_dir or BACKUP_DIR
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')

    if os.path.exists(csv_path):
        backup_csv = os.path.join(backup_dir, f"card_prices_summary_{timestamp}_{label}.csv")
        shutil.copy2(csv_path, backup_csv)

    if os.path.exists(results_path):
        backup_json = os.path.join(backup_dir, f"card_prices_results_{timestamp}_{label}.json")
        shutil.copy2(results_path, backup_json)

    return timestamp


def load_sales_history(card_name, results_json_path=None):
    """Load raw eBay sales for a card from card_prices_results.json."""
    results_json_path = results_json_path or RESULTS_JSON_PATH
    if not os.path.exists(results_json_path):
        return []
    try:
        with open(results_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        card_data = data.get(card_name, {})
        return card_data.get('raw_sales', [])
    except Exception:
        return []


def append_price_history(card_name, fair_value, num_sales, history_path=None):
    """Append a price snapshot to the history log."""
    history_path = history_path or HISTORY_PATH
    history = {}
    if os.path.exists(history_path):
        try:
            with open(history_path, 'r', encoding='utf-8') as f:
                history = json.load(f)
        except Exception:
            history = {}

    if card_name not in history:
        history[card_name] = []

    history[card_name].append({
        'date': datetime.now().strftime('%Y-%m-%d'),
        'fair_value': round(fair_value, 2),
        'num_sales': num_sales
    })

    with open(history_path, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def load_price_history(card_name, history_path=None):
    """Load fair value history for a card from price_history.json."""
    history_path = history_path or HISTORY_PATH
    if not os.path.exists(history_path):
        return []
    try:
        with open(history_path, 'r', encoding='utf-8') as f:
            history = json.load(f)
        return history.get(card_name, [])
    except Exception:
        return []


def append_portfolio_snapshot(total_value, total_cards, avg_value, portfolio_path=None):
    """Append a daily portfolio value snapshot. Deduplicates by date."""
    portfolio_path = portfolio_path or os.path.join(SCRIPT_DIR, "portfolio_history.json")
    snapshots = []
    if os.path.exists(portfolio_path):
        try:
            with open(portfolio_path, 'r', encoding='utf-8') as f:
                snapshots = json.load(f)
        except Exception:
            snapshots = []

    today = datetime.now().strftime('%Y-%m-%d')
    snapshots = [s for s in snapshots if s['date'] != today]
    snapshots.append({
        'date': today,
        'total_value': round(total_value, 2),
        'total_cards': total_cards,
        'avg_value': round(avg_value, 2),
    })

    with open(portfolio_path, 'w', encoding='utf-8') as f:
        json.dump(snapshots, f, indent=2, ensure_ascii=False)


def load_portfolio_history(portfolio_path=None):
    """Load portfolio snapshots list."""
    portfolio_path = portfolio_path or os.path.join(SCRIPT_DIR, "portfolio_history.json")
    if not os.path.exists(portfolio_path):
        return []
    try:
        with open(portfolio_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def scrape_graded_comparison(card_name):
    """Scrape raw and graded (PSA 9, PSA 10) prices for ROI comparison."""
    import time as _time
    import random as _random

    # Strip any existing grade from the card name
    raw_name = re.sub(r'\s*-?\s*\[PSA\s+\d+\]', '', card_name).strip()
    raw_name = re.sub(r'\s*-?\s*\bPSA\s+\d+\b', '', raw_name, flags=re.IGNORECASE).strip()
    raw_name = raw_name.rstrip(' -').strip()

    driver = create_driver()
    try:
        results = {}
        for label, search_name in [
            ('raw', raw_name),
            ('psa_9', f"{raw_name} PSA 9"),
            ('psa_10', f"{raw_name} PSA 10"),
        ]:
            sales = search_ebay_sold(driver, search_name, max_results=30)
            if sales:
                fair_price, stats = calculate_fair_price(sales)
                results[label] = {
                    'fair_price': stats.get('fair_price', 0),
                    'num_sales': stats.get('num_sales', 0),
                    'min': stats.get('min', 0),
                    'max': stats.get('max', 0),
                }
            else:
                results[label] = None
            _time.sleep(_random.uniform(1.0, 2.0))
        return results
    finally:
        driver.quit()


def archive_card(df, card_name, archive_path=None):
    """Move a card from the main CSV to the archive CSV. Returns updated df."""
    archive_path = archive_path or ARCHIVE_PATH
    card_rows = df[df['Card Name'] == card_name]
    if len(card_rows) == 0:
        return df

    archive_row = card_rows.copy()
    archive_row = archive_row.drop(columns=[c for c in PARSED_COLS if c in archive_row.columns], errors='ignore')
    archive_row['Archived Date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    for col in MONEY_COLS:
        archive_row[col] = archive_row[col].apply(lambda x: f"${x:.2f}" if pd.notna(x) else "$0.00")

    if os.path.exists(archive_path):
        archive_row.to_csv(archive_path, mode='a', header=False, index=False)
    else:
        archive_row.to_csv(archive_path, index=False)

    df = df[df['Card Name'] != card_name].reset_index(drop=True)
    return df


def load_archive(archive_path=None):
    """Load archived cards."""
    archive_path = archive_path or ARCHIVE_PATH
    if not os.path.exists(archive_path):
        return pd.DataFrame()
    try:
        archive_df = pd.read_csv(archive_path)
        for col in MONEY_COLS:
            if col in archive_df.columns:
                archive_df[col] = archive_df[col].astype(str).str.replace('$', '', regex=False).str.replace(',', '', regex=False)
                archive_df[col] = pd.to_numeric(archive_df[col], errors='coerce').fillna(0)
        return archive_df
    except Exception:
        return pd.DataFrame()


def restore_card(card_name, archive_path=None):
    """Remove a card from the archive and return its row data for re-adding."""
    archive_path = archive_path or ARCHIVE_PATH
    if not os.path.exists(archive_path):
        return None
    try:
        archive_df = pd.read_csv(archive_path)
        card_rows = archive_df[archive_df['Card Name'] == card_name]
        if len(card_rows) == 0:
            return None
        archive_df = archive_df[archive_df['Card Name'] != card_name]
        if len(archive_df) > 0:
            archive_df.to_csv(archive_path, index=False)
        else:
            os.remove(archive_path)
        return card_rows.iloc[0].to_dict()
    except Exception:
        return None


# ── Master DB ───────────────────────────────────────────────────

YG_PRICE_HISTORY_PATH = os.path.join(MASTER_DB_DIR, "yg_price_history.json")
YG_PORTFOLIO_HISTORY_PATH = os.path.join(MASTER_DB_DIR, "yg_portfolio_history.json")
YG_RAW_SALES_PATH = os.path.join(MASTER_DB_DIR, "yg_raw_sales.json")


def append_yg_price_history(card_name, fair_value, num_sales, history_path=None,
                            graded_prices=None):
    """Append a price snapshot for a Young Guns card to the YG history log.

    Args:
        card_name: Card identifier
        fair_value: Raw/ungraded fair value
        num_sales: Number of raw sales found
        history_path: Override path for history JSON
        graded_prices: Optional dict of graded price data, e.g.
            {'PSA 10': {'fair_value': 150.0, 'num_sales': 5}, 'BGS 9.5': {...}}
    """
    history_path = history_path or YG_PRICE_HISTORY_PATH
    os.makedirs(os.path.dirname(history_path), exist_ok=True)
    history = {}
    if os.path.exists(history_path):
        try:
            with open(history_path, 'r', encoding='utf-8') as f:
                history = json.load(f)
        except Exception:
            history = {}

    if card_name not in history:
        history[card_name] = []

    today = datetime.now().strftime('%Y-%m-%d')
    # Deduplicate: replace today's entry if it exists
    existing = [h for h in history[card_name] if h.get('date') == today]
    history[card_name] = [h for h in history[card_name] if h.get('date') != today]

    entry = {
        'date': today,
        'fair_value': round(fair_value, 2),
        'num_sales': num_sales,
    }

    # Merge graded prices: if we have existing graded data from today, keep it
    if existing and existing[0].get('graded') and not graded_prices:
        entry['graded'] = existing[0]['graded']
    elif graded_prices:
        # Merge with any existing graded data from today
        merged_graded = existing[0].get('graded', {}) if existing else {}
        merged_graded.update(graded_prices)
        entry['graded'] = merged_graded

    history[card_name].append(entry)

    with open(history_path, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def load_yg_price_history(card_name=None, history_path=None):
    """Load YG price history. If card_name given, return that card's list.
    If None, return entire dict."""
    history_path = history_path or YG_PRICE_HISTORY_PATH
    if not os.path.exists(history_path):
        return [] if card_name else {}
    try:
        with open(history_path, 'r', encoding='utf-8') as f:
            history = json.load(f)
        if card_name:
            return history.get(card_name, [])
        return history
    except Exception:
        return [] if card_name else {}


def append_yg_portfolio_snapshot(total_value, total_cards, avg_value, cards_scraped,
                                 portfolio_path=None):
    """Append a daily YG market snapshot. Deduplicates by date."""
    portfolio_path = portfolio_path or YG_PORTFOLIO_HISTORY_PATH
    os.makedirs(os.path.dirname(portfolio_path), exist_ok=True)
    snapshots = []
    if os.path.exists(portfolio_path):
        try:
            with open(portfolio_path, 'r', encoding='utf-8') as f:
                snapshots = json.load(f)
        except Exception:
            snapshots = []

    today = datetime.now().strftime('%Y-%m-%d')
    snapshots = [s for s in snapshots if s['date'] != today]
    snapshots.append({
        'date': today,
        'total_value': round(total_value, 2),
        'total_cards': total_cards,
        'avg_value': round(avg_value, 2),
        'cards_scraped': cards_scraped,
    })

    with open(portfolio_path, 'w', encoding='utf-8') as f:
        json.dump(snapshots, f, indent=2, ensure_ascii=False)


def load_yg_portfolio_history(portfolio_path=None):
    """Load YG market snapshots list."""
    portfolio_path = portfolio_path or YG_PORTFOLIO_HISTORY_PATH
    if not os.path.exists(portfolio_path):
        return []
    try:
        with open(portfolio_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def save_yg_raw_sales(card_name, sales, path=None):
    """Save raw eBay sales for a card, merging with existing data.
    Deduplicates by (sold_date, title). Caps at 50 sales per card."""
    path = path or YG_RAW_SALES_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {}
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = {}

    # Filter to sales with valid sold_date and price
    new_sales = [
        {'sold_date': s['sold_date'], 'price_val': s['price_val'], 'title': s.get('title', '')}
        for s in sales
        if s.get('sold_date') and s.get('price_val')
    ]

    existing = data.get(card_name, [])
    # Merge: use (sold_date, title) as dedup key
    seen = {(s['sold_date'], s['title']) for s in existing}
    for s in new_sales:
        key = (s['sold_date'], s['title'])
        if key not in seen:
            existing.append(s)
            seen.add(key)

    # Cap at 50 most recent
    existing.sort(key=lambda x: x['sold_date'], reverse=True)
    data[card_name] = existing[:50]

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_yg_raw_sales(card_name=None, path=None):
    """Load raw sales. If card_name given, return that card's list. Otherwise return all."""
    path = path or YG_RAW_SALES_PATH
    if not os.path.exists(path):
        return [] if card_name else {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if card_name:
            return data.get(card_name, [])
        return data
    except Exception:
        return [] if card_name else {}


def batch_save_yg_raw_sales(all_sales_dict, path=None):
    """Batch-save raw sales for multiple cards in a single file write.
    Args:
        all_sales_dict: {card_name: [sales_list]} to merge
    """
    path = path or YG_RAW_SALES_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {}
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = {}

    for card_name, sales in all_sales_dict.items():
        new_sales = [
            {'sold_date': s['sold_date'], 'price_val': s['price_val'], 'title': s.get('title', '')}
            for s in sales
            if s.get('sold_date') and s.get('price_val')
        ]
        existing = data.get(card_name, [])
        seen = {(s['sold_date'], s['title']) for s in existing}
        for s in new_sales:
            key = (s['sold_date'], s['title'])
            if key not in seen:
                existing.append(s)
                seen.add(key)
        existing.sort(key=lambda x: x['sold_date'], reverse=True)
        data[card_name] = existing[:50]

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def batch_append_yg_price_history(updates, path=None):
    """Batch-append price history for multiple cards in a single file write.
    Args:
        updates: {card_name: {'fair_value': float, 'num_sales': int, 'graded_prices': dict|None}}
    """
    path = path or YG_PRICE_HISTORY_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    history = {}
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                history = json.load(f)
        except Exception:
            history = {}

    today = datetime.now().strftime('%Y-%m-%d')

    for card_name, info in updates.items():
        if card_name not in history:
            history[card_name] = []

        existing = [h for h in history[card_name] if h.get('date') == today]
        history[card_name] = [h for h in history[card_name] if h.get('date') != today]

        entry = {
            'date': today,
            'fair_value': round(info['fair_value'], 2),
            'num_sales': info['num_sales'],
        }

        graded_prices = info.get('graded_prices')
        if existing and existing[0].get('graded') and not graded_prices:
            entry['graded'] = existing[0]['graded']
        elif graded_prices:
            merged_graded = existing[0].get('graded', {}) if existing else {}
            merged_graded.update(graded_prices)
            entry['graded'] = merged_graded

        history[card_name].append(entry)

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def load_yg_market_timeline(path=None):
    """Aggregate all raw sales across cards into a daily market timeline.
    Returns a list of dicts: [{date, avg_price, total_volume, min_price, max_price}, ...]
    sorted by date ascending."""
    all_sales = load_yg_raw_sales(path=path)
    if not all_sales:
        return []

    # Collect all sales by date
    by_date = {}
    for card_name, sales in all_sales.items():
        for s in sales:
            d = s.get('sold_date')
            p = s.get('price_val')
            if d and p:
                by_date.setdefault(d, []).append(p)

    timeline = []
    for date, prices in sorted(by_date.items()):
        timeline.append({
            'date': date,
            'avg_price': round(sum(prices) / len(prices), 2),
            'total_volume': len(prices),
            'min_price': round(min(prices), 2),
            'max_price': round(max(prices), 2),
        })

    return timeline


def load_master_db(path=MASTER_DB_PATH):
    """Load the master card database CSV."""
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path)
    df['Team'] = df['Team'].fillna('').str.strip()
    df['Position'] = df['Position'].fillna('').str.strip()
    return df


def save_master_db(df, path=MASTER_DB_PATH):
    """Save the master card database CSV."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_csv(path, index=False)
