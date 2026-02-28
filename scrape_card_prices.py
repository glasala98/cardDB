import csv
import json
import time
import random
import re
import urllib.parse
import statistics
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except ImportError:
    print("Installing selenium...")
    import subprocess
    subprocess.check_call(['pip', 'install', 'selenium'])
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

try:
    from webdriver_manager.chrome import ChromeDriverManager
    _use_webdriver_manager = True
except ImportError:
    _use_webdriver_manager = False


def is_graded_card(card_name):
    """Return True if the card name contains a PSA or BGS grade marker.

    Args:
        card_name: Full card name string, e.g. "2023-24 Upper Deck - Young Guns #201 - Bedard [PSA 10]".

    Returns:
        True if a PSA or BGS grade is found in card_name, False otherwise.
    """
    return bool(re.search(r'\b(PSA|BGS)\s+\d+(\.\d+)?', card_name, re.IGNORECASE))


def get_grade_info(card_name):
    """Extract the grade label and numeric value from a card name.

    Checks for BGS first (to handle decimal grades like 9.5 before PSA integer
    grades are matched), then falls back to PSA. Supports both bracketed
    "[PSA 10]" and bare "PSA 10" forms.

    Args:
        card_name: Full card name string that may contain a grade marker.

    Returns:
        A tuple (grade_str, grade_num) where grade_str is a string like
        "PSA 9" or "BGS 9.5" and grade_num is the corresponding float.
        Returns (None, None) if no grade is found.
    """
    # Check BGS first (more specific due to decimal grades)
    bgs_match = re.search(r'\[BGS\s+(\d+(?:\.\d+)?)\]', card_name, re.IGNORECASE)
    if bgs_match:
        grade_num = float(bgs_match.group(1))
        return f"BGS {bgs_match.group(1)}", grade_num
    bgs_match = re.search(r'\bBGS\s+(\d+(?:\.\d+)?)\b', card_name, re.IGNORECASE)
    if bgs_match:
        grade_num = float(bgs_match.group(1))
        return f"BGS {bgs_match.group(1)}", grade_num
    # Check PSA (integer grades)
    psa_match = re.search(r'\[PSA\s+(\d+)\]', card_name, re.IGNORECASE)
    if psa_match:
        grade_num = float(psa_match.group(1))
        return f"PSA {int(grade_num)}", grade_num
    psa_match = re.search(r'\bPSA\s+(\d+)\b', card_name, re.IGNORECASE)
    if psa_match:
        grade_num = float(psa_match.group(1))
        return f"PSA {int(grade_num)}", grade_num
    return None, None


