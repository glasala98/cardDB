import os
import base64
import json
import re
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

from db import get_db
from psycopg2.extras import RealDictCursor, execute_values

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_YAML = os.path.join(SCRIPT_DIR, "users.yaml")

MONEY_COLS = ['Fair Value', 'Median (All)', 'Min', 'Max', 'Cost Basis']

# ── User management ──────────────────────────────────────────────

def load_users():
    """Load the user configuration from users.yaml.

    Returns:
        Dict mapping username strings to their configuration dicts (which
        include at least ``password_hash``).  Returns an empty dict when
        users.yaml does not exist or contains no ``users`` key.
    """
    if not os.path.exists(USERS_YAML):
        return {}
    with open(USERS_YAML, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f) or {}
    return config.get('users', {})


def verify_password(username, password):
    """Verify a plaintext password against the bcrypt hash stored in users.yaml.

    Args:
        username: The username to look up.
        password: The plaintext password to check.

    Returns:
        True if the username exists and the password matches its stored hash,
        False otherwise (including when bcrypt is unavailable).
    """
    users = load_users()
    if username not in users:
        return False
    pw_hash = users[username].get('password_hash', '')
    try:
        return bcrypt.checkpw(password.encode('utf-8'), pw_hash.encode('utf-8'))
    except Exception:
        return False


def analyze_card_images(front_image_bytes, back_image_bytes=None):
    """Use Claude Vision to extract structured card details from photo bytes.

    Sends the front (and optionally back) image to the Anthropic API and
    returns a parsed dict of card attributes.  Both JPEG, PNG, and WebP
    inputs are supported; the correct media type is detected automatically.

    Args:
        front_image_bytes: Raw bytes of the card front image.
        back_image_bytes: Raw bytes of the card back image.  Optional — pass
            ``None`` to analyse the front only.

    Returns:
        Tuple ``(card_info, error)``.

        * On success: ``card_info`` is a dict with keys ``player_name``,
          ``card_number``, ``card_set``, ``year``, ``variant``, ``grade``,
          ``confidence``, ``is_sports_card``, ``validation_reason``; and
          ``error`` is ``None``.
        * On failure: ``card_info`` is ``None`` and ``error`` is a
          human-readable string describing the problem.
    """
    if not HAS_ANTHROPIC:
        return None, "anthropic package not installed. Run: pip install anthropic"

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None, "ANTHROPIC_API_KEY not set. Add it to your environment."

    client = anthropic.Anthropic(api_key=api_key)

    def _detect_media_type(image_bytes):
        """Detect the MIME type of an image from its magic bytes.

        Args:
            image_bytes: Raw image bytes to inspect.

        Returns:
            MIME type string — one of ``"image/png"``, ``"image/jpeg"``, or
            ``"image/webp"``.  Defaults to ``"image/jpeg"`` when the header
            is not recognised.
        """
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


def _merge_sales(new_sales, existing_sales):
    """Merge two lists of eBay sale dicts, deduplicating by (sold_date, title).

    New sales are preferred when there is a duplicate key — the new entry
    appears first in the combined list before deduplication runs.  The
    returned list is sorted with the most recent ``sold_date`` first;
    entries without a date sort last.

    Args:
        new_sales: List of freshly scraped sale dicts.
        existing_sales: List of previously stored sale dicts.

    Returns:
        Merged, deduplicated, and date-sorted list of sale dicts.
    """
    seen = set()
    merged = []
    for sale in new_sales + existing_sales:
        key = (sale.get('sold_date', ''), sale.get('title', ''))
        if key not in seen:
            seen.add(key)
            merged.append(sale)
    # Sort by date descending (newest first), undated last
    merged.sort(key=lambda s: s.get('sold_date') or '0000-00-00', reverse=True)
    return merged


def _filter_sales_by_variant(card_name, sales):
    """Filter eBay comp sales to those matching the card's variant/parallel keywords.

    Parses the subset/parallel name out of ``card_name`` and keeps only sales
    whose listing title contains at least one of its distinctive keywords.
    Common generic words (e.g. ``rookie``, ``young``, ``guns``) are excluded
    from the keyword list to avoid over-filtering.

    Falls back to the full unfiltered list when no keywords can be extracted
    or when filtering would remove every sale.

    Args:
        card_name: Full card name string (e.g. ``"2023-24 UD - Young Guns Red
            Prism #201 - Connor Bedard"``).
        sales: List of eBay sale dicts, each with at least a ``"title"`` key.

    Returns:
        Filtered list of sale dicts, or the original ``sales`` list unchanged
        when filtering is not applicable.
    """
    if not sales:
        return sales
    parsed = parse_card_name(card_name)
    subset = (parsed.get('Subset') or '').strip()
    if not subset:
        return sales
    # Words too generic to distinguish one parallel from another
    _SKIP = {
        'marquee', 'rookie', 'rookies', 'young', 'guns', 'rc', 'base',
        'sp', 'ssp', 'variation', 'short', 'print', 'the', 'and',
    }
    kws = [w for w in re.findall(r'\b[A-Za-z]{3,}\b', subset) if w.lower() not in _SKIP]
    if not kws:
        return sales
    # Require ALL keywords present (AND logic) — prevents e.g. "Red" alone
    # matching an unrelated parallel that doesn't say "Red Prism" in the title.
    filtered = [s for s in sales if all(kw.lower() in s.get('title', '').lower() for kw in kws)]
    # Return empty rather than falling back to all sales — a wrong-variant price
    # is worse than "No Data". The scraper's stage fallbacks handle the empty case.
    return filtered


def _strip_grade_from_name(card_name):
    """Remove a grading-company label from a card name to obtain its raw equivalent.

    Handles both bracketed forms (``[PSA 9]``) and trailing inline forms
    (``PSA 9`` at end of string).  Supports PSA, BGS, CGC, SGC, and CSG.

    Args:
        card_name: Full card name string that may contain a grade marker.

    Returns:
        Card name string with the grade marker stripped and surrounding
        whitespace cleaned up.
    """
    name = re.sub(r'\s*\[(?:PSA|BGS|CGC|SGC|CSG)\s+[\d.]+[^\]]*\]', '', card_name)
    name = re.sub(r'\s+(?:PSA|BGS|CGC|SGC|CSG)\s+\d+(?:\.\d+)?\s*$', '', name, flags=re.IGNORECASE)
    return name.strip()


def scrape_single_card(card_name, username):
    """Scrape eBay sold listings for one card and persist the results to Supabase.

    Launches a headless Chrome driver, searches eBay for the card, applies
    variant/parallel filtering, and falls back to simplified queries or grade
    estimation (raw → PSA 9, raw/PSA 9 → PSA 10) when no direct comps are
    found.  Merges new sales with any previously stored sales in ``card_results``,
    preserves existing ``image_url`` data, and upserts the updated row.

    Args:
        card_name: Full card name string used as the eBay search query and
            the key in ``card_results``.
        username: Username whose card_results row should be updated.

    Returns:
        Stats dict from ``calculate_fair_price`` (keys include ``fair_price``,
        ``num_sales``, ``min``, ``max``, ``median``) when sales are found, or
        ``None`` when no comparable sales could be located.
    """
    driver = create_driver()
    try:
        sales = search_ebay_sold(driver, card_name)
        # Filter to comps that match the card's specific variant/parallel
        sales = _filter_sales_by_variant(card_name, sales)

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
            # Apply variant filter to simplified results too
            sales = _filter_sales_by_variant(card_name, sales)

        # ── Graded card estimation fallback ──────────────────────────────────
        # When no direct comps exist, estimate from raw or PSA-9 comps.
        # PSA 9  ≈ raw price   (1×)
        # PSA 10 ≈ 2.5× raw or 2.5× PSA 9
        is_estimated = False
        price_source = 'direct'
        if not sales:
            grade_str, grade_num = get_grade_info(card_name)
            if grade_str and grade_num:
                raw_name = _strip_grade_from_name(card_name)
                if raw_name and raw_name != card_name:
                    raw_sales = search_ebay_sold(driver, raw_name, max_results=30)
                    raw_sales = _filter_sales_by_variant(raw_name, raw_sales)
                    if raw_sales:
                        if grade_num == 9:
                            sales = raw_sales
                            is_estimated = True
                            price_source = 'raw_estimate'
                        elif grade_num == 10:
                            sales = [{**s, 'price_val': round(s.get('price_val', 0) * 2.5, 2)}
                                     for s in raw_sales]
                            is_estimated = True
                            price_source = 'raw_estimate_psa10'
                # PSA 10 secondary fallback: PSA 9 comps × 2.5
                if not sales and grade_num == 10:
                    psa9_name = re.sub(r'\bPSA\s*10\b', 'PSA 9', card_name, flags=re.IGNORECASE)
                    if psa9_name != card_name:
                        psa9_sales = search_ebay_sold(driver, psa9_name, max_results=30)
                        psa9_sales = _filter_sales_by_variant(psa9_name, psa9_sales)
                        if psa9_sales:
                            sales = [{**s, 'price_val': round(s.get('price_val', 0) * 2.5, 2)}
                                     for s in psa9_sales]
                            is_estimated = True
                            price_source = 'psa9_estimate'

        if sales:
            from scrape_card_prices import extract_serial_run, _normalize_shipping
            target_serial = extract_serial_run(card_name)
            sales = _normalize_shipping(sales)
            fair_price, stats = calculate_fair_price(sales, target_serial=target_serial)
            # Load existing card_results to merge/preserve image_url
            existing_data = load_card_results(username, card_name)
            existing_sales = existing_data.get('raw_sales', [])
            merged = _merge_sales(sales, existing_sales)
            image_url = existing_data.get('image_url') or next(
                (s.get('image_url') for s in sales if s.get('image_url')), None
            )
            save_card_results(
                username, card_name,
                raw_sales=merged,
                scraped_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                confidence=stats.get('confidence', ''),
                image_url=image_url,
                image_hash=existing_data.get('image_hash', ''),
            )
            return stats
        return None
    finally:
        driver.quit()

