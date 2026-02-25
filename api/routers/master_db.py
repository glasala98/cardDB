"""Master DB endpoints — Young Guns market database."""

from fastapi import APIRouter, HTTPException

from dashboard_utils import (
    load_master_db,
    load_yg_price_history,
    load_yg_portfolio_history,
    load_nhl_player_stats,
)

router = APIRouter()


@router.get("")
def list_young_guns(search: str = ""):
    """Return all Young Guns cards."""
    df = load_master_db()
    if search:
        s = search.lower()
        mask = (
            df["PlayerName"].str.lower().str.contains(s, na=False)
            | df["Season"].astype(str).str.contains(s)
            | df["Set"].str.lower().str.contains(s, na=False)
        )
        df = df[mask]

    cards = []
    for _, r in df.fillna("").iterrows():
        cards.append({
            "player":      r.get("PlayerName", ""),
            "season":      r.get("Season", ""),
            "set":         r.get("Set", ""),
            "card_number": r.get("CardNumber", ""),
            "team":        r.get("Team", ""),
            "position":    r.get("Position", ""),
            "fair_value":  r.get("FairValue") or None,
            "num_sales":   r.get("NumSales") or None,
            "psa10_price": r.get("PSA10_Value") or None,
            "psa10_sales": r.get("PSA10_Sales") or None,
            "psa9_price":  r.get("PSA9_Value") or None,
            "bgs95_price": r.get("BGS9_5_Value") or None,
            "trend":       r.get("Trend", ""),
            "owned":       bool(r.get("Owned", 0)),
            "cost_basis":  r.get("CostBasis") or None,
        })
    return {"cards": cards}


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
