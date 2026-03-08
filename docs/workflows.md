# CardDB — GitHub Actions Workflows

All scraping and CI runs on GitHub Actions. No local compute — the local machine is for code editing and git push only.

---

## Overview

| Workflow | File | Schedule | Purpose |
|---|---|---|---|
| Catalog Staple | `catalog_tier_staple.yml` | Daily 6am UTC | Raw prices for staple-tier cards |
| Catalog Premium | `catalog_tier_premium.yml` | Monday 10am UTC | Raw prices for premium-tier cards |
| Catalog Stars | `catalog_tier_stars.yml` | 1st of month | Raw prices for stars-tier cards |
| Catalog Base | `catalog_tier_base.yml` | Wednesday 6am UTC | Raw prices for base-tier 2010+ cards |
| Catalog Graded | `catalog_tier_graded.yml` | Sunday 6am UTC | PSA/BGS prices for all staple cards (≥$5) |
| Master DB Daily | `master_db_daily.yml` | Daily 1am EST | 4 sports × 1K cards, stale-days 7 |
| Master DB Weekly | `master_db_weekly.yml` | Sunday 2am EST | Full rookie sweep, stale-days 30 |
| Ledger Scrape | `daily_scrape.yml` | On demand | Personal ledger cards (trigger via UI) |
| Set Info Scrape | `scrape_set_info.yml` | 1st of month 6am UTC | Sealed product MSRP + pack config |
| Catalog Update | `catalog_update.yml` | Periodic / manual | Populate card_catalog from TCDB/CLI/CBC |
| Catalog Quality | `catalog_quality_report.yml` | Monday 10am UTC | pytest + gap analysis → Step Summary |
| Fix Sealed Sport | `fix_sealed_sport.yml` | Manual | One-time: delete sport-mismatched sealed rows |
| Migrate Users | `migrate_users.yml` | Manual | One-time DB migrations |
| Migrate Graded | `migrate_graded_data.yml` | Manual | Run migrate_add_graded_data.py |

---

## Catalog Tier Workflows

### `catalog_tier_staple.yml` — Catalog Staple (Daily)

Scrapes raw eBay prices for all `catalog_tier = 'staple'` cards.

```yaml
schedule: '0 6 * * *'   # 1am EST daily
matrix: [NHL, NBA, NFL, MLB]  # 4 parallel jobs
timeout: 300 minutes
```

Command:
```bash
python -u scrape_master_db.py \
  --sport ${{ matrix.sport }} \
  --catalog-tier staple \
  --stale-days 7 \
  --workers 3
```

4 parallel jobs (one per sport) each running up to 5 hours.

---

### `catalog_tier_premium.yml` — Catalog Premium (Weekly)

```yaml
schedule: '0 2 * * 0'   # Sunday 2am UTC
matrix: [NHL, NBA, NFL, MLB]
```

Command:
```bash
python -u scrape_master_db.py \
  --sport ${{ matrix.sport }} \
  --catalog-tier premium \
  --stale-days 30 \
  --workers 3
```

---

### `catalog_tier_stars.yml` — Catalog Stars (Weekly)

```yaml
schedule: '0 3 * * 0'   # Sunday 3am UTC
matrix: [NHL, NBA, NFL, MLB]
```

Same structure as premium, `--catalog-tier stars`.

---

### `catalog_tier_graded.yml` — Catalog Graded Prices (Sunday)

Seeds `market_prices.graded_data` with PSA/BGS prices for all staple-tier cards with `fair_value >= 5.00`.

```yaml
schedule: '0 6 * * 0'   # Sunday 6am UTC (after staple raw run)
matrix: [NHL, NBA, NFL, MLB]
timeout: 300 minutes
```

Command:
```bash
python -u scrape_master_db.py \
  --sport ${{ matrix.sport }} \
  --catalog-tier staple \
  --graded \
  --min-raw-value ${{ github.event.inputs.min_raw_value || '5.0' }} \
  --workers 3
```

**workflow_dispatch inputs:**
- `sport` — override to scrape one sport only
- `min_raw_value` — minimum raw fair value to qualify for graded scrape (default 5.0)

---

## Master DB Workflows

### `master_db_daily.yml` — Master DB Daily

Broad daily sweep of catalog cards (not tier-filtered).

```yaml
schedule: '0 6 * * *'   # 1am EST daily
matrix: [NHL, NBA, NFL, MLB]
```

Command:
```bash
python -u scrape_master_db.py \
  --sport ${{ matrix.sport }} \
  --stale-days 7 \
  --limit 2000 \
  --workers 3
```

