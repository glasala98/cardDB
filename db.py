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
