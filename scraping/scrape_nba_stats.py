#!/usr/bin/env python3
"""
Scrape NBA player stats from ESPN's public API and store in player_stats.

Uses ESPN's unofficial public API (no auth required) — same approach as scrape_nfl_stats.py.

Usage:
    python scrape_nba_stats.py                  # current season
    python scrape_nba_stats.py --season 2024    # specific season year
    python scrape_nba_stats.py --dry-run
    python scrape_nba_stats.py --verbose
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

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
ESPN_CORE = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba"

CURRENT_SEASON = datetime.now().year if datetime.now().month >= 10 else datetime.now().year - 1


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
        except (URLError, OSError):
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            return None
    return None


# ── Data fetching ─────────────────────────────────────────────────────────────

def fetch_team_list():
    data = fetch_json(f"{ESPN_BASE}/teams?limit=40")
    if not data:
        return []
    return [t for t in data.get("sports", [{}])[0]
            .get("leagues", [{}])[0]
            .get("teams", [])]


def fetch_team_roster(team_id):
    data = fetch_json(f"{ESPN_BASE}/teams/{team_id}/roster")
    if not data:
        return []
    athletes = []
    for group in data.get("athletes", []):
        athletes.extend(group.get("items", []))
    return athletes


def fetch_player_stats(player_id, season):
    url = f"{ESPN_BASE}/athletes/{player_id}/stats?season={season}"
    data = fetch_json(url)
    if not data:
        return {}
    stats = {}
    # Parse splitCategories for cleaner season totals/averages
    for split in data.get("splitCategories", []):
        if split.get("name") in ("Season", "Regular Season"):
            for cat in split.get("categories", []):
                cat_label = cat.get("displayName", cat.get("name", "")).lower()
                labels = cat.get("labels", [])
                values = cat.get("values", [])
                for label, value in zip(labels, values):
                    key = f"{cat_label}_{label}".lower().replace(" ", "_")
                    stats[key] = value
    # Fallback: flat categories
    if not stats:
        for cat in data.get("categories", []):
            for stat in cat.get("stats", []):
                key = stat.get("name", "").lower().replace(" ", "_")
                stats[key] = stat.get("value", 0)
    return stats


def fetch_standings(season):
    url = f"{ESPN_BASE}/standings?season={season}"
    data = fetch_json(url)
    if not data:
        return {}
    standings = {}
    for group in data.get("standings", []):
        for entry in group.get("entries", []):
            team = entry.get("team", {})
            abbrev = team.get("abbreviation", "")
            if not abbrev:
                continue
            stats_map = {s["name"]: s["value"] for s in entry.get("stats", [])}
            standings[abbrev] = {
                "team_name":       team.get("displayName", ""),
                "wins":            int(stats_map.get("wins", 0)),
                "losses":          int(stats_map.get("losses", 0)),
                "win_pct":         round(float(stats_map.get("winPercent", 0)), 3),
                "conference":      group.get("name", ""),
                "conference_rank": int(stats_map.get("playoffSeed", 0)),
            }
    return standings


# ── Matching ──────────────────────────────────────────────────────────────────

def normalize_name(name):
    nfkd = unicodedata.normalize("NFKD", str(name))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def build_roster_index(rosters):
    idx = {}
    for team_abbrev, athletes in rosters.items():
        for a in athletes:
            name = a.get("fullName", "")
            if name:
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

def build_entry(player_info, raw_stats, standings, existing=None):
    today = date.today().isoformat()
    team = player_info.get("team", "")

    # ESPN NBA stat keys vary — try common patterns
    def _get(*keys):
        for k in keys:
            if k in raw_stats:
                return raw_stats[k]
        return 0

    season_stats = {
        "games_played":  int(_get("general_gp", "general_games", "gp")),
        "points":        round(float(_get("scoring_pts", "general_pts", "pts")), 1),
        "rebounds":      round(float(_get("rebounds_reb", "general_reb", "reb")), 1),
        "assists":       round(float(_get("assists_ast", "general_ast", "ast")), 1),
        "steals":        round(float(_get("general_stl", "stl")), 1),
        "blocks":        round(float(_get("general_blk", "blk")), 1),
        "turnovers":     round(float(_get("general_to", "to")), 1),
        "fg_pct":        round(float(_get("shooting_fg%", "general_fg%", "fg_pct")), 3),
        "fg3_pct":       round(float(_get("shooting_3p%", "general_3p%", "fg3_pct")), 3),
        "ft_pct":        round(float(_get("shooting_ft%", "general_ft%", "ft_pct")), 3),
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

    return {
        "current_team":   team,
        "position":       player_info.get("position", ""),
        "current_season": season_stats,
        "team_standings": standings.get(team, {}),
        "history":        history,
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
    parser = argparse.ArgumentParser(description="Scrape NBA stats → player_stats (ESPN)")
    parser.add_argument("--season",  type=int, default=CURRENT_SEASON)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("NBA PLAYER STATS SCRAPER (ESPN)")
    print(f"Season: {args.season}-{args.season + 1}")
    print("=" * 60)

    print("\nFetching NBA teams...")
    teams_data = fetch_team_list()
    teams = [(t.get("team", {}).get("id"), t.get("team", {}).get("abbreviation", ""))
             for t in teams_data if t.get("team", {}).get("id")]
    print(f"  {len(teams)} teams")

    print("\nFetching team rosters...")
    rosters = {}
    for team_id, abbrev in teams:
        athletes = fetch_team_roster(team_id)
        rosters[abbrev] = athletes
        if args.verbose:
            print(f"  {abbrev}: {len(athletes)} players")
        time.sleep(0.3)

    player_idx = build_roster_index(rosters)
    print(f"  {len(player_idx)} players indexed")

    print(f"\nFetching standings ({args.season})...")
    standings = fetch_standings(args.season)
    print(f"  {len(standings)} teams")

    print("\nLoading NBA players from card_catalog...")
    catalog_players = load_nba_players_from_catalog()
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

        raw_stats = fetch_player_stats(player_info["id"], args.season)
        time.sleep(0.25)

        if not raw_stats:
            if args.verbose:
                print(f"  NO STATS: {name}")
            continue

        entry = build_entry(player_info, raw_stats, standings, existing.get(name))
        matched[name] = entry

        if args.verbose:
            cs = entry["current_season"]
            print(f"  MATCH: {name} ({player_info['position']}/{player_info['team']}) "
                  f"— {cs['points']}pts {cs['rebounds']}reb {cs['assists']}ast")

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
