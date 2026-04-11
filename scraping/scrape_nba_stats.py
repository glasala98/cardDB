#!/usr/bin/env python3
"""
Scrape NBA player stats from the Ball Don't Lie API and store in player_stats.

Uses the free Ball Don't Lie API (https://api.balldontlie.io).
Requires BALLDONTLIE_API_KEY env var — free key at https://api.balldontlie.io

Writes to player_stats + standings tables (same schema as scrape_nhl_stats.py).

Usage:
    python scrape_nba_stats.py                  # scrape all NBA players
    python scrape_nba_stats.py --season 2024    # specific season (default: current)
    python scrape_nba_stats.py --dry-run        # print without saving
    python scrape_nba_stats.py --verbose        # detailed output
"""

import argparse
import json
import os
import sys
import time
import unicodedata
from datetime import datetime, date
from difflib import get_close_matches
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

BDL_BASE = "https://api.balldontlie.io/v1"

# Current NBA season start year (2024 = 2024-25 season)
CURRENT_SEASON = datetime.now().year if datetime.now().month >= 10 else datetime.now().year - 1


# ── API helpers ───────────────────────────────────────────────────────────────

def fetch_json(url, headers, retries=3):
    for attempt in range(retries + 1):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode())
        except HTTPError as e:
            if e.code == 429:
                wait = 2 ** attempt
                print(f"  Rate limited — sleeping {wait}s")
                time.sleep(wait)
                continue
            print(f"  HTTP {e.code}: {url}")
            return None
        except (URLError, OSError) as e:
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            print(f"  ERROR: {e}")
            return None
    return None


def fetch_all_pages(url, headers, page_size=100):
    """Fetch all pages from a paginated BDL endpoint."""
    results = []
    cursor = None
    while True:
        sep = "&" if "?" in url else "?"
        page_url = f"{url}{sep}per_page={page_size}"
        if cursor:
            page_url += f"&cursor={cursor}"
        data = fetch_json(page_url, headers)
        if not data:
            break
        results.extend(data.get("data", []))
        meta = data.get("meta", {})
        cursor = meta.get("next_cursor")
        if not cursor:
            break
        time.sleep(0.3)
    return results


def bdl_headers(api_key):
    return {"Authorization": api_key, "User-Agent": "CardDB/1.0"}


# ── Data fetching ─────────────────────────────────────────────────────────────

def fetch_season_averages(api_key, season):
    """Fetch all player season averages for a given season."""
    headers = bdl_headers(api_key)
    url = f"{BDL_BASE}/season_averages?season={season}&season_type=regular"
    averages = fetch_all_pages(url, headers)
    print(f"  {len(averages)} player season averages fetched")
    return {a["player_id"]: a for a in averages}


def fetch_all_players(api_key):
    """Fetch all active NBA players."""
    headers = bdl_headers(api_key)
    players = fetch_all_pages(f"{BDL_BASE}/players/active", headers)
    print(f"  {len(players)} active NBA players fetched")
    return players


def fetch_standings(api_key, season):
    """Fetch NBA standings (team wins/losses)."""
    headers = bdl_headers(api_key)
    data = fetch_json(f"{BDL_BASE}/standings?season={season}", headers)
    if not data:
        return {}
    standings = {}
    entries = data.get("data", [])
    for e in entries:
        team = e.get("team", {})
        abbrev = team.get("abbreviation", "")
        if not abbrev:
            continue
        standings[abbrev] = {
            "team_name":      team.get("full_name", ""),
            "wins":           e.get("wins", 0),
            "losses":         e.get("losses", 0),
            "win_pct":        round(e.get("wins", 0) / max(e.get("wins", 0) + e.get("losses", 0), 1), 3),
            "conference":     e.get("conference", ""),
            "conference_rank": e.get("conference_rank", 0),
            "division":       e.get("division", ""),
        }
    return standings


# ── Matching ──────────────────────────────────────────────────────────────────

def normalize_name(name):
    nfkd = unicodedata.normalize("NFKD", str(name))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def build_player_index(players):
    """Build {full_name: player_dict} lookup."""
    idx = {}
    for p in players:
        first = p.get("first_name", "")
        last  = p.get("last_name", "")
        name  = f"{first} {last}".strip()
        if name:
            idx[name] = p
    return idx


def match_player(player_name, player_idx):
    if player_name in player_idx:
        return player_idx[player_name]
    norm = normalize_name(player_name)
    for name, data in player_idx.items():
        if normalize_name(name) == norm:
            return data
    all_names = list(player_idx.keys())
    matches = get_close_matches(player_name, all_names, n=1, cutoff=0.85)
    return player_idx[matches[0]] if matches else None


# ── Entry building ────────────────────────────────────────────────────────────

