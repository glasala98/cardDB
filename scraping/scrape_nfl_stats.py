#!/usr/bin/env python3
"""
Scrape NFL player stats from ESPN's public API and store in player_stats.

Uses ESPN's unofficial public API (no auth required).
Fetches current season stats for QBs, WRs, RBs, TEs, and DEF players.

Usage:
    python scrape_nfl_stats.py                  # all positions
    python scrape_nfl_stats.py --dry-run
    python scrape_nfl_stats.py --verbose
    python scrape_nfl_stats.py --season 2024    # specific season year
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

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
ESPN_CORE = "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl"

CURRENT_SEASON = datetime.now().year if datetime.now().month >= 9 else datetime.now().year - 1

# ESPN stat category IDs for NFL
STAT_CATEGORIES = {
    "passing":   "0",
    "rushing":   "1",
    "receiving": "2",
    "defense":   "3",
    "kicking":   "5",
}


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def fetch_json(url, retries=3):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }
    for attempt in range(retries + 1):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode())
        except HTTPError as e:
            if e.code == 429:
                time.sleep(2 ** attempt)
                continue
            if attempt < retries:
                time.sleep(1)
                continue
            return None
        except (URLError, OSError) as e:
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            return None
    return None


# ── Data fetching ─────────────────────────────────────────────────────────────

def fetch_team_roster(team_abbrev):
    """Fetch full roster for a team."""
    url = f"{ESPN_BASE}/teams/{team_abbrev}/roster"
    data = fetch_json(url)
    if not data:
        return []
    athletes = []
    for group in data.get("athletes", []):
        athletes.extend(group.get("items", []))
    return athletes


def fetch_team_list():
    """Fetch all NFL teams."""
    data = fetch_json(f"{ESPN_BASE}/teams?limit=40")
    if not data:
        return []
    return [t for t in data.get("sports", [{}])[0]
            .get("leagues", [{}])[0]
            .get("teams", [])]


def fetch_player_stats(player_id, season):
    """Fetch season stats for a specific player from ESPN."""
    url = f"{ESPN_BASE}/athletes/{player_id}/stats?season={season}"
    data = fetch_json(url)
    if not data:
        return {}

    stats = {}
    for category in data.get("categories", []):
        cat_name = category.get("name", "")
        for stat in category.get("stats", []):
            key = f"{cat_name}_{stat.get('name', '')}".lower().replace(" ", "_")
            stats[key] = stat.get("value", 0)

    # Also pull from the cleaner splitCategories if available
    for split in data.get("splitCategories", []):
        if split.get("name") == "Season":
            for cat in split.get("categories", []):
                cat_label = cat.get("displayName", cat.get("name", "")).lower()
                labels = cat.get("labels", [])
                values = cat.get("values", [])
                for label, value in zip(labels, values):
                    key = f"{cat_label}_{label}".lower().replace(" ", "_").replace("/", "_per_")
                    stats[key] = value

    return stats


def fetch_standings(season):
    """Fetch NFL standings."""
    url = f"{ESPN_BASE}/standings?season={season}"
    data = fetch_json(url)
    if not data:
        return {}
    standings = {}
    for group in data.get("standings", [{}]):
        for entry in group.get("entries", []):
            team = entry.get("team", {})
            abbrev = team.get("abbreviation", "")
            if not abbrev:
                continue
            stats_map = {s["name"]: s["value"] for s in entry.get("stats", [])}
            standings[abbrev] = {
                "team_name":  team.get("displayName", ""),
                "wins":       int(stats_map.get("wins", 0)),
                "losses":     int(stats_map.get("losses", 0)),
                "ties":       int(stats_map.get("ties", 0)),
                "win_pct":    round(float(stats_map.get("winPercent", 0)), 3),
                "points_for": float(stats_map.get("pointsFor", 0)),
                "division":   group.get("name", ""),
            }
    return standings


# ── Matching ──────────────────────────────────────────────────────────────────

def normalize_name(name):
    nfkd = unicodedata.normalize("NFKD", str(name))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def build_roster_index(rosters):
    """Build {player_name: {id, position, team}} from all team rosters."""
    idx = {}
    for team_abbrev, athletes in rosters.items():
        for a in athletes:
            name = a.get("fullName", "")
            if not name:
                continue
            idx[name] = {
                "id":       a.get("id"),
                "position": a.get("position", {}).get("abbreviation", ""),
                "team":     team_abbrev,
            }
    return idx


def match_player(player_name, player_idx):
    if player_name in player_idx:
        return player_idx[player_name]
    norm = normalize_name(player_name)
    for name, data in player_idx.items():
        if normalize_name(name) == norm:
            return data
    matches = get_close_matches(player_name, list(player_idx.keys()), n=1, cutoff=0.85)
    return player_idx[matches[0]] if matches else None


# ── Entry building ────────────────────────────────────────────────────────────

def extract_key_stats(raw_stats, position):
    """Extract position-relevant stats from the raw ESPN stats dict."""
    pos = (position or "").upper()

    if pos == "QB":
        return {
            "passing_yards":       raw_stats.get("passing_passingyards", raw_stats.get("general_passingyards", 0)),
            "passing_tds":         raw_stats.get("passing_passingtouchdowns", 0),
            "interceptions":       raw_stats.get("passing_interceptions", 0),
            "completions":         raw_stats.get("passing_completions", 0),
            "attempts":            raw_stats.get("passing_passingattempts", 0),
            "completion_pct":      raw_stats.get("passing_completionpct", 0),
            "passer_rating":       raw_stats.get("passing_qbrating", 0),
            "rushing_yards":       raw_stats.get("rushing_rushingyards", 0),
            "rushing_tds":         raw_stats.get("rushing_rushingtouchdowns", 0),
        }
    elif pos in ("RB", "FB"):
        return {
            "rushing_yards":       raw_stats.get("rushing_rushingyards", 0),
            "rushing_tds":         raw_stats.get("rushing_rushingtouchdowns", 0),
            "rushing_attempts":    raw_stats.get("rushing_rushingattempts", 0),
            "yards_per_carry":     raw_stats.get("rushing_yardsperrushingattempt", 0),
            "receiving_yards":     raw_stats.get("receiving_receivingyards", 0),
            "receiving_tds":       raw_stats.get("receiving_receivingtouchdowns", 0),
            "receptions":          raw_stats.get("receiving_receptions", 0),
        }
    elif pos in ("WR", "TE"):
        return {
            "receptions":          raw_stats.get("receiving_receptions", 0),
            "receiving_yards":     raw_stats.get("receiving_receivingyards", 0),
            "receiving_tds":       raw_stats.get("receiving_receivingtouchdowns", 0),
            "targets":             raw_stats.get("receiving_receivingtargets", 0),
            "yards_per_reception": raw_stats.get("receiving_yardsperreception", 0),
        }
    else:
        # Generic — return whatever we have
        return {k: v for k, v in raw_stats.items() if isinstance(v, (int, float)) and v != 0}


def build_entry(player_info, raw_stats, standings, season, existing=None):
    today = date.today().isoformat()
    position = player_info.get("position", "")
    team     = player_info.get("team", "")

    season_stats = extract_key_stats(raw_stats, position)
    season_stats["games_played"] = int(raw_stats.get("general_games", raw_stats.get("general_gamesplayed", 0)))

    snapshot = {"date": today, "season": season, **season_stats}

    history = []
    if existing and "history" in existing:
        history = [h for h in existing["history"] if h.get("date") != today]
    history.append(snapshot)
    history.sort(key=lambda x: x["date"])

    return {
        "current_team":   team,
        "position":       position,
        "current_season": season_stats,
        "team_standings": standings.get(team, {}),
        "history":        history,
    }


# ── DB helpers ────────────────────────────────────────────────────────────────

def load_nfl_players_from_catalog():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT player_name, team
                FROM card_catalog
                WHERE sport = 'NFL' AND player_name != ''
                ORDER BY player_name
            """)
            return [{"player_name": r[0], "team": r[1]} for r in cur.fetchall()]


