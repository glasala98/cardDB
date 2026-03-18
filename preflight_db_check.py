"""
preflight_db_check.py — Fail fast if Railway PostgreSQL is running low on disk.

Exits 0 if healthy, 1 if over the hard limit (blocks the workflow).
Prints a size breakdown so failures are immediately actionable.

Usage:
    python preflight_db_check.py                  # default: warn 40GB, fail 45GB
    python preflight_db_check.py --volume-gb 50   # explicit volume size → thresholds auto-scaled
"""
import os, sys, argparse
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--volume-gb", type=float, default=50.0,
                        help="Total Railway volume size in GB (default: 50)")
    args = parser.parse_args()

    warn_gb = args.volume_gb * 0.80   # 80% — print warning but continue
    fail_gb = args.volume_gb * 0.90   # 90% — block the workflow

    conn = psycopg2.connect(DATABASE_URL)
    cur  = conn.cursor()

    # Total DB size
    cur.execute("SELECT pg_database_size(current_database())")
    total_bytes = cur.fetchone()[0]
    total_gb    = total_bytes / (1024 ** 3)

    # Top 10 tables by total size (table + indexes + toast)
    cur.execute("""
        SELECT
            schemaname || '.' || tablename AS table_name,
            pg_total_relation_size(schemaname || '.' || tablename) / (1024*1024.0) AS size_mb,
            pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) AS pretty
        FROM pg_tables
        WHERE schemaname = 'public'
        ORDER BY 2 DESC
        LIMIT 10
    """)
    top_tables = cur.fetchall()

    cur.close()
    conn.close()

    print(f"DB size: {total_gb:.2f} GB / {args.volume_gb:.0f} GB volume "
          f"({total_gb / args.volume_gb * 100:.1f}% used)")
    print("Top tables:")
    for name, _, pretty in top_tables:
        print(f"  {pretty:>10}  {name}")

    if total_gb >= fail_gb:
        print(f"\nERROR: DB at {total_gb:.1f}GB — over 90% of {args.volume_gb:.0f}GB volume. "
              f"Aborting to prevent DiskFull crash. Expand the Railway volume first.", file=sys.stderr)
        sys.exit(1)

    if total_gb >= warn_gb:
        print(f"\nWARNING: DB at {total_gb:.1f}GB — over 80% of {args.volume_gb:.0f}GB volume. "
              f"Consider expanding the Railway volume soon.")
    else:
        print(f"\nOK — {args.volume_gb - total_gb:.1f}GB free")


if __name__ == "__main__":
    main()