def parse_card_name(card_name):
    """Parse a structured card name string into its constituent fields.

    Supports the canonical ``"YEAR SET - SUBSET - PLAYER"`` dash-delimited
    format as well as freeform names.  Extracts serial numbers (``#70/99``),
    grading labels (``[PSA 9]``), card numbers (``#201``), subset names, and
    player names via regex heuristics.

    Examples::

        parse_card_name("2023-24 Upper Deck - Young Guns #201 - Connor Bedard [PSA 9] /99")
        # → {'Player': 'Connor Bedard', 'Year': '2023-24',
        #    'Set': '2023-24 Upper Deck', 'Subset': 'Young Guns',
        #    'Card #': '201', 'Serial': '1/99', 'Grade': 'PSA 9'}

    Args:
        card_name: Raw card name string to parse.

    Returns:
        Dict with string values for keys ``Player``, ``Year``, ``Set``,
        ``Subset``, ``Card #``, ``Serial``, and ``Grade``.  Any field that
        cannot be determined is set to an empty string.
    """
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


_COL_FROM_DB = {
    'card_name':    'Card Name',
    'fair_value':   'Fair Value',
    'trend':        'Trend',
    'top_3_prices': 'Top 3 Prices',
    'median_all':   'Median (All)',
    'min_price':    'Min',
    'max_price':    'Max',
    'num_sales':    'Num Sales',
    'tags':         'Tags',
    'cost_basis':   'Cost Basis',
    'purchase_date': 'Purchase Date',
}
_COL_TO_DB = {v: k for k, v in _COL_FROM_DB.items()}


