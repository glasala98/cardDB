# Scraper Scripts — Reference

Four Python scripts handle all data collection. They are run via GitHub Actions (daily automated), manually from the command line, or triggered via the API's "Rescrape All" button.

---

## scrape_card_prices.py — eBay Scraping Engine

The core scraping library. Not run directly — imported by `daily_scrape.py`, `scrape_master_db.py`, and the FastAPI `cards` router.

### How it works

Each card goes through a **4-stage search strategy**:

| Stage | Query type | Confidence |
|-------|-----------|-----------|
| 1 | Exact: player + card# + parallel/subset + serial + year + brand | `high` |
| 2 | Set: player + card# + year + set name (no parallel) | `medium` |
| 3 | Broad: player + card# + serial + year only | `low` |
| 4 | Serial comps: find nearby serials, adjust price by multiplier | `estimated` |

If no sales are found at any stage, confidence is `none` and `estimated_value` is `DEFAULT_PRICE` ($5.00).

### Key Functions

```python
process_card(card_name: str) -> tuple[str, dict]
```
Main entry point. Runs the 4-stage search and returns `(card_name, result_dict)`.

Result dict keys: `estimated_value`, `confidence`, `stats` (median, trend, num_sales, min, max, top_3_prices), `raw_sales` (list), `search_url`, `image_url`.

---

```python
search_ebay_sold(
    driver: WebDriver,
    card_name: str,
    max_results: int = 240,
    search_query: str = None
) -> list[dict]
```
Scrapes eBay sold listings using Selenium. Returns a list of sale dicts with: `title`, `price_val`, `shipping`, `sold_date`, `days_ago`, `listing_url`, `image_url`.

For graded cards, filters listings to only include the exact grade (rejects mismatched grades and mixed-grade lots).

---

```python
calculate_fair_price(
    sales: list,
    target_serial: int = None
) -> tuple[float, dict]
```
Calculates a representative fair market value from raw sales data. Algorithm:
1. Remove outliers (prices > 3× or < 1/3 of median)
2. Sort by recency
3. Pick the median of the top 3 most recent sales
4. Determine trend: `up` / `down` / `stable` based on last 3 vs previous 3

Returns `(fair_price, stats_dict)` where stats has: `fair_price`, `trend`, `top_3_prices`, `median_all`, `num_sales`, `outliers_removed`, `min`, `max`.

---

```python
serial_multiplier(from_serial: int, to_serial: int) -> float
```
Price adjustment multiplier between two print runs. Used in stage 4 (serial comps). Based on the `SERIAL_VALUE` table which maps common print runs (1, 5, 10, 25, 50, 99, 199, 249, 499, 999) to relative values.

Example: a `/10` card found with no sales can be estimated from a `/99` result with multiplier `~5.9×`.

---

```python
clean_card_name_for_search(card_name: str) -> str
```
Builds a focused eBay search query from a card name. Strips 250+ known variant name strings (e.g., "Red Prism", "Cracked Ice") to avoid false matches, but keeps grade terms when the card is graded.

---

```python
create_driver() -> WebDriver
def get_driver() -> WebDriver
```
`create_driver()` spins up a headless Chrome with memory-saving flags and a realistic user-agent. `get_driver()` returns a thread-local driver, creating one if needed. Used for concurrent scraping without driver conflicts.

---

### Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `NUM_WORKERS` | 10 | Default parallel Chrome instances |
| `DEFAULT_PRICE` | 5.00 | Fallback price when no sales found |
| `SERIAL_VALUE` | dict | Print run → relative value multiplier |

---

## daily_scrape.py — Daily Price Update

Entry point for the automated daily rescrape. Called by GitHub Actions (`daily_scrape.yml`) and by the FastAPI "Rescrape All" workflow dispatch.

### Usage

```bash
python daily_scrape.py                    # scrape all users, 3 workers
python daily_scrape.py --workers 5        # more parallel browsers
python daily_scrape.py --user admin       # one user only
```

