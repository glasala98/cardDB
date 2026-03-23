# CardDB — Claude Code Rules

## Core Rules

### No local compute
This is a **cloud-only** project. The local machine is for **code editing and git push only**.
- Never run `python ...`, `node ...`, or any data/scraping commands locally
- All script execution runs via **GitHub Actions** (`gh workflow run`)
- All infrastructure runs on **Railway** (auto-deploys from `main`)

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

### GitHub Actions limits
- Scheduled jobs have a **6-hour hard kill** — always pass `--max-hours 5.75` to scrapers
- Job `timeout-minutes` should be set conservatively based on expected runtime
- Email/notify jobs should complete in <5 minutes

---

## Backfill Timeline (as of 2026-03-23)

| Milestone | Target date | Cards needed | Status |
|---|---|---|---|
| 25% base priced | ~Mar 31 | 385,882 | in progress |
| 50% base priced | ~Apr 10 | 771,765 | — |
| 75% base priced | ~Apr 20 | 1,157,647 | — |
| 100% base priced | ~Apr 30 | 1,543,529 | — |

**Base tier target:** NFL 479,793 · NBA 298,550 · MLB 765,186 (2015+)
**Rate:** 135,000 cards/day target · ETA ~Apr 30, 2026

---

## Post-Backfill Checklist (~Apr 30)
- [ ] Re-enable per-sport progress bars in email (backfill_market_prices_sport.yml must be done)
- [ ] Consolidate tier workflows into one unified daily job
- [ ] Tighten stale-days: premium 7→3, stars 30→7
- [ ] Switch progress notify to monthly-only
- [ ] NHL full sweep (drop year filter from 2015 to 2010)
