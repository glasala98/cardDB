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
            mp.fair_value,
            mp.prev_value,
            mp.trend,
            mp.confidence,
            mp.num_sales,
            mp.scraped_at
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
