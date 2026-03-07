"""Master DB endpoints — Young Guns market database."""

import datetime
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from db import get_db
from dashboard_utils import (
    load_master_db,
    save_master_db,
    load_yg_price_history,
    load_yg_portfolio_history,
    load_nhl_player_stats,
    get_market_alerts,
    scrape_single_card,
)

router = APIRouter()


def _num(r, col):
    """Extract a numeric value from a DataFrame row dict, returning None for blanks.

    Args:
        r: Dict representing one row from the master DB DataFrame.
        col: Column name to extract.

    Returns:
        Float value if the cell is non-empty and parseable, otherwise None.
    """
    v = r.get(col)
    try:
        return float(v) if v not in ("", None) else None
    except (ValueError, TypeError):
        return None


@router.get("")
def list_young_guns(search: str = ""):
    """Return all Young Guns cards with full graded price and ownership data.

    Optionally filters by a free-text search string matched against player
    name, season, set, and team fields. Always returns the full unique
    season and team lists for populating filter dropdowns.

    Args:
        search: Optional free-text filter applied across PlayerName, Season,
                Set, and Team columns (case-insensitive substring match).
                Defaults to '' (no filter).

    Returns:
        Dict with keys 'cards' (list of card dicts with raw, PSA, and BGS
        price fields plus ownership info), 'seasons' (sorted list of unique
        season strings, descending), and 'teams' (sorted list of unique team
        strings).
    """
    df = load_master_db()
    if search:
        s = search.lower()
        mask = (
            df["PlayerName"].str.lower().str.contains(s, na=False)
            | df["Season"].astype(str).str.contains(s)
            | df["Set"].str.lower().str.contains(s, na=False)
            | df["Team"].str.lower().str.contains(s, na=False)
        )
        df = df[mask]

    cards = []
    for _, r in df.fillna("").iterrows():
        cards.append({
            "player":       r.get("PlayerName", ""),
            "season":       r.get("Season", ""),
            "set":          r.get("Set", ""),
            "card_number":  r.get("CardNumber", ""),
            "team":         r.get("Team", ""),
            "position":     r.get("Position", ""),
            "fair_value":   _num(r, "FairValue"),
            "num_sales":    _num(r, "NumSales"),
            "min":          _num(r, "Min"),
            "max":          _num(r, "Max"),
            "trend":        r.get("Trend", ""),
            "last_scraped": r.get("LastScraped", ""),
            # Graded prices
            "psa8_price":   _num(r, "PSA8_Value"),
            "psa8_sales":   _num(r, "PSA8_Sales"),
            "psa9_price":   _num(r, "PSA9_Value"),
            "psa9_sales":   _num(r, "PSA9_Sales"),
            "psa10_price":  _num(r, "PSA10_Value"),
            "psa10_sales":  _num(r, "PSA10_Sales"),
            "bgs9_price":   _num(r, "BGS9_Value"),
            "bgs9_sales":   _num(r, "BGS9_Sales"),
            "bgs95_price":  _num(r, "BGS9_5_Value"),
            "bgs95_sales":  _num(r, "BGS9_5_Sales"),
            "bgs10_price":  _num(r, "BGS10_Value"),
            "bgs10_sales":  _num(r, "BGS10_Sales"),
            # Ownership
            "owned":        bool(r.get("Owned", 0)),
            "cost_basis":   _num(r, "CostBasis"),
            "purchase_date": r.get("PurchaseDate", "") or "",
            # Full name for price-history lookup
            "card_name":    r.get("CardName", ""),
        })

    # Unique season + team lists for filter dropdowns
    seasons = sorted(df["Season"].dropna().astype(str).unique().tolist(), reverse=True)
    teams   = sorted(df["Team"].dropna().unique().tolist())

    return {"cards": cards, "seasons": seasons, "teams": teams}


