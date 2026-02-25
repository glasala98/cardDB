"""Card ledger endpoints — personal collection CRUD."""

import os
import json
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from dashboard_utils import (
    load_data, save_data, archive_card, restore_card, load_archive,
    load_price_history, load_portfolio_history, append_price_history,
    scrape_single_card,
    get_user_paths, CSV_PATH, RESULTS_JSON_PATH, MONEY_COLS,
)

router = APIRouter()

DEFAULT_USER = "admin"


def _get_paths(user: str = DEFAULT_USER):
    try:
        return get_user_paths(user)
    except Exception:
        base = os.path.dirname(CSV_PATH)
        return {
            "csv":        CSV_PATH,
            "results":    RESULTS_JSON_PATH,
            "history":    os.path.join(base, "price_history.json"),
            "portfolio":  os.path.join(base, "portfolio_history.json"),
            "archive":    os.path.join(base, "card_archive.csv"),
            "backup_dir": os.path.join(base, "backups"),
        }


def _normalise_row(r: dict) -> dict:
    """Convert a DataFrame row dict to the API card shape."""
    return {
        "card_name":    r.get("Card Name", ""),
        "fair_value":   r.get("Fair Value")   or None,
        "cost_basis":   r.get("Cost Basis")   or None,
        "purchase_date": r.get("Purchase Date", "") or "",
        "tags":         r.get("Tags", "") or "",
        "trend":        r.get("Trend", ""),
        "num_sales":    r.get("Num Sales") or 0,
        "median_all":   r.get("Median (All)") or None,
        "min":          r.get("Min") or None,
        "max":          r.get("Max") or None,
        "top3":         r.get("Top 3 Prices", ""),
        "last_scraped": r.get("Last Scraped", ""),
    }


# ── Request bodies ────────────────────────────────────────────────────────────

class CardUpdate(BaseModel):
    fair_value:    Optional[float] = None
    cost_basis:    Optional[float] = None
    purchase_date: Optional[str]   = None
    tags:          Optional[str]   = None


class CardCreate(BaseModel):
    card_name:     str
    cost_basis:    Optional[float] = 0.0
    purchase_date: Optional[str]   = ""
    tags:          Optional[str]   = ""


# ── Read endpoints ────────────────────────────────────────────────────────────

@router.get("")
def list_cards(user: str = DEFAULT_USER):
    """Return all cards for the ledger table."""
    paths = _get_paths(user)
    df = load_data(paths["csv"], paths["results"])
    return {"cards": [_normalise_row(r) for r in df.fillna("").to_dict(orient="records")]}


@router.get("/portfolio-history")
def portfolio_history(user: str = DEFAULT_USER):
    """Return portfolio value snapshots."""
    paths = _get_paths(user)
    hist_dir = os.path.dirname(paths["history"])
    portfolio_path = os.path.join(hist_dir, "portfolio_history.json")
    return {"history": load_portfolio_history(portfolio_path=portfolio_path)}


@router.get("/archive")
def list_archive(user: str = DEFAULT_USER):
    """Return all archived cards."""
    paths = _get_paths(user)
    try:
        archive_df = load_archive(archive_path=paths["archive"])
        cards = [
            {
                "card_name":     r.get("Card Name", ""),
                "archived_date": r.get("Archived Date", ""),
                "fair_value":    r.get("Fair Value") or None,
            }
            for r in archive_df.fillna("").to_dict(orient="records")
        ]
        return {"cards": cards}
    except Exception:
        return {"cards": []}


@router.get("/{card_name}")
def card_detail(card_name: str, user: str = DEFAULT_USER):
    """Return full detail for a single card (price history, sales, confidence)."""
    paths = _get_paths(user)
    df = load_data(paths["csv"], paths["results"])

    match = df[df["Card Name"] == card_name]
    if match.empty:
        raise HTTPException(status_code=404, detail="Card not found")

    card = _normalise_row(match.iloc[0].fillna("").to_dict())

    # Price history — deduplicated by date (keep latest value per date)
    price_history = []
    if os.path.exists(paths["history"]):
        entries = load_price_history(card_name, history_path=paths["history"])
        seen_dates = {}
        for e in entries:
            d = e.get("date", "")
            if d and e.get("fair_value"):
                seen_dates[d] = e["fair_value"]   # last write wins
        price_history = [{"date": d, "price": p} for d, p in sorted(seen_dates.items())]

    # Raw sales + confidence
    raw_sales = []
    confidence = "unknown"
    search_url = None
    if os.path.exists(paths["results"]):
        with open(paths["results"], "r", encoding="utf-8") as f:
            results = json.load(f)
        card_result = results.get(card_name, {})
        confidence  = card_result.get("confidence", "unknown") or "unknown"
        search_url  = card_result.get("search_url")
        raw_sales = [
            {
                "sold_date":   s.get("sold_date", ""),
                # Strip eBay's appended "Opens in a new window or tab" text
                "title":       s.get("title", "").split("\n")[0].strip(),
                "price":       s.get("price_val") or s.get("price"),
                "listing_url": s.get("listing_url"),
            }
            for s in card_result.get("raw_sales", [])
        ]

    return {
        "card":          card,
        "price_history": price_history,
        "raw_sales":     raw_sales,
        "confidence":    confidence,
        "search_url":    search_url,
    }