def clean_card_name_for_search(card_name):
    """Build a focused eBay sold-listing search query from a card name.

    Parses the card name into player, card number, serial, variant, subset,
    year, and brand components, then assembles them in priority order:
    player > card number > serial > variant > subset > year > brand.

    Strips over 250 known variant/parallel names that do not affect value,
    and appends grade inclusion/exclusion terms for graded cards (e.g.
    '"PSA 9" -BGS -SGC') or grade exclusions for raw cards ('-PSA -BGS').

    Args:
        card_name: Full card name string in the standard format, e.g.
            "2023-24 Upper Deck - Young Guns #201 - Connor Bedard".

    Returns:
        A search query string ready for URL-encoding and submission to eBay.
    """

    grade_str, grade_num = get_grade_info(card_name)

    # Work on a copy without grade/condition brackets
    clean = re.sub(r'\[PSA [^\]]*\]', '', card_name)
    clean = re.sub(r'\[BGS [^\]]*\]', '', clean)
    clean = re.sub(r'\[Passed Pre[^\]]*\]', '', clean)
    clean = re.sub(r'\[Poor to Fair\]', '', clean)
    # Also strip unbracketed grades (from manual entry)
    clean = re.sub(r'\bPSA\s+\d+\b', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'\bBGS\s+\d+(?:\.\d+)?\b', '', clean, flags=re.IGNORECASE)

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

    # Clean card number from brand for mapping check
    brand_clean = re.sub(r'#\S+', '', brand).strip()

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
        if brand_clean == full:
            brand = short
            break

    # --- Extract variant/parallel that affects value ---
    variant = ""
    for part in parts[1:]:
        part_clean = re.sub(r'\[Base\]', '', part).strip()
        part_clean = re.sub(r'#\S+', '', part_clean).strip()
        if part_clean.lower() in ['', 'rookies', 'marquee rookies']:
            continue
        # Keep value-relevant variants — comprehensive list across manufacturers
        for v in [
                   # === Upper Deck ===
                   'Red Prism', 'Arctic Freeze', 'Violet Pixels', 'Emerald Surge',
                   'Seismic Gold', 'Pond Hockey', 'NHL Shield', 'Clear Cut',
                   'Outburst', 'Silver Foil', 'Deluxe', 'Exclusives',
                   'Blue Foil', 'Photo Variation', 'Photo Driven',
                   'Color Flow', 'Orange Yellow Spectrum', 'Blue Luster',
                   'Purple Parallax', 'Hypnosis', 'High Gloss',
                   'French', 'Speckled Rainbow', 'Retro Rainbow',
                   'UD Canvas', 'Clear Cut Acetate',
                   'Fluorescence', 'Fluorescent', 'Buyback',
                   'Printing Plate', 'Black Diamond',
                   # Upper Deck Exclusives & numbered
                   'Young Guns Exclusives', 'High Series Exclusives',
                   'Exclusives Die Cut', 'Update Exclusives',
                   # Upper Deck SP / SPx
                   'Spectrum', 'Holoview FX', 'Finite',
                   # Upper Deck Ice
                   'Ice Premieres', 'Glacial Graphs', 'Ice Gems',
                   # Upper Deck Artifacts
                   'Ruby', 'Emerald', 'Sapphire', 'Copper', 'Silver',
                   # Upper Deck general parallels
                   'Platinum', 'Diamond', 'Onyx',
                   # === Panini Prizm ===
                   'Silver Prizm', 'Red Prizm', 'Blue Prizm', 'Green Prizm',
                   'Gold Prizm', 'Orange Prizm', 'Purple Prizm', 'Pink Prizm',
                   'Black Prizm', 'White Prizm',
                   'Disco', 'Disco Prizm',
                   'Neon Green', 'Neon Orange', 'Neon Pink', 'Neon Blue',
                   'Hyper', 'Hyper Prizm',
                   'Mojo', 'Snakeskin', 'Camo', 'Tiger Stripe',
                   'Zebra', 'Tiger', 'Dragon Scale',
                   'Checkerboard', 'Marble',
                   'Tie-Dye', 'Scope', 'Fast Break',
                   'Ice', 'Cracked Ice', 'Choice',
                   'Stained Glass', 'Color Blast', 'Shimmer',
                   'Flashback', 'No Huddle', 'Fireworks',
                   'Red White Blue', 'Red White & Blue',
                   'Black Gold', 'Black Finite',
                   'Laser', 'Sparkle', 'Wave',
                   # === Panini Select ===
                   'Red Shock', 'Orange Shock', 'Blue Shock',
                   'Green Shock', 'Purple Shock', 'White Shock',
                   'Copper Shock', 'Black Shock',
                   'Red & Yellow Shock', 'Green & Yellow Shock',
                   'Black & Red Shock',
                   'Die-Cut', 'Select Die-Cut',
                   'Tri-Color', 'Tri Color',
                   'Light Blue', 'Courtside', 'Field Level',
                   'Purple Die-Cut', 'Silver Die-Cut', 'Gold Die-Cut',
                   # === Panini Donruss / Optic ===
                   'Optic', 'Optic Holo', 'Optic Rated Rookie',
                   'Red Velocity', 'Blue Velocity', 'Pink Velocity',
                   'Aqua', 'Lime Green', 'Orange Laser',
                   'Purple Stars', 'Blue Hyper', 'Black Velocity',
                   'Press Proof', 'Diamond Kings',
                   'Downtown', 'Kaboom',
                   # === Panini Mosaic ===
                   'Mosaic', 'Mosaic Prizm',
                   'Genesis', 'Reactive Blue', 'Reactive Gold',
                   'Reactive Orange', 'Reactive Green',
                   'Green Fluorescent', 'Pink Fluorescent',
                   'National Pride', 'Stained Glass Mosaic',
                   # === Panini Contenders ===
                   'Cracked Ice Ticket', 'Championship Ticket',
                   'Playoff Ticket', 'Super Bowl Ticket',
                   'Variation', 'Photo Variation',
                   # === Panini general ===
                   'Holo', 'Holofoil', 'Refractor',
                   'Auto', 'Autograph', 'Patch Auto',
                   'RPA', 'Rookie Patch Auto',
                   'Memorabilia', 'Jersey', 'Patch',
                   # === Topps Chrome ===
                   'Refractor', 'Gold Refractor', 'Orange Refractor',
                   'Red Refractor', 'Blue Refractor', 'Green Refractor',
                   'Purple Refractor', 'Pink Refractor', 'Black Refractor',
                   'Sepia Refractor', 'Prism Refractor',
                   'X-Fractor', 'Xfractor',
                   'SuperFractor', 'Super Refractor',
                   'Atomic Refractor', 'Wave Refractor',
                   'Negative Refractor', 'Aqua Refractor',
                   'Rose Gold Refractor', 'Sapphire',
                   'Gold Wave', 'Red Wave', 'Blue Wave',
                   'Speckle', 'Raywave',
                   # === Topps base / flagship ===
                   'Gold', 'Rainbow Foil', 'Rainbow',
                   'Foilboard', 'Silver Pack', 'Silver',
                   'Vintage Stock', 'Independence Day',
                   'Platinum Anniversary', 'Mother\'s Day Pink',
                   'Father\'s Day Blue', 'Memorial Day Camo',
                   'Black', 'Mini', 'Printing Plate',
                   'Clear', 'Silk', 'Wood',
                   # === Topps Finest ===
                   'Finest Refractor', 'Green Refractor', 'Gold Refractor',
                   'Superfractor',
                   # === Topps Bowman ===
                   'Bowman Chrome', 'Chrome Refractor',
                   'Bowman 1st', 'First Bowman',
                   'Shimmer', 'Atomic', 'Mojo Refractor',
                   'Sky Blue', 'Orange', 'Cream',
                   # === Topps Heritage ===
                   'Chrome Heritage', 'Real One Auto',
                   'Red Ink Auto', 'Blue Ink Auto',
                   'French Text', 'Action Variation',
                   'Nickname Variation', 'Error',
                   # === Topps general inserts ===
                   'SP', 'SSP', 'Short Print', 'Image Variation',
                   'Photo Variation', 'Bat Down', 'Rookie Debut',
                   ]:
            if v.lower() in part_clean.lower():
                variant = v
                break
        if variant:
            break

    # --- Extract subset that matters ---
    subset = ""
    for kw in [
               # Upper Deck Hockey
               'Young Guns', 'UD Canvas', 'Prominent Prospects', 'Young Guns Renewed',
               'Young Guns Checklist', 'Dazzlers', 'Day with the Cup',
               'Bootlegs', 'Holoview', 'Finite Rookies', 'Rookie Autographs',
               'UD Portraits', 'Auto Patch', 'Auto Jersey', 'Signature Fabrics',
               'License to Ice', 'GR8 Moments', 'Cranked Up',
               'French Connection', 'Program of Excellence', 'UD Game Jersey',
               'Rookie Materials', 'Rookie Breakouts', 'Star Rookies',
               # Panini inserts
               'Concourse', 'Premier Level', 'Club Level', 'Field Level',
               'Courtside', 'Rated Rookie', 'Rated Rookies',
               'Rookie Ticket', 'Contenders Rookie', 'MVP',
               'Downtown', 'Kaboom', 'Case Hit',
               'Net Marvels', 'Color Blast', 'No Huddle',
               # Topps inserts
               'Rookie Debut', '1st Edition', 'Chrome Rookie',
               'Bowman 1st', 'Heritage Rookie', 'Finest Rookie',
               'All-Star Rookie', 'Future Stars', 'Rookie Cup',
               ]:
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

    # Add serial number to search for numbered cards (/99, /25, etc.)
    # Sellers consistently include this in titles, so it filters out base cards and lots.
    # Falls back to broader search automatically if no results found.
    serial = extract_serial_run(clean)
    if serial:
        query_parts.append(f'/{serial}')

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
        if grade_str.upper().startswith('BGS'):
            bgs_grades = ['6', '7', '7.5', '8', '8.5', '9', '9.5', '10']
            current = grade_str.split()[-1]
            for g in bgs_grades:
                if g != current:
                    search_term += f' -"BGS {g}"'
            search_term += ' -PSA -SGC'
        else:
            other_grades = [g for g in range(1, 11) if g != int(grade_num)]
            for g in other_grades:
                search_term += f' -"PSA {g} "'
            search_term += ' -BGS -SGC'
    else:
        search_term = f"{search_term} -PSA -BGS -SGC -graded"

    return search_term.strip()


