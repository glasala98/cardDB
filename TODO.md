# CardDB — Things To Do

## 🔥 Immediate (Server / Deployment)
- [ ] Consider resizing DO droplet to 2GB ($12/mo) — currently at 81% RAM usage

## 🔑 Dev Setup Notes
- FastAPI runs on **port 8001** locally (WSL ghost process holds :8000) — `vite.config.js` proxy target is `:8001`
- **GITHUB_TOKEN** must be in `.env` for "Rescrape All" to trigger GitHub Actions workflow (needs `repo` + `workflow` scopes on a classic PAT)
- Auth dev fallback: if no `users.yaml` present, `admin` / `admin` always works locally

---

---

## 🏗️ Big Architecture — Supabase Migration
Goal: replace all CSV/JSON files with a hosted PostgreSQL database so the
app scales to all sports, all card types, millions of rows.

### Why
- Current CSV/JSON approach hits RAM limits as data grows
- Want to expand: NHL → all sports, rookies → all card types
- Supabase is free up to 500MB, accessible from anywhere (VPS, TrueNAS, local, GitHub Actions)

### Plan
1. [ ] Create Supabase project (free at supabase.com)
2. [ ] Design DB schema:
   - `cards` table — user collection (replaces card_prices_summary.csv)
   - `card_results` table — raw sales + scrape data (replaces card_prices_results.json)
   - `price_history` table — per-card price snapshots (replaces price_history.json)
   - `portfolio_history` table — daily portfolio value (replaces portfolio_history.json)
   - `master_cards` table — market DB (replaces young_guns.csv, expandable to all sports)
   - `card_archive` table — archived cards (replaces card_archive.csv)
3. [ ] Migrate existing data (CSV/JSON → Supabase)
4. [ ] Rewrite `dashboard_utils.py` data layer (load_data, save_data, etc. → Supabase queries)
5. [ ] Update GitHub Actions scraper to write to Supabase instead of CSV/JSON
6. [ ] Update FastAPI routers (minimal changes — mostly just dashboard_utils changes flow up)
7. [ ] Remove file-based caching (_DATA_CACHE) — Supabase handles this
8. [ ] Test end-to-end locally, then deploy

### Benefits after migration
- All sports (NHL, NBA, MLB, NFL) with a `sport` column
- All card types (rookies, autos, parallels, refractors, etc.)
- Proper full-text search across millions of cards
- No more scp uploads for data changes
- GitHub Actions + VPS + TrueNAS all read/write the same DB
- Could eventually cancel VPS and run API on TrueNAS (data lives in cloud)

---

## 🔐 Security (Post-Supabase)
After the Supabase migration, harden the auth and data layer:

### Authentication
- [ ] Replace `users.yaml` with Supabase Auth (built-in JWT, bcrypt, session management)
- [ ] Add **user self-registration** — sign-up form with email + password, email verification
- [ ] Add **password reset** flow (email link via Supabase Auth)
- [ ] Add **OAuth login** option (Google, GitHub) via Supabase Auth providers
- [ ] Session expiry — currently 24h JWT; consider refresh tokens for longer sessions

### Authorization & Data Isolation
- [ ] Enable **Supabase Row Level Security (RLS)** on all tables — users can only read/write their own rows
- [ ] `cards`, `price_history`, `portfolio_history`, `card_archive` tables: RLS policy `auth.uid() = user_id`
- [ ] `master_cards` table: read-only for all authenticated users, write only from service role (scrapers)
- [ ] API service role key (server-side only) — never expose to frontend

### API Security
- [ ] Move JWT secret to environment variable (already done) — ensure it rotates on breach
- [ ] Rate-limit login endpoint (prevent brute force) — FastAPI middleware or nginx `limit_req`
- [ ] Validate all user inputs at API boundary (already partially done via Pydantic)
- [ ] Sanitize card names before passing to shell/scraper (no command injection)
- [ ] HTTPS only in production (already handled by nginx + Let's Encrypt)
- [ ] Review CORS origins — lock down to production domain only in prod

### GitHub Repo
- [ ] Make repo **private** (Settings → General → Danger Zone → Change visibility)
  - GitHub Actions still works on private repos ✅
  - VPS `git pull` via SSH still works ✅
  - No code exposed publicly ✅

---

## 📐 Data Architecture & Flow
*See [docs/architecture.md](docs/architecture.md) for the full diagram*

- [ ] Create `docs/architecture.md` — data flow diagram covering:
  - Browser → React → FastAPI → dashboard_utils → data files (current)
  - Future: Browser → React → FastAPI → Supabase (target)
  - GitHub Actions scraper flow (current vs future)
  - Multi-user data isolation (current: `data/{user}/`, future: RLS)
  - Card scan flow (image → Claude Vision → parsed fields → add card → auto-scrape)
  - Auth flow (login → JWT → axios interceptor → protected routes)

---

## 🌟 Feature Ideas
- [ ] Expand Master DB beyond Young Guns to all rookie cards (all sports)
- [ ] Add card image storage in Supabase (replace eBay hash approach)
- [ ] Better scan accuracy — improve AI prompt for more card types
- [ ] Mobile app (React Native reuse of existing API)
- [ ] Public market page (no login required) for sharing collection value
- [ ] Price alerts — notify when a card crosses a threshold
- [ ] Compare tool — side-by-side card value comparison

---

## ✅ Recently Completed
- [x] React frontend live at southwestsportscards.ca
- [x] FastAPI backend running as systemd service
- [x] AI card scan (brand/parallel/serial detection)
- [x] Auto-scrape after adding card via scan modal
- [x] Admin role fix (/me endpoint)
- [x] Portfolio 500 error fix (NaN serialization)
- [x] Table column reorder (Card Ledger)
- [x] MasterDB slim to 9 columns (removed redundant grade price cols)
- [x] Responsive tables (hide columns at tablet/mobile breakpoints)
- [x] In-process data cache (mtime-based, load_data + load_master_db)
- [x] 1GB swap file added to server
- [x] Admin password changed to lasala8324
- [x] Full documentation pass (README rewrite, api/README, frontend/README, docs/, docstrings on all Python functions)
- [x] All dev changes deployed to production (frontend dist, users.yaml, git pull, API restart)
