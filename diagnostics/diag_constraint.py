"""Check if the unique constraint on listing_hash exists."""
import os, psycopg2
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()
cur.execute("""
    SELECT conname, contype
    FROM pg_constraint
    WHERE conrelid = 'market_raw_sales'::regclass
      AND conname = 'market_raw_sales_listing_hash_key'
""")
row = cur.fetchone()
if row:
    print(f"CONSTRAINT EXISTS: {row[0]} (type={row[1]})")
else:
    print("CONSTRAINT MISSING — migration has not run yet")

cur.execute("SELECT COUNT(*) FROM market_raw_sales")
print(f"market_raw_sales row count: {cur.fetchone()[0]:,}")
cur.close()
conn.close()
