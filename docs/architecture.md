# CardDB — System Architecture

> **Status:** Production on Railway (Pro plan). PostgreSQL + FastAPI + React.
> **Live at:** southwestsportscards.ca
> **As of:** 2026-03

---

## What It Is

CardDB is a free sports card market intelligence platform. The data is the product.

800K+ cards with daily-updated eBay sold prices, graded values (PSA/BGS), and price history accumulating over time — across NHL, NBA, NFL, and MLB. Free, when everything comparable costs money.

Three monetization layers:
1. **Price checker + public catalog** — drives traffic, ad impressions
2. **Portfolio tracker** — creates returning users
3. **Public API** *(roadmap)* — developers, resellers, hobbyists

The moat is time: anyone can build a scraper, but the price history dataset only grows from the day you start collecting it.

---

## System Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                        BROWSER                               │
│   React 18 + Vite  (southwestsportscards.ca)                 │
│                                                              │
│  Pages: /catalog  /my-cards  /my-cards/collection  /scan     │
│         /young-guns  /portfolio  /charts  /settings  /admin  │
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
│  /api/catalog     1.26M card browse · paginated · filters    │
│  /api/collection  User ownership layer (FK → card_catalog)   │
│  /api/master-db   Young Guns analytics · grading ROI lookup  │
│  /api/stats       Market alerts · workflow status · trigger  │
│  /api/scan        Claude Vision card identification          │
│  /api/ai          Grading advisor · market digest · deal finder│
│  /api/admin       User CRUD · scrape monitoring (admin only) │
│  /api/health      DB ping · "ok" or "degraded"               │
│                                                              │
│  Static: React dist/ served via SPA catch-all fallback       │
└────────────┬─────────────────────────────────────────────────┘
             │ psycopg2 ThreadedConnectionPool (1–10)
             ▼
┌──────────────────────────────────────────────────────────────┐
│         RAILWAY PostgreSQL  (Pro — 80GB volume)              │
│         Current usage: ~5GB data, ~11GB filesystem           │
│                                                              │
│  ── Market Data ──────────────────────────────────────────── │
│  card_catalog        1.26M cards (TCDB / CLI / CBC)          │
│  market_prices       Current price + graded_data JSONB       │
│  market_price_history  Delta-only SCD Type 2 price history   │
│  market_raw_sales    Every eBay sold listing (880K+ rows)    │
│  market_prices_status  View: staleness / freshness per card  │
│                                                              │
│  ── Personal Collection ──────────────────────────────────── │
│  collection          user_id · card_catalog_id FK · grade    │
│  cards               Ledger: user_id + card_name (text key)  │
│  card_results        Raw eBay sales per ledger card          │
│  card_price_history  Per-card fair-value snapshots           │
│  portfolio_history   Daily portfolio totals                  │
│                                                              │
│  ── Auth ─────────────────────────────────────────────────── │
│  users               username · bcrypt hash · role           │
│                                                              │
│  ── Scrape Tracking ──────────────────────────────────────── │
│  scrape_runs         Status, progress, cards_processed       │
│  scrape_run_errors   Per-card error log per run              │
│                                                              │
│  ── Sealed Products ──────────────────────────────────────── │
│  sealed_products     Box/pack MSRP, pack config              │
│  sealed_product_odds Pack odds per product                   │
│                                                              │
│  ── Analytics (legacy / supplementary) ───────────────────── │
│  rookie_cards / rookie_price_history / player_stats          │
│  standings                                                   │
└──────────────────────────────────────────────────────────────┘
             ↑ writes