@router.get("/market-movers")
def market_movers():
    """Return top 6 price gainers and top 6 losers from YG price history.

    Uses get_market_alerts with a minimum 2% change threshold. Splits the
    resulting alert list into 'gainers' (direction=='up') and 'losers'
    (direction=='down'), each capped at 6 entries.

    Returns:
        Dict with keys 'gainers' and 'losers', each a list of alert dicts
        with at minimum 'card_name', 'direction', and 'pct_change'.
    """
    history = load_yg_price_history()
    alerts = get_market_alerts(history, top_n=6, min_pct=2)
    gainers = [a for a in alerts if a["direction"] == "up"][:6]
    losers  = [a for a in alerts if a["direction"] == "down"][:6]
    return {"gainers": gainers, "losers": losers}


@router.get("/price-history/{card_name}")
def yg_price_history(card_name: str):
    """Return the full price history for a single YG card by path parameter.

    Note: for card names containing special characters (brackets, slashes,
    hashes) prefer the query-param variant GET /yg-price-history?name=.

    Args:
        card_name: Exact card name as stored in the YG price history JSON.

    Returns:
        Dict with keys 'card' (the card name string) and 'history' (list of
        snapshot dicts, each with 'date' and 'fair_value').

    Raises:
        HTTPException: 404 if no history entry exists for the given card name.
    """
    history = load_yg_price_history()
    entries = history.get(card_name)
    if entries is None:
        raise HTTPException(status_code=404, detail="Card not found in price history")
    return {"card": card_name, "history": entries}


@router.get("/portfolio-history")
def yg_portfolio_history():
    """Return time-series portfolio value snapshots for the YG master database.

    Returns:
        Dict with key 'history' containing a list of snapshot dicts from the
        YG portfolio history JSON file.
    """
    history = load_yg_portfolio_history()
    return {"history": history}


@router.get("/nhl-stats")
def nhl_stats():
    """Return YG cards merged with current-season NHL player stats.

    Joins the master DB rows with the nhl_player_stats JSON keyed by player
    name. Includes skater stats (goals, assists, points, plus_minus, shots),
    goalie stats (wins, save_pct, gaa), biographical data (birth_country,
    draft_overall, draft_round), and card pricing.

    Returns:
        Dict with key 'players' containing a list of merged row dicts.
        Players not found in the NHL stats data have None for stat fields.
    """
    df = load_master_db()
    stats_data = load_nhl_player_stats()
    players_data = stats_data.get("players", {})

    result = []
    for _, r in df.fillna("").iterrows():
        player_name = r.get("PlayerName", "")
        ps = players_data.get(player_name, {})
        cs = ps.get("current_season", {})
        bio = ps.get("bio", {})
        result.append({
            "player":        player_name,
            "team":          r.get("Team", ""),
            "position":      r.get("Position", ""),
            "season":        r.get("Season", ""),
            "fair_value":    _num(r, "FairValue"),
            "psa10_price":   _num(r, "PSA10_Value"),
            "psa9_price":    _num(r, "PSA9_Value"),
            "num_sales":     _num(r, "NumSales"),
            # Current-season stats (skaters)
            "games_played":  cs.get("games_played"),
            "goals":         cs.get("goals"),
            "assists":       cs.get("assists"),
            "points":        cs.get("points"),
            "plus_minus":    cs.get("plus_minus"),
            "shots":         cs.get("shots"),
            # Goalie-specific stats
            "wins":          cs.get("wins"),
            "save_pct":      cs.get("save_pct"),
            "gaa":           cs.get("gaa"),
            # Bio
            "birth_country": bio.get("birth_country", ""),
            "draft_overall": bio.get("draft_overall"),
            "draft_round":   bio.get("draft_round"),
        })
    return {"players": result}