def create_driver():
    """Create a headless Chrome WebDriver with memory-saving and anti-detection flags.

    Launches Chrome in headless mode with flags that reduce RAM usage on
    low-resource servers (--no-zygote, --disable-background-networking, etc.)
    and spoof the user-agent to avoid bot-detection. Uses webdriver-manager
    to auto-download ChromeDriver when available, otherwise falls back to the
    system-installed driver.

    Returns:
        A configured selenium.webdriver.Chrome instance ready for use.
    """
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1280,720')
    options.add_argument('--disable-extensions')
    options.add_argument('--ignore-certificate-errors')
    options.add_argument('--allow-running-insecure-content')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    # Memory-saving flags for low-RAM servers
    options.add_argument('--no-zygote')
    options.add_argument('--disable-background-networking')
    options.add_argument('--disable-sync')
    options.add_argument('--disable-translate')
    options.add_argument('--disable-default-apps')
    options.add_argument('--disable-software-rasterizer')
    options.add_argument('--disable-crash-reporter')
    options.add_argument('--mute-audio')
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    if _use_webdriver_manager:
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)
    return webdriver.Chrome(options=options)


def title_matches_grade(title, grade_str, grade_num):
    """Verify that a listing title matches the expected grade exactly.

    For graded cards, confirms the title contains the target grade and rejects
    titles that contain any other grade from the same grading company (to filter
    out mixed-grade lots). For raw cards, rejects titles that mention any
    grading service (PSA, BGS, SGC, or "graded").

    Args:
        title: eBay listing title string.
        grade_str: Grade label to match, e.g. "PSA 9" or "BGS 9.5". Pass None
            for raw (ungraded) cards.
        grade_num: Numeric grade as a float, e.g. 9.0 or 9.5. Ignored when
            grade_str is None.

    Returns:
        True if the title is a valid comp for the target grade, False otherwise.
    """
    title_upper = title.upper()

    if grade_str:
        if grade_str.upper().startswith('BGS'):
            # BGS matching — handles decimal grades like 9.5
            grade_display = grade_str.split()[-1]
            pattern = rf'BGS\s*{re.escape(grade_display)}(?:\s|$|[^0-9.])'
            if not re.search(pattern, title_upper):
                return False
            other_bgs = re.findall(r'BGS\s*(\d+(?:\.\d+)?)', title_upper)
            for g in other_bgs:
                if float(g) != grade_num:
                    return False
            if re.search(r'\bPSA\b', title_upper):
                return False
            return True
        else:
            # PSA matching
            pattern = rf'PSA\s*{int(grade_num)}(?:\s|$|[^0-9])'
            if not re.search(pattern, title_upper):
                return False
            other_psa = re.findall(r'PSA\s*(\d+)', title_upper)
            for g in other_psa:
                if int(g) != int(grade_num):
                    return False
            if re.search(r'\bBGS\b', title_upper):
                return False
            return True
    else:
        # Raw card - reject if title mentions any grading service
        if re.search(r'\bPSA\b|\bBGS\b|\bSGC\b|\bGRADED\b', title_upper):
            return False
        return True


