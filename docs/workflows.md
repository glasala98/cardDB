# CardDB — GitHub Actions Workflows

All scraping and CI runs on GitHub Actions. No local compute — the local machine is for code editing and `git push` only.

---

## Overview Table

| Workflow file | Schedule | Purpose |
|---|---|---|
| `catalog_tier_base.yml` | Daily 6am UTC | Base prices 2010+, all 4 sports parallel, backfill |
| `catalog_tier_staple.yml` | Daily 8am UTC | Staple prices, all 4 sports parallel |
| `catalog_tier_premium.yml` | Daily 10am UTC (temp elevated) | Premium prices, all 4 sports parallel |
| `catalog_tier_stars.yml` | Daily noon UTC (temp elevated) | Stars prices, all 4 sports parallel |
| `catalog_tier_graded.yml` | Sunday 6am UTC | PSA/BGS graded prices for staple cards ≥$5 |
| `master_db_daily.yml` | Daily 6am UTC (1am EST) | 4 sports × 1,000 cards, stale-days 7 |
| `master_db_weekly.yml` | Sunday 2am EST | Full rookie sweep, stale-days 30 |
| `daily_scrape.yml` | On demand (UI trigger) | Personal ledger card scrape |
| `scrape_set_info.yml` | 1st of month 6am UTC | Sealed product MSRP + pack config |
| `catalog_update.yml` | Manual | Populate card_catalog from TCDB/CLI/CBC |
| `catalog_quality_report.yml` | Monday 10am UTC | pytest + gap analysis → GitHub Step Summary |
| `backfill_raw_sales.yml` | Manual | Backfill market_raw_sales per tier |
| `backfill_all_tiers.yml` | Daily 1:21pm UTC | Sequential staple/premium/stars/base raw sales backfill |
| `db_health_check.yml` | Daily 5am UTC | DB disk usage check, top tables by size |
| `coverage_notify.yml` | Daily noon UTC | Email when price coverage crosses 10% milestone |
| `quarantine_outliers.yml` | Nightly | Flag statistical price outliers in market_prices |
| `sales_quality_check.yml` | Periodic | Spot check raw sales data quality |
| `diag_*.yml` | Manual | Diagnostic and debug workflows |
| `migrate_*.yml` | Manual | One-time DB migrations |
| `scrape_fanatics.yml` | Manual | Fanatics auction house scraper |
| `scrape_goldin.yml` | Manual | Goldin auction house scraper |
| `scrape_heritage.yml` | Manual | Heritage auction house scraper |
| `scrape_myslabs.yml` | Manual | MySlabs auction house scraper |
| `scrape_pristine.yml` | Manual | Pristine auction house scraper |
| `scrape_pwcc.yml` | Manual | PWCC auction house scraper |
| `tests.yml` | On push | pytest unit tests |

---

## Catalog Tier Workflows

All four catalog tier workflows follow the same pattern: 4 parallel matrix jobs (one per sport), each running `scrape_master_db.py` with the appropriate `--catalog-tier` flag. Each job runs a preflight DB check before scraping.

### `catalog_tier_base.yml` — Base Tier (Daily)

Scrapes raw eBay prices for all `catalog_tier = 'base'` cards from 2010 onward. This is the largest tier (~800K cards) and is currently in active backfill. ~8.5% priced as of 2026-03.

```yaml
schedule: '0 6 * * *'   # 6am UTC daily
matrix: [NHL, NBA, NFL, MLB]
timeout: 360 minutes
email notifications: on start, on cancel
```

Key args:
```bash
python -u scrape_master_db.py \
  --sport ${{ matrix.sport }} \
  --catalog-tier base \
  --stale-days 30 \
  --workers 3 \
  --max-hours 5.75 \
  --year-min 2010
```

Notes:
- `--max-hours 5.75` ensures graceful exit before GitHub's 6h runner kill
- Email notifications via dawidd6/action-send-mail@v3 on job start and cancellation
- preflight_db_check.py runs first: `--warn-gb 60 --fail-gb 70`

---

### `catalog_tier_staple.yml` — Staple Tier (Daily)

Scrapes raw eBay prices for all `catalog_tier = 'staple'` cards. These are the highest-value, most frequently traded cards (YG, Prizm RC, Chrome RC, SP Authentic).

```yaml
schedule: '0 8 * * *'   # 8am UTC daily
matrix: [NHL, NBA, NFL, MLB]
timeout: 300 minutes
```

