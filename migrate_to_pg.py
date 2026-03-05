#!/usr/bin/env python3
"""One-time migration: read all CSV/JSON data files → insert into local PostgreSQL.

Run from the project root AFTER:
1. Installing PostgreSQL and creating the database
2. Running schema.sql against the database
3. Setting DATABASE_URL in your environment (or .env)

Usage:
    python migrate_to_pg.py
    python migrate_to_pg.py --dry-run   # print counts without writing
    python migrate_to_pg.py --user admin  # migrate only one user
"""

import os
import sys
import json
import csv
import argparse
import math
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

SCRIPT_DIR = Path(__file__).parent
DATA_ROOT = SCRIPT_DIR / "data"
MASTER_DB_DIR = DATA_ROOT / "master_db"

CHUNK = 500  # rows per batch


def _chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def _clean_numeric(val):
    """Convert a value to float, stripping $ and commas.  Returns None on failure."""
    if val is None or val == '' or (isinstance(val, float) and math.isnan(val)):
        return None
    s = str(val).replace('$', '').replace(',', '').strip()
    if s.startswith("'") and len(s) > 1 and s[1] in ('=', '+', '-', '@'):
        s = s[1:]
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _clean_str(val):
    """Strip leading single-quote CSV-injection guard from string values."""
    if not isinstance(val, str):
        return val or ''
    if len(val) > 1 and val[0] == "'" and val[1] in ('=', '+', '-', '@'):
        return val[1:]
    return val


def _upsert(cur, table, cols, rows, conflict):
    """Batch-upsert rows into table using execute_values."""
    from psycopg2.extras import execute_values
    col_list   = ', '.join(cols)
    update_set = ', '.join(f"{c} = EXCLUDED.{c}" for c in cols if c not in conflict.split(','))
    sql = f"""
        INSERT INTO {table} ({col_list})
        VALUES %s
        ON CONFLICT ({conflict}) DO UPDATE SET {update_set}
    """
    for chunk in _chunks(rows, CHUNK):
        execute_values(cur, sql, chunk)


def _insert(cur, table, cols, rows):
    """Batch-insert rows (no conflict check)."""
    from psycopg2.extras import execute_values
    col_list = ', '.join(cols)
    sql = f"INSERT INTO {table} ({col_list}) VALUES %s"
    for chunk in _chunks(rows, CHUNK):
        execute_values(cur, sql, chunk)


