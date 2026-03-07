# CardDB — Scraping Engine Deep Reference

Covers every function in `scrape_card_prices.py` and `scrape_master_db.py` — the complete eBay pricing pipeline.

---

## Overview: What happens when one card is priced

```
process_card("2023-24 Upper Deck - Young Guns #201 - Connor Bedard")
  │
  ├─ Stage 1: clean_card_name_for_search() → full eBay query
  │            search_ebay_sold() → raw results
  │            _apply_variant_filter() → filtered comps
  │            → if results: confidence=high, done
  │
  ├─ Stage 2: build_set_query() → drop parallel name
  │            search_ebay_sold() → raw results
  │            _apply_variant_filter()
  │            → if results: confidence=medium, done
  │
  ├─ Stage 3: build_simplified_query() → player + card# + serial + year only
  │            search_ebay_sold() → raw results
  │            _apply_variant_filter()
  │            → if results: confidence=low, done
  │
  ├─ Stage 4: (numbered cards only) get_nearby_serials()
  │            for each nearby serial:
  │              build_serial_comp_query() → comp-serial query
  │              search_ebay_sold()
  │              price × serial_multiplier(comp_serial, target_serial)
  │            → confidence=estimated, NOT stored historically
  │
  └─ Stage 5: build_player_card_query() → player + card# only, last resort
               → confidence=low

  _normalize_shipping(sales)          ← cap outlier shipping costs
  calculate_fair_price(sales, serial) ← produce fair_value + stats
  return (card_name, result_dict)
```

---

## Card Name Format

The entire system is built around a structured card name string:

```
"YEAR BRAND - SUBSET #CARDNUM - PLAYER [GRADE] /SERIAL"
```

Examples:
```
"2023-24 Upper Deck - Young Guns #201 - Connor Bedard"
"2021-22 O-Pee-Chee Platinum - Rainbow Foil #RC-201 - Trevor Zegras /99"
"2020 Panini Prizm - Silver Prizm #301 - Joe Burrow [PSA 10]"
```

Rules:
- Segments separated by ` - ` (space-dash-space)
- Segment 0: year + brand
- Segment 1: subset / parallel (may include card number)
- Last segment: player name
- Grade in square brackets: `[PSA 9]`, `[BGS 9.5]`
- Serial as `/N` or `#N/M` anywhere in the string

All parsing functions strip, regex, and split on this format.

---

## `scrape_card_prices.py` — Function Reference

### Query Building Functions

---

#### `clean_card_name_for_search(card_name) → str`
**Stage 1 query builder.** Produces the most specific eBay search possible.

**Priority order of terms included:**
1. Player name (always — the anchor)
2. Card number (`#201`)
3. Serial number (`/99`) — filters out base cards automatically
4. Variant/parallel name (`Rainbow Foil`) — from `_VARIANT_KEYWORDS`
5. Subset (`Young Guns`) — from a fixed list of ~60 known subsets
6. Year (`2023-24`)
7. Short brand (`OPC Platinum`, not `O-Pee-Chee Platinum`)

**Grade handling:**
- Raw card → appends `-PSA -BGS -SGC -graded` (exclude all graded)
- PSA 9 → appends `"PSA 9" -"PSA 1" -"PSA 2" ... -"PSA 8" -"PSA 10" -BGS -SGC`
- BGS 9.5 → appends `"BGS 9.5" -"BGS 6" -"BGS 7" ... -PSA -SGC`

This ensures results are only comparable sales, not mixed-grade lots.

**Brand abbreviation map:**
```
O-Pee-Chee Platinum → OPC Platinum
O-Pee-Chee          → OPC
Upper Deck Extended Series → UD Extended
```

---

#### `build_set_query(card_name) → str`
**Stage 2 query builder.** Drops the parallel/subset name; keeps serial + set + year.

Used when stage 1 returns no results — sometimes sellers don't include the parallel name in the title, just the base set name.

Terms included: player + card# + serial + year + short brand.

---

