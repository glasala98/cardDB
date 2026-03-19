# CardDB — Sports Card Market Tracker

A full-stack platform for tracking sports card collections, monitoring eBay market prices, and building long-term historical price data across NHL, NBA, NFL, and MLB.

**Live:** [southwestsportscards.ca](https://southwestsportscards.ca)

---

## Overview

CardDB is built around two goals:

1. **Your collection** — track cards you own, cost basis, current market value, and P&L over time.
2. **The market** — a catalog of 1.26M+ cards with daily eBay price scraping, graded card values (PSA/BGS), sealed product MSRP/box prices, and append-only price history for long-term trend analysis.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + Vite, Recharts, CSS Modules |
| Backend | FastAPI (Python 3.11), psycopg2 ThreadedConnectionPool 1-10 |
| Database | PostgreSQL (Railway Pro, 80GB volume) |
| Scraping | Selenium + headless Chrome, curl_cffi |
| AI | Anthropic Claude (card photo scanning) |
| Hosting | Railway Pro plan (~8GB RAM), Dockerfile, auto-deploy from `main` |
| CI | GitHub Actions (all scraping — no local compute) |

---

## Pages / Routes

| Route | Description |
|-------|-------------|
| `/catalog` | Public card catalog — 1.26M+ cards, sport/year/set filters, tier badges, price sparklines, slide-in detail panel. No login required. |
| `/collection` | My Collection — cards you own, P&L, add/remove |
| `/ledger` | Personal ledger (text-keyed cards) — search, filter, cost basis edit, bulk import, AI scan, export CSV |
| `/ledger/:name` | Card detail — price history chart, raw eBay sales, grading ROI calculator, card image lightbox |
| `/archive` | Archived ledger cards — view and restore |
| `/portfolio` | Portfolio overview — total value, P&L, trend breakdown, top cards, gainers/losers |
| `/charts` | Portfolio charts — value distribution, trend breakdown, grade mix, set analysis |
| `/admin` | Admin dashboard — scrape monitoring, user management, outlier review, sealed products, pipeline health |
| `/settings` | User settings |

Default route: `/` → `/catalog`

---

## Architecture (brief)

```
cardDB/
├── api/                         # FastAPI backend
│   ├── main.py                  # App entry, router mounts, React static file serving
│   └── routers/
│       ├── auth.py              # JWT login/logout (PostgreSQL users table)
│       ├── cards.py             # Card CRUD, scrape, archive, bulk import, AI scan
│       ├── catalog.py           # card_catalog browse + filters + price history
│       ├── collection.py        # User collection CRUD, owned-ids, grades
│       ├── master_db.py         # Grading lookup: CSV → graded_data → rookie_price_history
│       ├── stats.py             # Portfolio history, GH Actions trigger, scrape status
│       ├── admin.py             # User mgmt, scrape monitoring, outlier review
│       └── scan.py              # Claude Vision card image analysis
├── frontend/                    # Vite + React SPA
│   └── src/
│       ├── pages/               # Catalog, Ledger, Portfolio, Admin, Settings, ...
│       ├── components/          # Navbar, CatalogCardDetail, PageTabs, shared UI
│       ├── context/             # AuthContext, CurrencyContext
│       └── api/                 # Axios wrappers per router
├── db.py                        # psycopg2 connection pool, get_db() context manager
├── dashboard_utils.py           # Shared Python utilities (price parsing, alerts)
├── scrape_card_prices.py        # Core eBay scraping engine (Selenium)
├── scrape_master_db.py          # Mass catalog scraper: card_catalog → market_prices
├── scrape_beckett_catalog.py    # Catalog builder (TCDB / CLI / CBC sources)
├── scrape_set_info.py           # Sealed product scraper (cardboardconnection.com)
├── daily_scrape.py              # Scrapes all cards in a user's personal ledger
├── assign_catalog_tiers.py      # Labels card_catalog rows as staple/premium/stars
├── preflight_db_check.py        # DB disk usage preflight gate (absolute GB thresholds)
├── quarantine_outliers.py       # Flags statistical price outliers in market_prices
├── catalog_gap_analysis.py      # Audits catalog coverage by sport/year
├── migrate_add_*.py             # Idempotent DB migrations (run on every Railway deploy)
├── .github/workflows/           # GitHub Actions automations (all scraping runs here)
└── Dockerfile                   # Production build (python:3.11-slim + Node 20)
```

See `docs/architecture.md` for the full system diagram and data flow details.

---

## Database Schema

| Table | Description |
|-------|-------------|
| `card_catalog` | 1.26M+ card definitions (sport, year, set, player, variant, is_rookie, scrape_tier) |
| `market_prices` | Current fair value per catalog card (upserted by scraper); `graded_data JSONB` for PSA/BGS |
| `market_price_history` | Append-only price history (SCD Type 2 — only inserts on value change) |
| `market_raw_sales` | Every individual eBay sold listing, permanent storage (880K+ rows, growing) |
| `market_prices_status` | View: is_stale / is_fresh / days_since_scraped per card |
| `collection` | User → catalog card ownership (grade, quantity, cost_basis, purchase_date) |
| `users` | Authentication (username, bcrypt hash, role: admin/user/guest) |
| `scrape_runs` | One row per scraper invocation — status, cards_total, cards_processed, cards_found, errors |
| `scrape_run_errors` | Per-card error log per run |
| `sealed_products` | Box/pack products with MSRP, box price, pack config (scraped monthly) |
| `sealed_product_odds` | Pack odds per product |
| `cards` | Legacy personal ledger (text-keyed, pre-catalog) |
| `card_results` | Raw eBay sales per ledger card |
| `card_price_history` | Daily price snapshots per ledger card |
| `portfolio_history` | Daily portfolio total value per user |
| `rookie_cards` | Young Guns / Rookie market DB with PSA/BGS price columns |
| `rookie_price_history` | Price snapshots per rookie with `graded_data JSONB` |
| `player_stats` | NHL/NBA/NFL/MLB stats as JSONB |
| `standings` | Team standings per sport |

Schema defined in `schema.sql`. All migrations are idempotent (`IF NOT EXISTS`) and run automatically on every Railway deploy before uvicorn starts.

**Database volume:** 80GB (resized 2026-03-18). Current usage: ~5GB data, ~11GB filesystem (WAL + overhead).

---

## Card Catalog

1.26M+ cards built from multiple checklist sources:

| Source | Sports | Coverage |
|--------|--------|---------|
| TCDB (tradingcarddatabase.com) | All | NHL 1951–2026, NBA/NFL/MLB through ~1997 |
| CBC (cardboardconnection.com) | MLB, NFL | 2008–2026 |
| CLI (checklistinsider.com) | NHL, MLB | 2022–2026 |

**Current totals:** NHL ~310K · NBA ~278K · NFL ~316K · MLB ~358K = **~1,262,503 cards**

### Scrape Tiers (`card_catalog.scrape_tier`)

| Tier | Examples | Current schedule |
|------|----------|-----------------|
| `staple` | YG, Prizm RC, Chrome RC, SP Authentic | Daily 8am UTC |
| `premium` | Autos, patches, serials, relics | Daily 10am UTC (temporarily elevated for backfill) |
| `stars` | Major-brand rookies | Daily noon UTC (temporarily elevated for backfill) |
| `base` | Everything else 2010+ | Daily 6am UTC (backfill in progress — ~8.5% priced so far) |

Tiers assigned by `assign_catalog_tiers.py`.

---

## Price Scraping

eBay sold listings are scraped using headless Chrome via `scrape_card_prices.py` (core engine), called by:

- **`scrape_master_db.py`** — mass catalog scraper (raw mode + `--graded` mode for PSA/BGS)
- **`daily_scrape.py`** — personal ledger scraper

Results write to:
- `market_prices` — current fair value (upserted)
- `market_price_history` — append-only; only inserts when value changes (SCD Type 2)
- `market_raw_sales` — every individual eBay sold listing, permanent storage

The scraper enforces `--max-hours 5.75` self-limit so it exits gracefully before GitHub Actions' 6h kill timeout.

**DSM fix:** `scrape_master_db.py` runs `SET max_parallel_workers_per_gather = 0` before the `load_cards()` query to prevent PostgreSQL shared memory exhaustion on Railway.

---

## GitHub Actions

All scraping runs on GitHub Actions. No local compute — the local machine is for code editing and `git push` only.

| Workflow | Schedule | Description |
|----------|----------|-------------|
| `catalog_tier_staple.yml` | Daily 8am UTC | Raw prices for staple-tier cards, all 4 sports parallel, stale-days 1 |
| `catalog_tier_premium.yml` | Daily 10am UTC (temp elevated) | Raw prices for premium-tier cards, stale-days 7 |
| `catalog_tier_stars.yml` | Daily noon UTC (temp elevated) | Raw prices for stars-tier cards, stale-days 30 |
| `catalog_tier_base.yml` | Daily 6am UTC | Base prices 2010+, all 4 sports parallel, stale-days 30, max-hours 5.75 |
| `catalog_tier_graded.yml` | Sunday 6am UTC | PSA/BGS prices for staple cards with fair_value ≥ $5 |
| `master_db_daily.yml` | Daily 6am UTC (1am EST) | 4 sports × 1,000 cards, stale-days 7 |
| `master_db_weekly.yml` | Sunday 2am EST | Full rookie sweep, stale-days 30 |
| `daily_scrape.yml` | On demand (UI trigger) | Personal ledger cards |
| `scrape_set_info.yml` | 1st of month 6am UTC | Sealed product MSRP + pack config |
| `catalog_update.yml` | Manual | Populate card_catalog from TCDB/CLI/CBC |
| `catalog_quality_report.yml` | Monday 10am UTC | pytest + gap analysis → GitHub Step Summary |
| `backfill_raw_sales.yml` | Manual | Backfill market_raw_sales per tier |
| `backfill_all_tiers.yml` | Daily 1:21pm UTC | Sequential staple/premium/stars/base raw sales backfill |
| `db_health_check.yml` | Daily 5am UTC | DB disk usage check, top tables by size |
| `coverage_notify.yml` | Daily noon UTC | Email when price coverage crosses 10% milestone |
| `quarantine_outliers.yml` | Nightly | Flag statistical price outliers |
| `sales_quality_check.yml` | Periodic | Spot check raw sales data quality |
| `diag_*.yml` | Manual | Diagnostic and debug workflows |
| `migrate_*.yml` | Manual | One-time DB migrations |
| `scrape_fanatics/goldin/heritage/myslabs/pristine/pwcc.yml` | Manual | Auction house scrapers |
| `tests.yml` | On push | pytest unit tests |

**Required GitHub Secrets:**

| Secret | Description |
|--------|-------------|
| `DATABASE_URL` | Railway PostgreSQL connection string |
| `GH_PAT` | Classic PAT with `repo` + `workflow` scopes |
| `NOTIFY_EMAIL_TO` | Recipient email address |
| `NOTIFY_GMAIL_USER` | Gmail sender address |
| `NOTIFY_GMAIL_APP_PASSWORD` | Gmail App Password |

### Triggering via GitHub CLI

```bash
gh workflow run catalog_tier_staple.yml
gh workflow run catalog_tier_graded.yml -f sport=NHL -f min_raw_value=10.0
gh workflow run master_db_daily.yml
gh workflow run scrape_set_info.yml -f sport=NHL
```

---

## Admin Dashboard

The `/admin` page has six tabs:

| Tab | What it shows |
|-----|--------------|
| **Pipeline** | Coverage stats (priced 7d/30d), workflow health cards with consecutive-failure badges, overdue detection, Run trigger buttons |
| **Runs** | Live active jobs with progress bars, cards/hr rate, ETA; completed run history with hit rate, delta, anomaly flags |
| **Quality** | Snapshot audit, data quality checks, freshness by tier |
| **Sealed** | Sealed product admin: browse/edit rows, data quality (sport mismatches, bad MSRP), one-click fix |
| **Users** | User management (admin role only) |
| **Outliers** | Review statistical price outliers, bulk-ignore |

Active jobs update every 30s. `scrape_runs.cards_processed` and `cards_found` are written every 50 cards mid-run so progress bars and hit rates reflect live state.

---

## Local Development

**Prerequisites:** Python 3.11+, Node 20+, Google Chrome

```bash
git clone https://github.com/glasala98/cardDB
cd cardDB

# Python dependencies
pip install -r requirements.txt

# Frontend dependencies
cd frontend && npm install && cd ..

# Environment
cp .env.example .env
# Set: DATABASE_URL, JWT_SECRET, ANTHROPIC_API_KEY, GITHUB_TOKEN

# Run backend
cd api && uvicorn main:app --reload
# → http://localhost:8000/docs

# Run frontend (separate terminal)
cd frontend && npm run dev
# → http://localhost:5173  (proxies /api → :8000)
```

Default dev login: **admin / admin**

---

## Production Deployment

Hosted on Railway. Push to `main` to auto-deploy:

```bash
git push origin main
# Railway builds via Dockerfile → deploys automatically
```

The Dockerfile:
1. Builds the React frontend (`npm run build`)
2. Installs Python dependencies
3. Runs all idempotent migrations (`migrate_add_graded_data.py`, `migrate_add_cards_processed.py`)
4. Starts FastAPI which serves both `/api/*` and the React SPA from `frontend/dist/`

**Environment variables** (set in Railway dashboard):

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | Railway PostgreSQL internal URL |
| `JWT_SECRET` | Random 32-byte hex string |
| `ANTHROPIC_API_KEY` | Anthropic Claude API key |
| `GITHUB_TOKEN` | Classic PAT with `repo` + `workflow` scopes |

---

## Authentication

- JWT-based (`PyJWT`), 7-day expiry
- Users stored in PostgreSQL `users` table (bcrypt passwords)
- `guest` role available (read-only access)
- Admin role required for `/admin` routes and scrape monitoring

**Note:** Use `PyJWT` (not `python-jose`) — auth.py uses `import jwt` / `jwt.PyJWTError`.

---

## Features

- Bloomberg-style dark UI — teal accent (`#00d4aa`), tabular-nums, JetBrains Mono for numbers
- **AI card scanning** — photograph a card, Claude extracts player/year/set/grade
- **Bulk import** — paste a list of card names to add multiple at once
- **Grading ROI calculator** — compare raw vs PSA 9/10 / BGS 9.5 / BGS 10 values
- **Sealed products** — MSRP, box price, pack config per set, scraped monthly
- **Live scrape monitoring** — active job progress bars with cards/hr rate and ETA
- **Inline editing** — cost basis editable directly in the ledger table
- **Currency toggle** — CAD/USD with live exchange rate
- **Price history charts** — line chart per card, trajectory summary
- **Raw sales storage** — every individual eBay sold listing permanently stored in `market_raw_sales`

---

## Future Plans

See `docs/architecture.md` for the full roadmap. Key initiatives:

1. **Post-backfill delta mode** — Once all base-tier cards are priced (~4-6 weeks out), daily runs switch to pure delta. Estimated: 6-hour runs shrink to ~10 minutes.
2. **Vector search** — pgvector on Railway PostgreSQL for fuzzy card name matching and entity resolution.
3. **Price alerts** — Email/in-app notification when a tracked card moves >10% in 7 days.
4. **Caching layer** — Redis for expensive aggregate queries (portfolio total, releases page).
5. **Public sealed products page** — Browse sealed products by sport/year with MSRP and pack odds. Data already exists in `sealed_products` + `sealed_product_odds`.
