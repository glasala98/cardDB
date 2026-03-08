# CardDB — Backend Reference

FastAPI application at `api/`. All endpoints live under `/api/*`. The React dist is served as static files for all other routes (SPA fallback).

---

## App Entry Point — `api/main.py`

- Creates the FastAPI app instance
- Configures CORS for `localhost:5173`, `localhost:4173`, `southwestsportscards.ca`, `*.up.railway.app`
- Registers all 8 routers with their `/api/*` prefixes
- Imports `get_db` from `db.py` for the health check
- Mounts React `frontend/dist/assets` as StaticFiles
- SPA catch-all: any unknown path returns `index.html`

### Health check
```
GET /api/health
  → SELECT 1 against DB pool
  ← {"status": "ok"|"degraded", "db": true|false}
```
Railway uses this for service health monitoring.

---

## Router: `auth.py` — `/api/auth`

JWT-based session auth. Token stored client-side in localStorage, sent as `Authorization: Bearer <token>` on every request.

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/api/auth/login` | POST | None | bcrypt verify → JWT (HS256, 7-day) |
| `/api/auth/me` | GET | Required | Returns `{username, display_name, role}` |
| `/api/auth/logout` | POST | None | Client-side only (no server state) |

**Key internals:**
- `JWT_SECRET` from env var (`dev-secret-change-in-prod` fallback for local)
- `get_current_user(credentials)` — FastAPI dependency used by all protected routes. Decodes JWT, returns username string.
- Users stored in `users` PostgreSQL table: `username`, `display_name`, `password_hash`, `role`
- `PyJWT` (`import jwt`) — NOT `python-jose`

**What is NOT here:** signup is disabled in production (admin creates users via `/api/admin`).

---

## Router: `cards.py` — `/api/cards`

Personal card ledger (the user's own physical cards). Text-keyed by card name — predates the catalog FK system.

All endpoints use query params (`?name=...`) because card names contain characters (`[`, `]`, `#`, `/`) that break URL path segments.

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `GET /api/cards` | GET | Required | All user's ledger cards + latest price data |
| `GET /api/cards/detail` | GET | Required | Single card: price history + raw sales + confidence |
| `POST /api/cards` | POST | Required | Add a new card to ledger |
| `PATCH /api/cards` | PATCH | Required | Update fair_value, cost_basis, purchase_date, tags |
| `DELETE /api/cards` | DELETE | Required | Remove card from ledger |
| `POST /api/cards/archive` | POST | Required | Move card to archive |
| `POST /api/cards/restore` | POST | Required | Restore from archive |
| `GET /api/cards/archive` | GET | Required | List archived cards |
| `POST /api/cards/scrape` | POST | Required | Trigger background rescrape for one card |
| `POST /api/cards/fetch-image` | POST | Required | Selenium: fetch eBay listing image for card |
| `POST /api/cards/bulk-import` | POST | Required | CSV upload → batch add cards |

**Data shape (card row):**
```json
{
  "card_name": "2023-24 Upper Deck - Young Guns #201 - Bedard",
  "fair_value": 45.00,
  "cost_basis": 30.00,
  "purchase_date": "2024-01-15",
  "tags": "rookie, key card",
  "trend": "up",
  "num_sales": 8,
  "median_all": 44.50,
  "min": 38.00,
  "max": 52.00,
  "top3": "$52, $48, $45",
  "confidence": "high",
  "last_scraped": "2026-03-05 14:32"
}
```

---

## Router: `catalog.py` — `/api/catalog`

Read-only browsing of the 1.26M-card `card_catalog` table. Public — no auth required.

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `GET /api/catalog` | GET | None | Paginated browse with filters |
| `GET /api/catalog/filters` | GET | None | Distinct years + set names for a sport |

**Browse query params:**