#### `build_simplified_query(card_name) → str`
**Stage 3 query builder.** Only player + card# + serial + year. No set, no parallel.

Casts the widest meaningful net while still being card-specific. Serial is kept so numbered-card comps don't mix with base cards.

---

#### `build_serial_comp_query(card_name, comp_serial) → str`
**Stage 4 query builder.** Substitutes a different serial number to find nearby comp sales.

Example: target is `/99` with no sales → query for `/75` and price-adjust via `serial_multiplier(75, 99)`.

Terms: player + card# + `/comp_serial` + year + brand.

---

#### `build_player_card_query(card_name) → str`
**Stage 5 query builder.** Last resort — player + card# only.

Strips everything else (year, serial, brand, variant). Used for cards whose names are too unusual for earlier stages, or un-numbered cards with no comps.

---

### eBay Scraping

---

#### `search_ebay_sold(driver, card_name, max_results=240, search_query=None) → list[dict]`

Scrapes eBay completed/sold listings. Returns up to `max_results` sale records.

**URL built:**
```
https://www.ebay.com/sch/i.html?
  _nkw={encoded_query}
  &_sacat=0          # all categories
  &LH_Complete=1     # completed listings
  &LH_Sold=1         # sold only
  &_sop=13           # sort: most recent first
  &_ipg=240          # 240 results per page
```

**Per-listing extraction:**
| Field | Source | Notes |
|---|---|---|
| `title` | `.s-card__title` text | |
| `item_price` | `.s-card__price` | formatted string e.g. `"$12.99"` |
| `shipping` | XPath shipping text | `"Free"` or `"$3.99"` |
| `price_val` | item + shipping float | total cost to buyer |
| `sold_date` | `.s-card__caption` regex | ISO `"YYYY-MM-DD"` |
| `days_ago` | `now - sold_date` | int or None |
| `listing_url` | `a.s-card__link[href]` | eBay strip `epid`, `itmprp`, `_skw` params |
| `image_url` | `img[src/data-src]` | `ebayimg.com` only |

**Filters applied per listing:**
1. Skip if `title` is empty
2. `title_matches_grade(title, grade_str, grade_num)` — grade match
3. Lot/bundle exclusion regex:
   - "you pick", "your pick", "u pick"
   - "lot of", "bundle"
   - "buy N get"
   - Card number ranges like "251-500"
   - Combination sets ("canvas outburst")

**Returns:** empty list on error or no results.

---

#### `title_matches_grade(title, grade_str, grade_num) → bool`

Validates a listing title matches exactly the target grade.

**Raw card (`grade_str=None`):**
- Returns `False` if title contains `PSA`, `BGS`, `SGC`, or `GRADED`

**PSA card (e.g. `"PSA 9"`):**
- Must contain `PSA 9` (regex: `PSA\s*9(?:\s|$|[^0-9])`)
- Must NOT contain any other PSA grade (`PSA 8`, `PSA 10`, etc.)
- Must NOT contain `BGS`

**BGS card (e.g. `"BGS 9.5"`):**
- Must contain `BGS 9.5` (handles decimal)
- Must NOT contain any other BGS grade
- Must NOT contain `PSA`

---

### Filtering Functions

---

#### `_apply_variant_filter(card_name, sales) → list[dict]`

**The most important post-search filter.** Removes sales for the wrong parallel.

**Example:** Card is "Rainbow Foil /99". Without this filter, eBay results might include "Rainbow Color Wheel /99" (different, higher-value parallel) and "Retro Rainbow" listings.

**How it works:**

1. `_extract_variant_keyword(card_name)` → finds the variant (e.g. `"Rainbow"`)
2. `_VARIANT_ALIASES.get(v_lower)` → synonyms (e.g. `{'autograph'}` for `'auto'`)
3. Build `supersets` list: all keywords where the variant is a substring, excluding aliases
   - "Rainbow" → supersets = ["Rainbow Foil", "Rainbow Color Wheel", "Speckled Rainbow", "Retro Rainbow"]
4. Per sale: keep if title contains variant (or alias), AND does NOT contain any superset

