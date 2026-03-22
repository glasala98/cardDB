"""
Spot-check market_raw_sales — verify titles are landing and look correct.

Prints:
  - Total row count + distinct cards
  - 20 random recent sales (card name + eBay title + price)
  - Top 10 cards by sale count
  - Any cards where >50% of titles look suspiciously mismatched (title doesn't
    contain the player name or set year)
"""
import os, psycopg2, random

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

# ── Totals ────────────────────────────────────────────────────────────────────
cur.execute("SELECT COUNT(*), COUNT(DISTINCT card_catalog_id) FROM market_raw_sales")
total_sales, distinct_cards = cur.fetchone()
print(f"Total sales stored:   {total_sales:,}")
print(f"Distinct cards:       {distinct_cards:,}")

if total_sales == 0:
    print("\nNo data yet — backfill still running.")
    conn.close()
    exit()

# ── 20 random recent sales ────────────────────────────────────────────────────
print("\n--- 20 RANDOM RECENT SALES ---")
cur.execute("""
    SELECT cc.year, cc.brand, cc.set_name, cc.player_name, cc.variant,
           mrs.sold_date, mrs.price_val, mrs.title
    FROM market_raw_sales mrs
    JOIN card_catalog cc ON cc.id = mrs.card_catalog_id
    WHERE mrs.scraped_at > NOW() - INTERVAL '2 hours'
    ORDER BY random()
    LIMIT 20
""")
for r in cur.fetchall():
    year, brand, set_name, player, variant, sold_date, price, title = r
    card = f"{year} {brand} {set_name}{(' - ' + variant) if variant else ''} — {player}"
    print(f"  Card:  {card}")
    print(f"  Title: {title}")
    print(f"  Price: ${price}  Date: {sold_date}")
    print()

# ── Top 10 cards by sale count ────────────────────────────────────────────────
print("--- TOP 10 CARDS BY SALE COUNT ---")
cur.execute("""
    SELECT cc.year, cc.brand, cc.set_name, cc.player_name, cc.variant,
           COUNT(*) AS cnt
    FROM market_raw_sales mrs
    JOIN card_catalog cc ON cc.id = mrs.card_catalog_id
    GROUP BY cc.year, cc.brand, cc.set_name, cc.player_name, cc.variant
    ORDER BY cnt DESC
    LIMIT 10
""")
for r in cur.fetchall():
    year, brand, set_name, player, variant, cnt = r
    card = f"{year} {brand} {set_name}{(' - ' + variant) if variant else ''} — {player}"
    print(f"  {cnt:>5} sales — {card}")

# ── Sanity check: titles missing player name ──────────────────────────────────
print("\n--- SANITY CHECK: titles not containing player last name ---")
cur.execute("""
    SELECT cc.player_name,
           COUNT(*) AS total,
           COUNT(*) FILTER (
               WHERE LOWER(mrs.title) NOT LIKE '%' || LOWER(SPLIT_PART(cc.player_name, ' ', 2)) || '%'
           ) AS missing_name
    FROM market_raw_sales mrs
    JOIN card_catalog cc ON cc.id = mrs.card_catalog_id
    WHERE SPLIT_PART(cc.player_name, ' ', 2) != ''
    GROUP BY cc.player_name
    HAVING COUNT(*) FILTER (
               WHERE LOWER(mrs.title) NOT LIKE '%' || LOWER(SPLIT_PART(cc.player_name, ' ', 2)) || '%'
           ) * 100 / COUNT(*) > 50
       AND COUNT(*) >= 5
    ORDER BY missing_name DESC
    LIMIT 10
""")
rows = cur.fetchall()
if rows:
    for player, total, missing in rows:
        pct = round(missing / total * 100)
        print(f"  {pct}% mismatch — {player} ({missing}/{total} titles missing last name)")
else:
    print("  None found — titles look clean!")

cur.close()
conn.close()