| Param | Type | Description |
|---|---|---|
| `search` | string | Free-text across player_name + set_name |
| `sport` | string | NHL / NBA / NFL / MLB |
| `year` | string | Exact year (e.g. `2024-25`) |
| `set_name` | string | Partial match |
| `is_rookie` | bool | Filter rookie flag |
| `has_price` | bool | Only cards with market_prices data |
| `sort` | string | Column: player_name / year / fair_value / num_sales |
| `dir` | string | asc / desc |
| `page` | int | 1-based |
| `per_page` | int | 1–200 (default 50) |

**Performance note:** Total count uses `pg_class` estimate for unfiltered queries to avoid a full-scan COUNT(*) on 2.6M rows. Filtered queries do exact COUNT(*) since the WHERE clause limits scope.

**Response:**
```json
{
  "cards": [...],
  "total": 310000,
  "page": 1,
  "pages": 6200,
  "per_page": 50
}
```

Each card includes: `id`, `sport`, `year`, `brand`, `set_name`, `card_number`, `player_name`, `team`, `variant`, `print_run`, `is_rookie`, `catalog_tier`, `fair_value`, `trend`, `confidence`, `num_sales`, `scraped_at`.

---

## Router: `collection.py` — `/api/collection`

Links a user's ownership to `card_catalog` entries. Supports quantity, grade, cost basis, and notes per owned card. One row per `(user_id, card_catalog_id, grade)` — same card at different grades is two rows.

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `GET /api/collection` | GET | Required | Full collection joined with catalog + market prices |
| `GET /api/collection/owned-ids` | GET | Required | Set of card_catalog_ids for ✓ badges on Catalog page |
| `POST /api/collection` | POST | Required | Add card; ON CONFLICT increments quantity |
| `PATCH /api/collection/{id}` | PATCH | Required | Update grade, quantity, cost_basis, notes |
| `DELETE /api/collection/{id}` | DELETE | Required | Remove from collection |

**Add request body:**
```json
{
  "card_catalog_id": 12345,
  "grade": "Raw",
  "quantity": 1,
  "cost_basis": 30.00,
  "purchase_date": "2024-01-15",
  "notes": "Pack pull"
}
```

Grades supported: Raw, PSA 1–10, BGS 8–10, SGC 9–10.

---

## Router: `master_db.py` — `/api/master-db`

Young Guns / Rookie analytics page and grading ROI lookup.

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `GET /api/master-db` | GET | Required | Full YG list with PSA/BGS prices + filters |
| `GET /api/master-db/grading-lookup` | GET | Required | Graded price lookup for a player |
| `GET /api/master-db/price-history` | GET | Required | YG price history chart data |
| `GET /api/master-db/portfolio-history` | GET | Required | YG portfolio history |
| `GET /api/master-db/raw-sales` | GET | Required | Raw eBay sales for a YG card |
| `POST /api/master-db/scrape` | POST | Required | Background rescrape one YG card |

**Grading lookup priority chain:**
```
1. young_guns.csv master DB (CSV) — existing PSA/BGS columns
2. market_prices.graded_data JSONB — new catalog-linked source
3. rookie_price_history.graded_data — legacy fallback
Response includes "source" field indicating which was used.
```

---

## Router: `stats.py` — `/api/stats`

Scrape orchestration and monitoring.

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `GET /api/stats/alerts` | GET | None | Market movement alerts (>5% change) |
| `POST /api/stats/trigger-scrape` | POST | Required | Dispatch `daily_scrape.yml` via GitHub API |
| `GET /api/stats/scrape-status` | GET | Required | Latest run status for `daily_scrape.yml` |
| `GET /api/stats/workflow-status` | GET | Required | Status of all 7 tracked workflows |

**Workflow status response:**
```json
{
  "workflows": [
    {
      "name": "Catalog Staple",
      "file": "catalog_tier_staple.yml",
      "status": "completed",
      "conclusion": "success",
      "started_at": "2026-03-06T01:00:00Z",
      "updated_at": "2026-03-06T05:12:00Z",
      "html_url": "https://github.com/...",
      "run_number": 42
    },
    ...
  ]
}
```

