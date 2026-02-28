# dashboard_utils.py — Reference

Core data/utility layer shared by the FastAPI backend (`api/routers/`) and the legacy Streamlit dashboard. All data reads/writes, card parsing, scraping, archiving, and NHL stats go through this module.

---

## Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `DATA_ROOT` | `data/` | Base directory for all data files |
| `CSV_PATH` | `data/admin/card_prices_summary.csv` | Default (legacy single-user) card CSV |
| `RESULTS_JSON_PATH` | `data/admin/card_prices_results.json` | Default results JSON |
| `HISTORY_PATH` | `data/admin/price_history.json` | Default price history |
| `ARCHIVE_PATH` | `data/admin/card_archive.csv` | Default archive CSV |
| `MASTER_DB_PATH` | `data/master_db/young_guns.csv` | Young Guns market DB |
| `MONEY_COLS` | list of str | Columns that hold monetary values (Fair Value, Cost Basis, Min, Max, etc.) |
| `_DATA_CACHE` | dict | In-process mtime-based cache for `load_data()` |
| `_MASTER_DB_CACHE` | dict | In-process mtime-based cache for `load_master_db()` |

---

## Caching

Two in-process DataFrame caches prevent repeated CSV/JSON parsing on every API request. Each cache entry stores `(mtime_tuple, dataframe)`. On every call, file mtimes are checked; if unchanged, the cached DataFrame copy is returned without re-reading disk.

```python
_DATA_CACHE     # key: (csv_path, results_json_path)  → (mtime_tuple, df)
_MASTER_DB_CACHE  # key: csv_path  → (mtime_tuple, df)
```

```python
def _file_mtime(path: str) -> float
```
Returns `os.path.getmtime(path)` or `0` if the file doesn't exist.

---

## Auth Helpers

```python
def load_users() -> dict | None
```
Loads `users.yaml` from the project root. Returns a dict of `{username: {display_name, role, password_hash}}`, or `None` if the file doesn't exist (triggers dev fallback in the auth router).

---

```python
def verify_password(username: str, password: str) -> bool
```
Looks up the user in `users.yaml` and checks the provided password against the stored bcrypt hash. Returns `False` if the user doesn't exist.

---

```python
def get_user_paths(username: str) -> dict
```
Resolves per-user data file paths under `data/{username}/`. Returns a dict with keys: `csv`, `results`, `history`, `portfolio`, `archive`, `backup_dir`.

---

## Data I/O

```python
def init_user_data(csv_path: str) -> None
```
Creates an empty CSV with the correct column headers at `csv_path` if the file doesn't already exist. Used when a new user logs in for the first time.

---

```python
def load_data(csv_path: str, results_json_path: str) -> pd.DataFrame
```
Loads the card collection as a DataFrame. Merges the CSV (`card_prices_summary.csv`) with the results JSON (`card_prices_results.json`) to add parsed fields: `Player`, `Year`, `Set Name`, `Grade`, `Confidence`, `Last Scraped`. Uses `_DATA_CACHE` to skip re-parsing if files haven't changed. Returns a `.copy()` of the cached DataFrame.

---

```python
def save_data(df: pd.DataFrame, csv_path: str) -> None
```
Writes the DataFrame back to `csv_path`. Converts monetary columns to 2dp floats before writing.

---

```python
def backup_data(label: str, csv_path: str, results_path: str, backup_dir: str) -> None
```
Creates timestamped copies of the CSV and results JSON in `backup_dir/`. Label is included in the filename (e.g., `"pre-scrape"`).

Args:
- `label`: Short string included in the backup filename.
- `csv_path`: Source CSV to back up.
- `results_path`: Source results JSON to back up.
- `backup_dir`: Directory to write backups into (created if needed).

---

## Card Parsing

```python
def parse_card_name(card_name: str) -> dict
```
Parses a structured card name string into its component fields. Expected format:
```
"YEAR BRAND - SUBSET #CARDNUM - PLAYER [GRADE] /SERIAL"
```

