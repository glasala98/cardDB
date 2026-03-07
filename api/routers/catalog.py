"""Card Catalog browse endpoints — paginated search across 2M+ cards."""

import math
from typing import Optional
from fastapi import APIRouter, Query

from db import get_db

router = APIRouter()

SORT_COLS = {
    "player_name": "cc.player_name",
    "year":        "cc.year",
    "set_name":    "cc.set_name",
    "card_number": "cc.card_number",
    "fair_value":  "mp.fair_value",
    "num_sales":   "mp.num_sales",
    "sport":       "cc.sport",
}


@router.get("")
def browse_catalog(
    search:    Optional[str]  = Query(None),
    sport:     Optional[str]  = Query(None),
    year:      Optional[str]  = Query(None),
    set_name:  Optional[str]  = Query(None),
    is_rookie: Optional[bool] = Query(None),
    has_price: Optional[bool] = Query(None),
    sort:      str            = Query("year"),
    dir:       str            = Query("desc"),
    page:      int            = Query(1, ge=1),
    per_page:  int            = Query(50, ge=1, le=200),
):
    """Paginated browse of card_catalog with optional market_prices join.

    Returns cards matching all supplied filters. Joins market_prices for
    fair_value / trend / confidence when available (LEFT JOIN so un-scraped
    cards still appear).

    Args:
        search:    Free-text search against player_name and set_name.
        sport:     Filter to one sport (NHL/NBA/NFL/MLB).
        year:      Exact year match (e.g. '2024-25' or '2024').
        set_name:  Partial set name match (case-insensitive).
        is_rookie: True/False filter on the is_rookie flag.
        has_price: True = only cards with a market price; False = only without.
        sort:      Column to sort by (player_name/year/set_name/card_number/fair_value/num_sales/sport).
        dir:       'asc' or 'desc'.
        page:      1-based page number.
        per_page:  Rows per page (max 200).

    Returns:
        Dict with keys: cards (list), total (int), page (int), pages (int), per_page (int).
    """
    sort_col = SORT_COLS.get(sort, "cc.year")
    sort_dir = "DESC" if dir.lower() == "desc" else "ASC"

    where_parts = []
    params = []

    if sport:
        where_parts.append("cc.sport = %s")
        params.append(sport.upper())

    if year:
        where_parts.append("cc.year = %s")
        params.append(year)

    if set_name:
        where_parts.append("cc.set_name ILIKE %s")
        params.append(f"%{set_name}%")

    if search:
        where_parts.append("(cc.player_name ILIKE %s OR cc.set_name ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])

    if is_rookie is True:
        where_parts.append("cc.is_rookie = TRUE")
    elif is_rookie is False:
        where_parts.append("cc.is_rookie = FALSE")

    if has_price is True:
        where_parts.append("mp.id IS NOT NULL")
    elif has_price is False:
        where_parts.append("mp.id IS NULL")

    # Always exclude admin-ignored price entries from public browse
    where_parts.append("(mp.ignored IS NULL OR mp.ignored = FALSE)")

    where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    base_query = f"""
        FROM card_catalog cc
        LEFT JOIN market_prices mp ON mp.card_catalog_id = cc.id
        {where_sql}
    """

    data_sql = f"""
        SELECT
            cc.id,
            cc.sport,
            cc.year,
            cc.brand,
            cc.set_name,
            cc.card_number,
            cc.player_name,
            cc.team,
            cc.variant,
            cc.print_run,
            cc.is_rookie,
            cc.is_parallel,
            cc.scrape_tier,
            mp.fair_value,
            mp.prev_value,
            mp.trend,
            mp.confidence,
            mp.num_sales,
            mp.scraped_at,
            COALESCE(mp.image_url, '') AS image_url
        {base_query}
        ORDER BY {sort_col} {sort_dir} NULLS LAST,
                 cc.player_name ASC
        LIMIT %s OFFSET %s
    """

    offset = (page - 1) * per_page

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SET statement_timeout = '8s'")

        # Use fast pg_class estimate when no filters are active; exact COUNT otherwise
        if where_parts:
            cur.execute(f"SELECT COUNT(*) {base_query}", params)
            total = cur.fetchone()[0]
        else:
            cur.execute("SELECT reltuples::bigint FROM pg_class WHERE relname = 'card_catalog'")
            total = cur.fetchone()[0] or 0

        cur.execute(data_sql, params + [per_page, offset])
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]

    cards = []
    for row in rows:
        r = dict(zip(cols, row))
        # Convert Decimal/datetime to JSON-safe types
        for k in ("fair_value", "prev_value"):
            if r[k] is not None:
                r[k] = float(r[k])
        if r.get("scraped_at"):
            r["scraped_at"] = r["scraped_at"].isoformat()
        cards.append(r)

    return {
        "cards":    cards,
        "total":    total,
        "page":     page,
        "pages":    math.ceil(total / per_page) if per_page else 1,
        "per_page": per_page,
    }


