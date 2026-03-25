# CardDB Changelog

All notable changes to this project are documented here.
Format: `### [date] — description`

---

## 2026-03-24

### Write optimization — reduce Railway DB churn
- `market_prices` ON CONFLICT now skips UPDATE when fair_value/num_sales/confidence unchanged — eliminates WAL churn for stable prices (critical post-backfill)
- `market_price_history` correlated subquery replaced with LATERAL JOIN — single index sweep instead of N per-card subqueries for batches of 1000+ cards
- `save_prices_batch` now pre-fetches existing `listing_hash` values in one query before bulk insert — eliminates dead tuples from ON CONFLICT DO NOTHING on duplicates

### DB Backup — delta exports after every scrape run
- `migrate_add_raw_sales_created_at.py` — adds `created_at TIMESTAMPTZ DEFAULT NOW()` + index to `market_raw_sales` for delta filtering
- `db_backup_delta.yml` — triggers via `workflow_run` after any scraper workflow completes; exports last 25h of `market_raw_sales` + `market_price_history` as gzipped CSV artifacts (30-day retention)
- Dockerfile updated to run migration on deploy

### DB Backup — weekly pg_dump to GitHub Actions artifact
- `db_backup.yml` runs every Sunday at 2am UTC (after graded scraper finishes)
- `pg_dump --format=custom --compress=9` — compact binary, restore with `pg_restore`
- Artifact retained 90 days — download from Actions tab → DB Backup → Artifacts
- Manual trigger available via `workflow_dispatch` for on-demand backups

### NHL Stats — now live on player_stats DB + card_catalog prices (DB-first)
- `nhl_stats` endpoint rewritten: pulls player stats from `player_stats` table (sport='NHL'), joins best rookie card price per player from `card_catalog + market_prices`
- `catalog_id` included in response — NHLStats page can now deep-link to card sales (Phase 1 TODO)
- CSV fallback retained; response shape unchanged, no frontend changes needed
- Phase 1 DB migration: both Young Guns and NHL Stats now off CSV for primary data

### Graded scraper widened — premium + stars tiers now included
- `catalog_tier_graded.yml` now runs 3 jobs each Sunday: staple (9am), premium (11am), stars (1pm UTC)
- Staggered to avoid overlap with base scraper at 6am UTC
- min_raw_value thresholds: staple $5, premium $3, stars $8 (only high-value stars cards worth grading)
- PSA/BGS graded prices will now populate for all NHL/NBA/NFL/MLB rookie tiers
- Connection budget: 4 sports × 3 workers = 12 connections per tier — well within 80 limit

### Young Guns — now live on card_catalog + market_prices (DB-first)
- `list_young_guns` endpoint rewritten to query `card_catalog JOIN market_prices WHERE is_rookie=TRUE AND sport='NHL' AND scrape_tier IN ('staple','premium','stars')`
- Response shape is identical — frontend (MasterDB.jsx) requires zero changes
- CSV (`load_master_db`) is now a fallback only; once DB has full NHL rookie coverage the CSV path will be removed
- Graded prices (PSA 8/9/10, BGS 9/9.5/10) pulled from `market_prices.graded_data` JSONB
- Ownership (`owned`, `cost_basis`) not available from DB source — tracked in `collection` table per user; will be wired in Phase 2
- Added `source` field to response (`"db"` or `"csv"`) for debugging
- Phase 1 of DB architecture migration documented in TODO.md

### Card Sales page — listing thumbnail + shipping cost added
- Each sale row now shows the eBay listing photo (44×60px thumbnail) as the first column
- Shipping cost displayed below the sale price: `+$X.XX ship` (muted) or `Free ship` (green)
- `shipping_val` added to `/catalog/{id}/raw-sales` API SELECT (was already in DB, just not returned)
- Mobile: thumbnail column preserved; grade + serial hidden to keep table readable at small widths
- Free shipping highlighted in green; paid shipping shown in muted text below the price

---

## 2026-03-24

