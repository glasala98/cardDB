#!/usr/bin/env python3
"""
Scrape PSA population reports and store in psa_population table.

PSA pop counts are the primary supply-side signal for graded card pricing.
A PSA 10 with 50 copies is worth far more than one with 5,000 copies.

Approach:
  1. Load priced cards from card_catalog (elite/staple tier by default)
  2. Search PSA API for matching card specification
  3. Fetch per-grade population counts
  4. Upsert into psa_population table

Requirements:
  PSA_API_KEY env var — free API key from https://api.psacard.com/

Usage:
    python scrape_psa_pop.py                        # elite + staple tier
    python scrape_psa_pop.py --tier premium         # specific tier
    python scrape_psa_pop.py --sport NHL            # one sport
    python scrape_psa_pop.py --limit 500            # cap cards processed
    python scrape_psa_pop.py --stale-days 30        # skip recently scraped
    python scrape_psa_pop.py --dry-run              # print without saving
"""

import argparse
import json
import os
import sys
import time
import unicodedata
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass

from db import get_db

PSA_API_BASE = "https://api.psacard.com/publicapi"
PSA_SPORT_MAP = {
    "NHL": "Hockey",
    "NBA": "Basketball",
    "NFL": "Football",
    "MLB": "Baseball",
}
GRADES = ["A", "1", "1.5", "2", "2.5", "3", "3.5", "4", "4.5",
          "5", "5.5", "6", "6.5", "7", "7.5", "8", "8.5", "9", "9.5", "10"]


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def fetch_json(url, headers=None, retries=3, delay=1.0):
    for attempt in range(retries + 1):
        try:
            req = Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode())
        except HTTPError as e:
            if e.code == 429:
                wait = delay * (2 ** attempt)
                print(f"  Rate limited — sleeping {wait:.0f}s")
                time.sleep(wait)
                continue
            if e.code in (401, 403):
                print(f"  AUTH ERROR {e.code}: check PSA_API_KEY")
                return None
            print(f"  HTTP {e.code} fetching {url}")
            return None
        except (URLError, OSError) as e:
            if attempt < retries:
                time.sleep(delay * (2 ** attempt))
                continue
            print(f"  ERROR fetching {url}: {e}")
            return None
    return None


def psa_headers(api_key):
    return {
        "Authorization": f"bearer {api_key}",
        "Content-Type":  "application/json",
        "User-Agent":    "CardDB/1.0",
    }


# ── PSA API calls ─────────────────────────────────────────────────────────────

def search_psa_specs(api_key, player_name, year, sport, set_name=None):
    """Search PSA for card specifications matching a player/year/sport."""
    psa_sport = PSA_SPORT_MAP.get(sport, sport)
    query = f"{player_name} {year}"
    params = urlencode({"title": query, "category": psa_sport})
    url = f"{PSA_API_BASE}/pop/SearchAndGetSpecifications?{params}"
    data = fetch_json(url, headers=psa_headers(api_key))
    if not data:
        return []
    specs = data if isinstance(data, list) else data.get("specifications", [])
    return specs


def get_psa_pop_report(api_key, spec_id):
    """Fetch per-grade population counts for a PSA specification ID."""
    url = f"{PSA_API_BASE}/pop/GetSpecificationDetail?specId={spec_id}"
    data = fetch_json(url, headers=psa_headers(api_key))
    if not data:
        return {}
    # Returns list of {grade, popCount, ...} or dict with grades key
    items = data if isinstance(data, list) else data.get("grades", data.get("items", []))
    pop = {}
    for item in items:
        grade = str(item.get("grade", item.get("gradeName", ""))).strip()
        count = int(item.get("popCount", item.get("count", 0)) or 0)
        if grade:
            pop[grade] = count
    return pop


# ── Matching ──────────────────────────────────────────────────────────────────

def normalize(text):
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def similarity(a, b):
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def best_spec_match(specs, player_name, year, set_name):
    """Pick the best-matching PSA spec from search results."""
    best_score = 0
    best_spec = None
    for spec in specs[:20]:  # only look at top 20 results
        title = spec.get("title", spec.get("name", ""))
        spec_year = str(spec.get("year", ""))
        # Year must match exactly
        if spec_year and str(year) not in spec_year:
            continue
        # Score on player name match
        score = similarity(player_name, title)
        # Bonus for set name match
        if set_name:
            score += similarity(set_name, title) * 0.3
        if score > best_score:
            best_score = score
            best_spec = spec
    # Require at least 60% match on player name
    if best_score < 0.6:
        return None
    return best_spec


# ── DB helpers ────────────────────────────────────────────────────────────────

