"""
preflight_db_check.py — Fail fast if Railway PostgreSQL is running low on disk.

Exits 0 if healthy, 1 if over the fail threshold (blocks the workflow).
Thresholds are set in absolute GB — no need to know the volume size.

Usage:
    python preflight_db_check.py                     # warn at 60GB, fail at 70GB
    python preflight_db_check.py --fail-gb 70        # explicit fail threshold
"""
import os, sys, argparse
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--warn-gb", type=float, default=60.0,
                        help="Warn if DB exceeds this size in GB (default: 60)")
    parser.add_argument("--fail-gb", type=float, default=70.0,
                        help="Fail if DB exceeds this size in GB (default: 70)")
    args = parser.parse_args()

    conn = psycopg2.connect(DATABASE_URL)
    cur  = conn.cursor()

    cur.execute("SELECT pg_database_size(current_database())")
    total_bytes = cur.fetchone()[0]
    total_gb    = total_bytes / (1024 ** 3)

    cur.execute("""
        SELECT
            schemaname || '.' || tablename AS table_name,
            pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) AS pretty
        FROM pg_tables
        WHERE schemaname = 'public'
        ORDER BY pg_total_relation_size(schemaname || '.' || tablename) DESC
        LIMIT 10
    """)
    top_tables = cur.fetchall()

    cur.close()
    conn.close()

    print(f"DB size: {total_gb:.2f} GB")
    print("Top tables:")
    for name, pretty in top_tables:
        print(f"  {pretty:>10}  {name}")

    if total_gb >= args.fail_gb:
        print(f"\nERROR: DB at {total_gb:.1f}GB — over fail threshold of {args.fail_gb:.0f}GB. "
              f"Aborting to prevent DiskFull crash. Expand the Railway volume first.", file=sys.stderr)
        sys.exit(1)

    if total_gb >= args.warn_gb:
        print(f"\nWARNING: DB at {total_gb:.1f}GB — over warn threshold of {args.warn_gb:.0f}GB.")
    else:
        print(f"\nOK — {args.fail_gb - total_gb:.1f}GB below fail threshold")


if __name__ == "__main__":
    main()