**Word-boundary matching** (`_kw_in_title`):
- Variants in `_WORD_BOUNDARY_VARIANTS` use `\b` regex: `ice`, `sp`, `ssp`, `mini`, `silk`, `wave`, `laser`, `clear`, `error`
- Prevents "ice" matching "price", "sp" matching "display"

**Base cards** (no variant extracted) → return sales unchanged.

---

#### `_extract_variant_keyword(card_name) → str`

Scans dash-separated segments of the card name for a matching keyword from `_VARIANT_KEYWORDS`.

Strips `[Base]`, card numbers, and blank segments first. Returns the FIRST match (list is ordered most-specific first, so "Rainbow Color Wheel" is matched before "Rainbow").

Returns `""` for base cards.

---

#### `_VARIANT_KEYWORDS`

130+ ordered list of known parallel names. Multi-word variants are listed BEFORE single-word variants so extraction picks the most specific match.

Coverage includes: OPC Platinum, Upper Deck, Panini Prizm, Panini Select, Donruss/Optic, Mosaic, Contenders, Topps Chrome, Finest, Bowman, Heritage, and generic parallels (Gold, Silver, Black, etc.).

---

#### `_VARIANT_ALIASES`
```python
{
    'auto':      {'autograph'},   # sellers use both interchangeably
    'autograph': {'auto'},
}
```

Prevents "Autograph" from being treated as a superset of "Auto" and excluded.

---

#### `_filter_sales_by_variant(card_name, sales) → list[dict]`

**Legacy filter** in `dashboard_utils.py` (used by the old single-card scraper path). Different approach than `_apply_variant_filter`: uses keyword extraction from the subset/parallel name and requires ALL keywords to be present (AND logic).

Returns empty list rather than falling back — a wrong-variant price is worse than "no data".

---

### Price Calculation

---

#### `calculate_fair_price(sales, target_serial=None) → (float, dict)`

The core pricing algorithm. Produces a single fair value from a list of eBay sales.

**Step 1 — Serial adjustment (numbered cards):**
```
adjust_sales_for_serial(sales, target_serial)
  → Prefer exact serial matches
  → If none, price-adjust other numbered comps via serial_multiplier()
  → Discard base (unnumbered) sales entirely
```

**Step 2 — Outlier removal:**
```
median_price = statistics.median(all prices)
keep only: price between (median / 3) and (median × 3)
```
Catches $0.99 "pick from list" auctions and lot sales. Falls back to all sales if filtering removes everything.

**Step 3 — Trend determination:**
```
Sort by recency (dated first, then undated)
If 4+ sales:
  Split into older half and recent half
  recent_avg vs older_avg → pct_change
  pct_change > 10%  → trend = "up"
  pct_change < -10% → trend = "down"
  otherwise         → trend = "stable"
If 2-3 sales:
  Most recent vs oldest: ±10% threshold
```

**Step 4 — Pick representative from top 3 most recent:**
```
trend = "up"     → highest of top 3 (market is rising, favor current price)
trend = "down"   → lowest of top 3 (market is falling, favor current price)
trend = "stable" → median of top 3
```

**Returns:**
```python
fair_price = 45.00  # float

stats = {
    'fair_price': 45.00,
    'chosen_sale': "2023-24 Upper Deck Young Guns Bedard #201",
    'chosen_date': "2026-02-15",
    'trend': "stable",
    'top_3_prices': ["$48.00", "$45.00", "$43.00"],
    'median_all': 44.50,
    'num_sales': 12,
    'outliers_removed': 1,
    'min': 38.00,
    'max': 52.00,
}
```

---

#### `_normalize_shipping(sales) → list[dict]`

Caps outlier shipping costs before they inflate the fair price.

**Algorithm:**
1. Parse `item_price` and infer shipping = `price_val - item_price`
2. Compute median of all non-zero shipping values
3. Cap = median × 2.0
4. For any sale with shipping > cap: replace `price_val` with `item_price + median_shipping`

