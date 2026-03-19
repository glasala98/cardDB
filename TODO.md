# CardDB — Master TODO & Roadmap

---

## Scraping & Data Collection
- [x] **Catalog Scraper:** checklistinsider / cardboardconnection / TCDB / Beckett sources — populates card_catalog (1.26M+ cards)
- [x] **Price Scraper:** eBay sold listings → market_prices + market_price_history (raw + graded modes)
- [x] **Scrape Tiers:** assign_catalog_tiers.py classifies staple / premium / stars / base
- [x] **Set Info Scraper:** scrape_set_info.py — cardboardconnection MSRP, pack config, release date, odds → sealed_products
- [x] **GH Actions Schedules:** daily staple, daily/elevated premium+stars (backfill), daily base (backfill), Sunday graded, monthly set info
- [x] **NHL Player Stats scrape failing** — fixed INSERT column mismatch (updated_at listed but not in values tuple)
- [x] **Image Retrieval:** scrape card images from eBay listings during price scrape; store in market_prices.image_url
- [x] **Scraping Resiliency:** scrape_run_errors table; per-card error capture + DB flush; consecutive-failure backoff (5→10s, 10→30s, 20→90s); admin Runs tab error drill-down
- [x] **market_raw_sales table:** permanent storage for every individual eBay sold listing (880K+ rows, dedup by listing_hash)
- [x] **Backfill infrastructure:** backfill_raw_sales.yml + backfill_all_tiers.yml workflows to populate market_raw_sales from historical data
- [x] **DSM shared memory fix:** SET max_parallel_workers_per_gather = 0 in scrape_master_db.py load_cards() to prevent PostgreSQL exhaustion on Railway
- [x] **Email notifications:** start/cancel emails on catalog_tier_base.yml and master_db_daily.yml (dawidd6/action-send-mail@v3)
- [x] **Preflight DB check:** absolute GB thresholds (--warn-gb 60 --fail-gb 70) — not percentage-based; runs before all heavy scrape jobs
- [x] **DB volume resize:** 10GB → 80GB (2026-03-18), current usage ~11GB filesystem
- [ ] **Base-tier backfill completion:** ~8.5% priced as of 2026-03; needs ~4-6 more weeks of daily runs to reach 100%
- [ ] **[AI] Entity Resolution Agent:** LangGraph agent to map ambiguous eBay titles to card_catalog records

## Data / Backend
- [x] **market_prices.ignored:** admin flag to hide bad prices from public catalog
- [x] **market_prices.graded_data JSONB:** PSA/BGS prices per card keyed by grade
- [x] **Performance indexes:** pg_trgm GIN on player_name/set_name, expression index on year cast, partial index on fair_value
- [x] **sealed_products + sealed_product_odds tables:** MSRP / pack config / odds per set/product type
- [x] **GET /catalog/sealed-products:** filterable API endpoint with nested odds
- [x] **Populate sealed_products:** trigger scrape_set_info GH Actions workflow for first data run (all sports, 2022+)
- [x] **Lock ignore/delete to admin:** PATCH /admin/market-prices/{id}/ignore already uses _require_admin
- [x] **[AI] Outlier Quarantine:** auto-flag prices deviating >50% from player median; quarantine_outliers.py + nightly workflow
- [ ] **Refine price queries:** tighten sales window / outlier exclusion to reduce price spread noise
- [ ] **[AI] Vector Search:** embed 1.26M records for sub-second fuzzy card matching (needs pgvector on Railway PostgreSQL)
- [ ] **Raw sales analytics API:** expose market_raw_sales in endpoints — per-card sold history, price trend from raw data

## Admin Dashboard
- [x] **Pipeline Health tab:** catalog coverage by tier, last scrape per sport, GH Actions status cards
- [x] **Quarantine/Outliers tab:** outlier detection (>5× player median), ignore/restore toggle
- [x] **Users tab:** role management (admin/user/guest) inline
- [x] **Runs tab:** KPI strip, delta + hit-rate charts, date range filter, refresh, anomaly feed
- [x] **Quality tab:** stale/never-scraped/low-confidence KPIs, freshness by tier bar, priority stale + low-confidence card tables
- [x] **ETL Snapshot Audit:** show last 5 price snapshots per card (data already in market_price_history)
- [x] **Sealed Products Manager:** view/edit MSRP and pack config per set inline in admin (Sealed tab)
- [x] **Live progress bars:** cards_processed + cards_found updated every 50 cards mid-run; shows hit rate + cards/hr + ETA
- [x] **Consecutive failure badges + overdue detection:** red ✕N badge; amber overdue badge from cadence inference
- [x] **Timed-out anomaly + orphan cleanup:** distinct status for killed runs; 7h broad sweep + narrow same-workflow cleanup
- [x] **Sealed data quality panel:** sport mismatch detection, $1.00 parse error detection, one-click fix
- [x] **NHS stats retry:** exponential backoff (1s/2s/4s) catches TimeoutError/OSError on NHL API calls
- [ ] **Crowdsourced Price Gap Filler:** user-submitted prices for cards with no eBay data → admin review queue

