# CardDB — Architecture & Data Flow

> **Status:** Production on Railway (Pro plan). PostgreSQL + FastAPI + React. No file-based storage.

---

## System Overview

```
┌──────────────────────────────────────────────────────────────┐
│                        BROWSER                               │
│   React 18 + Vite  (southwestsportscards.ca)                 │
│                                                              │
│  Pages:                                                      │
│   /ledger          Card Ledger (personal owned cards)        │
│   /ledger/:name    Card detail + price history               │
│   /portfolio       Portfolio value over time                 │
│   /collection      My Collection (catalog-linked ownership)  │
│   /catalog         Card Catalog (2.6M cards, browse/search)  │
│   /master-db       YG/Rookie market analytics                │
│   /charts          Value distribution + trend charts         │
│   /nhl-stats       NHL player stats with card values         │
│   /archive         Archived cards                            │
│   /admin           User management (admin only)              │
│                                                              │
│  Contexts: AuthContext · CurrencyContext · PublicModeContext  │
│  API:      src/api/*.js  (axios, Bearer JWT, auto-unwrap)     │
└────────────────────────┬─────────────────────────────────────┘
                         │ HTTPS/JSON  (Bearer JWT)
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                  FASTAPI  (Railway — port $PORT)              │
│                  api/main.py                                 │
│                                                              │
│  Routers:                                                    │
│  /api/auth        auth.py       login · /me · logout         │
│  /api/cards       cards.py      CRUD · scrape · scan · import│
│  /api/catalog     catalog.py    browse 2.6M catalog, filters │
│  /api/collection  collection.py ownership layer              │
│  /api/master-db   master_db.py  YG/Rookie market analytics   │
│  /api/stats       stats.py      portfolio · GH Actions       │
│  /api/scan        scan.py       Claude Vision card scan      │
│  /api/admin       admin.py      user CRUD (admin only)       │
│                                                              │
│  Static: React build served via SPA catch-all fallback       │
└────────────┬─────────────────────────────────────────────────┘
             │ psycopg2 (ThreadedConnectionPool 1–10)
             ▼
┌──────────────────────────────────────────────────────────────┐
│             RAILWAY PostgreSQL  (Pro — 10GB)                 │
│                                                              │
│  ── Personal Collection ──────────────────────────────────── │
│  cards               Ledger: user_id + card_name (text key)  │
│  card_results        Raw eBay sales + image URLs             │
│  card_price_history  Per-card fair-value snapshots           │
│  portfolio_history   Daily portfolio totals                  │
│                                                              │
│  collection          Ownership layer (user → card_catalog)   │
│    user_id · card_catalog_id FK · grade · quantity           │
│    cost_basis · purchase_date · notes                        │
│                                                              │
│  ── Card Reference ───────────────────────────────────────── │
│  card_catalog        2.6M cards (TCDB / CLI / CBC)           │
│    sport · year · brand · set_name · card_number             │
│    player_name · team · variant · is_rookie · is_parallel    │
│                                                              │
│  market_prices       Current price per card (FK→catalog)     │
│  market_price_history  Delta-only SCD Type 2 price history   │
│                                                              │
│  ── Market / Analytics ───────────────────────────────────── │
│  rookie_cards              YG/Rookie market DB               │
│  rookie_price_history      Price snapshots per rookie        │
│  rookie_portfolio_history  Daily YG portfolio totals         │
│  rookie_raw_sales          Raw eBay sales per rookie         │
│  player_stats              NHL/NBA/NFL/MLB stats (JSONB)     │
│  standings                 Team standings per sport          │
│  rookie_correlation_history  Analytics snapshots             │
└──────────────────────────────────────────────────────────────┘
             ↑ writes
┌──────────────────────────────────────────────────────────────┐
│       Scraper Scripts  (local CLI / GitHub Actions)          │
│                                                              │
│  scrape_card_prices.py      eBay Selenium engine (shared)    │
│  daily_scrape.py            Scrape ledger cards → cards table│
│  scrape_master_db.py        Scrape catalog → market_prices   │
│  scrape_beckett_catalog.py  Populate card_catalog (TCDB/CLI) │
│  scrape_nhl_stats.py        NHL API → player_stats table     │
└──────────────────────────────────────────────────────────────┘
```

---

## Deployment (Railway)