def load_data(username: str) -> pd.DataFrame:
    """Load the active card collection for a user from PostgreSQL."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM cards WHERE user_id = %s AND archived = FALSE",
                (username,)
            )
            rows = cur.fetchall()

    if not rows:
        parse_cols = ['Player', 'Year', 'Set', 'Subset', 'Card #', 'Serial', 'Grade']
        return pd.DataFrame(columns=list(_COL_FROM_DB.values()) + parse_cols + ['Last Scraped', 'Confidence'])

    df = pd.DataFrame([dict(r) for r in rows]).rename(columns=_COL_FROM_DB)

    # Drop internal columns that callers don't expect
    for drop_col in ('id', 'user_id', 'archived', 'archived_date', 'created_at', 'updated_at'):
        if drop_col in df.columns:
            df = df.drop(columns=[drop_col])

    # Normalize money columns
    for col in MONEY_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    df['Num Sales'] = pd.to_numeric(df.get('Num Sales', 0), errors='coerce').fillna(0).astype(int)
    df['Trend'] = df['Trend'].replace({'insufficient data': 'no data', 'unknown': 'no data'}).fillna('no data')
    df['Tags'] = df['Tags'].fillna('')
    df['Top 3 Prices'] = df['Top 3 Prices'].fillna('')
    df['Purchase Date'] = df['Purchase Date'].fillna('')

    # Fetch Last Scraped + Confidence from card_results
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT card_name, scraped_at, confidence, image_url FROM card_results WHERE user_id = %s",
                (username,)
            )
            res_rows = cur.fetchall()
    res_map = {r['card_name']: r for r in res_rows}
    df['Last Scraped'] = df['Card Name'].map(
        lambda n: (str(res_map.get(n, {}).get('scraped_at') or ''))[:10]
    )
    df['Confidence'] = df['Card Name'].map(
        lambda n: res_map.get(n, {}).get('confidence') or ''
    )
    df['Image URL'] = df['Card Name'].map(
        lambda n: res_map.get(n, {}).get('image_url') or ''
    )

    # Parse card names into display columns
    parse_cols = ['Player', 'Year', 'Set', 'Subset', 'Card #', 'Serial', 'Grade']
    if len(df) > 0:
        parsed = df['Card Name'].apply(parse_card_name).apply(pd.Series)
        for col in parse_cols:
            df[col] = parsed[col] if col in parsed.columns else ''
    else:
        for col in parse_cols:
            df[col] = pd.Series(dtype='object')

    return df

PARSED_COLS = ['Player', 'Year', 'Set', 'Subset', 'Card #', 'Serial', 'Grade', 'Last Scraped', 'Confidence']


def save_data(df: pd.DataFrame, username: str) -> None:
    """Upsert the card collection DataFrame to Supabase.

    Drops display-only parsed columns before saving and converts
    DataFrame column names back to snake_case for the ``cards`` table.

    Args:
        df: Card collection DataFrame as returned by ``load_data``.
        username: Username whose ``cards`` rows to upsert.
    """
    save_df = df.drop(columns=[c for c in PARSED_COLS if c in df.columns], errors='ignore').copy()
    save_df = save_df.rename(columns=_COL_TO_DB)

    rows = []
    for rec in save_df.to_dict('records'):
        rec['user_id'] = username
        rec['archived'] = False
        for k, v in rec.items():
            if isinstance(v, float) and pd.isna(v):
                rec[k] = None
        rows.append(rec)

    with get_db() as conn:
        with conn.cursor() as cur:
            for i in range(0, len(rows), 500):
                execute_values(cur, """
                    INSERT INTO cards
                        (user_id, card_name, fair_value, trend, top_3_prices,
                         median_all, min_price, max_price, num_sales, tags,
                         cost_basis, purchase_date, archived)
                    VALUES %s
                    ON CONFLICT (user_id, card_name) DO UPDATE SET
                        fair_value    = EXCLUDED.fair_value,
                        trend         = EXCLUDED.trend,
                        top_3_prices  = EXCLUDED.top_3_prices,
                        median_all    = EXCLUDED.median_all,
                        min_price     = EXCLUDED.min_price,
                        max_price     = EXCLUDED.max_price,
                        num_sales     = EXCLUDED.num_sales,
                        tags          = EXCLUDED.tags,
                        cost_basis    = EXCLUDED.cost_basis,
                        purchase_date = EXCLUDED.purchase_date,
                        updated_at    = NOW()
                """, [
                    (r.get('user_id'), r.get('card_name'), r.get('fair_value'),
                     r.get('trend'), r.get('top_3_prices'), r.get('median_all'),
                     r.get('min_price'), r.get('max_price'), r.get('num_sales'),
                     r.get('tags'), r.get('cost_basis'), r.get('purchase_date'),
                     r.get('archived', False))
                    for r in rows[i:i + 500]
                ])


def load_card_results(username: str, card_name: str) -> dict:
    """Load the scrape metadata + raw_sales for one card from Supabase.

    Args:
        username: Username whose card_results to query.
        card_name: Exact card name key.

    Returns:
        Dict with keys ``raw_sales``, ``scraped_at``, ``confidence``,
        ``image_url``, ``image_hash``, ``image_url_back``, ``search_url``,
        ``is_estimated``, ``price_source``.  Returns an empty dict when not found.
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT raw_sales, scraped_at, confidence, image_url, image_hash,
                       image_url_back, search_url, is_estimated, price_source
                FROM card_results WHERE user_id = %s AND card_name = %s
            """, (username, card_name))
            row = cur.fetchone()
    return dict(row) if row else {}


def load_all_card_results(username: str) -> dict:
    """Load scrape metadata + raw_sales for ALL cards belonging to a user.

    Returns a dict keyed by card_name for efficient batch lookups (e.g.
    during the daily scrape where N per-card queries would be slow).

    Args:
        username: Username whose card_results to query.

    Returns:
        Dict mapping card_name strings to result dicts (same shape as
        ``load_card_results``).
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT card_name, raw_sales, scraped_at, confidence, image_url,
                       image_hash, image_url_back, search_url, is_estimated, price_source
                FROM card_results WHERE user_id = %s
            """, (username,))
            rows = cur.fetchall()
    return {r['card_name']: dict(r) for r in rows}


def save_card_results(username: str, card_name: str, raw_sales: list,
                      scraped_at: str = None, confidence: str = '',
                      image_url: str = '', image_hash: str = '',
                      image_url_back: str = '', search_url: str = '',
                      is_estimated: bool = False,
                      price_source: str = 'direct') -> None:
    """Upsert raw sales + scrape metadata for one card in Supabase.

    Args:
        username: Username whose card_results row to upsert.
        card_name: Exact card name key.
        raw_sales: List of sale dicts from the scraper.
        scraped_at: ISO timestamp string of when the scrape ran.
        confidence: Confidence level string (e.g. ``'high'``).
        image_url: eBay or CDN image URL for the card front.
        image_hash: eBay image hash used to build the CDN URL.
        image_url_back: eBay or CDN image URL for the card back.
        search_url: eBay search URL used to find the card.
        is_estimated: True when the price was estimated (not from direct comps).
        price_source: Source of the price ('direct', 'raw_estimate', etc.).
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO card_results
                    (user_id, card_name, raw_sales, scraped_at, confidence,
                     image_url, image_hash, image_url_back, search_url,
                     is_estimated, price_source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, card_name) DO UPDATE SET
                    raw_sales      = EXCLUDED.raw_sales,
                    scraped_at     = EXCLUDED.scraped_at,
                    confidence     = EXCLUDED.confidence,
                    image_url      = EXCLUDED.image_url,
                    image_hash     = EXCLUDED.image_hash,
                    image_url_back = EXCLUDED.image_url_back,
                    search_url     = EXCLUDED.search_url,
                    is_estimated   = EXCLUDED.is_estimated,
                    price_source   = EXCLUDED.price_source,
                    updated_at     = NOW()
            """, (
                username, card_name,
                json.dumps(raw_sales),
                scraped_at or datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                confidence or '', image_url or '', image_hash or '',
                image_url_back or '', search_url or '',
                bool(is_estimated), price_source or 'direct',
            ))


def load_sales_history(username: str, card_name: str) -> list:
    """Load the raw eBay sold-listing history for a single card.

    Args:
        username: Username whose card_results to query.
        card_name: The card name key.

    Returns:
        List of sale dicts (each with keys such as ``sold_date``, ``title``,
        ``price_val``).  Returns an empty list when no results found.
    """
    data = load_card_results(username, card_name)
    return data.get('raw_sales', [])


def append_price_history(username: str, card_name: str, fair_value: float,
                         num_sales: int) -> None:
    """Upsert a dated price snapshot for a card in ``card_price_history``.

    At most one snapshot per (user, card, date) is kept (upsert on conflict).

    Args:
        username: Username whose price history to update.
        card_name: Card identifier.
        fair_value: Calculated fair market value to record.
        num_sales: Number of eBay sales used to compute the value.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO card_price_history (user_id, card_name, date, price, num_sales)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id, card_name, date) DO UPDATE SET
                    price     = EXCLUDED.price,
                    num_sales = EXCLUDED.num_sales
            """, (username, card_name, datetime.now().strftime('%Y-%m-%d'),
                  round(float(fair_value), 2), int(num_sales)))


def load_price_history(username: str, card_name: str) -> list:
    """Load the fair-value price history for a single card.

    Args:
        username: Username whose price history to load.
        card_name: The card name to look up.

    Returns:
        List of snapshot dicts ``{"date", "fair_value", "num_sales"}``,
        ordered oldest-first.  Returns an empty list when no history found.
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT date, price, num_sales FROM card_price_history
                WHERE user_id = %s AND card_name = %s ORDER BY date
            """, (username, card_name))
            rows = cur.fetchall()
    return [{'date': str(r['date']), 'fair_value': r['price'], 'num_sales': r['num_sales']}
            for r in rows]


def load_all_price_history(username: str) -> dict:
    """Load fair-value history for ALL active cards belonging to a user.

    Returns a dict keyed by card_name for efficient batch use (e.g. portfolio
    history chart which must aggregate across every card).

    Args:
        username: Username whose card_price_history to query.

    Returns:
        Dict mapping card_name → list of ``{"date", "fair_value", "num_sales"}``
        dicts ordered oldest-first.
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT card_name, date, price, num_sales FROM card_price_history
                WHERE user_id = %s ORDER BY date
            """, (username,))
            rows = cur.fetchall()
    result: dict = {}
    for r in rows:
        result.setdefault(r['card_name'], []).append({
            'date':       str(r['date']),
            'fair_value': r['price'],
            'num_sales':  r['num_sales'],
        })
    return result


def append_portfolio_snapshot(username: str, total_value: float,
                              total_cards: int, avg_value: float) -> None:
    """Upsert a daily portfolio value snapshot in Supabase.

    At most one snapshot per (user, date) is kept (upsert on conflict).

    Args:
        username: Username whose portfolio history to update.
        total_value: Sum of fair values across the whole collection (CAD).
        total_cards: Number of cards in the collection.
        avg_value: Average fair value per card.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO portfolio_history (user_id, date, total_value, total_cards, avg_value)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id, date) DO UPDATE SET
                    total_value = EXCLUDED.total_value,
                    total_cards = EXCLUDED.total_cards,
                    avg_value   = EXCLUDED.avg_value
            """, (username, datetime.now().strftime('%Y-%m-%d'),
                  round(float(total_value), 2), int(total_cards), round(float(avg_value), 2)))


def load_portfolio_history(username: str) -> list:
    """Load the full list of daily portfolio value snapshots from Supabase.

    Args:
        username: Username whose portfolio history to load.

    Returns:
        List of snapshot dicts ``{"date", "total_value", "total_cards",
        "avg_value"}``, ordered by date ascending.
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT date, total_value, total_cards, avg_value FROM portfolio_history
                WHERE user_id = %s ORDER BY date
            """, (username,))
            rows = cur.fetchall()
    return [{'date': str(r['date']), 'total_value': r['total_value'],
             'total_cards': r['total_cards'], 'avg_value': r['avg_value']}
            for r in rows]


def scrape_graded_comparison(card_name):
    """Scrape eBay sold prices for a card at raw, PSA 9, and PSA 10 grades.

    Strips any existing grade marker from ``card_name`` and then runs three
    separate eBay searches (raw / PSA 9 / PSA 10) in the same browser
    session.  A short random sleep is inserted between searches to reduce
    the risk of rate-limiting.

    Args:
        card_name: Full card name string.  Any existing grading label is
            removed before constructing the per-grade search queries.

    Returns:
        Dict with keys ``"raw"``, ``"psa_9"``, ``"psa_10"``.  Each value is
        either a stats dict ``{"fair_price", "num_sales", "min", "max"}`` or
        ``None`` when no comparable sales were found for that grade.
    """
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


def archive_card(df: pd.DataFrame, username: str, card_name: str) -> pd.DataFrame:
    """Mark a card as archived in Supabase and remove it from the active DataFrame.

    Sets ``archived=TRUE`` and ``archived_date`` on the ``cards`` row.
    If the card is not found in ``df``, the DataFrame is returned unchanged.

    Args:
        df: Active card collection DataFrame (as returned by ``load_data``).
        username: Username whose card to archive.
        card_name: Exact ``Card Name`` value of the card to archive.

    Returns:
        Updated DataFrame with the specified card removed.
    """
    if df[df['Card Name'] == card_name].empty:
        return df

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE cards SET archived = TRUE, archived_date = NOW()
                WHERE user_id = %s AND card_name = %s
            """, (username, card_name))

    return df[df['Card Name'] != card_name].reset_index(drop=True)


