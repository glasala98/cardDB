# CardDB — Project Architecture

> **Status:** Production on Railway (Pro plan). PostgreSQL + FastAPI + React. No file-based storage.
> **Live at:** southwestsportscards.ca
> **As of:** 2026-03

---

## What It Is

CardDB is a sports card market tracker and personal collection manager for NHL, NBA, NFL, and MLB cards. It scrapes eBay sold prices for 1.26M+ cards in a central catalog, lets users manage their personal collection, and calculates grading ROI (PSA/BGS).

---

## High-Level Stack

```
┌──────────────────────────────────────────────────────────────┐
│                        BROWSER                               │
│   React 18 + Vite  (southwestsportscards.ca)                 │
│                                                              │
│  Pages: /catalog  /collection  /ledger  /portfolio           │
│         /charts   /settings    /archive  /master-db          │
│                                                              │
│  Contexts: Auth · Currency · Preferences · PublicMode        │
│  API:      src/api/*.js  (axios, Bearer JWT, auto-unwrap)    │
└────────────────────────┬─────────────────────────────────────┘
                         │ HTTPS/JSON  (Authorization: Bearer JWT)
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                  FASTAPI  (Railway — port $PORT)             │
│                  api/main.py                                 │
│                                                              │
│  Routers:                                                    │
│  /api/auth        login · /me · logout · JWT 7-day           │
│  /api/cards       Ledger CRUD · scrape trigger · bulk import │
│  /api/catalog     1.26M card browse · paginated · filters     │
│  /api/collection  User ownership layer (FK → card_catalog)   │
│  /api/master-db   Young Guns analytics · grading ROI lookup  │
│  /api/stats       Market alerts · workflow status · trigger  │
│  /api/scan        Claude Vision card identification          │
│  /api/admin       User CRUD (admin role required)            │
│  /api/health      DB ping · "ok" or "degraded"               │
│                                                              │
│  Static: React dist/ served via SPA catch-all fallback       │
└────────────┬─────────────────────────────────────────────────┘
             │ psycopg2 ThreadedConnectionPool (1–10)
             ▼
┌──────────────────────────────────────────────────────────────┐
│             RAILWAY PostgreSQL  (Pro — 10GB)                 │
│                                                              │
│  ── Card Reference ───────────────────────────────────────── │
│  card_catalog        1.26M cards (TCDB / CLI / CBC)           │
│  market_prices       Current price + graded_data JSONB       │
│  market_price_history  Delta-only SCD Type 2 price history   │
│                                                              │
│  ── Personal Collection ──────────────────────────────────── │
│  collection          user_id · card_catalog_id FK · grade    │
│  cards               Ledger: user_id + card_name (text key)  │
│  card_results        Raw eBay sales + image URLs             │
│  card_price_history  Per-card fair-value snapshots           │
│  portfolio_history   Daily portfolio totals                  │
│                                                              │
│  ── Auth ─────────────────────────────────────────────────── │
│  users               username · bcrypt hash · role           │
│                                                              │
│  ── Analytics (legacy) ───────────────────────────────────── │
│  rookie_cards / rookie_price_history / player_stats          │
│  standings / rookie_correlation_history                      │
└──────────────────────────────────────────────────────────────┘
             ↑ writes
┌──────────────────────────────────────────────────────────────┐
│           GITHUB ACTIONS  (Scraping — cloud only)            │
│                                                              │
│  scrape_card_prices.py    eBay Selenium engine (shared lib)  │
│  scrape_master_db.py      Bulk catalog scraper               │
│  scrape_beckett_catalog.py  Populate card_catalog            │
│  daily_scrape.py          Scrape ledger cards → cards table  │
│                                                              │
│  Workflows (7):                                              │
│  catalog_tier_staple.yml    Daily — staple-tier raw prices   │
│  catalog_tier_premium.yml   Weekly — premium-tier prices     │
│  catalog_tier_stars.yml     Weekly — stars-tier prices       │
│  catalog_tier_graded.yml    Sunday — PSA/BGS graded prices   │
│  master_db_daily.yml        Daily — 4-sport 2K card sweep    │
│  master_db_weekly.yml       Sunday — full rookie sweep       │
│  daily_scrape.yml           Ledger card scrape (on demand)   │
└──────────────────────────────────────────────────────────────┘
```

---

## Repository Layout

```
cardDB/
├── api/                        # FastAPI application
│   ├── main.py                 # App factory, CORS, health, SPA
│   └── routers/                # One file per feature domain
│       ├── auth.py             # Login / session / JWT
│       ├── cards.py            # Card ledger CRUD + scrape trigger
│       ├── catalog.py          # 1.26M card catalog browse
│       ├── collection.py       # User collection (FK to catalog)
│       ├── master_db.py        # Young Guns DB + grading ROI
│       ├── stats.py            # Workflow status + scrape trigger
│       ├── scan.py             # Claude Vision card identification
│       └── admin.py            # User management (admin only)
│
├── frontend/                   # React 18 + Vite
│   └── src/
│       ├── App.jsx             # Router + context providers
│       ├── pages/              # One file per route
│       ├── components/         # Shared UI components
│       ├── context/            # Auth, Currency, Preferences, PublicMode
│       └── api/                # Axios wrappers per domain
│
├── scrape_card_prices.py       # Core eBay scraping engine
├── scrape_master_db.py         # Bulk catalog scraper
├── scrape_beckett_catalog.py   # card_catalog populator
├── daily_scrape.py             # Ledger card scraper
├── dashboard_utils.py          # Shared Python utilities
├── db.py                       # psycopg2 connection pool
├── migrate_add_graded_data.py  # Idempotent DB migration (runs on deploy)
│
├── .github/workflows/          # 7 scrape workflows + CI
├── Dockerfile                  # Railway: python:3.11-slim + Node 20
└── docs/                       # Component documentation
```