def migrate_user(username: str, conn, dry_run: bool):
    """Migrate one user's card data files into PostgreSQL."""
    user_dir = DATA_ROOT / username
    if not user_dir.is_dir():
        return

    print(f"\n-- Migrating user: {username} --")

    # ── 1. cards (card_prices_summary.csv) ───────────────────────────────
    summary_path = user_dir / "card_prices_summary.csv"
    if summary_path.exists():
        with open(summary_path, newline='', encoding='utf-8') as f:
            rows_raw = list(csv.DictReader(f))

        rows = [
            (username,
             _clean_str(r.get('Card Name', '')),
             _clean_numeric(r.get('Fair Value')),
             _clean_str(r.get('Trend', 'no data')),
             _clean_str(r.get('Top 3 Prices', '')),
             _clean_numeric(r.get('Median (All)')),
             _clean_numeric(r.get('Min')),
             _clean_numeric(r.get('Max')),
             int(_clean_numeric(r.get('Num Sales')) or 0),
             _clean_str(r.get('Tags', '')),
             _clean_numeric(r.get('Cost Basis')),
             _clean_str(r.get('Purchase Date', '')),
             False)
            for r in rows_raw
        ]
        cols = ['user_id', 'card_name', 'fair_value', 'trend', 'top_3_prices',
                'median_all', 'min_price', 'max_price', 'num_sales', 'tags',
                'cost_basis', 'purchase_date', 'archived']
        print(f"  cards: {len(rows)} rows")
        if not dry_run:
            with conn.cursor() as cur:
                _upsert(cur, 'cards', cols, rows, 'user_id,card_name')

    # Also migrate archived cards (card_archive.csv)
    archive_path = user_dir / "card_archive.csv"
    if archive_path.exists():
        with open(archive_path, newline='', encoding='utf-8') as f:
            arch_raw = list(csv.DictReader(f))

        arch_rows = [
            (username,
             _clean_str(r.get('Card Name', '')),
             _clean_numeric(r.get('Fair Value')),
             _clean_str(r.get('Trend', 'no data')),
             _clean_str(r.get('Top 3 Prices', '')),
             _clean_numeric(r.get('Median (All)')),
             _clean_numeric(r.get('Min')),
             _clean_numeric(r.get('Max')),
             int(_clean_numeric(r.get('Num Sales')) or 0),
             _clean_str(r.get('Tags', '')),
             _clean_numeric(r.get('Cost Basis')),
             _clean_str(r.get('Purchase Date', '')),
             True,
             _clean_str(r.get('Archived Date', '')) or None)
            for r in arch_raw
        ]
        arch_cols = ['user_id', 'card_name', 'fair_value', 'trend', 'top_3_prices',
                     'median_all', 'min_price', 'max_price', 'num_sales', 'tags',
                     'cost_basis', 'purchase_date', 'archived', 'archived_date']
        print(f"  archived cards: {len(arch_rows)} rows")
        if not dry_run:
            with conn.cursor() as cur:
                _upsert(cur, 'cards', arch_cols, arch_rows, 'user_id,card_name')

    # ── 2. card_results (card_prices_results.json) ────────────────────────
    results_path = user_dir / "card_prices_results.json"
    if results_path.exists():
        with open(results_path, encoding='utf-8') as f:
            results = json.load(f)

        res_rows = [
            (username,
             card_name,
             json.dumps(data.get('raw_sales', [])),
             data.get('scraped_at'),
             data.get('confidence', ''),
             data.get('image_url', ''),
             data.get('image_hash', ''),
             data.get('image_url_back', ''),
             data.get('search_url', ''),
             bool(data.get('is_estimated', False)),
             data.get('price_source', 'direct'))
            for card_name, data in results.items()
        ]
        res_cols = ['user_id', 'card_name', 'raw_sales', 'scraped_at', 'confidence',
                    'image_url', 'image_hash', 'image_url_back', 'search_url',
                    'is_estimated', 'price_source']
        print(f"  card_results: {len(res_rows)} rows")
        if not dry_run:
            with conn.cursor() as cur:
                _upsert(cur, 'card_results', res_cols, res_rows, 'user_id,card_name')

    # ── 3. card_price_history (price_history.json) ────────────────────────
    ph_path = user_dir / "price_history.json"
    if ph_path.exists():
        with open(ph_path, encoding='utf-8') as f:
            ph = json.load(f)

        ph_dedup = {}
        for card_name, entries in ph.items():
            for entry in entries:
                date = entry.get('date')
                if not date:
                    continue
                key = (username, card_name, date)
                ph_dedup[key] = (
                    username, card_name, date,
                    _clean_numeric(entry.get('fair_value')) or 0,
                    int(entry.get('num_sales') or 0),
                )
        ph_rows = list(ph_dedup.values())
        print(f"  card_price_history: {len(ph_rows)} rows")
        if not dry_run:
            with conn.cursor() as cur:
                _upsert(cur, 'card_price_history',
                        ['user_id', 'card_name', 'date', 'price', 'num_sales'],
                        ph_rows, 'user_id,card_name,date')

    # ── 4. portfolio_history (portfolio_history.json) ─────────────────────
    port_path = user_dir / "portfolio_history.json"
    if port_path.exists():
        with open(port_path, encoding='utf-8') as f:
            port = json.load(f)

        port_rows = [
            (username,
             e.get('date'),
             _clean_numeric(e.get('total_value')) or 0,
             int(e.get('total_cards') or 0),
             _clean_numeric(e.get('avg_value')) or 0)
            for e in port if e.get('date')
        ]
        print(f"  portfolio_history: {len(port_rows)} rows")
        if not dry_run:
            with conn.cursor() as cur:
                _upsert(cur, 'portfolio_history',
                        ['user_id', 'date', 'total_value', 'total_cards', 'avg_value'],
                        port_rows, 'user_id,date')


