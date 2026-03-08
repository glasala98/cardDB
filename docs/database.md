# CardDB — Database Reference

Railway PostgreSQL (Pro plan, 10GB). Connection: `psycopg2.ThreadedConnectionPool(1, 10, DATABASE_URL)` via `db.py`.

---

## Connection Pool — `db.py`

```python
from db import get_db

with get_db() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT ...", (param,))
        rows = cur.fetchall()
# commits on exit, rolls back on exception, always returns conn to pool
```

Pool size: min 1, max 10 connections. `DATABASE_URL` env var required.

---

## Tables

### `card_catalog` — The reference catalog (2.6M+ cards)

Populated by `scrape_beckett_catalog.py`. Read-only at runtime.

| Column | Type | Notes |
|---|---|---|
| `id` | SERIAL PK | |
| `sport` | TEXT | NHL / NBA / NFL / MLB |
| `year` | TEXT | e.g. `2024-25` or `2024` |
| `brand` | TEXT | Upper Deck, Panini, Topps… |
| `set_name` | TEXT | e.g. `O-Pee-Chee Platinum` |
| `card_number` | TEXT | e.g. `201` or `RC-12` |
| `player_name` | TEXT | |
| `team` | TEXT | |
| `variant` | TEXT | Parallel name, e.g. `Rainbow Foil` |
| `is_rookie` | BOOLEAN | |
| `is_parallel` | BOOLEAN | |
| `print_run` | INTEGER | Serial # limit (NULL = unlimited) |
| `catalog_tier` | TEXT | `staple` / `premium` / `stars` / NULL |
| `search_query` | TEXT | Pre-built eBay search string |
| `source` | TEXT | tcdb / cli / cbc |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

**Index:** `(sport, year, set_name, player_name)` — used by catalog browse queries.

**Unique constraint:** `(sport, year, set_name, card_number, player_name, variant)`.

---

### `market_prices` — Current price per catalog card

One row per `card_catalog_id`. Upserted on each scrape.

| Column | Type | Notes |
|---|---|---|
| `id` | SERIAL PK | |
| `card_catalog_id` | INT FK → card_catalog.id | UNIQUE |
| `fair_value` | NUMERIC(10,2) | Latest eBay median fair value (CAD) |
| `prev_value` | NUMERIC(10,2) | Previous scrape value (for trend) |
| `trend` | TEXT | `up` / `down` / `stable` |
| `confidence` | TEXT | `high` / `medium` / `low` / `estimated` / `none` / `not found` |
| `num_sales` | INTEGER | |
| `min_price` | NUMERIC(10,2) | |
| `max_price` | NUMERIC(10,2) | |
| `median_price` | NUMERIC(10,2) | |
| `search_url` | TEXT | eBay search URL used |
| `graded_data` | JSONB | `{"PSA 10": {"fair_value": 80, "num_sales": 3, "min": 70, "max": 95}}` |
| `scraped_at` | TIMESTAMP | Last scrape time |

**graded_data structure:**
```json
{
  "PSA 10": {"fair_value": 80.00, "num_sales": 3, "min": 70.00, "max": 95.00},
  "PSA 9":  {"fair_value": 45.00, "num_sales": 5, "min": 40.00, "max": 50.00},
  "BGS 9.5":{"fair_value": 55.00, "num_sales": 2, "min": 50.00, "max": 60.00}
}
```
Merged on upsert: `graded_data = market_prices.graded_data || EXCLUDED.graded_data`.

---

### `market_price_history` — SCD Type 2 price history

Only inserts when `fair_value` changes from the previous row (delta-only = true SCD Type 2). Never duplicates consecutive identical prices.

| Column | Type | Notes |
|---|---|---|
| `id` | SERIAL PK | |
| `card_catalog_id` | INT FK → card_catalog.id | |
| `fair_value` | NUMERIC(10,2) | |
| `confidence` | TEXT | |
| `num_sales` | INTEGER | |
| `scraped_at` | TIMESTAMP | |

**Insert pattern:**
```sql
INSERT INTO market_price_history (card_catalog_id, scraped_at, fair_value, ...)
SELECT ... WHERE NOT EXISTS (
    SELECT 1 FROM market_price_history h
    WHERE h.card_catalog_id = i.card_catalog_id
      AND h.fair_value = i.fair_value
      AND h.scraped_at = (
          SELECT MAX(scraped_at) FROM market_price_history
          WHERE card_catalog_id = i.card_catalog_id
      )
)
```

---

### `collection` — User ownership layer

Links users to catalog cards. One row per `(user_id, card_catalog_id, grade)`.