@router.get("/{catalog_id}/history")
def catalog_card_history(catalog_id: int):
    """Return price history for a single catalog card."""
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
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Card not found")
        cols = [d[0] for d in cur.description]
        card = dict(zip(cols, row))
        for k in ("fair_value", "prev_value"):
            if card[k] is not None:
                card[k] = float(card[k])
        if card.get("scraped_at"):
            card["scraped_at"] = card["scraped_at"].isoformat()

        cur.execute("""
            SELECT scraped_at, fair_value, confidence, num_sales, min_price, max_price
            FROM market_price_history
            WHERE card_catalog_id = %s
            ORDER BY scraped_at ASC
        """, [catalog_id])
        hist_cols = [d[0] for d in cur.description]
        history = []
        for r in cur.fetchall():
            h = dict(zip(hist_cols, r))
            h["fair_value"] = float(h["fair_value"]) if h["fair_value"] is not None else None
            h["min_price"]  = float(h["min_price"])  if h["min_price"]  is not None else None
            h["max_price"]  = float(h["max_price"])  if h["max_price"]  is not None else None
            h["scraped_at"] = h["scraped_at"].isoformat() if h["scraped_at"] else None
            history.append(h)

    return {"card": card, "history": history}


@router.get("/releases")
def new_releases(
    sport:   Optional[str] = Query(None),
    seasons: int           = Query(2, ge=1, le=5),
    limit:   int           = Query(60, ge=1, le=200),
):
    """Return recent sets grouped by (sport, year, set_name), filtered by card release year.

    Uses the card's year field (e.g. '2024-25', '2024') to determine recency —
    NOT the catalog import date — so that sets appear based on when they were
    actually released, not when we scraped them.

    Args:
        sport:   Filter to one sport.
        seasons: How many seasons back to include (1 = current only, 2 = last 2, etc.)
        limit:   Max number of sets to return.

    Returns:
        Dict with key 'sets', each entry containing sport/year/set_name/brand,
        card_count, priced_count, top_value, avg_value, indexed_at (ISO string),
        and top_cards (list of up to 5 cards with name + fair_value + is_rookie).
    """
    where_parts = [
        "CAST(SUBSTRING(cc.year FROM '^\\d+') AS INTEGER) >= EXTRACT(YEAR FROM NOW())::INTEGER - %s"
    ]
    params: list = [seasons]

    if sport:
        where_parts.append("cc.sport = %s")
        params.append(sport.upper())

    where_sql = "WHERE " + " AND ".join(where_parts)

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SET statement_timeout = '10s'")

        # Aggregate per set
        cur.execute(f"""
            SELECT
                cc.sport,
                cc.year,
                cc.set_name,
                cc.brand,
                COUNT(*)                                                          AS card_count,
                COUNT(mp.id)                                                      AS priced_count,
                MAX(mp.fair_value)                                                AS top_value,
                AVG(mp.fair_value)                                                AS avg_value,
                AVG(mp.prev_value) FILTER (WHERE mp.prev_value > 0)              AS avg_prev_value,
                CAST(SUBSTRING(cc.year FROM '^\\d+') AS INTEGER)                 AS year_num,
                COALESCE(SUM(mp.num_sales), 0)                                    AS total_sales,
                MAX(mp.scraped_at)                                                AS last_scraped,
                COUNT(*) FILTER (WHERE cc.scrape_tier = 'staple')                AS staple_count,
                COUNT(*) FILTER (WHERE cc.scrape_tier IN ('staple','premium'))   AS flagship_count
            FROM card_catalog cc
            LEFT JOIN market_prices mp ON mp.card_catalog_id = cc.id
            {where_sql}
            GROUP BY cc.sport, cc.year, cc.set_name, cc.brand
            ORDER BY
                year_num DESC,
                -- Populated sets (any priced cards) always before empty shells
                CASE WHEN COUNT(mp.id) FILTER (WHERE mp.fair_value > 0
                                                 AND NOT COALESCE(mp.ignored, FALSE)) > 0
                     THEN 0 ELSE 1 END,
                COUNT(*) FILTER (WHERE cc.scrape_tier IN ('staple','premium')) DESC,
                COALESCE(SUM(mp.num_sales), 0) DESC,
                MAX(mp.fair_value) DESC NULLS LAST,
                COUNT(mp.id) DESC
            LIMIT %s
        """, params + [limit])

        set_cols = [d[0] for d in cur.description]
        set_rows = [dict(zip(set_cols, r)) for r in cur.fetchall()]

        # For each set, fetch top 5 UNIQUE players by best card fair_value
        result_sets = []
        for s in set_rows:
            cur.execute("""
                SELECT player_name, is_rookie, variant, fair_value, id
                FROM (
                    SELECT DISTINCT ON (cc.player_name)
                        cc.player_name, cc.is_rookie, cc.variant, mp.fair_value, cc.id
                    FROM card_catalog cc
                    JOIN market_prices mp ON mp.card_catalog_id = cc.id
                    WHERE cc.sport = %s AND cc.year = %s AND cc.set_name = %s
                      AND mp.fair_value IS NOT NULL
                      AND NOT COALESCE(mp.ignored, FALSE)
                    ORDER BY cc.player_name, mp.fair_value DESC
                ) deduped
                ORDER BY fair_value DESC
                LIMIT 5
            """, [s["sport"], s["year"], s["set_name"]])
            top_cards = [
                {
                    "id":          r[4],
                    "player_name": r[0],
                    "is_rookie":   r[1],
                    "variant":     r[2],
                    "fair_value":  float(r[3]) if r[3] is not None else None,
                }
                for r in cur.fetchall()
            ]

            avg_val  = float(s["avg_value"])      if s["avg_value"]      is not None else None
            avg_prev = float(s["avg_prev_value"]) if s["avg_prev_value"] is not None else None
            if avg_val is not None and avg_prev and avg_prev > 0:
                momentum_pct = round((avg_val - avg_prev) / avg_prev * 100, 1)
            else:
                momentum_pct = None

            result_sets.append({
                "sport":        s["sport"],
                "year":         s["year"],
                "set_name":     s["set_name"],
                "brand":        s["brand"],
                "card_count":   s["card_count"],
                "priced_count": s["priced_count"],
                "top_value":    float(s["top_value"]) if s["top_value"] is not None else None,
                "avg_value":    avg_val,
                "momentum_pct": momentum_pct,
                "total_sales":    int(s["total_sales"])    if s["total_sales"]    else 0,
                "staple_count":   int(s["staple_count"])   if s["staple_count"]   else 0,
                "flagship_count": int(s["flagship_count"]) if s["flagship_count"] else 0,
                "top_cards":      top_cards,
            })

    return {"sets": result_sets}