### CLI Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--workers` | 3 | Number of parallel Chrome instances |
| `--user` | None | Scrape only this username. If omitted, scrapes all users in `users.yaml`. |

### What it does

1. Loads `users.yaml` to get the user list (falls back to single-user legacy mode if missing)
2. For each user:
   - Creates a timestamped backup of the CSV + results JSON
   - Loads current card list from CSV
   - Scrapes all cards in parallel using `process_card()`
   - Merges new raw sales with existing (deduped by date + title)
   - Updates CSV columns: `Fair Value`, `Trend`, `Min`, `Max`, `Num Sales`, `Top 3 Prices`
   - Preserves existing `image_url` (only fetched once via `POST /cards/fetch-image`)
   - Appends price snapshots to `price_history.json`
   - Appends portfolio snapshot to `portfolio_history.json`
3. Prints progress `[completed/total]` and a summary (Updated / No Sales / Failed counts)

### Key Functions

```python
def daily_scrape_user(
    csv_path: str,
    results_path: str,
    history_path: str,
    backup_dir: str,
    max_workers: int = 3
) -> None
```
Scrapes all cards for one user and writes all output files.

---

```python
def daily_scrape(max_workers: int = 3, user: str = None) -> None
```
Main entry point. Orchestrates multi-user scraping.

---

## scrape_master_db.py — Young Guns Bulk Scraper

Scrapes the Young Guns master database (`young_guns.csv`). Supports both raw (ungraded) and graded price scraping with intelligent probing.

### Usage

```bash
# Scrape all ungraded YG prices
python scrape_master_db.py

# Scrape only the 2023-24 season
python scrape_master_db.py --season "2023-24"

# Scrape graded prices (PSA 8/9/10, BGS 9/9.5/10)
python scrape_master_db.py --graded

# Specific grades only
python scrape_master_db.py --graded --grades "PSA 10,BGS 9.5"

# Force re-scrape even if recently scraped
python scrape_master_db.py --force

# Skip cards below $5 raw value when grading
python scrape_master_db.py --graded --min-raw-value 10.0
```

### CLI Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--workers` | 15 | Parallel Chrome instances |
| `--season` | None | Filter to one season (e.g., `"2023-24"`) |
| `--force` | False | Re-scrape cards regardless of last scraped date |
| `--limit` | 0 | Max cards to process (0 = all) |
| `--graded` | False | Scrape graded prices (PSA/BGS) instead of raw |
| `--grades` | None | Comma-separated list of specific grades to scrape |
| `--min-raw-value` | 5.0 | Skip graded scraping for cards with raw value below this |

### What it does

**Raw scrape mode (default):**
1. Loads `young_guns.csv`
2. Filters to cards not recently scraped (unless `--force`)
3. Scrapes each card using a fast/lean Chrome driver in parallel
4. Writes every 50 cards (batch checkpoint) to avoid losing progress
5. Updates CSV: `FairValue`, `NumSales`, `Min`, `Max`, `Trend`, `Top3Prices`, `LastScraped`
6. Appends to `young_guns_price_history.json` and portfolio snapshot

**Graded scrape mode (`--graded`):**
1. Filters to cards with raw value ≥ `--min-raw-value`
2. For each card, probes grades in priority order: PSA 10 → PSA 9 → PSA 8, BGS 10 → BGS 9.5 → BGS 9
3. **Smart probing**: if PSA 10 has 0 sales, skips PSA 9 and PSA 8 (saves time)
4. Updates grade-specific columns in CSV (e.g., `PSA10_Value`, `PSA10_Sales`)
5. Appends graded prices nested in price history: `{graded_prices: {"PSA 10": {fair_value, num_sales}}}`

### Key Functions

```python
def build_card_name(row: pd.Series) -> str
```
Converts a master DB row into the scraper's expected format:
`"SEASON Upper Deck - Young Guns #CARDNUM - PLAYER"`

---

```python
def scrape_one_graded_card(card_name: str, grades_to_scrape: list[str]) -> dict
```
Scrapes multiple grade variants for one card with smart probing. Returns `{grade_key: {fair_value, num_sales, raw_sales}}`.

