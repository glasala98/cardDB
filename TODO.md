# CardDB — TODO & Roadmap

Priority levels: **P1** = blocking or high-impact · **P2** = important, next up · **P3** = nice-to-have

---

## 🔄 Active (In Progress)

| Item | Notes |
|---|---|
| **Base-tier backfill** | ~8.5% priced as of 2026-03-19. Daily runs, ~4–6 weeks to 100% |
| **Premium/stars backfill** | Bumped to daily schedule until fully priced |
| **market_raw_sales backfill** | backfill_all_tiers.yml running daily — capturing full eBay history per card |

---

## P1 — High Impact, Do Next

### Frontend / UX
- [ ] **Mobile catalog layout** — card catalog needs responsive column collapse; site is live and mobile is broken
- [ ] **Portfolio value over time chart** — data exists in `portfolio_history`, just needs the line chart on `/charts`
- [ ] **Sell tracking** — record sale price + date per collection card; auto-calculate realized gain/loss vs cost basis

### Data / Backend
- [ ] **Raw sales analytics API** — expose `market_raw_sales` in endpoints: per-card sold history, volume over time, price trend from raw data (880K+ rows sitting unused)
- [ ] **Sealed products public browse page** — data is fully ready in `sealed_products` + `sealed_product_odds`; just needs a public `/sets` or `/sealed` page
- [ ] **Connection retry resilience** — `assign_catalog_tiers.py` and `scrape_nhl_stats.py` crash on `server closed the connection unexpectedly` with no retry. Add reconnect logic or retry wrapper in `db.py`

---

## P2 — Important, Schedule Soon

### Frontend / UX
- [ ] **Catalog full-text search** — single search bar across player name + set + year simultaneously (currently separate filters only)
- [ ] **Price alerts** — email notification when a tracked collection card moves >10% in 7 days; built on `market_price_history` + existing email secrets
- [ ] **Bulk import** — CSV upload to add multiple cards to collection at once
- [ ] **Rarity funnel** — visual print run breakdown per set (base → parallels → autos → 1/1s)

### Data / Backend
- [ ] **Refine price queries** — tighten sales window / outlier exclusion to reduce price spread noise on low-volume cards
- [ ] **master_db_daily sport filter fix** — when triggered with `sport=NHL`, the `if:` condition should skip NBA/NFL/MLB jobs entirely; currently they queue as skipped rather than not running

### Infrastructure
- [ ] **API rate limiting** — protect public `/catalog` and `/catalog/sealed-products` endpoints from abuse
- [ ] **Caching layer** — Redis for expensive aggregate queries: portfolio total, releases page set grid, catalog count

---

## P3 — Nice to Have

- [ ] **[AI] Vector Search** — pgvector on Railway PostgreSQL; embed card names for fuzzy matching / entity resolution (verify `CREATE EXTENSION IF NOT EXISTS vector` is supported first)
- [ ] **[AI] Entity Resolution Agent** — LangGraph agent to map ambiguous eBay titles to `card_catalog` records; replaces manual `_apply_variant_filter`
- [ ] **Crowdsourced Price Gap Filler** — user-submitted prices for cards with no eBay data → admin review queue

---

## Post-Backfill Optimization (Target: ~4–6 weeks)

Once base-tier reaches ~100% coverage, all daily runs become pure delta (tiny batches). Do these then:

- [ ] **Consolidate tier workflows** — merge staple/premium/stars/base into one unified daily workflow (runs are small enough to sequence)
- [ ] **Tighten stale-days** — premium 7→3 days, stars 30→7 days for fresher prices
- [ ] **Return schedules to steady-state** — premium back to weekly, stars back to weekly; base stays daily at stale-days 30
- [ ] **Disable/throttle backfill_all_tiers.yml** — switch from daily to weekly once raw sales are fully populated
- [ ] **Auto-tuning stale-days** — high-value staple cards stay at 1 day; low-value base cards can be 90 days; tune by tier + fair_value