@router.get("/filters")
def catalog_filters(
    sport: Optional[str] = Query(None),
    year:  Optional[str] = Query(None),
):
    """Return unique sports, years, and set names for filter dropdowns.

    Sets are scoped by both sport and year when supplied, so the dropdown
    only shows sets that actually exist for the selected sport+year combo.

    Args:
        sport: Scope years and sets to this sport.
        year:  Scope sets to this year (requires sport to be useful).

    Returns:
        Dict with keys: sports (list), years (list desc), sets (list).
    """
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SET statement_timeout = '8s'")

        cur.execute("SELECT DISTINCT sport FROM card_catalog ORDER BY sport")
        sports = [r[0] for r in cur.fetchall()]

        # Only load years/sets when a sport is selected — too expensive unfiltered
        if not sport:
            return {"sports": sports, "years": [], "sets": []}

        cur.execute(
            "SELECT DISTINCT year FROM card_catalog WHERE sport = %s ORDER BY year DESC",
            [sport.upper()]
        )
        years = [r[0] for r in cur.fetchall()]

        set_conds = ["sport = %s"]
        set_params = [sport.upper()]
        if year:
            set_conds.append("year = %s")
            set_params.append(year)
        set_where = "WHERE " + " AND ".join(set_conds)
        cur.execute(
            f"""SELECT set_name, COUNT(*) cnt
                FROM card_catalog {set_where}
                GROUP BY set_name
                ORDER BY cnt DESC
                LIMIT 300""",
            set_params
        )
        sets = [r[0] for r in cur.fetchall()]

    return {"sports": sports, "years": years, "sets": sets}
