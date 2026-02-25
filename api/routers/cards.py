"""Card ledger endpoints — personal collection data."""

import os
import json
from fastapi import APIRouter, HTTPException, BackgroundTasks

from dashboard_utils import (
    load_data, load_price_history, load_portfolio_history,
    get_user_paths, CSV_PATH, RESULTS_JSON_PATH,
)

router = APIRouter()

# TODO: wire up real auth; for now always use admin user
DEFAULT_USER = "admin"


def _get_paths(user: str = DEFAULT_USER):
    try:
        paths = get_user_paths(user)
    except Exception:
        paths = {
            "csv": CSV_PATH,
            "results": RESULTS_JSON_PATH,
            "history": os.path.join(os.path.dirname(CSV_PATH), "price_history.json"),
        }
    return paths


@router.get("")
def list_cards(user: str = DEFAULT_USER):
    """Return all cards as a flat list for the ledger table."""
    paths = _get_paths(user)
    df = load_data(paths["csv"], paths["results"])
    cards = df.fillna("").to_dict(orient="records")
    # Normalise column names to snake_case
    normalised = [
        {
            "card_name":  r.get("Card Name", ""),
            "fair_value": r.get("Fair Value") or None,
            "cost_basis": r.get("Cost Basis") or None,
            "trend":      r.get("Trend", ""),
            "num_sales":  r.get("Num Sales") or 0,
            "last_sale":  r.get("Last Sale", ""),
            "top3":       r.get("Top 3 Prices", ""),
        }
        for r in cards
    ]
    return {"cards": normalised}


@router.get("/portfolio-history")
def portfolio_history(user: str = DEFAULT_USER):
    """Return portfolio value snapshots."""
    paths = _get_paths(user)
    hist_dir = os.path.dirname(paths["history"])
    portfolio_path = os.path.join(hist_dir, "portfolio_history.json")
    history = load_portfolio_history(portfolio_path=portfolio_path)
    return {"history": history}


@router.get("/{card_name}")
def card_detail(card_name: str, user: str = DEFAULT_USER):
    """Return full detail for a single card."""
    paths = _get_paths(user)
    df = load_data(paths["csv"], paths["results"])

    match = df[df["Card Name"] == card_name]
    if match.empty:
        raise HTTPException(status_code=404, detail="Card not found")

    row = match.iloc[0].fillna("").to_dict()
    card = {
        "card_name":  row.get("Card Name", ""),
        "fair_value": row.get("Fair Value") or None,
        "cost_basis": row.get("Cost Basis") or None,
        "trend":      row.get("Trend", ""),
        "num_sales":  row.get("Num Sales") or 0,
        "median_all": row.get("Median (All)") or None,
        "min":        row.get("Min") or None,
        "max":        row.get("Max") or None,
    }

    # Price history
    price_history = []
    if os.path.exists(paths["history"]):
        raw = load_price_history(history_path=paths["history"])
        entries = raw.get(card_name, [])
        price_history = [
            {"date": e.get("date", ""), "price": e.get("fair_price", 0)}
            for e in entries
            if e.get("fair_price")
        ]

    # Raw sales + confidence
    raw_sales = []
    confidence = "unknown"
    results_path = paths.get("results", RESULTS_JSON_PATH)
    if os.path.exists(results_path):
        with open(results_path, "r", encoding="utf-8") as f:
            results = json.load(f)
        card_result = results.get(card_name, {})
        confidence = card_result.get("confidence", "unknown")
        raw_sales = [
            {
                "sold_date": s.get("sold_date", ""),
                "title":     s.get("title", ""),
                "price":     s.get("price_val") or s.get("price"),
            }
            for s in card_result.get("raw_sales", [])
        ]

    return {
        "card": card,
        "price_history": price_history,
        "raw_sales": raw_sales,
        "confidence": confidence,
    }


@router.post("/{card_name}/scrape")
def scrape_card(card_name: str, background_tasks: BackgroundTasks, user: str = DEFAULT_USER):
    """Trigger a background re-scrape for a single card.
    Returns immediately; scrape runs in background.
    """
    # TODO: implement single-card scrape via dashboard_utils.scrape_single_card
    return {"status": "queued", "card": card_name}
