"""Card Catalog browse endpoints — paginated search across 2M+ cards."""

import json
import math
import os
import threading
from datetime import date, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, Request, Response
from cachetools import TTLCache

from db import get_db

# In-process TTL caches (thread-safe via locks)
_releases_cache: TTLCache = TTLCache(maxsize=20,  ttl=300)   # 5 min
_filters_cache:  TTLCache = TTLCache(maxsize=50,  ttl=600)   # 10 min
_ai_cache:       TTLCache = TTLCache(maxsize=200, ttl=300)   # 5 min, keyed by query
_browse_cache:   TTLCache = TTLCache(maxsize=500, ttl=60)    # 60s — keyed by full query string
_cache_lock = threading.Lock()

# Live-price safety: card result cache + rate limiting
_live_cache:      TTLCache = TTLCache(maxsize=500, ttl=3600)  # 1h per card_id
_live_ip_times:   dict     = {}   # ip -> last request timestamp
_live_global_times: list   = []   # rolling window of all request timestamps
_live_lock = threading.Lock()
_LIVE_PER_IP_COOLDOWN  = 10   # seconds between requests from same IP
_LIVE_GLOBAL_RPM       = 30   # max live-price requests per minute across all users

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

# Multi-column relevance sort: tier → has price → sales volume → value → rookie → name
FEATURED_ORDER = """
    CASE cc.scrape_tier WHEN 'staple' THEN 3 WHEN 'premium' THEN 2 WHEN 'stars' THEN 1 ELSE 0 END DESC,
    CASE WHEN mp.fair_value IS NOT NULL THEN 1 ELSE 0 END DESC,
    COALESCE(mp.num_sales, 0) DESC,
    COALESCE(mp.fair_value, 0) DESC,
    CASE WHEN cc.is_rookie THEN 1 ELSE 0 END DESC,
    cc.player_name ASC
"""


