# CardDB API

FastAPI backend for the React frontend. Runs on port 8000 (production) or 8001 (local dev).

## Start

```bash
# From project root
cd api
uvicorn main:app --reload --port 8001
```

Swagger UI: http://localhost:8001/docs
ReDoc: http://localhost:8001/redoc

---

## Authentication

All protected endpoints require a `Bearer` token in the `Authorization` header:

```
Authorization: Bearer <token>
```

Tokens are issued by `POST /api/auth/login` and expire after **24 hours**.

**Dev fallback:** if `users.yaml` is missing, `admin` / `admin` always works.

---

## Multi-User Data Paths

Each user's data is stored under `data/{username}/`:

```
data/
  admin/
    card_prices_summary.csv
    card_prices_results.json
    price_history.json
    portfolio_history.json
    card_archive.csv
  josh/
    ...
  master_db/
    young_guns.csv
    yg_price_history.json
    nhl_stats.json
    nhl_standings.json
```

---

## Endpoints

### Auth — `/api/auth`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/auth/login` | No | Login with username + password. Returns JWT token. |
| GET | `/api/auth/me` | Yes | Returns current user's username, display name, and role. |
| POST | `/api/auth/logout` | No | Client-side logout (no server state). |

**Login request:**
```json
{ "username": "admin", "password": "admin" }
```
**Login response:**
```json
{ "token": "<jwt>", "username": "admin" }
```

---

### Cards — `/api/cards`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/cards` | Yes | All cards in the user's collection with fair value, trend, confidence, etc. |
| POST | `/api/cards` | Yes | Add a new card manually. |
| PATCH | `/api/cards/update?name=` | Yes | Update a card's fair value, cost basis, tags, etc. |
| DELETE | `/api/cards/archive?name=` | Yes | Soft-delete a card (move to archive). |
| POST | `/api/cards/restore?name=` | Yes | Restore a card from archive. |
| GET | `/api/cards/detail?name=` | Yes | Full detail for one card: price history, raw sales, image URL. |
| POST | `/api/cards/scrape?name=` | Yes | Trigger a rescrape for one card (runs in background). |
| POST | `/api/cards/fetch-image?name=` | Yes | Extract and cache eBay card image. |
| GET | `/api/cards/archive` | Yes | List all archived cards. |
| GET | `/api/cards/portfolio-history` | Yes | Portfolio total value over time. |
| GET | `/api/cards/card-of-the-day` | Yes | Random card with above-average value. |
| POST | `/api/cards/bulk-import` | Yes | Upload a CSV file to add multiple cards at once. |

> **Note:** Card names contain special characters (`[`, `]`, `#`, `/`) so all endpoints use **query params** (`?name=`) instead of path params to avoid routing issues.

**GET /api/cards response shape:**
```json
{
  "cards": [
    {
      "card_name": "2023-24 Upper Deck - Young Guns #201 - Connor Bedard",
      "player": "Connor Bedard",
      "year": "2023-24",
      "set_name": "Upper Deck",
      "grade": "",
      "fair_value": 45.00,
      "cost_basis": 30.00,
      "trend": "up",
      "confidence": "high",
      "num_sales": 12,
      "last_scraped": "2024-01-15",
      "tags": "rookie,hot",
      "purchase_date": "2023-10-01"
    }
  ]
}
```

---

### Stats — `/api/stats`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/stats/alerts` | Yes | Market movers — cards with significant price changes. |
| POST | `/api/stats/trigger-scrape` | Yes | Dispatch the `daily_scrape` GitHub Actions workflow. Requires `GITHUB_TOKEN` env var. |
| GET | `/api/stats/scrape-status` | Yes | Poll the latest GitHub Actions run status (for the progress modal). |

---

### Master DB — `/api/master-db`

Young Guns market database endpoints (shared across all users).

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/master-db` | Yes | All Young Guns cards with graded prices. Supports `?search=` query param. |
| GET | `/api/master-db/market-movers` | Yes | Top gainers and losers by price change. |
| GET | `/api/master-db/price-history/{card_name}` | Yes | Price history for a specific YG card. |
| GET | `/api/master-db/yg-price-history?name=` | Yes | Price history via query param (avoids special char routing issues). |
| GET | `/api/master-db/portfolio-history` | Yes | YG portfolio total value over time. |
| GET | `/api/master-db/nhl-stats` | Yes | Young Guns cards merged with current NHL player stats. |
| GET | `/api/master-db/seasonal-trends` | Yes | Monthly average YG prices by season. |
| GET | `/api/master-db/grading-lookup/{player_name}` | Yes | Graded price comparison for a player's YG card. |
| POST | `/api/master-db/scrape?player=&season=` | Yes | Trigger scrape for a specific YG card (background task). |
| PATCH | `/api/master-db/ownership?player=&season=` | Yes | Mark a YG card as owned with cost basis and purchase date. |

---

### Admin — `/api/admin`

Requires `admin` role. Regular users get 403 Forbidden.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/admin/users` | Admin | List all users (usernames, display names, roles). |
| POST | `/api/admin/users` | Admin | Create a new user with username, password, display name. |
| DELETE | `/api/admin/users/{username}` | Admin | Delete a user (cannot delete yourself). |
| PATCH | `/api/admin/users/{username}/password` | Admin | Change a user's password. |

---

### Scan — `/api/scan`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/scan/analyze` | Yes | Upload front (required) and back (optional) card images. Claude Vision extracts player, set, year, card number, grade, parallel, serial, confidence. |

**Request:** `multipart/form-data` with fields `front` (file) and optionally `back` (file).

**Response:**
```json
{
  "player_name": "Connor Bedard",
  "year": "2023-24",
  "brand": "Upper Deck",
  "subset": "Young Guns",
  "card_number": "201",
  "parallel": "",
  "serial_number": "",
  "grade": "",
  "confidence": "high",
  "is_sports_card": true,
  "validation_reason": "Clear front image with player name visible",
  "raw_text": "...",
  "parse_error": null
}
```

---

## Health Check

```
GET /api/health → { "status": "ok" }
```
