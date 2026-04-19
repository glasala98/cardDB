"""
Reporting API — read-only endpoints authenticated via X-API-Key header.

Designed for external reporting / analytics sites. All responses are JSON.
CORS is open (*) on this sub-app so any origin can call it with the API key.

Endpoints:
  GET /market-movers        — cards with biggest price change over the last N days
  GET /coverage             — % of catalog priced, by sport and tier
  GET /cards                — paginated card browse (mirrors /api/catalog)
  GET /cards/{id}/history   — full SCD Type 2 price history for one card
"""

import os
import math
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware

from db import get_db

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

_API_KEY = os.environ.get("REPORT_API_KEY", "")


def _check_key(x_api_key: Optional[str] = None):
    """Header dependency — accepts X-API-Key or ?api_key= query param."""
    from fastapi import Header
    return x_api_key


def require_api_key(
    x_api_key: Optional[str] = Query(None, alias="api_key"),
    header_key: Optional[str] = None,
):
    # Accept key from X-API-Key header OR ?api_key= query param
    pass  # resolved in app-level middleware below


# Use a simple FastAPI dependency instead of the above placeholder:
from fastapi import Header as _Header


def _api_key_dep(
    x_api_key: Optional[str] = _Header(None),
    api_key:   Optional[str] = Query(None),
):
    provided = x_api_key or api_key
    if not _API_KEY:
        raise HTTPException(503, detail="Reporting API not configured (REPORT_API_KEY missing)")
    if provided != _API_KEY:
        raise HTTPException(401, detail="Invalid API key")
    return provided


router = APIRouter(dependencies=[Depends(_api_key_dep)])


# ---------------------------------------------------------------------------
# /market-movers
# ---------------------------------------------------------------------------

@router.get("/market-movers")
def market_movers(
    sport:   Optional[str] = Query(None, description="NHL / NBA / NFL / MLB"),
    tier:    Optional[str] = Query(None, description="elite / staple / premium / stars / base"),
    days:    int           = Query(7, ge=1, le=90, description="Look-back window in days"),
    min_sales: int         = Query(3, ge=1, description="Min num_sales on current price"),
    limit:   int           = Query(50, ge=1, le=200),
):
    """Cards with the biggest absolute price change vs their price N days ago.

    Returns gainers and losers sorted by absolute % change descending.
    Only includes cards where both current and historical prices exist and
    num_sales >= min_sales (filters out illiquid/noise cards).
    """
    conditions = ["mp.fair_value > 0", "mp.num_sales >= %s", "mph_prev.fair_value IS NOT NULL",
                  "mp.fair_value != mph_prev.fair_value"]
    params: list = [min_sales]

    sport_filter = ""
    if sport:
        sport_filter = "AND cc.sport = %s"
        params.append(sport.upper())

    tier_filter = ""
    if tier:
        tier_filter = "AND cc.scrape_tier = %s"
        params.append(tier.lower())

    params.append(days)   # for the LATERAL interval
    params.append(limit)

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SET statement_timeout = '15s'")
        cur.execute(f"""
            SELECT
                cc.id,
                cc.player_name,
                cc.sport,
                cc.year,
                cc.set_name,
                cc.variant,
                cc.scrape_tier,
                cc.is_rookie,
                COALESCE(mp.image_url, '') AS image_url,
                mp.fair_value              AS current_price,
                mp.num_sales,
                mp.scraped_at              AS price_updated_at,
                mph_prev.fair_value        AS prev_price,
                mph_prev.scraped_at        AS prev_price_date,
                ROUND(
                    (mp.fair_value - mph_prev.fair_value)
                    / mph_prev.fair_value * 100, 1
                )                          AS pct_change,
                mp.fair_value - mph_prev.fair_value AS abs_change
            FROM market_prices mp
            JOIN card_catalog cc ON cc.id = mp.card_catalog_id
            LEFT JOIN LATERAL (
                SELECT fair_value, scraped_at
                FROM market_price_history
                WHERE card_catalog_id = mp.card_catalog_id
                  AND scraped_at < NOW() - (INTERVAL '1 day' * %s)
                  AND fair_value > 0
                ORDER BY scraped_at DESC
                LIMIT 1
            ) mph_prev ON true
            WHERE mp.fair_value > 0
              AND mp.num_sales >= %s
              AND mph_prev.fair_value IS NOT NULL
              AND mp.fair_value != mph_prev.fair_value
              AND NOT COALESCE(mp.ignored, FALSE)
              {sport_filter}
              {tier_filter}
            ORDER BY ABS(mp.fair_value - mph_prev.fair_value) / mph_prev.fair_value DESC
            LIMIT %s
        """, [days, min_sales] + ([sport.upper()] if sport else []) + ([tier.lower()] if tier else []) + [limit])

        cols = [d[0] for d in cur.description]
        rows = []
        for r in cur.fetchall():
            row = dict(zip(cols, r))
            for f in ("current_price", "prev_price", "abs_change"):
                if row[f] is not None:
                    row[f] = float(row[f])
            row["pct_change"] = float(row["pct_change"]) if row["pct_change"] is not None else None
            for f in ("price_updated_at", "prev_price_date"):
                if row[f]:
                    row[f] = row[f].isoformat()
            rows.append(row)

    gainers = [r for r in rows if r["pct_change"] and r["pct_change"] > 0]
    losers  = [r for r in rows if r["pct_change"] and r["pct_change"] < 0]
    return {
        "window_days": days,
        "gainers": sorted(gainers, key=lambda r: r["pct_change"], reverse=True),
        "losers":  sorted(losers,  key=lambda r: r["pct_change"]),
        "total":   len(rows),
    }


