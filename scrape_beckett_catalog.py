#!/usr/bin/env python3
"""
Build the card_catalog table from four sources:

  --source cli       checklistinsider.com       (default, no login, NHL 2022-26)
  --source cbc       cardboardconnection.com    (no login, NHL back to 2019-20)
  --source tcdb      Trading Card Database       (no login, curl_cffi, all eras back to 1900s)
  --source beckett   Beckett OPG                (login required, most complete)

checklistinsider URL structure:
  https://www.checklistinsider.com/hockey-cards/2024-25-hockey-cards  ← year index
  https://www.checklistinsider.com/2024-25-upper-deck-series-1-hockey ← set checklist

cardboardconnection URL structure:
  https://www.cardboardconnection.com/sports-cards-sets/nhl-hockey-cards/2021-2022-hockey-cards  ← year index
  https://www.cardboardconnection.com/2021-22-upper-deck-series-1-hockey-cards                   ← set checklist

Card line format (both CLI sources):
  "42 Connor Bedard - Chicago Blackhawks"
  organized under section headers like "Base Checklist", "Young Guns Checklist"

Beckett login selectors (set BECKETT_EMAIL + BECKETT_PASSWORD in .env):
  #loginEmail  /  #loginPassword  /  #btn_login

Usage:
    python scrape_beckett_catalog.py                         # CLI, NHL, last 5 years
    python scrape_beckett_catalog.py --year 2024-25          # one year
    python scrape_beckett_catalog.py --year-from 2020        # from 2020 to now
    python scrape_beckett_catalog.py --source cbc --year-from 2019  # CBC, NHL 2019-22
    python scrape_beckett_catalog.py --source tcdb --year-from 1990 # TCDB, all 90s+ NHL
    python scrape_beckett_catalog.py --source beckett        # Beckett (needs login)
    python scrape_beckett_catalog.py --debug --dry-run       # inspect without DB writes
    python scrape_beckett_catalog.py --reset                 # clear checkpoint
"""

import os, sys, re, time, random, json, argparse, logging, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("catalog")

# ── Optional Selenium (only needed for Beckett) ──────────────────────────────
def _selenium_available():
    try:
        from selenium import webdriver
        return True
    except ImportError:
        return False

# ── Constants ───────────────────────────────────────────────────────────────
CLI_BASE     = "https://www.checklistinsider.com"
CBC_BASE     = "https://www.cardboardconnection.com"
BECKETT_BASE = "https://www.beckett.com"

SPORT_SLUG_CLI     = {"NHL": "hockey",     "NBA": "basketball", "NFL": "football",  "MLB": "baseball"}
SPORT_SLUG_BECKETT = {"NHL": "hockey",     "NBA": "basketball", "NFL": "football",  "MLB": "baseball"}
SPORT_ID_BECKETT   = {"NHL": 185225,       "NBA": 185226,       "NFL": 185227,      "MLB": 185228}

# cardboardconnection uses full 4-digit years in the index URL path
SPORT_PATH_CBC   = {"NHL": "nhl-hockey-cards",    "NBA": "nba-basketball-cards",
                    "NFL": "nfl-football-cards",   "MLB": "mlb-baseball-cards"}
SPORT_SUFFIX_CBC = {"NHL": "hockey-cards",         "NBA": "basketball-cards",
                    "NFL": "football-cards",        "MLB": "baseball-cards"}

# TCDB uses the sport's display name in the URL
TCDB_BASE       = "https://www.tcdb.com"
SPORT_SLUG_TCDB = {"NHL": "Hockey", "NBA": "Basketball", "NFL": "Football", "MLB": "Baseball"}

CHECKPOINT_FILE = "catalog_checkpoint.json"
DEBUG_DIR       = Path("catalog_debug")

# Friendly headers so sites don't reject us
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

PARALLEL_KEYWORDS = [
    r'/\d+', r'\bsilver\b', r'\bgold\b', r'\bblue\b', r'\bred\b', r'\bgreen\b',
    r'\bprism\b', r'\brefractor\b', r'\bautograph\b', r'\bauto\b',
    r'\bpatch\b', r'\bjsy\b', r'\bjersey\b', r'\brelic\b',
    r'\bspectrum\b', r'\brainbow\b', r'\bsuperfractor\b',
]
ROOKIE_KEYWORDS = [
    r'\byoung guns?\b', r'\brookie\b', r'\brc\b', r'\bfirst editions?\b',
]


