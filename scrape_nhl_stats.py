#!/usr/bin/env python3
"""
Scrape NHL player stats from the public NHL API and match to Young Guns card database.

Usage:
    python scrape_nhl_stats.py                    # Scrape all stats, match to 2020+ cards
    python scrape_nhl_stats.py --season 2025-26   # Only match cards from one season
    python scrape_nhl_stats.py --dry-run           # Show matches without saving
    python scrape_nhl_stats.py --verbose           # Print detailed match info
"""

import argparse
import json
import os
import sys
import time
import unicodedata
from datetime import datetime
from difflib import get_close_matches
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from dashboard_utils import (
    load_master_db, save_master_db,
    load_nhl_player_stats, save_nhl_player_stats,
    TEAM_NAME_TO_ABBREV, TEAM_ABBREV_TO_NAME,
    NHL_STATS_PATH,
)

NHL_API_BASE = "https://api-web.nhle.com/v1"
MIN_SEASON = "2020-21"


def fetch_json(url, retries=2):
    """Fetch JSON from NHL API with retry."""
    for attempt in range(retries + 1):
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=15) as resp:
                # Handle redirects — read final URL content
                return json.loads(resp.read().decode())
        except (URLError, HTTPError) as e:
            if attempt < retries:
                time.sleep(1)
                continue
            print(f"  ERROR fetching {url}: {e}")
            return None


def fetch_standings():
    """Fetch current NHL standings. Returns dict keyed by team abbreviation."""
    data = fetch_json(f"{NHL_API_BASE}/standings/now")
    if not data or 'standings' not in data:
        return {}

    standings = {}
    teams_list = data['standings']
    # Sort by points descending to determine league rank
    teams_list.sort(key=lambda t: t.get('points', 0), reverse=True)

    # Track division ranks
    div_ranks = {}
    for i, team in enumerate(teams_list):
        abbrev = team.get('teamAbbrev', {}).get('default', '')
        if not abbrev:
            continue

        div = team.get('divisionName', '')
        div_ranks[div] = div_ranks.get(div, 0) + 1

        standings[abbrev] = {
            'team_name': team.get('teamName', {}).get('default', ''),
            'wins': team.get('wins', 0),
            'losses': team.get('losses', 0),
            'otl': team.get('otLosses', 0),
            'points': team.get('points', 0),
            'games_played': team.get('gamesPlayed', 0),
            'goal_diff': team.get('goalDifferential', 0),
            'league_rank': i + 1,
            'division_rank': div_ranks[div],
            'division': div,
            'conference': team.get('conferenceName', ''),
            'streak': f"{team.get('streakCode', '')}{team.get('streakCount', '')}",
        }

    return standings


def fetch_team_stats(team_abbrev):
    """Fetch roster stats for a single team. Returns (skaters, goalies) lists."""
    data = fetch_json(f"{NHL_API_BASE}/club-stats/{team_abbrev}/now")
    if not data:
        return [], []
    return data.get('skaters', []), data.get('goalies', [])


def normalize_name(name):
    """Strip diacritics and normalize for matching."""
    nfkd = unicodedata.normalize('NFKD', name)
    return ''.join(c for c in nfkd if not unicodedata.combining(c)).strip().lower()


def build_player_index(all_teams_data):
    """Build player index from all team roster data.
    Returns (skaters_by_name, goalies_by_name) dicts keyed by 'First Last'."""
    skaters = {}
    goalies = {}

    for team_abbrev, (team_skaters, team_goalies) in all_teams_data.items():
        for s in team_skaters:
            first = s.get('firstName', {}).get('default', '')
            last = s.get('lastName', {}).get('default', '')
            name = f"{first} {last}".strip()
            if not name:
                continue
            skaters[name] = {
                'nhl_id': s.get('playerId'),
                'team': team_abbrev,
                'position': s.get('positionCode', ''),
                'games_played': s.get('gamesPlayed', 0),
                'goals': s.get('goals', 0),
                'assists': s.get('assists', 0),
                'points': s.get('points', 0),
                'plus_minus': s.get('plusMinus', 0),
                'shots': s.get('shots', 0),
                'shooting_pct': round(s.get('shootingPctg', 0), 4),
                'powerplay_goals': s.get('powerPlayGoals', 0),
                'game_winning_goals': s.get('gameWinningGoals', 0),
            }

        for g in team_goalies:
            first = g.get('firstName', {}).get('default', '')
            last = g.get('lastName', {}).get('default', '')
            name = f"{first} {last}".strip()
            if not name:
                continue
            goalies[name] = {
                'nhl_id': g.get('playerId'),
                'team': team_abbrev,
                'position': 'G',
                'games_played': g.get('gamesPlayed', 0),
                'games_started': g.get('gamesStarted', 0),
                'wins': g.get('wins', 0),
                'losses': g.get('losses', 0),
                'otl': g.get('overtimeLosses', 0),
                'save_pct': round(g.get('savePercentage', 0), 4),
                'gaa': round(g.get('goalsAgainstAverage', 0), 3),
                'shutouts': g.get('shutouts', 0),
            }

    return skaters, goalies


