"""
backup_db.py — Local PostgreSQL backup.

Tries pg_dump first (fastest, complete). Falls back to a Python/psycopg2
COPY-TO-CSV backup if pg_dump is not on PATH.

Usage:
    python backup_db.py                        # full backup (all tables)
    python backup_db.py --tables cards collection market_prices
    python backup_db.py --keep 7               # retain last 7 backups (default: 10)
    python backup_db.py --method python        # force Python fallback

Output: db_backups/carddb_<timestamp>/   (one .csv.gz per table)
        or db_backups/carddb_full_<timestamp>.sql.gz  (pg_dump)
"""

import csv
import gzip
import io
import os
import shutil
import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path='.env')
except ImportError:
    pass

import psycopg2

BACKUP_DIR = Path('db_backups')

ALL_TABLES = [
    'cards', 'card_results', 'card_price_history', 'portfolio_history',
    'collection',
    'card_catalog', 'market_prices', 'market_price_history',
    'rookie_cards', 'rookie_price_history', 'rookie_portfolio_history',
    'rookie_raw_sales', 'player_stats', 'standings', 'rookie_correlation_history',
]


def parse_db_url(url: str) -> dict:
    p = urlparse(url)
    return {
        'host':     p.hostname,
        'port':     str(p.port or 5432),
        'dbname':   p.path.lstrip('/'),
        'user':     p.username,
        'password': p.password,
    }


def backup_pgdump(db_url: str, tables: list[str] | None, timestamp: str) -> Path:
    db = parse_db_url(db_url)
    suffix = '_' + '_'.join(tables) if tables else '_full'
    sql_file = BACKUP_DIR / f'carddb{suffix}_{timestamp}.sql'
    gz_file  = sql_file.with_suffix('.sql.gz')

    cmd = ['pg_dump', '-h', db['host'], '-p', db['port'],
           '-U', db['user'], '-d', db['dbname'], '--no-password',
           '--format=plain', '--encoding=UTF8']
    for t in (tables or []):
        cmd += ['-t', t]

    env = os.environ.copy()
    env['PGPASSWORD'] = db['password'] or ''

    with open(sql_file, 'w', encoding='utf-8') as f:
        result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, env=env, text=True)

    if result.returncode != 0:
        sql_file.unlink(missing_ok=True)
        raise RuntimeError(f'pg_dump failed:\n{result.stderr}')

    with open(sql_file, 'rb') as f_in, gzip.open(gz_file, 'wb') as f_out:
        shutil.copyfileobj(f_in, f_out)
    sql_file.unlink()

    return gz_file


def backup_python(db_url: str, tables: list[str] | None, timestamp: str) -> Path:
    """Dump each table to a gzip-compressed CSV. No external tools required."""
    out_dir = BACKUP_DIR / f'carddb_{timestamp}'
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = psycopg2.connect(db_url)
    cur  = conn.cursor()

    target_tables = tables or ALL_TABLES
    total_rows = 0

    for table in target_tables:
        # Check if table exists
        cur.execute("SELECT to_regclass(%s)", [f'public.{table}'])
        if cur.fetchone()[0] is None:
            print(f'  [skip] {table} — not found')
            continue

        gz_path = out_dir / f'{table}.csv.gz'
        buf = io.StringIO()
        writer = csv.writer(buf)

        cur.execute(f'SELECT * FROM {table}')
        cols = [d[0] for d in cur.description]
        writer.writerow(cols)

        rows = cur.fetchall()
        for row in rows:
            writer.writerow([str(v) if v is not None else '' for v in row])

        compressed = gzip.compress(buf.getvalue().encode('utf-8'))
        gz_path.write_bytes(compressed)

        size_kb = gz_path.stat().st_size / 1024
        print(f'  {table:<35} {len(rows):>8,} rows  {size_kb:>7.1f} KB')
        total_rows += len(rows)

    cur.close()
    conn.close()

    # Write a manifest
    manifest = out_dir / 'manifest.txt'
    manifest.write_text(
        f'CardDB backup\nTimestamp: {timestamp}\n'
        f'Tables: {", ".join(target_tables)}\n'
        f'Total rows: {total_rows:,}\n'
        f'Restore: psql $DATABASE_URL < <(zcat <table>.csv.gz) or use restore_db.py\n'
    )

    return out_dir


def prune_backups(keep: int):
    # Prune both .sql.gz files and directories
    items = sorted(
        [p for p in BACKUP_DIR.iterdir() if p.name.startswith('carddb')],
        key=lambda p: p.stat().st_mtime
    )
    if len(items) > keep:
        for old in items[:-keep]:
            if old.is_dir():
                shutil.rmtree(old)
            else:
                old.unlink()
            print(f'Removed old backup: {old.name}')


def main():
    parser = argparse.ArgumentParser(description='Backup CardDB PostgreSQL database locally.')
    parser.add_argument('--tables', nargs='+', metavar='TABLE',
                        help='Specific tables (default: all)')
    parser.add_argument('--keep', type=int, default=10,
                        help='Number of backups to retain (default: 10)')
    parser.add_argument('--method', choices=['auto', 'pgdump', 'python'], default='auto',
                        help='Backup method (default: auto — pg_dump if available, else Python)')
    args = parser.parse_args()

    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        sys.exit('DATABASE_URL not set. Add it to .env or export it.')

    BACKUP_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    use_pgdump = args.method == 'pgdump' or (
        args.method == 'auto' and shutil.which('pg_dump') is not None
    )

    tables_label = ', '.join(args.tables) if args.tables else 'all tables'
    print(f'\nCardDB Backup — {timestamp}')
    print(f'Tables:  {tables_label}')
    print(f'Method:  {"pg_dump" if use_pgdump else "Python/psycopg2 CSV"}')
    print()

    try:
        if use_pgdump:
            out = backup_pgdump(db_url, args.tables, timestamp)
            size_mb = out.stat().st_size / 1_048_576
            print(f'Done — {out.name}  ({size_mb:.1f} MB)')
        else:
            out = backup_python(db_url, args.tables, timestamp)
            total_mb = sum(f.stat().st_size for f in out.iterdir()) / 1_048_576
            print(f'\nDone — {out.name}/  ({total_mb:.1f} MB total)')
    except Exception as e:
        sys.exit(f'Backup failed: {e}')

    prune_backups(args.keep)
    print(f'Backups retained: {args.keep}')


if __name__ == '__main__':
    main()