# ── Shared helpers ───────────────────────────────────────────────────────────

def infer_flags(variant: str, card_number: str):
    text = f"{variant} {card_number}".lower()
    is_r = any(re.search(k, text) for k in ROOKIE_KEYWORDS)
    is_p = any(re.search(k, text) for k in PARALLEL_KEYWORDS)
    m    = re.search(r'/(\d+)', text)
    return is_r, is_p, int(m.group(1)) if m else None


def infer_brand(set_name: str) -> str:
    sl = set_name.lower()
    if any(x in sl for x in ("upper deck", "o-pee-chee", "opc", "parkhurst", "sp ", "spx", "ultimate", "fleer ultra", "skybox")):
        return "Upper Deck"
    if any(x in sl for x in ("topps", "chrome", "bowman")):
        return "Topps"
    if any(x in sl for x in ("panini", "prizm", "donruss", "contenders", "select", "optic")):
        return "Panini"
    if "leaf"  in sl: return "Leaf"
    if "score" in sl: return "Score"
    return ""


def build_search_query(year, brand, set_name, card_number, player_name, variant) -> str:
    parts = [year, brand or "", set_name]
    if card_number:
        parts.append(card_number)
    parts.append(player_name)
    if variant and variant.lower() not in ("base", ""):
        parts.append(variant)
    return " ".join(p for p in parts if p).strip()


def section_to_variant(section_header: str) -> str:
    """Convert a checklist section header to a clean variant name."""
    h = section_header.lower()
    h = re.sub(r'\s+checklist$', '', h).strip()
    h = re.sub(r'\s+cards?$', '', h).strip()
    return h.title() if h else "Base"


# ════════════════════════════════════════════════════════════════════════════
# SOURCE 1 — checklistinsider.com  (no login, requests + BeautifulSoup)
# ════════════════════════════════════════════════════════════════════════════

def cli_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def cli_get_set_urls(session: requests.Session, sport: str, year: str, debug: bool) -> list[dict]:
    """Fetch the year index page and return all set checklist URLs."""
    slug   = SPORT_SLUG_CLI.get(sport, "hockey")
    url    = f"{CLI_BASE}/{slug}-cards/{year}-{slug}-cards"
    resp   = session.get(url, timeout=15)

    if resp.status_code != 200:
        log.warning(f"  checklistinsider {sport} {year}: HTTP {resp.status_code} — {url}")
        return []

    if debug:
        _save_text(resp.text, f"cli_year_{sport}_{year}")

    soup = BeautifulSoup(resp.text, "html.parser")
    sets = []
    seen = set()

    # Set links follow the pattern /YEAR-SET-NAME-SPORT or /YEAR-SET-NAME-SPORT-CARDS
    year_prefix = year.split("-")[0]  # e.g. "2024" from "2024-25"
    pattern = re.compile(rf'{CLI_BASE}/{year_prefix}', re.IGNORECASE)

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("http"):
            href = CLI_BASE + href
        name = a.get_text(strip=True)
        if pattern.search(href) and name and href not in seen:
            # Skip category/year index pages, only want set-level
            path_parts = href.replace(CLI_BASE, "").strip("/").split("/")
            if len(path_parts) == 1 and name:
                seen.add(href)
                sets.append({"set_name": name, "url": href})

    log.info(f"  checklistinsider {sport} {year}: {len(sets)} sets")
    return sets


