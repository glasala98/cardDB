# market_raw_sales — Full eBay Sales History Build-Out Plan

## Goal
Capture every individual eBay sold listing ever for every card in card_catalog.
Store them permanently in `market_raw_sales` so we own the data past eBay's 90-day purge window.
Build it up over 2–3 months using efficient delta scraping after the initial backfill.

---

## Current State (as of 2026-03-16)

### What exists
| Table | Purpose | Status |
|---|---|---|
| `market_prices` | Current price per card (upserted each scrape) | ✅ Live |
| `market_price_history` | Aggregate price snapshots when price changes | ✅ Live |
| `market_prices_status` | View: is_stale, is_fresh, days_since_scraped | ✅ Live |
| `market_raw_sales` | Individual eBay sold listings | ✅ Created today — EMPTY |

### What market_raw_sales stores
```
id              BIGSERIAL PK
card_catalog_id FK → card_catalog
sold_date       DATE (nullable)
price_val       NUMERIC (card price)
shipping_val    NUMERIC (shipping separately)
title           TEXT (full eBay listing title)
listing_hash    TEXT UNIQUE — md5(card_catalog_id|sold_date|title)
scraped_at      TIMESTAMPTZ
```

### Dedup logic
`listing_hash = md5(card_catalog_id | sold_date | title)` — NULL-safe, computed in Python.
`ON CONFLICT (listing_hash) DO NOTHING` — re-scraping same card never creates duplicates.

### What's wired up today
- `scrape_master_db.py` → `save_prices_batch()` → calls `save_raw_sales()` ✅
- `scrape_market_prices.py` → `save_price_result()` → calls `save_raw_sales()` ✅
- `db.py` → `save_raw_sales()` shared function ✅
- Primary scrape: `max_results` cap removed → captures all 240 eBay returns ✅

### What's NOT wired up yet
- Pagination (eBay shows 240/page — popular cards have 500+ sales in 90 days)
- `last_sale_date` per card (needed for stop condition on delta runs)
- `--backfill` mode in scraper (full 90-day, no price write)
- Dedicated backfill GH Actions workflow

---

## Architecture: Two Modes

### Mode 1 — Price mode (existing, enhanced)
**When:** Every regular scrape run (daily/weekly schedules)
**What it does:**
- Loads cards with `last_sale_date` from `market_raw_sales`
- Calls `search_ebay_sold_paginated(since_date=last_sale_date)`
- Stops paginating as soon as a full page is older than `last_sale_date`
- For most cards after backfill: 1–2 pages max (very fast)
- Saves new sales → `market_raw_sales`
- Calculates fair_value from last 30 days only
- Writes → `market_prices` + `market_price_history`

### Mode 2 — Backfill mode (new `--backfill` flag)
**When:** Manual trigger per tier until `market_raw_sales` is fully populated
**What it does:**
- Only processes cards with 0 rows in `market_raw_sales`
- Paginates ALL pages until sales are 90+ days old or pages run out
- Saves ALL sales → `market_raw_sales` (up to ~3,600 per card)
- Does NOT write to `market_prices` or `market_price_history` (price already up to date)
- Slower per card but runs independently of price scrapes

---

## Build Steps (IN ORDER)

### Step 1 — `search_ebay_sold_paginated()` in `scrape_card_prices.py`
**File:** `scrape_card_prices.py`
**What:** New function that wraps `search_ebay_sold()` with a pagination loop.

```python
def search_ebay_sold_paginated(driver, card_name, since_date=None, max_pages=15, search_query=None):
    """
    Paginate eBay sold listings, returning all sales across multiple pages.

    since_date: 'YYYY-MM-DD' string or None
      None    → first run / backfill — collect until 90 days back or pages run out
      date    → delta run — stop when a full page has no sales newer than this date

    Stop conditions (checked after each page):
      1. Page returns zero results
      2. Every dated sale on the page is older than since_date (delta cutoff)
      3. Every dated sale on the page is older than 90 days (first run cutoff)
      4. max_pages reached (safety cap)
    """
```

**URL pattern:** `&_pgn=2`, `&_pgn=3` etc. appended to existing URL.
**Stop logic:** After each page, check `min(sold_date for sales with sold_date)`.
- If min date ≤ since_date → stop (delta mode)
- If min date ≤ today - 90 days → stop (backfill mode)
- Do NOT stop mid-page — always collect the full page, then decide.

**Status:** ✅ Done

---

### Step 2 — `last_sale_date` in card batch query (`scrape_master_db.py`)
**File:** `scrape_master_db.py` → `_load_cards()` or equivalent card SELECT
**What:** Add LEFT JOIN to get `MAX(sold_date)` per card from `market_raw_sales`.

```sql
SELECT cc.*, mp.fair_value AS existing_price, mp.scraped_at AS last_scraped,
       mrs_max.last_sale_date                          -- NEW
FROM card_catalog cc
LEFT JOIN market_prices mp ON mp.card_catalog_id = cc.id
LEFT JOIN (
    SELECT card_catalog_id, MAX(sold_date) AS last_sale_date
    FROM market_raw_sales
    GROUP BY card_catalog_id
) mrs_max ON mrs_max.card_catalog_id = cc.id
WHERE ...
```

Each card dict gets `card['last_sale_date']` — None if never stored.

**Status:** ✅ Done

---

