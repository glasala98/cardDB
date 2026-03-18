"""Quick diagnostic: Connor McDavid Young Guns cards in card_catalog."""
import os, psycopg2

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

print("=== McDavid cards with 'young' or 'gun' in any field ===")
cur.execute("""
    SELECT id, year, set_name, variant, card_number, scrape_tier,
           mp.fair_value, mp.num_sales
    FROM card_catalog cc
    LEFT JOIN market_prices mp ON mp.card_catalog_id = cc.id
    WHERE cc.player_name ILIKE '%mcdavid%'
      AND (cc.set_name ILIKE '%young%' OR cc.variant ILIKE '%young%'
           OR cc.set_name ILIKE '%gun%'  OR cc.variant ILIKE '%gun%')
    ORDER BY cc.year, cc.set_name, cc.variant
""")
rows = cur.fetchall()
print(f"Found {len(rows)} rows:")
for r in rows:
    print(f"  id={r[0]}  year={r[1]}  set={r[2]!r}  variant={r[3]!r}  #={r[4]}  tier={r[5]}  fv={r[6]}  sales={r[7]}")

print()
print("=== All McDavid cards in 2015-16 Upper Deck sets ===")
cur.execute("""
    SELECT id, set_name, variant, card_number, scrape_tier, mp.fair_value
    FROM card_catalog cc
    LEFT JOIN market_prices mp ON mp.card_catalog_id = cc.id
    WHERE cc.player_name ILIKE '%mcdavid%'
      AND cc.year ILIKE '2015%'
    ORDER BY cc.set_name, cc.variant
""")
rows2 = cur.fetchall()
print(f"Found {len(rows2)} rows:")
for r in rows2:
    print(f"  id={r[0]}  set={r[1]!r}  variant={r[2]!r}  #={r[3]}  tier={r[4]}  fv={r[5]}")

conn.close()