def migrate_master_db(conn, dry_run: bool):
    """Migrate young_guns.csv and all related master-DB JSON files."""
    print("\n-- Migrating Master DB --")

    # ── young_guns.csv → rookie_cards ─────────────────────────────────────
    yg_path = MASTER_DB_DIR / "young_guns.csv"
    if yg_path.exists():
        with open(yg_path, newline='', encoding='utf-8') as f:
            yg_raw = list(csv.DictReader(f))

        yg_dedup = {}
        for r in yg_raw:
            player = _clean_str(r.get('PlayerName', ''))
            season = _clean_str(str(r.get('Season', '')))
            card_name = _clean_str(r.get('CardName', ''))
            cleaned = {k: _clean_str(v) for k, v in r.items()}
            yg_dedup[('NHL', player, season)] = (
                'NHL', player, season, card_name, json.dumps(cleaned)
            )
        yg_rows = list(yg_dedup.values())
        print(f"  rookie_cards: {len(yg_rows)} rows")
        if not dry_run:
            with conn.cursor() as cur:
                _upsert(cur, 'rookie_cards',
                        ['sport', 'player', 'season', 'card_name', 'row_data'],
                        yg_rows, 'sport,player,season')

    # ── yg_price_history.json → rookie_price_history ──────────────────────
    yg_ph_path = MASTER_DB_DIR / "yg_price_history.json"
    if yg_ph_path.exists():
        with open(yg_ph_path, encoding='utf-8') as f:
            yg_ph = json.load(f)

        ph_dedup = {}
        for card_name, entries in yg_ph.items():
            for entry in entries:
                date = entry.get('date')
                if not date:
                    continue
                key = ('NHL', card_name, '', date)
                ph_dedup[key] = (
                    'NHL', card_name, '', date,
                    _clean_numeric(entry.get('fair_value')) or 0,
                    int(entry.get('num_sales') or 0),
                    json.dumps(entry.get('graded', {})),
                )
        ph_rows = list(ph_dedup.values())
        print(f"  rookie_price_history: {len(ph_rows)} rows")
        if not dry_run:
            with conn.cursor() as cur:
                _upsert(cur, 'rookie_price_history',
                        ['sport', 'player', 'season', 'date',
                         'fair_value', 'num_sales', 'graded_data'],
                        ph_rows, 'sport,player,season,date')

    # ── yg_portfolio_history.json → rookie_portfolio_history ──────────────
    yg_port_path = MASTER_DB_DIR / "yg_portfolio_history.json"
    if yg_port_path.exists():
        with open(yg_port_path, encoding='utf-8') as f:
            yg_port = json.load(f)

        port_rows = [
            ('NHL', e.get('date'),
             _clean_numeric(e.get('total_value')) or 0,
             int(e.get('total_cards') or 0),
             _clean_numeric(e.get('avg_value')) or 0,
             int(e.get('cards_scraped') or 0))
            for e in yg_port if e.get('date')
        ]
        print(f"  rookie_portfolio_history: {len(port_rows)} rows")
        if not dry_run:
            with conn.cursor() as cur:
                _upsert(cur, 'rookie_portfolio_history',
                        ['sport', 'date', 'total_value', 'total_cards',
                         'avg_value', 'cards_scraped'],
                        port_rows, 'sport,date')

    # ── yg_raw_sales.json → rookie_raw_sales ──────────────────────────────
    yg_sales_path = MASTER_DB_DIR / "yg_raw_sales.json"
    if yg_sales_path.exists():
        with open(yg_sales_path, encoding='utf-8') as f:
            yg_sales = json.load(f)

        sales_rows = [
            ('NHL', card_name, '', s['sold_date'], float(s['price_val']), s.get('title', ''))
            for card_name, sales in yg_sales.items()
            for s in sales
            if s.get('sold_date') and s.get('price_val')
        ]
        print(f"  rookie_raw_sales: {len(sales_rows)} rows")
        if not dry_run:
            with conn.cursor() as cur:
                _insert(cur, 'rookie_raw_sales',
                        ['sport', 'player', 'season', 'sold_date', 'price_val', 'title'],
                        sales_rows)

    # ── nhl_player_stats.json → player_stats + standings ──────────────────
    nhl_path = MASTER_DB_DIR / "nhl_player_stats.json"
    if nhl_path.exists():
        with open(nhl_path, encoding='utf-8') as f:
            nhl_data = json.load(f)

        player_rows = [
            ('NHL', name, json.dumps(pdata))
            for name, pdata in nhl_data.get('players', {}).items()
        ]
        print(f"  player_stats: {len(player_rows)} rows")
        if not dry_run:
            with conn.cursor() as cur:
                _upsert(cur, 'player_stats', ['sport', 'player', 'data'],
                        player_rows, 'sport,player')

        standing_rows = [
            ('NHL', team, json.dumps(sdata))
            for team, sdata in nhl_data.get('standings', {}).items()
        ]
        print(f"  standings: {len(standing_rows)} rows")
        if not dry_run:
            with conn.cursor() as cur:
                _upsert(cur, 'standings', ['sport', 'team', 'data'],
                        standing_rows, 'sport,team')

    # ── yg_correlation_history.json → rookie_correlation_history ──────────
    corr_path = MASTER_DB_DIR / "yg_correlation_history.json"
    if corr_path.exists():
        with open(corr_path, encoding='utf-8') as f:
            corr = json.load(f)

        corr_rows = [
            ('NHL', date_str, json.dumps(snapshot))
            for date_str, snapshot in corr.items()
            if date_str
        ]
        print(f"  rookie_correlation_history: {len(corr_rows)} rows")
        if not dry_run:
            with conn.cursor() as cur:
                _upsert(cur, 'rookie_correlation_history',
                        ['sport', 'date', 'data'],
                        corr_rows, 'sport,date')


