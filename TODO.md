# CardDB — Active TODO

> Full product roadmap is in `docs/architecture.md` and `README.md`.
> This file tracks specific in-flight engineering tasks only.

---

## Active

| Item | Notes |
|---|---|
| **Base-tier backfill** | NFL/NBA/MLB 2015+ in progress. ~135K/day target, ETA ~Apr 15. Progress email fires daily at noon + on milestone cross |
| **market_raw_sales backfill** | `backfill_all_tiers.yml` running daily — capturing full eBay history |

---

## P1 — Do Next

### Data / Infra
- [ ] **Offsite DB backups** — weekly `pg_dump` to Cloudflare R2 via GitHub Actions; test restore before it counts ⚠️ highest priority — 1.7M raw sales rows can't be re-scraped
- [ ] **Connection retry resilience** — `assign_catalog_tiers.py` + `scrape_nhl_stats.py` crash on `server closed the connection unexpectedly`; add reconnect in `db.py`
- [ ] **eBay affiliate links** — add Partner Network tracking IDs to existing listing links (zero extra scraping)

### Frontend / UX
- [ ] **Mobile catalog layout** — card catalog needs responsive column collapse; live but broken on mobile
- [ ] **Google AdSense** — integrate on public pages (`/catalog`, `/trending`, `/releases`, `/sets`)
- [ ] **Portfolio value over time chart** — data exists in `portfolio_history`, needs the line chart on `/charts`

---

## P2 — Soon

### AI
- [ ] **Market Digest** — weekly GH Actions cron → Claude summary of biggest price movers → store in DB + email
- [ ] **Price alerts** — email when tracked card moves >10% in 7 days; uses `market_price_history` + existing email infra
- [ ] **Deal Finder** — `POST /api/ai/deal-finder` — surfaces cards with high grading upside at current raw prices

### Frontend / UX
- [ ] **SEO card pages** — prerender or SSR `/catalog/:id` pages so Google indexes individual card prices
- [ ] **Sell tracking** — record sale price + date per collection card; auto-calculate realized gain/loss
- [ ] **Guest → signup conversion** — clear CTAs when guests hit auth walls

### Data / Backend
- [ ] **Raw sales analytics API** — expose `market_raw_sales` in endpoints: per-card volume, price trend (1.7M+ rows underutilised)
- [ ] **Sealed products public page** — data ready in `sealed_products` + `sealed_product_odds`; needs a public page
- [ ] **master_db_daily sport filter** — when triggered with `sport=NHL`, NBA/NFL/MLB jobs queue as skipped; should not start

---

## P3 — Medium-term

- [ ] **Multi-source pricing** — PWCC, Goldin, Heritage, Whatnot, COMC sold data alongside eBay (see `docs/architecture.md`)
- [ ] **Public API v1** — `GET /api/v1/cards/{id}/price` + `/history`, API key auth, free + paid tiers
- [ ] **Natural language portfolio queries** — Claude answers "what's my best performing card this month?" from user's data
- [ ] **Vector search** — pgvector for fuzzy card matching (verify Railway supports it before starting)
- [ ] **Caching layer** — Redis for expensive aggregates: portfolio total, releases set grid, catalog count

---

## Post-Backfill (do when base tier hits ~100%, ~Apr 15)

- [ ] Consolidate tier workflows — merge staple/premium/stars/base into one unified daily job
- [ ] Tighten stale-days — premium 7→3 days, stars 30→7 days for fresher prices
- [ ] Return premium/stars to weekly schedule; base stays daily at stale-days 30
- [ ] Disable/throttle `backfill_all_tiers.yml` — weekly once raw sales fully populated
- [ ] Switch progress notify to monthly-only after backfill complete
- [ ] NHL base tier full sweep — drop year filter from 2015 to 2010, run full pass
