# CardDB — Sports Card Portfolio Tracker

A full-stack sports card collection manager. Tracks eBay market value, scrapes sold listings automatically, and visualizes your portfolio — with a React frontend, FastAPI backend, and AI-powered card scanning.

**Live at:** https://southwestsportscards.ca

---

## Architecture

```
browser  ←→  React (Vite)  ←→  FastAPI (:8000)  ←→  dashboard_utils.py
                                      ↑                      ↑
                              api/routers/*.py        data/{user}/*.csv|json
                                                            ↑
                                              GitHub Actions (daily scrape)
```

| Layer | Stack | Location |
|-------|-------|----------|
| Frontend | React 18, Vite, Recharts, CSS Modules | `frontend/` |
| API | FastAPI, uvicorn, JWT auth | `api/` |
| Shared utils | Python, pandas, Selenium, Anthropic SDK | `dashboard_utils.py` |
| Data | CSV + JSON flat files (Supabase migration planned) | `data/{username}/` |
| Scraping | Selenium + Chrome, GitHub Actions cron | `scrape_card_prices.py`, `.github/workflows/` |

---

## Quick Start (Local Dev)

### Prerequisites
- Python 3.9+
- Node 18+
- Google Chrome (for scraper)

### 1. Clone and install

```bash
git clone https://github.com/glasala98/cardDB.git
cd cardDB
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment variables

Create a `.env` file in the project root (see table below). The API reads this automatically via systemd `EnvironmentFile` in production; locally, export them or use a shell script.

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export JWT_SECRET="change-me-in-prod"
export GITHUB_TOKEN="ghp_..."   # only needed for Rescrape All button
```

| Variable | Required | Purpose |
|----------|----------|---------|
| `ANTHROPIC_API_KEY` | Yes | Claude Vision AI card scanning |
| `JWT_SECRET` | Prod only | Signs JWT tokens (dev uses hardcoded fallback) |
| `GITHUB_TOKEN` | Optional | Triggers `daily_scrape` GitHub Actions workflow via API |

### 3. Start the API

```bash
cd api
uvicorn main:app --reload --port 8001
```

API runs at http://localhost:8001. Swagger docs at http://localhost:8001/docs.

> **Note:** Local dev uses port 8001 because WSL can hold a ghost process on 8000. The Vite proxy in `frontend/vite.config.js` targets `:8001`.

### 4. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

React dev server starts at http://localhost:5173. All `/api` requests proxy to `:8001`.

### 5. Login

Default dev credentials (no `users.yaml` needed):
- **Username:** `admin`
- **Password:** `admin`