---

## Key Data Flows

### 1. Scraping Pipeline
```
GitHub Actions trigger (schedule or workflow_dispatch)
  → scrape_master_db.py reads card_catalog
  → For each card: scrape_card_prices.process_card()
      → Headless Chrome → eBay sold listings
      → _apply_variant_filter() — strips wrong parallels
      → calculate_fair_price() → fair_value
  → UPSERT market_prices (fair_value, trend, confidence)
  → INSERT market_price_history only when price changed (SCD Type 2)
  → Graded mode: accumulate graded_data JSONB → flush to market_prices
```

### 2. User Request
```
Browser → FastAPI → psycopg2 pool → PostgreSQL → JSON → React renders
```

### 3. Authentication
```
POST /api/auth/login → bcrypt verify → JWT (HS256, 7-day)
  → stored in localStorage
  → axios interceptor: Authorization: Bearer <token>
  → get_current_user() dependency validates on protected routes
```

### 4. Card Catalog Browse
```
GET /api/catalog?sport=NHL&year=2024-25&page=1
  → SELECT FROM card_catalog cc
    LEFT JOIN market_prices mp ON mp.card_catalog_id = cc.id
    WHERE cc.sport='NHL' AND cc.year='2024-25'
    ORDER BY year DESC LIMIT 50 OFFSET 0
  Total count: pg_class estimate (avoids full-scan on 1.26M rows)
```

### 5. Collection Management
```
POST /api/collection {card_catalog_id, grade, cost_basis}
  → INSERT INTO collection ON CONFLICT (user_id, card_catalog_id, grade)
    DO UPDATE SET quantity = quantity + 1

GET /api/collection/owned-ids
  → Set of card_catalog_ids (used for ✓ badges on Catalog page)
```

### 6. Grading ROI Lookup
```
GET /api/master-db/grading-lookup?player=Bedard
  Priority 1: young_guns.csv master DB (CSV-backed)
  Priority 2: market_prices.graded_data JSONB (new — catalog-linked)
  Priority 3: rookie_price_history.graded_data (legacy fallback)
  → CardInspect renders ROI table: Raw / PSA 9 / PSA 10 / BGS 9.5 / BGS 10
```

---

## Deployment

| Setting | Value |
|---|---|
| Platform | Railway Pro plan |
| Builder | Dockerfile (python:3.11-slim + Node 20) |
| Build | `pip install -r requirements.txt` → `npm run build` |
| On deploy | `python migrate_add_graded_data.py` (idempotent) |
| Start | `uvicorn api.main:app --host 0.0.0.0 --port $PORT` |
| Auto-deploy | Push/merge to `main` → Railway rebuilds |
| Custom domain | southwestsportscards.ca |

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| Single Railway service | FastAPI serves both API and React dist — one deploy |
| Dockerfile over Nixpacks | Explicit control over Python + Node versions |
| psycopg2 ThreadedConnectionPool | Sync FastAPI workers; pool avoids per-request reconnects |
| All card endpoints use query params | Card names contain `[`, `]`, `#`, `/` — breaks URL path routing |
| GitHub Actions for scraping | Chrome/Selenium needs real compute; GH Actions runners are free |
| CSS Modules | Scoped styles per component, no collisions |
| SCD Type 2 price history | Only write history rows when fair_value actually changes |
| graded_data JSONB in market_prices | Single FK-linked source for PSA/BGS — no fragmentation |
| PyJWT not python-jose | `import jwt` / `jwt.PyJWTError` — jose caused import issues on Railway |

---

## Auth & Roles

| Role | Access |
|---|---|
| `admin` | All pages + user management + scrape health panel |
| `user` | All personal pages (ledger, collection, portfolio) |
| `guest` | Read-only access, no writes |
| Public (`?public=true`) | Catalog browse only, no login required |

---

## card_catalog Coverage (as of 2026-03)

| Sport | Cards | Sources | Era |
|---|---|---|---|
| NHL | ~310K | TCDB + CLI | 1951–2026 |
| NBA | ~278K | TCDB | 1967–2026 |
| NFL | ~643K | TCDB + CBC | 1948–2026 |
| MLB | ~1.4M | TCDB + CBC + CLI | 1907–2026 |
| **Total** | **~1.26M** | | |

---

## Component Documents

| Document | What it covers |
|---|---|
| [concepts.md](concepts.md) | Key vocabulary and mental models (card format, tiers, confidence, etc.) |
| [backend.md](backend.md) | FastAPI routers — endpoints, inputs, outputs, auth |
| [database.md](database.md) | PostgreSQL tables, schema, query patterns |
| [frontend.md](frontend.md) | React pages, components, contexts, API layer |
| [scrapers.md](scrapers.md) | eBay scraping engine, variant filter, bulk scraper |
| [scrape_engine.md](scrape_engine.md) | Deep function-level reference for the scraping pipeline |
| [workflows.md](workflows.md) | GitHub Actions schedules, triggers, env vars |
| [dashboard_utils.md](dashboard_utils.md) | Shared Python utility layer |
