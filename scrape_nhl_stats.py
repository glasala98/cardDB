#!/usr/bin/env python3
"""
Scrape NHL player stats from the public NHL API and store in PostgreSQL.

Reads players from card_catalog (sport='NHL'), matches to live NHL API data,
and writes to player_stats + standings + rookie_correlation_history tables.

Usage:
    python scrape_nhl_stats.py                    # Scrape all stats
    python scrape_nhl_stats.py --fetch-bios       # Also fetch birth/draft info
    python scrape_nhl_stats.py --dry-run          # Print matches without saving
    python scrape_nhl_stats.py --verbose          # Detailed match output
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
sys.path.insert(0, SCRIPT_DIR)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(SCRIPT_DIR, '.env'))
except ImportError:
    pass

from db import get_db

NHL_API_BASE = "https://api-web.nhle.com/v1"


# ── NHL API helpers ───────────────────────────────────────────────────────────

def fetch_json(url, retries=2):
    for attempt in range(retries + 1):
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except (URLError, HTTPError) as e:
            if attempt < retries:
                time.sleep(1)
                continue
            print(f"  ERROR fetching {url}: {e}")
            return None


def fetch_standings():
    data = fetch_json(f"{NHL_API_BASE}/standings/now")
    if not data or 'standings' not in data:
        return {}
    teams_list = data['standings']
    teams_list.sort(key=lambda t: t.get('points', 0), reverse=True)
    div_ranks = {}
    standings = {}
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
    data = fetch_json(f"{NHL_API_BASE}/club-stats/{team_abbrev}/now")
    if not data:
        return [], []
    return data.get('skaters', []), data.get('goalies', [])


def build_player_index(all_teams_data):
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


def normalize_name(name):
    nfkd = unicodedata.normalize('NFKD', name)
    return ''.join(c for c in nfkd if not unicodedata.combining(c)).strip().lower()


def match_player(player_name, skaters, goalies):
    if player_name in skaters:
        return skaters[player_name], 'skater'
    if player_name in goalies:
        return goalies[player_name], 'goalie'
    norm = normalize_name(player_name)
    for name, data in skaters.items():
        if normalize_name(name) == norm:
            return data, 'skater'
    for name, data in goalies.items():
        if normalize_name(name) == norm:
            return data, 'goalie'
    all_names = list(skaters.keys()) + list(goalies.keys())
    matches = get_close_matches(player_name, all_names, n=1, cutoff=0.85)
    if matches:
        m = matches[0]
        if m in skaters: return skaters[m], 'skater'
        if m in goalies:  return goalies[m], 'goalie'
    return None, None


def fetch_player_bio(nhl_id):
    data = fetch_json(f"{NHL_API_BASE}/player/{nhl_id}/landing")
    if not data:
        return None
    draft = data.get('draftDetails', {}) or {}
    def _str(field):
        v = data.get(field, '')
        return v.get('default', '') if isinstance(v, dict) else (v or '')
    return {
        'birth_country':         _str('birthCountry'),
        'birth_city':            _str('birthCity'),
        'birth_state_province':  _str('birthStateProvince'),
        'birth_date':            data.get('birthDate', ''),
        'draft_year':            draft.get('year'),
        'draft_round':           draft.get('round'),
        'draft_overall':         draft.get('overallPick'),
        'draft_team':            draft.get('teamAbbrev', ''),
        'height_inches':         data.get('heightInInches'),
        'weight_pounds':         data.get('weightInPounds'),
        'shoots_catches':        data.get('shootsCatches', ''),
    }


def build_player_entry(api_data, player_type, card_team, standings, existing=None):
    today = datetime.now().strftime('%Y-%m-%d')
    team = api_data['team']
    entry = {
        'nhl_id':       api_data['nhl_id'],
        'current_team': team,
        'position':     api_data['position'],
        'card_team':    card_team,
        'type':         player_type,
    }
    if player_type == 'skater':
        entry['current_season'] = {
            'games_played':       api_data['games_played'],
            'goals':              api_data['goals'],
            'assists':            api_data['assists'],
            'points':             api_data['points'],
            'plus_minus':         api_data['plus_minus'],
            'shots':              api_data['shots'],
            'shooting_pct':       api_data['shooting_pct'],
            'powerplay_goals':    api_data['powerplay_goals'],
            'game_winning_goals': api_data['game_winning_goals'],
        }
        snapshot = {
            'date': today,
            'games_played': api_data['games_played'],
            'goals':        api_data['goals'],
            'assists':      api_data['assists'],
            'points':       api_data['points'],
            'plus_minus':   api_data['plus_minus'],
        }
    else:
        ts = standings.get(team, {})
        entry['current_season'] = {
            'games_played':  api_data['games_played'],
            'games_started': api_data['games_started'],
            'wins':          api_data['wins'],
            'losses':        api_data['losses'],
            'otl':           api_data['otl'],
            'save_pct':      api_data['save_pct'],
            'gaa':           api_data['gaa'],
            'shutouts':      api_data['shutouts'],
        }
        entry['team_standings'] = {
            'team_points':  ts.get('points', 0),
            'league_rank':  ts.get('league_rank', 0),
            'division_rank': ts.get('division_rank', 0),
        }
        snapshot = {
            'date':         today,
            'games_played': api_data['games_played'],
            'wins':         api_data['wins'],
            'save_pct':     api_data['save_pct'],
            'gaa':          api_data['gaa'],
            'team_points':  ts.get('points', 0),
        }

    history = []
    if existing and 'history' in existing:
        history = [h for h in existing['history'] if h.get('date') != today]
    history.append(snapshot)
    history.sort(key=lambda x: x['date'])
    entry['history'] = history
    return entry


# ── DB helpers ────────────────────────────────────────────────────────────────

def load_nhl_players_from_catalog():
    """Return list of {player_name, team} dicts from card_catalog for NHL."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT player_name, team
                FROM card_catalog
                WHERE sport = 'NHL' AND player_name != ''
                ORDER BY player_name
            """)
            return [{'player_name': r[0], 'team': r[1]} for r in cur.fetchall()]


def load_existing_player_stats():
    """Load previously stored player stats from player_stats table."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT player, data FROM player_stats WHERE sport = 'NHL'")
            return {row[0]: row[1] for row in cur.fetchall()}


