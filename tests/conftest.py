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


@pytest.fixture(scope="session")
def db():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor(cursor_factory=RealDictCursor)
    yield cur
    cur.close()
    conn.close()