| Column | Type | Notes |
|---|---|---|
| `id` | SERIAL PK | |
| `user_id` | TEXT | FK to users.username |
| `card_catalog_id` | INT FK → card_catalog.id | |
| `grade` | TEXT | Raw / PSA 10 / BGS 9.5 / etc. |
| `quantity` | INTEGER | Default 1 |
| `cost_basis` | NUMERIC(10,2) | Per card cost (CAD) |
| `purchase_date` | DATE | |
| `notes` | TEXT | |
| `created_at` | TIMESTAMP | |

**Unique constraint:** `(user_id, card_catalog_id, grade)`.

**On conflict:** `DO UPDATE SET quantity = collection.quantity + 1`.

---

### `users` — Authentication

| Column | Type | Notes |
|---|---|---|
| `username` | TEXT PK | Login identifier |
| `display_name` | TEXT | Shown in UI |
| `password_hash` | TEXT | bcrypt |
| `role` | TEXT | `admin` / `user` / `guest` |
| `created_at` | TIMESTAMP | |

---

### `cards` — Personal ledger (text-keyed, legacy)

Pre-catalog ownership system. Keyed by `card_name` text rather than `card_catalog_id` FK.

| Column | Type | Notes |
|---|---|---|
| `id` | SERIAL PK | |
| `user_id` | TEXT | |
| `card_name` | TEXT | Full structured name |
| `fair_value` | NUMERIC(10,2) | |
| `cost_basis` | NUMERIC(10,2) | |
| `purchase_date` | DATE | |
| `tags` | TEXT | |
| `trend` | TEXT | |
| `num_sales` | INTEGER | |
| `median_all` | NUMERIC(10,2) | |
| `min_price` | NUMERIC(10,2) | |
| `max_price` | NUMERIC(10,2) | |
| `top3_prices` | TEXT | Formatted "$52, $48, $45" |
| `confidence` | TEXT | |
| `last_scraped` | TIMESTAMP | |
| `image_url` | TEXT | |
| `image_url_back` | TEXT | |

---

### `card_results` — Raw eBay sales per ledger card

| Column | Type | Notes |
|---|---|---|
| `id` | SERIAL PK | |
| `user_id` | TEXT | |
| `card_name` | TEXT | |
| `title` | TEXT | eBay listing title |
| `price_val` | NUMERIC(10,2) | |
| `shipping` | NUMERIC(10,2) | |
| `sold_date` | DATE | |
| `listing_url` | TEXT | |
| `image_url` | TEXT | |
| `scraped_at` | TIMESTAMP | |

---

### `card_price_history` — Per-ledger-card price snapshots

| Column | Type | Notes |
|---|---|---|
| `id` | SERIAL PK | |
| `user_id` | TEXT | |
| `card_name` | TEXT | |
| `fair_value` | NUMERIC(10,2) | |
| `num_sales` | INTEGER | |
| `recorded_at` | DATE | One row per day |

---

### `portfolio_history` — Daily portfolio totals

| Column | Type | Notes |
|---|---|---|
| `id` | SERIAL PK | |
| `user_id` | TEXT | |
| `total_value` | NUMERIC(12,2) | |
| `total_cards` | INTEGER | |
| `avg_value` | NUMERIC(10,2) | |
| `recorded_at` | DATE | |

---

### `scrape_runs` — Scrape job tracking

One row per scraper invocation. Used by Admin → Runs tab for live progress and history.

| Column | Type | Notes |
|---|---|---|
| `id` | SERIAL PK | |
| `workflow` | TEXT | e.g. `catalog_tier_staple` |
| `sport` | TEXT | NHL / NBA / NFL / MLB |
| `tier` | TEXT | staple / premium / stars / base / NULL |
| `mode` | TEXT | raw / graded |
| `status` | TEXT | `running` / `completed` / `error` / `timed_out` |
| `cards_total` | INTEGER | Set at run start |
| `cards_processed` | INTEGER | Updated every 50 cards mid-run |
| `cards_found` | INTEGER | Cards with eBay results (updated mid-run) |
| `cards_delta` | INTEGER | Cards with price change (written at finish) |
| `errors` | INTEGER | Scrape errors (written at finish) |
| `started_at` | TIMESTAMP | |
| `finished_at` | TIMESTAMP | NULL while running |

Stale `running` rows (>1h old, same workflow+sport) are auto-marked `timed_out` when the next run starts.

---

### `scrape_run_errors` — Per-card error log

| Column | Type | Notes |
|---|---|---|
| `id` | SERIAL PK | |
| `run_id` | INT FK → scrape_runs.id | |
| `card_name` | TEXT | |
| `error_msg` | TEXT | |
| `attempted_at` | TIMESTAMP | |

