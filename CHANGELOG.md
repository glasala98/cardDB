# CardDB Changelog

All notable changes to this project are documented here.
Format: `### [date] — description`

---

## 2026-03-23

### Progress email fixed — hardcoded catalog targets, pg_class-only queries
- Removed all slow `COUNT(*)` queries from the hourly progress email
- Catalog targets hardcoded (NFL 479,793 / NBA 298,550 / MLB 765,186) — stable between set releases
- All DB queries now use `pg_class`/`pg_stats` estimates (instant, no table scans)
- Restored 5-minute timeout on notify job

### Railway deploy unblocked — migration backfill moved to GH Actions
- `migrate_add_market_prices_sport.py` was running a massive `UPDATE market_prices SET sport=...` on every deploy, blocking Railway for hours
- Removed the UPDATE from the migration (now only adds columns + index)
- Created `backfill_market_prices_sport.yml` workflow — runs the backfill in 10K-row batches manually

### Boilerplate titles cleaned
- `migrate_clean_boilerplate_titles.py` deletes rows where title contains "opens in a new window"
- Fixes `test_no_ebay_boilerplate` DB quality test (was failing with 3 rows)

### market_prices denormalization — sport/scrape_tier/year columns added
- `migrations/migrate_add_market_prices_sport.py` adds sport/scrape_tier/year to market_prices
- Once backfill completes, all progress queries can run directly on market_prices (no JOIN)
- Index `idx_mp_sport_tier_year` created for fast filtering

---

## 2026-03-22

### Project reorganized into subdirectories
- `scraping/` — 14 scraper files (scrape_*.py, daily_scrape.py, auction_match.py, auction_title_parser.py)
- `migrations/` — 16 migrate_*.py files
- `diagnostics/` — 7 debug/quality scripts
- `scripts/` — 9 maintenance utilities
- sys.path injection added to all moved scrapers
- Dockerfile CMD updated for new migration paths
- 20+ workflow files updated for new script paths

### Progress email redesigned — timeline + pace tracking
- Added milestone schedule table (25/50/75/90/100%)
- Pace indicator (ahead/behind vs 135K/day target)
- ETA projected from actual daily rate
- Smart send: only fires at noon UTC or on milestone crossing (not every hour)

### Base tier scraper fixed — --max-hours 5.75 added
- `catalog_tier_base.yml` was missing `--max-hours 5.75`
- All 12 matrix shards were hitting GitHub's 6h hard kill and being cancelled
- Fixed: scraper now exits cleanly before the 6h limit

### Dead files removed
- `nixpacks.toml` — Railway uses Dockerfile, nixpacks was dead
- `RAW_SALES_BACKFILL_PLAN.md` — all steps completed
- `load_admin_cards.py`, 4 one-time migration scripts, 4 matching workflow files
- `batch_price_output.csv`, `batch_price_report.xlsx` — stale outputs, added to .gitignore

### 4 broken workflow paths fixed
- `scrape_set_info.yml`, `fix_sealed_sport.yml`, `migrate_graded_data.yml`, `catalog_quality_report.yml`
- All were referencing root-level script paths before the reorganization

### Test imports fixed
- `test_auction_match.py`, `test_auction_title_parser.py` → updated path to `scraping/`
- `test_export_ml.py` → updated path to `scripts/`

### Grading Advisor AI feature launched
- `api/routers/ai.py` — `POST /api/ai/grading-advice` using Claude Sonnet
- Button added to CardInspect page with purple response panel
- `frontend/src/api/ai.js` axios wrapper

---

## 2026-03-21 and earlier

### Raw sales backfill completed
- 1.7M+ sales rows across 76K+ cards in `market_raw_sales`
- `backfill_all_tiers.yml` running daily

### Base tier backfill started (2026-03-22)
- 12-shard matrix: NFL×5, NBA×4, MLB×3
- Target: ~135K cards/day, ETA ~Apr 30, 2026

### Project plan documented
- Full 7-phase roadmap in `memory/project_plan.md`
- Multi-source pricing roadmap (PWCC, Goldin, Heritage, Whatnot, COMC, StockX)