@router.get("/seasonal-trends")
def seasonal_trends():
    """Return monthly average, maximum, and sample count aggregated from YG price history.

    Iterates all entries in the YG price history JSON, buckets them by
    YYYY-MM month, and computes summary statistics. Useful for identifying
    seasonal pricing patterns in the YG market.

    Returns:
        Dict with key 'months' containing a list of dicts sorted by month,
        each with 'month' (YYYY-MM string), 'avg_price', 'max_price', and
        'sample_count'. Returns {'months': []} if no history data exists.
    """
    history = load_yg_price_history()
    if not history:
        return {"months": []}

    monthly: dict[str, list] = {}
    for entries in history.values():
        for e in entries:
            date = e.get("date", "")
            price = e.get("fair_value")
            if not date or price is None:
                continue
            month = date[:7]
            monthly.setdefault(month, []).append(float(price))

    result = [
        {
            "month":        m,
            "avg_price":    round(sum(v) / len(v), 2),
            "max_price":    round(max(v), 2),
            "sample_count": len(v),
        }
        for m, v in sorted(monthly.items())
    ]
    return {"months": result}


@router.get("/grading-lookup/{player_name}")
def grading_lookup(player_name: str):
    """Return PSA and BGS graded price data for a player's cards.

    Priority:
    1. Master DB CSV (Young Guns + high-priority cards with explicit PSA/BGS values).
    2. rookie_price_history.graded_data (scraped graded prices for all catalog cards).

    Args:
        player_name: Player name to look up (path parameter, URL-encoded).

    Returns:
        Dict with key 'cards' containing a list of dicts with 'card_name',
        'season', 'fair_value', 'psa10_price', 'psa9_price', 'psa8_price',
        'psa10_mult', and 'psa9_mult'. Returns {'cards': []} if not found.
    """
    df = load_master_db()
    matches = df[df["PlayerName"].str.lower() == player_name.lower().strip()]
    if matches.empty:
        matches = df[df["PlayerName"].str.lower().str.contains(player_name.lower().strip(), na=False)]

    if not matches.empty:
        cards = []
        for _, r in matches.fillna("").iterrows():
            raw  = _num(r, "FairValue")
            p10  = _num(r, "PSA10_Value")
            p9   = _num(r, "PSA9_Value")
            p8   = _num(r, "PSA8_Value")
            b10  = _num(r, "BGS10_Value")
            b95  = _num(r, "BGS9_5_Value")
            b9   = _num(r, "BGS9_Value")
            cards.append({
                "card_name":   r.get("CardName", ""),
                "season":      r.get("Season", ""),
                "fair_value":  raw,
                "psa10_price": p10,
                "psa9_price":  p9,
                "psa8_price":  p8,
                "bgs10_price": b10,
                "bgs95_price": b95,
                "bgs9_price":  b9,
                "psa10_mult":  round(p10 / raw, 2) if raw and p10 else None,
                "psa9_mult":   round(p9  / raw, 2) if raw and p9  else None,
                "source":      "master_db",
            })
        return {"cards": cards}

    # Fallback 1: market_prices.graded_data (catalog-linked, populated by graded scraper)
    try:
        from psycopg2.extras import RealDictCursor
        with get_db() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT cc.player_name, cc.year, cc.set_name, cc.variant,
                           mp.fair_value, mp.graded_data
                    FROM card_catalog cc
                    JOIN market_prices mp ON mp.card_catalog_id = cc.id
                    WHERE cc.player_name ILIKE %s
                      AND mp.graded_data != '{}'
                    ORDER BY cc.year DESC, mp.fair_value DESC
                    LIMIT 10
                """, (f"%{player_name.strip()}%",))
                rows = cur.fetchall()

        if rows:
            def _gv(gd, grade): return float((gd.get(grade) or {}).get("fair_value") or 0)
            cards = []
            for r in rows:
                gd  = r.get("graded_data") or {}
                raw = float(r["fair_value"] or 0)
                p10 = _gv(gd, "PSA 10"); p9 = _gv(gd, "PSA 9"); p8 = _gv(gd, "PSA 8")
                b10 = _gv(gd, "BGS 10"); b95 = _gv(gd, "BGS 9.5"); b9 = _gv(gd, "BGS 9")
                variant = r.get("variant") or ""
                suffix = f" {variant}" if variant and variant.lower() != "base" else ""
                cards.append({
                    "card_name":   f"{r['year']} {r['set_name']}{suffix}",
                    "season":      str(r["year"] or ""),
                    "fair_value":  raw,
                    "psa10_price": p10, "psa9_price": p9, "psa8_price": p8,
                    "bgs10_price": b10, "bgs95_price": b95, "bgs9_price": b9,
                    "psa10_mult":  round(p10 / raw, 2) if raw and p10 else None,
                    "psa9_mult":   round(p9  / raw, 2) if raw and p9  else None,
                    "source":      "market_prices",
                })
            return {"cards": cards}

        # Fallback 2: legacy rookie_price_history.graded_data
        with get_db() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT player, season, fair_value, graded_data
                    FROM rookie_price_history
                    WHERE player ILIKE %s AND graded_data != '{}'
                    ORDER BY date DESC LIMIT 10
                """, (f"%{player_name.strip()}%",))
                rows = cur.fetchall()
        if not rows:
            return {"cards": []}
        def _gv2(gd, grade): return float((gd.get(grade) or {}).get("fair_value") or 0)
        cards = []; seen = set()
        for r in rows:
            if r["player"] in seen: continue
            seen.add(r["player"])
            gd = r.get("graded_data") or {}; raw = float(r["fair_value"] or 0)
            p10 = _gv2(gd, "PSA 10"); p9 = _gv2(gd, "PSA 9"); p8 = _gv2(gd, "PSA 8")
            b10 = _gv2(gd, "BGS 10"); b95 = _gv2(gd, "BGS 9.5"); b9 = _gv2(gd, "BGS 9")
            cards.append({
                "card_name": r["player"], "season": r.get("season", ""),
                "fair_value": raw,
                "psa10_price": p10, "psa9_price": p9, "psa8_price": p8,
                "bgs10_price": b10, "bgs95_price": b95, "bgs9_price": b9,
                "psa10_mult": round(p10/raw,2) if raw and p10 else None,
                "psa9_mult":  round(p9/raw,2)  if raw and p9  else None,
                "source": "price_history",
            })
        return {"cards": cards}
    except Exception:
        return {"cards": []}


