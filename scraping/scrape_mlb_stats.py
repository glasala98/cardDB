#!/usr/bin/env python3
"""
Scrape MLB player stats from the official MLB Stats API and store in player_stats.

Uses MLB's official free public API (no auth required):
https://statsapi.mlb.com/api/v1/

Usage:
    python scrape_mlb_stats.py                  # current season
    python scrape_mlb_stats.py --season 2024    # specific season
    python scrape_mlb_stats.py --dry-run
    python scrape_mlb_stats.py --verbose
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

MLB_BASE = "https://statsapi.mlb.com/api/v1"
CURRENT_SEASON = datetime.now().year


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def fetch_json(url, retries=3):
    headers = {"User-Agent": "CardDB/1.0", "Accept": "application/json"}
    for attempt in range(retries + 1):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode())
        except HTTPError as e:
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            return None
        except (URLError, OSError):
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            return None
    return None


# ── Data fetching ─────────────────────────────────────────────────────────────

def fetch_all_players(season):
    """Fetch all active MLB players for a season."""
    url = f"{MLB_BASE}/sports/1/players?season={season}&gameType=R"
    data = fetch_json(url)
    if not data:
        return []
    return data.get("people", [])


def fetch_batting_stats(season):
    """Fetch season batting stats for all players."""
    url = (f"{MLB_BASE}/stats?stats=season&group=hitting&season={season}"
           f"&gameType=R&playerPool=ALL&limit=2000")
    data = fetch_json(url)
    if not data:
        return {}
    stats_map = {}
    for entry in data.get("stats", [{}])[0].get("splits", []):
        player = entry.get("player", {})
        pid = player.get("id")
        if pid:
            stats_map[pid] = entry.get("stat", {})
    return stats_map


def fetch_pitching_stats(season):
    """Fetch season pitching stats for all players."""
    url = (f"{MLB_BASE}/stats?stats=season&group=pitching&season={season}"
           f"&gameType=R&playerPool=ALL&limit=2000")
    data = fetch_json(url)
    if not data:
        return {}
    stats_map = {}
    for entry in data.get("stats", [{}])[0].get("splits", []):
        player = entry.get("player", {})
        pid = player.get("id")
        if pid:
            stats_map[pid] = entry.get("stat", {})
    return stats_map


def fetch_standings(season):
    """Fetch MLB standings."""
    url = f"{MLB_BASE}/standings?leagueId=103,104&season={season}&standingsTypes=regularSeason"
    data = fetch_json(url)
    if not data:
        return {}
    standings = {}
    for record in data.get("records", []):
        division = record.get("division", {}).get("name", "")
        for team_record in record.get("teamRecords", []):
            team = team_record.get("team", {})
            abbrev = team.get("abbreviation", "")
            if not abbrev:
                continue
            standings[abbrev] = {
                "team_name":      team.get("name", ""),
                "wins":           team_record.get("wins", 0),
                "losses":         team_record.get("losses", 0),
                "win_pct":        round(float(team_record.get("winningPercentage", 0)), 3),
                "games_back":     team_record.get("gamesBack", "-"),
                "division":       division,
                "division_rank":  team_record.get("divisionRank", 0),
                "streak":         team_record.get("streak", {}).get("streakCode", ""),
            }
    return standings


# ── Matching ──────────────────────────────────────────────────────────────────

def normalize_name(name):
    nfkd = unicodedata.normalize("NFKD", str(name))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def build_player_index(players):
    """Build {full_name: player_dict} index."""
    idx = {}
    for p in players:
        name = p.get("fullName", "")
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
    matches = get_close_matches(player_name, list(player_idx.keys()), n=1, cutoff=0.85)
    return player_idx[matches[0]] if matches else None


# ── Entry building ────────────────────────────────────────────────────────────

def build_entry(player, batting, pitching, standings, existing=None):
    today = date.today().isoformat()
    position = player.get("primaryPosition", {}).get("abbreviation", "")
    team     = player.get("currentTeam", {}).get("abbreviation", "")
    is_pitcher = position in ("SP", "RP", "P", "CP")

    if is_pitcher and pitching:
        season_stats = {
            "games_played":  int(pitching.get("gamesPlayed", 0)),
            "wins":          int(pitching.get("wins", 0)),
            "losses":        int(pitching.get("losses", 0)),
            "era":           round(float(pitching.get("era", 0) or 0), 2),
            "strikeouts":    int(pitching.get("strikeOuts", 0)),
            "whip":          round(float(pitching.get("whip", 0) or 0), 3),
            "innings_pitched": float(pitching.get("inningsPitched", 0) or 0),
            "saves":         int(pitching.get("saves", 0)),
            "walks":         int(pitching.get("baseOnBalls", 0)),
        }
        snapshot = {
            "date":     today,
            "wins":     season_stats["wins"],
            "era":      season_stats["era"],
            "so":       season_stats["strikeouts"],
            "whip":     season_stats["whip"],
        }
    elif batting:
        season_stats = {
            "games_played":  int(batting.get("gamesPlayed", 0)),
            "avg":           round(float(batting.get("avg", 0) or 0), 3),
            "home_runs":     int(batting.get("homeRuns", 0)),
            "rbi":           int(batting.get("rbi", 0)),
            "hits":          int(batting.get("hits", 0)),
            "runs":          int(batting.get("runs", 0)),
            "stolen_bases":  int(batting.get("stolenBases", 0)),
            "obp":           round(float(batting.get("obp", 0) or 0), 3),
            "slg":           round(float(batting.get("slg", 0) or 0), 3),
            "ops":           round(float(batting.get("ops", 0) or 0), 3),
            "at_bats":       int(batting.get("atBats", 0)),
        }
        snapshot = {
            "date":       today,
            "avg":        season_stats["avg"],
            "hr":         season_stats["home_runs"],
            "rbi":        season_stats["rbi"],
            "ops":        season_stats["ops"],
        }
    else:
        return None

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

def load_mlb_players_from_catalog():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT player_name, team
                FROM card_catalog
                WHERE sport = 'MLB' AND player_name != ''
                ORDER BY player_name
            """)
            return [{"player_name": r[0], "team": r[1]} for r in cur.fetchall()]