def load_archive(username: str) -> pd.DataFrame:
    """Load archived cards for a user from Supabase.

    Args:
        username: Username whose archive to load.

    Returns:
        DataFrame of archived cards with an ``Archived Date`` column,
        or an empty DataFrame when none exist.
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM cards WHERE user_id = %s AND archived = TRUE",
                (username,)
            )
            rows = cur.fetchall()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame([dict(r) for r in rows]).rename(columns=_COL_FROM_DB)
    if 'archived_date' in df.columns:
        df['Archived Date'] = df['archived_date']
    for drop_col in ('id', 'user_id', 'archived', 'archived_date', 'created_at', 'updated_at'):
        if drop_col in df.columns:
            df = df.drop(columns=[drop_col])
    for col in MONEY_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    return df


def restore_card(username: str, card_name: str) -> dict | None:
    """Clear the archived flag on a card and return its data for re-adding.

    Args:
        username: Username whose archived card to restore.
        card_name: Exact ``Card Name`` value to restore.

    Returns:
        Dict of the card row (with original column names), or ``None`` when
        the card is not found in the archive.
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM cards
                WHERE user_id = %s AND card_name = %s AND archived = TRUE
            """, (username, card_name))
            row = cur.fetchone()
        if not row:
            return None
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE cards SET archived = FALSE, archived_date = NULL
                WHERE user_id = %s AND card_name = %s
            """, (username, card_name))

    raw = dict(row)
    return {_COL_FROM_DB.get(k, k): v for k, v in raw.items()}


# ── Master DB ───────────────────────────────────────────────────
CANADIAN_TEAM_ABBREVS = {'TOR', 'MTL', 'OTT', 'WPG', 'CGY', 'EDM', 'VAN'}

TEAM_NAME_TO_ABBREV = {
    "Anaheim Ducks": "ANA", "Arizona Coyotes": "ARI", "Boston Bruins": "BOS",
    "Buffalo Sabres": "BUF", "Calgary Flames": "CGY", "Carolina Hurricanes": "CAR",
    "Chicago Blackhawks": "CHI", "Colorado Avalanche": "COL", "Columbus Blue Jackets": "CBJ",
    "Dallas Stars": "DAL", "Detroit Red Wings": "DET", "Edmonton Oilers": "EDM",
    "Florida Panthers": "FLA", "Los Angeles Kings": "LAK", "Minnesota Wild": "MIN",
    "Montreal Canadiens": "MTL", "Nashville Predators": "NSH", "New Jersey Devils": "NJD",
    "New York Islanders": "NYI", "New York Rangers": "NYR", "Ottawa Senators": "OTT",
    "Philadelphia Flyers": "PHI", "Pittsburgh Penguins": "PIT", "San Jose Sharks": "SJS",
    "Seattle Kraken": "SEA", "St. Louis Blues": "STL", "Tampa Bay Lightning": "TBL",
    "Toronto Maple Leafs": "TOR", "Utah Hockey Club": "UTA", "Vancouver Canucks": "VAN",
    "Vegas Golden Knights": "VGK", "Washington Capitals": "WSH", "Winnipeg Jets": "WPG",
}
TEAM_ABBREV_TO_NAME = {v: k for k, v in TEAM_NAME_TO_ABBREV.items()}


def load_player_stats(player_name=None, sport: str = 'NHL'):
    """Load player statistics from Supabase for a given sport.

    Args:
        player_name: If provided, return only the stats dict for this player.
            Pass ``None`` to return the full ``{"players": ..., "standings": ...}``
            dict (matching the old JSON file shape used by analytics callers).
        sport: Sport code (default ``'NHL'``). Future values: ``'NBA'``, ``'NFL'``, ``'MLB'``.

    Returns:
        When ``player_name`` is given: the player's stats dict, or ``None``
        if the player is not found.
        When ``player_name`` is ``None``: dict with keys ``players`` and
        ``standings``, or ``{}`` on error.
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if player_name:
                cur.execute(
                    "SELECT data FROM player_stats WHERE sport = %s AND player = %s",
                    (sport, player_name)
                )
                row = cur.fetchone()
                return row['data'] if row else None
            cur.execute("SELECT player, data FROM player_stats WHERE sport = %s", (sport,))
            player_rows = cur.fetchall()
            cur.execute("SELECT team, data FROM standings WHERE sport = %s", (sport,))
            standing_rows = cur.fetchall()
    return {
        'players':   {r['player']: r['data'] for r in player_rows},
        'standings': {r['team']:   r['data'] for r in standing_rows},
    }


# Backward-compat alias used by scrape_nhl_stats.py callers
load_nhl_player_stats = load_player_stats


def save_player_stats(data: dict, sport: str = 'NHL') -> None:
    """Write the full player stats dict to Supabase for a given sport.

    Upserts every player into ``player_stats`` and every team into ``standings``.

    Args:
        data: Complete stats dict with keys ``players`` and ``standings``.
        sport: Sport code (default ``'NHL'``).
    """
    player_rows = [(sport, name, json.dumps(pdata))
                   for name, pdata in data.get('players', {}).items()]
    standing_rows = [(sport, team, json.dumps(sdata))
                     for team, sdata in data.get('standings', {}).items()]
    with get_db() as conn:
        with conn.cursor() as cur:
            for i in range(0, len(player_rows), 500):
                execute_values(cur, """
                    INSERT INTO player_stats (sport, player, data)
                    VALUES %s
                    ON CONFLICT (sport, player) DO UPDATE SET
                        data = EXCLUDED.data, updated_at = NOW()
                """, player_rows[i:i + 500])
            for i in range(0, len(standing_rows), 500):
                execute_values(cur, """
                    INSERT INTO standings (sport, team, data)
                    VALUES %s
                    ON CONFLICT (sport, team) DO UPDATE SET
                        data = EXCLUDED.data, updated_at = NOW()
                """, standing_rows[i:i + 500])


# Backward-compat alias
save_nhl_player_stats = save_player_stats


def load_standings(sport: str = 'NHL') -> dict:
    """Load team standings from Supabase for a given sport.

    Returns:
        Dict mapping team abbreviation strings to standings data dicts.
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT team, data FROM standings WHERE sport = %s", (sport,))
            rows = cur.fetchall()
    return {r['team']: r['data'] for r in rows}


# Backward-compat alias
load_nhl_standings = load_standings


def get_player_stats_for_card(player_name, sport: str = 'NHL'):
    """Return a formatted current-season stats dict for a card's player.

    Reads from Supabase and reshapes the ``current_season`` block into a flat
    dict that includes a pre-built human-readable ``summary`` string.  Skater
    and goalie stats are handled separately.

    Args:
        player_name: Full player name as stored in ``nhl_player_stats``.

    Returns:
        Dict with keys ``type``, ``position``, ``current_team``, ``nhl_id``,
        ``history``, ``summary``, and all current-season stat fields (e.g.
        ``goals``, ``assists``, ``points`` for skaters; ``wins``, ``gaa``,
        ``save_pct`` for goalies).  Returns ``None`` when the player is not
        found or has no current-season data.
    """
    stats = load_player_stats(player_name, sport='NHL')
    if not stats:
        return None
    current = stats.get('current_season', {})
    result = {
        'type': stats.get('type', 'skater'),
        'position': stats.get('position', ''),
        'current_team': stats.get('current_team', ''),
        'nhl_id': stats.get('nhl_id'),
        'history': stats.get('history', []),
    }
    if result['type'] == 'skater':
        result.update({
            'goals': current.get('goals', 0),
            'assists': current.get('assists', 0),
            'points': current.get('points', 0),
            'games_played': current.get('games_played', 0),
            'plus_minus': current.get('plus_minus', 0),
            'shots': current.get('shots', 0),
            'shooting_pct': current.get('shooting_pct', 0),
            'powerplay_goals': current.get('powerplay_goals', 0),
            'game_winning_goals': current.get('game_winning_goals', 0),
            'summary': f"{current.get('points',0)}pts ({current.get('goals',0)}G, {current.get('assists',0)}A) in {current.get('games_played',0)}GP",
        })
    else:
        result.update({
            'wins': current.get('wins', 0),
            'losses': current.get('losses', 0),
            'save_pct': current.get('save_pct', 0),
            'gaa': current.get('gaa', 0),
            'games_played': current.get('games_played', 0),
            'shutouts': current.get('shutouts', 0),
            'summary': f"{current.get('wins',0)}W-{current.get('losses',0)}L, {current.get('save_pct',0):.3f}SV%, {current.get('gaa',0):.2f}GAA",
        })
    return result


def get_player_bio_for_card(player_name):
    """Return the biographical data dict for a card's player.

    Args:
        player_name: Full player name as stored in ``nhl_player_stats``.

    Returns:
        Bio dict with fields such as ``nationality``, ``draft_round``, and
        ``draft_overall``, or ``None`` when the player is not found or has
        no bio data.
    """
    stats = load_player_stats(player_name, sport='NHL')
    if not stats or not stats.get('bio'):
        return None
    return stats['bio']