def build_simplified_query(card_name):
    """Build the stage-3 fallback eBay query: player + card number + serial + year only.

    Drops all parallel, variant, subset, and brand information to cast the
    widest net when stages 1 and 2 return no results. Serial number is kept
    so numbered-card results are not polluted by base-card comps.

    Args:
        card_name: Full card name string in the standard format.

    Returns:
        A simplified search query string with grade exclusion/inclusion terms appended.
    """
    grade_str, grade_num = get_grade_info(card_name)

    clean = re.sub(r'\[.*?\]', '', card_name)
    clean = re.sub(r'\bPSA\s+\d+\b', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'\bBGS\s+\d+(?:\.\d+)?\b', '', clean, flags=re.IGNORECASE)
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

    # Serial number — keep in fallback so /99 comps from other parallels are used
    serial = extract_serial_run(clean)
    serial_str = f'/{serial}' if serial else ''

    # Player (last segment)
    player = ""
    if parts:
        last = parts[-1]
        last = re.sub(r'#\d+/\d+', '', last).strip()
        last = re.sub(r'\(.*?\)', '', last).strip()
        if last:
            player = last

    # Player + card# + serial + year — drop parallel name but keep serial
    query_parts = [p for p in [player, card_num, serial_str, year] if p]
    search_term = ' '.join(query_parts)

    if grade_str:
        search_term = f"{search_term} \"{grade_str}\""
        if grade_str.upper().startswith('BGS'):
            search_term += ' -PSA -SGC'
        else:
            search_term += ' -BGS -SGC'
    else:
        search_term = f"{search_term} -PSA -BGS -SGC -graded"

    return search_term.strip()