def load_existing_stats():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT player, data FROM player_stats WHERE sport = 'MLB'")
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
                """, [("MLB", name, json.dumps(data)) for name, data in matched.items()])
            if standings:
                execute_values(cur, """
                    INSERT INTO standings (sport, team, data)
                    VALUES %s
                    ON CONFLICT (sport, team) DO UPDATE SET
                        data       = EXCLUDED.data,
                        updated_at = NOW()
                """, [("MLB", team, json.dumps(data)) for team, data in standings.items()])
    print(f"  Saved {len(matched)} players, {len(standings)} teams to DB")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Scrape MLB stats → player_stats")
    parser.add_argument("--season",  type=int, default=CURRENT_SEASON)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("MLB PLAYER STATS SCRAPER")
    print(f"Season: {args.season}")
    print("=" * 60)

    print("\nFetching all MLB players...")
    players = fetch_all_players(args.season)
    player_idx = build_player_index(players)
    print(f"  {len(player_idx)} players indexed")

    print(f"\nFetching batting stats ({args.season})...")
    batting_stats = fetch_batting_stats(args.season)
    print(f"  {len(batting_stats)} batters")

    print(f"\nFetching pitching stats ({args.season})...")
    pitching_stats = fetch_pitching_stats(args.season)
    print(f"  {len(pitching_stats)} pitchers")

    print(f"\nFetching standings ({args.season})...")
    standings = fetch_standings(args.season)
    print(f"  {len(standings)} teams")

    print("\nLoading MLB players from card_catalog...")
    catalog_players = load_mlb_players_from_catalog()
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

        pid = player.get("id")
        batting  = batting_stats.get(pid, {})
        pitching = pitching_stats.get(pid, {})

        if not batting and not pitching:
            if args.verbose:
                print(f"  NO STATS: {name}")
            continue

        entry = build_entry(player, batting, pitching, standings, existing.get(name))
        if not entry:
            continue
        matched[name] = entry

        if args.verbose:
            pos = entry["position"]
            cs  = entry["current_season"]
            if pos in ("SP", "RP", "P", "CP"):
                print(f"  MATCH: {name} ({pos}) — ERA:{cs.get('era')} W:{cs.get('wins')}")
            else:
                print(f"  MATCH: {name} ({pos}) — .{str(cs.get('avg',0)).replace('0.','')}"
                      f" HR:{cs.get('home_runs')} RBI:{cs.get('rbi')}")

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