## New Releases Page
- [x] **Set grid:** sport filter tabs, season range, card count / top value / avg / sales / % priced per set
- [x] **Top 5 cards per set:** deduplicated by player, RC badge guarded by variant keyword
- [x] **Sort logic:** year desc → populated first → flagship count → total sales → top value
- [x] **Flagship badge:** shown when set has staple/premium cards
- [x] **Momentum %:** avg price vs prev_value delta
- [x] **MSRP + Box Price display:** show Hobby/Blaster MSRP on each set card (data in sealed_products)
- [x] **EV vs MSRP:** compare top-N card values against hobby box MSRP to show expected value
- [x] **Hero Top Card:** highlight the single highest-value card across all current releases
- [x] **Volatility indicators:** 7/14-day price delta from market_price_history (delta_7d_pct on set cards)
- [x] **Individual sales drill-down:** last 5 price snapshots (date/fair value/range/sales) in CatalogCardDetail panel
- [ ] **Rarity funnel:** visual print run breakdown (base → parallels → autos → 1/1s)

## Catalog Page
- [x] **Public browse:** no login required, paginated, sport/year/set/search/rookie/price filters
- [x] **CatalogCardDetail panel:** slide-in with price summary, sparkline, add-to-collection
- [x] **Tier badges:** Staple / Premium / Stars + RC badge
- [x] **Card image in rows:** CardThumb component in catalog rows — shows eBay image or sport-colored initials fallback
- [x] **Price history graph:** sparkline + snapshot table in CatalogCardDetail slide-in panel
- [ ] **Mobile layout:** card catalog needs responsive column collapse for small screens

## Card Ledger / Collection
- [x] **CardInspect page:** side-by-side layout, lightbox image, grading ROI
- [x] **Collection table:** tracks owned cards by grade, cost basis, purchase date
- [ ] **Bulk import:** CSV upload to add multiple cards to collection at once
- [ ] **Sell tracking:** record sale price + date; auto-calculate realized gain/loss vs cost basis

## Global / Infrastructure
- [x] **Mobile nav:** fixed bottom tab bar (Catalog / Ledger / Portfolio / Settings)
- [x] **RBAC:** admin/user/guest roles, AdminRoute guard, useIsAdmin() hook
- [x] **Railway deploy:** Dockerfile, auto-deploy from main, migrations run on startup
- [x] **JWT auth:** 7-day expiry, bcrypt, PostgreSQL users table
- [x] **DB health check workflow:** daily disk usage monitoring (db_health_check.yml), warns at 60GB, fails at 70GB
- [x] **Coverage milestone notifications:** email when base-tier coverage crosses 10% milestones (coverage_notify.yml)
- [ ] **Sealed products public browse page:** sport/year filter, set list with MSRP, box price, pack config
- [ ] **Portfolio value over time chart:** line chart on Charts page using market_price_history
- [ ] **Price alerts:** in-app or email notification when a tracked card moves >10% in 7 days
- [ ] **Catalog full-text search bar:** search player name + set + year simultaneously
- [ ] **Caching layer:** Redis/Memcached for expensive aggregate queries (portfolio total, releases page)
- [ ] **API rate limiting:** protect public endpoints from abuse

---

## Post-Backfill Optimization (Target: ~4-6 weeks from 2026-03)

These items become actionable once the base-tier backfill reaches ~100% coverage.

- [ ] **Switch all tiers to delta mode:** once base is 100% priced, daily runs become pure stale-days delta only. Estimated run time: 6h → ~10 minutes per sport per tier.
- [ ] **Reduce stale-days for premium/stars:** premium 7→3 days, stars 30→7 days for fresher prices
- [ ] **Return premium/stars to less frequent schedules:** weekly for premium, monthly for stars — once backfill is done and delta batches are tiny
- [ ] **Disable or reduce backfill_all_tiers.yml frequency:** switch from daily to weekly once raw sales are fully backfilled
- [ ] **Consolidate tier workflows:** consider merging staple/premium/stars/base into one unified daily workflow once batches are small enough
- [ ] **Auto-tuning stale-days:** adjust stale-days based on card popularity/value — staple high-value cards stay at 1 day, low-value base cards can be 90 days
- [ ] **Add pgvector extension:** `CREATE EXTENSION IF NOT EXISTS vector` in schema.sql + verify Railway PostgreSQL supports it
- [ ] **Vector-based entity resolution:** replace manual _apply_variant_filter with semantic similarity matching using embedded card names