---

### Output Files

| File | Description |
|------|-------------|
| `data/master_db/young_guns.csv` | Updated with FairValue, NumSales, Trend, grade columns |
| `data/master_db/young_guns_price_history.json` | Append-only price snapshots per card |
| `data/master_db/young_guns_raw_sales.json` | Raw eBay sale records per card |
| `data/master_db/young_guns_portfolio_history.json` | Daily YG portfolio total value |

---

## scrape_nhl_stats.py — NHL Stats Fetcher

Fetches current-season player stats and standings from the NHL API and matches them to Young Guns cards in the master DB.

### Usage

```bash
python scrape_nhl_stats.py                         # Match all cards
python scrape_nhl_stats.py --season "2023-24"      # Only match this season
python scrape_nhl_stats.py --dry-run               # Show matches, don't save
python scrape_nhl_stats.py --fetch-bios            # Also fetch nationality/draft info
python scrape_nhl_stats.py --verbose               # Print detailed match info
```

### CLI Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--season` | None | Only match cards from this season |
| `--dry-run` | False | Print matches without saving any files |
| `--fetch-bios` | False | Also fetch player bio (birth country, draft round/overall, height/weight) from NHL API |
| `--verbose` | False | Print per-team and per-player match details |

### How matching works

Players are matched from the NHL API roster by a 3-stage strategy:
1. **Exact name match** — card player name == API player name
2. **Normalized match** — strip diacritics, lowercase both (e.g., "Mathew Barzal" ≈ "Mathew Barzal")
3. **Fuzzy match** — 85% similarity cutoff (handles short names, typos)

Unmatched cards are logged separately with a reason.

### Key Functions

```python
def fetch_json(url: str, retries: int = 2) -> dict | None
```
Fetch JSON from the NHL API with retry on network errors. Sleeps 1 second between retries.

---

```python
def fetch_standings() -> dict
```
Returns current standings keyed by team abbreviation. Per-team fields: wins, losses, OTL, points, games played, goal differential, league rank, division rank, division, conference, streak.

---

```python
def match_player(
    player_name: str,
    skaters: dict,
    goalies: dict
) -> tuple[dict | None, str | None]
```
Tries to match a card player name to an NHL API player. Returns `(api_data, player_type)` or `(None, None)` if unmatched. `player_type` is `"skater"` or `"goalie"`.

---

```python
def build_player_entry(
    player_name: str,
    api_data: dict,
    player_type: str,
    card_team: str,
    standings: dict,
    existing_entry: dict = None
) -> dict
```
Builds or updates a player stats entry. Skater fields: goals, assists, points, plus/minus, shots, shooting %, power play goals, game-winning goals. Goalie fields: save %, GAA, wins. History is an append-only list of dated snapshots (deduped by date).

---

### Output Files

| File | Description |
|------|-------------|
| `data/admin/nhl_player_stats.json` | Full player index: meta, standings, players dict, unmatched list |
| `data/master_db/young_guns.csv` | Updated `Position` column (if empty cells filled from API) |
| `data/admin/correlation_snapshot.json` | R² stats, price tiers, team premiums, draft round breakdown |

---

## GitHub Actions Workflows

| Workflow | File | Schedule | What it runs |
|----------|------|----------|-------------|
| Daily card scrape | `.github/workflows/daily_scrape.yml` | Daily 8am UTC | `python daily_scrape.py --workers 3` |
| YG daily update | `.github/workflows/master_db_daily.yml` | Daily | `python scrape_master_db.py` |
| YG weekly full | `.github/workflows/master_db_weekly.yml` | Weekly | `python scrape_master_db.py --force` |

All workflows: checkout code → install Chrome → install dependencies → SSH into server to download current data → run scraper → SSH back to upload results.

The **Rescrape All** button in the frontend triggers `daily_scrape.yml` via the GitHub Actions API (`POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches`). Requires `GITHUB_TOKEN` in the server's `.env`.