Key args:
```bash
python -u scrape_master_db.py \
  --sport ${{ matrix.sport }} \
  --catalog-tier staple \
  --stale-days 1 \
  --workers 3 \
  --max-hours 5.75
```

Notes:
- `--stale-days 1` means every staple card gets re-scraped daily
- Runs after the base tier at 8am to avoid resource contention

---

### `catalog_tier_premium.yml` — Premium Tier (Daily, temporarily elevated)

Scrapes raw eBay prices for `catalog_tier = 'premium'` cards (autos, patches, serials, relics). Normally weekly; temporarily set to daily during backfill.

```yaml
schedule: '0 10 * * *'   # 10am UTC daily (was: Monday only)
matrix: [NHL, NBA, NFL, MLB]
timeout: 300 minutes
```

Key args:
```bash
python -u scrape_master_db.py \
  --sport ${{ matrix.sport }} \
  --catalog-tier premium \
  --stale-days 7 \
  --workers 3 \
  --max-hours 5.75
```

---

### `catalog_tier_stars.yml` — Stars Tier (Daily, temporarily elevated)

Scrapes raw eBay prices for `catalog_tier = 'stars'` cards (major-brand rookies). Normally Wednesday; temporarily set to daily during backfill.

```yaml
schedule: '0 12 * * *'   # noon UTC daily (was: Wednesday only)
matrix: [NHL, NBA, NFL, MLB]
timeout: 300 minutes
```

Key args:
```bash
python -u scrape_master_db.py \
  --sport ${{ matrix.sport }} \
  --catalog-tier stars \
  --stale-days 30 \
  --workers 3 \
  --max-hours 5.75
```

---

### `catalog_tier_graded.yml` — Graded Prices (Sunday)

Seeds `market_prices.graded_data` JSONB with PSA/BGS prices for all staple-tier cards with `fair_value >= 5.00`. Runs Sunday after the staple raw run completes.

```yaml
schedule: '0 6 * * 0'   # Sunday 6am UTC
matrix: [NHL, NBA, NFL, MLB]
timeout: 300 minutes
```

Key args:
```bash
python -u scrape_master_db.py \
  --sport ${{ matrix.sport }} \
  --catalog-tier staple \
  --graded \
  --min-raw-value ${{ github.event.inputs.min_raw_value || '5.0' }} \
  --workers 3 \
  --max-hours 5.75
```

**workflow_dispatch inputs:**
- `sport` — override to scrape one sport only (default: all 4)
- `min_raw_value` — minimum raw fair value to qualify for graded scrape (default: 5.0)

---

## Master DB Workflows

### `master_db_daily.yml` — Master DB Daily

Broad daily sweep of catalog cards not filtered by tier. Targets cards stale for ≥7 days across all sports.

```yaml
schedule: '0 6 * * *'   # 6am UTC (1am EST) daily
matrix: [NHL, NBA, NFL, MLB]
timeout: 300 minutes
email notifications: on start, on cancel
```

Key args:
```bash
python -u scrape_master_db.py \
  --sport ${{ matrix.sport }} \
  --stale-days 7 \
  --limit 1000 \
  --workers 3 \
  --max-hours 5.75
```

---

### `master_db_weekly.yml` — Master DB Weekly

Full rookie sweep targeting the `rookie_cards` table with a wider stale window.

```yaml
schedule: '0 7 * * 0'   # Sunday 7am UTC (2am EST)
matrix: [NHL, NBA, NFL, MLB]
timeout: 300 minutes
```

Key args:
```bash
python -u scrape_master_db.py \
  --sport ${{ matrix.sport }} \
  --rookies \
  --stale-days 30 \
  --workers 3 \
  --max-hours 5.75
```

---

## Ledger and Personal Scrape

### `daily_scrape.yml` — Ledger Card Scrape

Scrapes all cards in the personal ledger (`cards` table). Primarily triggered on-demand from the admin UI "Rescrape All" button.

```yaml
on:
  workflow_dispatch:    # Triggered via POST /api/stats/trigger-scrape
  schedule: (optional)
```

Key args:
```bash
python -u daily_scrape.py --workers 3
```

Notes:
- Frontend polls `GET /api/stats/scrape-status` every 15s and shows progress in `ScrapeProgressModal`
- Requires `GH_PAT` secret for the frontend to trigger via GitHub API

---

## Backfill Workflows

### `backfill_raw_sales.yml` — Backfill Raw Sales (Manual)

Manually triggered backfill to populate `market_raw_sales` from historical scrapes. Accepts a tier input to target a specific tier.