def match_player(player_name, skaters, goalies):
    """Try to match a card player name to an NHL API player.
    Returns (api_data, player_type) or (None, None)."""
    # Exact match — skaters first (more common)
    if player_name in skaters:
        return skaters[player_name], 'skater'
    if player_name in goalies:
        return goalies[player_name], 'goalie'

    # Normalized match (strip diacritics)
    norm_name = normalize_name(player_name)
    for name, data in skaters.items():
        if normalize_name(name) == norm_name:
            return data, 'skater'
    for name, data in goalies.items():
        if normalize_name(name) == norm_name:
            return data, 'goalie'

    # Fuzzy match as last resort
    all_names = list(skaters.keys()) + list(goalies.keys())
    matches = get_close_matches(player_name, all_names, n=1, cutoff=0.85)
    if matches:
        match_name = matches[0]
        if match_name in skaters:
            return skaters[match_name], 'skater'
        if match_name in goalies:
            return goalies[match_name], 'goalie'

    return None, None


def build_player_entry(player_name, api_data, player_type, card_team, standings, existing_entry=None):
    """Build a player stats entry, merging with existing history."""
    today = datetime.now().strftime('%Y-%m-%d')
    team = api_data['team']

    entry = {
        'nhl_id': api_data['nhl_id'],
        'current_team': team,
        'position': api_data['position'],
        'card_team': card_team,
        'type': player_type,
    }

    if player_type == 'skater':
        entry['current_season'] = {
            'games_played': api_data['games_played'],
            'goals': api_data['goals'],
            'assists': api_data['assists'],
            'points': api_data['points'],
            'plus_minus': api_data['plus_minus'],
            'shots': api_data['shots'],
            'shooting_pct': api_data['shooting_pct'],
            'powerplay_goals': api_data['powerplay_goals'],
            'game_winning_goals': api_data['game_winning_goals'],
        }
        history_snapshot = {
            'date': today,
            'games_played': api_data['games_played'],
            'goals': api_data['goals'],
            'assists': api_data['assists'],
            'points': api_data['points'],
            'plus_minus': api_data['plus_minus'],
        }
    else:
        team_standing = standings.get(team, {})
        entry['current_season'] = {
            'games_played': api_data['games_played'],
            'games_started': api_data['games_started'],
            'wins': api_data['wins'],
            'losses': api_data['losses'],
            'otl': api_data['otl'],
            'save_pct': api_data['save_pct'],
            'gaa': api_data['gaa'],
            'shutouts': api_data['shutouts'],
        }
        entry['team_standings'] = {
            'team_points': team_standing.get('points', 0),
            'league_rank': team_standing.get('league_rank', 0),
            'division_rank': team_standing.get('division_rank', 0),
        }
        history_snapshot = {
            'date': today,
            'games_played': api_data['games_played'],
            'wins': api_data['wins'],
            'save_pct': api_data['save_pct'],
            'gaa': api_data['gaa'],
            'team_points': team_standing.get('points', 0),
        }

    # Merge with existing history
    history = []
    if existing_entry and 'history' in existing_entry:
        history = [h for h in existing_entry['history'] if h.get('date') != today]
    history.append(history_snapshot)
    history.sort(key=lambda x: x['date'])
    entry['history'] = history

    return entry