def save_to_db(matched: dict, standings: dict, args):
    """Upsert player stats and standings to PostgreSQL."""
    if args.dry_run:
        return

    with get_db() as conn:
        with conn.cursor() as cur:
            from psycopg2.extras import execute_values

            # Upsert player stats
            if matched:
                execute_values(cur, """
                    INSERT INTO player_stats (sport, player, data, updated_at)
                    VALUES %s
                    ON CONFLICT (sport, player) DO UPDATE SET
                        data       = EXCLUDED.data,
                        updated_at = NOW()
                """, [('NHL', name, json.dumps(data)) for name, data in matched.items()])

            # Upsert standings
            if standings:
                execute_values(cur, """
                    INSERT INTO standings (sport, team, data, updated_at)
                    VALUES %s
                    ON CONFLICT (sport, team) DO UPDATE SET
                        data       = EXCLUDED.data,
                        updated_at = NOW()
                """, [('NHL', team, json.dumps(data)) for team, data in standings.items()])

        conn.commit()

    print(f"  Saved {len(matched)} players to player_stats")
    print(f"  Saved {len(standings)} teams to standings")


def save_correlation_to_db(matched: dict, standings: dict):
    """Compute and save a price-vs-performance correlation snapshot."""
    try:
        # Get card prices from market_prices + card_catalog
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT cc.player_name, mp.fair_value
                    FROM card_catalog cc
                    JOIN market_prices mp ON mp.card_catalog_id = cc.id
                    WHERE cc.sport = 'NHL'
                    AND cc.is_rookie = TRUE
                    AND mp.fair_value > 0
                    AND mp.confidence NOT IN ('none', '')
                """)
                price_rows = cur.fetchall()

        if not price_rows:
            print("  Skipping correlation — no market_prices data yet")
            return

        # Build player → avg_price map
        player_prices: dict = {}
        for player, value in price_rows:
            if player not in player_prices:
                player_prices[player] = []
            player_prices[player].append(float(value))
        player_avg = {p: sum(v) / len(v) for p, v in player_prices.items()}

        # Build skater correlation data
        skater_data = []
        for name, entry in matched.items():
            if entry.get('type') != 'skater':
                continue
            price = player_avg.get(name)
            if not price:
                continue
            cs = entry.get('current_season', {})
            skater_data.append({
                'player': name,
                'price': price,
                'points': cs.get('points', 0),
                'goals': cs.get('goals', 0),
                'games_played': cs.get('games_played', 0),
            })

        if len(skater_data) < 5:
            print(f"  Skipping correlation — only {len(skater_data)} skaters with prices")
            return

        # Simple Pearson r
        def pearson_r(xs, ys):
            n = len(xs)
            if n < 2: return 0
            mx, my = sum(xs)/n, sum(ys)/n
            num = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
            den = (sum((x-mx)**2 for x in xs) * sum((y-my)**2 for y in ys)) ** 0.5
            return round(num/den, 4) if den else 0

        prices = [d['price'] for d in skater_data]
        points = [d['points'] for d in skater_data]
        goals  = [d['goals'] for d in skater_data]

        snapshot = {
            'meta': {
                'date': date.today().isoformat(),
                'skaters_with_price': len(skater_data),
            },
            'correlations': {
                'points_vs_price': {'r': pearson_r(points, prices)},
                'goals_vs_price':  {'r': pearson_r(goals, prices)},
            },
        }

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO rookie_correlation_history (sport, date, data)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (sport, date) DO UPDATE SET data = EXCLUDED.data
                """, ('NHL', date.today(), json.dumps(snapshot)))
            conn.commit()

        pts_r = snapshot['correlations']['points_vs_price']['r']
        goals_r = snapshot['correlations']['goals_vs_price']['r']
        n = snapshot['meta']['skaters_with_price']
        print(f"  Correlation saved: points r={pts_r}, goals r={goals_r} (n={n})")

    except Exception as e:
        print(f"  WARNING: Correlation snapshot failed: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Scrape NHL player stats → PostgreSQL")
    parser.add_argument('--fetch-bios', action='store_true', help="Fetch birth/draft bios")
    parser.add_argument('--dry-run',    action='store_true', help="Print without saving")
    parser.add_argument('--verbose',    action='store_true', help="Detailed match output")
    args = parser.parse_args()

    print("=" * 60)
    print("NHL PLAYER STATS SCRAPER")
    print("=" * 60)

    # Step 1: Fetch standings
    print("\nFetching NHL standings...")
    standings = fetch_standings()
    if not standings:
        print("ERROR: Could not fetch standings.")
        sys.exit(1)
    print(f"  {len(standings)} teams")

    # Step 2: Fetch all team rosters
    print(f"\nFetching roster stats for {len(standings)} teams...")
    all_teams_data = {}
    for i, abbrev in enumerate(sorted(standings.keys())):
        skaters, goalies = fetch_team_stats(abbrev)
        all_teams_data[abbrev] = (skaters, goalies)
        if args.verbose:
            print(f"  [{i+1}/{len(standings)}] {abbrev}: {len(skaters)} skaters, {len(goalies)} goalies")
        if i < len(standings) - 1:
            time.sleep(0.3)

    skaters_idx, goalies_idx = build_player_index(all_teams_data)
    print(f"  {len(skaters_idx)} skaters, {len(goalies_idx)} goalies indexed")

    # Step 3: Load players from card_catalog
    print("\nLoading NHL players from card_catalog...")
    catalog_players = load_nhl_players_from_catalog()
    print(f"  {len(catalog_players):,} distinct players")

    existing_stats = load_existing_player_stats()
    print(f"  {len(existing_stats)} players already in player_stats")

    # Step 4: Match players
    print("\nMatching players...")
    matched = {}
    unmatched = []

    seen = set()
    for row in catalog_players:
        player_name = row['player_name']
        if player_name in seen:
            continue
        seen.add(player_name)

        card_team = (row['team'] or '').split('/')[0].strip()
        api_data, player_type = match_player(player_name, skaters_idx, goalies_idx)

        if api_data:
            entry = build_player_entry(
                api_data, player_type, card_team, standings,
                existing=existing_stats.get(player_name),
            )
            # Preserve existing bio
            if player_name in existing_stats and existing_stats[player_name].get('bio'):
                entry['bio'] = existing_stats[player_name]['bio']
            matched[player_name] = entry
            if args.verbose:
                if player_type == 'skater':
                    print(f"  MATCH: {player_name} ({api_data['team']}) — {api_data['points']}pts")
                else:
                    print(f"  MATCH: {player_name} ({api_data['team']}) — {api_data['wins']}W {api_data['save_pct']:.3f}SV%")
        else:
            unmatched.append(player_name)
            if args.verbose:
                print(f"  MISS:  {player_name}")

    # Also keep previously matched players not in current candidates
    for name, entry in existing_stats.items():
        if name not in matched:
            matched[name] = entry

    total = len(matched) + len(unmatched)
    print(f"  Matched:   {len(matched)}")
    print(f"  Unmatched: {len(unmatched)}")
    print(f"  Match rate: {len(matched)/total*100:.1f}%")

    if args.dry_run:
        print("\n[DRY RUN] Not saving.")
        for p in unmatched[:20]:
            print(f"  MISS: {p}")
        return

    # Step 5: Save to DB
    print("\nSaving to PostgreSQL...")
    save_to_db(matched, standings, args)

    # Step 6: Fetch bios
    if args.fetch_bios:
        print("\nFetching player bios...")
        fetched = skipped = errors = 0
        for name, entry in matched.items():
            nhl_id = entry.get('nhl_id')
            if not nhl_id:
                continue
            if entry.get('bio', {}).get('birth_country'):
                skipped += 1
                continue
            bio = fetch_player_bio(nhl_id)
            if bio:
                entry['bio'] = bio
                fetched += 1
                if args.verbose:
                    print(f"  BIO: {name} — {bio.get('birth_country', '?')}")
            else:
                errors += 1
            time.sleep(0.3)
        print(f"  Fetched {fetched}, cached {skipped}, errors {errors}")
        # Re-save with bios
        save_to_db(matched, standings, args)

    # Step 7: Correlation snapshot
    print("\nComputing price-vs-performance correlations...")
    save_correlation_to_db(matched, standings)

    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)


if __name__ == '__main__':
    main()
