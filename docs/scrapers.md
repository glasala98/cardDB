# CardDB — Scraper Reference

All scraping is cloud-only. Scripts run on GitHub Actions runners — never locally. Chrome/Selenium is installed fresh on each runner via the workflow setup steps.

---

## scrape_card_prices.py — eBay Scraping Engine

Shared library. Not run directly — imported by `scrape_master_db.py`, `daily_scrape.py`, and the FastAPI `cards` router (for single-card scrapes).

### 4-Stage Search Strategy

Each card goes through up to 4 search stages until sales are found:

| Stage | Query | Confidence |
|---|---|---|
| 1 | Player + card# + parallel + serial + year + set | `high` |
| 2 | Player + card# + serial + set (no parallel name) | `medium` |
| 3 | Player + card# + serial + year only | `low` |
| 4 | Nearest serial comps × `serial_multiplier()` | `estimated` |

No sales at any stage → `confidence: none`, value = `$5.00` default.

### Key Functions

**`process_card(card_name) → (card_name, result_dict)`**
Main entry point. Runs 4-stage search. Result keys:
- `estimated_value` — fair value (CAD)
- `confidence` — high / medium / low / estimated / none / not found
- `stats` — `{median, min, max, num_sales, top3}`
- `raw_sales` — list of individual sale dicts
- `search_url` — eBay URL used
- `image_url` / `image_url_back` — fetched listing images

**`search_ebay_sold(driver, card_name, max_results=240) → list[dict]`**
Selenium scrape of eBay "sold listings". Each sale dict:
```python
{
  "title": "2023-24 Upper Deck Young Guns Bedard #201",
  "price_val": 45.00,
  "shipping": 5.00,
  "sold_date": "2026-02-15",
  "listing_url": "https://ebay.com/...",
  "image_url": "https://i.ebayimg.com/..."
}
```

**`calculate_fair_price(sales, target_serial=None) → (float, dict)`**
1. Remove outliers (price > 3× median or < ⅓ median)
2. Sort by recency
3. Median of top 3 recent sales = fair value
4. Trend: compare average of last 3 sales vs previous 3 (`up`/`down`/`stable`)

**`serial_multiplier(from_serial, to_serial) → float`**
Adjusts price between print runs using the `SERIAL_VALUE` table. Values mapped for: /1, /5, /10, /25, /50, /99, /199, /249, /299, /399, /499, /999, unlimited. Used in Stage 4 (estimated confidence).

**`build_set_query(card) / build_simplified_query(card)`**
Construct stage-2 and stage-3 eBay search strings from a card name.

**`create_driver() / get_driver()`**
Headless Chrome with memory flags: `--headless`, `--disable-gpu`, `--no-sandbox`, `--disable-dev-shm-usage`, `--disable-images`. `get_driver()` returns a thread-local driver — one Chrome instance per worker thread.

---

### Variant Filter — `_apply_variant_filter(card_name, sales)`

Strips sales that belong to a different parallel than the card being priced.

**How it works:**
1. Extract the card's variant keyword from its name via `_extract_variant_keyword()`
2. Keep only sales whose listing title contains that keyword
3. Exclude sales whose title contains a "superset" — a longer variant name that contains the matched keyword as a substring (e.g. when matching "Rainbow", exclude "Rainbow Foil" and "Rainbow Color Wheel" sales)
4. For aliases (Auto ↔ Autograph): accept both spellings as equivalent

**`_VARIANT_KEYWORDS`** — ordered list of 130+ known parallel names. More specific multi-word variants appear before single-word ones so extraction matches the most specific parallel first.

**`_VARIANT_ALIASES`** — synonym map:
```python
{'auto': {'autograph'}, 'autograph': {'auto'}}
```
Sellers use "Autograph" and "Auto" interchangeably for the same type of card.

**`_WORD_BOUNDARY_VARIANTS`** — short variants that need regex `\b` word-boundary matching to avoid false positives:
```python
{'ice', 'sp', 'ssp', 'mini', 'silk', 'wave', 'laser', 'clear', 'error'}
```
Without boundaries, "ice" would match "price", "sp" would match "display".

**`_kw_in_title(keyword, title) → bool`**
Applies word-boundary regex for variants in `_WORD_BOUNDARY_VARIANTS`, plain substring check for all others.

**Superset exclusion logic:**
```python
# For variant "Rainbow", supersets = ["rainbow foil", "rainbow color wheel",
#                                       "speckled rainbow", "retro rainbow"]
# A title matching any superset is a different card → excluded
supersets = [
    kw.lower() for kw in _VARIANT_KEYWORDS
    if kw.lower() != v_lower
    and v_lower in kw.lower()
    and kw.lower() not in aliases  # don't exclude aliases
]
```

---

## scrape_master_db.py — Catalog Market Price Scraper

Reads from `card_catalog`, writes to `market_prices` + `market_price_history`. Supports raw prices and graded PSA/BGS prices.

### CLI Arguments

