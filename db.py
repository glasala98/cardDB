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


def save_raw_sales(card_catalog_id: int, raw_sales: list, conn=None) -> int:
    """Insert individual eBay sold listings into market_raw_sales.

    Deduplicates on (card_catalog_id, sold_date, title) so re-scraping the
    same card never creates duplicate rows.  Returns the number of new rows
    inserted.

    Args:
        card_catalog_id: FK to card_catalog.id
        raw_sales: list of dicts with keys price_val, sold_date, title
        conn: optional existing psycopg2 connection (uses pool if not provided)
    """
    if not raw_sales:
        return 0

    rows = []
    now = datetime.utcnow()
    for sale in raw_sales:
        price = sale.get('price_val') or sale.get('price')
        if not price:
            continue
        sold_date = sale.get('sold_date')  # already 'YYYY-MM-DD' string or None
        title = (sale.get('title') or '')[:500]  # cap at 500 chars
        rows.append((card_catalog_id, sold_date, float(price), title, now))

    if not rows:
        return 0

    sql = """
        INSERT INTO market_raw_sales (card_catalog_id, sold_date, price_val, title, scraped_at)
        VALUES %s
        ON CONFLICT (card_catalog_id, sold_date, title) DO NOTHING
    """

    def _run(c):
        with c.cursor() as cur:
            psycopg2.extras.execute_values(cur, sql, rows)
            return cur.rowcount

    if conn is not None:
        return _run(conn)

    with get_db() as c:
        return _run(c)
