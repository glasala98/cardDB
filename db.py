"""PostgreSQL connection pool for CardDB.

Uses a psycopg2 ThreadedConnectionPool backed by DATABASE_URL from the
environment.  Import ``get_db`` as a context manager that yields a
connection, commits on clean exit, and rolls back on exception.
"""
import os
import psycopg2
import psycopg2.pool
import psycopg2.extras
from contextlib import contextmanager
from datetime import datetime
import hashlib

_pool = None


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(1, 10, os.environ["DATABASE_URL"])
    return _pool


@contextmanager
def get_db():
    """Yield a psycopg2 connection from the pool.

    Commits on clean exit, rolls back on exception, always returns the
    connection to the pool.  Example::

        from db import get_db
        from psycopg2.extras import RealDictCursor

        with get_db() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM cards WHERE user_id = %s", (username,))
                rows = cur.fetchall()
    """
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def _sale_hash(card_catalog_id: int, sold_date, title: str) -> str:
    """Deterministic hash that uniquely identifies one eBay sold listing.

    Keyed on (card_catalog_id, sold_date, title) — no two real sales share
    the same card, date, and listing title.  NULL sold_date is replaced with
    empty string so the hash is always defined.
    """
    raw = f"{card_catalog_id}|{sold_date or ''}|{title.strip().lower()}"
    return hashlib.md5(raw.encode()).hexdigest()


def save_raw_sales(card_catalog_id: int, raw_sales: list, conn=None) -> int:
    """Insert individual eBay sold listings into market_raw_sales.

    Deduplicates on listing_hash — an md5 of (card_catalog_id, sold_date,
    title, price_val) computed in Python before insert.  NULL-safe: undated
    sales with the same title and price are treated as the same listing.
    Returns the number of new rows inserted.

    Args:
        card_catalog_id: FK to card_catalog.id
        raw_sales: list of dicts with keys price_val, sold_date, title,
                   and optionally shipping (raw shipping value as float)
        conn: optional existing psycopg2 connection (uses pool if not provided)
    """
    if not raw_sales:
        return 0

    rows = []
    now = datetime.utcnow()
    for sale in raw_sales:
        price_val = sale.get('price_val') or sale.get('price')
        if not price_val:
            continue
        price_val = float(price_val)
        sold_date = sale.get('sold_date')       # 'YYYY-MM-DD' string or None
        title = (sale.get('title') or '')[:500]

        # Parse shipping — scraper stores it as "$3.50" string or 0.0 float
        raw_ship = sale.get('shipping', 0)
        if isinstance(raw_ship, str):
            import re
            m = re.search(r'[\d.]+', raw_ship)
            shipping_val = float(m.group()) if m else 0.0
        else:
            shipping_val = float(raw_ship or 0)

        listing_hash = _sale_hash(card_catalog_id, sold_date, title)
        rows.append((card_catalog_id, sold_date, price_val, shipping_val, title,
                     listing_hash, now))

    if not rows:
        return 0

    sql = """
        INSERT INTO market_raw_sales
            (card_catalog_id, sold_date, price_val, shipping_val, title, listing_hash, scraped_at)
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