def build_set_query(card_name):
    """Build the stage-2 fallback eBay query: player + card number + serial + set + year.

    Drops the parallel/subset name (e.g. "Red Prism") while keeping the base
    set name (e.g. "OPC Platinum") and serial number. Used when the stage-1
    exact query returns no results.

    Args:
        card_name: Full card name string in the standard format.

    Returns:
        A set-level search query string with grade exclusion/inclusion terms appended.
    """
    grade_str, grade_num = get_grade_info(card_name)

    clean = re.sub(r'\[.*?\]', '', card_name)
    clean = re.sub(r'\bPSA\s+\d+\b', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'\bBGS\s+\d+(?:\.\d+)?\b', '', clean, flags=re.IGNORECASE)
    parts = [p.strip() for p in clean.split(' - ')]

    year = ""
    year_match = re.search(r'(\d{4}(?:-\d{2})?)', parts[0] if parts else '')
    if year_match:
        year = year_match.group(1)

    card_num = ""
    num_match = re.search(r'#(\S+)', clean)
    if num_match:
        raw = num_match.group(1)
        if '/' not in raw:
            card_num = '#' + raw

    serial = extract_serial_run(clean)
    serial_str = f'/{serial}' if serial else ''

    player = ""
    if parts:
        last = parts[-1]
        last = re.sub(r'#\d+/\d+', '', last).strip()
        last = re.sub(r'\(.*?\)', '', last).strip()
        if last:
            player = last

    # Extract short brand/set (same mapping as clean_card_name_for_search)
    brand = parts[0] if parts else ""
    brand = re.sub(r'^\d{4}(?:-\d{2})?\s*', '', brand).strip()
    brand = re.sub(r'#\S+', '', brand).strip()
    brand_map = {
        'O-Pee-Chee Platinum': 'OPC Platinum',
        'O-Pee-Chee': 'OPC',
        'Upper Deck Extended Series': 'UD Extended',
        'Upper Deck Series 1': 'Upper Deck Series 1',
        'Upper Deck Series 2': 'Upper Deck Series 2',
    }
    brand = brand_map.get(brand, brand)

    # Player + card# + serial + year + set — no parallel/subset
    query_parts = [p for p in [player, card_num, serial_str, year, brand] if p]
    search_term = ' '.join(query_parts)

    if grade_str:
        search_term = f"{search_term} \"{grade_str}\""
        if grade_str.upper().startswith('BGS'):
            search_term += ' -PSA -SGC'
        else:
            search_term += ' -BGS -SGC'
    else:
        search_term = f"{search_term} -PSA -BGS -SGC -graded"

    return search_term.strip()


def search_ebay_sold(driver, card_name, max_results=240, search_query=None):
    """Scrape eBay completed/sold listings for a card and return structured sale records.

    Navigates to eBay's sold-listing search page sorted by most recent, waits
    for the card-based result layout to load, then iterates over each listing
    to extract title, item price, shipping cost (added to total), sold date,
    listing URL, and thumbnail image URL. Applies title_matches_grade() to
    filter out listings that do not match the target grade.

    Args:
        driver: A Selenium WebDriver instance (should already be created via
            get_driver() or create_driver()).
        card_name: Full card name string used to extract grade info for filtering.
        max_results: Maximum number of sale records to return. Defaults to 240
            (one full eBay results page).
        search_query: Pre-built eBay query string. If None, one is generated via
            clean_card_name_for_search(card_name).

    Returns:
        A list of dicts, each containing:
            - title (str): listing title.
            - item_price (str): formatted item price, e.g. "$12.99".
            - shipping (str): "Free" or formatted shipping cost.
            - price_val (float): total price (item + shipping).
            - sold_date (str or None): ISO date string "YYYY-MM-DD" or None.
            - days_ago (int or None): days since sold, or None if date unknown.
            - listing_url (str): direct URL to the eBay listing.
            - image_url (str): thumbnail image URL, or empty string.
        Returns an empty list on error or if no results are found.
    """

    if search_query is None:
        search_query = clean_card_name_for_search(card_name)
    grade_str, grade_num = get_grade_info(card_name)
    encoded_query = urllib.parse.quote(search_query)

    # eBay sold listings URL, sorted by most recent
    url = f"https://www.ebay.com/sch/i.html?_nkw={encoded_query}&_sacat=0&LH_Complete=1&LH_Sold=1&_sop=13&_ipg=240"

    try:
        driver.get(url)

        # Wait for card-based results to load
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.s-card'))
        )

        sales = []
        items = driver.find_elements(By.CSS_SELECTOR, '.s-card')

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

                # Grab thumbnail image — best-effort, eBay lazy-loads some images
                item_image_url = ''
                try:
                    img_elem = item.find_element(By.CSS_SELECTOR, 'img')
                    for attr in ('src', 'data-src', 'data-defer-img'):
                        val = img_elem.get_attribute(attr) or ''
                        if val and 'ebayimg.com' in val and '.gif' not in val:
                            item_image_url = val
                            break
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
                    'search_url': url,
                    'image_url': item_image_url,
                })

                if len(sales) >= max_results:
                    break
            except Exception:
                continue

        return sales

    except Exception as e:
        print(f"  Error fetching data: {e}")
        return []


def extract_serial_run(text):
    """Extract the print-run number from a card name or listing title.

    Looks for a '/NNN' pattern, as found in numbered card references like
    "#70/99" or "Numbered /25".

    Args:
        text: Any string that may contain a print-run notation.

    Returns:
        The print-run limit as an int (e.g. 99), or None if not found.
    """
    m = re.search(r'/(\d+)', text)
    return int(m.group(1)) if m else None