### Trending page fixed — minimum price floor eliminates garbage % spikes
- Added `>= $2.00` minimum price threshold to HAVING clause on both current and previous 7d windows
- Cards going from $0.01 to $6 no longer show as +187,000% movers
- % now shows negative values in red (was always hardcoded green)
- `fmtDelta()` helper handles both positive and negative formatting

### Catalog: featured sort + 25-per-page for faster, better first impressions
- Default sort changed from `year DESC` to `featured` — surfaces most desirable
  cards: staple tier → has price → num_sales DESC → fair_value DESC → rookie → name
- PER_PAGE reduced 50→25: half the DB rows fetched, faster initial load, less scroll
- `✦` button in table header last column to toggle featured sort on/off
- Sales column header is now clickable to sort by num_sales
- `FEATURED_ORDER` SQL constant in catalog.py; search+featured combo: FTS rank first,
  then featured order as tiebreaker

### All filter dropdowns now cascade — no phantom options anywhere
- **CardLedger**: set dropdown scoped to selected year; grade dropdown scoped
  to selected year + set; changing year auto-clears set + grade; changing
  set auto-clears grade (all local client-side, no API calls needed)
- **SetBrowser**: year dropdown now scoped to search term — searching "Upper Deck"
  only shows years with Upper Deck sets; year resets when search changes

### Catalog filters scoped to active search — no phantom years/sets
- `/catalog/filters` API now accepts `search` param; scopes years and sets
  to rows matching that player/set name (ILIKE), so "Connor McDavid" only
  shows years he actually has cards in
- Years reload when search term changes (≥2 chars), not just on sport change
- Sets reload scoped to current search + year combo
- Year dropdown stays enabled when a search is active (not just when sport selected)
- Search-scoped filter results bypass the TTL cache (too many combos)

### Global design system polish — enterprise feel across all pages
- Define missing `--bg-hover: #192030` CSS variable (was referenced but undefined)
- Global table: bolder header labels (10.5px/700/0.7px tracking), tighter column header, +2px row padding for breathing room, use `--bg-hover` on row hover
- `Page.module.css` header: 22px→24px/800 title, letter-spacing −0.5px, bottom border separator, new `.subtitle` class
- `Navbar`: section labels "Discover" and "My Portfolio" appear above nav groups in desktop sidebar; hidden in mobile tab bar
- App main area: padding 24→28px top, 32→36px sides, max-width clamp so content doesn't over-stretch on ultrawide

### Catalog Browse — sport tabs, active filter chips, Priced toggle
- Sport quick-tabs now visible in main area above AI search (All/NHL/NBA/NFL/MLB)
- Active filter chips appear below sport tabs showing what's filtered, each removable with ×
- "Priced" quick toggle to show only cards with a market price (useful during backfill)
- Year dropdown disables + shows "Select sport first" hint when no sport selected
- Count badge says "X results" when filters active vs "X cards" when unfiltered

### Scan Card page — proper full-page layout (no more modal wrapper)
- `ScanPage.jsx` now renders `ScanCardModal` in `pageMode` — no overlay, no backdrop
- Added `pageContainer`, `pageCard`, `pageHeader` CSS for clean page layout
- `ScanCardModal` accepts `pageMode` prop; shares all logic/state between modal and page modes

---

## 2026-03-23

### Scrape validation workflow added
- `validate_scrape_run.yml` fires automatically after every base tier run
- Checks new prices written in last 7h by sport (NFL/NBA/MLB)
- Fails + emails alert if any sport wrote 0 or <1K prices
- Also runnable manually with configurable window

### Scraping throughput doubled — 24 shards, 4 runs/day, 8 workers
- NFL: 5→10 shards, NBA: 4→8, MLB: 3→6 = 24 parallel runners (was 12)
- Added midnight UTC run — now 4 runs/day (was 3)
- Increased `--workers` 5→8 per runner
- Combined effect: ~270K cards/day (was ~135K), ETA ~Apr 15 (was ~Apr 30)

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