def main():
    parser = argparse.ArgumentParser(description="Migrate CardDB files to local PostgreSQL")
    parser.add_argument('--dry-run', action='store_true',
                        help="Print row counts without writing to PostgreSQL")
    parser.add_argument('--user', type=str, default=None,
                        help="Migrate only this user (default: all users)")
    args = parser.parse_args()

    if args.dry_run:
        print("DRY RUN -- no data will be written to PostgreSQL")
        conn = None
    else:
        from db import get_db
        _conn_ctx = get_db()
        conn = _conn_ctx.__enter__()
        print("Connected to PostgreSQL")

    if not DATA_ROOT.exists():
        print(f"Data directory not found: {DATA_ROOT}")
        sys.exit(1)

    try:
        if args.user:
            migrate_user(args.user, conn, args.dry_run)
        else:
            for entry in sorted(DATA_ROOT.iterdir()):
                if entry.is_dir() and entry.name != 'master_db':
                    migrate_user(entry.name, conn, args.dry_run)

        migrate_master_db(conn, args.dry_run)

        if conn:
            conn.commit()
            _conn_ctx.__exit__(None, None, None)
    except Exception as e:
        if conn:
            _conn_ctx.__exit__(type(e), e, e.__traceback__)
        raise

    print("\nMigration complete.")
    if args.dry_run:
        print("Run without --dry-run to write data to PostgreSQL.")


if __name__ == '__main__':
    main()