def main():
    parser = argparse.ArgumentParser(description="Scrape NHL player stats and match to Young Guns DB")
    parser.add_argument('--season', type=str, help="Only match cards from this season (e.g. 2025-26)")
    parser.add_argument('--dry-run', action='store_true', help="Show matches without saving")
    parser.add_argument('--verbose', action='store_true', help="Print detailed match info")
    args = parser.parse_args()

    print("=" * 60)
    print("NHL PLAYER STATS SCRAPER")
    print("=" * 60)

    # Step 1: Fetch standings
    print("\nFetching NHL standings...")
    standings = fetch_standings()
    if not standings:
        print("ERROR: Could not fetch standings. Aborting.")
        sys.exit(1)
    print(f"  {len(standings)} teams found")

    # Step 2: Fetch all team rosters
    print(f"\nFetching roster stats for {len(standings)} teams...")
    all_teams_data = {}
    team_abbrevs = sorted(standings.keys())
    for i, abbrev in enumerate(team_abbrevs):
        team_name = standings[abbrev].get('team_name', abbrev)
        skaters, goalies = fetch_team_stats(abbrev)
        all_teams_data[abbrev] = (skaters, goalies)
        if args.verbose:
            print(f"  [{i+1}/{len(team_abbrevs)}] {abbrev} ({team_name}): {len(skaters)} skaters, {len(goalies)} goalies")
        if i < len(team_abbrevs) - 1:
            time.sleep(0.3)

    # Step 3: Build player index
    skaters_idx, goalies_idx = build_player_index(all_teams_data)
    total_api_players = len(skaters_idx) + len(goalies_idx)
    print(f"  {len(skaters_idx)} skaters, {len(goalies_idx)} goalies indexed ({total_api_players} total)")

    # Step 4: Load card database
    print("\nLoading Young Guns database...")
    df = load_master_db()
    if df.empty:
        print("ERROR: No master database found. Aborting.")
        sys.exit(1)

    # Filter to active-era seasons
    if args.season:
        candidates = df[df['Season'] == args.season].copy()
        print(f"  Filtering to season {args.season}: {len(candidates)} cards")
    else:
        candidates = df[df['Season'] >= MIN_SEASON].copy()
        print(f"  Filtering to seasons >= {MIN_SEASON}: {len(candidates)} cards")

    # Step 5: Match players
    print("\nMatching players...")
    existing_data = load_nhl_player_stats() or {}
    existing_players = existing_data.get('players', {})

    matched = {}
    unmatched = []
    positions_updated = 0

    for idx, row in candidates.iterrows():
        player_name = row['PlayerName']
        card_team = str(row['Team']).split('/')[0].strip() if row['Team'] else ''

        api_data, player_type = match_player(player_name, skaters_idx, goalies_idx)

        if api_data:
            entry = build_player_entry(
                player_name, api_data, player_type,
                card_team, standings,
                existing_entry=existing_players.get(player_name),
            )
            matched[player_name] = entry

            # Update Position in CSV if empty
            current_pos = row.get('Position', '')
            if (not current_pos or str(current_pos).strip() == '' or str(current_pos) == 'nan'):
                df.at[idx, 'Position'] = api_data['position']
                positions_updated += 1

            if args.verbose:
                team_abbrev = api_data['team']
                if player_type == 'skater':
                    print(f"  MATCH: {player_name} ({team_abbrev}) — {api_data['points']}pts ({api_data['goals']}G, {api_data['assists']}A)")
                else:
                    print(f"  MATCH: {player_name} ({team_abbrev}) — {api_data['wins']}W, {api_data['save_pct']:.3f}SV%")
        else:
            unmatched.append({
                'player': player_name,
                'season': row['Season'],
                'team': card_team,
                'reason': 'not_in_nhl',
            })
            if args.verbose:
                print(f"  MISS:  {player_name} ({row['Season']}, {card_team})")

    # Summary
    print(f"\n  Matched: {len(matched)}")
    print(f"  Unmatched: {len(unmatched)}")
    print(f"  Match rate: {len(matched)/(len(matched)+len(unmatched))*100:.1f}%")
    if positions_updated:
        print(f"  Positions updated: {positions_updated}")

    if args.dry_run:
        print("\n[DRY RUN] No files saved.")
        if unmatched:
            print(f"\nTop unmatched players:")
            for u in unmatched[:20]:
                print(f"  {u['player']} ({u['season']}, {u['team']})")
        return

    # Step 6: Save
    # Merge with existing players (keep players from previous runs not in current candidates)
    for name, entry in existing_players.items():
        if name not in matched:
            matched[name] = entry

    output = {
        'meta': {
            'last_scraped': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'season': '20252026',
            'matched': len(matched),
            'unmatched': len(unmatched),
        },
        'standings': standings,
        'players': matched,
        'unmatched': unmatched,
    }

    save_nhl_player_stats(output)
    print(f"\n  Saved to: {NHL_STATS_PATH}")

    # Save updated positions to CSV
    if positions_updated > 0:
        save_master_db(df)
        print(f"  Updated {positions_updated} positions in young_guns.csv")

    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)


if __name__ == '__main__':
    main()
