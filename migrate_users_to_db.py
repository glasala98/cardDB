#!/usr/bin/env python3 -u
"""
One-time migration: copy users from users.yaml → PostgreSQL users table.
Safe to re-run — uses INSERT ... ON CONFLICT DO NOTHING.

Usage (via GitHub Actions):
    python migrate_users_to_db.py
"""
import os, sys
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, '.env'))
except ImportError:
    pass

import yaml
from db import get_db

USERS_YAML = os.path.join(ROOT, 'users.yaml')

def main():
    # Create users table if it doesn't exist
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id            BIGSERIAL    PRIMARY KEY,
                    username      TEXT         NOT NULL UNIQUE,
                    display_name  TEXT         NOT NULL DEFAULT '',
                    password_hash TEXT         NOT NULL,
                    role          TEXT         NOT NULL DEFAULT 'user',
                    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
        conn.commit()
    print("users table ready")

    if not os.path.exists(USERS_YAML):
        print("No users.yaml found — nothing to migrate")
        return

    with open(USERS_YAML, 'r') as f:
        config = yaml.safe_load(f) or {}
    users = config.get('users', {})

    if not users:
        print("users.yaml has no users — nothing to migrate")
        return

    migrated = 0
    with get_db() as conn:
        with conn.cursor() as cur:
            for username, data in users.items():
                cur.execute("""
                    INSERT INTO users (username, display_name, password_hash, role)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (username) DO NOTHING
                """, (
                    username,
                    data.get('display_name', username),
                    data['password_hash'],
                    data.get('role', 'user'),
                ))
                if cur.rowcount:
                    migrated += 1
                    print(f"  Migrated: {username} (role={data.get('role','user')})")
                else:
                    print(f"  Skipped (already exists): {username}")
        conn.commit()

    print(f"\nDone — {migrated} users migrated to PostgreSQL")

if __name__ == '__main__':
    main()
