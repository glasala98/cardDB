"""Master DB endpoints — Young Guns market database."""

import os
from fastapi import APIRouter, HTTPException

from dashboard_utils import (
    load_master_db,
    load_yg_price_history,
    load_yg_portfolio_history,
    load_nhl_player_stats,
)

router = APIRouter()

MASTER_DB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "master_db"
)


@router.get("")
def list_young_guns(search: str = ""):
    """Return all Young Guns cards."""
    df = load_master_db()
    if search:
        mask = (
            df.get("Player", df.iloc[:, 0]).str.contains(search, case=False, na=False)
            | df.get("Year",   df.iloc[:, 0]).astype(str).str.contains(search)
            | df.get("Set",    df.iloc[:, 0]).str.contains(search, case=False, na=False)
        )
        df = df[mask]

    cards = []
    for _, r in df.fillna("").iterrows():
        cards.append({
            "player":      r.get("Player", ""),
            "year":        r.get("Year", ""),
            "set":         r.get("Set", ""),
            "card_number": r.get("Card #", ""),
            "raw_price":   r.get("Raw Price") or None,
            "psa10_price": r.get("PSA 10") or None,
            "bgs95_price": r.get("BGS 9.5") or None,
            "trend":       r.get("Trend", ""),
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
    stats = load_nhl_player_stats()
    players = []
    for player, data in stats.items():
        s = data.get("stats", {})
        players.append({
            "player":     player,
            "team":       data.get("team", ""),
            "position":   data.get("position", ""),
            "gp":         s.get("gp", 0),
            "goals":      s.get("goals", 0),
            "assists":    s.get("assists", 0),
            "points":     s.get("points", 0),
            "plus_minus": s.get("plusMinus", 0),
        })
    return {"players": players}