def get_all_player_bios():
    """Return biographical data for every player that has bio information.

    Returns:
        Dict mapping player name strings to their bio dicts.  Players with no
        ``bio`` entry are excluded.  Returns an empty dict when no stats exist.
    """
    data = load_nhl_player_stats()
    if not data:
        return {}
    players = data.get('players', {})
    return {name: entry['bio'] for name, entry in players.items() if entry.get('bio')}


def compute_correlation_snapshot(cards_df, nhl_players, nhl_standings):
    """Compute a price-vs-performance correlation snapshot.

    Args:
        cards_df: DataFrame with at least PlayerName, FairValue columns
        nhl_players: dict from nhl_player_stats.json 'players' key
        nhl_standings: dict from nhl_player_stats.json 'standings' key

    Returns:
        dict: snapshot ready to store in yg_correlation_history.json
    """
    from scipy.stats import linregress

    # Build paired data
    paired_skaters = []
    paired_goalies = []
    seen_players = set()

    for _, row in cards_df.iterrows():
        pname = row['PlayerName']
        if pname in seen_players:
            continue
        seen_players.add(pname)
        price = float(row.get('FairValue', 0) or 0)
        if price <= 0:
            continue
        nhl = nhl_players.get(pname)
        if not nhl or not nhl.get('current_season'):
            continue

        cs = nhl['current_season']
        team = nhl.get('current_team', '')
        pos = nhl.get('position', '')

        if nhl.get('type') == 'skater':
            paired_skaters.append({
                'name': pname, 'price': price,
                'points': cs.get('points', 0),
                'goals': cs.get('goals', 0),
                'assists': cs.get('assists', 0),
                'gp': cs.get('games_played', 0),
                'plus_minus': cs.get('plus_minus', 0),
                'team': team, 'position': pos,
            })
        else:
            team_stand = nhl_standings.get(team, {})
            paired_goalies.append({
                'name': pname, 'price': price,
                'wins': cs.get('wins', 0),
                'svpct': cs.get('save_pct', 0),
                'gaa': cs.get('gaa', 0),
                'team': team, 'position': 'G',
                'team_points': team_stand.get('points', 0),
            })

    def safe_linregress(x_vals, y_vals):
        """Run a linear regression, returning None when there are too few points.

        Args:
            x_vals: Sequence of independent-variable values.
            y_vals: Sequence of dependent-variable values (same length as
                ``x_vals``).

        Returns:
            Dict with keys ``r``, ``r_squared``, ``slope``, ``intercept``,
            ``p_value``, and ``n``, or ``None`` when fewer than three data
            points are provided.
        """
        if len(x_vals) < 3:
            return None
        result = linregress(x_vals, y_vals)
        return {
            'r': round(result.rvalue, 4),
            'r_squared': round(result.rvalue ** 2, 4),
            'slope': round(result.slope, 4),
            'intercept': round(result.intercept, 4),
            'p_value': round(result.pvalue, 6),
            'n': len(x_vals),
        }

    # Correlations
    sk_prices = [s['price'] for s in paired_skaters]
    sk_points = [s['points'] for s in paired_skaters]
    sk_goals = [s['goals'] for s in paired_skaters]
    sk_assists = [s['assists'] for s in paired_skaters]

    correlations = {}
    correlations['points_vs_price'] = safe_linregress(sk_points, sk_prices)
    correlations['goals_vs_price'] = safe_linregress(sk_goals, sk_prices)
    correlations['assists_vs_price'] = safe_linregress(sk_assists, sk_prices)

    gl_prices = [g['price'] for g in paired_goalies]
    gl_wins = [g['wins'] for g in paired_goalies]
    gl_svpct = [g['svpct'] for g in paired_goalies]
    correlations['goalie_wins_vs_price'] = safe_linregress(gl_wins, gl_prices)
    correlations['goalie_svpct_vs_price'] = safe_linregress(gl_svpct, gl_prices)
    correlations = {k: v for k, v in correlations.items() if v is not None}

    # Tiers
    tier_brackets = [
        (0, 5, '<5 pts'), (6, 10, '6-10 pts'), (11, 20, '11-20 pts'),
        (21, 30, '21-30 pts'), (31, 40, '31-40 pts'), (41, 50, '41-50 pts'),
        (51, 999, '51+ pts'),
    ]
    tiers = []
    for low, high, label in tier_brackets:
        tier_players = [s for s in paired_skaters if low <= s['points'] <= high]
        if tier_players:
            prices = [s['price'] for s in tier_players]
            avg_p = round(sum(prices) / len(prices), 2)
            med_p = round(sorted(prices)[len(prices) // 2], 2)
            tiers.append({
                'bracket': f"{low}-{high}" if high < 999 else f"{low}+",
                'label': label, 'avg_price': avg_p, 'median_price': med_p,
                'count': len(tier_players),
            })

    # Team premiums
    team_groups = {}
    for s in paired_skaters + paired_goalies:
        t = s['team']
        if t not in team_groups:
            team_groups[t] = {'prices': [], 'points': [], 'wins': []}
        team_groups[t]['prices'].append(s['price'])
        if 'points' in s:
            team_groups[t]['points'].append(s['points'])
        if 'wins' in s:
            team_groups[t]['wins'].append(s['wins'])

    team_premiums = {}
    for t, data in team_groups.items():
        entry = {
            'avg_price': round(sum(data['prices']) / len(data['prices']), 2),
            'count': len(data['prices']),
            'country': 'CA' if t in CANADIAN_TEAM_ABBREVS else 'US',
        }
        if data['points']:
            entry['avg_points'] = round(sum(data['points']) / len(data['points']), 1)
        team_premiums[t] = entry

    # Position breakdown
    pos_groups = {}
    for s in paired_skaters:
        p = s['position']
        pos_groups.setdefault(p, {'prices': [], 'points': []})
        pos_groups[p]['prices'].append(s['price'])
        pos_groups[p]['points'].append(s['points'])

    position_breakdown = {}
    for p, data in pos_groups.items():
        position_breakdown[p] = {
            'avg_price': round(sum(data['prices']) / len(data['prices']), 2),
            'avg_points': round(sum(data['points']) / len(data['points']), 1),
            'count': len(data['prices']),
        }
    if paired_goalies:
        position_breakdown['G'] = {
            'avg_price': round(sum(g['price'] for g in paired_goalies) / len(paired_goalies), 2),
            'avg_wins': round(sum(g['wins'] for g in paired_goalies) / len(paired_goalies), 1),
            'count': len(paired_goalies),
        }

    # Compact per-player data
    players_compact = {}
    for s in paired_skaters:
        players_compact[s['name']] = {
            'price': s['price'], 'points': s['points'],
            'goals': s['goals'], 'gp': s['gp'],
            'team': s['team'], 'position': s['position'],
        }
    for g in paired_goalies:
        players_compact[g['name']] = {
            'price': g['price'], 'wins': g['wins'],
            'svpct': g['svpct'], 'team': g['team'], 'position': 'G',
        }

    return {
        'meta': {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'matched_players': len(paired_skaters) + len(paired_goalies),
            'skaters_with_price': len(paired_skaters),
            'goalies_with_price': len(paired_goalies),
        },
        'correlations': correlations,
        'tiers': tiers,
        'team_premiums': team_premiums,
        'position_breakdown': position_breakdown,
        'players': players_compact,
    }


def load_correlation_history(sport: str = 'NHL') -> dict:
    """Load the full correlation history from Supabase.

    Args:
        sport: Sport code (default ``'NHL'``).

    Returns:
        Dict keyed by ``"YYYY-MM-DD"`` date strings, each mapping to the
        snapshot produced by ``compute_correlation_snapshot``.
        Returns an empty dict when no history is stored.
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT date, data FROM rookie_correlation_history WHERE sport = %s",
                (sport,)
            )
            rows = cur.fetchall()
    return {str(r['date']): r['data'] for r in rows}


def save_correlation_snapshot(snapshot: dict, sport: str = 'NHL') -> None:
    """Upsert today's correlation snapshot in Supabase.

    Args:
        snapshot: Snapshot dict as returned by ``compute_correlation_snapshot``.
        sport: Sport code (default ``'NHL'``).
    """
    today = datetime.now().strftime('%Y-%m-%d')
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO rookie_correlation_history (sport, date, data)
                VALUES (%s, %s, %s)
                ON CONFLICT (sport, date) DO UPDATE SET data = EXCLUDED.data
            """, (sport, today, json.dumps(snapshot)))


def append_rookie_price_history(card_name: str, fair_value: float, num_sales: int,
                               graded_prices: dict = None, sport: str = 'NHL') -> None:
    """Upsert a price snapshot for a rookie card in Supabase.

    Merges ``graded_prices`` with any existing graded data for today.

    Args:
        card_name: Full CardName string used as the ``player`` key.
        fair_value: Raw/ungraded fair value.
        num_sales: Number of raw sales found.
        graded_prices: Optional dict of graded price data.
        sport: Sport code (default ``'NHL'``).
    """
    today = datetime.now().strftime('%Y-%m-%d')
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT graded_data FROM rookie_price_history
                WHERE sport = %s AND player = %s AND season = '' AND date = %s
            """, (sport, card_name, today))
            existing = cur.fetchone()
        merged_graded = (existing['graded_data'] or {}) if existing else {}
        if graded_prices:
            merged_graded.update(graded_prices)
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO rookie_price_history
                    (sport, player, season, date, fair_value, num_sales, graded_data)
                VALUES (%s, %s, '', %s, %s, %s, %s)
                ON CONFLICT (sport, player, season, date) DO UPDATE SET
                    fair_value  = EXCLUDED.fair_value,
                    num_sales   = EXCLUDED.num_sales,
                    graded_data = EXCLUDED.graded_data
            """, (sport, card_name, today,
                  round(float(fair_value), 2), int(num_sales),
                  json.dumps(merged_graded)))