@router.get("/yg-price-history")
def yg_price_history_by_name(name: str):
    """Return price history for a card — queries market_price_history first,
    falls back to legacy JSON store if no DB records found.

    Args:
        name: Card name string (query param).

    Returns:
        Dict with keys 'card' and 'history' (list of {date, fair_value} dicts).
    """
    # Try market_price_history (new DB-backed history)
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                # Extract player name from card name for fuzzy catalog match
                cur.execute("""
                    SELECT mph.scraped_at, mph.fair_value, mph.confidence, mph.num_sales
                    FROM market_price_history mph
                    JOIN card_catalog cc ON cc.id = mph.card_catalog_id
                    WHERE cc.player_name ILIKE %s
                    ORDER BY mph.scraped_at ASC
                    LIMIT 365
                """, (f"%{name.split(' - ')[-1].strip()}%",))
                rows = cur.fetchall()
                if rows:
                    return {
                        "card": name,
                        "history": [
                            {"date": str(r[0]), "fair_value": float(r[1]),
                             "confidence": r[2], "num_sales": r[3]}
                            for r in rows
                        ]
                    }
    except Exception:
        pass

    # Fallback to legacy JSON
    history = load_yg_price_history()
    entries = history.get(name)
    if not entries:
        return {"card": name, "history": []}
    return {"card": name, "history": entries}