def cli_get_cards(session: requests.Session, set_info: dict, sport: str, year: str,
                   debug: bool, source: str = "cli") -> list[dict]:
    """Scrape a checklistinsider set page.

    Card lines live inside <div> elements separated by <br/> tags:
        <div>1 Troy Terry - Anaheim Ducks<br/>2 Jackson LaCombe - Anaheim Ducks<br/>...</div>
    Section headers are <h2>/<h3>/<h4> tags immediately before their card divs.
    We scope parsing to the article content div to avoid picking up navigation items.
    """
    resp = session.get(set_info["url"], timeout=15)
    if resp.status_code != 200:
        log.warning(f"    HTTP {resp.status_code} — {set_info['url']}")
        return []

    if debug:
        safe = re.sub(r'[^a-z0-9]', '_', set_info['set_name'].lower())[:40]
        _save_text(resp.text, f"cli_set_{safe}")

    set_name = set_info["set_name"]
    brand    = infer_brand(set_name)
    soup     = BeautifulSoup(resp.text, "html.parser")
    cards    = []

    # Scope to article content to skip navigation menus
    content = (
        soup.find("div", class_="yuki-article-content")
        or soup.find("div", class_=re.compile(r"entry-content|article-content|post-content"))
        or soup.find("article")
        or soup.body
    )

    # "42 Connor Bedard - Chicago Blackhawks" or "PP-1 Trevor Zegras - Anaheim Ducks"
    card_pat = re.compile(r'^(\S+)\s+(.+?)\s*-\s*(.+)$')
    # Valid card numbers: digits only, or optional 1-5 letter prefix + dash + digits (e.g. PP-1, YG-50, C-10)
    card_num_pat = re.compile(r'^[A-Za-z]{0,5}[-/]?\d+[A-Za-z]?$')

    current_section = "Base"

    def _parse_line(line: str):
        """Parse one card line; returns card dict or None."""
        line = line.strip()
        if not line:
            return None
        m = card_pat.match(line)
        if not m:
            return None
        card_number = m.group(1)
        player_name = m.group(2).strip()
        team        = m.group(3).strip()
        # Card number must look like a real card number (digits / short prefix-number)
        if not card_num_pat.match(card_number):
            return None
        # Player name sanity: at least 3 chars, no 4-digit year, no hobby/pack keywords
        if len(player_name) < 3 or re.search(r'\d{4}', player_name):
            return None
        if re.search(r'\b(hobby|epack|blaster|odds|packs?|box|case|foil|prism|chrome|parallel)\b',
                     player_name, re.I):
            return None
        is_r, is_p, pr = infer_flags(current_section, card_number)
        return {
            "sport": sport, "year": year, "brand": brand, "set_name": set_name,
            "card_number": card_number, "player_name": player_name,
            "team": team, "variant": current_section,
            "print_run": pr, "is_rookie": is_r, "is_parallel": is_p,
            "source": source,
        }

    for el in content.find_all(["h2", "h3", "h4", "div", "li", "p"]):
        # Section headers update current_section
        if el.name in ("h2", "h3", "h4"):
            text = el.get_text(strip=True)
            if re.search(r'(checklist|insert|autograph|parallel|subset)', text, re.I):
                current_section = section_to_variant(text)
            continue

        # For <div> elements, split on <br> tags to get individual card lines
        if el.name == "div":
            # Get text with br → newline, ignore nested divs (process leaf divs only)
            if el.find("div"):
                continue  # skip container divs; their children will be visited individually
            # Replace <br> with newlines then get text
            for br in el.find_all("br"):
                br.replace_with("\n")
            raw = el.get_text()
            for line in raw.split("\n"):
                card = _parse_line(line)
                if card:
                    cards.append(card)
        else:
            # <li> / <p> — each element is one potential card line
            card = _parse_line(el.get_text(strip=True))
            if card:
                cards.append(card)

    if cards:
        log.info(f"    {set_name}: {len(cards)} cards")
    else:
        log.warning(f"    {set_name}: 0 cards found — check --debug HTML")

    return cards


# ════════════════════════════════════════════════════════════════════════════
# SOURCE 2 — cardboardconnection.com  (no login, same format as CLI)
# ════════════════════════════════════════════════════════════════════════════

def cbc_expand_year(year: str) -> str:
    """Convert year to CBC URL format.
    '2021-22' → '2021-2022' (hockey season)
    '2009'    → '2009'       (calendar year sports like MLB/NFL/NBA)
    """
    if "-" not in year:
        return year
    start, end = year.split("-")
    return f"{start}-{start[:2]}{end}"


