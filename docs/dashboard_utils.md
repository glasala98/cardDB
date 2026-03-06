# dashboard_utils.py — Reference

Core utility layer shared by `api/routers/` and scraper scripts. Handles auth, card data I/O, scraping, parsing, and legacy YG market DB access.

---

## Auth

**`load_users() → dict | None`**
Loads `users.yaml` from project root. Returns `{username: {display_name, role, password_hash}}` or `None` (triggers dev fallback).

**`verify_password(username, password) → bool`**
Checks password against bcrypt hash in `users.yaml`.

**`get_user_paths(username) → dict`**
Returns per-user file paths under `data/{username}/`: `csv`, `results`, `history`, `portfolio`, `archive`, `backup_dir`. (Legacy — new code uses PostgreSQL directly.)

---

## Card Data I/O  (PostgreSQL-backed via `db.py`)

The FastAPI routers call `db.get_db()` directly for all database access. `dashboard_utils` retains helpers for the scraper scripts and legacy compatibility.

**`load_data(csv_path, results_json_path) → DataFrame`**
Loads legacy CSV + results JSON, merges, returns DataFrame. Uses mtime-based cache `_DATA_CACHE`. Still used by `daily_scrape.py`.

**`save_data(df, csv_path)`**
Writes DataFrame to CSV. Converts money columns to 2dp floats.

**`backup_data(label, csv_path, results_path, backup_dir)`**
Timestamped backup of CSV + results JSON. Used by `daily_scrape.py` before each run.

---

## Card Name Parsing

**`parse_card_name(card_name) → dict`**
Parses structured card name into components. Expected format:
```
"YEAR BRAND - SUBSET #CARDNUM - PLAYER [GRADE] /SERIAL"
```
Returns: `player`, `year`, `brand`, `set_name`, `subset`, `card_number`, `serial`, `grade`, `tags`.

---

## Scraping

**`scrape_single_card(card_name, results_json_path=None) → dict`**
Calls `process_card()` from `scrape_card_prices.py`. Updates results JSON. Returns `{estimated_value, confidence, stats, raw_sales}`.

**`scrape_graded_comparison(card_name) → dict`**
PSA 8/9/10 + BGS 9/9.5/10 price comparison. Used by CardInspect grading ROI calculator.

**`analyze_card_images(front_bytes, back_bytes=None) → dict`**
Sends images to Claude Vision (claude-sonnet-4-5). Returns: `player_name`, `year`, `brand`, `subset`, `card_number`, `parallel`, `serial_number`, `grade`, `confidence`, `is_sports_card`.

---

## Price & Portfolio History  (legacy JSON files)

These functions are used by `daily_scrape.py`. New code writes directly to PostgreSQL tables (`card_price_history`, `portfolio_history`).

**`append_price_history(card_name, fair_value, num_sales, history_path)`**
**`load_price_history(card_name, history_path) → list`**
Per-card price snapshots. Each entry: `{date, fair_value, num_sales}`.

**`append_portfolio_snapshot(total_value, total_cards, avg_value, portfolio_path)`**
**`load_portfolio_history(portfolio_path) → list`**
Daily portfolio totals.

---

## Archive

**`archive_card(df, card_name, archive_path) → DataFrame`**
Removes card from DataFrame, appends to `card_archive.csv` with `ArchivedAt` timestamp.

**`load_archive(archive_path) → DataFrame`**

**`restore_card(card_name, archive_path) → dict`**
Removes from archive, returns row dict for re-adding to collection.

---

## Market Alerts

**`get_market_alerts(history=None, top_n=10, min_pct=5.0) → list`**
Compares latest vs previous price per card. Returns list of `{card_name, direction, pct_change, current, previous}` sorted by magnitude.

---

## Master DB / Young Guns  (CSV-backed legacy)

Still used by `api/routers/master_db.py` for the MasterDB analytics page.

**`load_master_db(path=MASTER_DB_PATH) → DataFrame`**
Loads `young_guns.csv`. Mtime-cached.

**`save_master_db(df, path=MASTER_DB_PATH)`**

**`append_yg_price_history(card_name, fair_value, num_sales, history_path, graded_prices=None)`**
**`load_yg_price_history(...) → dict`**
**`append_yg_portfolio_snapshot(...) / load_yg_portfolio_history(...)`**
**`save_yg_raw_sales / load_yg_raw_sales / batch_save_yg_raw_sales / batch_append_yg_price_history`**

Note: `market_price_history` (PostgreSQL) is the preferred price history for `card_catalog`-linked cards. The YG JSON history is legacy, retained for the MasterDB page until fully migrated.

---

## NHL Stats

**`load_nhl_player_stats(player_name, path) → dict`**
Returns `{current_season, history, bio}` from cached stats JSON.

**`save_nhl_player_stats(data, path)`**

**`get_player_stats_for_card(player_name, path) → dict | None`**
Returns just `current_season` sub-dict.

**`get_player_bio_for_card(player_name, path) → dict | None`**
Returns `bio` sub-dict (nationality, draft info, height/weight).

**`get_all_player_bios(path) → dict`**
Returns `{player_name: bio_dict}` for all players with bio data.

---

## Correlation Analytics

**`compute_correlation_snapshot(cards_df, nhl_players, nhl_standings) → dict`**
Price vs performance R² correlations. Returns: `r2_points`, `r2_goals`, `price_tiers`, `team_premiums`, `position_breakdown`, `nationality_breakdown`, `draft_round_breakdown`.

**`load_correlation_history(path) → list`**
**`save_correlation_snapshot(snapshot, path)`**

---

## db.py — Database Connection Pool

```python
from db import get_db

with get_db() as conn:
    cur = conn.cursor()
    cur.execute("SELECT ...")
    rows = cur.fetchall()
    conn.commit()
```

`get_db()` is a context manager over a `psycopg2.ThreadedConnectionPool` (min 1, max 10).
`DATABASE_URL` env var required (set in Railway or local `.env`).
Returns a `RealDictCursor`-like connection; commit is explicit.