@router.get("")
def browse_catalog(
    response:    Response,
    search:      Optional[str]  = Query(None),
    fts:         Optional[str]  = Query(None),
    player_name: Optional[str]  = Query(None),
    sport:       Optional[str]  = Query(None),
    year:        Optional[str]  = Query(None),
    set_name:    Optional[str]  = Query(None),
    variant:     Optional[str]  = Query(None),
    is_rookie:   Optional[bool] = Query(None),
    card_number: Optional[str]  = Query(None),
    tier:        Optional[str]  = Query(None),
    has_price:   Optional[bool] = Query(None),
    sort:        str            = Query("featured"),
    dir:         str            = Query("desc"),
    page:        int            = Query(1, ge=1),
    per_page:    int            = Query(25, ge=1, le=200),
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
    # Server-side cache — keyed by all query params. Skipped for authenticated
    # or highly-specific queries (search/fts/player) since those are less repeated.
    _browse_key = f"{search}|{fts}|{player_name}|{sport}|{year}|{set_name}|{variant}|{is_rookie}|{card_number}|{tier}|{has_price}|{sort}|{dir}|{page}|{per_page}"
    with _cache_lock:
        if _browse_key in _browse_cache:
            return _browse_cache[_browse_key]

    use_featured = (sort == "featured")
    sort_col = SORT_COLS.get(sort, "cc.year") if not use_featured else None
    sort_dir = "DESC" if dir.lower() == "desc" else "ASC"

    where_parts = []
    params = []
    rank_params = []  # extra params injected into ORDER BY (after WHERE params)

    if sport:
        where_parts.append("cc.sport = %s")
        params.append(sport.upper())

    if year:
        where_parts.append("cc.year = %s")
        params.append(year)

    if set_name:
        where_parts.append("cc.set_name ILIKE %s")
        params.append(f"%{set_name}%")

    if player_name:
        where_parts.append("cc.player_name ILIKE %s")
        params.append(f"%{player_name}%")

    if variant:
        where_parts.append("cc.variant ILIKE %s")
        params.append(f"%{variant}%")

    if card_number:
        where_parts.append("cc.card_number ILIKE %s")
        params.append(f"%{card_number}%")

    if search:
        # Use FTS (search_vector GIN index) for multi-word/natural-language queries
        # plus ILIKE fallback so short names and stop-word-only terms still match.
        where_parts.append("""(
            cc.search_vector @@ plainto_tsquery('english', %s)
            OR cc.player_name ILIKE %s
            OR cc.set_name ILIKE %s
        )""")
        params.extend([search, f"%{search}%", f"%{search}%"])

    if fts:
        # Multi-term AND: every token must appear in at least one of the key fields.
        # "Connor McDavid Young Guns" → each word matched independently so
        # "Connor"/"McDavid" hits player_name and "Young"/"Guns" hits variant.
        for token in fts.split():
            if len(token) >= 2:  # skip single chars
                where_parts.append(
                    "(cc.player_name ILIKE %s OR cc.set_name ILIKE %s OR cc.variant ILIKE %s)"
                )
                params.extend([f"%{token}%", f"%{token}%", f"%{token}%"])

    if is_rookie is True:
        where_parts.append("cc.is_rookie = TRUE")
    elif is_rookie is False:
        where_parts.append("cc.is_rookie = FALSE")

    if tier:
        where_parts.append("cc.scrape_tier = %s")
        params.append(tier.lower())

    if has_price is True:
        where_parts.append("mp.id IS NOT NULL")
    elif has_price is False:
        where_parts.append("mp.id IS NULL")

    # Always exclude admin-ignored price entries from public browse
    where_parts.append("(mp.ignored IS NULL OR mp.ignored = FALSE)")

    where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    # When search is active, prepend FTS rank so best matches sort first.
    if search:
        tail = FEATURED_ORDER if use_featured else f"{sort_col} {sort_dir} NULLS LAST, cc.player_name ASC"
        order_sql = (
            f"ORDER BY ts_rank(cc.search_vector, plainto_tsquery('english', %s)) DESC, {tail}"
        )
        rank_params = [search]
    elif use_featured:
        order_sql = f"ORDER BY {FEATURED_ORDER}"
        rank_params = []
    else:
        order_sql = f"ORDER BY {sort_col} {sort_dir} NULLS LAST, cc.player_name ASC"
        rank_params = []

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
        {order_sql}
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

        cur.execute(data_sql, params + rank_params + [per_page, offset])
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

    # Cache browse results in the browser / CDN:
    # 30s fresh + 5 min stale-while-revalidate for filtered queries,
    # 60s + 10 min for the default unfiltered view.
    if where_parts:
        response.headers["Cache-Control"] = "public, max-age=30, stale-while-revalidate=300"
    else:
        response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=600"

    result = {
        "cards":    cards,
        "total":    total,
        "page":     page,
        "pages":    math.ceil(total / per_page) if per_page else 1,
        "per_page": per_page,
    }
    with _cache_lock:
        _browse_cache[_browse_key] = result
    return result


@router.get("/{catalog_id}/history")
def catalog_card_history(catalog_id: int, response: Response):
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

    # History is scraped at most daily — cache for 10 min, stale-while-revalidate 1h
    response.headers["Cache-Control"] = "public, max-age=600, stale-while-revalidate=3600"
    return {"card": card, "history": history}


@router.get("/{catalog_id}/raw-sales")
def catalog_raw_sales(
    catalog_id:  int,
    source:      List[str]      = Query(default=[]),
    grade:       Optional[str]  = Query(None),
    serial_only: bool           = Query(False),
    date_from:   Optional[date] = Query(None),
    date_to:     Optional[date] = Query(None),
    price_min:   Optional[float]= Query(None, ge=0),
    price_max:   Optional[float]= Query(None),
    sort:        str            = Query("date_desc"),
    limit:       int            = Query(50, ge=1, le=200),
    offset:      int            = Query(0, ge=0),
):
    """Return paginated sales from market_raw_sales for a catalog card, with filters."""
    ORDER_MAP = {
        "date_desc":  "sold_date DESC NULLS LAST",
        "date_asc":   "sold_date ASC  NULLS LAST",
        "price_desc": "price_val DESC",
        "price_asc":  "price_val ASC",
    }
    order = ORDER_MAP.get(sort, "sold_date DESC NULLS LAST")

    conditions = ["card_catalog_id = %s"]
    params: list = [catalog_id]

    if source:
        conditions.append("source = ANY(%s)")
        params.append([s.lower() for s in source])
    if grade:
        conditions.append("grade ILIKE %s")
        params.append(f"%{grade}%")
    if serial_only:
        conditions.append("serial_number IS NOT NULL")
    if date_from:
        conditions.append("sold_date >= %s"); params.append(date_from)
    if date_to:
        conditions.append("sold_date <= %s"); params.append(date_to)
    if price_min is not None:
        conditions.append("price_val >= %s"); params.append(price_min)
    if price_max is not None:
        conditions.append("price_val <= %s"); params.append(price_max)

    where = " AND ".join(conditions)

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT COUNT(*), AVG(price_val), MAX(price_val), MIN(price_val)
            FROM market_raw_sales WHERE {where} AND price_val > 0
        """, params)
        agg = cur.fetchone()
        total    = agg[0]
        avg_val  = float(agg[1]) if agg[1] is not None else None
        high_val = float(agg[2]) if agg[2] is not None else None
        low_val  = float(agg[3]) if agg[3] is not None else None

        cur.execute(f"""
            SELECT id, sold_date, price_val, shipping_val, title, source,
                   grade, grade_company, grade_numeric,
                   serial_number, print_run,
                   lot_url, image_url,
                   hammer_price, buyer_premium_pct, is_auction,
                   scraped_at
            FROM market_raw_sales
            WHERE {where}
            ORDER BY {order}
            LIMIT %s OFFSET %s
        """, params + [limit, offset])
        cols = [d[0] for d in cur.description]
        cutoff = date.today() - timedelta(days=90)
        sales = []
        for r in cur.fetchall():
            s = dict(zip(cols, r))
            s["price_val"]     = float(s["price_val"])     if s["price_val"]     is not None else None
            s["shipping_val"]  = float(s["shipping_val"])  if s["shipping_val"]  is not None else None
            s["grade_numeric"] = float(s["grade_numeric"]) if s["grade_numeric"] is not None else None
            s["hammer_price"]  = float(s["hammer_price"])  if s["hammer_price"]  is not None else None
            s["sold_date"]     = s["sold_date"].isoformat()  if s["sold_date"]  else None
            s["scraped_at"]    = s["scraped_at"].isoformat() if s["scraped_at"] else None
            s["exclusive"]     = (date.fromisoformat(s["sold_date"]) < cutoff) if s["sold_date"] else False
            sales.append(s)

    return {
        "sales":  sales,
        "total":  total,
        "limit":  limit,
        "offset": offset,
        "stats":  {"avg": avg_val, "high": high_val, "low": low_val},
    }


@router.get("/releases")
def new_releases(
    sport:   Optional[str] = Query(None),
    seasons: int           = Query(2, ge=1, le=5),
    limit:   int           = Query(60, ge=1, le=200),
):  # noqa: C901
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
    cache_key = f"releases|{sport}|{seasons}|{limit}"
    with _cache_lock:
        if cache_key in _releases_cache:
            return _releases_cache[cache_key]

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
            HAVING COUNT(mp.id) FILTER (WHERE mp.fair_value > 0
                                          AND NOT COALESCE(mp.ignored, FALSE)) > 0
            ORDER BY
                year_num DESC,
                COUNT(*) FILTER (WHERE cc.scrape_tier IN ('staple','premium')) DESC,
                COALESCE(SUM(mp.num_sales), 0) DESC,
                MAX(mp.fair_value) DESC NULLS LAST,
                COUNT(mp.id) DESC
            LIMIT %s
        """, params + [limit])

        set_cols = [d[0] for d in cur.description]
        set_rows = [dict(zip(set_cols, r)) for r in cur.fetchall()]

        # Batch fetch 7-day price delta from market_price_history for all returned sets
        volatility_lookup: dict = {}
        if set_rows:
            vol_sport_filter = "AND cc.sport = %s" if sport else ""
            vol_params = [seasons] + ([sport.upper()] if sport else [])
            cur.execute(f"""
                SELECT cc.sport, cc.year, cc.set_name,
                       AVG(mph.fair_value) FILTER (
                           WHERE mph.scraped_at >= NOW() - INTERVAL '7 days'
                       ) AS avg_7d,
                       AVG(mph.fair_value) FILTER (
                           WHERE mph.scraped_at >= NOW() - INTERVAL '14 days'
                             AND mph.scraped_at <  NOW() - INTERVAL '7 days'
                       ) AS avg_prev_7d
                FROM market_price_history mph
                JOIN card_catalog cc ON cc.id = mph.card_catalog_id
                WHERE mph.fair_value > 0
                  AND mph.scraped_at >= NOW() - INTERVAL '14 days'
                  AND CAST(SUBSTRING(cc.year FROM '^\\d+') AS INTEGER)
                      >= EXTRACT(YEAR FROM NOW())::INTEGER - %s
                  {vol_sport_filter}
                GROUP BY cc.sport, cc.year, cc.set_name
            """, vol_params)
            for row in cur.fetchall():
                vsport, vyear, vset, avg_7d, avg_prev_7d = row
                if avg_7d is not None and avg_prev_7d and avg_prev_7d > 0:
                    delta = round((float(avg_7d) - float(avg_prev_7d)) / float(avg_prev_7d) * 100, 1)
                else:
                    delta = None
                volatility_lookup[f"{vsport}|{vyear}|{vset}"] = delta

        # Batch-fetch top 5 unique players per set in ONE query (replaces N round-trips)
        top_cards_by_set: dict = {}
        if set_rows:
            # Build VALUES list for all (sport, year, set_name) keys
            values_sql = ",".join(["(%s,%s,%s)"] * len(set_rows))
            set_params = []
            for s in set_rows:
                set_params.extend([s["sport"], s["year"], s["set_name"]])

            cur.execute(f"""
                WITH deduped AS (
                    SELECT DISTINCT ON (cc.sport, cc.year, cc.set_name, cc.player_name)
                        cc.sport, cc.year, cc.set_name,
                        cc.player_name, cc.is_rookie, cc.variant, cc.id, mp.fair_value
                    FROM card_catalog cc
                    JOIN market_prices mp ON mp.card_catalog_id = cc.id
                    WHERE (cc.sport, cc.year, cc.set_name) IN (VALUES {values_sql})
                      AND mp.fair_value IS NOT NULL
                      AND NOT COALESCE(mp.ignored, FALSE)
                    ORDER BY cc.sport, cc.year, cc.set_name, cc.player_name, mp.fair_value DESC
                ),
                ranked AS (
                    SELECT *,
                           ROW_NUMBER() OVER (
                               PARTITION BY sport, year, set_name
                               ORDER BY fair_value DESC
                           ) AS rn
                    FROM deduped
                )
                SELECT sport, year, set_name, player_name, is_rookie, variant, id, fair_value
                FROM ranked
                WHERE rn <= 5
                ORDER BY sport, year, set_name, fair_value DESC
            """, set_params)

            for row in cur.fetchall():
                vsport, vyear, vset, player, is_rookie, variant, cid, fv = row
                key = f"{vsport}|{vyear}|{vset}"
                top_cards_by_set.setdefault(key, []).append({
                    "id":          cid,
                    "player_name": player,
                    "is_rookie":   is_rookie,
                    "variant":     variant,
                    "fair_value":  float(fv) if fv is not None else None,
                })

        result_sets = []
        for s in set_rows:
            avg_val  = float(s["avg_value"])      if s["avg_value"]      is not None else None
            avg_prev = float(s["avg_prev_value"]) if s["avg_prev_value"] is not None else None
            momentum_pct = round((avg_val - avg_prev) / avg_prev * 100, 1) if (
                avg_val is not None and avg_prev and avg_prev > 0
            ) else None

            vkey = f"{s['sport']}|{s['year']}|{s['set_name']}"
            result_sets.append({
                "sport":          s["sport"],
                "year":           s["year"],
                "set_name":       s["set_name"],
                "brand":          s["brand"],
                "card_count":     s["card_count"],
                "priced_count":   s["priced_count"],
                "top_value":      float(s["top_value"]) if s["top_value"] is not None else None,
                "avg_value":      avg_val,
                "momentum_pct":   momentum_pct,
                "delta_7d_pct":   volatility_lookup.get(vkey),
                "total_sales":    int(s["total_sales"])    if s["total_sales"]    else 0,
                "staple_count":   int(s["staple_count"])   if s["staple_count"]   else 0,
                "flagship_count": int(s["flagship_count"]) if s["flagship_count"] else 0,
                "top_cards":      top_cards_by_set.get(vkey, []),
            })

    result = {"sets": result_sets}
    with _cache_lock:
        _releases_cache[cache_key] = result
    return result


