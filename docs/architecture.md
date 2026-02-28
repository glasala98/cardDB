# CardDB — Data Architecture & Flow

> **Status:** Current state documented below. Target (Supabase) state is planned — see [TODO.md](../TODO.md).

---

## Current Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        BROWSER                                  │
│   React 18 + Vite  (http://localhost:5173 dev / nginx prod)     │
│                                                                 │
│  Pages: /ledger  /portfolio  /master-db  /charts  /admin  etc.  │
│  Contexts: AuthContext  CurrencyContext  PublicModeContext       │
│  API clients: src/api/*.js  (axios, auto-unwrap res.data)        │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTP/JSON  (Bearer JWT)
                         │ /api/*  proxied by nginx in prod
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FASTAPI  (port 8000)                         │
│                    api/main.py                                  │
│                                                                 │
│  Routers:                                                       │
│  /api/auth      → auth.py      (login, /me, logout)            │
│  /api/cards     → cards.py     (CRUD, scrape, scan, import)    │
│  /api/master-db → master_db.py (YG market DB, NHL stats)       │
│  /api/stats     → stats.py     (alerts, GH Actions dispatch)   │
│  /api/admin     → admin.py     (user management)               │
│  /api/scan      → scan.py      (Claude Vision analysis)        │
└────────────┬───────────────────────────┬────────────────────────┘
             │ import                    │ import
             ▼                           ▼
┌────────────────────────┐  ┌───────────────────────────────────┐
│   dashboard_utils.py   │  │    scrape_card_prices.py          │
│   (shared utility)     │  │    (Selenium eBay scraper)        │
│                        │  │                                   │
│  - load_data()         │  │  - process_card()                 │
│  - save_data()         │  │  - search_ebay_sold()             │
│  - parse_card_name()   │  │  - calculate_fair_price()         │
│  - archive_card()      │  │  - 4-stage search strategy        │
│  - load_users()        │  │  - serial comp estimation         │
│  - analyze_card_images()│  └───────────────────────────────────┘
│  - load_master_db()    │
│  - NHL stats helpers   │
│  - Correlation funcs   │
└────────────┬───────────┘
             │ read/write
             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     DATA FILES                                  │
│                                                                 │
│  data/                                                          │
│  ├── admin/                     (per-user, one folder each)    │
│  │   ├── card_prices_summary.csv    main card collection       │
│  │   ├── card_prices_results.json   raw eBay sales + images    │
│  │   ├── price_history.json         price snapshots over time  │
│  │   ├── portfolio_history.json     daily portfolio value      │
│  │   └── card_archive.csv           soft-deleted cards         │
│  ├── josh/                      (same structure per user)      │
│  └── master_db/                 (shared across all users)      │
│      ├── young_guns.csv             YG market DB               │
│      ├── young_guns_price_history.json                         │
│      ├── young_guns_raw_sales.json                             │
│      ├── nhl_stats.json             cached NHL API data        │
│      └── nhl_standings.json         cached team standings      │
│                                                                 │
│  users.yaml   (gitignored — user credentials, bcrypt hashes)   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Data Flows

### 1. User Login
```
Browser → POST /api/auth/login {username, password}
  → verify_password() checks bcrypt hash in users.yaml
  → returns JWT (24h expiry, signed with JWT_SECRET)
  → stored in localStorage
  → axios interceptor adds "Authorization: Bearer <token>" to all requests
```

### 2. Card Ledger Load
```
Browser → GET /api/cards
  → get_current_user() validates JWT → extracts username
  → get_user_paths(username) → resolves data/{username}/*.csv|json
  → load_data(csv_path, results_json_path)
      → checks _DATA_CACHE (mtime-based) — skips re-parse if unchanged
      → merges CSV + results JSON → adds parsed fields (Player, Year, Set, Grade, Confidence)
  → returns {cards: [...]}
```

### 3. Card Scan → Add
```
Browser (ScanCardModal)
  → POST /api/scan/analyze (multipart: front.jpg, [back.jpg])
  → analyze_card_images() → sends to Claude Vision (claude-3-5-sonnet)
  → Claude returns: player, year, brand, subset, card#, parallel, serial, grade, confidence
  → Browser shows pre-filled form
  → POST /api/cards {card_name, cost_basis, ...}
  → add_card() appends row to card_prices_summary.csv
  → auto-triggers POST /api/cards/scrape?name= (background task)
      → scrape_single_card() → process_card() → eBay scrape
      → updates results JSON + CSV with fair_value, trend, etc.
```

### 4. Rescrape All (GitHub Actions)
```
Browser → POST /api/stats/trigger-scrape
  → GitHub API: POST /repos/{owner}/{repo}/actions/workflows/daily_scrape.yml/dispatches
  → GitHub Actions runner:
      1. Checkout code
      2. SSH: download data files from server (scp)
      3. Run: python daily_scrape.py --workers 3
          → process_card() for each card (parallel, Selenium Chrome)
          → merges new sales, updates CSV, appends price/portfolio history
      4. SSH: upload updated data files back to server
  → Browser polls GET /api/stats/scrape-status (every 15s)
      → checks GitHub API for run status + step log
      → ScrapeProgressModal shows progress bar + steps
```

### 5. Daily Scrape (Cron)
```
GitHub Actions (cron: 0 8 * * *)
  → Same as "Rescrape All" above but scheduled automatically
  → Also runs scrape_master_db.py (YG prices) and scrape_nhl_stats.py
```

### 6. Multi-User Data Isolation (Current)
```
users.yaml defines usernames + bcrypt hashes
Each user gets their own folder: data/{username}/
FastAPI resolves paths via get_user_paths(username) on every request
No cross-user data access at the filesystem level
master_db/ is shared (read/write by all users + scrapers)
```

---

## Auth Flow Detail
```
┌──────────┐   POST /login    ┌───────────┐  verify_password()  ┌──────────────┐
│ Browser  │ ──────────────→  │  FastAPI  │ ──────────────────→ │  users.yaml  │
│          │ ←──────────────  │  auth.py  │ ←──────────────────  │  (bcrypt)    │
│ JWT token│   {token, user}  └───────────┘  True / False       └──────────────┘
│ stored in│
│localStorage
│          │   GET /api/cards  ┌───────────┐  _decode_token()
│          │ ──────────────→  │  FastAPI  │ ──────────────→  username
│  + Bearer│                  │  cards.py │
│   token  │ ←──────────────  │           │  get_user_paths(username) → file paths
│          │   {cards: [...]} └───────────┘
└──────────┘
```

---

## Target Architecture (Post-Supabase)

```
┌─────────────────────────────────────────────────────────────────┐
│                        BROWSER                                  │
│          React (same — minimal changes)                         │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FASTAPI  (port 8000)                         │
│           auth → Supabase Auth  (replaces users.yaml+JWT)       │
└────────────┬────────────────────────────────────────────────────┘
             │ supabase-py (service role key)
             ▼
┌─────────────────────────────────────────────────────────────────┐
│                  SUPABASE (PostgreSQL)                          │
│                                                                 │
│  Tables:                                                        │
│  cards             (replaces card_prices_summary.csv)           │
│  card_results      (replaces card_prices_results.json)          │
│  price_history     (replaces price_history.json)                │
│  portfolio_history (replaces portfolio_history.json)            │
│  card_archive      (replaces card_archive.csv)                  │
│  master_cards      (replaces young_guns.csv — all sports)       │
│                                                                 │
│  Row Level Security: each user reads/writes only their rows     │
│  Supabase Auth: email/password, OAuth, self-registration        │
│  Supabase Storage: card images (replaces eBay hash approach)    │
└─────────────────────────────────────────────────────────────────┘
             ↑
             │ write (service role — GitHub Actions scraper)
┌─────────────────────────────────────────────────────────────────┐
│              GitHub Actions Scraper                             │
│  daily_scrape.py → writes directly to Supabase                 │
│  scrape_master_db.py → writes to master_cards table            │
│  scrape_nhl_stats.py → writes to nhl_stats table               │
│  No more scp! Data lives in cloud, accessible everywhere.       │
└─────────────────────────────────────────────────────────────────┘
```

### Schema (planned)

```sql
-- User collection
cards (
  id uuid PRIMARY KEY,
  user_id uuid REFERENCES auth.users,  -- RLS key
  card_name text,
  player text, year text, set_name text, grade text,
  fair_value numeric, cost_basis numeric, trend text,
  num_sales int, confidence text, tags text,
  purchase_date date, last_scraped timestamptz,
  created_at timestamptz DEFAULT now()
)

-- Raw eBay sales per card
card_results (
  id uuid PRIMARY KEY,
  card_id uuid REFERENCES cards,
  user_id uuid REFERENCES auth.users,
  title text, price_val numeric, sold_date date,
  listing_url text, image_url text, scraped_at timestamptz
)

-- Per-card price snapshots
price_history (
  id uuid PRIMARY KEY,
  user_id uuid REFERENCES auth.users,
  card_name text, fair_value numeric, num_sales int,
  snapshot_date date
)

-- Daily portfolio totals
portfolio_history (
  id uuid PRIMARY KEY,
  user_id uuid REFERENCES auth.users,
  total_value numeric, total_cards int, avg_value numeric,
  snapshot_date date
)

-- Market DB (shared, all sports)
master_cards (
  id uuid PRIMARY KEY,
  sport text, season text, brand text, card_number text,
  player text, team text, position text,
  fair_value numeric, num_sales int, trend text,
  graded_prices jsonb,  -- {PSA10: {value, sales}, ...}
  last_scraped timestamptz
)
```