# Backward-compat alias
append_yg_price_history = append_rookie_price_history


def load_rookie_price_history(card_name=None, sport: str = 'NHL') -> list | dict:
    """Load rookie card price history from Supabase.

    Args:
        card_name: If provided, return the price snapshot list for this card.
            Pass ``None`` to return the full history dict keyed by card name.
        sport: Sport code (default ``'NHL'``).

    Returns:
        When ``card_name`` is given: list of snapshot dicts.
        When ``card_name`` is ``None``: full history dict keyed by card name.
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if card_name:
                cur.execute("""
                    SELECT date, fair_value, num_sales, graded_data
                    FROM rookie_price_history
                    WHERE sport = %s AND player = %s ORDER BY date
                """, (sport, card_name))
                rows = cur.fetchall()
                return [{'date': str(r['date']), 'fair_value': r['fair_value'],
                         'num_sales': r['num_sales'], 'graded': r.get('graded_data') or {}}
                        for r in rows]
            cur.execute("""
                SELECT player, date, fair_value, num_sales, graded_data
                FROM rookie_price_history WHERE sport = %s ORDER BY date
            """, (sport,))
            rows = cur.fetchall()
    result: dict = {}
    for r in rows:
        result.setdefault(r['player'], []).append({
            'date': str(r['date']), 'fair_value': r['fair_value'],
            'num_sales': r['num_sales'], 'graded': r.get('graded_data') or {}
        })
    return result


# Backward-compat alias
load_yg_price_history = load_rookie_price_history


def append_rookie_portfolio_snapshot(total_value: float, total_cards: int,
                                     avg_value: float, cards_scraped: int,
                                     sport: str = 'NHL') -> None:
    """Upsert a daily rookie market portfolio snapshot in Supabase.

    Args:
        total_value: Aggregate fair value of all rookie cards.
        total_cards: Total number of rookie cards tracked.
        avg_value: Average fair value per card.
        cards_scraped: Number of cards with fresh price data in this run.
        sport: Sport code (default ``'NHL'``).
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO rookie_portfolio_history
                    (sport, date, total_value, total_cards, avg_value, cards_scraped)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (sport, date) DO UPDATE SET
                    total_value   = EXCLUDED.total_value,
                    total_cards   = EXCLUDED.total_cards,
                    avg_value     = EXCLUDED.avg_value,
                    cards_scraped = EXCLUDED.cards_scraped
            """, (sport, datetime.now().strftime('%Y-%m-%d'),
                  round(float(total_value), 2), int(total_cards),
                  round(float(avg_value), 2), int(cards_scraped)))


# Backward-compat alias
append_yg_portfolio_snapshot = append_rookie_portfolio_snapshot


def load_rookie_portfolio_history(sport: str = 'NHL') -> list:
    """Load daily rookie market portfolio snapshots from Supabase.

    Args:
        sport: Sport code (default ``'NHL'``).

    Returns:
        List of snapshot dicts ordered by date ascending.
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT date, total_value, total_cards, avg_value, cards_scraped
                FROM rookie_portfolio_history WHERE sport = %s ORDER BY date
            """, (sport,))
            rows = cur.fetchall()
    return [{'date': str(r['date']), 'total_value': r['total_value'],
             'total_cards': r['total_cards'], 'avg_value': r['avg_value'],
             'cards_scraped': r['cards_scraped']} for r in rows]


# Backward-compat alias
load_yg_portfolio_history = load_rookie_portfolio_history


def save_rookie_raw_sales(card_name: str, sales: list, sport: str = 'NHL') -> None:
    """Insert raw eBay sales for a rookie card into Supabase.

    Args:
        card_name: Full CardName string stored in the ``player`` column.
        sales: List of sale dicts (each with at least ``sold_date``, ``price_val``).
        sport: Sport code (default ``'NHL'``).
    """
    rows = [
        (sport, card_name, '', s['sold_date'], float(s['price_val']), s.get('title', ''))
        for s in sales
        if s.get('sold_date') and s.get('price_val')
    ]
    if not rows:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            for i in range(0, len(rows), 500):
                execute_values(cur, """
                    INSERT INTO rookie_raw_sales
                        (sport, player, season, sold_date, price_val, title)
                    VALUES %s
                """, rows[i:i + 500])


# Backward-compat alias
save_yg_raw_sales = save_rookie_raw_sales


def load_rookie_raw_sales(card_name=None, sport: str = 'NHL') -> list | dict:
    """Load raw eBay sales for one or all rookie cards from Supabase.

    Args:
        card_name: If provided, return only the sales list for this card.
            Pass ``None`` to return the full dict keyed by card name.
        sport: Sport code (default ``'NHL'``).

    Returns:
        When ``card_name`` is given: list of sale dicts.
        When ``card_name`` is ``None``: full dict keyed by card name.
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if card_name:
                cur.execute("""
                    SELECT sold_date, price_val, title FROM rookie_raw_sales
                    WHERE sport = %s AND player = %s ORDER BY sold_date DESC
                """, (sport, card_name))
                rows = cur.fetchall()
                return [{'sold_date': str(r['sold_date']), 'price_val': r['price_val'],
                         'title': r['title']} for r in rows]
            cur.execute("""
                SELECT player, sold_date, price_val, title FROM rookie_raw_sales
                WHERE sport = %s ORDER BY sold_date DESC
            """, (sport,))
            rows = cur.fetchall()
    result: dict = {}
    for r in rows:
        result.setdefault(r['player'], []).append(
            {'sold_date': str(r['sold_date']), 'price_val': r['price_val'], 'title': r['title']}
        )
    return result


# Backward-compat alias
load_yg_raw_sales = load_rookie_raw_sales


def batch_save_rookie_raw_sales(all_sales_dict: dict, sport: str = 'NHL') -> None:
    """Batch-insert raw eBay sales for multiple rookie cards.

    Args:
        all_sales_dict: Dict mapping card name strings to lists of sale dicts.
        sport: Sport code (default ``'NHL'``).
    """
    rows = []
    for card_name, sales in all_sales_dict.items():
        for s in sales:
            if not s.get('sold_date') or not s.get('price_val'):
                continue
            rows.append((sport, card_name, '', s['sold_date'],
                         float(s['price_val']), s.get('title', '')))
    if not rows:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            for i in range(0, len(rows), 500):
                execute_values(cur, """
                    INSERT INTO rookie_raw_sales
                        (sport, player, season, sold_date, price_val, title)
                    VALUES %s
                """, rows[i:i + 500])


# Backward-compat alias
batch_save_yg_raw_sales = batch_save_rookie_raw_sales