**Example:** 12 comps at $3-5 shipping, 2 at $18 → those 2 normalized to ~$4.

---

### Serial Number Functions

---

#### `extract_serial_run(text) → int | None`

Extracts `/N` from any string. Returns `99` from `"#201/99"` or `"Connor Bedard /99"`.

---

#### `SERIAL_VALUE` — Print-run multiplier table

Maps print-run limits to relative market value multipliers, with /99 as baseline (1.0):

| Serial | Multiplier | Meaning |
|---|---|---|
| /1 | 50.0 | 50× more valuable than /99 |
| /5 | 12.0 | |
| /10 | 6.0 | |
| /25 | 2.8 | |
| /50 | 1.7 | |
| /99 | 1.0 | baseline |
| /199 | 0.6 | 40% less |
| /499 | 0.3 | 70% less |
| /999 | 0.15 | |

Values between known entries are linearly interpolated. Values above /999 extrapolate proportionally.

---

#### `serial_multiplier(from_serial, to_serial) → float`

Converts a comp serial's price to an estimate for the target serial.

```
multiplier = SERIAL_VALUE[to_serial] / SERIAL_VALUE[from_serial]
```

**Example:** comp is /10 ($60), target is /99
```
serial_multiplier(10, 99) = SERIAL_VALUE[99] / SERIAL_VALUE[10] = 1.0 / 6.0 = 0.167
estimated_price = $60 × 0.167 = $10.00
```

---

#### `get_nearby_serials(serial, n=4) → list[int]`

Returns the N closest known print-run values to use as comp serials when no direct sales exist (stage 4 fallback).

Example: `get_nearby_serials(99)` → `[100, 75, 150, 50]` (sorted by proximity).

---

#### `adjust_sales_for_serial(sales, target_serial) → list[dict]`

1. Separate: exact serial matches vs. other numbered comps vs. unnumbered
2. If exact matches exist → return those only (no adjustment)
3. If no exact matches → price-adjust all numbered comps via `serial_multiplier()`, add `_serial_adjusted=True` and `_original_serial` fields
4. Unnumbered sales discarded (different product)

---

### Driver Functions

---

#### `create_driver() → webdriver.Chrome`

Creates a headless Chrome instance with:
- `--headless=new` — new headless mode (better than legacy)
- `--no-sandbox`, `--disable-dev-shm-usage` — required for Docker/CI
- `--blink-settings=imagesEnabled=false` — skip loading images (faster)
- `--disable-blink-features=AutomationControlled` — basic bot detection bypass
- Spoofed user-agent: `Mozilla/5.0 ... Chrome/120.0.0.0 Safari/537.36`
- `excludeSwitches: ['enable-automation']` — removes automation flag
- Memory flags: `--no-zygote`, `--disable-background-networking`, `--disable-sync`
- 15s page load timeout, 10s script timeout
- `page_load_strategy: 'eager'` — don't wait for all resources

Uses `webdriver_manager` to auto-download ChromeDriver if available; falls back to system Chrome.

---

#### `get_driver() → webdriver.Chrome`

Returns the thread-local Chrome driver, creating it on first call. `scrape_master_db.py` monkey-patches this to use its own faster driver with reduced sleep delays.

---

### Grade Detection Functions

---

#### `is_graded_card(card_name) → bool`

Returns `True` if card name contains `PSA N` or `BGS N.N` (regex `\b(PSA|BGS)\s+\d+(\.\d+)?`).

---

#### `get_grade_info(card_name) → (str, float) | (None, None)`

Extracts grade label and numeric value.

Checks BGS first (handles decimals like 9.5 before PSA integer matching).

Supports both bracketed (`[PSA 10]`) and bare (`PSA 10`) forms.

Examples:
- `"[PSA 9]"` → `("PSA 9", 9.0)`
- `"[BGS 9.5]"` → `("BGS 9.5", 9.5)`
- No grade → `(None, None)`

---

#### `_extract_player_name(last_segment) → str`

Strips card numbers (`#66`, `#66/99`) and parenthetical text from the last dash-segment, then returns the first 2-3 capitalized words as the player name.