---

### `master_db_weekly.yml` — Master DB Weekly

Full rookie sweep with longer stale window.

```yaml
schedule: '0 7 * * 0'   # 2am EST Sunday
matrix: [NHL, NBA, NFL, MLB]
```

Command:
```bash
python -u scrape_master_db.py \
  --sport ${{ matrix.sport }} \
  --rookies \
  --stale-days 30 \
  --workers 3
```

---

## Ledger Scrape

### `daily_scrape.yml` — Ledger Card Scrape

Scrapes personal ledger cards. Primarily triggered on-demand from the frontend "Rescrape All" button.

```yaml
on:
  workflow_dispatch:    # UI trigger via POST /api/stats/trigger-scrape
  schedule: ...         # optional scheduled run
```

Command:
```bash
python -u daily_scrape.py --workers 3
```

The frontend polls `GET /api/stats/scrape-status` every 15s while this is running and shows progress in `ScrapeProgressModal`.

---

## CI / Quality

### `catalog_quality_report.yml` — Catalog Quality

```yaml
schedule: '0 10 * * 1'  # Monday 10am UTC
```

Steps:
1. `pytest tests/test_catalog_quality.py` — 23 assertions on catalog data integrity
2. `python catalog_gap_analysis.py --markdown` — gap analysis report
3. Publish results to `$GITHUB_STEP_SUMMARY`
4. Upload `test_report.md` + `gap_report.md` as artifacts (90-day retention)

---

## Migration Workflows

### `migrate_graded_data.yml`

Manual only (`workflow_dispatch`). Runs `migrate_add_graded_data.py` against the production DB.

```yaml
on: workflow_dispatch
```

Steps: checkout → python 3.11 → `pip install psycopg2-binary` → `python migrate_add_graded_data.py`

**Note:** This migration also runs automatically on every Railway deploy (Dockerfile CMD). The workflow is a manual fallback.

---

## Required Secrets

All workflows that touch the database or external services need these secrets set in GitHub → Settings → Secrets and Variables → Actions:

| Secret | Used by | Description |
|---|---|---|
| `DATABASE_URL` | All scrape workflows | Railway PostgreSQL connection string |
| `GH_PAT` | Catalog tier workflows | Personal Access Token for `GITHUB_TOKEN` env var in scraper (classic PAT, `repo` + `workflow` scopes) |

**Note:** `GITHUB_TOKEN` in workflow files uses the auto-generated token. `GH_PAT` (the `secrets.GH_PAT` secret) is the custom PAT for scraper scripts that need to trigger other workflows via the GitHub API.

---

## Chrome Installation (All Scrape Workflows)

Every scrape workflow installs Chrome fresh on the Ubuntu runner:

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

## Triggering Workflows Manually

Via GitHub CLI (`gh`):
```bash
gh workflow run catalog_tier_staple.yml
gh workflow run catalog_tier_graded.yml -f sport=NHL -f min_raw_value=10.0
gh workflow run master_db_daily.yml
```

Via GitHub API (what the frontend does):
```bash
curl -X POST \
  https://api.github.com/repos/glasala98/cardDB/actions/workflows/daily_scrape.yml/dispatches \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -d '{"ref":"main"}'
```

---

## Monitoring

The **Admin → Pipeline** tab shows live scrape health for all tracked workflows. Powered by:
- `GET /api/stats/workflow-status` — queries GitHub API concurrently for latest run status
- `GET /admin/scrape-runs` — queries `scrape_runs` table for DB-level progress

**Active job cards** show:
- Progress bar: `cards_processed / cards_total` (updated every 50 cards mid-run)
- Hit rate: `cards_found / cards_processed` (updated mid-run)
- Throughput: cards/hr + ETA
- Elapsed time

**Workflow health cards** show:
- Last run status and timestamp
- Consecutive failure count (red badge)
- Overdue badge if last run is older than the expected cadence
- ▶ Run button to trigger manually

**Anomaly flags** on completed runs:
- `timed_out` — run was killed before finishing (GitHub 6h limit or `--max-hours`)
- `zero_delta` — ran but found no price changes
- `low_hit_rate` — fewer than 10% of cards returned results
- `high_errors` — more than 10 scrape errors

Each scraper enforces `--max-hours 5.75` to exit gracefully before GitHub's 6h kill. Orphaned `running` rows (>1h old, same workflow+sport) are automatically marked `timed_out` when the next run starts.