Returns a dict with keys: `player`, `year`, `brand`, `set_name`, `subset`, `card_number`, `serial`, `grade`, `tags`.

Examples:
- `"2023-24 Upper Deck - Young Guns #201 - Connor Bedard"` → `{player: "Connor Bedard", year: "2023-24", brand: "Upper Deck", subset: "Young Guns", card_number: "201", ...}`
- `"2021-22 O-Pee-Chee #15 - Auston Matthews [PSA 9] /99"` → `{..., grade: "PSA 9", serial: "99"}`

---

## Scraping

```python
def scrape_single_card(card_name: str, results_json_path: str = None) -> dict
```
Scrapes eBay sold listings for a single card by calling `process_card()` from `scrape_card_prices.py`. Updates the results JSON with new sales, image URL, and timestamp. Returns the result dict with `estimated_value`, `confidence`, `stats`, `raw_sales`.

Args:
- `card_name`: Full card name string (must match format `parse_card_name` expects).
- `results_json_path`: Path to the results JSON to read/write. Defaults to `RESULTS_JSON_PATH`.

---

```python
def scrape_graded_comparison(card_name: str) -> dict
```
Runs graded price comparisons for a card (PSA 8, 9, 10 and BGS 9, 9.5, 10). Used by the CardInspect grading ROI calculator. Returns a dict keyed by grade string with `fair_value` and `num_sales`.

---

```python
def analyze_card_images(
    front_image_bytes: bytes,
    back_image_bytes: bytes = None
) -> dict
```
Sends card image(s) to Claude Vision (claude-3-5-sonnet) and extracts: `player_name`, `year`, `brand`, `subset`, `card_number`, `parallel`, `serial_number`, `grade`, `confidence`, `is_sports_card`, `validation_reason`, `raw_text`, `parse_error`.

Args:
- `front_image_bytes`: Raw image bytes for the card front (required).
- `back_image_bytes`: Raw image bytes for the card back (optional, improves accuracy).

---

## Sales History

```python
def load_sales_history(card_name: str, results_json_path: str) -> list
```
Returns the raw eBay sales list for a card from the results JSON. Each entry is a dict with `title`, `price_val`, `sold_date`, `listing_url`, `image_url`, etc. Returns `[]` if not found.

---

## Price History

```python
def append_price_history(
    card_name: str,
    fair_value: float,
    num_sales: int,
    history_path: str
) -> None
```
Appends a dated price snapshot for one card to `price_history.json`. Structure per entry: `{date, fair_value, num_sales}`.

---

```python
def load_price_history(card_name: str, history_path: str) -> list
```
Returns the list of price snapshots for a card from `price_history.json`. Each entry: `{date, fair_value, num_sales}`. Returns `[]` if not found.

---

## Portfolio History

```python
def append_portfolio_snapshot(
    total_value: float,
    total_cards: int,
    avg_value: float,
    portfolio_path: str
) -> None
```
Appends a daily portfolio snapshot to `portfolio_history.json`. Entry: `{date, total_value, total_cards, avg_value}`.

---

```python
def load_portfolio_history(portfolio_path: str) -> list
```
Returns the list of daily portfolio snapshots. Each entry: `{date, total_value, total_cards, avg_value}`.

---

## Archive

```python
def archive_card(df: pd.DataFrame, card_name: str, archive_path: str) -> pd.DataFrame
```
Soft-deletes a card by removing it from the DataFrame and appending it to `card_archive.csv` with an `ArchivedAt` timestamp. Returns the updated DataFrame (card removed).

Args:
- `df`: Current collection DataFrame.
- `card_name`: Exact card name to archive.
- `archive_path`: Path to the archive CSV.

---

```python
def load_archive(archive_path: str) -> pd.DataFrame
```
Loads the archive CSV and returns it as a DataFrame. Returns an empty DataFrame if the file doesn't exist.

---

```python
def restore_card(card_name: str, archive_path: str) -> dict
```
Removes a card from the archive CSV and returns its row as a dict (ready to add back to the collection). Raises `ValueError` if the card isn't in the archive.