Prevents descriptive segments like "Celebrini Scores First Goal of Career #66" from returning the full sentence instead of "Macklin Celebrini".

---

## `scrape_master_db.py` — Function Reference

The orchestration layer that runs `process_card()` in parallel across thousands of catalog cards.

---

### `build_card_name(row: dict) → str`

Converts a `card_catalog` DB row into the standard card name string format expected by `process_card()`.

```python
# Example output:
"2023-24 Upper Deck - Young Guns #201 - Connor Bedard"
"2021-22 O-Pee-Chee Platinum - Rainbow Foil #RC-201 - Trevor Zegras /99"
```

Logic:
- `{year} {brand} - {set_name} #{card_number} - {player_name}`
- If `variant` is not blank/base: append variant (or `/print_run` if serialized)

---

### `load_cards(args) → list[dict]`

Queries `card_catalog` for cards to scrape. Implements the **delta gate** — never fires Chrome for fresh data.

**Delta gate logic:**
```sql
LEFT JOIN market_prices mp ON mp.card_catalog_id = cc.id
WHERE ... AND (
    mp.scraped_at IS NULL              -- never scraped
    OR mp.scraped_at < NOW() - INTERVAL '{stale_days} days'  -- stale
)
ORDER BY mp.scraped_at NULLS FIRST, cc.is_rookie DESC, cc.year DESC
```

With `--force`: no join, no stale filter — re-scrape everything.

**Filters available:**
| Arg | SQL condition |
|---|---|
| `--sport NHL` | `cc.sport = 'NHL'` |
| `--year 2024-25` | `cc.year = '2024-25'` |
| `--rookies` | `cc.is_rookie = TRUE` |
| `--catalog-tier staple` | `cc.scrape_tier = 'staple'` |
| `--tier rookie_recent` | `cc.is_rookie = TRUE AND year >= 2015` |
| `--year-from 2015` | `SPLIT_PART(year,'-',1)::int >= 2015` |
| `--stale-days 7` | `scraped_at < NOW() - '7 days'` |

Returns rows including `existing_price` (from `market_prices`) for delta tracking.

---

### `scrape_one(card: dict) → (catalog_id, result_dict)`

Worker function for one raw (ungraded) card. Called by `ThreadPoolExecutor`.

1. `build_card_name(card)` → name string
2. `process_card(name)` → eBay result
3. Compare `new_price` vs `existing_price` → increment `_progress['deltas']` if changed
4. On exception: quit+restart driver, retry once; on second failure → return empty result

**Thread safety:** all `_progress` updates behind `_lock`.

---

### `scrape_one_graded(card: dict, grades: list) → (catalog_id, graded_results)`

Worker for graded prices. Probes PSA and BGS grades in order, skipping lower grades if the highest grade had no sales.

**Probe order:**
- PSA: PSA 10 → PSA 9 → PSA 8
- BGS: BGS 10 → BGS 9.5 → BGS 9
- If PSA 10 has no sales → skip PSA 9 and PSA 8 (same group, skip-rest=True)

**Returns:**
```python
{
    catalog_id: 12345,
    graded_results: {
        'PSA 10': {'fair_value': 80.00, 'num_sales': 3, 'stats': {...}},
        'PSA 9':  {'fair_value': 45.00, 'num_sales': 5, 'stats': {...}},
        'BGS 9.5':{'fair_value': 55.00, 'num_sales': 2, 'stats': {...}},
    }
}
```

---

### `save_prices_batch(results: list)`

Batch DB write for raw scrape results. Called every 50 cards (BATCH_SIZE).

**market_prices UPSERT:**
```sql
INSERT INTO market_prices (card_catalog_id, fair_value, trend, confidence, num_sales, scraped_at)
VALUES %s
ON CONFLICT (card_catalog_id) DO UPDATE SET
    prev_value = market_prices.fair_value,   -- preserve previous for trend display
    fair_value = EXCLUDED.fair_value,
    trend      = EXCLUDED.trend,
    confidence = EXCLUDED.confidence,
    num_sales  = EXCLUDED.num_sales,
    scraped_at = EXCLUDED.scraped_at,
    updated_at = NOW()
```