```yaml
on: workflow_dispatch
inputs:
  tier: staple | premium | stars | base
```

---

### `backfill_all_tiers.yml` — Backfill All Tiers (Daily)

Runs all four tier backfills sequentially in one job. Scheduled daily at 1:21pm UTC to fill `market_raw_sales` from any historical price data that predates the raw sales table.

```yaml
schedule: '21 13 * * *'   # 1:21pm UTC daily
timeout: 360 minutes
```

Runs staple → premium → stars → base in sequence.

---

## Maintenance and Monitoring Workflows

### `db_health_check.yml` — DB Health Check (Daily)

Checks Railway PostgreSQL disk usage. Outputs top tables by size to GitHub Step Summary.

```yaml
schedule: '0 5 * * *'   # 5am UTC daily
```

Key command:
```bash
python preflight_db_check.py --warn-gb 60 --fail-gb 70 --report
```

Fails the workflow (and sends an alert) if DB usage exceeds 70GB.

---

### `coverage_notify.yml` — Coverage Milestone Notify (Daily)

Checks current price coverage percentage for base-tier cards. Sends an email notification when coverage crosses a 10% milestone (10%, 20%, 30%, ...).

```yaml
schedule: '0 12 * * *'   # noon UTC daily
```

Email sent via dawidd6/action-send-mail@v3 using `NOTIFY_GMAIL_USER` + `NOTIFY_GMAIL_APP_PASSWORD` secrets.

---

### `quarantine_outliers.yml` — Quarantine Outliers (Nightly)

Runs `quarantine_outliers.py` to flag prices that deviate more than 5× from the player's median value. Flagged cards are marked in `market_prices` and reviewable in the Admin → Outliers tab.

```yaml
schedule: nightly
```

---

### `sales_quality_check.yml` — Sales Quality Check (Periodic)

Spot-checks `market_raw_sales` for data quality issues: suspiciously high/low prices, duplicate titles, unusually short titles.

---

### `catalog_quality_report.yml` — Catalog Quality Report (Monday)

Runs quality checks and gap analysis on the catalog. Publishes results to GitHub Step Summary and uploads artifacts.

```yaml
schedule: '0 10 * * 1'   # Monday 10am UTC
```

Steps:
1. `pytest tests/test_catalog_quality.py` — 23 assertions on catalog data integrity
2. `python catalog_gap_analysis.py --markdown` — gap analysis by sport/year/set
3. Publish to `$GITHUB_STEP_SUMMARY`
4. Upload `test_report.md` + `gap_report.md` as artifacts (90-day retention)

---

## Catalog and Sealed Product Workflows

### `catalog_update.yml` — Catalog Update (Manual)

Populates or updates `card_catalog` from TCDB, CLI, or CBC sources. Run manually when new sets are released.

```yaml
on: workflow_dispatch
inputs:
  source: tcdb | cli | cbc
  sport: NHL | NBA | NFL | MLB
  year: (year string)
```

---

### `scrape_set_info.yml` — Sealed Product Info (Monthly)

Scrapes cardboardconnection.com for sealed product data: MSRP, box price, pack configuration, release date, and pack odds.

```yaml
schedule: '0 6 1 * *'   # 1st of month 6am UTC
on: workflow_dispatch
inputs:
  sport: NHL | NBA | NFL | MLB | all
  year_min: (min year, default 2022)
```

Key command:
```bash
python -u scrape_set_info.py --sport ${{ inputs.sport }} --year-min ${{ inputs.year_min }}
```

---

## CI Workflow

### `tests.yml` — Unit Tests (On Push)

Runs the pytest test suite on every push to any branch.

```yaml
on: push
```

Steps: checkout → Python 3.11 → `pip install -r requirements.txt` → `pytest tests/`

---

## Migration Workflows

All migration workflows are `workflow_dispatch` only (manual trigger). They run idempotent migration scripts against production DB.

| Workflow | Script |
|---|---|
| `migrate_graded_data.yml` | `migrate_add_graded_data.py` |
| Other `migrate_*.yml` | Corresponding `migrate_*.py` scripts |

Note: Core migrations (`migrate_add_graded_data.py`, `migrate_add_cards_processed.py`) also run automatically on every Railway deploy. Migration workflows are manual fallbacks.

---

## Diagnostic Workflows

`diag_*.yml` workflows are manual-only debug tools. Examples:
- Check DB connection and pool state
- Inspect specific card scrape results
- Test variant filter against live eBay results
- Verify Chrome installation on runner