def cbc_get_set_urls(session: requests.Session, sport: str, year: str, debug: bool) -> list[dict]:
    """Fetch the cardboardconnection year index and return all set checklist URLs."""
    slug       = SPORT_PATH_CBC.get(sport, "nhl-hockey-cards")
    suffix     = SPORT_SUFFIX_CBC.get(sport, "hockey-cards")
    full_year  = cbc_expand_year(year)
    url        = f"{CBC_BASE}/sports-cards-sets/{slug}/{full_year}-{suffix}"
    resp       = session.get(url, timeout=15)

    if resp.status_code != 200:
        log.warning(f"  cardboardconnection {sport} {year}: HTTP {resp.status_code} — {url}")
        return []

    if debug:
        _save_text(resp.text, f"cbc_year_{sport}_{year}")

    soup = BeautifulSoup(resp.text, "html.parser")
    sets = []
    seen = set()

    year_prefix = year.split("-")[0]   # "2021" from "2021-22"
    pattern = re.compile(rf'{re.escape(CBC_BASE)}/{year_prefix}', re.IGNORECASE)

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("http"):
            href = CBC_BASE + href
        name = a.get_text(strip=True)
        if pattern.search(href) and name and href not in seen:
            path_parts = href.replace(CBC_BASE, "").strip("/").split("/")
            if len(path_parts) == 1:
                seen.add(href)
                sets.append({"set_name": name, "url": href})

    log.info(f"  cardboardconnection {sport} {year}: {len(sets)} sets")
    return sets


def cbc_get_cards(session: requests.Session, set_info: dict, sport: str, year: str,
                   debug: bool) -> list[dict]:
    """Scrape a cardboardconnection set page (same format as checklistinsider)."""
    return cli_get_cards(session, set_info, sport, year, debug, source="cbc")


# ════════════════════════════════════════════════════════════════════════════
# SOURCE 3 — Trading Card Database  (no login, curl_cffi bypasses Cloudflare)
# ════════════════════════════════════════════════════════════════════════════

def tcdb_session():
    try:
        from curl_cffi import requests as cffi_requests
        sess = cffi_requests.Session(impersonate="chrome124")
        sess.headers.update(HEADERS)
        return sess
    except ImportError:
        raise ImportError("curl_cffi required for --source tcdb: pip install curl_cffi")


def tcdb_get_set_urls(session, sport: str, year: str, debug: bool) -> list[dict]:
    """Fetch TCDB year index and return all set checklist URLs."""
    slug       = SPORT_SLUG_TCDB.get(sport, "Hockey")
    start_year = year.split("-")[0]   # "1993-94" → "1993"
    url        = f"{TCDB_BASE}/ViewAll.cfm/sp/{slug}/year/{start_year}"

    # Retry up to 4 times on 429 with exponential backoff
    for attempt in range(4):
        resp = session.get(url, timeout=15)
        if resp.status_code == 429:
            wait = 30 * (2 ** attempt)
            log.warning(f"  TCDB 429 — waiting {wait}s before retry {attempt+1}/4")
            time.sleep(wait)
            continue
        break

    if resp.status_code != 200:
        log.warning(f"  TCDB {sport} {year}: HTTP {resp.status_code} — {url}")
        return []

    if debug:
        _save_text(resp.text, f"tcdb_year_{sport}_{year}")

    soup = BeautifulSoup(resp.text, "html.parser")
    sets = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        name = a.get_text(strip=True)
        # Set links: /ViewSet.cfm/sid/4938/1993-94-Donruss
        m = re.match(r'^/ViewSet\.cfm/sid/(\d+)/(.+)$', href)
        if m and name and href not in seen:
            seen.add(href)
            sid   = m.group(1)
            slug_ = m.group(2)
            sets.append({
                "set_name": name,
                "url": f"{TCDB_BASE}/Checklist.cfm/sid/{sid}/{slug_}",
                "sid": sid,
            })

    log.info(f"  TCDB {sport} {year}: {len(sets)} sets")
    return sets


_CARD_NUM_PAT = re.compile(r'^\d+[A-Za-z]?$|^[A-Z]{1,5}[-/]?\d+[A-Za-z]?$')


def _parse_tcdb_row(cells: list[str]):
    """Dynamically find card_num / player_name / team from a TCDB table row.

    TCDB adds different numbers of empty icon/checkbox cells depending on login state
    and set type.  We locate the first cell matching a card-number pattern, then take
    the next two non-empty cells as player_name and team respectively.
    """
    for i, cell in enumerate(cells):
        if not _CARD_NUM_PAT.match(cell):
            continue
        # Collect the next two non-empty cells
        non_empty = [c for c in cells[i + 1:] if c]
        if not non_empty:
            continue
        player_name = non_empty[0]
        team        = non_empty[1] if len(non_empty) > 1 else ""
        # Quick sanity: player names are text, not digits or very short
        if len(player_name) < 2 or re.search(r'^\d+$', player_name):
            continue
        return cell, player_name, team
    return None, None, None