┌──────────────────────────────────────────────────────────────┐
│           GITHUB ACTIONS  (Scraping — cloud only)            │
│                                                              │
│  Core scripts:                                               │
│  scrape_card_prices.py    eBay Selenium engine (shared lib)  │
│  scrape_master_db.py      Bulk catalog scraper               │
│  scrape_beckett_catalog.py  Populate card_catalog            │
│  daily_scrape.py          Scrape ledger cards → cards table  │
│  preflight_db_check.py    DB disk usage gate (absolute GB)   │
│                                                              │
│  Scheduled workflows (key ones):                             │
│  catalog_tier_base.yml      Daily 6am UTC — base backfill    │
│  catalog_tier_staple.yml    Daily 8am UTC — staple prices    │
│  catalog_tier_premium.yml   Daily 10am UTC — premium prices  │
│  catalog_tier_stars.yml     Daily noon UTC — stars prices    │
│  catalog_tier_graded.yml    Sunday — PSA/BGS graded prices   │
│  master_db_daily.yml        Daily — 4-sport 1K card sweep    │
│  master_db_weekly.yml       Sunday — full rookie sweep       │
│  backfill_all_tiers.yml     Daily 1:21pm — raw sales backfill│
│  db_health_check.yml        Daily 5am — disk usage check     │
│  daily_scrape.yml           On demand — ledger card scrape   │
└──────────────────────────────────────────────────────────────┘
```

---

## Repository Layout

```
cardDB/
├── api/                        # FastAPI application
│   ├── main.py                 # App factory, CORS, health, SPA static
│   └── routers/                # One file per feature domain
│       ├── auth.py             # Login / session / JWT
│       ├── cards.py            # Card ledger CRUD + scrape trigger
│       ├── catalog.py          # 1.26M card catalog browse
│       ├── collection.py       # User collection (FK to catalog)
│       ├── master_db.py        # Young Guns DB + grading ROI
│       ├── stats.py            # Workflow status + scrape trigger
│       ├── scan.py             # Claude Vision card identification
│       ├── ai.py               # AI endpoints (grading advisor, market digest, deal finder)
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
├── scrape_card_prices.py       # Core eBay Selenium scraping engine
├── scrape_master_db.py         # Bulk catalog scraper (raw + graded modes)
├── scrape_beckett_catalog.py   # card_catalog populator (TCDB/CLI/CBC)
├── scrape_set_info.py          # Sealed products scraper
├── daily_scrape.py             # Personal ledger card scraper
├── assign_catalog_tiers.py     # Classifies cards as staple/premium/stars/base
├── preflight_db_check.py       # DB disk preflight (absolute GB thresholds)
├── quarantine_outliers.py      # Flags statistical outliers in market_prices
├── catalog_gap_analysis.py     # Audits coverage by sport/year
├── dashboard_utils.py          # Shared Python utility layer
├── db.py                       # psycopg2 ThreadedConnectionPool
├── schema.sql                  # Full PostgreSQL schema
├── migrate_add_graded_data.py  # Idempotent migration (runs on deploy)
├── migrate_add_cards_processed.py  # Idempotent migration (runs on deploy)
│
├── .github/workflows/          # 20+ workflows (all scraping, CI, migrations)
├── Dockerfile                  # Railway: python:3.11-slim + Node 20
└── docs/                       # Architecture, workflow, component docs
```

---

## Key Data Flows

### 1. Scraping Pipeline

```
GitHub Actions trigger (schedule or workflow_dispatch)
  → preflight_db_check.py: verify disk < 70GB (fail) / < 60GB (warn)
  → scrape_master_db.py reads card_catalog (filtered by tier, sport, stale-days)
      Note: SET max_parallel_workers_per_gather = 0 before load_cards() query
            (prevents PostgreSQL DSM shared memory exhaustion on Railway)
  → For each card: scrape_card_prices.process_card()
      → Headless Chrome → eBay sold listings page
      → _apply_variant_filter() — strips wrong parallels from results
      → parse sold prices → calculate_fair_price() → fair_value
  → UPSERT market_prices (fair_value, trend, confidence, image_url)
  → INSERT market_price_history only when price changed (SCD Type 2)
  → INSERT market_raw_sales individual listings (dedup by listing_hash)
  → Graded mode: accumulate graded_data JSONB → flush to market_prices
  → scrape_runs row updated every 50 cards (cards_processed, cards_found)
  → Graceful exit when elapsed >= --max-hours 5.75 (before GitHub 6h kill)
