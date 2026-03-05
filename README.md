# CardDB — Sports Card Market Tracker

A full-stack platform for tracking sports card collections, monitoring eBay market prices, and building long-term historical price data across NHL, NBA, NFL, and MLB.

**Live:** [southwestsportscards.ca](https://southwestsportscards.ca)

---

## Overview

CardDB is built around two goals:

1. **Your collection** — track cards you own, cost basis, current market value, and price history over time.
2. **The market** — a catalog of 1.26M+ cards with daily eBay price scraping, graded card values (PSA/BGS), and append-only price history for long-term trend analysis.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + Vite, Recharts, CSS Modules |
| Backend | FastAPI (Python 3.11) |
| Database | PostgreSQL (Railway) |
| Scraping | Selenium + Chrome, requests, curl_cffi |
| AI | Anthropic Claude (card photo scanning) |
| Hosting | Railway (Dockerfile build, auto-deploy from `main`) |
| CI | GitHub Actions (daily + weekly price scrapes) |

---

## Architecture

```
cardDB/
├── api/                         # FastAPI backend
│   ├── main.py                  # App entry, router mounts, React static file serving
│   └── routers/
│       ├── auth.py              # JWT login/logout (users.yaml, dev fallback admin/admin)
│       ├── cards.py             # Card CRUD, scrape, archive, bulk import, AI scan
│       ├── master_db.py         # Catalog queries, YG price history, ownership tracking
│       ├── stats.py             # Portfolio history, GitHub Actions trigger, scrape status
│       ├── admin.py             # User management (admin role only)
│       └── scan.py              # Claude Vision card image analysis
├── frontend/                    # Vite + React SPA
│   └── src/
│       ├── pages/               # One component per route
│       ├── components/          # Navbar, HelpModal, shared components
│       ├── context/             # AuthContext, CurrencyContext, PublicModeContext
│       └── api/                 # Axios wrappers per router
├── db.py                        # psycopg2 connection pool, get_db() context manager
├── dashboard_utils.py           # Shared DB utilities (load_data, save_data, price history)
├── scrape_card_prices.py        # eBay scraper: search, parse sales, compute fair value
├── scrape_master_db.py          # Mass price scraper: reads card_catalog → market_prices
├── scrape_beckett_catalog.py    # Card catalog builder (CLI / CBC / TCDB sources)
├── scrape_nhl_stats.py          # NHL API scraper → player_stats, standings tables
├── daily_scrape.py              # Scrapes all cards in a user's collection
├── catalog_gap_analysis.py      # Audits card_catalog coverage by sport/year
├── .github/workflows/           # GitHub Actions automations
└── Dockerfile                   # Production build (python:3.11-slim + Node 20)
```

---

## Pages

| Route | Description |
|-------|-------------|
| `/ledger` | Collection table — search, filter by trend/grade/confidence/price, inline cost basis edit, bulk import, AI card scan, export CSV |
| `/ledger/:name` | Card detail — price history chart, raw eBay sales, grading ROI calculator, card image |
| `/portfolio` | Portfolio overview — total value, P&L, value chart, trend breakdown, top 10 cards, gainers/losers, Card of the Day |
| `/master-db` | Master DB — 1.26M card catalog with 9 analytics sections: market overview, value finder, rookie impact score, player compare, correlation analytics, team premium, nationality analysis, seasonal trends |
| `/charts` | Charts — value distribution, trend breakdown, grade mix, set analysis, cost vs value scatter |
| `/nhl-stats` | NHL player stats — sortable table with position/team filters and card value columns |
| `/archive` | Archived cards — view and restore |
| `/admin` | User management (admin role only) |

---

## Database Schema

| Table | Description |
|-------|-------------|
| `cards` | User collection (card_name, fair_value, cost_basis, purchase_date, tags, grade, confidence) |
| `card_results` | Raw eBay sales data per card (JSONB) |
| `card_price_history` | Daily price snapshots per user card |
| `portfolio_history` | Daily portfolio total value snapshots |
| `card_catalog` | 1.26M+ card definitions (sport, year, set, player, variant, is_rookie, is_parallel, search_query) |
| `market_prices` | Current fair value per catalog card (upserted by scraper daily) |
| `market_price_history` | Append-only daily price history for catalog cards |
| `player_stats` | NHL player stats (JSONB blob, updated daily) |
| `standings` | NHL standings (JSONB blob, updated daily) |
| `young_guns` | Young Guns checklist with ownership tracking |

Schema defined in `schema.sql`.

---

## Card Catalog

1.26M+ cards built from multiple checklist sources:

| Source | Sport | Coverage |
|--------|-------|---------|
| TCDB (tradingcarddatabase.com) | All | NHL 1951–2026, NBA/NFL/MLB through ~1997 |
| CBC (cardboardconnection.com) | MLB | 2015–2022 |
| CBC | NFL | 2008–2023 |
| CLI (checklistinsider.com) | NHL | 2022–2026 |
| CLI | MLB | 2023+ |

**Current totals:** NHL 310K · NBA 278K · NFL 316K · MLB 358K = **1,262,503 cards**

To build or extend the catalog:
```bash
# TCDB — all eras, uses curl_cffi to bypass Cloudflare
python scrape_beckett_catalog.py --source tcdb --sport NHL --year-from 1906
python scrape_beckett_catalog.py --source tcdb --sport NBA --year-from 1948
python scrape_beckett_catalog.py --source tcdb --sport NFL --year-from 1935
python scrape_beckett_catalog.py --source tcdb --sport MLB --year-from 1869

# CBC — modern cards for MLB and NFL
python scrape_beckett_catalog.py --source cbc --sport MLB --year-from 2015
python scrape_beckett_catalog.py --source cbc --sport NFL --year-from 2012

# CLI — most recent years
python scrape_beckett_catalog.py --source cli --sport NHL --year-from 2022
python scrape_beckett_catalog.py --source cli --sport MLB --year-from 2023
```

Resumable via `catalog_checkpoint.json` — skips completed sets on restart.

Run a coverage audit:
```bash
python catalog_gap_analysis.py --sport ALL
```

---

## Price Scraping

eBay sold listings are scraped using headless Chrome:

```bash
# Scrape current prices for the master catalog (run via GitHub Actions daily)
python scrape_master_db.py --sport NHL --workers 5 --limit 2000
python scrape_master_db.py --sport NHL --graded --workers 5    # PSA/BGS grades
python scrape_master_db.py --sport NHL --rookies --workers 5   # rookie priority

# Scrape a user's personal collection
python daily_scrape.py --workers 3
```

Results write to `market_prices` (current price) and `market_price_history` (append-only daily record — the core of long-term historical data).

---

## GitHub Actions

| Workflow | Schedule | Description |
|----------|---------|-------------|
| `master_db_daily.yml` | 6am UTC daily | Scrape NHL/NBA/NFL/MLB prices (4 parallel jobs, 2000 cards each) |
| `master_db_weekly.yml` | 7am UTC Sunday | Graded prices (PSA/BGS), rookie refresh, NHL bios |
| `daily_scrape.yml` | 8am UTC daily | Rescrape each user's personal collection |

All workflows connect directly to Railway PostgreSQL via `DATABASE_URL` secret.

Required GitHub secrets:
- `DATABASE_URL` — Railway PostgreSQL connection string
- `JWT_SECRET` — JWT signing key
- `ANTHROPIC_API_KEY` — Claude API key

---

## Local Development

**Prerequisites:** Python 3.11+, Node 20+, PostgreSQL, Google Chrome

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

Default dev login: **admin / admin** (no `users.yaml` needed in dev mode)

---

## Production Deployment

Hosted on Railway. Push to `main` to deploy:

```bash
git checkout main && git merge dev && git push origin main
# Railway builds via Dockerfile and deploys automatically
```

The Dockerfile:
1. Builds the React frontend (`npm run build`)
2. Installs Python dependencies
3. Starts FastAPI which serves both `/api/*` and the React SPA from `frontend/dist/`

**Environment variables** set in Railway dashboard:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | Railway PostgreSQL internal URL |
| `JWT_SECRET` | Random 32-byte hex string (`openssl rand -hex 32`) |
| `ANTHROPIC_API_KEY` | Anthropic Claude API key |
| `GITHUB_TOKEN` | PAT with repo + workflow scopes (for Rescrape All button) |

---

## Authentication

- JWT-based (`PyJWT`)
- Users defined in `users.yaml` (bcrypt-hashed passwords)
- Dev fallback: `admin` / `admin` when `users.yaml` is absent
- **Public read-only mode:** append `?public=true` to any URL to share without login (hides write actions)

`users.yaml` format:
```yaml
users:
  admin:
    display_name: Admin
    role: admin
    password_hash: "$2b$12$..."
```

Generate a hash:
```python
import bcrypt
print(bcrypt.hashpw(b"yourpassword", bcrypt.gensalt()).decode())
```

---

## Features

- Bloomberg-style dark UI — teal accent (`#00d4aa`), tabular-nums, JetBrains Mono for numbers
- **AI card scanning** — photograph a card, Claude extracts player/year/set/grade
- **Bulk import** — paste a list of card names to add multiple at once
- **Inline editing** — cost basis editable directly in the ledger table
- **Grading ROI calculator** — compare raw vs PSA 9/10 / BGS 9.5 values
- **Card of the Day** — highlighted pick from your portfolio each day
- **Shareable links** — one-click copy of a read-only public URL
- **Scrape progress modal** — live GitHub Actions status after triggering a rescrape
- **Currency toggle** — CAD/USD with live exchange rate
- **Price history charts** — line chart + scatter plot per card, trajectory summary
- **9 analytics sections** in Master DB — value finder, rookie impact score, correlation analytics, team premium, seasonal trends, and more