def tcdb_get_cards(session, set_info: dict, sport: str, year: str, debug: bool) -> list[dict]:
    """Scrape all pages of a TCDB set checklist.

    Pages are 100 cards each; pagination via ?PageIndex=N.
    Cell layout varies by set/login state — use _parse_tcdb_row() to handle dynamically.
    """
    set_name = set_info["set_name"]
    brand    = infer_brand(set_name)
    cards    = []
    page     = 1

    while True:
        url  = f"{set_info['url']}?PageIndex={page}"
        for attempt in range(4):
            resp = session.get(url, timeout=15)
            if resp.status_code == 429:
                wait = 20 * (2 ** attempt)
                log.warning(f"    429 on {set_name} p{page} — waiting {wait}s (attempt {attempt+1}/4)")
                time.sleep(wait)
                continue
            break
        if resp.status_code != 200:
            break

        if debug and page == 1:
            safe = re.sub(r'[^a-z0-9]', '_', set_name.lower())[:40]
            _save_text(resp.text, f"tcdb_set_{safe}")

        soup = BeautifulSoup(resp.text, "html.parser")
        page_cards = 0

        for row in soup.find_all("tr"):
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cells) < 5:
                continue
            card_num, player_name, team = _parse_tcdb_row(cells)
            if not card_num or not player_name:
                continue
            if re.search(r'\d{4}', player_name):
                continue

            is_r, is_p, pr = infer_flags("Base", card_num)
            cards.append({
                "sport": sport, "year": year, "brand": brand, "set_name": set_name,
                "card_number": card_num, "player_name": player_name, "team": team,
                "variant": "Base", "print_run": pr, "is_rookie": is_r, "is_parallel": is_p,
                "source": "tcdb",
            })
            page_cards += 1

        # Stop if no next page link or no cards found
        has_next = any(
            f"PageIndex={page + 1}" in (a.get("href") or "")
            for a in soup.find_all("a", href=True)
        )
        if not has_next or page_cards == 0:
            break
        page += 1
        time.sleep(random.uniform(0.05, 0.15))

    if cards:
        log.info(f"    {set_name}: {len(cards)} cards ({page}p)")
    else:
        log.warning(f"    {set_name}: 0 cards — check --debug HTML")

    return cards


# ════════════════════════════════════════════════════════════════════════════
# SOURCE 4 — Beckett OPG  (login required, Selenium)
# ════════════════════════════════════════════════════════════════════════════

def _make_driver(headless=True):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        svc = Service(ChromeDriverManager().install())
    except ImportError:
        svc = Service()

    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument("--window-size=1280,900")
    opts.add_argument(f"user-agent={HEADERS['User-Agent']}")
    driver = webdriver.Chrome(service=svc, options=opts)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"}
    )
    return driver


def beckett_login(driver, email: str, password: str, debug: bool):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException

    log.info("Logging in to Beckett...")
    driver.get(f"{BECKETT_BASE}/login")
    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "loginEmail")))

    # Dismiss cookie consent banner if present
    try:
        accept = driver.find_element(By.CSS_SELECTOR,
            "#onetrust-accept-btn-handler, button[id*='accept'], button[class*='accept-all']")
        accept.click()
        time.sleep(0.5)
    except NoSuchElementException:
        pass
    # Use JS click to bypass any remaining overlay
    driver.find_element(By.ID, "loginEmail").send_keys(email)
    driver.find_element(By.ID, "loginPassword").send_keys(password)
    time.sleep(0.4)
    driver.execute_script("document.getElementById('btn_login').click()")

    try:
        WebDriverWait(driver, 15).until(EC.url_changes(f"{BECKETT_BASE}/login"))
        log.info(f"Logged in — {driver.current_url}")
    except TimeoutException:
        if debug:
            _save_text(driver.page_source, "beckett_login_fail")
        raise RuntimeError("Beckett login failed — check BECKETT_EMAIL / BECKETT_PASSWORD in .env")


