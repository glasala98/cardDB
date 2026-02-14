import os
import base64
import json
import re
from datetime import datetime
import urllib.parse
import pandas as pd
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Import scraper functions
# Assuming scrape_card_prices is in the same directory
try:
    from scrape_card_prices import (
        create_driver, search_ebay_sold, calculate_fair_price,
        build_simplified_query, get_grade_info, title_matches_grade
    )
except ImportError:
    # Handle case where it might be imported from a different context
    pass

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(SCRIPT_DIR, "card_prices_summary.csv")
MONEY_COLS = ['Fair Value', 'Median (All)', 'Min', 'Max']

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


def scrape_single_card(card_name):
    """Scrape eBay for a single card and return result dict."""
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
            fair_price, stats = calculate_fair_price(sales)
            return stats
        return None
    finally:
        driver.quit()

def parse_card_name(card_name):
    """Parse a card name string into Player, Year, Set, Card #, Grade components."""
    result = {'Player': '', 'Year': '', 'Set': '', 'Card #': '', 'Grade': ''}

    if not card_name or not isinstance(card_name, str):
        return result

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

        # Set: keep year with set name for clarity
        set_name = parts[0]
        # Add subset keywords from middle segments
        subsets = []
        for part in parts[1:-1]:
            clean_part = re.sub(r'\[.*?\]', '', part).strip()
            clean_part = re.sub(r'#\S+', '', clean_part).strip()
            if clean_part:
                subsets.append(clean_part)
        if subsets:
            set_name = set_name + ' ' + ' '.join(subsets)
        result['Set'] = ' '.join(set_name.split()).strip()

        # Card #: find #NNN or #CU-SC pattern (not serial numbered #70/99)
        num_match = re.search(r'#([\w-]+)(?!\s*/)', card_name)
        if num_match:
            raw_num = num_match.group(1)
            # Skip serial numbers like 70/99, 1/250
            if not re.search(r'#' + re.escape(raw_num) + r'\s*/\s*\d+', card_name):
                result['Card #'] = raw_num

        # Player: last segment, cleaned
        last = parts[-1]
        # Remove grade brackets
        last = re.sub(r'\[.*?\]', '', last).strip()
        # Remove serial numbers like #70/99
        last = re.sub(r'#\d+/\d+', '', last).strip()
        # Remove unbracketed PSA grades
        last = re.sub(r'\bPSA\s+\d+\b', '', last, flags=re.IGNORECASE).strip()
        result['Player'] = last
    else:
        # Freeform format - put the whole name as Player, stripping grade
        player = card_name
        player = re.sub(r'\[.*?\]', '', player).strip()
        player = re.sub(r'\bPSA\s+\d+\b', '', player, flags=re.IGNORECASE).strip()
        result['Player'] = player
        # Try to extract year
        year_match = re.search(r'(\d{4}(?:-\d{2,4})?)', card_name)
        if year_match:
            result['Year'] = year_match.group(1)

    return result


def load_data(csv_path=CSV_PATH):
    df = pd.read_csv(csv_path)
    for col in MONEY_COLS:
        df[col] = df[col].astype(str).str.replace('$', '', regex=False).str.replace(',', '', regex=False)
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    df['Num Sales'] = pd.to_numeric(df['Num Sales'], errors='coerce').fillna(0).astype(int)
    df['Trend'] = df['Trend'].replace({'insufficient data': 'no data', 'unknown': 'no data'})

    # Parse Card Name into display columns
    parsed = df['Card Name'].apply(parse_card_name).apply(pd.Series)
    for col in ['Player', 'Year', 'Set', 'Card #', 'Grade']:
        df[col] = parsed[col]

    return df

PARSED_COLS = ['Player', 'Year', 'Set', 'Card #', 'Grade']

def save_data(df, csv_path=CSV_PATH):
    save_df = df.copy()
    # Drop display-only parsed columns before saving
    save_df = save_df.drop(columns=[c for c in PARSED_COLS if c in save_df.columns], errors='ignore')
    for col in MONEY_COLS:
        save_df[col] = save_df[col].apply(lambda x: f"${x:.2f}" if pd.notna(x) else "$0.00")
    save_df.to_csv(csv_path, index=False)
