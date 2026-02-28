# CardDB — Things To Do

## 🔥 Immediate (Server / Deployment)
- [ ] Upload frontend dist to server (table layout changes pending)
  ```powershell
  scp -r d:\sportscarddb\cardDB\frontend\dist\* root@southwestsportscards.ca:~/cardDB/frontend/dist/
  ```
- [ ] Upload users.yaml to server (new admin password)
  ```powershell
  scp d:\sportscarddb\cardDB\users.yaml root@southwestsportscards.ca:~/cardDB/users.yaml
  ```
  > ⚠️ `users.yaml` is gitignored — must be manually scp'd every time passwords/users change.
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