All 9 tracked workflows are fetched concurrently via `ThreadPoolExecutor`. Requires `GITHUB_TOKEN` env var (classic PAT, `repo` + `workflow` scopes). The tracked list is defined in `_WORKFLOWS` at the top of `stats.py` — add new workflows there to include them in the health panel.

---

## Router: `scan.py` — `/api/scan`

Card identification via Claude Vision.

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `POST /api/scan/analyze` | POST | Required | Upload front (+ optional back) image → card details |

Accepts `multipart/form-data`. Max 20MB per image. Supported: JPEG, PNG, WebP.

Uses `claude-sonnet-4-6` with structured JSON prompt. Returns:
```json
{
  "player_name": "Connor Bedard",
  "year": "2023-24",
  "brand": "Upper Deck",
  "subset": "Young Guns",
  "card_number": "201",
  "parallel": null,
  "serial_number": null,
  "grade": null,
  "confidence": "high",
  "is_sports_card": true
}
```

On parse failure: `{"parse_error": true, "raw": "..."}`.

---

## Router: `admin.py` — `/api/admin`

Admin operations — scrape monitoring, data quality, sealed products, user management. All endpoints require `role: admin`.

**User management:**

| Endpoint | Method | Description |
|---|---|---|
| `GET /api/admin/users` | GET | List all users |
| `POST /api/admin/users` | POST | Create user (bcrypt hash, write to DB) |
| `DELETE /api/admin/users/{username}` | DELETE | Delete user |
| `PATCH /api/admin/users/{username}/password` | PATCH | Change password |

**Scrape monitoring:**

| Endpoint | Method | Description |
|---|---|---|
| `GET /api/admin/scrape-runs` | GET | Recent scrape run history + active runs |
| `GET /api/admin/scrape-runs/summary` | GET | Per-workflow stats, consecutive errors, anomalies |
| `GET /api/admin/scrape-run-errors/{run_id}` | GET | Per-card error log for a run |
| `GET /api/admin/pipeline-health` | GET | Coverage stats: priced 7d/30d, newly_priced counts |
| `GET /api/admin/data-quality` | GET | Snapshot audit: missing prices, stale data |
| `GET /api/admin/snapshot-audit` | GET | Catalog coverage snapshot |

**Sealed products:**

| Endpoint | Method | Description |
|---|---|---|
| `GET /api/admin/sealed-products` | GET | Paginated sealed product list |
| `PATCH /api/admin/sealed-products/{id}` | PATCH | Edit a sealed product row |
| `GET /api/admin/sealed-products/quality` | GET | Report: sport mismatches, bad MSRP ($1.00), duplicates |
| `DELETE /api/admin/sealed-products/mismatches` | DELETE | Delete rows where set name indicates wrong sport |

**Outlier management:**

| Endpoint | Method | Description |
|---|---|---|
| `GET /api/admin/outliers` | GET | Cards with statistically anomalous prices |
| `POST /api/admin/outliers/ignore` | POST | Bulk-ignore selected outlier cards |

---

## Common Patterns

### Auth dependency
```python
from api.routers.auth import get_current_user

@router.get("")
def my_endpoint(user: str = Depends(get_current_user)):
    # user = validated username string
```

### DB access
```python
from db import get_db

with get_db() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT ...", (param,))
        rows = cur.fetchall()
# auto-commits on clean exit, rolls back on exception
```

### Admin-only dependency
```python
from api.routers.admin import _require_admin

@router.get("")
def admin_endpoint(admin: str = Depends(_require_admin)):
    ...
```

---

## Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | Yes | psycopg2 connection string (Railway injects) |
| `JWT_SECRET` | Yes | HS256 signing key for auth tokens |
| `GITHUB_TOKEN` | Yes | PAT for triggering + reading GitHub Actions |
| `ANTHROPIC_API_KEY` | Yes | Claude Vision for card scanning |
| `PORT` | Yes | Railway injects; uvicorn binds to this |
