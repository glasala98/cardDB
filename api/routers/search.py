"""Sales search endpoint — powers the 130point-style search UI.

GET /api/search        — full-text search across market_raw_sales
GET /api/search/suggest — autocomplete suggestions from card_catalog
GET /api/search/sources — list of active sources with sale counts
"""

import re
import threading
from typing import Optional
from datetime import date, timedelta

from fastapi import APIRouter, Query, HTTPException
from cachetools import TTLCache

from db import get_db

router = APIRouter()

# TTL caches
_search_cache:  TTLCache = TTLCache(maxsize=1000, ttl=120)   # 2 min
_suggest_cache: TTLCache = TTLCache(maxsize=500,  ttl=60)    # 1 min
_sources_cache: TTLCache = TTLCache(maxsize=1,    ttl=300)   # 5 min
_cache_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Grade detection
# ---------------------------------------------------------------------------

_GRADE_RE = re.compile(
    r'\b(PSA|BGS|SGC|CGC|HGA|CSG)\s*(\d+(?:\.\d+)?)\b', re.IGNORECASE
)
_GRADE_WORD_RE = re.compile(
    r'\b(gem\s*mt?\s*10|gem\s*mint|pristine)\b', re.IGNORECASE
)


def _detect_grade(q: str) -> Optional[str]:
    """Return a grade label if one is found in the query string."""
    m = _GRADE_RE.search(q)
    if m:
        company = m.group(1).upper()
        num     = m.group(2)
        return f"{company} {num}"
    m2 = _GRADE_WORD_RE.search(q)
    if m2:
        return "GEM MT 10"
    return None


def _strip_grade(q: str) -> str:
    """Remove grade markers from query before catalog search."""
    q = _GRADE_RE.sub('', q)
    q = _GRADE_WORD_RE.sub('', q)
    return re.sub(r'\s+', ' ', q).strip()


# ---------------------------------------------------------------------------
# Primary search endpoint
# ---------------------------------------------------------------------------