---

## Market Alerts

```python
def get_market_alerts(
    history: dict = None,
    top_n: int = 10,
    min_pct: float = 5.0
) -> dict
```
Compares the most recent and previous price snapshots per card and returns top gainers and losers. Returns `{gainers: [...], losers: [...]}` where each entry is `{card_name, current, previous, change_pct}`.

Args:
- `history`: Pre-loaded price history dict. If `None`, loads from `HISTORY_PATH`.
- `top_n`: Number of top movers to return per side.
- `min_pct`: Minimum percentage change to include.

---

## Master DB / Young Guns

```python
def load_master_db(path: str = MASTER_DB_PATH) -> pd.DataFrame
```
Loads `young_guns.csv` as a DataFrame. Uses `_MASTER_DB_CACHE` to avoid re-parsing on every request.

---

```python
def save_master_db(df: pd.DataFrame, path: str = MASTER_DB_PATH) -> None
```
Writes the Young Guns DataFrame back to CSV.

---

```python
def append_yg_price_history(
    card_name: str,
    fair_value: float,
    num_sales: int,
    history_path: str,
    graded_prices: dict = None
) -> None
```
Appends a dated price snapshot for a YG card. `graded_prices` is an optional dict keyed by grade (e.g., `{"PSA 10": {fair_value, num_sales}}`).

---

```python
def load_yg_price_history(card_name: str, history_path: str) -> list
```
Returns price snapshots for a YG card. Each entry: `{date, fair_value, num_sales, [graded_prices]}`.

---

```python
def append_yg_portfolio_snapshot(
    total_value: float,
    total_cards: int,
    avg_value: float,
    portfolio_path: str
) -> None
```
Appends a daily snapshot of the YG portfolio total value.

---

```python
def load_yg_portfolio_history(portfolio_path: str) -> list
```
Returns the YG portfolio history list.

---

```python
def save_yg_raw_sales(card_name: str, sales: list, path: str) -> None
def load_yg_raw_sales(card_name: str, path: str) -> list
def batch_save_yg_raw_sales(all_sales_dict: dict, path: str) -> None
def batch_append_yg_price_history(updates: list, path: str) -> None
```
Raw sales I/O for the Young Guns master DB. Batch variants accumulate multiple cards before writing to reduce I/O.

---

## NHL Stats

```python
def load_nhl_player_stats(player_name: str, path: str) -> dict
```
Returns the stats dict for a specific player from the cached NHL stats JSON. Keys: `nhl_id`, `current_team`, `position`, `type`, `current_season`, `history`, optionally `bio`.

---

```python
def save_nhl_player_stats(data: dict, path: str) -> None
```
Writes the full NHL stats dict (including meta, standings, players, unmatched) back to disk.

---

```python
def get_player_stats_for_card(player_name: str, path: str) -> dict | None
```
Convenience wrapper — loads NHL stats and returns just the `current_season` sub-dict for a player, or `None` if not found.

---

```python
def get_player_bio_for_card(player_name: str, path: str) -> dict | None
```
Returns the `bio` sub-dict (nationality, draft info, height/weight) for a player, or `None`.

---

```python
def get_all_player_bios(path: str) -> dict
```
Returns `{player_name: bio_dict}` for all players that have bio data in the stats JSON.

---

## Correlation Analytics

```python
def compute_correlation_snapshot(
    cards_df: pd.DataFrame,
    nhl_players: dict,
    nhl_standings: dict
) -> dict
```
Computes statistical correlations between card prices and NHL performance metrics. Returns a snapshot dict with: `r2_points`, `r2_goals`, `price_tiers`, `team_premiums`, `position_breakdown`, `nationality_breakdown`, `draft_round_breakdown`.

---

```python
def load_correlation_history(path: str) -> list
def save_correlation_snapshot(snapshot: dict, path: str) -> None
```
Append-only correlation history I/O. Each snapshot is dated.