# ── Write endpoints ───────────────────────────────────────────────────────────

@router.post("")
def add_card(body: CardCreate, user: str = DEFAULT_USER):
    """Add a new card to the collection."""
    paths = _get_paths(user)
    df = load_data(paths["csv"], paths["results"])

    if body.card_name in df["Card Name"].values:
        raise HTTPException(status_code=409, detail="Card already exists")

    new_row = pd.DataFrame([{
        "Card Name":    body.card_name,
        "Fair Value":   0,
        "Cost Basis":   body.cost_basis or 0,
        "Purchase Date": body.purchase_date or "",
        "Tags":         body.tags or "",
        "Trend":        "",
        "Top 3 Prices": "",
        "Median (All)": 0,
        "Min":          0,
        "Max":          0,
        "Num Sales":    0,
    }])
    df = pd.concat([df, new_row], ignore_index=True)
    save_data(df, paths["csv"])
    return {"status": "ok", "card_name": body.card_name}


@router.patch("/{card_name}")
def update_card(card_name: str, body: CardUpdate, user: str = DEFAULT_USER):
    """Update editable fields on a card."""
    paths = _get_paths(user)
    df = load_data(paths["csv"], paths["results"])

    match = df[df["Card Name"] == card_name]
    if match.empty:
        raise HTTPException(status_code=404, detail="Card not found")

    i = match.index[0]
    if body.fair_value    is not None: df.at[i, "Fair Value"]    = body.fair_value
    if body.cost_basis    is not None: df.at[i, "Cost Basis"]    = body.cost_basis
    if body.purchase_date is not None: df.at[i, "Purchase Date"] = body.purchase_date
    if body.tags          is not None: df.at[i, "Tags"]          = body.tags

    save_data(df, paths["csv"])
    return {"status": "ok"}


@router.delete("/{card_name}")
def archive_card_endpoint(card_name: str, user: str = DEFAULT_USER):
    """Archive (soft-delete) a card."""
    paths = _get_paths(user)
    df = load_data(paths["csv"], paths["results"])

    if df[df["Card Name"] == card_name].empty:
        raise HTTPException(status_code=404, detail="Card not found")

    df = archive_card(df, card_name, archive_path=paths["archive"])
    save_data(df, paths["csv"])
    return {"status": "archived"}


@router.post("/restore/{card_name}")
def restore_card_endpoint(card_name: str, user: str = DEFAULT_USER):
    """Restore a card from the archive."""
    paths = _get_paths(user)
    card_data = restore_card(card_name, archive_path=paths["archive"])
    if not card_data:
        raise HTTPException(status_code=404, detail="Card not found in archive")

    # Convert "$X.XX" money strings back to floats
    for col in MONEY_COLS:
        if col in card_data:
            val = str(card_data[col]).replace("$", "").replace(",", "").strip()
            try:
                card_data[col] = float(val)
            except ValueError:
                card_data[col] = 0.0
    card_data.pop("Archived Date", None)

    df = load_data(paths["csv"], paths["results"])
    df = pd.concat([df, pd.DataFrame([card_data])], ignore_index=True)
    save_data(df, paths["csv"])
    return {"status": "restored", "card_name": card_name}


# ── Scrape endpoint ───────────────────────────────────────────────────────────

def _do_scrape(card_name: str, paths: dict):
    """Background task: scrape one card and save results."""
    try:
        result = scrape_single_card(card_name, results_json_path=paths["results"])
        if not result:
            return
        stats = result.get("stats", {})
        df = load_data(paths["csv"], paths["results"])
        idx = df[df["Card Name"] == card_name].index
        if len(idx) == 0:
            return
        i = idx[0]
        if stats.get("num_sales", 0) > 0:
            df.at[i, "Fair Value"]   = stats.get("fair_price", 0)
            df.at[i, "Trend"]        = stats.get("trend", "")
            df.at[i, "Median (All)"] = stats.get("median_all", 0)
            df.at[i, "Min"]          = stats.get("min", 0)
            df.at[i, "Max"]          = stats.get("max", 0)
            df.at[i, "Num Sales"]    = stats.get("num_sales", 0)
            df.at[i, "Top 3 Prices"] = " | ".join(stats.get("top_3_prices", []))
            append_price_history(
                card_name, stats.get("fair_price", 0),
                stats.get("num_sales", 0), history_path=paths["history"]
            )
        save_data(df, paths["csv"])
        print(f"[scrape] Done: {card_name} → ${stats.get('fair_price', 0):.2f}")
    except Exception as e:
        print(f"[scrape] Error for {card_name}: {e}")


@router.post("/{card_name}/scrape")
def scrape_card(card_name: str, background_tasks: BackgroundTasks, user: str = DEFAULT_USER):
    """Trigger a background re-scrape for a single card."""
    paths = _get_paths(user)
    df = load_data(paths["csv"], paths["results"])
    if df[df["Card Name"] == card_name].empty:
        raise HTTPException(status_code=404, detail="Card not found")
    background_tasks.add_task(_do_scrape, card_name, paths)
    return {"status": "queued", "card": card_name}