**market_price_history INSERT (SCD Type 2):**
```sql
INSERT INTO market_price_history (...)
SELECT ... WHERE NOT EXISTS (
    SELECT 1 FROM market_price_history h
    WHERE h.card_catalog_id = i.card_catalog_id
      AND h.fair_value = i.fair_value
      AND h.scraped_at = (
          SELECT MAX(scraped_at) FROM market_price_history
          WHERE card_catalog_id = i.card_catalog_id
      )
)
ON CONFLICT (card_catalog_id, scraped_at) DO NOTHING
```

Only inserts when fair_value differs from the most recent history row. This is true SCD Type 2 — no consecutive duplicate prices.

---

### `bump_tiers_by_sales(catalog_ids: list)`

Post-scrape tier demotion. Adjusts `catalog_tier` downward based on observed sales volume.

**Thresholds (30-day window via `num_sales` in market_prices):**
| Sales | Tier |
|---|---|
| ≥ 10 | staple |
| 3–9 | premium |
| 1–2 | stars |
| 0 | base |

**Only demotes, never promotes.** A card that suddenly has 15 sales stays at its tier until `assign_catalog_tiers.py --all` re-runs promotion.

Called after each batch in `--catalog-tier` mode only.

---

### `_get_fast_driver()`

`scrape_master_db.py` monkey-patches `scrape_card_prices.get_driver` with this function, which:
1. Checks if thread-local driver is still alive (via `driver.title`)
2. Quits and removes dead drivers
3. Creates new driver via `_create_fast_driver()` (more aggressive memory flags)

Also patches `scrape_card_prices.time.sleep` to cap all sleep calls at 0.3s (vs the 0.5-1.5s in the standalone scraper), since the bulk scraper operates under tighter time budgets.

---

### `main()` — Program entry point

**Raw mode pipeline:**
```
load_cards(args)                    → list of cards to scrape
ThreadPoolExecutor(workers)
  for each card: submit scrape_one()
  as completed:
    if num_sales > 0: add to batch
    every 50 cards: save_prices_batch() + bump_tiers_by_sales()
    print progress: [done/total] found | deltas | errors | ETA
```

**Graded mode pipeline:**
```
load_cards(args)
Filter: only cards with market_prices.fair_value >= min_raw_value

ThreadPoolExecutor(workers)
  for each card: submit scrape_one_graded(card, grades)
  as completed:
    accumulate graded_data dict: {catalog_id: {grade: {fair_value, ...}}}
    every 50 cards: flush graded_batch via JSONB merge upsert
    print progress
```

**Graded JSONB upsert (merge, not replace):**
```sql
INSERT INTO market_prices (card_catalog_id, graded_data)
VALUES %s
ON CONFLICT (card_catalog_id) DO UPDATE SET
    graded_data = market_prices.graded_data || EXCLUDED.graded_data,
    updated_at  = NOW()
```
`||` is PostgreSQL JSONB merge — adds new grade keys, updates existing ones, keeps unaffected grades intact.

---

## Data Flow Summary

```
card_catalog row
    → build_card_name()
    → process_card()
        → clean_card_name_for_search() / build_*_query()
        → search_ebay_sold() × up to 5 stages
        → _apply_variant_filter()
        → _normalize_shipping()
        → calculate_fair_price()
            → adjust_sales_for_serial() [if numbered]
            → outlier removal
            → trend calculation
            → top-3 representative pick
    → save_prices_batch() [raw] or graded_batch flush [graded]
        → market_prices UPSERT
        → market_price_history INSERT (SCD Type 2)
```

---

## What "NOT FOUND" means

When all 5 stages return 0 results:
- `confidence = 'none'` (or `'not found'` for ledger cards)
- `fair_value = $5.00` (the `DEFAULT_PRICE` constant)
- No history row written (no delta)
- CardInspect shows manual price override form