```

### 2. User Request

```
Browser → FastAPI → psycopg2 pool → PostgreSQL → JSON → React renders
```

The axios interceptor in `src/api/` automatically unwraps `res.data`, so callers receive the payload directly. All card-related endpoints use query parameters (not path segments) because card names frequently contain `[`, `]`, `#`, and `/`.

### 3. Authentication

```
POST /api/auth/login → bcrypt verify password → JWT (HS256, 7-day expiry)
  → stored in localStorage
  → axios interceptor adds: Authorization: Bearer <token>
  → get_current_user() FastAPI dependency validates on all protected routes
  → get_admin_user() dependency additionally checks role == 'admin'
```

### 4. Card Catalog Browse

```
GET /api/catalog?sport=NHL&year=2024-25&page=1
  → SELECT FROM card_catalog cc
    LEFT JOIN market_prices mp ON mp.card_catalog_id = cc.id
    WHERE cc.sport='NHL' AND cc.year='2024-25'
    ORDER BY year DESC LIMIT 50 OFFSET 0
  Total count: pg_class estimate (avoids full-scan on 1.26M rows)
  Results include: fair_value, trend, confidence, graded_data, image_url
```

### 5. Collection Management

```
POST /api/collection {card_catalog_id, grade, cost_basis}
  → INSERT INTO collection ON CONFLICT (user_id, card_catalog_id, grade)
    DO UPDATE SET quantity = quantity + 1

GET /api/collection/owned-ids
  → Returns set of card_catalog_ids (used for checkmark badges on Catalog page)
```

### 6. Grading ROI Lookup

```
GET /api/master-db/grading-lookup?player=Bedard
  Priority 1: young_guns.csv master DB (CSV-backed, highest quality)
  Priority 2: market_prices.graded_data JSONB (catalog-linked, up to date)
  Priority 3: rookie_price_history.graded_data (legacy fallback)
  → CardInspect renders ROI table: Raw / PSA 9 / PSA 10 / BGS 9.5 / BGS 10
```

### 7. Raw Sales Storage

```
scrape_card_prices.py returns individual eBay sold listings per card
  → listing_hash = md5(card_catalog_id|sold_date|title)
  → INSERT INTO market_raw_sales ON CONFLICT (listing_hash) DO NOTHING
  880K+ rows currently. Backfill via backfill_raw_sales.yml / backfill_all_tiers.yml.
```

### 8. Scrape Progress Monitoring

```
Admin → Pipeline tab polls GET /api/stats/workflow-status
  → FastAPI queries GitHub API concurrently for latest run per workflow
  → Overlay with scrape_runs table for in-progress DB state
  → cards_processed / cards_found written every 50 cards mid-run
  → Frontend shows: progress bar, hit rate, cards/hr, ETA, elapsed
```

---

## Deployment Config