def load_existing_stats():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT player, data FROM player_stats WHERE sport = 'NFL'")
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
                """, [("NFL", name, json.dumps(data)) for name, data in matched.items()])
            if standings:
                execute_values(cur, """
                    INSERT INTO standings (sport, team, data)
                    VALUES %s
                    ON CONFLICT (sport, team) DO UPDATE SET
                        data       = EXCLUDED.data,
                        updated_at = NOW()
                """, [("NFL", team, json.dumps(data)) for team, data in standings.items()])
    print(f"  Saved {len(matched)} players, {len(standings)} teams to DB")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Scrape NFL stats → player_stats")
    parser.add_argument("--season",  type=int, default=CURRENT_SEASON)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("NFL PLAYER STATS SCRAPER")
    print(f"Season: {args.season}")
    print("=" * 60)

    print("\nFetching NFL teams...")
    teams_data = fetch_team_list()
    team_abbrevs = [t.get("team", {}).get("abbreviation", "") for t in teams_data if t.get("team", {}).get("abbreviation")]
    print(f"  {len(team_abbrevs)} teams")

    print("\nFetching team rosters...")
    rosters = {}
    for i, abbrev in enumerate(team_abbrevs):
        athletes = fetch_team_roster(abbrev)
        rosters[abbrev] = athletes
        if args.verbose:
            print(f"  [{i+1}/{len(team_abbrevs)}] {abbrev}: {len(athletes)} players")
        time.sleep(0.3)

    player_idx = build_roster_index(rosters)
    print(f"  {len(player_idx)} players indexed")

    print(f"\nFetching standings ({args.season})...")
    standings = fetch_standings(args.season)
    print(f"  {len(standings)} teams")

    print("\nLoading NFL players from card_catalog...")
    catalog_players = load_nfl_players_from_catalog()
    print(f"  {len(catalog_players):,} distinct players")

    existing = load_existing_stats()
    print(f"  {len(existing)} already in player_stats")

    print("\nMatching players and fetching stats...")
    matched = {}
    unmatched = []
    seen = set()

    for i, row in enumerate(catalog_players):
        name = row["player_name"]
        if name in seen:
            continue
        seen.add(name)

        player_info = match_player(name, player_idx)
        if not player_info:
            unmatched.append(name)
            if args.verbose:
                print(f"  MISS:  {name}")
            continue

        player_id = player_info.get("id")
        raw_stats = fetch_player_stats(player_id, args.season)
        time.sleep(0.25)

        if not raw_stats:
            if args.verbose:
                print(f"  NO STATS: {name}")
            continue

        entry = build_entry(player_info, raw_stats, standings, args.season, existing.get(name))
        matched[name] = entry

        if args.verbose:
            cs = entry["current_season"]
            print(f"  MATCH: {name} ({player_info['position']}/{player_info['team']}) — {cs}")

        if (i + 1) % 50 == 0:
            print(f"  [{i+1}/{len(catalog_players)}] matched={len(matched)} missed={len(unmatched)}")

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