@router.get("/sealed-products")
def catalog_sealed_products(
    sport:    Optional[str] = Query(None),
    year:     Optional[str] = Query(None),
    set_name: Optional[str] = Query(None),
):
    """Return sealed product info (MSRP, pack config, odds) for matching sets.

    Args:
        sport:    Filter to one sport (NHL/NBA/NFL/MLB).
        year:     Filter to one year (e.g. '2024-25').
        set_name: Partial set name match (case-insensitive).

    Returns:
        Dict with key 'products' — list of sealed product rows, each with
        an 'odds' list of {card_type, odds_ratio} entries.
    """
    where_parts = []
    params = []

    if sport:
        where_parts.append("sp.sport = %s")
        params.append(sport.upper())
    if year:
        where_parts.append("sp.year = %s")
        params.append(year)
    if set_name:
        where_parts.append("sp.set_name ILIKE %s")
        params.append(f"%{set_name}%")

    where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT
                sp.id, sp.sport, sp.year, sp.set_name, sp.brand,
                sp.product_type, sp.msrp, sp.cards_per_pack, sp.packs_per_box,
                sp.release_date, sp.source_url
            FROM sealed_products sp
            {where_sql}
            ORDER BY sp.year DESC, sp.set_name, sp.product_type
        """, params)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()

        product_ids = [r[0] for r in rows]
        odds_by_id: dict = {}
        if product_ids:
            cur.execute("""
                SELECT sealed_product_id, card_type, odds_ratio
                FROM sealed_product_odds
                WHERE sealed_product_id = ANY(%s)
                ORDER BY sealed_product_id, card_type
            """, [product_ids])
            for pid, card_type, odds_ratio in cur.fetchall():
                odds_by_id.setdefault(pid, []).append(
                    {"card_type": card_type, "odds_ratio": odds_ratio}
                )

    products = []
    for row in rows:
        r = dict(zip(cols, row))
        r["msrp"] = float(r["msrp"]) if r["msrp"] is not None else None
        r["release_date"] = r["release_date"].isoformat() if r["release_date"] else None
        r["odds"] = odds_by_id.get(r["id"], [])
        products.append(r)

    return {"products": products}


# ---------------------------------------------------------------------------
# Set browser — distinct sets with card counts
# ---------------------------------------------------------------------------

@router.get("/sets")
def browse_sets(
    sport:    Optional[str] = Query(None),
    year:     Optional[str] = Query(None),
    search:   Optional[str] = Query(None),
    page:     int           = Query(1, ge=1),
    per_page: int           = Query(50, ge=1, le=200),
):
    """Return distinct (year, set_name) combinations with card and variant counts."""
    conditions = []
    params: list = []

    if sport:
        conditions.append("cc.sport = %s")
        params.append(sport.upper())
    if year:
        conditions.append("cc.year = %s")
        params.append(year)
    if search:
        conditions.append("cc.set_name ILIKE %s")
        params.append(f"%{search}%")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    offset = (page - 1) * per_page

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SET statement_timeout = '8s'")

        cur.execute(f"""
            SELECT COUNT(DISTINCT (cc.year, cc.set_name))
            FROM card_catalog cc
            LEFT JOIN catalog_sets cs
                ON cs.year = cc.year AND cs.set_name = cc.set_name AND cs.sport = cc.sport
            {where}
        """, params)
        total = cur.fetchone()[0]

        cur.execute(f"""
            SELECT
                cc.year,
                cc.set_name,
                cc.sport,
                COUNT(*) AS total_entries,
                COUNT(DISTINCT cc.player_name) AS total_players,
                COUNT(DISTINCT cc.card_number) AS total_cards,
                COUNT(DISTINCT cc.variant) AS total_variants,
                MIN(cc.brand) AS brand,
                MAX(cs.box_image_url) AS box_image_url
            FROM card_catalog cc
            LEFT JOIN catalog_sets cs
                ON cs.year = cc.year AND cs.set_name = cc.set_name AND cs.sport = cc.sport
            {where}
            GROUP BY cc.year, cc.set_name, cc.sport
            ORDER BY cc.year DESC NULLS LAST, cc.set_name ASC
            LIMIT %s OFFSET %s
        """, params + [per_page, offset])

        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]

    sets = [dict(zip(cols, r)) for r in rows]
    return {
        "sets": sets,
        "total": total,
        "page": page,
        "pages": math.ceil(total / per_page) if per_page else 1,
        "per_page": per_page,
    }


# ---------------------------------------------------------------------------
# Set detail — all cards in a set grouped by player/card_number with variants
# ---------------------------------------------------------------------------

@router.get("/set-detail")
def catalog_set_detail(
    year:     str           = Query(...),
    set_name: str           = Query(...),
    sport:    Optional[str] = Query(None),
    search:   Optional[str] = Query(None),   # filter by player name within the set
    page:     int           = Query(1, ge=1),
    per_page: int           = Query(100, ge=1, le=500),
):
    """Return cards in a specific set grouped by card_number/player_name, with all variants."""
    conditions = ["cc.year = %s", "cc.set_name = %s"]
    params: list = [year, set_name]

    if sport:
        conditions.append("cc.sport = %s")
        params.append(sport.upper())
    if search:
        conditions.append("cc.player_name ILIKE %s")
        params.append(f"%{search}%")

    where = "WHERE " + " AND ".join(conditions)
    offset = (page - 1) * per_page

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SET statement_timeout = '10s'")

        # Total unique player+card_number combos
        cur.execute(f"""
            SELECT COUNT(*) FROM (
                SELECT DISTINCT cc.card_number, cc.player_name
                FROM card_catalog cc {where}
            ) sub
        """, params)
        total = cur.fetchone()[0]

        # Grouped cards with aggregated variants
        cur.execute(f"""
            SELECT
                cc.card_number,
                cc.player_name,
                cc.team,
                cc.is_rookie,
                cc.sport,
                json_agg(
                    json_build_object(
                        'id',         cc.id,
                        'variant',    COALESCE(cc.variant, 'Base'),
                        'print_run',  cc.print_run,
                        'is_parallel',cc.is_parallel,
                        'fair_value', mp.fair_value,
                        'num_sales',  mp.num_sales
                    )
                    ORDER BY
                        CASE WHEN COALESCE(cc.variant, 'Base') = 'Base' THEN 0 ELSE 1 END,
                        cc.print_run DESC NULLS LAST,
                        cc.variant
                ) AS variants
            FROM card_catalog cc
            LEFT JOIN market_prices mp ON mp.card_catalog_id = cc.id
                AND (mp.ignored IS NULL OR mp.ignored = FALSE)
            {where}
            GROUP BY cc.card_number, cc.player_name, cc.team, cc.is_rookie, cc.sport
            ORDER BY
                CASE WHEN cc.card_number ~ '^[0-9]+$'
                     THEN cc.card_number::int ELSE 99999 END,
                cc.player_name
            LIMIT %s OFFSET %s
        """, params + [per_page, offset])

        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]

    cards = []
    for r in rows:
        row = dict(zip(cols, r))
        variants = row["variants"] or []
        for v in variants:
            if v.get("fair_value") is not None:
                v["fair_value"] = float(v["fair_value"])
        row["variants"] = variants
        cards.append(row)

    return {
        "year":     year,
        "set_name": set_name,
        "total":    total,
        "page":     page,
        "pages":    math.ceil(total / per_page) if per_page else 1,
        "per_page": per_page,
        "cards":    cards,
    }


@router.get("/filters")
def catalog_filters(
    sport:  Optional[str] = Query(None),
    year:   Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    """Return unique sports, years, and set names for filter dropdowns.

    When search is supplied, years and sets are scoped to rows that match
    that search term (player_name ILIKE or set_name ILIKE), so the dropdowns
    only show options that actually exist for the active query.

    Args:
        sport:  Scope to this sport.
        year:   Scope sets to this year.
        search: Scope years and sets to rows matching this player/set search.

    Returns:
        Dict with keys: sports (list), years (list desc), sets (list).
    """
    # Don't cache search-scoped results (too many combos); cache only plain sport|year
    cache_key = f"{sport}|{year}" if not search else None
    if cache_key:
        with _cache_lock:
            if cache_key in _filters_cache:
                return _filters_cache[cache_key]

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SET statement_timeout = '8s'")

        cur.execute("SELECT DISTINCT sport FROM card_catalog ORDER BY sport")
        sports = [r[0] for r in cur.fetchall()]

        # Need at least sport OR search to scope years — bare unfiltered year scan is too slow
        if not sport and not search:
            return {"sports": sports, "years": [], "sets": []}

        # Build base WHERE conditions shared by both year and set queries
        base_conds  = []
        base_params = []
        if sport:
            base_conds.append("sport = %s")
            base_params.append(sport.upper())
        if search:
            base_conds.append("(player_name ILIKE %s OR set_name ILIKE %s)")
            like = f"%{search}%"
            base_params.extend([like, like])

        base_where = ("WHERE " + " AND ".join(base_conds)) if base_conds else ""

        cur.execute(
            f"SELECT DISTINCT year FROM card_catalog {base_where} ORDER BY year DESC",
            base_params
        )
        years = [r[0] for r in cur.fetchall()]

        set_conds  = list(base_conds)
        set_params = list(base_params)
        if year:
            set_conds.append("year = %s")
            set_params.append(year)
        set_where = ("WHERE " + " AND ".join(set_conds)) if set_conds else ""
        cur.execute(
            f"""SELECT set_name, COUNT(*) cnt
                FROM card_catalog {set_where}
                GROUP BY set_name
                ORDER BY cnt DESC
                LIMIT 300""",
            set_params
        )
        sets = [r[0] for r in cur.fetchall()]

    result = {"sports": sports, "years": years, "sets": sets}
    if cache_key:
        with _cache_lock:
            _filters_cache[cache_key] = result
    return result


@router.get("/ai-search")
def ai_search(q: str = Query(..., min_length=2)):
    """Parse a natural-language card query with Claude and return matching catalog results.

    Example queries:
        "Connor McDavid Young Guns under $200"
        "LeBron James rookie cards"
        "2023 Topps Chrome NFL quarterbacks"

    Claude extracts structured filter params, then the normal browse_catalog
    logic is called with those params.

    Returns:
        Dict with keys: query (original), filters (parsed), cards, total, page, pages, per_page.
    """
    with _cache_lock:
        if q in _ai_cache:
            return _ai_cache[q]

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="AI search not configured")

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        system = (
            "You are a sports card search assistant. Parse the user's query into JSON filter "
            "params for a card catalog database. Return ONLY a JSON object with these optional keys:\n"
            "  search (str): player name or set name keyword\n"
            "  sport (str): one of NHL, NBA, NFL, MLB\n"
            "  year (str): card year, e.g. '2024-25' or '2024'\n"
            "  set_name (str): partial set name\n"
            "  is_rookie (bool): true if user specifically wants rookies/RCs\n"
            "  has_price (bool): true if user wants only priced cards\n"
            "  max_price (float): maximum fair_value in USD\n"
            "  min_price (float): minimum fair_value in USD\n"
            "Only include keys you're confident about. Never include keys not in the list above."
        )
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            system=system,
            messages=[{"role": "user", "content": q}],
        )
        raw = msg.content[0].text.strip()
        # Strip markdown code block if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        filters = json.loads(raw)
    except Exception as e:
        # Fall back to plain text search if Claude fails
        filters = {"search": q}

    # Extract price range — these aren't native browse_catalog params so handle separately
    min_price = filters.pop("min_price", None)
    max_price = filters.pop("max_price", None)

    # Call browse_catalog logic inline with parsed filters
    sort_col = SORT_COLS.get("fair_value", "mp.fair_value")
    sort_dir = "DESC"

    where_parts = []
    params = []

    sport    = filters.get("sport")
    year     = filters.get("year")
    set_name = filters.get("set_name")
    search   = filters.get("search")
    is_rookie = filters.get("is_rookie")
    has_price = filters.get("has_price", True)  # AI searches default to priced only

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
    if has_price:
        where_parts.append("mp.id IS NOT NULL")
    if min_price is not None:
        where_parts.append("mp.fair_value >= %s")
        params.append(float(min_price))
    if max_price is not None:
        where_parts.append("mp.fair_value <= %s")
        params.append(float(max_price))
    where_parts.append("(mp.ignored IS NULL OR mp.ignored = FALSE)")

    where_sql = "WHERE " + " AND ".join(where_parts)
    base_query = f"""
        FROM card_catalog cc
        LEFT JOIN market_prices mp ON mp.card_catalog_id = cc.id
        {where_sql}
    """
    data_sql = f"""
        SELECT
            cc.id, cc.sport, cc.year, cc.brand, cc.set_name, cc.card_number,
            cc.player_name, cc.team, cc.variant, cc.print_run,
            cc.is_rookie, cc.is_parallel, cc.scrape_tier,
            mp.fair_value, mp.prev_value, mp.trend, mp.confidence, mp.num_sales,
            mp.scraped_at, COALESCE(mp.image_url, '') AS image_url
        {base_query}
        ORDER BY {sort_col} {sort_dir} NULLS LAST, cc.player_name ASC
        LIMIT 50
    """

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SET statement_timeout = '8s'")
        cur.execute(f"SELECT COUNT(*) {base_query}", params)
        total = cur.fetchone()[0]
        cur.execute(data_sql, params)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]

    cards = []
    for row in rows:
        r = dict(zip(cols, row))
        for k in ("fair_value", "prev_value"):
            if r[k] is not None:
                r[k] = float(r[k])
        if r.get("scraped_at"):
            r["scraped_at"] = r["scraped_at"].isoformat()
        cards.append(r)

    result = {
        "query":    q,
        "filters":  {**filters, **({"min_price": min_price} if min_price else {}), **({"max_price": max_price} if max_price else {})},
        "cards":    cards,
        "total":    total,
        "page":     1,
        "pages":    math.ceil(total / 50) if total else 1,
        "per_page": 50,
    }
    with _cache_lock:
        _ai_cache[q] = result
    return result


# ---------------------------------------------------------------------------
# Natural-language parse endpoint (no DB — just Claude extraction)
# ---------------------------------------------------------------------------

_parse_cache: TTLCache = TTLCache(maxsize=500, ttl=300)  # 5 min

@router.get("/parse")
def parse_card_query(q: str = Query(..., min_length=2)):
    """Parse a natural-language card description into structured filter fields.

    Returns only the parsed filter dict — no DB call. Used to populate
    the advanced search panel in real time.

    Returns:
        Dict with: player_name, year, set_name, variant, sport, is_rookie (all optional)
    """
    with _cache_lock:
        cached = _parse_cache.get(q)
    if cached:
        return cached

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"error": "AI parse not configured", "fallback": True}

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        system = (
            "You are a sports card expert. Parse the user's text into JSON with these optional keys:\n"
            "  player_name (str): the player's full name\n"
            "  year (str): card year, e.g. '2024-25' or '2024'\n"
            "  set_name (str): the BASE set/product name only — e.g. 'Metal Universe', 'O-Pee-Chee Platinum', 'Topps Chrome', 'Upper Deck Series 1'\n"
            "  variant (str): the subset, parallel, or insert name — e.g. 'Young Guns', 'Precious Metal Gems', 'PMG', 'Red Prizm', 'Refractor', 'Gold', 'Rookie Patch Auto'\n"
            "  sport (str): one of NHL, NBA, NFL, MLB\n"
            "  is_rookie (bool): true if the user specifically wants a rookie card\n"
            "  card_number (str): the card number in the set, e.g. '201', '42', 'SP-15'\n"
            "IMPORTANT subset/insert classification rules:\n"
            "  - 'Precious Metal Gems' and 'PMG' are VARIANTS (inserts), NOT set names — Metal Universe is the set\n"
            "  - 'Young Guns', 'Canvas', 'UD Exclusives' are VARIANTS within Upper Deck sets\n"
            "  - 'Prizm', 'Refractor', 'Optic', 'Chrome' alone are VARIANTS; 'Topps Chrome' or 'Panini Prizm' are SET names\n"
            "  - Color parallels ('Red', 'Gold', 'Blue') go in variant\n"
            "  - When unsure whether something is a set or variant, prefer variant\n"
            "Only include keys you are confident about. Return ONLY valid JSON, no explanation."
        )
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            system=system,
            messages=[{"role": "user", "content": q}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw)
    except Exception:
        # Graceful degradation — return bare search keyword
        result = {"search": q}

    with _cache_lock:
        _parse_cache[q] = result
    return result


_trending_cache: TTLCache = TTLCache(maxsize=20, ttl=300)   # 5 min
_suggest_cache:  TTLCache = TTLCache(maxsize=500, ttl=120)  # 2 min

@router.get("/trending")
def trending_cards(
    sport: Optional[str] = Query(None),
    limit: int           = Query(12, ge=1, le=50),
):
    """Cards with the highest price momentum (7d avg vs prior 7d avg).

    Returns cards sorted by % price change descending, requiring at least
    3 sales in the last 7 days so low-volume noise is filtered out.
    """
    cache_key = f"trending|{sport}|{limit}"
    with _cache_lock:
        if cache_key in _trending_cache:
            return _trending_cache[cache_key]

    sport_filter = "AND cc.sport = %s" if sport else ""
    params: list = []
    if sport:
        params.append(sport.upper())

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SET statement_timeout = '6s'")
        cur.execute(f"""
            SELECT
                cc.id, cc.player_name, cc.sport, cc.year, cc.set_name,
                cc.variant, cc.card_number, cc.is_rookie, cc.scrape_tier,
                mp.fair_value, mp.num_sales, mp.image_url,
                AVG(mrs.price_val) FILTER (
                    WHERE mrs.sold_date >= CURRENT_DATE - 7 AND mrs.price_val > 0
                ) AS avg_7d,
                COUNT(mrs.id)      FILTER (
                    WHERE mrs.sold_date >= CURRENT_DATE - 7 AND mrs.price_val > 0
                ) AS cnt_7d,
                AVG(mrs.price_val) FILTER (
                    WHERE mrs.sold_date >= CURRENT_DATE - 14
                      AND mrs.sold_date <  CURRENT_DATE - 7
                      AND mrs.price_val > 0
                ) AS avg_prev_7d
            FROM card_catalog cc
            JOIN market_prices mp ON mp.card_catalog_id = cc.id
            JOIN market_raw_sales mrs ON mrs.card_catalog_id = cc.id
            WHERE mrs.sold_date >= CURRENT_DATE - 14
              AND mp.fair_value > 0
              AND NOT COALESCE(mp.ignored, FALSE)
              {sport_filter}
            GROUP BY cc.id, cc.player_name, cc.sport, cc.year, cc.set_name,
                     cc.variant, cc.card_number, cc.is_rookie, cc.scrape_tier,
                     mp.fair_value, mp.num_sales, mp.image_url
            HAVING
                COUNT(mrs.id) FILTER (
                    WHERE mrs.sold_date >= CURRENT_DATE - 7 AND mrs.price_val > 0
                ) >= 3
                AND AVG(mrs.price_val) FILTER (
                    WHERE mrs.sold_date >= CURRENT_DATE - 14
                      AND mrs.sold_date <  CURRENT_DATE - 7
                      AND mrs.price_val > 0
                ) >= 2.0
                AND AVG(mrs.price_val) FILTER (
                    WHERE mrs.sold_date >= CURRENT_DATE - 7 AND mrs.price_val > 0
                ) >= 2.0
            ORDER BY (
                AVG(mrs.price_val) FILTER (
                    WHERE mrs.sold_date >= CURRENT_DATE - 7 AND mrs.price_val > 0
                ) /
                AVG(mrs.price_val) FILTER (
                    WHERE mrs.sold_date >= CURRENT_DATE - 14
                      AND mrs.sold_date <  CURRENT_DATE - 7
                      AND mrs.price_val > 0
                ) - 1
            ) DESC NULLS LAST
            LIMIT %s
        """, params + [limit])

        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()

    cards = []
    for row in rows:
        r = dict(zip(cols, row))
        avg_7d     = float(r["avg_7d"])     if r["avg_7d"]     is not None else None
        avg_prev   = float(r["avg_prev_7d"]) if r["avg_prev_7d"] is not None else None
        r["fair_value"] = float(r["fair_value"]) if r["fair_value"] is not None else None
        r["pct_change"] = round((avg_7d - avg_prev) / avg_prev * 100, 1) if avg_7d and avg_prev and avg_prev > 0 else None
        r["avg_7d"]     = avg_7d
        r["cnt_7d"]     = r["cnt_7d"]
        del r["avg_prev_7d"]
        cards.append(r)

    result = {"cards": cards}
    with _cache_lock:
        _trending_cache[cache_key] = result
    return result


@router.get("/suggest")
def suggest(
    q:     str          = Query(..., min_length=2),
    sport: Optional[str]= Query(None),
    limit: int          = Query(8, ge=1, le=20),
):
    """Two-tier typeahead: player names with their top cards, plus FTS card search."""
    cache_key = f"v2|{q}|{sport}|{limit}"
    with _cache_lock:
        if cache_key in _suggest_cache:
            return _suggest_cache[cache_key]

    sport_up = sport.upper() if sport else None
    results: list = []
    seen_card_ids: set = set()

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SET statement_timeout = '3s'")

        # ── 1. Player-name matches ──────────────────────────────────────────
        p_params: list = [f"%{q}%"]
        p_where = "player_name ILIKE %s"
        if sport_up:
            p_where += " AND sport = %s"
            p_params.append(sport_up)

        cur.execute(f"""
            SELECT player_name, sport, COUNT(*) AS cnt
            FROM card_catalog
            WHERE {p_where}
            GROUP BY player_name, sport
            ORDER BY cnt DESC
            LIMIT 5
        """, p_params)
        player_rows = cur.fetchall()

        if player_rows:
            player_names = [r[0] for r in player_rows]
            name_ph = ','.join(['%s'] * len(player_names))
            c_params: list = list(player_names)
            c_extra = ""
            if sport_up:
                c_extra = " AND cc.sport = %s"
                c_params.append(sport_up)

            # Top 3 cards per player ordered by RC status then sales then value
            cur.execute(f"""
                WITH ranked AS (
                    SELECT
                        cc.id, cc.player_name, cc.sport, cc.year, cc.set_name,
                        cc.variant, cc.is_rookie, mp.num_sales, mp.fair_value,
                        ROW_NUMBER() OVER (
                            PARTITION BY cc.player_name
                            ORDER BY
                                cc.is_rookie DESC NULLS LAST,
                                COALESCE(mp.num_sales, 0) DESC,
                                COALESCE(mp.fair_value, 0) DESC
                        ) AS rn
                    FROM card_catalog cc
                    LEFT JOIN market_prices mp ON mp.card_catalog_id = cc.id
                    WHERE cc.player_name IN ({name_ph}) {c_extra}
                )
                SELECT id, player_name, sport, year, set_name, variant,
                       is_rookie, num_sales, fair_value
                FROM ranked WHERE rn <= 3
            """, c_params)
            card_rows = cur.fetchall()

            cards_by_player: dict = {}
            for r in card_rows:
                seen_card_ids.add(r[0])
                cards_by_player.setdefault(r[1], []).append({
                    "type": "card", "id": r[0], "player_name": r[1], "sport": r[2],
                    "year": r[3], "set_name": r[4], "variant": r[5],
                    "is_rookie": bool(r[6]), "num_sales": r[7], "fair_value": float(r[8]) if r[8] else None,
                })

            for pname, psport, pcnt in player_rows:
                results.append({"type": "player", "player_name": pname, "sport": psport, "count": pcnt})
                results.extend(cards_by_player.get(pname, []))

        # ── 2. Direct card FTS search for specific queries ("McDavid Young Guns") ──
        words = q.strip().split()
        if len(words) >= 2 or not player_rows:
            fts_params: list = [q, q]
            fts_extra = ""
            if sport_up:
                fts_extra = " AND cc.sport = %s"
                fts_params.append(sport_up)

            cur.execute(f"""
                SELECT cc.id, cc.player_name, cc.sport, cc.year, cc.set_name,
                       cc.variant, cc.is_rookie, mp.num_sales, mp.fair_value
                FROM card_catalog cc
                LEFT JOIN market_prices mp ON mp.card_catalog_id = cc.id
                WHERE cc.search_vector @@ plainto_tsquery('english', %s) {fts_extra}
                ORDER BY
                    ts_rank(cc.search_vector, plainto_tsquery('english', %s)) DESC,
                    cc.is_rookie DESC NULLS LAST,
                    COALESCE(mp.num_sales, 0) DESC
                LIMIT 5
            """, fts_params)
            for r in cur.fetchall():
                if r[0] not in seen_card_ids:
                    seen_card_ids.add(r[0])
                    results.append({
                        "type": "card", "id": r[0], "player_name": r[1], "sport": r[2],
                        "year": r[3], "set_name": r[4], "variant": r[5],
                        "is_rookie": bool(r[6]), "num_sales": r[7],
                        "fair_value": float(r[8]) if r[8] else None,
                    })

    with _cache_lock:
        _suggest_cache[cache_key] = results
    return results


# ── Parameterized routes MUST come after all fixed-path routes ──────────────
# FastAPI evaluates routes in definition order. /{catalog_id} would swallow
# any fixed path like /filters, /suggest, /releases if defined first.

@router.get("/{catalog_id}")
def get_catalog_card(catalog_id: int):
    """Return a single catalog card with its current market price."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT cc.id, cc.sport, cc.year, cc.brand, cc.set_name, cc.card_number,
                   cc.player_name, cc.team, cc.variant, cc.print_run, cc.is_rookie,
                   cc.scrape_tier,
                   mp.fair_value, mp.prev_value, mp.trend, mp.confidence,
                   mp.num_sales, mp.scraped_at, mp.image_url, mp.graded_data
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
        if card.get("graded_data") and isinstance(card["graded_data"], dict):
            card["graded_data"] = {
                grade: {**v, "fair_value": float(v["fair_value"])} if v.get("fair_value") else v
                for grade, v in card["graded_data"].items()
            }
        if card.get("scraped_at"):
            card["scraped_at"] = card["scraped_at"].isoformat()
    return card