def batch_append_rookie_price_history(updates: dict, sport: str = 'NHL') -> None:
    """Batch-upsert price history for multiple rookie cards in Supabase.

    Args:
        updates: Dict mapping card name strings to update dicts with keys
            ``fair_value``, ``num_sales``, and optional ``graded_prices``.
        sport: Sport code (default ``'NHL'``).
    """
    today = datetime.now().strftime('%Y-%m-%d')
    card_names = list(updates.keys())

    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT player, graded_data FROM rookie_price_history
                WHERE sport = %s AND player = ANY(%s) AND season = '' AND date = %s
            """, (sport, card_names, today))
            existing_rows = cur.fetchall()
        existing_graded = {r['player']: r.get('graded_data') or {} for r in existing_rows}

        rows = []
        for card_name, info in updates.items():
            merged_graded = existing_graded.get(card_name, {})
            if info.get('graded_prices'):
                merged_graded.update(info['graded_prices'])
            rows.append((sport, card_name, '', today,
                         round(float(info['fair_value']), 2), int(info['num_sales']),
                         json.dumps(merged_graded)))

        with conn.cursor() as cur:
            for i in range(0, len(rows), 500):
                execute_values(cur, """
                    INSERT INTO rookie_price_history
                        (sport, player, season, date, fair_value, num_sales, graded_data)
                    VALUES %s
                    ON CONFLICT (sport, player, season, date) DO UPDATE SET
                        fair_value  = EXCLUDED.fair_value,
                        num_sales   = EXCLUDED.num_sales,
                        graded_data = EXCLUDED.graded_data
                """, rows[i:i + 500])


# Backward-compat alias
batch_append_yg_price_history = batch_append_rookie_price_history


def load_rookie_market_timeline(sport: str = 'NHL') -> list:
    """Aggregate all rookie raw sales into a daily market price timeline.

    Args:
        sport: Sport code (default ``'NHL'``).

    Returns:
        List of dicts sorted by ``date`` ascending with ``date``,
        ``avg_price``, ``total_volume``, ``min_price``, ``max_price``.
    """
    all_sales_dict = load_rookie_raw_sales(sport=sport)
    if not all_sales_dict:
        return []

    by_date: dict = {}
    for sales in all_sales_dict.values():
        for s in sales:
            d = s.get('sold_date')
            p = s.get('price_val')
            if d and p:
                by_date.setdefault(str(d), []).append(float(p))

    return [
        {
            'date':         date,
            'avg_price':    round(sum(prices) / len(prices), 2),
            'total_volume': len(prices),
            'min_price':    round(min(prices), 2),
            'max_price':    round(max(prices), 2),
        }
        for date, prices in sorted(by_date.items())
    ]


# Backward-compat alias
load_yg_market_timeline = load_rookie_market_timeline


def load_rookie_cards(sport: str = 'NHL') -> pd.DataFrame:
    """Load the Young Guns master database from Supabase.

    Reconstructs the DataFrame from ``row_data JSONB`` stored per card,
    normalising ``Team``, ``Position``, ``Owned``, ``CostBasis``, and
    ``PurchaseDate`` columns.

    Returns:
        DataFrame of Young Guns cards, or an empty DataFrame when none exist.
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT row_data FROM rookie_cards WHERE sport = %s", (sport,))
            rows = cur.fetchall()
    if not rows:
        return pd.DataFrame()

    records = [r['row_data'] for r in rows]
    df = pd.DataFrame(records)

    # Ensure key columns exist with sensible defaults
    if 'Team' in df.columns:
        df['Team'] = df['Team'].fillna('').str.strip()
    if 'Position' in df.columns:
        df['Position'] = df['Position'].fillna('').str.strip()
    for col, default in [('Owned', 0), ('CostBasis', 0), ('PurchaseDate', '')]:
        if col not in df.columns:
            df[col] = default
    df['Owned'] = pd.to_numeric(df['Owned'], errors='coerce').fillna(0).astype(int)
    df['CostBasis'] = pd.to_numeric(df['CostBasis'], errors='coerce').fillna(0)
    df['PurchaseDate'] = df['PurchaseDate'].fillna('').astype(str)
    return df


def save_rookie_cards(df: pd.DataFrame, sport: str = 'NHL') -> None:
    """Upsert the rookie cards DataFrame to Supabase.

    Serialises each row as ``row_data JSONB``, keyed by ``(sport, player, season)``.

    Args:
        df: Rookie cards DataFrame (as returned by ``load_rookie_cards``).
        sport: Sport code (default ``'NHL'``).
    """
    rows = []
    for rec in df.to_dict('records'):
        player = str(rec.get('PlayerName', ''))
        season = str(rec.get('Season', ''))
        card_name = str(rec.get('CardName', ''))
        cleaned = {k: (None if isinstance(v, float) and pd.isna(v) else v)
                   for k, v in rec.items()}
        rows.append((sport, player, season, card_name, json.dumps(cleaned)))
    with get_db() as conn:
        with conn.cursor() as cur:
            for i in range(0, len(rows), 500):
                execute_values(cur, """
                    INSERT INTO rookie_cards (sport, player, season, card_name, row_data)
                    VALUES %s
                    ON CONFLICT (sport, player, season) DO UPDATE SET
                        card_name  = EXCLUDED.card_name,
                        row_data   = EXCLUDED.row_data,
                        updated_at = NOW()
                """, rows[i:i + 500])


# Backward-compat aliases
load_master_db = load_rookie_cards
save_master_db = save_rookie_cards


# ============================================================
# MARKET ALERTS
# ============================================================
def get_market_alerts(price_history, top_n=5, min_pct=5):
    """Detect cards with significant price swings between the two most recent scrapes.

    Compares the last two price snapshots for each card and flags those whose
    percentage change meets the minimum threshold.  The result is sorted by
    absolute percentage change descending so the largest movers appear first.

    Args:
        price_history: Dict mapping card name strings to lists of snapshot
            dicts (each with a ``fair_value`` key), as returned by
            ``load_yg_price_history()``.
        top_n: Maximum number of gainers and losers to return combined;
            the function returns up to ``top_n * 2`` entries. Defaults to 5.
        min_pct: Minimum absolute percentage change required to include a
            card in the results. Defaults to 5.

    Returns:
        List of dicts, each with keys ``card_name``, ``old_price``,
        ``new_price``, ``pct_change`` (signed float), and ``direction``
        (``"up"`` or ``"down"``).  At most ``top_n * 2`` entries are
        returned.
    """
    alerts = []
    for card_name, entries in price_history.items():
        if len(entries) < 2:
            continue
        latest = entries[-1]
        prev = entries[-2]
        new_p = float(latest.get('fair_value', 0) or 0)
        old_p = float(prev.get('fair_value', 0) or 0)
        if old_p <= 0 or new_p <= 0:
            continue
        pct = ((new_p - old_p) / old_p) * 100
        if abs(pct) < min_pct:
            continue
        alerts.append({
            'card_name': card_name,
            'old_price': old_p,
            'new_price': new_p,
            'pct_change': round(pct, 1),
            'direction': 'up' if pct > 0 else 'down',
        })
    alerts.sort(key=lambda x: abs(x['pct_change']), reverse=True)
    return alerts[:top_n * 2]  # return top gainers + losers


# ============================================================
# CARD OF THE DAY
# ============================================================
def get_card_of_the_day(master_df, nhl_players, price_history, correlation_snapshot=None):
    """Select a featured card of the day from the Young Guns master database.

    Selection priority:

    1. Biggest gainer — card with the largest positive percentage price change
       between its last two scrapes (must be > 5 %).
    2. Most undervalued — card whose actual price is furthest below the
       regression-expected price derived from ``correlation_snapshot``.
    3. Deterministic date hash — a stable pseudo-random pick based on today's
       date, ensuring a consistent result within a calendar day.

    Args:
        master_df: Young Guns master DataFrame (from ``load_master_db``).
            Must contain ``CardName``, ``PlayerName``, ``Team``, and
            ``FairValue`` columns.
        nhl_players: Dict from ``nhl_player_stats.json`` ``players`` key.
        price_history: Full YG price history dict (from
            ``load_yg_price_history()``).
        correlation_snapshot: Optional snapshot dict from
            ``compute_correlation_snapshot``; used for the undervalued
            fallback.  Pass ``None`` to skip that fallback.

    Returns:
        Dict with keys ``card_name``, ``player``, ``team``, ``price``,
        ``pct_change``, ``reason``, and ``stats`` (current-season NHL stats
        dict).  Returns ``None`` when ``master_df`` is empty.
    """
    import hashlib
    today = datetime.now().strftime('%Y-%m-%d')

    # Try biggest gainer first
    best_gainer = None
    best_pct = 0
    for card_name, entries in price_history.items():
        if len(entries) < 2:
            continue
        new_p = float(entries[-1].get('fair_value', 0) or 0)
        old_p = float(entries[-2].get('fair_value', 0) or 0)
        if old_p <= 0 or new_p <= 0:
            continue
        pct = ((new_p - old_p) / old_p) * 100
        if pct > best_pct:
            best_pct = pct
            best_gainer = card_name

    if best_gainer and best_pct > 5:
        row = master_df[master_df['CardName'] == best_gainer]
        player = row.iloc[0]['PlayerName'] if len(row) > 0 else best_gainer
        team = row.iloc[0].get('Team', '') if len(row) > 0 else ''
        price = float(row.iloc[0].get('FairValue', 0)) if len(row) > 0 else 0
        nhl = nhl_players.get(player, {})
        cs = nhl.get('current_season', {})
        return {
            'card_name': best_gainer, 'player': player, 'team': team,
            'price': price, 'pct_change': round(best_pct, 1),
            'reason': f'Biggest gainer today: +{best_pct:.1f}%',
            'stats': cs,
        }

    # Fallback: most undervalued card (use correlation regression)
    if correlation_snapshot:
        pts_corr = correlation_snapshot.get('correlations', {}).get('points_vs_price', {})
        slope = pts_corr.get('slope', 0)
        intercept = pts_corr.get('intercept', 0)
        players_data = correlation_snapshot.get('players', {})
        if slope > 0 and players_data:
            best_value = None
            best_ratio = 0
            for pname, pdata in players_data.items():
                if pdata.get('position') == 'G':
                    continue
                expected = slope * pdata.get('points', 0) + intercept
                actual = pdata.get('price', 0)
                if actual <= 0 or expected <= 0:
                    continue
                ratio = expected / actual  # higher = more undervalued
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_value = pname

            if best_value:
                pdata = players_data[best_value]
                row = master_df[master_df['PlayerName'] == best_value]
                card_name = row.iloc[0]['CardName'] if len(row) > 0 else ''
                return {
                    'card_name': card_name, 'player': best_value,
                    'team': pdata.get('team', ''),
                    'price': pdata.get('price', 0), 'pct_change': 0,
                    'reason': f'Best value: {best_ratio:.1f}x undervalued vs expected',
                    'stats': nhl_players.get(best_value, {}).get('current_season', {}),
                }

    # Final fallback: deterministic pick based on date hash
    if len(master_df) > 0:
        idx = int(hashlib.md5(today.encode()).hexdigest(), 16) % len(master_df)
        row = master_df.iloc[idx]
        player = row.get('PlayerName', '')
        nhl = nhl_players.get(player, {})
        return {
            'card_name': row.get('CardName', ''), 'player': player,
            'team': row.get('Team', ''),
            'price': float(row.get('FairValue', 0) or 0), 'pct_change': 0,
            'reason': 'Featured card',
            'stats': nhl.get('current_season', {}),
        }
    return None


