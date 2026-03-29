# CardDB — Claude Code Rules

## Core Rules

### Local vs cloud execution
- **Backfill scraping runs on local hardware** — no 6h kill, no GH Actions connection budget conflict, runs overnight uninterrupted. Use local PC for all bulk backfill work (staple/premium/stars/base).
- **Delta scraping (post-backfill) runs via GitHub Actions** — once all tiers are priced, daily delta runs are small and fast enough for GH Actions. Switch after backfill is complete.
- **Infrastructure runs on Railway** (auto-deploys from `main`)
- When running locally, use a `.env` file or export `DATABASE_URL` before executing scripts
- **Connection budget for overnight local runs**: 4 sports × 3 workers = 12 local + up to 80 GH Actions (if hourly workflows still active) + 5 app = 97 peak ✅

### Every change must be documented
When making any change to the project:
1. **Update `CHANGELOG.md`** — add an entry under the current date with what changed and why
2. **Update relevant docs** — if the change affects architecture, update `docs/architecture.md`; if it affects the roadmap, update `README.md`; if it affects scraping schedules, update `memory/MEMORY.md`
3. **Update `TODO.md`** — mark completed items, add new ones that emerge

### Pre-flight before triggering workflows
Before running any `gh workflow run`:
1. Verify the `.github/workflows/<name>.yml` file exists
2. Confirm the script it calls exists at the referenced path
3. Check `gh run list --workflow=<name> --status=in_progress` — don't double-trigger
4. For migrations: confirm all `ALTER TABLE` statements use `IF NOT EXISTS`

### Migration rules
- All migrations live in `migrations/`
- All migrations must be **idempotent** (`IF NOT EXISTS`, try/except)
- Never put slow/blocking operations (large UPDATEs, index builds on huge tables) in a migration that runs at Railway deploy time — move those to a separate GH Actions workflow
- Migrations run on every Railway deploy via `Dockerfile` CMD

### File organization
```
scraping/       — all scraper scripts
migrations/     — all migrate_*.py files
diagnostics/    — debug and quality scripts
scripts/        — maintenance utilities
api/            — FastAPI app
frontend/       — React app
db.py           — shared DB connection (root)
dashboard_utils.py — shared utilities (root)
```

### Query performance rules
- Never run `COUNT(*)` or `COUNT(DISTINCT ...)` on tables with millions of rows in scheduled workflows — use `pg_class` estimates instead
- Never do a JOIN between `market_prices` and `card_catalog` in a time-sensitive query — use denormalized `sport`/`scrape_tier`/`year` columns on `market_prices` instead
- Always test new DB queries with a timeout before scheduling them

### Database connection budget — HARD LIMIT
Railway PostgreSQL max_connections = **100**. Never exceed this or the DB kills all connections and the site goes 502.

**Allocation:**
| Consumer | Pool max | Notes |
|---|---|---|
| Railway app (FastAPI) | 5 | `db.py` ThreadedConnectionPool max |
| Railway dashboard / monitoring | 5 | reserved |
| GH Actions scrapers | ≤ 80 | `max-parallel × pool-max` |

**Formula: `max-parallel × pool-max ≤ 80`**

Current settings (base scrape): `max-parallel: 4` × `pool-max: 5` × `2 overlapping runs` = **40 connections** ✅

**Rules:**
- `db.py` pool max is **5** — never raise it without recalculating the budget
- `--workers N` controls Selenium threads only — workers never touch the DB pool. Only the main thread uses DB (1 connection at a time during `_flush_batch`). Safe to run `--workers 10` locally.
- For GH Actions: `max-parallel × pool-max ≤ 80` still applies (each GH Actions job holds its full pool open)
- For local runs: budget is `processes × 2` (1 active + 1 idle per process) — far below 100
- Use `run_tier.py` for local runs — it reads `tier_config.json` and launches the right subprocesses
- Never run two parallel scrape workflows at the same time on GH Actions — they share the same connection budget
- Never query `market_raw_sales` with a `GROUP BY card_catalog_id` or similar full-scan inside the catalog load path — it blocks all 24 shards simultaneously
- **Never set `--stale-days` above 60 for any tier** — eBay sold listings expire after 90 days. 60 days gives a 30-day safety buffer. Missing a rescrape window = permanent data loss.

### GitHub Actions limits
- Scheduled jobs have a **6-hour hard kill** — always pass `--max-hours 5.75` to scrapers
- **Never use `--max-hours 0` in any GH Actions workflow file** — `0` means no limit and the job will be killed mid-run at 6h with no clean shutdown. Local `run_tier.py` uses `--max-hours 0` intentionally; GH Actions must always use `--max-hours 5.75`.
- Job `timeout-minutes` should be set conservatively based on expected runtime
- Email/notify jobs should complete in <5 minutes

---

## Backfill Timeline (as of 2026-03-23)

First clean run: **Mar 23, 2026** (Mar 22 lost to DB crashes and debug runs)

| Milestone | Target date | Cards needed | Status |
|---|---|---|---|
| 25% base priced | ~Mar 24 | 385,882 | in progress |
| 50% base priced | ~Mar 26 | 771,765 | — |
| 75% base priced | ~Mar 28 | 1,157,647 | — |
| 100% base priced | ~Mar 30 | 1,543,529 | — |

**Base tier target:** NFL 479,793 · NBA 298,550 · MLB 765,186 (2015+)
**Rate:** 270,000 cards/day target (24 shards × 4 runs) · ETA ~Mar 28–30, 2026

---

## Post-Backfill Checklist (~Apr 30)
- [ ] Re-enable per-sport progress bars in email (backfill_market_prices_sport.yml must be done)
- [ ] Consolidate tier workflows into one unified daily job
- [ ] Tighten stale-days: premium 7→3, stars 30→7
- [ ] Switch progress notify to monthly-only
- [ ] NHL full sweep (drop year filter from 2015 to 2010)