| Setting | Value |
|---|---|
| Platform | Railway Pro plan (~8GB RAM) |
| Builder | Dockerfile (python:3.11-slim + Node 20) |
| Build steps | `pip install -r requirements.txt` → `npm run build` |
| On deploy | `python migrate_add_graded_data.py && python migrate_add_cards_processed.py` |
| Start | `uvicorn api.main:app --host 0.0.0.0 --port $PORT` |
| Auto-deploy | Push/merge to `main` → Railway rebuilds |
| Custom domain | southwestsportscards.ca |
| DB volume | 80GB (resized 2026-03-18 from 10GB) |

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| Single Railway service | FastAPI serves both API and React dist — one deploy, no CORS complexity |
| Dockerfile over Nixpacks | Explicit control over Python + Node versions; ensures Chrome installs correctly |
| psycopg2 ThreadedConnectionPool | Sync FastAPI workers; pool avoids per-request reconnects, bounded at 10 |
| All card endpoints use query params | Card names contain `[`, `]`, `#`, `/` — these break URL path routing |
| GitHub Actions for scraping | Headless Chrome needs real compute; GH Actions runners are free and ephemeral |
| CSS Modules | Scoped styles per component, no class name collisions |
| SCD Type 2 price history | Only write history rows when fair_value actually changes — keeps table lean |
| graded_data JSONB in market_prices | Single FK-linked source for PSA/BGS — no fragmentation across tables |
| PyJWT not python-jose | `import jwt` / `jwt.PyJWTError` — python-jose caused import failures on Railway |
| SET max_parallel_workers_per_gather = 0 | Prevents PostgreSQL DSM shared memory exhaustion in load_cards() on Railway |
| Absolute GB preflight thresholds | `--warn-gb 60 --fail-gb 70` — percentage thresholds were unreliable as volume grew; absolute values are predictable |
| listing_hash dedup on raw sales | md5(card_catalog_id|sold_date|title) — idempotent backfills, no duplicate sales rows |
| Email notifications on start/cancel | dawidd6/action-send-mail@v3 on catalog_tier_base.yml and master_db_daily.yml — visibility into long-running jobs |
| --max-hours 5.75 graceful exit | Scrapers self-terminate 15 minutes before GitHub's 6h runner kill, logging clean state |

---

## Auth and Roles

| Role | Access |
|---|---|
| `admin` | All pages + user management + admin dashboard + scrape health panel |
| `user` | All personal pages (ledger, collection, portfolio) |
| `guest` | Read-only access; write operations display prompt to sign in |
| Public (no token) | Catalog browse only — `/catalog` is fully public |

---

## card_catalog Coverage (as of 2026-03)

| Sport | Cards | Sources | Era |
|---|---|---|---|
| NHL | ~310K | TCDB + CLI | 1951–2026 |
| NBA | ~278K | TCDB | 1967–2026 |
| NFL | ~316K | TCDB + CBC | 1948–2026 |
| MLB | ~358K | TCDB + CBC + CLI | 1907–2026 |
| **Total** | **~1,262,503** | | |

---

## Scrape Tier Details

Tiers are assigned by `assign_catalog_tiers.py` and stored in `card_catalog.scrape_tier`.

| Tier | Card types | Volume estimate | Current status |
|---|---|---|---|
| staple | YG, Prizm RC, Chrome RC, SP Authentic RCs | ~15K cards | 100% priced, daily |
| premium | Autos, patches, serials, relics | ~80K cards | Backfill in progress |
| stars | Major-brand rookie cards | ~200K cards | Backfill in progress |
| base | Everything else 2010+ | ~800K cards | ~8.5% priced, backfill running |

The variant filter (`_apply_variant_filter`) excludes superset variants from results — e.g., when scraping a "Rainbow" parallel, "Rainbow Color Wheel" listings are excluded to avoid contaminating the price.

---

## Component Documents

| Document | What it covers |
|---|---|
| [concepts.md](concepts.md) | Key vocabulary and mental models |
| [backend.md](backend.md) | FastAPI routers — endpoints, inputs, outputs, auth |
| [database.md](database.md) | PostgreSQL tables, schema, query patterns |
| [frontend.md](frontend.md) | React pages, components, contexts, API layer |
| [scrapers.md](scrapers.md) | eBay scraping engine, variant filter, bulk scraper |
| [scrape_engine.md](scrape_engine.md) | Deep function-level reference for the scraping pipeline |
| [workflows.md](workflows.md) | GitHub Actions schedules, triggers, env vars |
| [dashboard_utils.md](dashboard_utils.md) | Shared Python utility layer |

---

## Roadmap

### Now — Base Tier Backfill *(active, ~7 days from 2026-03-22)*

12 parallel GH Actions runners, 3 runs/day (6am/noon/6pm UTC), ~135K cards/day.

Once all base-tier cards have a first price:
- Daily runs become pure delta — only stale cards re-scraped
- Runtime drops from 5.75h → ~10 min per sport per tier
- NHL base tier revisit (currently 89%+ miss rate, paused during backfill)

### Near-term — Monetization + AI *(1–2 weeks)*