# ---------------------------------------------------------------------------
# /coverage
# ---------------------------------------------------------------------------

@router.get("/coverage")
def coverage():
    """Catalog coverage: how many cards are priced, by sport and tier."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SET statement_timeout = '10s'")

        cur.execute("""
            SELECT
                cc.sport,
                cc.scrape_tier,
                COUNT(*)                                    AS total_cards,
                COUNT(mp.id) FILTER (WHERE mp.fair_value > 0
                    AND NOT COALESCE(mp.ignored, FALSE))    AS priced_cards,
                AVG(mp.fair_value) FILTER (WHERE mp.fair_value > 0
                    AND NOT COALESCE(mp.ignored, FALSE))    AS avg_price,
                MAX(mp.fair_value)                          AS max_price,
                COALESCE(SUM(mp.num_sales), 0)             AS total_sales,
                MAX(mp.scraped_at)                          AS last_scraped
            FROM card_catalog cc
            LEFT JOIN market_prices mp ON mp.card_catalog_id = cc.id
            GROUP BY cc.sport, cc.scrape_tier
            ORDER BY cc.sport, cc.scrape_tier
        """)
        cols = [d[0] for d in cur.description]
        rows = []
        for r in cur.fetchall():
            row = dict(zip(cols, r))
            row["avg_price"]    = float(row["avg_price"])    if row["avg_price"]    else None
            row["max_price"]    = float(row["max_price"])    if row["max_price"]    else None
            row["total_sales"]  = int(row["total_sales"])    if row["total_sales"]  else 0
            row["pct_priced"]   = round(row["priced_cards"] / row["total_cards"] * 100, 1) if row["total_cards"] else 0.0
            row["last_scraped"] = row["last_scraped"].isoformat() if row["last_scraped"] else None
            rows.append(row)

    # Roll up totals
    overall_total  = sum(r["total_cards"]  for r in rows)
    overall_priced = sum(r["priced_cards"] for r in rows)
    return {
        "by_sport_tier": rows,
        "totals": {
            "total_cards":  overall_total,
            "priced_cards": overall_priced,
            "pct_priced":   round(overall_priced / overall_total * 100, 1) if overall_total else 0.0,
        },
    }


# ---------------------------------------------------------------------------
# /cards  (browse)
# ---------------------------------------------------------------------------

SORT_COLS = {
    "player_name": "cc.player_name",
    "year":        "cc.year",
    "set_name":    "cc.set_name",
    "fair_value":  "mp.fair_value",
    "num_sales":   "mp.num_sales",
    "sport":       "cc.sport",
    "pct_change":  "pct_change",
}


@router.get("/cards")
def browse_cards(
    response:    Response,
    search:      Optional[str]  = Query(None),
    player_name: Optional[str]  = Query(None),
    sport:       Optional[str]  = Query(None),
    year:        Optional[str]  = Query(None),
    set_name:    Optional[str]  = Query(None),
    tier:        Optional[str]  = Query(None),
    is_rookie:   Optional[bool] = Query(None),
    has_price:   Optional[bool] = Query(None),
    sort:        str            = Query("fair_value"),
    dir:         str            = Query("desc"),
    page:        int            = Query(1, ge=1),
    per_page:    int            = Query(25, ge=1, le=200),
):
    """Paginated browse of card catalog with current prices and 7-day delta."""
    sort_col = SORT_COLS.get(sort, "mp.fair_value")
    sort_dir = "DESC" if dir.lower() == "desc" else "ASC"

    where_parts: list[str] = ["(mp.ignored IS NULL OR mp.ignored = FALSE)"]
    params: list = []

    if sport:
        where_parts.append("cc.sport = %s"); params.append(sport.upper())
    if year:
        where_parts.append("cc.year = %s"); params.append(year)
    if set_name:
        where_parts.append("cc.set_name ILIKE %s"); params.append(f"%{set_name}%")
    if player_name:
        where_parts.append("cc.player_name ILIKE %s"); params.append(f"%{player_name}%")
    if search:
        where_parts.append("(cc.player_name ILIKE %s OR cc.set_name ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    if is_rookie is True:
        where_parts.append("cc.is_rookie = TRUE")
    elif is_rookie is False:
        where_parts.append("cc.is_rookie = FALSE")
    if tier:
        where_parts.append("cc.scrape_tier = %s"); params.append(tier.lower())
    if has_price is True:
        where_parts.append("mp.fair_value > 0")
    elif has_price is False:
        where_parts.append("mp.id IS NULL")

    where_sql = "WHERE " + " AND ".join(where_parts)
    offset    = (page - 1) * per_page

    # pct_change is computed from prev_value inline so it can be sorted on
    select_extras = """
        CASE WHEN mp.prev_value > 0
             THEN ROUND((mp.fair_value - mp.prev_value) / mp.prev_value * 100, 1)
             END AS pct_change
    """

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SET statement_timeout = '10s'")

        cur.execute(f"SELECT COUNT(*) FROM card_catalog cc LEFT JOIN market_prices mp ON mp.card_catalog_id = cc.id {where_sql}", params)
        total = cur.fetchone()[0]

        cur.execute(f"""
            SELECT cc.id, cc.sport, cc.year, cc.brand, cc.set_name, cc.card_number,
                   cc.player_name, cc.team, cc.variant, cc.print_run, cc.is_rookie,
                   cc.is_parallel, cc.scrape_tier,
                   mp.fair_value, mp.prev_value, mp.trend, mp.confidence,
                   mp.num_sales, mp.scraped_at, COALESCE(mp.image_url, '') AS image_url,
                   {select_extras}
            FROM card_catalog cc
            LEFT JOIN market_prices mp ON mp.card_catalog_id = cc.id
            {where_sql}
            ORDER BY {sort_col} {sort_dir} NULLS LAST, cc.player_name ASC
            LIMIT %s OFFSET %s
        """, params + [per_page, offset])

        cols = [d[0] for d in cur.description]
        cards = []
        for row in cur.fetchall():
            r = dict(zip(cols, row))
            for k in ("fair_value", "prev_value", "pct_change"):
                if r[k] is not None:
                    r[k] = float(r[k])
            if r.get("scraped_at"):
                r["scraped_at"] = r["scraped_at"].isoformat()
            cards.append(r)

    response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=300"
    return {
        "cards":    cards,
        "total":    total,
        "page":     page,
        "pages":    math.ceil(total / per_page) if per_page else 1,
        "per_page": per_page,
    }


# ---------------------------------------------------------------------------
# /cards/{id}/history  — full SCD Type 2 history
# ---------------------------------------------------------------------------

@router.get("/cards/{catalog_id}/history")
def card_history(catalog_id: int, response: Response):
    """Full price history for one card using SCD Type 2 effective_from/effective_to."""
    with get_db() as conn:
        cur = conn.cursor()

        cur.execute("""
            SELECT cc.id, cc.sport, cc.year, cc.brand, cc.set_name, cc.card_number,
                   cc.player_name, cc.team, cc.variant, cc.print_run, cc.is_rookie,
                   cc.scrape_tier,
                   mp.fair_value, mp.prev_value, mp.trend, mp.confidence,
                   mp.num_sales, mp.scraped_at
            FROM card_catalog cc
            LEFT JOIN market_prices mp ON mp.card_catalog_id = cc.id
            WHERE cc.id = %s
        """, [catalog_id])
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Card not found")
        cols = [d[0] for d in cur.description]
        card = dict(zip(cols, row))
        for k in ("fair_value", "prev_value"):
            if card[k] is not None:
                card[k] = float(card[k])
        if card.get("scraped_at"):
            card["scraped_at"] = card["scraped_at"].isoformat()

        # SCD Type 2 history — effective_from / effective_to / is_current
        cur.execute("""
            SELECT
                scraped_at        AS effective_from,
                effective_to,
                is_current,
                fair_value,
                confidence,
                num_sales,
                min_price,
                max_price,
                source
            FROM market_price_history
            WHERE card_catalog_id = %s
            ORDER BY scraped_at ASC
        """, [catalog_id])
        hist_cols = [d[0] for d in cur.description]
        history = []
        for r in cur.fetchall():
            h = dict(zip(hist_cols, r))
            for f in ("fair_value", "min_price", "max_price"):
                if h[f] is not None:
                    h[f] = float(h[f])
            for f in ("effective_from", "effective_to"):
                if h[f]:
                    h[f] = h[f].isoformat()
            history.append(h)

    response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=3600"
    return {
        "card":    card,
        "history": history,
        "periods": len(history),
    }


# ---------------------------------------------------------------------------
# Mount as a standalone sub-app with open CORS (API key = the auth)
# ---------------------------------------------------------------------------

def build_report_app() -> FastAPI:
    """Return a FastAPI sub-app with its own open CORS for the report router."""
    app = FastAPI(
        title="CardDB Reporting API",
        description="Read-only reporting endpoints. Authenticate with X-API-Key header.",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],           # API key is the auth — no origin restriction
        allow_credentials=False,
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["X-API-Key", "Content-Type"],
    )
    app.include_router(router)
    return app