| Argument | Default | Description |
|---|---|---|
| `--sport` | ALL | Filter: NHL / NBA / NFL / MLB |
| `--workers` | 3 | Parallel Chrome instances (thread pool) |
| `--limit` | 0 | Max cards (0 = all) |
| `--force` | False | Re-scrape recently scraped cards |
| `--stale-days` | 7 | Skip cards scraped within N days |
| `--rookies` | False | Only `is_rookie=true` cards |
| `--year` | None | Filter to one year |
| `--catalog-tier` | None | Filter: staple / premium / stars |
| `--graded` | False | Scrape PSA/BGS graded prices instead of raw |
| `--min-raw-value` | 5.0 | Min fair_value to qualify for graded scrape |

### Raw Price Mode (default)

1. Query `card_catalog` for eligible cards (filtered by sport, tier, stale-days)
2. For each card in parallel: `process_card()` → fair_value
3. UPSERT `market_prices`: latest value, prev_value, trend, confidence
4. Insert `market_price_history` only if value changed (SCD Type 2)

**Progress counters:** done / found / not_found / errors / deltas (price changed)

### Graded Price Mode (`--graded`)

1. Query `card_catalog` joined with `market_prices` where `fair_value >= min_raw_value`
2. For each card: probe PSA 10, PSA 9, PSA 8, BGS 10, BGS 9.5, BGS 9 in order
   - Skip lower grade if higher grade found no sales
3. Accumulate results into `graded_batch: dict[catalog_id → {grade: {fair_value, num_sales, min, max}}]`
4. Flush batch via JSONB merge upsert:
   ```sql
   INSERT INTO market_prices (card_catalog_id, graded_data)
   VALUES (%s, %s::jsonb)
   ON CONFLICT (card_catalog_id)
   DO UPDATE SET graded_data = market_prices.graded_data || EXCLUDED.graded_data
   ```

Graded scraping uses the same Chrome thread pool and `process_card()` engine — just with grade tokens appended to the card name (e.g. `"... [PSA 10]"`).

### Thread Safety

- One Chrome driver per thread (`threading.local()`)
- Shared `_progress` dict protected by `threading.Lock()`
- `ThreadPoolExecutor(max_workers=N)` — N = `--workers` argument

---

## daily_scrape.py — Personal Ledger Scraper

Scrapes all cards in the `cards` table (user ledger) and writes updated prices.

### What it does
1. Loads all users from `users` DB table
2. For each user: `SELECT * FROM cards WHERE user_id = ?`
3. Scrapes all cards via `process_card()` in parallel
4. Writes to `cards` table: `fair_value`, `trend`, `min_price`, `max_price`, `num_sales`, `top3_prices`, `confidence`, `last_scraped`
5. Appends to `card_price_history`: one row per card per day
6. Appends to `portfolio_history`: daily total value snapshot

### Usage
```bash
python daily_scrape.py --workers 3
python daily_scrape.py --user admin    # one user only
```

---

## scrape_beckett_catalog.py — Card Catalog Populator

Populates `card_catalog` with all cards ever produced, from 3 sources.

### Sources

| Source | URL | Method | Era |
|---|---|---|---|
| TCDB | tradingcarddatabase.com | `curl_cffi` with `impersonate="chrome124"` (Cloudflare bypass) | All eras |
| CLI | checklistinsider.com | Standard requests | 2022+ |
| CBC | cardboardconnection.com | requests + BeautifulSoup | 2008–2023 |

### Checkpoint System

`catalog_checkpoint.json` stores completed set keys as `"{source}|{sport}|{year}|{set_name}"`. On restart, already-completed sets are skipped. Safe to interrupt and resume at any time.

### TCDB Rate Limiting

- 1.5–3s between year-index requests
- 0.5–1.2s between set-level requests
- Exponential backoff on 429: 30 → 60 → 120 → 240s
- ~3,500+ premium/autograph sets require TCDB login credentials — skipped without them

### Output
Upsert on `(sport, year, set_name, card_number, player_name, variant)`. Updates `team`, `is_rookie`, `is_parallel`, `updated_at` if row already exists.

### Usage
```bash
python scrape_beckett_catalog.py --source tcdb --sport NHL --year-from 1951
python scrape_beckett_catalog.py --source cli --sport NHL --year-from 2022
python scrape_beckett_catalog.py --source cbc --sport NFL --year-from 2008 --year-to 2023
```

---

## scrape_nhl_stats.py — NHL Stats Fetcher

Fetches current-season player stats and standings from the NHL API.

### Player matching (3-stage)
1. Exact name match
2. Normalized (strip diacritics, lowercase)
3. Fuzzy (85% similarity cutoff)

### Output
- `player_stats` table: `(sport, player)` → JSONB `{current_season, history, bio}`
- `standings` table: `(sport, team)` → JSONB `{wins, losses, points, division, ...}`

---

## assign_catalog_tiers.py

One-time and periodic script that assigns `catalog_tier` to `card_catalog` rows.

**Tier logic:**
| Tier | Criteria |
|---|---|
| `staple` | High-demand rookies / key players with consistent eBay volume |
| `premium` | Notable players, sets, or parallels with elevated value |
| `stars` | Notable players who are not quite staple level |
| NULL | All other cards |

Tier drives which GitHub Actions workflow scrapes the card and how frequently.