**Offsite DB backups** *(highest priority — protect the moat)*
- Weekly `pg_dump` to Cloudflare R2 via GitHub Actions (~$1/month)
- Single Railway instance is a single point of failure for the core asset
- Must be tested with a restore before it counts

**Ad integration**
- Google AdSense on public pages: `/catalog`, `/trending`, `/releases`, `/sets`, card detail pages
- Protected pages (My Cards, Portfolio) stay ad-free to preserve UX for returning users

**eBay affiliate links**
- Add eBay Partner Network tracking IDs to existing listing links — zero extra scraping required

**Market Digest AI** (`POST /api/ai/market-digest`)
- Weekly GitHub Actions cron queries `market_price_history` for biggest 7-day movers
- One Claude call → 3-paragraph plain English summary per sport
- Stored in DB, surfaced on a `/digest` page + optional email delivery

**Price alerts**
- Scheduled GH Actions checks `market_price_history` for >10% moves in 7 days
- Queries users who track the card → sends email via existing dawidd6/action-send-mail@v3 infra
- Requires: `user_alert_prefs` table migration

### Soon — Platform *(1 month)*

**SEO card pages**
- Individual catalog pages need to be Google-indexable
- Options: prerendering via react-snap, SSR layer, or static generation for high-value cards
- Goal: `/catalog/12345` → Google indexes "Patrick Mahomes 2020 Prizm RC price" → organic traffic → ads

**Deal Finder AI** (`POST /api/ai/deal-finder`)
- Claude surfaces cards where raw price is anomalously low vs graded comps (high upside)
- Data already in `market_prices.graded_data` — zero extra scraping

**Guest → signup conversion**
- Clear CTAs when guests hit auth walls in the catalog and card detail views

### Medium-term — Multi-Source Pricing *(2–3 months)*

eBay is the foundation. Adding more sold-data sources deepens every price point and widens coverage:

| Source | Card type | Why |
|---|---|---|
| **PWCC** | PSA/BGS slabs, high-end | Largest auction house — sets market price for premium cards |
| **Goldin** | PSA/BGS slabs, vintage | Key for vintage and graded comps |
| **Heritage Auctions** | Vintage, sets | Completeness for pre-1980 cards |
| **Whatnot** | Raw + slabs, all price points | Fastest-growing card marketplace — younger collectors |
| **COMC** | Raw base cards | Fixed-price; great for bulk/base coverage |
| **StockX** (cards) | Graded slabs | If data becomes accessible |

**Integration pattern:**
- New scraper per source → dedup against `market_raw_sales` via `listing_hash` → same price pipeline
- `market_raw_sales.source` column (add via migration) tracks where each sale came from
- Multi-source = better confidence scores, wider coverage, harder to replicate

**Public API v1**
- Versioned REST API: `GET /api/v1/cards/{id}/price`, `/history`
- API key auth separate from user JWT
- Free tier (100 req/day) + paid tier (Stripe, long-term)
- Documentation page at `/docs/api`

**Natural language portfolio queries** (`/api/ai/portfolio-query`)
- Chat input on Portfolio page — "what's my best performing card this month?"
- Claude answers from the authenticated user's ledger + price history data

**Vector search**
- `pgvector` on Railway PostgreSQL for fuzzy card name matching and entity resolution
- Would eventually replace the manual `_apply_variant_filter` logic
- Requires: `CREATE EXTENSION IF NOT EXISTS vector` in schema.sql + Railway support check first

### Long-term — Defensibility *(6+ months)*

The longer CardDB runs, the harder it is to replicate:
- 1 year of daily prices = dataset competitors cannot recreate retroactively
- 2 years = genuine historical archive no free alternative has
- Multi-source data = price validation no scraper-only site can match
- Portfolio tracking + price history = user lock-in (their data lives here)

**Premium tier:** ad-free + unlimited AI + higher API rate limits (Stripe billing)

**Volume resize:** At current growth (~340 MB/day filesystem), 80GB → 160GB planned for ~August 2026.