---

## Completed ✓

<details>
<summary>Scraping & Data Collection</summary>

- [x] Catalog scraper: TCDB / CLI / CBC sources → 1.26M+ cards in `card_catalog`
- [x] Price scraper: eBay sold listings → `market_prices` + `market_price_history` (raw + graded modes)
- [x] Scrape tiers: `assign_catalog_tiers.py` classifies staple / premium / stars / base
- [x] Set info scraper: `scrape_set_info.py` → `sealed_products` + `sealed_product_odds`
- [x] GH Actions schedules: all tiers on daily/elevated schedules
- [x] Image retrieval: eBay images scraped → `market_prices.image_url`
- [x] Scraping resiliency: `scrape_run_errors` table, per-card error capture, consecutive-failure backoff
- [x] `market_raw_sales` table: permanent eBay sales storage, dedup by `listing_hash`
- [x] Backfill infrastructure: `backfill_raw_sales.yml` + `backfill_all_tiers.yml`
- [x] DSM shared memory fix: `SET max_parallel_workers_per_gather = 0` in `load_cards()`
- [x] Email notifications: start/cancel emails on `catalog_tier_base.yml` + `master_db_daily.yml`
- [x] Preflight DB check: absolute GB thresholds (warn 60GB, fail 70GB)
- [x] DB volume resize: 10GB → 80GB (2026-03-18)
- [x] NHL player stats scrape fix: INSERT column mismatch resolved
</details>

<details>
<summary>Data / Backend</summary>

- [x] `market_prices.ignored` admin flag
- [x] `market_prices.graded_data` JSONB for PSA/BGS
- [x] Performance indexes: pg_trgm GIN, expression index on year cast, partial index on fair_value
- [x] `sealed_products` + `sealed_product_odds` tables
- [x] `GET /catalog/sealed-products` filterable endpoint
- [x] Outlier quarantine: auto-flag prices >50% from player median; nightly workflow
</details>

<details>
<summary>Admin Dashboard</summary>

- [x] Pipeline Health tab: coverage by tier, last scrape per sport, GH Actions status cards
- [x] Outliers tab: detection + ignore/restore
- [x] Users tab: role management inline
- [x] Runs tab: KPI strip, delta + hit-rate charts, anomaly feed, live progress bars
- [x] Quality tab: stale/never-scraped/low-confidence KPIs
- [x] ETL Snapshot Audit: last 5 price snapshots per card
- [x] Sealed Products Manager: browse/edit MSRP + pack config
- [x] Consecutive failure badges + overdue detection
- [x] Timed-out anomaly detection + orphan run cleanup
- [x] Sealed data quality panel: sport mismatch + bad MSRP detection
</details>

<details>
<summary>New Releases Page</summary>

- [x] Set grid with sport filter, season range, coverage stats
- [x] Top 5 cards per set, deduplicated by player
- [x] MSRP + Box Price display from `sealed_products`
- [x] EV vs MSRP calculator
- [x] Hero Top Card highlight
- [x] Volatility indicators (7/14-day delta)
- [x] Individual sales drill-down in `CatalogCardDetail`
</details>

<details>
<summary>Catalog Page</summary>

- [x] Public browse, paginated, all filters
- [x] `CatalogCardDetail` slide-in panel
- [x] Tier badges + RC badge
- [x] Card image thumbnails in rows
- [x] Price history sparkline + snapshot table
</details>

<details>
<summary>Global / Infrastructure</summary>

- [x] Mobile nav: fixed bottom tab bar
- [x] RBAC: admin/user/guest roles
- [x] Railway deploy: Dockerfile, auto-deploy from main
- [x] JWT auth: 7-day expiry, bcrypt, PostgreSQL users table
- [x] DB health check workflow: daily disk monitoring
- [x] Coverage milestone email notifications
</details>
