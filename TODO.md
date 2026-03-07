# Card Analytics Project TODOs

# Agent System Instruction: Pre-Flight Validation Gate

## Protocol
Before executing any task in the "Implementation Roadmap," you MUST perform a "Pre-Flight Check." Do not proceed if any condition is missing.

## Checklist
1. **Database:** Verify connection to the PostgreSQL instance and confirm `pgvector` extension is active.
2. **Environment:** Confirm all required API keys (OpenAI/Anthropic/Railway) are present in the environment variables.
3. **Connectivity:** Ensure the scraper has a valid path to the Railway internal URL.
4. **Data State:** Check if the target table exists and is not currently locked by another process.

## Cost-Control Logic
- If a check fails, stop execution immediately and report the specific missing component.
- DO NOT re-run expensive reasoning loops if the underlying data/connection is broken.
- Report "Ready for Execution" only once all checks pass.

---

# Card Analytics Project: Master TODO & Roadmap

# 
- The NHL Player stats scrape failed and why is that in the scrape but not nhl prices? 

## Modular Scraping & Data Collection
- [ ] **[Gate] Pre-Flight:** Verify Selenium environment, driver versions, and proxy rotation configs.
- [ ] **Modular Engine Refactor:** Transition to a single, modular scraper engine.
- [ ] **Config-Driven Scoping:** Templates for General Staples, New Set Releases, and Sport-Specific Selectors.
- [ ] **Scraping Resiliency:** Central error logging, timeout handling, and proxy/rate-limiting.
- [ ] **Image Retrieval:** Modular "Media Fetcher" for photo retrieval via Google vs. eBay.
- [ ] **[AI] Entity Resolution Agent:** Build LangGraph-based agent to map raw titles to 2.6M Beckett records.

## Data Processing & Logic (Backend)
- [ ] **[Gate] Pre-Flight:** Verify `pgvector` extension is active and check DB connection stability.
- [ ] **Raw Cards Focus:** Focus exclusively on building out raw card prices.
- [ ] **Refine Queries:** Adjust sales history querying to tighten price spreads.
- [ ] **Data Versioning (SDLC Type 2 ETL):** Call ETL integration for snapshot dates and versioning.
- [ ] **Manual Delete Logic:** API route for manual delete/override (`ignored = true` flag).
- [ ] **Caching Layer:** Implement Redis/Memcached for total capital and price history graphs.
- [ ] **[AI] Vector Search Layer:** Embed 2.6M records for sub-second "fuzzy" matching.
- [ ] **[AI] Outlier Quarantine:** Flag/quarantine prices deviating >50% from baseline.

## Admin & Health Dashboard (The Command Center)
- [x] **Pipeline Health UI:** Catalog coverage by tier, last scrape per sport, GitHub Actions workflow status cards.
- [x] **Quarantine Manager:** Outlier detection (>5× player median), ignore/restore toggle, hidden from public catalog.
- [x] **Role Management:** Admin can change any user's role (user/admin/guest) inline in user table.
- [x] **Manual Delete/Ignore:** `market_prices.ignored` column, `PATCH /admin/market-prices/{id}/ignore` endpoint.
- [x] **Delta Ingestion Monitor:** Runs tab with KPI strip, workflow health cards, delta + hit-rate charts, anomaly feed, filtered run history table.
- [ ] **AI Matcher Debugger:** Interface to inspect failed entity resolution attempts and manually map IDs.
- [ ] **ETL Snapshot Audit:** View last 5 price snapshots per card for Type 2 integrity review.
- [ ] **Crowdsourced Price Gap Filler:** Allow users to submit missing card prices for cards with no eBay data. Submissions go into a review queue; admin (or AI bot) validates legitimacy before accepting. Fills gaps for obscure/low-volume cards the scraper can't find.

## UI/UX Design (Card Catalog Page)
- [ ] **Layout Alignment:** Match Card Catalog format strictly to the Card Ledger layout.
- [ ] **Image Placement:** Insert card photo between "Card" and "Fair Value" columns.
- [ ] **Price History Graph:** Horizontal line graph between value headers and sidebar.
- [ ] **Graph Defaults:** Default to total capital and price of all cards.
- [ ] **Mobile Graph Responsiveness:** Define mobile-specific layout (sparkline or modal).
- [ ] **Loading States:** Add UI loading skeletons for stability.

## UI/UX Design (New Set Releases Page)
- [x] **Page Architecture:** `/releases` — card grid grouped by set, sport filter, 30/60/90 day window.
- [x] **Top 5 Cards per Set:** Cards ranked by fair value with RC badge shown inline.
- [ ] **Hero Top Card:** Highlight the single highest-value card across all current releases.
- [ ] **Box vs. Singles EV Tracker:** Calculator comparing sealed box price vs. aggregated singles value.
- [ ] **Volatility & Hype Indicators:** Implement 7/14-day momentum using market_price_history delta.
- [ ] **Rarity & Parallel Visualizer:** Visual print run funnel from base cards down to 1/1s.
- [ ] **Individual Sales Drill-Down:** View raw eBay sold listing data per card (not just aggregated fair value).

## Global Layout, Navigation & Security
- [x] **Relocate Navigation (Mobile):** Fixed bottom tab bar with icon + label.
- [x] **Relocate Account Controls:** Compact user row above tab bar on mobile.
- [x] **Settings Placement:** Settings gear in sidebar desktop, tab on mobile.
- [x] **Mobile Overlap Fix:** padding-bottom 120px to clear fixed nav bar.
- [x] **Role-Based Access Control (RBAC):** admin.py uses DB role column; AdminRoute guards /admin; useIsAdmin() hook available.
- [ ] **Lock Manual Delete to Admin:** API route for manual delete/ignore needs admin dependency.

---

# Implementation Roadmap (AI-Optimized & Cost-Efficient)

### Phase 1: Structural UI & Auth Logic (Highest Priority)
1. **[Gate] Pre-Flight:** Agent verifies all DB credentials and Railway secrets.
2. **Layout Overhaul:** Fix Navigation and Account Controls.
3. **RBAC Setup:** Establish Admin tier and secure the future Dashboard route.

### Phase 2: Modular Scraper & AI Foundation
1. **[Gate] Pre-Flight:** Agent verifies config file syntax and DB schema integrity.
2. **Engine Scaffolding:** Create the single scraper class.
3. **AI Foundation:** Deploy FastAPI agent on Railway for price ingestion and `pgvector` initialization.

### Phase 3: The Admin Dashboard & Delta Testing
1. **[Gate] Pre-Flight:** Agent confirms connection to ETL metadata tables and Admin RBAC.
2. **Dashboard Build:** Create the UI for monitoring delta ingestion and AI matching confidence.
3. **Delta Validation:** Run tests to confirm ETL is only pulling incremental changes (SDLC Type 2).

### Phase 4: Data Cleaning & Page Parity
1. **[Gate] Pre-Flight:** Agent verifies vector index count (2.6M records) matches expectations.
2. **Entity Resolution:** Run AI Agent to match new price scrapes to Beckett dataset.
3. **UI Sync:** Align Catalog/Ledger layouts and embed images/graphs.

### Phase 5: New Set Releases Page (The Analytics Engine)
1. **[Gate] Pre-Flight:** Agent confirms Redis cache and ETL snapshots are ready.
2. **Advanced Visuals:** Build EV Tracker, print run funnels, and momentum charts.