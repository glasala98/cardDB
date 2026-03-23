"""PostgreSQL connection pool for CardDB.

Uses a psycopg2 ThreadedConnectionPool backed by DATABASE_URL from the
environment.  Import ``get_db`` as a context manager that yields a
connection, commits on clean exit, and rolls back on exception.
"""
import os
import time
import psycopg2
import psycopg2.pool
import psycopg2.extras
from contextlib import contextmanager
from datetime import datetime
import hashlib

_pool = None
_DB_RETRIES = 3
_DB_RETRY_DELAY = 5  # seconds between retries


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(1, 5, os.environ["DATABASE_URL"])
    return _pool


def _reset_pool():
    """Close the pool and force a fresh one on next use."""
    global _pool
    try:
        if _pool:
            _pool.closeall()
    except Exception:
        pass
    _pool = None


@contextmanager
def get_db():
    """Yield a psycopg2 connection from the pool.

    Retries up to _DB_RETRIES times on SSL/connection errors — handles
    'SSL SYSCALL error: EOF detected' and 'connection already closed'
    which occur when the DB drops idle connections under heavy load.
    """
    last_err = None
    for attempt in range(_DB_RETRIES):
        try:
            pool = _get_pool()
            conn = pool.getconn()
            # Verify connection is alive before handing it out
            if conn.closed:
                pool.putconn(conn, close=True)
                raise psycopg2.OperationalError("connection is closed")
            try:
                yield conn
                conn.commit()
                return
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise
            finally:
                try:
                    pool.putconn(conn)
                except Exception:
                    pass
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            last_err = e
            print(f"[db] connection error (attempt {attempt + 1}/{_DB_RETRIES}): {e} — retrying in {_DB_RETRY_DELAY}s")
            _reset_pool()
            time.sleep(_DB_RETRY_DELAY)
    raise last_err


def _sale_hash(card_catalog_id: int, sold_date, title: str) -> str:
    """Deterministic hash that uniquely identifies one eBay sold listing.

    Keyed on (card_catalog_id, sold_date, title) — no two real sales share
    the same card, date, and listing title.  NULL sold_date is replaced with
    empty string so the hash is always defined.
    """
    raw = f"{card_catalog_id}|{sold_date or ''}|{title.strip().lower()}"
    return hashlib.md5(raw.encode()).hexdigest()


def save_raw_sales(card_catalog_id: int, raw_sales: list, conn=None,
                   source: str = 'ebay') -> int:
    """Insert sold listings into market_raw_sales (all sources).

    Deduplicates on listing_hash — an md5 of (card_catalog_id, sold_date,
    title) computed in Python before insert.  NULL-safe: undated sales with
    the same title are treated as the same listing.
    Returns the number of new rows inserted.

    Args:
        card_catalog_id: FK to card_catalog.id
        raw_sales: list of dicts with keys:
            Required: price_val, title
            Optional: sold_date, shipping (string or float),
                      source, grade, grade_company, grade_numeric,
                      serial_number, print_run, lot_url, lot_id,
                      hammer_price, buyer_premium_pct, image_url,
                      is_auction, raw_metadata (dict)
        conn:   optional existing psycopg2 connection (uses pool if not given)
        source: default source tag when not specified per-sale ('ebay')
    """
    import re as _re
    import json

    if not raw_sales:
        return 0

    # Lazy-import parser to avoid circular imports in scraper scripts
    try:
        from auction_title_parser import parse_title as _parse_title
    except ImportError:
        _parse_title = None

    rows = []
    now = datetime.utcnow()
    for sale in raw_sales:
        price_val = sale.get('price_val') or sale.get('price')
        if not price_val:
            continue
        price_val = float(price_val)
        sold_date = sale.get('sold_date')       # 'YYYY-MM-DD' string or None
        title = (sale.get('title') or '')[:500]

        # Skip eBay boilerplate scraping artifacts
        _tl = title.lower()
        if 'opens in a new window' in _tl or 'new window or tab' in _tl:
            continue

        # Shipping — "$3.50" string or numeric float
        raw_ship = sale.get('shipping', 0)
        if isinstance(raw_ship, str):
            m = _re.search(r'[\d.]+', raw_ship)
            shipping_val = float(m.group()) if m else 0.0
        else:
            shipping_val = float(raw_ship or 0)

        # Normalized fields — use sale-level values or parse from title
        parsed = _parse_title(title) if _parse_title else {}
        row_source       = sale.get('source') or source
        grade            = sale.get('grade')            or parsed.get('grade')
        grade_company    = sale.get('grade_company')    or parsed.get('grade_company')
        grade_numeric    = sale.get('grade_numeric')    or parsed.get('grade_numeric')
        serial_number    = sale.get('serial_number')    or parsed.get('serial_number')
        print_run        = sale.get('print_run')        or parsed.get('print_run')
        lot_url          = (sale.get('lot_url')  or '')[:2000]
        lot_id           = (sale.get('lot_id')   or '')[:200]
        hammer_price     = sale.get('hammer_price')
        buyer_prem       = sale.get('buyer_premium_pct')
        image_url        = (sale.get('image_url') or '')[:2000]
        is_auction       = bool(sale.get('is_auction', False))
        raw_meta         = sale.get('raw_metadata') or {}
        raw_meta_json    = json.dumps(raw_meta) if isinstance(raw_meta, dict) else (raw_meta or '{}')

        listing_hash = _sale_hash(card_catalog_id, sold_date, title)
        rows.append((
            card_catalog_id, sold_date, price_val, shipping_val, title,
            listing_hash, now, row_source,
            grade, grade_company, grade_numeric,
            serial_number, print_run,
            lot_url, lot_id,
            hammer_price, buyer_prem, image_url,
            is_auction, raw_meta_json,
        ))

    if not rows:
        return 0

    sql = """
        INSERT INTO market_raw_sales (
            card_catalog_id, sold_date, price_val, shipping_val, title,
            listing_hash, scraped_at, source,
            grade, grade_company, grade_numeric,
            serial_number, print_run,
            lot_url, lot_id,
            hammer_price, buyer_premium_pct, image_url,
            is_auction, raw_metadata
        )
        VALUES %s
        ON CONFLICT (listing_hash) DO NOTHING
    """

    def _run(c):
        with c.cursor() as cur:
            psycopg2.extras.execute_values(cur, sql, rows)
            return cur.rowcount

    if conn is not None:
        return _run(conn)

    with get_db() as c:
        return _run(c)