@router.get("")
def search_sales(
    q:          str            = Query(..., min_length=2, description="Search query"),
    source:     Optional[str]  = Query(None, description="Filter by source: ebay|goldin|heritage|pwcc|fanatics|pristine|myslabs"),
    date_from:  Optional[date] = Query(None, alias="from"),
    date_to:    Optional[date] = Query(None, alias="to"),
    sport:      Optional[str]  = Query(None),
    min_price:  Optional[float]= Query(None, ge=0),
    max_price:  Optional[float]= Query(None),
    grade:      Optional[str]  = Query(None, description="Grade filter e.g. 'PSA 10'"),
    sort:       str            = Query("date", pattern="^(date|price_asc|price_desc)$"),
    page:       int            = Query(1, ge=1),
    per_page:   int            = Query(50, ge=1, le=200),
):
    """Search all scraped sales across eBay, Goldin, Heritage, PWCC, etc.

    Two-phase:
      1. Resolve card_catalog IDs matching the query (tsvector + trigram)
      2. Fetch market_raw_sales rows for those IDs with applied filters
    """
    cache_key = f"{q}|{source}|{date_from}|{date_to}|{sport}|{min_price}|{max_price}|{grade}|{sort}|{page}|{per_page}"
    with _cache_lock:
        cached = _search_cache.get(cache_key)
    if cached:
        return cached

    detected_grade = _detect_grade(q)
    catalog_query  = _strip_grade(q)

    with get_db() as conn:
        conn.cursor().execute("SET statement_timeout = '5s'")
        cur = conn.cursor()

        # ── Phase 1: resolve card_catalog IDs ──────────────────────────────
        catalog_ids, matched_cards = _resolve_catalog_ids(cur, catalog_query, sport)

        # ── Phase 2: fetch sales ────────────────────────────────────────────
        effective_grade = grade or detected_grade

        where, params = _build_sales_where(
            catalog_ids, source, date_from, date_to,
            min_price, max_price, effective_grade,
        )

        order = {
            "date":       "mrs.sold_date DESC NULLS LAST",
            "price_asc":  "mrs.price_val ASC",
            "price_desc": "mrs.price_val DESC",
        }[sort]

        offset = (page - 1) * per_page

        cur.execute(f"""
            SELECT COUNT(*) FROM market_raw_sales mrs
            JOIN card_catalog cc ON cc.id = mrs.card_catalog_id
            WHERE {where}
        """, params)
        total = cur.fetchone()[0]

        cur.execute(f"""
            SELECT
                mrs.id,
                mrs.card_catalog_id,
                mrs.sold_date,
                mrs.price_val,
                mrs.shipping_val,
                mrs.title,
                mrs.source,
                mrs.grade,
                mrs.grade_company,
                mrs.grade_numeric,
                mrs.serial_number,
                mrs.print_run,
                mrs.lot_url,
                mrs.is_auction,
                cc.player_name,
                cc.year,
                cc.set_name,
                cc.variant,
                cc.sport,
                cc.is_rookie
            FROM market_raw_sales mrs
            JOIN card_catalog cc ON cc.id = mrs.card_catalog_id
            WHERE {where}
            ORDER BY {order}
            LIMIT %s OFFSET %s
        """, params + [per_page, offset])

        cols = [d[0] for d in cur.description]
        results = []
        for row in cur.fetchall():
            r = dict(zip(cols, row))
            r["sold_date"]    = r["sold_date"].isoformat()    if r["sold_date"]    else None
            r["price_val"]    = float(r["price_val"])         if r["price_val"]    else None
            r["shipping_val"] = float(r["shipping_val"] or 0)
            r["total_price"]  = round((r["price_val"] or 0) + r["shipping_val"], 2)
            r["grade_numeric"]= float(r["grade_numeric"])     if r["grade_numeric"] else None
            results.append(r)

    response = {
        "query":          q,
        "detected_grade": detected_grade,
        "matched_cards":  matched_cards[:10],
        "results":        results,
        "total":          total,
        "page":           page,
        "pages":          max(1, -(-total // per_page)),   # ceiling div
        "per_page":       per_page,
    }

    with _cache_lock:
        _search_cache[cache_key] = response
    return response


# ---------------------------------------------------------------------------
# Phase 1 helper — catalog ID resolution
# ---------------------------------------------------------------------------

def _resolve_catalog_ids(cur, query: str, sport: Optional[str]) -> tuple[list[int], list[dict]]:
    """Return (catalog_ids, matched_card_dicts) for a cleaned query string."""
    if not query:
        return [], []

    params: list = []
    sport_filter = ""
    if sport:
        sport_filter = "AND cc.sport = %s"
        params.append(sport.upper())

    try:
        tsq = ' & '.join(w for w in re.sub(r'[^\w\s]', '', query).split() if len(w) > 2)
        if not tsq:
            raise ValueError("empty tsquery")

        cur.execute(f"""
            SELECT
                cc.id,
                cc.player_name,
                cc.year,
                cc.set_name,
                cc.variant,
                cc.sport,
                cc.is_rookie,
                mp.fair_value,
                mp.num_sales,
                ts_rank(cc.search_vector, plainto_tsquery('english', %s)) AS ts_rank,
                similarity(cc.player_name, %s) AS sim_rank
            FROM card_catalog cc
            LEFT JOIN market_prices mp ON mp.card_catalog_id = cc.id
            WHERE (
                cc.search_vector @@ plainto_tsquery('english', %s)
                OR cc.player_name %% %s
            )
            {sport_filter}
            ORDER BY ts_rank DESC, sim_rank DESC, mp.num_sales DESC NULLS LAST
            LIMIT 20
        """, [tsq, query, tsq, query] + params)

    except Exception:
        # Fallback — simple ILIKE if tsvector/trigram fails
        cur.execute(f"""
            SELECT cc.id, cc.player_name, cc.year, cc.set_name, cc.variant,
                   cc.sport, cc.is_rookie, mp.fair_value, mp.num_sales,
                   0 AS ts_rank, 0 AS sim_rank
            FROM card_catalog cc
            LEFT JOIN market_prices mp ON mp.card_catalog_id = cc.id
            WHERE cc.player_name ILIKE %s {sport_filter}
            ORDER BY mp.num_sales DESC NULLS LAST
            LIMIT 20
        """, [f'%{query}%'] + params)

    rows = cur.fetchall()
    if not rows:
        return [], []

    cols = [d[0] for d in cur.description]
    cards = []
    ids   = []
    seen  = set()
    for row in rows:
        r = dict(zip(cols, row))
        if r["id"] not in seen:
            seen.add(r["id"])
            ids.append(r["id"])
            cards.append({
                "catalog_id":  r["id"],
                "player_name": r["player_name"],
                "year":        r["year"],
                "set_name":    r["set_name"],
                "variant":     r["variant"],
                "sport":       r["sport"],
                "is_rookie":   r["is_rookie"],
                "fair_value":  float(r["fair_value"]) if r["fair_value"] else None,
                "num_sales":   r["num_sales"],
            })

    return ids[:20], cards


# ---------------------------------------------------------------------------
# Phase 2 helper — WHERE clause builder
# ---------------------------------------------------------------------------

def _build_sales_where(
    catalog_ids: list[int],
    source:      Optional[str],
    date_from:   Optional[date],
    date_to:     Optional[date],
    min_price:   Optional[float],
    max_price:   Optional[float],
    grade:       Optional[str],
) -> tuple[str, list]:
    conditions = []
    params: list = []

    if catalog_ids:
        conditions.append("mrs.card_catalog_id = ANY(%s)")
        params.append(catalog_ids)
    else:
        # No catalog match — search titles directly via trigram
        conditions.append("1=1")

    if source:
        conditions.append("mrs.source = %s")
        params.append(source.lower())
    if date_from:
        conditions.append("mrs.sold_date >= %s")
        params.append(date_from)
    if date_to:
        conditions.append("mrs.sold_date <= %s")
        params.append(date_to)
    if min_price is not None:
        conditions.append("mrs.price_val >= %s")
        params.append(min_price)
    if max_price is not None:
        conditions.append("mrs.price_val <= %s")
        params.append(max_price)
    if grade:
        conditions.append("mrs.title ILIKE %s")
        params.append(f"%{grade}%")

    return " AND ".join(conditions) if conditions else "1=1", params


# ---------------------------------------------------------------------------
# Autocomplete suggestions
# ---------------------------------------------------------------------------

@router.get("/suggest")
def search_suggest(q: str = Query(..., min_length=2, max_length=100)):
    """Return up to 8 card name suggestions matching the partial query."""
    with _cache_lock:
        cached = _suggest_cache.get(q)
    if cached:
        return cached

    with get_db() as conn:
        conn.cursor().execute("SET statement_timeout = '2s'")
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT DISTINCT
                    cc.player_name,
                    cc.year,
                    cc.set_name,
                    cc.sport,
                    mp.num_sales
                FROM card_catalog cc
                LEFT JOIN market_prices mp ON mp.card_catalog_id = cc.id
                WHERE cc.player_name ILIKE %s
                   OR cc.player_name %% %s
                ORDER BY mp.num_sales DESC NULLS LAST
                LIMIT 8
            """, [f'%{q}%', q])
            rows = cur.fetchall()
        except Exception:
            rows = []

    suggestions = [
        {
            "label":       f"{r[0]} — {r[1]} {r[2]}".strip(" —"),
            "player_name": r[0],
            "year":        r[1],
            "set_name":    r[2],
            "sport":       r[3],
        }
        for r in rows
    ]
    result = {"suggestions": suggestions}
    with _cache_lock:
        _suggest_cache[q] = result
    return result


# ---------------------------------------------------------------------------
# Active sources
# ---------------------------------------------------------------------------

@router.get("/sources")
def search_sources():
    """Return list of active data sources with sale counts."""
    with _cache_lock:
        cached = _sources_cache.get("sources")
    if cached:
        return cached

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT source, COUNT(*) AS sale_count, MAX(scraped_at) AS last_scraped
            FROM market_raw_sales
            GROUP BY source
            ORDER BY sale_count DESC
        """)
        rows = cur.fetchall()

    SOURCE_LABELS = {
        "ebay":     "eBay",
        "goldin":   "Goldin",
        "heritage": "Heritage",
        "pwcc":     "PWCC",
        "fanatics": "Fanatics",
        "pristine": "Pristine",
        "myslabs":  "MySlabs",
    }

    sources = [
        {
            "key":          r[0],
            "label":        SOURCE_LABELS.get(r[0], r[0].title()),
            "sale_count":   r[1],
            "last_scraped": r[2].isoformat() if r[2] else None,
        }
        for r in rows
    ]
    result = {"sources": sources}
    with _cache_lock:
        _sources_cache["sources"] = result
    return result
