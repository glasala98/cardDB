"""Master DB endpoints — Young Guns market database."""

from fastapi import APIRouter, HTTPException

from dashboard_utils import (
    load_master_db,
    load_yg_price_history,
    load_yg_portfolio_history,
    load_nhl_player_stats,
    get_market_alerts,
)

router = APIRouter()


def _num(r, col):
    v = r.get(col)
    try:
        return float(v) if v not in ("", None) else None
    except (ValueError, TypeError):
        return None


@router.get("")
def list_young_guns(search: str = ""):
    """Return all Young Guns cards with full graded price data."""
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
        })

    # Unique season + team lists for filter dropdowns
    seasons = sorted(df["Season"].dropna().astype(str).unique().tolist(), reverse=True)
    teams   = sorted(df["Team"].dropna().unique().tolist())

    return {"cards": cards, "seasons": seasons, "teams": teams}


@router.get("/market-movers")
def market_movers():
    """Return top gainers + losers from YG price history."""
    history = load_yg_price_history()
    alerts = get_market_alerts(history, top_n=6, min_pct=2)
    gainers = [a for a in alerts if a["direction"] == "up"][:6]
    losers  = [a for a in alerts if a["direction"] == "down"][:6]
    return {"gainers": gainers, "losers": losers}


@router.get("/price-history/{card_name}")
def yg_price_history(card_name: str):
    """Return price history for a single YG card."""
    history = load_yg_price_history()
    entries = history.get(card_name)
    if entries is None:
        raise HTTPException(status_code=404, detail="Card not found in price history")
    return {"card": card_name, "history": entries}


@router.get("/portfolio-history")
def yg_portfolio_history():
    """Return YG portfolio history snapshots."""
    history = load_yg_portfolio_history()
    return {"history": history}


@router.get("/nhl-stats")
def nhl_stats():
    """Return YG cards merged with live NHL player stats for correlation analytics."""
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
            # Current-season stats
            "games_played":  cs.get("games_played"),
            "goals":         cs.get("goals"),
            "assists":       cs.get("assists"),
            "points":        cs.get("points"),
            "plus_minus":    cs.get("plus_minus"),
            "shots":         cs.get("shots"),
            # Bio
            "birth_country": bio.get("birth_country", ""),
            "draft_overall": bio.get("draft_overall"),
            "draft_round":   bio.get("draft_round"),
        })
    return {"players": result}


@router.get("/seasonal-trends")
def seasonal_trends():
    """Return monthly avg price aggregated from YG price history."""
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
    """Return PSA/BGS graded prices for a player (for ROI calculator)."""
    df = load_master_db()
    matches = df[df["PlayerName"].str.lower() == player_name.lower().strip()]
    if matches.empty:
        # Fuzzy — contains
        matches = df[df["PlayerName"].str.lower().str.contains(player_name.lower().strip(), na=False)]
    if matches.empty:
        return {"cards": []}

    cards = []
    for _, r in matches.fillna("").iterrows():
        raw = _num(r, "FairValue")
        p10 = _num(r, "PSA10_Value")
        p9  = _num(r, "PSA9_Value")
        p8  = _num(r, "PSA8_Value")
        cards.append({
            "card_name":   r.get("CardName", ""),
            "season":      r.get("Season", ""),
            "fair_value":  raw,
            "psa10_price": p10,
            "psa9_price":  p9,
            "psa8_price":  p8,
            "psa10_mult":  round(p10 / raw, 2) if raw and p10 else None,
            "psa9_mult":   round(p9  / raw, 2) if raw and p9  else None,
        })
    return {"cards": cards}


@router.get("/nhl-stats")
def nhl_stats():
    """Return NHL player stats for all tracked players."""
    raw = load_nhl_player_stats()
    players_data = raw.get("players", {})
    players = []
    for player, data in players_data.items():
        s = data.get("current_season", {})
        players.append({
            "player":     player,
            "team":       data.get("current_team", ""),
            "position":   data.get("position", ""),
            "gp":         s.get("games_played", 0),
            "goals":      s.get("goals", 0),
            "assists":    s.get("assists", 0),
            "points":     s.get("points", 0),
            "plus_minus": s.get("plus_minus", 0),
            "shots":      s.get("shots", 0),
        })
    return {"players": players}
