"""Migration: add ebay_tokens and ebay_drafts tables.

Idempotent — safe to re-run on every deploy.
"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass

from db import get_db

def run():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ebay_tokens (
                    user_id            TEXT        PRIMARY KEY REFERENCES users(username) ON DELETE CASCADE,
                    access_token       TEXT        NOT NULL,
                    refresh_token      TEXT        NOT NULL,
                    expires_at         TIMESTAMPTZ NOT NULL,
                    refresh_expires_at TIMESTAMPTZ,
                    scope              TEXT        NOT NULL DEFAULT '',
                    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ebay_drafts (
                    id            BIGSERIAL    PRIMARY KEY,
                    user_id       TEXT         NOT NULL REFERENCES users(username) ON DELETE CASCADE,
                    sku           TEXT         NOT NULL,
                    offer_id      TEXT,
                    card_name     TEXT         NOT NULL,
                    listing_price NUMERIC      NOT NULL,
                    status        TEXT         NOT NULL DEFAULT 'draft',
                    ebay_draft_url TEXT        NOT NULL DEFAULT '',
                    error_detail  TEXT         NOT NULL DEFAULT '',
                    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ebay_drafts_user ON ebay_drafts (user_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ebay_drafts_status ON ebay_drafts (user_id, status)")
        conn.commit()
    print("Migration complete: ebay_tokens + ebay_drafts tables ready.")

if __name__ == "__main__":
    run()
