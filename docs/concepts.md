# CardDB — Core Concepts

Key vocabulary, mental models, and design decisions that show up everywhere in the codebase.

---

## Card Name Format

The canonical card identifier used throughout the system — in the ledger, scraper, price history, and eBay search queries:

```
"YEAR BRAND - SUBSET #CARDNUM - PLAYER [GRADE] /SERIAL"
```

Examples:
```
"2023-24 Upper Deck - Young Guns #201 - Connor Bedard"
"2023-24 Upper Deck - Young Guns #201 - Connor Bedard [PSA 10]"
"2023-24 Upper Deck - Ice #45 - Auston Matthews /99"
"2023-24 Topps - Chrome #150 - Victor Wembanyama [BGS 9.5] /49"
```

**Rules:**
- Year is `YYYY` for single seasons or `YYYY-YY` for hockey (e.g. `2023-24`)
- Set and subset are separated by ` - `
- Card number is prefixed by `#`
- Player name comes after the card number, separated by ` - `
- Grade in square brackets: `[PSA 10]`, `[BGS 9.5]`, `[SGC 10]`
- Serial number prefixed by `/`: `/99`, `/1`, `/249`

The `parse_card_name()` function in `dashboard_utils.py` deconstructs this string into its component fields.

---

## Two Card Systems: Ledger vs. Collection

There are two separate systems for tracking cards you own. They are not linked to each other.

### Ledger (`cards` table)
- **The original system.** Text-keyed by card name string.
- Predates the catalog. Each row is a card name string + fair value + price history.
- Supports: scan-to-add, bulk CSV import, scrape history, archive/restore.
- UI: `/ledger` page → `CardInspect` detail view
- Scraped by `daily_scrape.py` (triggered via "Rescrape All" or GitHub Actions).

### Collection (`collection` table)
- **The catalog-linked system.** Each row has a `card_catalog_id` FK.
- Tracks ownership of catalog cards: grade, quantity, cost basis, purchase date, notes.
- Prices come from `market_prices` (scraped by `scrape_master_db.py`), not from individual scrapes.
- UI: `/collection` page (tab alongside `/catalog`)
- Does not have its own scrape trigger — relies on the catalog scrape workflows.

**When to use which:**
- If you want to track a specific card you bought (with cost basis and P&L), add it to the Ledger.
- If you want to see what cards you own from the reference catalog (and compare to market prices), use Collection.

---

## Card Catalog (`card_catalog` table)

The reference database of ~1.26M cards ever produced across NHL/NBA/NFL/MLB. Every card that was ever manufactured has (or should have) a row here.

**Sources:**
- **TCDB** (tradingcarddatabase.com) — primary source, all eras
- **CLI** (checklistinsider.com) — 2022+ modern sets
- **CBC** (cardboardconnection.com) — 2008–2023

Cards in the catalog are identified by: `(sport, year, set_name, card_number, player_name, variant)`.

The catalog is append-and-update only — rows are never deleted. Populated by `scrape_beckett_catalog.py`.

---

## Catalog Tiers

Each card in `card_catalog` has a `catalog_tier` field that controls how often it gets scraped for market price data.

| Tier | Scrape Schedule | Typical Cards |
|------|----------------|---------------|
| `staple` | Daily | High-demand rookies, key players with consistent eBay volume |
| `premium` | Weekly (Sunday) | Notable players and sets with elevated value |
| `stars` | Weekly (Sunday) | Solid players, not quite staple-level |
| `NULL` | Never | Everything else — obscure commons, low-value parallels |

Tiers are assigned by `assign_catalog_tiers.py` and can be demoted (but never auto-promoted) by `bump_tiers_by_sales()` in `scrape_master_db.py` based on observed eBay sales volume.

---

## Market Prices (`market_prices` table)

Current pricing snapshot for each card in the catalog. One row per `card_catalog_id`.

Key fields:
- `fair_value` — current estimated market value (CAD)
- `prev_value` — value before the last scrape
- `trend` — `up` / `down` / `stable`
- `confidence` — `high` / `medium` / `low` / `estimated` / `none`
- `num_sales` — number of eBay sold listings found
- `graded_data` — JSONB blob with PSA/BGS prices: `{"PSA 10": {"fair_value": 150.00, "num_sales": 8}, ...}`
- `scraped_at` — timestamp of last scrape (used by `--stale-days` delta gate)

---

## Price History (SCD Type 2)

`market_price_history` stores price changes over time — but **only when the price actually changes**. This is a Slowly Changing Dimension Type 2 pattern: a new row is only inserted when the new `fair_value` differs from the most recent stored value.

```sql
INSERT INTO market_price_history (card_catalog_id, fair_value, num_sales, scraped_at)
SELECT %s, %s, %s, NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM market_price_history
    WHERE card_catalog_id = %s
    ORDER BY scraped_at DESC LIMIT 1
    HAVING fair_value = %s
)
```

This means the history table only has meaningful deltas — not a row for every daily scrape when price is unchanged.

---

## Scrape Confidence

Every eBay price estimate comes with a confidence level indicating how closely the search matched the actual card:

| Level | What matched | Reliability |
|-------|-------------|-------------|
| `high` | Exact parallel + serial + year + set | Very reliable |
| `medium` | Set + serial (parallel name dropped) | Good |
| `low` | Broad: player + card# + serial + year only | Rough estimate |
| `estimated` | Serial-extrapolated from nearby print run | Derived, not observed |
| `none` | No eBay sales found at any stage | No data — defaults to $5.00 |

The 4-stage search strategy in `scrape_card_prices.py` tries stages in order until sales are found.

---

## Serial Numbers and Print Runs