# ============================================================
# TEAM MARKET MULTIPLIER
# ============================================================
def compute_team_multipliers(correlation_snapshot):
    """Compute per-team price premium multipliers relative to regression-expected prices.

    For each team, divides the observed average card price by the price
    predicted by the points-vs-price linear regression stored in
    ``correlation_snapshot``.  A multiplier > 1 indicates a market premium
    for that team; < 1 indicates a discount.

    Args:
        correlation_snapshot: Snapshot dict as produced by
            ``compute_correlation_snapshot``, containing at least
            ``correlations.points_vs_price`` and ``team_premiums``.

    Returns:
        Dict mapping team abbreviation strings to dicts with keys:
        ``actual`` (float), ``expected`` (float), ``multiplier`` (float),
        ``premium_pct`` (float), ``count`` (int), ``country`` (``"CA"`` or
        ``"US"``).  Returns an empty dict when the regression slope is
        non-positive or ``team_premiums`` is absent.
    """
    pts_corr = correlation_snapshot.get('correlations', {}).get('points_vs_price', {})
    slope = pts_corr.get('slope', 0)
    intercept = pts_corr.get('intercept', 0)
    team_premiums = correlation_snapshot.get('team_premiums', {})

    if slope <= 0 or not team_premiums:
        return {}

    multipliers = {}
    for team, data in team_premiums.items():
        avg_pts = data.get('avg_points', 0)
        avg_price = data.get('avg_price', 0)
        if avg_pts <= 0 or avg_price <= 0:
            continue
        expected = slope * avg_pts + intercept
        if expected <= 0:
            expected = 1.0
        mult = avg_price / expected
        multipliers[team] = {
            'actual': round(avg_price, 2),
            'expected': round(expected, 2),
            'multiplier': round(mult, 2),
            'premium_pct': round((mult - 1) * 100, 1),
            'count': data.get('count', 0),
            'country': data.get('country', 'US'),
        }
    return multipliers


# ============================================================
# ROOKIE SEASON IMPACT SCORE
# ============================================================
def compute_impact_scores(master_df, nhl_players, team_multipliers=None):
    """Compute a 0–100 composite Rookie Impact Score for each Young Guns player.

    Only skaters with at least 5 games played are scored.  Each factor is
    normalised across all qualifying players before weighting.

    Score weights:

    * Points pace (pts/GP): 40 %
    * Team market multiplier: 20 %
    * Draft position (lower pick = higher score): 15 %
    * Shooting percentage: 10 %
    * Plus/minus rate (per GP): 15 %

    Undrafted players are assigned a ``draft_overall`` of 300 (worst rank).

    Args:
        master_df: Young Guns master DataFrame (from ``load_master_db``).
            Must contain ``PlayerName`` column.
        nhl_players: Dict from ``nhl_player_stats.json`` ``players`` key.
        team_multipliers: Optional dict from ``compute_team_multipliers``.
            When provided, the team market score uses the player's team
            multiplier; otherwise all team scores default to 1.0.

    Returns:
        Dict mapping player name strings to dicts with keys ``score``
        (float, 0–100), ``breakdown`` (dict with ``pace``, ``team``,
        ``draft``, ``shooting``, ``plusminus``), ``team``, ``points``,
        ``goals``, ``gp``, and ``position``.  Players with insufficient
        data are excluded.
    """
    raw = {}
    for _, row in master_df.iterrows():
        pname = row['PlayerName']
        if pname in raw:
            continue
        nhl = nhl_players.get(pname)
        if not nhl or not nhl.get('current_season'):
            continue
        cs = nhl['current_season']
        bio = nhl.get('bio', {})
        gp = cs.get('games_played', 0)
        if gp < 5:
            continue

        pts_pace = cs.get('points', 0) / gp
        shooting = cs.get('shooting_pct', 0) * 100 if cs.get('shooting_pct', 0) < 1 else cs.get('shooting_pct', 0)
        pm_rate = cs.get('plus_minus', 0) / gp
        draft_pick = bio.get('draft_overall') or 300  # undrafted = 300
        team = nhl.get('current_team', '')

        # Team multiplier score
        tm_score = 1.0
        if team_multipliers and team in team_multipliers:
            tm_score = team_multipliers[team].get('multiplier', 1.0)

        raw[pname] = {
            'pts_pace': pts_pace,
            'shooting': shooting,
            'pm_rate': pm_rate,
            'draft_pick': draft_pick,
            'tm_score': tm_score,
            'team': team,
            'gp': gp,
            'points': cs.get('points', 0),
            'goals': cs.get('goals', 0),
            'position': nhl.get('position', ''),
            'type': nhl.get('type', 'skater'),
        }

    if not raw:
        return {}

    # Normalize each factor to 0-100
    all_pace = [v['pts_pace'] for v in raw.values()]
    all_shoot = [v['shooting'] for v in raw.values()]
    all_pm = [v['pm_rate'] for v in raw.values()]
    all_draft = [v['draft_pick'] for v in raw.values()]
    all_tm = [v['tm_score'] for v in raw.values()]

    def normalize(val, vals, invert=False):
        """Min-max normalise a value to the 0–100 range across a population.

        Args:
            val: The value to normalise.
            vals: Full population of values used to determine the range.
            invert: When ``True``, lower raw values score higher (e.g. draft
                pick number, where 1st overall is best).  Defaults to
                ``False``.

        Returns:
            Float in [0, 100].  Returns 50 when all population values are
            identical (zero range).
        """
        mn, mx = min(vals), max(vals)
        if mx == mn:
            return 50
        n = (val - mn) / (mx - mn) * 100
        return 100 - n if invert else n

    scores = {}
    for pname, v in raw.items():
        if v['type'] != 'skater':
            continue
        pace_n = normalize(v['pts_pace'], all_pace)
        shoot_n = normalize(v['shooting'], all_shoot)
        pm_n = normalize(v['pm_rate'], all_pm)
        draft_n = normalize(v['draft_pick'], all_draft, invert=True)  # lower pick = better
        tm_n = normalize(v['tm_score'], all_tm)

        score = (pace_n * 0.40 + tm_n * 0.20 + draft_n * 0.15 +
                 shoot_n * 0.10 + pm_n * 0.15)

        scores[pname] = {
            'score': round(score, 1),
            'breakdown': {
                'pace': round(pace_n, 1),
                'team': round(tm_n, 1),
                'draft': round(draft_n, 1),
                'shooting': round(shoot_n, 1),
                'plusminus': round(pm_n, 1),
            },
            'team': v['team'],
            'points': v['points'],
            'goals': v['goals'],
            'gp': v['gp'],
            'position': v['position'],
        }
    return scores
