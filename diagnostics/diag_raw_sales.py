"""Quick diagnostic: check market_raw_sales row counts and title coverage."""
import os, psycopg2
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM market_raw_sales")
total = cur.fetchone()[0]
print(f"Total rows in market_raw_sales: {total:,}")

cur.execute("SELECT COUNT(*) FROM market_raw_sales WHERE title IS NOT NULL AND title != ''")
with_title = cur.fetchone()[0]
print(f"Rows with non-null title:        {with_title:,}")

cur.execute("SELECT COUNT(DISTINCT card_catalog_id) FROM market_raw_sales")
cards = cur.fetchone()[0]
print(f"Distinct cards with raw sales:   {cards:,}")

if total > 0:
    cur.execute("SELECT title, sold_date, price_val FROM market_raw_sales LIMIT 5")
    print("\nSample rows:")
    for r in cur.fetchall():
        print(f"  title={r[0]!r}  date={r[1]}  price={r[2]}")

cur.close()
conn.close()
