# Scraper Scripts — Reference

Five Python scripts handle all data collection. Run via GitHub Actions (automated), local CLI, or triggered by the "Rescrape All" button in the frontend.

---

## scrape_card_prices.py — eBay Scraping Engine

Shared scraping library. Not run directly — imported by `daily_scrape.py`, `scrape_master_db.py`, and the FastAPI `cards` router.

### 4-Stage Search Strategy

| Stage | Query | Confidence |
|-------|-------|-----------|
| 1 | Exact: player + card# + parallel + serial + year + brand | `high` |
| 2 | Set: player + card# + year + set name (no parallel) | `medium` |
| 3 | Broad: player + card# + serial + year only | `low` |
| 4 | Serial comps: find nearby serials, adjust by multiplier | `estimated` |

No sales at any stage → confidence `none`, value = `$5.00` default.

### Key Functions

**`process_card(card_name) → (card_name, result_dict)`**
Main entry point. Runs 4-stage search. Result keys: `estimated_value`, `confidence`, `stats`, `raw_sales`, `search_url`, `image_url`.

**`search_ebay_sold(driver, card_name, max_results=240) → list[dict]`**
Selenium scrape of eBay sold listings. Each sale: `title`, `price_val`, `shipping`, `sold_date`, `listing_url`, `image_url`. Filters to exact grade for graded cards.

**`calculate_fair_price(sales, target_serial=None) → (float, dict)`**
1. Remove outliers (>3× or <1/3 median)
2. Sort by recency
3. Median of top 3 recent sales
4. Trend: `up`/`down`/`stable` (last 3 vs previous 3)

**`serial_multiplier(from_serial, to_serial) → float`**
Price adjustment between two print runs using `SERIAL_VALUE` table (maps /1, /5, /10, /25, /50, /99, /199 … to relative values).

**`create_driver() / get_driver()`**
Headless Chrome with memory-saving flags. `get_driver()` returns a thread-local driver.

---

## daily_scrape.py — Personal Ledger Scraper

Scrapes all cards in the user ledger (`cards` table) and writes updated prices to PostgreSQL.

### Usage
```bash
python daily_scrape.py                 # all users, 3 workers
python daily_scrape.py --workers 5
python daily_scrape.py --user admin    # one user only
```

### What it does
1. Gets user list from `users.yaml`
2. For each user: loads cards from `cards` table
3. Scrapes all cards in parallel via `process_card()`
4. Writes to `cards` table: `fair_value`, `trend`, `min_price`, `max_price`, `num_sales`
5. Appends to `card_price_history`: one row per card per day
6. Appends to `portfolio_history`: daily total value snapshot

---

## scrape_master_db.py — Catalog Market Price Scraper

Scrapes cards from `card_catalog` and writes prices to `market_prices` + `market_price_history` (SCD Type 2).

### Usage
```bash
python scrape_master_db.py --sport NHL --limit 500
python scrape_master_db.py --sport MLB --workers 5
python scrape_master_db.py --force       # re-scrape recently scraped cards too
python scrape_master_db.py --sport NBA --limit 50  # test run
```

### CLI Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--sport` | ALL | Filter to one sport (NHL/NBA/NFL/MLB) |
| `--workers` | 3 | Parallel Chrome instances |
| `--limit` | 0 | Max cards to process (0 = all) |
| `--force` | False | Re-scrape even if recently scraped |

### SCD Type 2 delta capture
```sql
-- Only inserts a history row when fair_value has changed from the previous row.
-- No consecutive duplicate prices — true SCD Type 2.
INSERT INTO market_price_history (card_catalog_id, scraped_at, fair_value, ...)
SELECT ... WHERE NOT EXISTS (
    SELECT 1 FROM market_price_history h
    WHERE h.card_catalog_id = i.card_catalog_id
      AND h.fair_value = i.fair_value
      AND h.scraped_at = (SELECT MAX(scraped_at) FROM market_price_history
                          WHERE card_catalog_id = i.card_catalog_id)
)
```

### Output tables
| Table | What's written |
|-------|---------------|
| `market_prices` | UPSERT: latest fair_value, prev_value, trend, confidence, num_sales |
| `market_price_history` | INSERT only when price changed (SCD Type 2) |

---

## scrape_beckett_catalog.py — Card Catalog Populator

Populates `card_catalog` with all cards ever produced, sourced from TCDB, CLI, and CBC.

### Usage
```bash
# TCDB — all eras
python scrape_beckett_catalog.py --source tcdb --sport NHL --year-from 1906
python scrape_beckett_catalog.py --source tcdb --sport MLB --year-from 1869

# CLI — modern sets (2022+)
python scrape_beckett_catalog.py --source cli --sport NHL --year-from 2022

# CBC — mid-era (2008–2023)
python scrape_beckett_catalog.py --source cbc --sport NFL --year-from 2008

# Year range split for parallel runs
python scrape_beckett_catalog.py --source tcdb --sport MLB --year-from 2000 --year-to 2010
```

### Source Coverage

| Source | Sports | Years |
|--------|--------|-------|
| TCDB (tradingcarddatabase.com) | All | All eras |
| CLI (checklistinsider.com) | NHL, MLB | 2022–2026 |
| CBC (cardboardconnection.com) | NFL, MLB | 2008–2023 |

### TCDB specifics
- Uses `curl_cffi` with `impersonate="chrome124"` to bypass Cloudflare — regular requests/Selenium fail
- Rate limiting: 1.5–3s between year-index requests, 0.5–1.2s between sets
- Exponential backoff on 429s: 30/60/120/240s
- ~3,500+ sets per sport require TCDB login (premium/autograph sets) — skipped without credentials

### Checkpoint
`catalog_checkpoint.json` stores `{source}|{sport}|{year}|{set_name}` keys for completed sets.
Restarts skip already-done sets automatically — safe to interrupt and resume.

### Output table: `card_catalog`
One row per unique `(sport, year, set_name, card_number, player_name, variant)`.
Upsert on conflict: updates `team`, `is_rookie`, `is_parallel`, `updated_at`.

---

## scrape_nhl_stats.py — NHL Stats Fetcher

Fetches current-season player stats and standings from the NHL API and writes to `player_stats` + `standings` tables.

### Usage
```bash
python scrape_nhl_stats.py                      # all YG players
python scrape_nhl_stats.py --season "2023-24"   # one season
python scrape_nhl_stats.py --fetch-bios          # include nationality/draft info
python scrape_nhl_stats.py --dry-run             # show matches, don't save
```

### Player matching (3-stage)
1. **Exact** — card name == API name
2. **Normalized** — strip diacritics, lowercase
3. **Fuzzy** — 85% similarity cutoff

### Output
- `player_stats` table: `{sport, player}` → JSONB with `current_season`, `history`, `bio`
- `standings` table: `{sport, team}` → JSONB with wins, losses, points, division, etc.

---

## GitHub Actions Workflows

| Workflow | File | Schedule | What it runs |
|----------|------|----------|--------------|
| Daily card scrape | `daily_scrape.yml` | Daily 8am UTC | `python daily_scrape.py --workers 3` |
| Catalog quality report | `catalog_quality_report.yml` | Monday 10am UTC | pytest + gap analysis → Step Summary |

The **Rescrape All** button in the frontend dispatches `daily_scrape.yml` via GitHub API.
Requires `GITHUB_TOKEN` in Railway env vars (classic PAT with `repo` + `workflow` scopes).
