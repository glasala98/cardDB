"""Shared pytest fixtures for CardDB test suite."""
import os
import pytest
import psycopg2
from psycopg2.extras import RealDictCursor

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
except ImportError:
    pass


def _build_dsn() -> str:
    url = os.environ["DATABASE_URL"]
    if "proxy.rlwy.net" in url and "sslmode=" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"
    return url


@pytest.fixture(scope="session")
def db():
    conn = psycopg2.connect(_build_dsn())
    cur = conn.cursor(cursor_factory=RealDictCursor)
    yield cur
    cur.close()
    conn.close()
