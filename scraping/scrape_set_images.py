#!/usr/bin/env python3
"""Scrape box front image URLs from TCDB for all sets in card_catalog.

For each distinct (year, set_name, sport) in card_catalog:
  1. Look up the TCDB set listing page for that sport + year
  2. Find matching set by fuzzy name match
  3. Store tcdb_sid + box_image_url in catalog_sets

Box images are at: https://www.tcdb.com/Media/BoxFront/{sid}.jpg

Usage:
    python scraping/scrape_set_images.py               # all sports, last 3 years
    python scraping/scrape_set_images.py --sport NHL   # single sport
    python scraping/scrape_set_images.py --year-from 2015  # from year
    python scraping/scrape_set_images.py --force       # re-fetch even if already stored
"""
import os, sys, re, time, argparse, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from bs4 import BeautifulSoup
from db import get_db

try:
    from curl_cffi.requests import Session as CurlSession
except ImportError:
    CurlSession = None

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

TCDB_BASE = "https://www.tcdb.com"
SPORT_SLUG_TCDB = {
    "NHL": "Hockey",
    "NBA": "Basketball",
    "NFL": "Football",
    "MLB": "Baseball",
}


def _normalize(s: str) -> str:
    """Lowercase, strip punctuation/extra spaces for fuzzy matching."""
    s = s.lower()
    s = re.sub(r"[''']", "", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _best_match(target: str, candidates: list[dict]) -> dict | None:
    """Return the candidate whose name best matches target, or None."""
    t = _normalize(target)
    # Exact match first
    for c in candidates:
        if _normalize(c["set_name"]) == t:
            return c
    # Substring match
    for c in candidates:
        n = _normalize(c["set_name"])
        if t in n or n in t:
            return c
    # Token overlap (≥70%)
    t_words = set(t.split())
    best, best_score = None, 0
    for c in candidates:
        n_words = set(_normalize(c["set_name"]).split())
        if not t_words or not n_words:
            continue
        overlap = len(t_words & n_words) / max(len(t_words), len(n_words))
        if overlap > best_score:
            best_score = overlap
            best = c
    return best if best_score >= 0.7 else None


def tcdb_get_sets(session, sport: str, year: str) -> list[dict]:
    """Fetch all sets for a sport+year from TCDB. Returns [{set_name, sid}]."""
    slug = SPORT_SLUG_TCDB.get(sport, "Hockey")
    start_year = year.split("-")[0]
    url = f"{TCDB_BASE}/ViewAll.cfm/sp/{slug}/year/{start_year}"

    for attempt in range(4):
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code == 429:
                wait = 30 * (2 ** attempt)
                log.warning(f"  TCDB 429 — waiting {wait}s")
                time.sleep(wait)
                continue
            break
        except Exception as e:
            log.warning(f"  TCDB request failed: {e}")
            return []

    if resp.status_code != 200:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    sets, seen = [], set()
    for a in soup.find_all("a", href=True):
        m = re.match(r'^/ViewSet\.cfm/sid/(\d+)/', a["href"])
        if m and a["href"] not in seen:
            seen.add(a["href"])
            sets.append({"set_name": a.get_text(strip=True), "sid": m.group(1)})

    return sets


def run(sports=None, year_from=None, force=False):
    if CurlSession is None:
        log.error("curl_cffi not installed — run: pip install curl_cffi")
        sys.exit(1)

    sports = sports or list(SPORT_SLUG_TCDB.keys())
    current_year = datetime.now().year
    min_year = year_from or (current_year - 3)

    # Load distinct sets from card_catalog that need images
    with get_db() as conn:
        with conn.cursor() as cur:
            if force:
                cur.execute("""
                    SELECT DISTINCT cc.year, cc.set_name, cc.sport
                    FROM card_catalog cc
                    WHERE cc.sport = ANY(%s)
                      AND SPLIT_PART(cc.year, '-', 1) ~ '^\d{4}$'
                      AND SPLIT_PART(cc.year, '-', 1)::int >= %s
                    ORDER BY cc.year DESC, cc.sport, cc.set_name
                """, (sports, min_year))
            else:
                cur.execute("""
                    SELECT DISTINCT cc.year, cc.set_name, cc.sport
                    FROM card_catalog cc
                    LEFT JOIN catalog_sets cs
                        ON cs.year = cc.year AND cs.set_name = cc.set_name AND cs.sport = cc.sport
                    WHERE cc.sport = ANY(%s)
                      AND SPLIT_PART(cc.year, '-', 1) ~ '^\d{4}$'
                      AND SPLIT_PART(cc.year, '-', 1)::int >= %s
                      AND cs.tcdb_sid IS NULL
                    ORDER BY cc.year DESC, cc.sport, cc.set_name
                """, (sports, min_year))
            catalog_sets = cur.fetchall()

    log.info(f"Found {len(catalog_sets):,} sets needing box images")
    if not catalog_sets:
        return

    session = CurlSession(impersonate="chrome110")

    # Group by (sport, year) to minimize TCDB requests
    by_sport_year = {}
    for year, set_name, sport in catalog_sets:
        by_sport_year.setdefault((sport, year), []).append(set_name)

    saved = 0
    for (sport, year), set_names in by_sport_year.items():
        log.info(f"  {sport} {year} — {len(set_names)} sets")
        tcdb_sets = tcdb_get_sets(session, sport, year)
        if not tcdb_sets:
            log.warning(f"    No TCDB sets found for {sport} {year}")
            time.sleep(2)
            continue

        rows = []
        for set_name in set_names:
            match = _best_match(set_name, tcdb_sets)
            if match:
                sid = match["sid"]
                box_url = f"{TCDB_BASE}/Media/BoxFront/{sid}.jpg"
                rows.append((year, set_name, sport, sid, box_url))
            else:
                # Store with NULL image so we don't retry it every run
                rows.append((year, set_name, sport, None, None))

        if rows:
            with get_db() as conn:
                with conn.cursor() as cur:
                    from psycopg2.extras import execute_values
                    execute_values(cur, """
                        INSERT INTO catalog_sets (year, set_name, sport, tcdb_sid, box_image_url, updated_at)
                        VALUES %s
                        ON CONFLICT (year, set_name, sport) DO UPDATE SET
                            tcdb_sid      = EXCLUDED.tcdb_sid,
                            box_image_url = EXCLUDED.box_image_url,
                            updated_at    = NOW()
                    """, rows)
                conn.commit()
            matched = sum(1 for r in rows if r[3])
            saved += matched
            log.info(f"    Saved {matched}/{len(rows)} with images")

        time.sleep(1.5)  # be polite to TCDB

    log.info(f"Done — {saved} box images stored")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sport",     nargs="+", choices=["NHL","NBA","NFL","MLB"])
    parser.add_argument("--year-from", type=int,  default=None, dest="year_from")
    parser.add_argument("--force",     action="store_true")
    args = parser.parse_args()
    run(sports=args.sport, year_from=args.year_from, force=args.force)