def build_entry(player, avg, standings, existing=None):
    today = date.today().isoformat()
    team_abbrev = (player.get("team", {}) or {}).get("abbreviation", "")

    season_stats = {
        "games_played":  avg.get("games_played", 0),
        "points":        round(avg.get("pts", 0), 1),
        "rebounds":      round(avg.get("reb", 0), 1),
        "assists":       round(avg.get("ast", 0), 1),
        "steals":        round(avg.get("stl", 0), 1),
        "blocks":        round(avg.get("blk", 0), 1),
        "turnovers":     round(avg.get("turnover", 0), 1),
        "fg_pct":        round(avg.get("fg_pct", 0), 3),
        "fg3_pct":       round(avg.get("fg3_pct", 0), 3),
        "ft_pct":        round(avg.get("ft_pct", 0), 3),
        "minutes":       avg.get("min", ""),
    }

    snapshot = {
        "date":         today,
        "games_played": season_stats["games_played"],
        "points":       season_stats["points"],
        "rebounds":     season_stats["rebounds"],
        "assists":      season_stats["assists"],
    }

    history = []
    if existing and "history" in existing:
        history = [h for h in existing["history"] if h.get("date") != today]
    history.append(snapshot)
    history.sort(key=lambda x: x["date"])

    team_standing = standings.get(team_abbrev, {})

    return {
        "current_team":    team_abbrev,
        "position":        player.get("position", ""),
        "current_season":  season_stats,
        "team_standings":  team_standing,
        "history":         history,
    }


# ── DB helpers ────────────────────────────────────────────────────────────────

def load_nba_players_from_catalog():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT player_name, team
                FROM card_catalog
                WHERE sport = 'NBA' AND player_name != ''
                ORDER BY player_name
            """)
            return [{"player_name": r[0], "team": r[1]} for r in cur.fetchall()]


def load_existing_stats():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT player, data FROM player_stats WHERE sport = 'NBA'")
            return {r[0]: r[1] for r in cur.fetchall()}


def save_to_db(matched, standings, dry_run=False):
    if dry_run:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            from psycopg2.extras import execute_values
            if matched:
                execute_values(cur, """
                    INSERT INTO player_stats (sport, player, data)
                    VALUES %s
                    ON CONFLICT (sport, player) DO UPDATE SET
                        data       = EXCLUDED.data,
                        updated_at = NOW()
                """, [("NBA", name, json.dumps(data)) for name, data in matched.items()])
            if standings:
                execute_values(cur, """
                    INSERT INTO standings (sport, team, data)
                    VALUES %s
                    ON CONFLICT (sport, team) DO UPDATE SET
                        data       = EXCLUDED.data,
                        updated_at = NOW()
                """, [("NBA", team, json.dumps(data)) for team, data in standings.items()])
    print(f"  Saved {len(matched)} players, {len(standings)} teams to DB")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Scrape NBA stats → player_stats")
    parser.add_argument("--season",  type=int, default=CURRENT_SEASON)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    api_key = os.environ.get("BALLDONTLIE_API_KEY", "")
    if not api_key:
        print("ERROR: BALLDONTLIE_API_KEY not set.")
        print("Get a free key at https://api.balldontlie.io")
        sys.exit(1)

    print("=" * 60)
    print("NBA PLAYER STATS SCRAPER")
    print(f"Season: {args.season}-{args.season+1}")
    print("=" * 60)

    print("\nFetching active NBA players...")
    players = fetch_all_players(api_key)
    player_idx = build_player_index(players)

    print(f"\nFetching season averages ({args.season})...")
    averages = fetch_season_averages(api_key, args.season)

    print(f"\nFetching standings...")
    standings = fetch_standings(api_key, args.season)
    print(f"  {len(standings)} teams")

    print(f"\nLoading NBA players from card_catalog...")
    catalog_players = load_nba_players_from_catalog()
    print(f"  {len(catalog_players):,} distinct players")

    existing = load_existing_stats()
    print(f"  {len(existing)} already in player_stats")

    print("\nMatching players...")
    matched = {}
    unmatched = []
    seen = set()

    for row in catalog_players:
        name = row["player_name"]
        if name in seen:
            continue
        seen.add(name)

        player = match_player(name, player_idx)
        if not player:
            unmatched.append(name)
            if args.verbose:
                print(f"  MISS:  {name}")
            continue

        player_id = player.get("id")
        avg = averages.get(player_id, {})
        if not avg:
            # Player matched but no stats this season (injured/inactive)
            if args.verbose:
                print(f"  NO STATS: {name} (matched but no averages)")
            continue

        entry = build_entry(player, avg, standings, existing=existing.get(name))
        matched[name] = entry

        if args.verbose:
            cs = entry["current_season"]
            print(f"  MATCH: {name} — {cs['points']}pts {cs['rebounds']}reb {cs['assists']}ast")

    # Preserve existing players not in current catalog
    for name, data in existing.items():
        if name not in matched:
            matched[name] = data

    total = len(matched) + len(unmatched)
    print(f"  Matched:    {len(matched)}")
    print(f"  Unmatched:  {len(unmatched)}")
    print(f"  Match rate: {len(matched)/max(total,1)*100:.1f}%")

    if args.dry_run:
        print("\n[DRY RUN] Not saving.")
        return

    print("\nSaving to PostgreSQL...")
    save_to_db(matched, standings, dry_run=args.dry_run)

    print("\n" + "=" * 60)
    print("DONE")


if __name__ == "__main__":
    main()