def beckett_get_set_urls(driver, sport: str, year: str, debug: bool) -> list[dict]:
    from selenium.webdriver.common.by import By

    slug      = SPORT_SLUG_BECKETT.get(sport, "hockey")
    sport_id  = SPORT_ID_BECKETT.get(sport, 185225)
    # Year on Beckett is just the first 4 digits: "2021-22" → "2021"
    year_num  = year.split("-")[0]
    url = f"{BECKETT_BASE}/sets?sport={sport_id}&year={year_num}"
    driver.get(url)
    time.sleep(random.uniform(2.0, 3.0))

    if debug:
        _save_text(driver.page_source, f"beckett_year_{sport}_{year}")

    sets = []
    seen = set()
    # Set links follow: /hockey/2021-22/set-slug  OR  /hockey/2021/set-slug
    pat = re.compile(rf'/{re.escape(slug)}/({re.escape(year)}|{re.escape(year_num)})/([^/?#]+)/?$')

    for link in driver.find_elements(By.TAG_NAME, "a"):
        href = link.get_attribute("href") or ""
        name = link.text.strip()
        m = pat.search(href)
        if m and name and href not in seen:
            seen.add(href)
            sets.append({"set_name": name, "url": href})

    log.info(f"  Beckett {sport} {year}: {len(sets)} sets")
    return sets


def beckett_get_cards(driver, set_info: dict, sport: str, year: str, debug: bool) -> list[dict]:
    from selenium.webdriver.common.by import By
    from selenium.common.exceptions import NoSuchElementException

    driver.get(set_info["url"])
    time.sleep(random.uniform(1.5, 2.5))

    set_name = set_info["set_name"]
    brand    = infer_brand(set_name)

    if debug:
        _save_text(driver.page_source, f"beckett_set_{re.sub(r'[^a-z0-9]','_',set_name.lower())[:40]}")

    cards = []
    page  = 1

    while True:
        rows = driver.find_elements(
            By.CSS_SELECTOR,
            "table.checklistTable tr, #checklist tr, table tr"
        )
        for row in rows:
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) < 2:
                continue
            texts = [c.text.strip() for c in cells]
            card_number = texts[0].lstrip("#")
            player_name = texts[1] if len(texts) > 1 else ""
            team        = texts[2] if len(texts) > 2 and len(texts[2]) < 35 else ""
            variant     = texts[3] if len(texts) > 3 else "Base"
            if not player_name or not re.search(r'[A-Za-z]{2,}', player_name):
                continue
            is_r, is_p, pr = infer_flags(variant, card_number)
            cards.append({
                "sport": sport, "year": year, "brand": brand, "set_name": set_name,
                "card_number": card_number, "player_name": player_name,
                "team": team, "variant": variant or "Base",
                "print_run": pr, "is_rookie": is_r, "is_parallel": is_p,
                "source": "beckett",
            })

        try:
            nxt = driver.find_element(
                By.CSS_SELECTOR, "a.next, a[aria-label='Next'], .pagination .next a"
            )
            if "disabled" in (nxt.get_attribute("class") or ""):
                break
            nxt.click()
            time.sleep(random.uniform(1.2, 2.0))
            page += 1
        except NoSuchElementException:
            break

    if cards:
        log.info(f"    {set_name}: {len(cards)} cards ({page}p)")
    else:
        log.warning(f"    {set_name}: 0 cards — check --debug HTML for selector adjustments")

    return cards


# ── DB upsert ────────────────────────────────────────────────────────────────