def load_cards(sport=None, tiers=("elite", "staple"), limit=0, stale_days=7):
    """Load cards to scrape PSA pop for, deduplicated by (player, year, set)."""
    stale_cutoff = datetime.utcnow() - timedelta(days=stale_days)

    sport_filter = "AND cc.sport = %s" if sport else ""
    tier_list = ",".join(f"'{t}'" for t in tiers)
    limit_clause = f"LIMIT {limit}" if limit else ""

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT DISTINCT ON (cc.player_name, cc.year, cc.set_name)
                    cc.id, cc.player_name, cc.year, cc.set_name,
                    cc.card_number, cc.sport, cc.scrape_tier
                FROM card_catalog cc
                WHERE cc.scrape_tier IN ({tier_list})
                  AND cc.player_name != ''
                  {sport_filter}
                  AND NOT EXISTS (
                      SELECT 1 FROM psa_population pp
                      WHERE pp.card_catalog_id = cc.id
                        AND pp.scraped_at > %s
                  )
                ORDER BY cc.player_name, cc.year, cc.set_name,
                         CASE cc.scrape_tier
                             WHEN 'elite'   THEN 1
                             WHEN 'staple'  THEN 2
                             ELSE 3 END
                {limit_clause}
            """, ([sport.upper()] if sport else []) + [stale_cutoff])
            rows = cur.fetchall()
    return [
        {"id": r[0], "player_name": r[1], "year": r[2], "set_name": r[3],
         "card_number": r[4], "sport": r[5], "tier": r[6]}
        for r in rows
    ]


def upsert_pop(card_id, psa_spec_id, psa_title, pop_by_grade, dry_run=False):
    """Write per-grade pop counts to psa_population."""
    if not pop_by_grade:
        return 0
    if dry_run:
        print(f"    [DRY RUN] would upsert {len(pop_by_grade)} grades for card {card_id}")
        return len(pop_by_grade)

    rows = []
    grade_keys = sorted(pop_by_grade.keys())
    for i, grade in enumerate(grade_keys):
        count = pop_by_grade[grade]
        # pop_higher = sum of all higher-grade counts (rough supply at quality)
        pop_higher = sum(
            pop_by_grade.get(g, 0)
            for g in grade_keys[i + 1:]
        )
        rows.append((card_id, psa_spec_id, psa_title, grade, count, pop_higher))

    with get_db() as conn:
        with conn.cursor() as cur:
            from psycopg2.extras import execute_values
            execute_values(cur, """
                INSERT INTO psa_population
                    (card_catalog_id, psa_spec_id, psa_title, grade, pop_count, pop_higher, scraped_at)
                VALUES %s
                ON CONFLICT (card_catalog_id, grade) DO UPDATE SET
                    psa_spec_id = EXCLUDED.psa_spec_id,
                    psa_title   = EXCLUDED.psa_title,
                    pop_count   = EXCLUDED.pop_count,
                    pop_higher  = EXCLUDED.pop_higher,
                    scraped_at  = NOW()
            """, rows)
    return len(rows)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Scrape PSA pop reports → psa_population")
    parser.add_argument("--sport",      help="NHL/NBA/NFL/MLB")
    parser.add_argument("--tier",       default="elite,staple", help="Comma-separated tiers")
    parser.add_argument("--limit",      type=int, default=0)
    parser.add_argument("--stale-days", type=int, default=7,
                        help="Skip cards scraped within N days (default: 7)")
    parser.add_argument("--dry-run",    action="store_true")
    parser.add_argument("--verbose",    action="store_true")
    args = parser.parse_args()

    api_key = os.environ.get("PSA_API_KEY", "")
    if not api_key:
        print("ERROR: PSA_API_KEY environment variable not set.")
        print("Get a free key at https://api.psacard.com/")
        sys.exit(1)

    tiers = [t.strip() for t in args.tier.split(",")]

    print("=" * 60)
    print("PSA POP REPORT SCRAPER")
    print("=" * 60)
    print(f"  Tiers:      {tiers}")
    print(f"  Sport:      {args.sport or 'all'}")
    print(f"  Stale days: {args.stale_days}")
    print(f"  Dry run:    {args.dry_run}")

    # Ensure table exists
    if not args.dry_run:
        from migrations.migrate_add_psa_population import main as run_migration
        run_migration()

    cards = load_cards(
        sport=args.sport,
        tiers=tiers,
        limit=args.limit,
        stale_days=args.stale_days,
    )
    print(f"\n  {len(cards):,} cards to process")

    matched = missed = saved = errors = 0

    for i, card in enumerate(cards):
        player   = card["player_name"]
        year     = card["year"]
        set_name = card["set_name"]
        sport    = card["sport"]
        card_id  = card["id"]

        # Extract base year (handles "2024-25" → "2024")
        base_year = str(year).split("-")[0]

        if args.verbose:
            print(f"\n[{i+1}/{len(cards)}] {player} {year} {set_name} ({sport})")

        # Search PSA
        specs = search_psa_specs(api_key, player, base_year, sport, set_name)
        time.sleep(0.5)  # rate limit: ~2 req/s

        if not specs:
            missed += 1
            if args.verbose:
                print(f"  MISS: no PSA specs found")
            continue

        spec = best_spec_match(specs, player, base_year, set_name)
        if not spec:
            missed += 1
            if args.verbose:
                print(f"  MISS: no spec matched (best similarity < 60%)")
            continue

        spec_id    = spec.get("specificationId", spec.get("id"))
        psa_title  = spec.get("title", spec.get("name", ""))
        matched   += 1

        if args.verbose:
            print(f"  MATCH: {psa_title} (spec_id={spec_id})")

        # Get pop report
        pop = get_psa_pop_report(api_key, spec_id)
        time.sleep(0.5)

        if not pop:
            if args.verbose:
                print(f"  WARNING: empty pop report")
            continue

        n = upsert_pop(card_id, spec_id, psa_title, pop, dry_run=args.dry_run)
        saved += n

        if args.verbose:
            top = sorted(pop.items(), key=lambda x: -x[1])[:5]
            print(f"  Pop: {', '.join(f'{g}:{c}' for g,c in top)}")

        if (i + 1) % 100 == 0:
            print(f"  [{i+1}/{len(cards)}] matched={matched} missed={missed} grades_saved={saved}")

    print(f"\n{'='*60}")
    print(f"  Cards processed: {len(cards)}")
    print(f"  PSA matched:     {matched}")
    print(f"  No match:        {missed}")
    print(f"  Match rate:      {matched/max(len(cards),1)*100:.1f}%")
    print(f"  Grades saved:    {saved}")
    print("DONE")


if __name__ == "__main__":
    main()