@router.get("/{catalog_id}/live-price")
def live_price(catalog_id: int, request: Request):
    """
    Fallback live eBay scrape for cards with no DB price data yet.
    Uses requests (no Selenium) — lightweight but may be blocked on some IPs.
    Returns recent sold listings so the card page isn't empty.

    Safety: 1h result cache per card, 10s per-IP cooldown, 30 RPM global cap.
    """
    import re, time as _time, requests as req
    from datetime import timezone
    from bs4 import BeautifulSoup

    client_ip = request.client.host if request.client else "unknown"
    now = _time.monotonic()

    with _live_lock:
        # 1) Serve from cache if available
        if catalog_id in _live_cache:
            return {**_live_cache[catalog_id], "cached": True}

        # 2) Per-IP cooldown — prevent a single user from hammering eBay
        last = _live_ip_times.get(client_ip, 0)
        if now - last < _LIVE_PER_IP_COOLDOWN:
            wait = round(_LIVE_PER_IP_COOLDOWN - (now - last))
            raise HTTPException(status_code=429, detail=f"Please wait {wait}s before another live search.")

        # 3) Global RPM cap — protect Railway's IP from eBay rate limiting
        cutoff = now - 60
        _live_global_times[:] = [t for t in _live_global_times if t > cutoff]
        if len(_live_global_times) >= _LIVE_GLOBAL_RPM:
            raise HTTPException(status_code=429, detail="Live search is busy — try again in a moment.")

        # Reserve slot
        _live_ip_times[client_ip] = now
        _live_global_times.append(now)

    # Get card info + check if we already have fresh DB data
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT cc.player_name, cc.year, cc.set_name, cc.variant,
                   cc.card_number, cc.sport,
                   mp.fair_value, mp.scraped_at
            FROM card_catalog cc
            LEFT JOIN market_prices mp ON mp.card_catalog_id = cc.id
            WHERE cc.id = %s
        """, [catalog_id])
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Card not found")

    player, year, set_name, variant, card_number, sport, fair_value, scraped_at = row

    # Skip live scrape if DB has a fresh price (< 30 days old)
    if fair_value and scraped_at:
        from datetime import timedelta
        age = datetime.now(timezone.utc) - scraped_at.replace(tzinfo=timezone.utc)
        if age.days < 30:
            return {"source": "db", "sales": [], "query": None, "skipped": True}

    # Build tight search query
    parts = [player, year, set_name]
    if variant and variant.lower() not in ("base", ""):
        parts.append(variant)
    if card_number:
        parts.append(f"#{card_number}")
    query = " ".join(str(p) for p in parts if p)

    ebay_url = (
        "https://www.ebay.com/sch/i.html"
        f"?_nkw={req.utils.quote(query)}"
        "&LH_Complete=1&LH_Sold=1&_sop=13&_sacat=212&_ipg=25"
    )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        resp = req.get(ebay_url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        sales = []
        for item in soup.select(".s-item")[:20]:
            title_el = item.select_one(".s-item__title")
            price_el = item.select_one(".s-item__price")
            date_el  = item.select_one(".s-item__ended-date, .POSITIVE")
            link_el  = item.select_one("a.s-item__link")
            if not title_el or not price_el:
                continue
            title = title_el.get_text(strip=True)
            if title.lower().startswith("shop on ebay"):
                continue
            price_text = price_el.get_text(strip=True)
            price_match = re.search(r"[\d]+\.?\d*", price_text.replace(",", ""))
            if not price_match:
                continue
            try:
                price = float(price_match.group())
            except ValueError:
                continue
            sales.append({
                "title": title,
                "price": price,
                "date":  date_el.get_text(strip=True) if date_el else None,
                "url":   link_el["href"].split("?")[0] if link_el else None,
            })

        prices = [s["price"] for s in sales]
        avg    = round(sum(prices) / len(prices), 2) if prices else None

        result = {
            "source":    "ebay_live",
            "query":     query,
            "ebay_url":  ebay_url,
            "sales":     sales,
            "avg_price": avg,
            "count":     len(sales),
        }
        # Cache successful results (even empty ones) for 1 hour
        with _live_lock:
            _live_cache[catalog_id] = result
        return result

    except Exception as e:
        # Don't cache errors — let user retry
        return {
            "source":    "ebay_live",
            "query":     query,
            "ebay_url":  ebay_url,
            "sales":     [],
            "avg_price": None,
            "count":     0,
            "error":     str(e)[:100],
        }