def upsert_cards(cards: list[dict], dry_run: bool) -> int:
    if not cards:
        return 0
    if dry_run:
        for c in cards[:5]:
            log.info(f"  [dry-run]  #{c['card_number']:5s}  {c['player_name']:<25s}  {c['variant']}  ({c['set_name']})")
        if len(cards) > 5:
            log.info(f"  [dry-run]  ... and {len(cards)-5} more")
        return len(cards)

    from db import get_db
    from psycopg2.extras import execute_values

    sql = """
        INSERT INTO card_catalog
            (sport, year, brand, set_name, card_number, player_name,
             team, variant, print_run, is_rookie, is_parallel,
             source, search_query, updated_at)
        VALUES %s
        ON CONFLICT (sport, year, set_name, card_number, player_name, variant)
        DO UPDATE SET
            brand        = EXCLUDED.brand,
            team         = EXCLUDED.team,
            print_run    = EXCLUDED.print_run,
            is_rookie    = EXCLUDED.is_rookie,
            is_parallel  = EXCLUDED.is_parallel,
            search_query = EXCLUDED.search_query,
            source       = EXCLUDED.source,
            updated_at   = NOW()
    """
    seen = set()
    rows = []
    for c in cards:
        key = (c["sport"], c["year"], c["set_name"], c["card_number"], c["player_name"], c["variant"])
        if key in seen:
            continue
        seen.add(key)
        sq = build_search_query(c["year"], c["brand"], c["set_name"],
                                c["card_number"], c["player_name"], c["variant"])
        rows.append((
            c["sport"], c["year"], c["brand"], c["set_name"], c["card_number"],
            c["player_name"], c["team"], c["variant"], c["print_run"],
            c["is_rookie"], c["is_parallel"], c["source"], sq,
        ))

    with get_db() as conn:
        cur = conn.cursor()
        execute_values(cur, sql, rows,
                       template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())",
                       page_size=500)
        conn.commit()
    return len(cards)


# ── Checkpoint ───────────────────────────────────────────────────────────────

def load_checkpoint() -> set:
    if Path(CHECKPOINT_FILE).exists():
        return set(json.loads(Path(CHECKPOINT_FILE).read_text()).get("done", []))
    return set()


_checkpoint_lock = threading.Lock()
_thread_local    = threading.local()


def save_checkpoint(done: set):
    with _checkpoint_lock:
        Path(CHECKPOINT_FILE).write_text(json.dumps({"done": sorted(done)}, indent=2))


def _thread_session(source: str):
    """Per-thread session cache — avoids creating a new session on every task."""
    if not hasattr(_thread_local, "session") or getattr(_thread_local, "source", None) != source:
        _thread_local.session = tcdb_session() if source == "tcdb" else cli_session()
        _thread_local.source  = source
    return _thread_local.session


