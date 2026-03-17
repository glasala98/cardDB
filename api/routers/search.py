"""Sales search endpoint — powers the 130point-style search UI.

GET /api/search          — full-text search across market_raw_sales
GET /api/search/suggest  — autocomplete suggestions from card_catalog
GET /api/search/sources  — list of active sources with sale counts
GET /api/search/trending — top queries from last 7 days
"""

import re
import threading
from typing import Optional, List
from datetime import date

from fastapi import APIRouter, Query, BackgroundTasks
from cachetools import TTLCache

from db import get_db

router = APIRouter()

# TTL caches
_search_cache:   TTLCache = TTLCache(maxsize=1000, ttl=120)   # 2 min
_suggest_cache:  TTLCache = TTLCache(maxsize=500,  ttl=60)    # 1 min
_sources_cache:  TTLCache = TTLCache(maxsize=1,    ttl=300)   # 5 min
_trending_cache: TTLCache = TTLCache(maxsize=1,    ttl=600)   # 10 min
_cache_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Grade detection helpers
# ---------------------------------------------------------------------------

_GRADE_RE = re.compile(
    r'\b(PSA|BGS|SGC|CGC|HGA|CSG)\s*(\d+(?:\.\d+)?)\b', re.IGNORECASE
)
_GRADE_WORD_RE = re.compile(
    r'\b(gem\s*m(?:t|int)\s*10|gem\s*mint|pristine)\b', re.IGNORECASE
)


def _detect_grade(q: str) -> Optional[str]:
    m = _GRADE_RE.search(q)
    if m:
        return f"{m.group(1).upper()} {m.group(2)}"
    m2 = _GRADE_WORD_RE.search(q)
    if m2:
        text = m2.group(1).lower()
        return "GEM MINT" if re.search(r'mint\s*$', text) else "GEM MT 10"
    return None


def _strip_grade(q: str) -> str:
    q = _GRADE_RE.sub('', q)
    q = _GRADE_WORD_RE.sub('', q)
    return re.sub(r'\s+', ' ', q).strip()


# ---------------------------------------------------------------------------
# Background search logger
# ---------------------------------------------------------------------------

def _log_search(query: str, result_count: int):
    """Fire-and-forget: write one row to search_log."""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO search_log (query, result_count) VALUES (%s, %s)",
                    [query.strip()[:500], result_count],
                )
            conn.commit()
    except Exception:
        pass  # never let logging break the response


# ---------------------------------------------------------------------------
# Main search endpoint
# ---------------------------------------------------------------------------