| Setting | Value |
|---------|-------|
| Platform | Railway Pro plan |
| Builder | Dockerfile (python:3.11-slim + Node 20) |
| Build step | `pip install -r requirements.txt` + `npm run build` |
| Start | `uvicorn api.main:app --host 0.0.0.0 --port $PORT` |
| Auto-deploy | Push/merge to `main` → Railway rebuilds |
| Custom domain | southwestsportscards.ca |
| Database | Railway internal PostgreSQL (same project, 10GB) |

**Key gotcha:** use `PyJWT` not `python-jose` — `import jwt` / `jwt.PyJWTError`.

---

## Key Data Flows

### 1. User Login
```
POST /api/auth/login {username, password}
  → verify_password() checks bcrypt hash in users.yaml
  → returns JWT (24h, signed with JWT_SECRET env var)
  → stored in localStorage
  → axios sets "Authorization: Bearer <token>" on all requests
```

### 2. Card Ledger
```
GET /api/cards
  → validates JWT → extracts username
  → SELECT FROM cards WHERE user_id=? + card_results JOIN
  → returns {cards: [...]}

Price updates: scraper writes to cards.fair_value + appends card_price_history.
```

### 3. Card Catalog Browse
```
GET /api/catalog?sport=NHL&year=2024-25&page=1
  → SELECT FROM card_catalog cc
    LEFT JOIN market_prices mp ON mp.card_catalog_id = cc.id
    WHERE cc.sport='NHL' AND cc.year='2024-25'
    ORDER BY year DESC LIMIT 50

Total count: pg_class estimate (unfiltered) to avoid full-scan timeout on 2.6M rows.
Filter dropdowns: GET /api/catalog/filters?sport=NHL → years + sets.
```

### 4. My Collection
```
POST /api/collection {card_catalog_id, grade, cost_basis, ...}
  → INSERT INTO collection (user_id, card_catalog_id, grade, ...)
    ON CONFLICT (user_id, card_catalog_id, grade) DO UPDATE quantity += 1

GET /api/collection/owned-ids → Set of card_catalog_ids (for ✓ badges in Catalog page)
GET /api/collection           → Full list joined with card_catalog + market_prices
```

### 5. Market Price Scraping — SCD Type 2
```
scrape_master_db.py --sport NHL --limit 500
  → SELECT FROM card_catalog WHERE player_name!='' AND set_name!=''
  → For each card: eBay Selenium via scrape_card_prices.process_card()
  → UPSERT market_prices (latest fair_value, trend, confidence)
  → INSERT market_price_history ONLY when fair_value changed from last row
    (delta-only insert = no consecutive duplicate prices = SCD Type 2)
```

### 6. Rescrape All (via GitHub Actions)
```
POST /api/stats/trigger-scrape
  → GitHub API dispatches daily_scrape.yml
  → Runner: python daily_scrape.py --workers 3
      → eBay Selenium for each ledger card
      → Updates cards + card_price_history + portfolio_history
  → Browser polls GET /api/stats/scrape-status every 15s
      → ScrapeProgressModal: live step log + progress bar
```

### 7. Catalog Quality Reports (weekly CI)
```
.github/workflows/catalog_quality_report.yml  (Monday 10am UTC + manual)
  → pytest tests/test_catalog_quality.py  (23 assertions)
  → python catalog_gap_analysis.py --markdown --output gap_report.md
  → Publish to $GITHUB_STEP_SUMMARY
  → Upload artifacts: test_report.md + gap_report.md (90-day retention)
```

---

## Auth & Users

```
users.yaml  (gitignored — bcrypt hashes)
  admin: { display_name, role: admin, password_hash }
  josh:  { display_name, role: user,  password_hash }

Dev fallback: admin/admin when users.yaml absent
?public=true URL param → read-only share mode
```

---

## Multi-User Data Isolation

Every personal table has a `user_id TEXT` column. All queries filter by the JWT username.
`card_catalog`, `market_prices`, `rookie_cards`, and `player_stats` are shared read-only.

---

## card_catalog Coverage (as of 2026-03)

| Sport | Cards | Sources | Era |
|-------|-------|---------|-----|
| NHL | ~310K | TCDB + CLI | 1951–2026 |
| NBA | ~278K | TCDB | 1967–2026 |
| NFL | ~643K | TCDB + CBC | 1948–2026 |
| MLB | ~1.4M | TCDB + CBC + CLI | 1907–2026 |
| **Total** | **~2.6M** | | |

Sources: **TCDB** (curl_cffi, bypasses Cloudflare) · **CLI** (checklistinsider.com, 2022+) · **CBC** (cardboardconnection.com, 2008–2023).
Checkpoint: `catalog_checkpoint.json` — resumes interrupted runs without re-scraping completed sets.