def _save_text(text: str, name: str):
    DEBUG_DIR.mkdir(exist_ok=True)
    path = DEBUG_DIR / f"{name}_{datetime.now().strftime('%H%M%S')}.html"
    path.write_text(text, encoding="utf-8")
    log.debug(f"  Saved debug HTML → {path}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Populate card_catalog from checklistinsider or Beckett")
    ap.add_argument("--source",     default="cli", choices=["cli", "cbc", "tcdb", "beckett"],
                    help="cli = checklistinsider.com (no login, 2022+); cbc = cardboardconnection.com (no login, 2009+); tcdb = tradingcarddatabase.com (no login, all eras); beckett = Beckett OPG (login required)")
    ap.add_argument("--sport",      default="NHL", choices=["NHL","NBA","NFL","MLB"])
    ap.add_argument("--year",       help="Single year e.g. 2024-25")
    ap.add_argument("--year-from",  type=int, help="Start year (default: 5 years ago)")
    ap.add_argument("--no-headless",action="store_true", help="Show browser (Beckett only)")
    ap.add_argument("--debug",      action="store_true", help="Save HTML snapshots to catalog_debug/")
    ap.add_argument("--dry-run",    action="store_true", help="Print cards without writing to DB")
    ap.add_argument("--reset",      action="store_true", help="Clear checkpoint and restart")
    ap.add_argument("--workers",    type=int, default=1,
                    help="Parallel workers for TCDB set fetching (default 1; try 4 for ~3-4x speedup)")
    args = ap.parse_args()

    if args.reset:
        Path(CHECKPOINT_FILE).unlink(missing_ok=True)
        log.info("Checkpoint cleared.")

    # Build year list
    # MLB/NFL/NBA use calendar years on CBC/CLI; NHL uses season format (2021-22)
    CALENDAR_YEAR_SPORTS = {"MLB", "NFL", "NBA"}
    if args.year:
        years = [args.year]
    else:
        cur   = datetime.now().year
        start = args.year_from or (cur - 5)
        if args.sport in CALENDAR_YEAR_SPORTS and args.source in ("cli", "cbc"):
            years = [str(y) for y in range(start, cur + 1)]
        else:
            years = [f"{y}-{str(y+1)[-2:]}" for y in range(start, cur + 1)]

    log.info(f"Source: {args.source.upper()}  |  Sport: {args.sport}  |  Years: {years}")

    done   = load_checkpoint()
    total  = 0
    driver = None

    # Set up Beckett driver + login if needed
    if args.source == "beckett":
        email    = os.getenv("BECKETT_EMAIL")
        password = os.getenv("BECKETT_PASSWORD")
        if not email or not password:
            log.error("Set BECKETT_EMAIL and BECKETT_PASSWORD in .env for Beckett source")
            sys.exit(1)
        driver = _make_driver(headless=not args.no_headless)
        beckett_login(driver, email, password, args.debug)

    if args.source in ("cli", "cbc"):
        session = cli_session()
    elif args.source == "tcdb":
        session = tcdb_session()
    else:
        session = None

    def _run_set(src, set_info, sport, year, debug, dry_run):
        """Fetch + upsert one set.  Safe to call from a worker thread (TCDB only)."""
        # Stagger worker startup to avoid simultaneous requests
        time.sleep(random.uniform(0.0, 0.4))
        sess = _thread_session(src)
        if src == "cli":
            cards = cli_get_cards(sess, set_info, sport, year, debug)
        elif src == "cbc":
            cards = cbc_get_cards(sess, set_info, sport, year, debug)
        else:   # tcdb
            cards = tcdb_get_cards(sess, set_info, sport, year, debug)
        return upsert_cards(cards, dry_run=dry_run)

    try:
        for year in years:
            if args.source == "cli":
                sets = cli_get_set_urls(session, args.sport, year, args.debug)
            elif args.source == "cbc":
                sets = cbc_get_set_urls(session, args.sport, year, args.debug)
            elif args.source == "tcdb":
                sets = tcdb_get_set_urls(session, args.sport, year, args.debug)
                time.sleep(random.uniform(0.5, 1.2))   # pace year-index requests
            else:
                sets = beckett_get_set_urls(driver, args.sport, year, args.debug)

            pending = [s for s in sets
                       if f"{args.source}|{args.sport}|{year}|{s['set_name']}" not in done]

            use_parallel = args.source == "tcdb" and args.workers > 1 and len(pending) > 1

            if use_parallel:
                # ── Parallel TCDB set fetching ────────────────────────────────
                with ThreadPoolExecutor(max_workers=args.workers) as pool:
                    fut_map = {
                        pool.submit(
                            _run_set, args.source, s, args.sport, year, args.debug, args.dry_run
                        ): s
                        for s in pending
                    }
                    for fut in as_completed(fut_map):
                        s   = fut_map[fut]
                        key = f"{args.source}|{args.sport}|{year}|{s['set_name']}"
                        try:
                            n = fut.result()
                        except Exception as e:
                            log.error(f"  Error on {key}: {e}")
                            n = 0
                        total += n
                        done.add(key)
                        if not args.dry_run:
                            save_checkpoint(done)
            else:
                # ── Sequential (non-TCDB or workers=1) ───────────────────────
                for set_info in pending:
                    key = f"{args.source}|{args.sport}|{year}|{set_info['set_name']}"
                    try:
                        if args.source == "beckett":
                            cards = beckett_get_cards(driver, set_info, args.sport, year, args.debug)
                            n = upsert_cards(cards, dry_run=args.dry_run)
                        else:
                            n = _run_set(args.source, set_info, args.sport, year, args.debug, args.dry_run)
                        total += n
                        done.add(key)
                        if not args.dry_run:
                            save_checkpoint(done)
                        if args.source == "tcdb":
                            time.sleep(random.uniform(0.1, 0.25))
                    except Exception as e:
                        log.error(f"  Error on {key}: {e}")
                        if args.debug and driver:
                            _save_text(driver.page_source,
                                       f"err_{re.sub(r'[^a-z0-9]','_',key.lower())[:50]}")

        log.info(f"\nDone — {total:,} cards {'(dry-run, not saved)' if args.dry_run else 'upserted into card_catalog'}")

    finally:
        if driver:
            driver.quit()


if __name__ == "__main__":
    main()