---

## Auction House Scrapers

All manual (`workflow_dispatch`). Scrape sold results from major auction houses.

| Workflow | Source |
|---|---|
| `scrape_fanatics.yml` | Fanatics Auctions |
| `scrape_goldin.yml` | Goldin Auctions |
| `scrape_heritage.yml` | Heritage Auctions |
| `scrape_myslabs.yml` | MySlabs |
| `scrape_pristine.yml` | Pristine Auction |
| `scrape_pwcc.yml` | PWCC Marketplace |

---

## Required Secrets

Set in GitHub → Settings → Secrets and Variables → Actions:

| Secret | Required by | Description |
|---|---|---|
| `DATABASE_URL` | All scrape + migration workflows | Railway PostgreSQL connection string |
| `GH_PAT` | Catalog tier workflows, daily_scrape.yml | Classic PAT with `repo` + `workflow` scopes. Used by scraper scripts that trigger other workflows via GitHub API. |
| `NOTIFY_EMAIL_TO` | coverage_notify.yml, master_db_daily.yml, catalog_tier_base.yml | Recipient email address for notifications |
| `NOTIFY_GMAIL_USER` | Same as above | Gmail sender address |
| `NOTIFY_GMAIL_APP_PASSWORD` | Same as above | Gmail App Password (not account password) |

Note: `GITHUB_TOKEN` in workflow files is the auto-generated token. `GH_PAT` is the custom PAT for scripts that need to trigger other workflows programmatically.

---

## Chrome Installation (All Scrape Workflows)

Every scrape workflow installs Chrome fresh on the Ubuntu runner before scraping:

```yaml
- name: Install Chrome
  run: |
    wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
    sudo sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" \
      >> /etc/apt/sources.list.d/google-chrome.list'
    sudo apt-get update -q
    sudo apt-get install -y google-chrome-stable
```

`scrape_card_prices.py` detects whether `webdriver_manager` is available and falls back to system Chrome if not.

---

## Monitoring

The **Admin → Pipeline** tab shows live scrape health for all tracked workflows. Powered by:
- `GET /api/stats/workflow-status` — queries GitHub API concurrently for latest run per workflow
- `GET /admin/scrape-runs` — queries `scrape_runs` table for DB-level progress

**Active job cards** show:
- Progress bar: `cards_processed / cards_total` (updated every 50 cards mid-run)
- Hit rate: `cards_found / cards_processed`
- Throughput: cards/hr + ETA
- Elapsed time

**Workflow health cards** show:
- Last run status and timestamp
- Consecutive failure count (red badge)
- Overdue badge if last run is older than the expected cadence
- Run button to trigger manually

**Anomaly flags** on completed runs:
- `timed_out` — run was killed before finishing
- `zero_delta` — ran but found no price changes
- `low_hit_rate` — fewer than 10% of cards returned results
- `high_errors` — more than 10 scrape errors

Orphaned `running` rows (>7h old) are automatically marked `timed_out` when the next run of the same workflow+sport starts.

---

## Triggering Workflows Manually

Via GitHub CLI:
```bash
gh workflow run catalog_tier_staple.yml
gh workflow run catalog_tier_graded.yml -f sport=NHL -f min_raw_value=10.0
gh workflow run master_db_daily.yml
gh workflow run scrape_set_info.yml -f sport=NHL -f year_min=2022
gh workflow run backfill_raw_sales.yml -f tier=staple
```

Via GitHub API (what the frontend does for the ledger scrape):
```bash
curl -X POST \
  https://api.github.com/repos/glasala98/cardDB/actions/workflows/daily_scrape.yml/dispatches \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -d '{"ref":"main"}'
```

---

## Post-Backfill Workflow Simplification

Once the base-tier backfill reaches 100% coverage (estimated ~4-6 weeks from 2026-03), the workflow landscape simplifies significantly:

**What changes:**
- All tier workflows switch from "fill everything" to pure delta mode (`--stale-days` only)
- Daily run times drop from ~5.75 hours to ~10 minutes per sport per tier
- `backfill_all_tiers.yml` can be disabled or set to weekly
- premium and stars tiers can return to less frequent schedules (weekly/monthly)
- Potential consolidation: all four tier workflows merge into one unified daily workflow

**What stays the same:**
- Staple stays daily (high-value cards need fresh prices)
- Graded run stays Sunday
- Master DB daily and weekly sweeps continue unchanged
- All monitoring, notifications, and preflight checks remain