# Relative value multipliers: how much more/less a serial is worth vs baseline.
# Lower print runs = higher value. These are approximate market ratios.
SERIAL_VALUE = {
    1: 50.0, 5: 12.0, 10: 6.0, 15: 4.0, 25: 2.8,
    35: 2.2, 49: 1.8, 50: 1.7, 75: 1.3, 99: 1.0,
    100: 0.95, 149: 0.75, 150: 0.72, 199: 0.6, 200: 0.58,
    249: 0.5, 250: 0.48, 299: 0.42, 399: 0.35, 499: 0.3,
    599: 0.25, 799: 0.2, 999: 0.15,
}


def get_nearby_serials(serial, n=4):
    """Return the n closest known print-run values to use as comp serials.

    Used in stage-4 fallback when no direct sales exist for the target serial.
    Excludes the target serial itself from results.

    Args:
        serial: The target print-run number (e.g. 99).
        n: Number of nearby serials to return. Defaults to 4.

    Returns:
        A list of up to n ints from SERIAL_VALUE, sorted by proximity to serial.
    """
    all_serials = sorted(SERIAL_VALUE.keys())
    distances = sorted((abs(s - serial), s) for s in all_serials if s != serial)
    return [s for _, s in distances[:n]]


def build_serial_comp_query(card_name, comp_serial):
    """Build an eBay search query targeting a nearby serial print run as a price comp.

    Used in stage-4 fallback to find sales of a different print-run variant of
    the same card (e.g. search for /75 when the target is /99 but has no sales).
    Substitutes comp_serial for the card's own serial in the query.

    Args:
        card_name: Full card name string in the standard format.
        comp_serial: The substitute print-run number to query (e.g. 75).

    Returns:
        A search query string with the comp serial embedded and grade terms appended.
    """
    grade_str, grade_num = get_grade_info(card_name)

    clean = re.sub(r'\[.*?\]', '', card_name)
    clean = re.sub(r'\bPSA\s+\d+\b', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'\bBGS\s+\d+(?:\.\d+)?\b', '', clean, flags=re.IGNORECASE)
    parts = [p.strip() for p in clean.split(' - ')]

    year = ""
    year_match = re.search(r'(\d{4}(?:-\d{2})?)', parts[0] if parts else '')
    if year_match:
        year = year_match.group(1)

    card_num = ""
    num_match = re.search(r'#(\S+)', clean)
    if num_match:
        raw = num_match.group(1)
        if '/' not in raw:
            card_num = '#' + raw

    player = ""
    if parts:
        last = parts[-1]
        last = re.sub(r'#\d+/\d+', '', last).strip()
        last = re.sub(r'\(.*?\)', '', last).strip()
        if last:
            player = last

    brand = parts[0] if parts else ""
    brand = re.sub(r'^\d{4}(?:-\d{2})?\s*', '', brand).strip()
    brand = re.sub(r'#\S+', '', brand).strip()
    brand_map = {
        'O-Pee-Chee Platinum': 'OPC Platinum',
        'O-Pee-Chee': 'OPC',
        'Upper Deck Extended Series': 'UD Extended',
        'Upper Deck Series 1': 'Upper Deck Series 1',
        'Upper Deck Series 2': 'Upper Deck Series 2',
    }
    brand = brand_map.get(brand, brand)

    query_parts = [p for p in [player, card_num, f'/{comp_serial}', year, brand] if p]
    search_term = ' '.join(query_parts)

    if grade_str:
        search_term = f"{search_term} \"{grade_str}\""
        if grade_str.upper().startswith('BGS'):
            search_term += ' -PSA -SGC'
        else:
            search_term += ' -BGS -SGC'
    else:
        search_term = f"{search_term} -PSA -BGS -SGC -graded"

    return search_term.strip()


def serial_multiplier(from_serial, to_serial):
    """Compute the price multiplier to scale a comp serial's price to the target serial.

    Uses the SERIAL_VALUE table of relative market multipliers. Values between
    known entries are linearly interpolated; values outside the table range are
    clamped or extrapolated proportionally.

    Example:
        serial_multiplier(10, 99) returns ~0.167, because a /10 card sells for
        roughly 6x a /99, so dividing by 6 converts a /10 price to a /99 estimate.

    Args:
        from_serial: The print-run of the comp sale (e.g. 10).
        to_serial: The print-run of the target card (e.g. 99).

    Returns:
        A float multiplier. Multiply the comp price by this value to estimate
        the target serial's price.
    """
    if from_serial == to_serial:
        return 1.0

    def get_value(s):
        """Return the relative market value for serial s, interpolating if needed."""
        if s in SERIAL_VALUE:
            return SERIAL_VALUE[s]
        # Interpolate from nearest known values
        keys = sorted(SERIAL_VALUE.keys())
        if s < keys[0]:
            return SERIAL_VALUE[keys[0]]
        if s > keys[-1]:
            return SERIAL_VALUE[keys[-1]] * (keys[-1] / s)
        for i in range(len(keys) - 1):
            if keys[i] <= s <= keys[i + 1]:
                lo, hi = keys[i], keys[i + 1]
                ratio = (s - lo) / (hi - lo)
                return SERIAL_VALUE[lo] + ratio * (SERIAL_VALUE[hi] - SERIAL_VALUE[lo])
        return 1.0

    return get_value(to_serial) / get_value(from_serial)