def _do_yg_scrape(player: str, season: str):
    """Background task: scrape eBay sales for one YG card and update the master DB.

    Looks up the card's full name from the master DB, calls scrape_single_card,
    and writes the resulting fair price, trend, min/max, num_sales, and
    last-scraped date back to the master DB CSV. Silently no-ops on errors
    or when no sales data is returned.

    Args:
        player: PlayerName string to identify the row in the master DB.
        season: Season string (e.g. '2020-21') to uniquely identify the row
                alongside the player name.
    """
    try:
        df = load_master_db()
        mask = (df["PlayerName"] == player) & (df["Season"].astype(str) == str(season))
        if not mask.any():
            return
        card_name = str(df.loc[mask, "CardName"].iloc[0])
        result = scrape_single_card(card_name)
        if not result:
            return
        stats = result.get("stats", {})
        if stats.get("num_sales", 0) > 0:
            df.loc[mask, "FairValue"]   = stats.get("fair_price", 0)
            df.loc[mask, "Trend"]       = stats.get("trend", "")
            df.loc[mask, "Min"]         = stats.get("min", 0)
            df.loc[mask, "Max"]         = stats.get("max", 0)
            df.loc[mask, "NumSales"]    = stats.get("num_sales", 0)
            df.loc[mask, "LastScraped"] = datetime.date.today().isoformat()
            save_master_db(df)
    except Exception as e:
        print(f"[yg_scrape] Error for {player} {season}: {e}")


@router.post("/scrape")
def scrape_yg_card(player: str, season: str, background_tasks: BackgroundTasks):
    """Trigger an asynchronous eBay re-scrape for a single YG card.

    Validates the card exists in the master DB, then schedules _do_yg_scrape
    as a FastAPI background task. The response returns immediately.

    Args:
        player: PlayerName query param to identify the YG card row.
        season: Season query param (e.g. '2020-21') to uniquely identify the row.
        background_tasks: FastAPI BackgroundTasks instance for deferred execution.

    Returns:
        Dict with keys 'status' ('queued') and 'card' (the full card name string).

    Raises:
        HTTPException: 404 if the master DB is empty or no matching row is found.
    """
    df = load_master_db()
    if df.empty:
        raise HTTPException(status_code=404, detail="Master DB not found")
    mask = (df["PlayerName"] == player) & (df["Season"].astype(str) == str(season))
    if not mask.any():
        raise HTTPException(status_code=404, detail="Card not found")
    card_name = str(df.loc[mask, "CardName"].iloc[0])
    background_tasks.add_task(_do_yg_scrape, player, season)
    return {"status": "queued", "card": card_name}


class OwnershipUpdate(BaseModel):
    owned: bool = False
    cost_basis: Optional[float] = None
    purchase_date: Optional[str] = None


@router.patch("/ownership")
def update_ownership(player: str, season: str, body: OwnershipUpdate):
    """Update ownership metadata for a YG card row in the master database.

    Writes the Owned flag (1/0), and optionally CostBasis and PurchaseDate,
    to the matching row in the master DB CSV. The PurchaseDate column is
    created if it does not already exist.

    Args:
        player: PlayerName query param identifying the card row.
        season: Season query param (e.g. '2020-21') identifying the card row.
        body: OwnershipUpdate payload with 'owned' (bool), optional
              'cost_basis' (float), and optional 'purchase_date' (str).

    Returns:
        Dict with key 'status' set to 'updated'.

    Raises:
        HTTPException: 404 if the master DB is empty or no matching row is found.
    """
    df = load_master_db()
    if df.empty:
        raise HTTPException(status_code=404, detail="Master DB not found")

    mask = (df["PlayerName"] == player) & (df["Season"].astype(str) == str(season))
    if not mask.any():
        raise HTTPException(status_code=404, detail="Card not found")

    df.loc[mask, "Owned"] = 1 if body.owned else 0
    if body.cost_basis is not None:
        df.loc[mask, "CostBasis"] = body.cost_basis
    if body.purchase_date is not None:
        if "PurchaseDate" not in df.columns:
            df["PurchaseDate"] = ""
        df.loc[mask, "PurchaseDate"] = body.purchase_date

    save_master_db(df)
    return {"status": "updated"}