---

### `sealed_products` — Sealed product catalog

Scraped monthly from cardboardconnection.com. One row per `(sport, year, set_name, product_type)`.

| Column | Type | Notes |
|---|---|---|
| `id` | SERIAL PK | |
| `sport` | TEXT | NHL / NBA / NFL / MLB |
| `year` | TEXT | e.g. `2024-25` |
| `set_name` | TEXT | |
| `product_type` | TEXT | Hobby Box / Blaster / Jumbo / Rack / etc. |
| `msrp` | NUMERIC(10,2) | |
| `box_price` | NUMERIC(10,2) | Current secondary market price |
| `cards_per_pack` | INTEGER | |
| `packs_per_box` | INTEGER | |
| `autos_per_box` | INTEGER | |
| `source_url` | TEXT | |
| `scraped_at` | TIMESTAMP | |

**Unique constraint:** `(sport, year, set_name, product_type)`. Sport mismatch detection in `scrape_set_info.py` skips cross-listed products (e.g. a football set appearing on the hockey CBC page).

---

### Legacy Analytics Tables

These power the `/nhl-stats` page and grading lookup. Still queried at runtime.

| Table | Purpose |
|---|---|
| `rookie_cards` | Young Guns / Rookie market DB with PSA/BGS price columns |
| `rookie_price_history` | Price snapshots per rookie + `graded_data` JSONB |
| `rookie_raw_sales` | Raw eBay sales per rookie |
| `rookie_portfolio_history` | Daily YG portfolio totals |
| `player_stats` | NHL/NBA/NFL/MLB stats as JSONB |
| `standings` | Team standings per sport |
| `rookie_correlation_history` | Price vs performance R² snapshots |

---

## Common Query Patterns

### Catalog browse with market price join
```sql
SELECT
    cc.id, cc.sport, cc.year, cc.brand, cc.set_name,
    cc.card_number, cc.player_name, cc.team, cc.variant,
    cc.is_rookie, cc.catalog_tier, cc.print_run,
    mp.fair_value, mp.trend, mp.confidence, mp.num_sales, mp.scraped_at
FROM card_catalog cc
LEFT JOIN market_prices mp ON mp.card_catalog_id = cc.id
WHERE cc.sport = %s AND cc.year = %s
ORDER BY cc.year DESC
LIMIT %s OFFSET %s
```

### Collection with P&L
```sql
SELECT
    col.*,
    cc.player_name, cc.set_name, cc.year, cc.is_rookie,
    mp.fair_value,
    mp.fair_value - col.cost_basis AS gain_loss
FROM collection col
JOIN card_catalog cc ON cc.id = col.card_catalog_id
LEFT JOIN market_prices mp ON mp.card_catalog_id = col.card_catalog_id
WHERE col.user_id = %s
ORDER BY mp.fair_value DESC NULLS LAST
```

### Graded data lookup
```sql
SELECT mp.graded_data
FROM market_prices mp
JOIN card_catalog cc ON cc.id = mp.card_catalog_id
WHERE cc.player_name ILIKE %s
  AND mp.graded_data != '{}'
ORDER BY mp.fair_value DESC NULLS LAST
LIMIT 1
```

### Upsert graded data (merge JSONB)
```sql
INSERT INTO market_prices (card_catalog_id, graded_data)
VALUES (%s, %s::jsonb)
ON CONFLICT (card_catalog_id)
DO UPDATE SET graded_data = market_prices.graded_data || EXCLUDED.graded_data
```

---

## Migrations

Migrations are idempotent Python scripts using `IF NOT EXISTS` / `ON CONFLICT`. They run automatically on every Railway deploy via the Dockerfile CMD before uvicorn starts.

| Script | Purpose |
|---|---|
| `migrate_add_graded_data.py` | Adds `graded_data JSONB` to `market_prices`; migrates data from `rookie_price_history` |
| `migrate_add_perf_indexes.py` | Adds performance indexes on `card_catalog`, `market_prices`, `collection` |
| `migrate_add_sealed_products.py` | Creates `sealed_products` table |
| `migrate_add_scrape_error_log.py` | Creates `scrape_runs` and `scrape_run_errors` tables |
| `migrate_add_cards_processed.py` | Adds `cards_processed INT DEFAULT 0` to `scrape_runs` |

All run in order on every Railway deploy (Dockerfile CMD). Each uses `IF NOT EXISTS` / `try/except` — safe to re-run. If a migration fails, the error is logged and uvicorn still starts (no crash loop).