def adjust_sales_for_serial(sales, target_serial):
    """Filter or price-adjust a sale list to reflect the target serial number.

    Prefers exact-serial matches; if none exist, scales other numbered-card
    prices using serial_multiplier(). Unnumbered (base-card) sales in the list
    are discarded entirely since they represent a different product.

    Adjusted sale dicts receive two extra keys:
        _serial_adjusted (bool): True to flag the record as estimated.
        _original_serial (int): The actual serial from the listing title.

    Args:
        sales: List of sale dicts as returned by search_ebay_sold().
        target_serial: The card's own print-run number as an int, or None to
            skip adjustment and return sales unchanged.

    Returns:
        A list of sale dicts. Returns exact matches only when they exist,
        otherwise returns price-adjusted dicts for all numbered comps found.
        Returns the original sales list unchanged when target_serial is None.
    """
    if not target_serial:
        return sales

    # Separate exact matches from others
    exact = []
    others = []
    for s in sales:
        sale_serial = extract_serial_run(s.get('title', ''))
        if sale_serial == target_serial:
            exact.append(s)
        elif sale_serial:
            # Adjust this sale's price to estimate the target serial value
            mult = serial_multiplier(sale_serial, target_serial)
            adjusted = dict(s)
            adjusted['price_val'] = round(s['price_val'] * mult, 2)
            adjusted['_serial_adjusted'] = True
            adjusted['_original_serial'] = sale_serial
            others.append(adjusted)
        else:
            # No serial in title — base/non-numbered card.
            # Skip as comp for serial-numbered cards (different product entirely).
            pass

    # If we have exact matches, use only those
    if exact:
        return exact

    # Otherwise use the adjusted others
    return others


def calculate_fair_price(sales, target_serial=None):
    """Calculate a fair market price from a list of recent eBay sales.

    Steps:
      1. Optionally filters/adjusts sales for a numbered card's serial via
         adjust_sales_for_serial().
      2. Removes outliers more than 3x or less than 1/3 of the median price
         (catches lot sales and $0.99 auctions).
      3. Determines trend by comparing average price of the older half of sales
         to the newer half (up/down/stable at ±10% threshold).
      4. Selects the representative price from the 3 most recent sales:
         highest for uptrend, lowest for downtrend, median for stable.

    Args:
        sales: List of sale dicts as returned by search_ebay_sold() or
            adjust_sales_for_serial(). Each dict must have 'price_val' and
            optionally 'days_ago'.
        target_serial: Print-run number of the card, or None for unnumbered cards.
            When provided, sales are first passed through adjust_sales_for_serial().

    Returns:
        A tuple (fair_price, stats) where:
            - fair_price (float): the chosen representative price.
            - stats (dict): summary with keys 'fair_price', 'chosen_sale',
              'chosen_date', 'trend', 'top_3_prices', 'median_all',
              'num_sales', 'outliers_removed', 'min', 'max'.
        Returns (None, {}) if sales is empty or all sales are filtered out.
    """

    if not sales:
        return None, {}

    # Adjust sales for serial number if card is numbered
    if target_serial:
        sales = adjust_sales_for_serial(sales, target_serial)
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


NUM_WORKERS = 10  # Number of parallel Chrome instances

# Thread-local storage for Chrome drivers
_thread_local = threading.local()


def get_driver():
    """Return the thread-local Chrome WebDriver, creating it on first use.

    Each worker thread maintains its own driver instance stored in
    _thread_local.driver. scrape_master_db monkey-patches this function
    to substitute its own faster driver configuration.

    Returns:
        A selenium.webdriver.Chrome instance bound to the calling thread.
    """
    if not hasattr(_thread_local, 'driver'):
        _thread_local.driver = create_driver()
    return _thread_local.driver


DEFAULT_PRICE = 5.00