### Step 3 — Pass `since_date` through `scrape_one()` (`scrape_master_db.py`)
**File:** `scrape_master_db.py` → `scrape_one(card)`
**What:** Replace `search_ebay_sold()` call with `search_ebay_sold_paginated()`, passing `card['last_sale_date']` as `since_date`.

```python
def scrape_one(card):
    all_sales = search_ebay_sold_paginated(
        driver, card_name,
        since_date=card.get('last_sale_date')  # None = first run
    )
    # Storage: all sales
    save_raw_sales(card['id'], all_sales)
    # Pricing: last 30 days only
    cutoff = (date.today() - timedelta(days=30)).isoformat()
    pricing_sales = [s for s in all_sales if (s.get('sold_date') or '') >= cutoff] or all_sales
    stats = calculate_fair_price(pricing_sales)
```

**Status:** ✅ Done

---

### Step 4 — `--backfill` flag in `scrape_master_db.py`
**File:** `scrape_master_db.py`
**What:** New argparse flag that changes the card filter and skip logic.

```
--backfill    Only process cards with 0 rows in market_raw_sales.
              Paginates full 90 days. Does NOT write market_prices or market_price_history.
```

Card filter when `--backfill`:
```sql
WHERE NOT EXISTS (
    SELECT 1 FROM market_raw_sales WHERE card_catalog_id = cc.id
)
```

**Status:** ✅ Done

---

### Step 5 — `backfill_raw_sales.yml` GH Actions workflow
**File:** `.github/workflows/backfill_raw_sales.yml`
**What:** Manual trigger workflow that runs backfill mode per tier.

```yaml
on:
  workflow_dispatch:
    inputs:
      tier:
        description: 'Tier to backfill (staple / premium / stars / base)'
        required: true
      sport:
        description: 'Sport (NHL / NBA / NFL / MLB / ALL)'
        default: 'ALL'
      workers:
        description: 'Parallel Chrome workers'
        default: '5'
```

Runs: `python -u scrape_master_db.py --backfill --catalog-tier {tier} --sport {sport} --workers {workers} --max-hours 5`

**Status:** ✅ Done

---

### Step 6 — Delete `scrape_market_prices.py`
**File:** `scrape_market_prices.py`
**Why:** No GH Actions workflow calls it. Dead code. Confusing to maintain alongside `scrape_master_db.py`.
**Confirm:** Verify no other file imports it before deleting.

**Status:** ✅ Done

---

## Backfill Execution Schedule

Once Steps 1–5 are built and deployed:

| Run | Tier | Cards | Est. time | When |
|---|---|---|---|---|
| 1 | staple | ~5k | 2–3 hrs | Manual, ASAP |
| 2 | premium | ~50k | 10–15 hrs (multiple runs) | Week 1 |
| 3 | stars | ~100k | 20+ hrs (multiple runs) | Week 2–3 |
| 4 | base | ~800k | Months (ongoing with existing base scrape) | Ongoing |

After backfill for a tier is complete, all regular scrapes for that tier automatically run in delta mode (fast).

---

## Steady State (after backfill complete)

```
Every scrape run:
  card has last_sale_date → since_date = Mar 1
  Page 1: sales Mar 2–Mar 16 → all new → insert
  Page 1 oldest date > Mar 1 → check page 2
  Page 2: sales Feb 15–Mar 1 → all older than since_date → STOP
  Result: ~15–30 new rows per card, 1–2 pages, fast

market_raw_sales grows forever:
  Every eBay sale ever recorded → permanent
  eBay purges after 90 days → we still have it
  Fair value always recomputable from raw data
```

---

## Key Design Decisions

| Decision | Choice | Reason |
|---|---|---|
| Dedup key | `listing_hash = md5(card_catalog_id\|sold_date\|title)` | NULL-safe, sale identity is date+title |
| Storage vs pricing split | Store all 90 days, price from last 30 | Avoids stale sales skewing fair_value |
| Stop condition | Full page older than cutoff | Handles NULL dates, same-day partial coverage |
| Backfill separate from price | `--backfill` flag, separate workflow | Don't re-price cards that are already current |
| One canonical scraper | `scrape_master_db.py` only | `scrape_market_prices.py` is dead code |

---

## Files Changed / To Change

| File | Change | Status |
|---|---|---|
| `db.py` | `save_raw_sales()` + `_sale_hash()` | ✅ Done |
| `migrate_add_market_raw_sales.py` | Create table + indexes | ✅ Done |
| `migrate_fix_market_raw_sales.py` | Add listing_hash, drop old constraint | ✅ Done |
| `migrate_add_market_prices_status.py` | is_stale/is_fresh/days_since_scraped view | ✅ Done |
| `scrape_master_db.py` | Wire save_raw_sales into write_batch | ✅ Done |
| `scrape_market_prices.py` | Wire save_raw_sales into save_price_result | ✅ Done |
| `dashboard_utils.py` | Remove max_results=50 cap on primary scrape | ✅ Done |
| `scrape_card_prices.py` | Add `search_ebay_sold_paginated()` | ✅ Done — Step 1 |
| `scrape_master_db.py` | Add last_sale_date to card batch query | ✅ Done — Step 2 |
| `scrape_master_db.py` | Pass since_date through scrape_one() | ✅ Done — Step 3 |
| `scrape_master_db.py` | Add --backfill flag | ✅ Done — Step 4 |
| `.github/workflows/backfill_raw_sales.yml` | New backfill workflow | ✅ Done — Step 5 |
| `scrape_market_prices.py` | Delete (dead code) | ✅ Done — Step 6 |
