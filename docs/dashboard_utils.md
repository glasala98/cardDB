# dashboard_utils.py — Reference

Shared Python utility layer. Imported by `api/routers/` and scraper scripts. Handles card name parsing, scraping delegation, price history, archive, market alerts, and legacy YG DB access.

**Note:** New API routers use `db.get_db()` directly for all PostgreSQL access. `dashboard_utils` retains helpers for scraper scripts and legacy compatibility.

---

## db.py — Connection Pool

```python
from db import get_db

with get_db() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT ...", (param,))
        rows = cur.fetchall()
    # auto-commits on clean exit, rolls back on exception
```

`get_db()` is a `@contextmanager` over `psycopg2.ThreadedConnectionPool(min=1, max=10, DATABASE_URL)`. Always returns the connection to the pool in the `finally` block.

---

## Auth

**`load_users() → dict`**
Loads `users.yaml` from project root. Returns `{username: {display_name, role, password_hash}}` or empty dict. Used by legacy scraper scripts. API auth uses the `users` PostgreSQL table directly.

**`verify_password(username, password) → bool`**
Checks plaintext password against bcrypt hash in `users.yaml`.

**`USERS_YAML`** — absolute path constant to `users.yaml`.

---

## Card Name Parsing

**`parse_card_name(card_name) → dict`**

Parses the structured card name format used throughout the system:
```
"YEAR BRAND - SUBSET #CARDNUM - PLAYER [GRADE] /SERIAL"
```

Returns:
```python
{
  "player": "Connor Bedard",
  "year": "2023-24",
  "brand": "Upper Deck",
  "set_name": "Upper Deck",
  "subset": "Young Guns",
  "card_number": "201",
  "serial": "99",       # from "/99"
  "grade": "PSA 10",    # from "[PSA 10]"
  "tags": ""
}
```

---

## Scraping Delegation

**`scrape_single_card(card_name, results_json_path=None) → dict`**
Calls `process_card()` from `scrape_card_prices.py`. Returns:
```python
{"estimated_value", "confidence", "stats", "raw_sales", "search_url", "image_url"}
```
Used by the `cards` router for single-card rescrape.

**`scrape_graded_comparison(card_name) → dict`**
PSA 8/9/10 + BGS 9/9.5/10 price comparison. Used by `CardInspect` grading ROI (legacy path — `market_prices.graded_data` is now preferred).

**`analyze_card_images(front_bytes, back_bytes=None) → dict`**
Sends images to Claude (`claude-sonnet-4-6`). Returns structured card identity:
```python
{
  "player_name", "year", "brand", "subset", "card_number",
  "parallel", "serial_number", "grade",
  "confidence": "high"|"medium"|"low",
  "is_sports_card": True|False
}
```
Used by `scan.py` router and `ScanCardModal`.

---

## Card Data I/O (PostgreSQL-backed)

These are used by `daily_scrape.py` and the legacy `cards` router paths.

**`load_data(username) → DataFrame`**
Loads cards from `cards` table for a given user. Returns DataFrame with all card columns.

**`save_data(df, username)`**
Writes updated DataFrame rows back to `cards` table.

**`backup_data(label, username, backup_dir)`**
Creates a timestamped backup snapshot. Used by `daily_scrape.py` before each run.

---

## Price History (PostgreSQL)

**`load_price_history(card_name, username) → list`**
Reads from `card_price_history` table. Each entry: `{date, fair_value, num_sales}`.

**`append_price_history(card_name, fair_value, num_sales, username)`**
Inserts one row per day into `card_price_history`.

**`load_all_price_history(username) → dict`**
All price history for all cards, keyed by card name.

**`load_card_results(card_name, username) → list`**
Raw eBay sales from `card_results` table.

**`save_card_results(card_name, sales, username)`**
Upserts into `card_results`. Deduplicates by listing URL.

---

## Portfolio History

**`append_portfolio_snapshot(total_value, total_cards, avg_value, username)`**
Inserts daily total into `portfolio_history`.

**`load_portfolio_history(username) → list`**
Reads `portfolio_history` for the portfolio chart.

---

## Archive

**`archive_card(card_name, username)`**
Moves card from `cards` table to `card_archive` with `ArchivedAt` timestamp.

**`load_archive(username) → list`**
Returns all archived cards for the user.

**`restore_card(card_name, username) → dict`**
Removes from archive, re-inserts into `cards`. Returns the restored row dict.

---

## Market Alerts

**`get_market_alerts(username, top_n=10, min_pct=5.0) → list`**
Compares current vs previous `fair_value` in `card_price_history`. Returns:
```python
[
  {
    "card_name": "...",
    "direction": "up"|"down",
    "pct_change": 12.5,
    "current": 45.00,
    "previous": 40.00
  },
  ...
]
```
Sorted by `pct_change` descending. Only cards that changed by at least `min_pct`%.

---

## Master DB / Young Guns (CSV-backed legacy)

Used by `api/routers/master_db.py` for the MasterDB analytics page. CSV file: `young_guns.csv` at project root.

**`load_master_db(path=MASTER_DB_PATH) → DataFrame`**
Loads `young_guns.csv`. Mtime-cached — re-reads only when file changes.

**`save_master_db(df, path=MASTER_DB_PATH)`**
Writes updated DataFrame back to CSV.

**`load_yg_price_history(player, path) → list`**
Per-player YG price history from JSON sidecar.

**`append_yg_price_history(player, fair_value, num_sales, path, graded_prices=None)`**
Appends to YG price history JSON.

**`load_yg_portfolio_history(path) → list`**
**`append_yg_portfolio_snapshot(total, count, avg, path)`**
YG portfolio totals.

**`load_yg_raw_sales / save_yg_raw_sales / batch_save_yg_raw_sales`**
Raw eBay sales storage for YG cards.

**Migration status:** `market_price_history` (PostgreSQL) is the preferred history for `card_catalog`-linked cards. YG JSON history is legacy, retained for the MasterDB page analytics until fully migrated.

---

## NHL Stats

**`load_nhl_player_stats(player_name, path) → dict`**
Returns `{current_season, history, bio}` from the `player_stats` JSON / DB.

**`get_player_stats_for_card(player_name, path) → dict | None`**
Returns just `current_season` sub-dict.

**`get_player_bio_for_card(player_name, path) → dict | None`**
Returns bio sub-dict: nationality, draft info, height/weight.

**`get_all_player_bios(path) → dict`**
Returns `{player_name: bio_dict}` for all players.

---

## Correlation Analytics

**`compute_correlation_snapshot(cards_df, nhl_players, standings) → dict`**
Computes price-vs-performance R² correlations. Returns:
```python
{
  "r2_points": 0.62,
  "r2_goals": 0.55,
  "price_tiers": {...},
  "team_premiums": {...},
  "position_breakdown": {...},
  "nationality_breakdown": {...},
  "draft_round_breakdown": {...}
}
```

**`load_correlation_history(path) → list`**
**`save_correlation_snapshot(snapshot, path)`**

---

## Constants

| Constant | Value | Description |
|---|---|---|
| `MONEY_COLS` | `['Fair Value', 'Median (All)', 'Min', 'Max', 'Cost Basis']` | Columns rounded to 2dp on save |
| `MASTER_DB_PATH` | `young_guns.csv` | Path to YG master CSV |
| `USERS_YAML` | `users.yaml` | Absolute path to user config file |
| `SCRIPT_DIR` | `os.path.dirname(__file__)` | Project root |