def process_card(card):
    """Search eBay and compute a fair market price for a single card.

    Executes a 4-stage search with decreasing specificity, stopping as soon
    as any stage returns results:

      Stage 1 — Exact (confidence: high):
          Full query: variant + subset + serial + set + year.
      Stage 2 — Set (confidence: medium):
          Drops parallel/subset name; keeps serial + set + year.
      Stage 3 — Broad (confidence: low):
          Player + card number + serial + year only.
      Stage 4 — Serial comps (confidence: estimated):
          Searches nearby print-run variants (e.g. /75 for a /99 card) and
          adjusts prices via serial_multiplier(). Stage-4 sales are NOT
          written to historical raw_sales.

    A random sleep of 0.5–1.5 s is added before each search to avoid
    rate-limiting.

    Args:
        card: Full card name string, e.g.
            "2023-24 Upper Deck - Young Guns #201 - Connor Bedard".

    Returns:
        A tuple (card_name, result_dict) where result_dict contains:
            - estimated_value (str): formatted price string, e.g. "$12.50".
            - confidence (str): one of 'high', 'medium', 'low', 'estimated', 'none'.
            - stats (dict): output of calculate_fair_price() plus 'confidence' key.
            - raw_sales (list): direct comp sales (stages 1-3 only).
            - search_url (str or None): URL of the successful eBay search.
            - image_url (str or None): thumbnail URL from the first direct sale.
        When no sales are found at any stage, estimated_value defaults to
        $5.00 and confidence is 'none'.
    """
    driver = get_driver()
    time.sleep(random.uniform(0.5, 1.5))

    target_serial = extract_serial_run(card)
    confidence = 'high'
    pricing_sales = []   # used for fair value calculation
    direct_sales = []    # stored historically (direct comps only)

    # Stage 1: full query — variant + subset + serial + set
    pricing_sales = search_ebay_sold(driver, card)

    if not pricing_sales:
        # Stage 2: drop parallel/subset name, keep serial + set
        time.sleep(random.uniform(0.5, 1.0))
        confidence = 'medium'
        pricing_sales = search_ebay_sold(driver, card, search_query=build_set_query(card))

    if not pricing_sales:
        # Stage 3: drop set — player + card# + serial + year only
        time.sleep(random.uniform(0.5, 1.0))
        confidence = 'low'
        pricing_sales = search_ebay_sold(driver, card, search_query=build_simplified_query(card))

    if pricing_sales:
        # Stages 1-3: these are direct comps — store historically
        direct_sales = list(pricing_sales)
    elif target_serial:
        # Stage 4: no direct results found — search nearby serial print runs as comps
        confidence = 'estimated'
        nearby = get_nearby_serials(target_serial)
        for comp_serial in nearby:
            comp_query = build_serial_comp_query(card, comp_serial)
            comp_raw = search_ebay_sold(driver, card, search_query=comp_query)
            if comp_raw:
                for s in comp_raw:
                    adj = dict(s)
                    adj['price_val'] = round(s['price_val'] * serial_multiplier(comp_serial, target_serial), 2)
                    adj['_serial_adjusted'] = True
                    adj['_original_serial'] = comp_serial
                    pricing_sales.append(adj)
                break  # Use first nearby serial that has results
        # direct_sales stays empty — stage 4 comps are NOT stored historically

    if pricing_sales:
        fair_price, stats = calculate_fair_price(pricing_sales, target_serial=target_serial)
        stats['confidence'] = confidence
        # Pick the first real image URL from direct sales (best-confidence listings)
        image_url = next(
            (s.get('image_url') for s in direct_sales if s.get('image_url')),
            None
        )
        return card, {
            'estimated_value': f"${fair_price}",
            'confidence': confidence,
            'stats': stats,
            'raw_sales': direct_sales,
            'search_url': pricing_sales[0].get('search_url', ''),
            'image_url': image_url,
        }
    else:
        return card, {
            'estimated_value': f"${DEFAULT_PRICE}",
            'confidence': 'none',
            'stats': {
                'fair_price': DEFAULT_PRICE,
                'confidence': 'none',
                'chosen_sale': 'No sales found - default estimate',
                'chosen_date': 'N/A',
                'trend': 'unknown',
                'top_3_prices': [],
                'median_all': DEFAULT_PRICE,
                'num_sales': 0,
                'outliers_removed': 0,
                'min': DEFAULT_PRICE,
                'max': DEFAULT_PRICE,
            },
            'raw_sales': [],
            'search_url': None
        }


def main():
    """Run a full one-shot scrape of all cards in hockey_cards.csv.

    Backs up existing data, reads unique card names from hockey_cards.csv,
    scrapes all cards in parallel using NUM_WORKERS Chrome instances, then
    writes two output files:
        - card_prices_results.json: full result dicts keyed by card name.
        - card_prices_summary.csv: one-row-per-card summary with fair value,
          trend, price range, and number of sales.

    Returns:
        Dict mapping card_name to result_dict (same as written to JSON).
    """
    # Backup existing data before full scrape
    try:
        from dashboard_utils import backup_data
        ts = backup_data(label="full-scrape")
        print(f"Backup saved: {ts}")
    except Exception:
        pass

    # Read cards from CSV
    cards = []
    with open('hockey_cards.csv', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            cards.append(row['card_name'])

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
    results = main()
