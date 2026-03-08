# CardDB — Master TODO & Roadmap

---

## Scraping & Data Collection
- [x] **Catalog Scraper:** checklistinsider / cardboardconnection / TCDB / Beckett sources — populates card_catalog (2.6M+ cards)
- [x] **Price Scraper:** eBay sold listings → market_prices + market_price_history (raw + graded modes)
- [x] **Scrape Tiers:** assign_catalog_tiers.py classifies staple / premium / stars / base
- [x] **Set Info Scraper:** scrape_set_info.py — cardboardconnection MSRP, pack config, release date, odds → sealed_products
- [x] **GH Actions Schedules:** daily staple, weekly full sweep, monthly premium/stars/graded, monthly set info
- [x] **NHL Player Stats scrape failing** — fixed INSERT column mismatch (updated_at listed but not in values tuple)
- [ ] **Image Retrieval:** scrape card images from eBay listings during price scrape; store in market_prices.image_url
- [ ] **Scraping Resiliency:** central error logging, retry logic, rate-limit backoff across all scrapers
- [ ] **[AI] Entity Resolution Agent:** LangGraph agent to map ambiguous eBay titles to card_catalog records

## Data / Backend
- [x] **market_prices.ignored:** admin flag to hide bad prices from public catalog
- [x] **market_prices.graded_data JSONB:** PSA/BGS prices per card keyed by grade
- [x] **Performance indexes:** pg_trgm GIN on player_name/set_name, expression index on year cast, partial index on fair_value
- [x] **sealed_products + sealed_product_odds tables:** MSRP / pack config / odds per set/product type
- [x] **GET /catalog/sealed-products:** filterable API endpoint with nested odds
- [x] **Populate sealed_products:** trigger scrape_set_info GH Actions workflow for first data run (all sports, 2022+)
- [ ] **Lock ignore/delete to admin:** add admin dependency to PATCH /admin/market-prices/{id}/ignore
- [ ] **Refine price queries:** tighten sales window / outlier exclusion to reduce price spread noise
- [ ] **[AI] Outlier Quarantine:** auto-flag prices deviating >50% from player median
- [ ] **[AI] Vector Search:** embed 2.6M records for sub-second fuzzy card matching (needs pgvector)

## Admin Dashboard
- [x] **Pipeline Health tab:** catalog coverage by tier, last scrape per sport, GH Actions status cards
- [x] **Quarantine/Outliers tab:** outlier detection (>5× player median), ignore/restore toggle
- [x] **Users tab:** role management (admin/user/guest) inline
- [x] **Runs tab:** KPI strip, delta + hit-rate charts, date range filter, refresh, anomaly feed
- [x] **Quality tab:** stale/never-scraped/low-confidence KPIs, freshness by tier bar, priority stale + low-confidence card tables
- [x] **ETL Snapshot Audit:** show last 5 price snapshots per card (data already in market_price_history)
- [ ] **Sealed Products Manager:** view/edit MSRP and pack config per set inline in admin
- [ ] **Crowdsourced Price Gap Filler:** user-submitted prices for cards with no eBay data → admin review queue

## New Releases Page
- [x] **Set grid:** sport filter tabs, season range, card count / top value / avg / sales / % priced per set
- [x] **Top 5 cards per set:** deduplicated by player, RC badge guarded by variant keyword
- [x] **Sort logic:** year desc → populated first → flagship count → total sales → top value
- [x] **Flagship badge:** shown when set has staple/premium cards
- [x] **Momentum %:** avg price vs prev_value delta
- [x] **MSRP + Box Price display:** show Hobby/Blaster MSRP on each set card (data now in sealed_products)
- [x] **EV vs MSRP:** compare top-N card values against hobby box MSRP to show expected value
- [x] **Hero Top Card:** highlight the single highest-value card across all current releases
- [x] **Volatility indicators:** 7/14-day price delta from market_price_history (delta_7d_pct on set cards)
- [x] **Individual sales drill-down:** last 5 price snapshots (date/fair value/range/sales) in CatalogCardDetail panel
- [ ] **Rarity funnel:** visual print run breakdown (base → parallels → autos → 1/1s)

## Catalog Page
- [x] **Public browse:** no login required, paginated, sport/year/set/search/rookie/price filters
- [x] **CatalogCardDetail panel:** slide-in with price summary, sparkline, add-to-collection
- [x] **Tier badges:** Staple / Premium / Stars + RC badge
- [ ] **Card image in rows:** image_url already in API response — show thumbnail in catalog table
- [ ] **Price history graph:** sparkline or line chart embedded in catalog row / detail panel
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
- [ ] **Caching layer:** Redis/Memcached for expensive aggregate queries (portfolio total, releases page)
- [ ] **API rate limiting:** protect public endpoints from abuse
