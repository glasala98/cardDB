"""Migration: tune autovacuum on high-churn tables.

market_raw_sales receives millions of inserts during backfill. PostgreSQL's
default autovacuum threshold is 20% of table rows before it fires — at 1.7M
rows that's 340K dead tuples accumulating before cleanup, causing table bloat
and periodic performance spikes.

Setting scale_factor to 1% means autovacuum fires at ~17K dead tuples instead,
keeping the table lean. Each vacuum run is smaller and faster.

market_price_history is append-only but benefits from more frequent analyze
so the query planner has accurate statistics for the LATERAL JOIN.

Idempotent — safe to re-run.
"""
import os
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]


def run():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    # market_raw_sales — high insert/dead-tuple churn during backfill
    cur.execute("""
        ALTER TABLE market_raw_sales SET (
            autovacuum_vacuum_scale_factor   = 0.01,
            autovacuum_analyze_scale_factor  = 0.01,
            autovacuum_vacuum_cost_delay     = 2
        );
    """)
    print("market_raw_sales autovacuum tuned (scale_factor=1%, cost_delay=2ms)")

    # market_price_history — append-only, needs fresh stats for LATERAL JOIN planner
    cur.execute("""
        ALTER TABLE market_price_history SET (
            autovacuum_analyze_scale_factor = 0.01
        );
    """)
    print("market_price_history autovacuum analyze tuned (scale_factor=1%)")

    # market_prices — upserted on every scrape; keep stats fresh
    cur.execute("""
        ALTER TABLE market_prices SET (
            autovacuum_vacuum_scale_factor  = 0.01,
            autovacuum_analyze_scale_factor = 0.01
        );
    """)
    print("market_prices autovacuum tuned (scale_factor=1%)")

    cur.close()
    conn.close()


if __name__ == "__main__":
    run()