Sports cards are often produced in a limited print run, indicated by a serial number like `/99` (meaning this card is #X of 99 total). Rarer cards command higher prices.

The `SERIAL_VALUE` table in `scrape_card_prices.py` maps print runs to relative market multipliers (using `/99` as the 1.0 baseline):

| Print Run | Multiplier |
|-----------|-----------|
| /1 | 50.0× |
| /5 | 12.0× |
| /10 | 7.0× |
| /25 | 3.5× |
| /50 | 2.0× |
| /99 | 1.0× (baseline) |
| /249 | 0.6× |
| /999 | 0.3× |
| unlimited | 0.2× |

When Stage 4 (estimated confidence) is triggered, the scraper finds eBay sales for the nearest available print run and multiplies the price by the ratio between the two multipliers.

---

## Variants / Parallels

Most modern card sets are produced in multiple parallel versions — different foil treatments, colors, or patterns — of the same base card. These are called "parallels" or "variants."

Examples for the same base card:
- Base (no variant)
- Gold Foil
- Rainbow Foil
- Autograph /99
- Printing Plate /1

Variants dramatically affect price — a base card worth $5 might have a Rainbow /25 worth $200. The scraper's `_apply_variant_filter()` function strips eBay results that belong to a different parallel than the card being priced, using the `_VARIANT_KEYWORDS` list of 130+ known parallel names.

**Alias handling:** `Auto` and `Autograph` are treated as the same variant (`_VARIANT_ALIASES`), since sellers use both spellings interchangeably.

**Word boundary matching:** Short variants like `ice`, `sp`, `wave` use regex `\b` boundaries to avoid false matches inside common words (`price` → `ice`, `display` → `sp`).

---

## Graded vs. Raw Cards

Cards come in two conditions:
- **Raw** — ungraded, in whatever condition the seller claims. Most cards are raw.
- **Graded** — professionally assessed and sealed in a tamper-evident case by PSA, BGS (Beckett), or SGC. Comes with a numeric grade.

Common grading scales:
- **PSA**: 1–10 (PSA 10 = Gem Mint, the highest)
- **BGS**: 1–10 in 0.5 increments (BGS 9.5 = Gem Mint, BGS 10 = Pristine, rare)

Graded cards sell for a premium over raw depending on the grade. The Grading ROI calculator on the `CardInspect` page shows the raw baseline vs. PSA/BGS grades to help decide if grading is profitable.

Graded prices are stored in `market_prices.graded_data` JSONB and scraped by `scrape_master_db.py --graded` (Sunday runs, staple-tier cards with `fair_value >= $5`).

---

## Fair Value Calculation

The "fair value" shown throughout the app is **not** the average sale price. It's the **median of the 3 most recent sales** after outlier removal, with a trend adjustment:

1. Remove outliers: drop sales priced > 3× median or < ⅓ median
2. Sort remaining sales by date (newest first)
3. Calculate trend: compare average of last 3 sales vs previous 3
   - > 10% higher → `up`
   - > 10% lower → `down`
   - Otherwise → `stable`
4. Pick from the top 3 most recent sales:
   - Trending up → pick the highest of the 3 (reflects rising market)
   - Trending down → pick the lowest of the 3 (reflects falling market)
   - Stable → pick the median of the 3

This makes fair value responsive to recent market trends while avoiding single-sale anomalies.

---

## Delta Gate (Stale Days)

To avoid re-scraping cards that already have fresh data, `scrape_master_db.py` uses a `--stale-days` argument (default 7). During `load_cards()`, only cards whose `market_prices.scraped_at` is older than `NOW() - INTERVAL 'N days'` (or NULL) are queued for scraping.

This prevents redundant Chrome sessions for already-fresh cards, which is critical given the GitHub Actions runner time limits.

---

## Currency

All prices in the database are stored in **CAD (Canadian dollars)**. The frontend converts to USD on display using a live exchange rate fetched once per session from a public FX API.

The currency toggle in Settings (and the `CurrencyContext`) switches the display between CAD and USD. The `fmtPrice(v)` function from `CurrencyContext` handles the conversion.

---

## Public Mode

Appending `?public=true` to any URL makes the app read-only and skips the login requirement. The `PublicModeContext` propagates this flag throughout the app:
- Catalog is browsable
- All write actions (add to collection, edit, delete) are disabled
- "Sign in to add" is shown instead of action buttons

Useful for sharing a read-only view of the catalog with someone who doesn't have an account.

---

## Auth Roles

| Role | Access |
|------|--------|
| `admin` | Full access: all pages, user management, scrape health panel |
| `user` | Standard access: catalog, own ledger/collection/portfolio |
| `guest` | Read-only: catalog browse only (pre-filled login: guest/guest) |

JWT tokens are issued on login and stored in `localStorage`. The `AuthContext` validates the token on mount via `GET /api/auth/me`.

---

## GitHub Actions as the Compute Layer

No scraping or data processing runs on the local machine or the Railway server. All compute happens on **GitHub Actions runners**:

- Scraper scripts (`scrape_master_db.py`, `scrape_beckett_catalog.py`, `daily_scrape.py`) are triggered by cron schedules or `workflow_dispatch` events
- Chrome is installed fresh on each runner for Selenium scraping
- Results write directly to the Railway PostgreSQL database via `DATABASE_URL`

The local machine and Railway server are only for: code editing, git push, serving the web app, and API requests. This separation keeps Railway costs low (no long-running compute jobs on the server).

---

## Checkpoint System

`catalog_checkpoint.json` tracks which catalog sets have been fully scraped by `scrape_beckett_catalog.py`. Each completed set is recorded as `"{source}|{sport}|{year}|{set_name}"`.

On restart (e.g., after a GitHub Actions timeout), already-completed sets are skipped automatically. Safe to interrupt at any time — progress is never lost.