For production credentials, see [`users.yaml`](#usersyaml) below.

---

## Production Deploy

### Full deploy (frontend + backend)

```bash
# 1. Build React app locally
cd frontend && npm run build

# 2. Upload frontend dist to server
scp -r frontend/dist/* root@southwestsportscards.ca:~/cardDB/frontend/dist/

# 3. Upload users.yaml (if passwords/users changed)
scp users.yaml root@southwestsportscards.ca:~/cardDB/users.yaml

# 4. Push code changes to origin, then pull on server
git push origin dev
ssh root@southwestsportscards.ca "cd ~/cardDB && git pull"

# 5. Restart API service
ssh root@southwestsportscards.ca "systemctl restart carddb-api"
```

### Server details

| Item | Value |
|------|-------|
| OS | Ubuntu 24.04, DigitalOcean 1GB droplet |
| nginx | Serves `frontend/dist/`, proxies `/api/` → :8000 |
| systemd service | `carddb-api` (venv at `/root/cardDB/venv`) |
| nginx config | `/etc/nginx/sites-available/card-dashboard` |
| systemd unit | `/etc/systemd/system/carddb-api.service` |
| Logs | `journalctl -u carddb-api -n 50` |

### Useful server commands

```bash
systemctl status carddb-api          # Check service status
systemctl restart carddb-api         # Restart after code changes
journalctl -u carddb-api -f          # Tail logs live
nginx -t && systemctl reload nginx   # Test + reload nginx config
```

---

## Project Structure

```
cardDB/
├── api/                     # FastAPI backend → see api/README.md
│   ├── main.py              # App entry point, CORS, router mounts
│   └── routers/
│       ├── auth.py          # JWT login / me / logout
│       ├── cards.py         # Card ledger CRUD, scrape, scan, bulk import
│       ├── stats.py         # Market alerts, GitHub Actions workflow dispatch
│       ├── master_db.py     # Young Guns market DB endpoints
│       ├── admin.py         # User management (admin role)
│       └── scan.py          # Claude Vision card image analysis
│
├── frontend/                # React + Vite app → see frontend/README.md
│   ├── src/
│   │   ├── App.jsx          # Root router
│   │   ├── pages/           # One component per route
│   │   ├── components/      # Shared UI components
│   │   ├── context/         # Auth, Currency, PublicMode providers
│   │   └── api/             # Axios API client wrappers
│   ├── vite.config.js
│   └── package.json
│
├── dashboard_utils.py       # Shared data/scraping utilities → see docs/dashboard_utils.md
├── scrape_card_prices.py    # Selenium eBay scraper → see docs/scrapers.md
├── daily_scrape.py          # Daily rescrape cron entry point
├── scrape_master_db.py      # Young Guns bulk scraper
├── scrape_nhl_stats.py      # NHL API stats fetcher
│
├── data/                    # Data directory (gitignored)
│   ├── admin/               # Per-user data folders
│   │   ├── card_prices_summary.csv
│   │   ├── card_prices_results.json
│   │   ├── price_history.json
│   │   └── portfolio_history.json
│   └── master_db/
│       ├── young_guns.csv
│       └── yg_price_history.json
│
├── .github/workflows/
│   ├── daily_scrape.yml         # Daily 8am UTC scrape of user collection
│   ├── master_db_daily.yml      # Daily YG price update
│   └── master_db_weekly.yml     # Weekly full YG rescrape
│
├── tests/                   # Unit tests → see tests/README.md
├── requirements.txt
├── users.yaml               # User credentials (gitignored — see below)
└── TODO.md                  # Development roadmap
```

---

## Python Scripts

| Script | Purpose | Docs |
|--------|---------|------|
| `dashboard_utils.py` | Core data layer: load/save CSV+JSON, parse card names, scrape, archive, NHL stats, caching | [docs/dashboard_utils.md](docs/dashboard_utils.md) |
| `scrape_card_prices.py` | Selenium eBay scraper — builds queries, scrapes sold listings, calculates fair value | [docs/scrapers.md](docs/scrapers.md) |
| `daily_scrape.py` | Cron/GitHub Actions entry point — rescrapes all cards, logs price deltas | [docs/scrapers.md](docs/scrapers.md) |
| `scrape_master_db.py` | Bulk scraper for the Young Guns master database (with grade probing) | [docs/scrapers.md](docs/scrapers.md) |
| `scrape_nhl_stats.py` | Fetches current-season player stats + standings from the NHL API | [docs/scrapers.md](docs/scrapers.md) |

---

## Data Files

| File | Location | Description |
|------|----------|-------------|
| `card_prices_summary.csv` | `data/{user}/` | Main collection — one row per card, fair value + metadata |
| `card_prices_results.json` | `data/{user}/` | Raw eBay sales per card, image hash, last scraped timestamp |
| `price_history.json` | `data/{user}/` | Append-only fair value snapshots over time per card |
| `portfolio_history.json` | `data/{user}/` | Daily portfolio total value snapshots |
| `card_archive.csv` | `data/{user}/` | Soft-deleted cards (restorable) |
| `young_guns.csv` | `data/master_db/` | Young Guns market DB — all graded prices, raw value, NHL stats |
| `yg_price_history.json` | `data/master_db/` | Per-YG-card price history |
| `nhl_stats.json` | `data/master_db/` | Cached NHL API player stats |
| `nhl_standings.json` | `data/master_db/` | Cached NHL team standings |

---

## users.yaml

Controls multi-user auth. **Gitignored** — must be created/updated manually and scp'd to the server on every change.

```yaml
users:
  admin:
    display_name: Admin
    role: admin
    password_hash: "$2b$12$..."   # bcrypt hash
  josh:
    display_name: Josh
    role: user
    password_hash: "$2b$12$..."
```

**Dev fallback:** if `users.yaml` is missing, `admin` / `admin` always works.

To generate a bcrypt hash:
```python
import bcrypt
print(bcrypt.hashpw(b"yourpassword", bcrypt.gensalt()).decode())
```

---

## Running Tests

```bash
python run_tests.py
```

See [tests/README.md](tests/README.md) for test coverage details and how to add new tests.

---

## Further Reading

- [api/README.md](api/README.md) — All API endpoints, auth details, multi-user paths
- [frontend/README.md](frontend/README.md) — React app structure, build steps, component map
- [docs/dashboard_utils.md](docs/dashboard_utils.md) — Core utility function reference
- [docs/scrapers.md](docs/scrapers.md) — Scraper scripts in detail
- [tests/README.md](tests/README.md) — Test suite
- [TODO.md](TODO.md) — Roadmap (Supabase migration, feature ideas)