@router.get("")
def search_sales(
    background_tasks: BackgroundTasks,
    q:          str            = Query(..., min_length=2),
    source:     List[str]      = Query(default=[]),
    date_from:  Optional[date] = Query(None),
    date_to:    Optional[date] = Query(None),
    sport:      Optional[str]  = Query(None),
    price_min:  Optional[float]= Query(None, ge=0),
    price_max:  Optional[float]= Query(None),
    grade:      Optional[str]  = Query(None),
    graded_only:bool           = Query(False),
    sort:       str            = Query("date_desc"),
    limit:      int            = Query(25, ge=1, le=200),
    offset:     int            = Query(0, ge=0),
):
    sources_key  = ",".join(sorted(source))
    cache_key = f"{q}|{sources_key}|{date_from}|{date_to}|{sport}|{price_min}|{price_max}|{grade}|{graded_only}|{sort}|{limit}|{offset}"
    with _cache_lock:
        cached = _search_cache.get(cache_key)
    if cached:
        return cached

    detected_grade = _detect_grade(q)
    catalog_query  = _strip_grade(q)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = '5s'")

            # Phase 1 — resolve catalog IDs
            catalog_ids, matched_cards = _resolve_catalog_ids(cur, catalog_query, sport)

            # Phase 2 — fetch sales
            effective_grade = grade or detected_grade
            where, params = _build_sales_where(
                catalog_ids, source, date_from, date_to,
                price_min, price_max, effective_grade, graded_only, q,
            )

            ORDER_MAP = {
                "date_desc":  "mrs.sold_date DESC NULLS LAST",
                "date_asc":   "mrs.sold_date ASC  NULLS LAST",
                "price_desc": "mrs.price_val DESC",
                "price_asc":  "mrs.price_val ASC",
            }
            order = ORDER_MAP.get(sort, "mrs.sold_date DESC NULLS LAST")

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
                    mrs.title,
                    mrs.source,
                    mrs.grade,
                    mrs.grade_company,
                    mrs.grade_numeric,
                    mrs.serial_number,
                    mrs.print_run,
                    mrs.lot_url,
                    mrs.image_url,
                    mrs.hammer_price,
                    mrs.buyer_premium_pct,
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
            """, params + [limit, offset])

            cols = [d[0] for d in cur.description]
            results = []
            for row in cur.fetchall():
                r = dict(zip(cols, row))
                r["sold_date"]     = r["sold_date"].isoformat()    if r["sold_date"]     else None
                r["price_val"]     = float(r["price_val"])         if r["price_val"]     else None
                r["grade_numeric"] = float(r["grade_numeric"])     if r["grade_numeric"] else None
                r["hammer_price"]  = float(r["hammer_price"])      if r["hammer_price"]  else None
                results.append(r)

    response = {
        "query":          q,
        "detected_grade": detected_grade,
        "matched_cards":  matched_cards[:10],
        "results":        results,
        "total":          total,
        "limit":          limit,
        "offset":         offset,
    }

    with _cache_lock:
        _search_cache[cache_key] = response

    background_tasks.add_task(_log_search, q, total)
    return response


# ---------------------------------------------------------------------------
# Phase 1 — catalog ID resolution
# ---------------------------------------------------------------------------

def _resolve_catalog_ids(cur, query: str, sport: Optional[str]) -> tuple[list, list]:
    if not query:
        return [], []

    params: list = []
    sport_filter = ""
    if sport:
        sport_filter = "AND cc.sport = %s"
        params.append(sport.upper())

    words = [w for w in re.sub(r'[^\w\s]', '', query).split() if len(w) > 1]
    tsq   = ' & '.join(words) if words else None

    try:
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

    cols  = [d[0] for d in cur.description]
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
# Phase 2 — WHERE clause builder
# ---------------------------------------------------------------------------

def _build_sales_where(
    catalog_ids: list,
    sources:     list,
    date_from:   Optional[date],
    date_to:     Optional[date],
    price_min:   Optional[float],
    price_max:   Optional[float],
    grade:       Optional[str],
    graded_only: bool,
    raw_query:   str,
) -> tuple[str, list]:
    conditions: list[str] = []
    params: list = []

    if catalog_ids:
        conditions.append("mrs.card_catalog_id = ANY(%s)")
        params.append(catalog_ids)
    else:
        # Fall back to title trigram search when no catalog match
        conditions.append("mrs.title ILIKE %s")
        params.append(f'%{raw_query}%')

    if sources:
        conditions.append("mrs.source = ANY(%s)")
        params.append([s.lower() for s in sources])

    if date_from:
        conditions.append("mrs.sold_date >= %s"); params.append(date_from)
    if date_to:
        conditions.append("mrs.sold_date <= %s"); params.append(date_to)
    if price_min is not None:
        conditions.append("mrs.price_val >= %s"); params.append(price_min)
    if price_max is not None:
        conditions.append("mrs.price_val <= %s"); params.append(price_max)
    if grade:
        conditions.append("(mrs.grade ILIKE %s OR mrs.title ILIKE %s)")
        params += [f'%{grade}%', f'%{grade}%']
    if graded_only:
        conditions.append("mrs.grade IS NOT NULL")

    return (" AND ".join(conditions) if conditions else "1=1"), params


# ---------------------------------------------------------------------------
# Autocomplete suggest
# ---------------------------------------------------------------------------

@router.get("/suggest")
def search_suggest(q: str = Query(..., min_length=2, max_length=100)):
    """Return up to 8 card suggestions matching the partial query."""
    with _cache_lock:
        cached = _suggest_cache.get(q)
    if cached:
        return cached

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = '2s'")
            try:
                cur.execute("""
                    SELECT DISTINCT ON (cc.player_name, cc.year, cc.set_name)
                        cc.player_name,
                        cc.year,
                        cc.set_name,
                        cc.sport,
                        mp.num_sales
                    FROM card_catalog cc
                    LEFT JOIN market_prices mp ON mp.card_catalog_id = cc.id
                    WHERE cc.player_name ILIKE %s
                       OR cc.player_name %% %s
                    ORDER BY cc.player_name, cc.year, cc.set_name,
                             mp.num_sales DESC NULLS LAST
                    LIMIT 8
                """, [f'%{q}%', q])
                rows = cur.fetchall()
            except Exception:
                rows = []

    result = [
        {
            "display_name": f"{r[0]} {r[1] or ''}".strip(),
            "player_name":  r[0],
            "year":         r[1],
            "set_name":     r[2],
            "sport":        r[3],
        }
        for r in rows
    ]
    with _cache_lock:
        _suggest_cache[q] = result
    return result


# ---------------------------------------------------------------------------
# Active sources
# ---------------------------------------------------------------------------

@router.get("/sources")
def search_sources():
    with _cache_lock:
        cached = _sources_cache.get("sources")
    if cached:
        return cached

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT source, COUNT(*) AS sale_count, MAX(scraped_at) AS last_scraped
                FROM market_raw_sales
                GROUP BY source
                ORDER BY sale_count DESC
            """)
            rows = cur.fetchall()

    SOURCE_LABELS = {
        "ebay": "eBay", "goldin": "Goldin", "heritage": "Heritage",
        "pwcc": "PWCC", "fanatics": "Fanatics", "pristine": "Pristine",
        "myslabs": "MySlabs",
    }
    result = [
        {
            "key":          r[0],
            "label":        SOURCE_LABELS.get(r[0], r[0].title()),
            "sale_count":   r[1],
            "last_scraped": r[2].isoformat() if r[2] else None,
        }
        for r in rows
    ]
    with _cache_lock:
        _sources_cache["sources"] = result
    return result


# ---------------------------------------------------------------------------
# Trending searches (last 7 days)
# ---------------------------------------------------------------------------

@router.get("/trending")
def search_trending(limit: int = Query(10, ge=1, le=50)):
    """Return the most-searched queries over the last 7 days."""
    with _cache_lock:
        cached = _trending_cache.get("trending")
    if cached:
        return cached

    with get_db() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("""
                    SELECT lower(query) AS q, COUNT(*) AS searches
                    FROM search_log
                    WHERE searched_at >= NOW() - INTERVAL '7 days'
                      AND result_count > 0
                    GROUP BY lower(query)
                    ORDER BY searches DESC
                    LIMIT %s
                """, [limit])
                rows = cur.fetchall()
            except Exception:
                rows = []

    result = [{"query": r[0], "searches": r[1]} for r in rows]
    with _cache_lock:
        _trending_cache["trending"] = result
    return result
