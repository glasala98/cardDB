"""Card ledger endpoints — personal collection CRUD."""

import io
import os
import json
import re
import datetime
import hashlib
import urllib.request
import urllib.parse
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File
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
    """Resolve file paths for a given user's data directory.

    Falls back to the global admin paths if user-specific paths cannot be
    determined (e.g. single-user deployments without users.yaml).

    Args:
        user: Username whose paths should be resolved. Defaults to 'admin'.

    Returns:
        Dict with keys 'csv', 'results', 'history', 'portfolio', 'archive',
        and 'backup_dir', each mapped to an absolute file path string.
    """
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
    """Convert a DataFrame row dict to the canonical API card shape.

    Maps raw CSV column names (e.g. 'Card Name', 'Fair Value') to the
    snake_case keys expected by the frontend (e.g. 'card_name', 'fair_value').
    Missing or falsy values are normalised to None or empty string as
    appropriate.

    Args:
        r: Dict representing one row from the cards DataFrame, with original
           column names as keys.

    Returns:
        Dict with standardised API field names suitable for JSON serialisation.
    """
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
        # Parsed from card name
        "player":       r.get("Player", "") or "",
        "year":         r.get("Year", "") or "",
        "set_name":     r.get("Set", "") or "",
        "subset":       r.get("Subset", "") or "",
        "card_number":  r.get("Card #", "") or "",
        "serial":       r.get("Serial", "") or "",
        "grade":        r.get("Grade", "") or "",
        "confidence":   r.get("Confidence", "") or "",
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
    """Return all cards in the collection for the ledger table.

    Loads the cards CSV and results JSON, merges them, and returns every row
    in the normalised API shape.

    Args:
        user: Username whose collection to load. Defaults to 'admin'.

    Returns:
        Dict with key 'cards' containing a list of normalised card dicts.
    """
    paths = _get_paths(user)
    df = load_data(paths["csv"], paths["results"])
    return {"cards": [_normalise_row(r) for r in df.fillna("").to_dict(orient="records")]}


@router.get("/portfolio-history")
def portfolio_history(user: str = DEFAULT_USER):
    """Return time-series portfolio value recalculated from per-card price history.

    Dynamically sums fair values from price_history.json for each date, using
    only cards currently in the collection. Archived cards are excluded so a
    card added then removed within a day won't cause a spike. Today's live
    values from the CSV are always appended as the final data point.

    Args:
        user: Username whose portfolio history to load. Defaults to 'admin'.

    Returns:
        Dict with key 'history' containing a list of snapshot dicts each with
        'date', 'total_value', 'total_cards', and 'avg_value'.
    """
    paths = _get_paths(user)
    df = load_data(paths["csv"], paths["results"])
    current_cards = set(df["Card Name"].tolist())

    date_totals: dict = {}
    if os.path.exists(paths["history"]):
        try:
            with open(paths["history"], "r", encoding="utf-8") as f:
                price_hist = json.load(f)
        except Exception:
            price_hist = {}

        for card_name, entries in price_hist.items():
            if card_name not in current_cards:
                continue  # skip archived / removed cards
            for entry in entries:
                d = entry.get("date")
                v = float(entry.get("fair_value") or 0)
                if d and v > 0:
                    bucket = date_totals.setdefault(d, {"total": 0.0, "count": 0})
                    bucket["total"] += v
                    bucket["count"] += 1

    # Always include today's live CSV values as the rightmost point
    today = datetime.date.today().isoformat()
    try:
        today_vals = df["Fair Value"].fillna(0).astype(float)
        today_total = round(float(today_vals.sum()), 2)
        today_count = int((today_vals > 0).sum())
        if today_total > 0:
            date_totals[today] = {"total": today_total, "count": today_count}
    except Exception:
        pass

    history = [
        {
            "date":        d,
            "total_value": round(b["total"], 2),
            "total_cards": b["count"],
            "avg_value":   round(b["total"] / b["count"], 2) if b["count"] else 0,
        }
        for d, b in sorted(date_totals.items())
    ]
    return {"history": history}


@router.get("/archive")
def list_archive(user: str = DEFAULT_USER):
    """Return all soft-deleted (archived) cards.

    Reads the card_archive.csv for the given user. Returns an empty list if
    no archive file exists rather than raising an error.

    Args:
        user: Username whose archive to load. Defaults to 'admin'.

    Returns:
        Dict with key 'cards' containing a list of dicts, each with
        'card_name', 'archived_date', and 'fair_value'.
    """
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


@router.get("/detail")
def card_detail(name: str, user: str = DEFAULT_USER):
    """Return full detail for a single card including price history and raw sales.

    Loads both the cards CSV and the results JSON to build a combined response.
    Price history entries are deduplicated by date (latest value wins).
    Raw sale titles have eBay's appended accessibility text stripped.

    Args:
        name: Exact card name to look up (passed as query param to avoid
              path-encoding issues with brackets and slashes).
        user: Username whose data to query. Defaults to 'admin'.

    Returns:
        Dict with keys: 'card' (normalised card dict), 'price_history' (list of
        {'date', 'price'} dicts), 'raw_sales' (list of sale dicts), 'confidence',
        'search_url', 'image_url', 'image_url_back', 'is_estimated', 'price_source'.

    Raises:
        HTTPException: 404 if no card with that name exists in the collection.
    """
    card_name = name
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
        confidence     = card_result.get("confidence", "unknown") or "unknown"
        search_url     = card_result.get("search_url")
        image_url      = card_result.get("image_url")
        image_url_back = card_result.get("image_url_back")
        is_estimated   = bool(card_result.get("is_estimated", False))
        price_source   = card_result.get("price_source", "direct") or "direct"
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
        "card":           card,
        "price_history":  price_history,
        "raw_sales":      raw_sales,
        "confidence":     confidence,
        "search_url":     search_url,
        "image_url":      image_url,
        "image_url_back": image_url_back,
        "is_estimated":   is_estimated,
        "price_source":   price_source,
    }


# ── Write endpoints ───────────────────────────────────────────────────────────

@router.post("")
def add_card(body: CardCreate, user: str = DEFAULT_USER):
    """Add a new card to the collection.

    Appends a row to the user's cards CSV with default pricing values of zero.
    The card can then be scraped separately to populate market data.

    Args:
        body: CardCreate payload with card_name (required), cost_basis,
              purchase_date, and tags.
        user: Username whose collection to update. Defaults to 'admin'.

    Returns:
        Dict with keys 'status' ('ok') and 'card_name'.

    Raises:
        HTTPException: 409 if a card with the same name already exists.
    """
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


@router.patch("/update")
def update_card(name: str, body: CardUpdate, user: str = DEFAULT_USER):
    """Update editable fields on a card.

    Only fields explicitly provided in the request body are written; omitted
    fields are left unchanged. Supports updating fair_value, cost_basis,
    purchase_date, and tags.

    Args:
        name: Exact card name to update (query param).
        body: CardUpdate payload with optional fields to overwrite.
        user: Username whose collection to update. Defaults to 'admin'.

    Returns:
        Dict with key 'status' set to 'ok'.

    Raises:
        HTTPException: 404 if no card with that name exists.
    """
    card_name = name
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


@router.delete("/archive")
def archive_card_endpoint(name: str, user: str = DEFAULT_USER):
    """Archive (soft-delete) a card, moving it out of the active collection.

    The card row is removed from the live CSV and appended to card_archive.csv
    with an 'Archived Date' timestamp. It can be restored via POST /restore.

    Args:
        name: Exact card name to archive (query param).
        user: Username whose collection to update. Defaults to 'admin'.

    Returns:
        Dict with key 'status' set to 'archived'.

    Raises:
        HTTPException: 404 if no card with that name exists in the active collection.
    """
    card_name = name
    paths = _get_paths(user)
    df = load_data(paths["csv"], paths["results"])

    if df[df["Card Name"] == card_name].empty:
        raise HTTPException(status_code=404, detail="Card not found")

    df = archive_card(df, card_name, archive_path=paths["archive"])
    save_data(df, paths["csv"])
    return {"status": "archived"}


@router.post("/restore")
def restore_card_endpoint(name: str, user: str = DEFAULT_USER):
    """Restore a previously archived card back into the active collection.

    Reads the card row from card_archive.csv, converts any money strings
    (e.g. '$12.50') back to floats, strips the 'Archived Date' field, and
    appends the row to the live cards CSV.

    Args:
        name: Exact card name to restore (query param).
        user: Username whose archive and collection to update. Defaults to 'admin'.

    Returns:
        Dict with keys 'status' ('restored') and 'card_name'.

    Raises:
        HTTPException: 404 if the card is not found in the archive.
    """
    card_name = name
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
    """Background task: scrape eBay sales for one card and persist updated stats.

    Calls scrape_single_card, then writes the resulting fair price, trend,
    min/max, num_sales, and top-3 prices back to the cards CSV. Also appends
    a new entry to the price history JSON. Silently no-ops if scraping returns
    no sales data or encounters an error.

    Args:
        card_name: Exact card name string to scrape.
        paths: Dict of file paths as returned by _get_paths(), used to locate
               the CSV, results JSON, and price history JSON.
    """
    try:
        result = scrape_single_card(card_name, results_json_path=paths["results"])
        if not result:
            return
        stats = result  # scrape_single_card returns the stats dict directly
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


@router.get("/card-of-the-day")
def card_of_the_day(user: str = DEFAULT_USER):
    """Return a deterministically selected highlighted card for the current day.

    Uses an MD5 hash of today's date to pick a stable index into the list of
    cards that have a non-zero fair value, so the same card is returned for
    all requests within a calendar day.

    Args:
        user: Username whose collection to select from. Defaults to 'admin'.

    Returns:
        Dict with keys 'card' (normalised card dict or None if no priced cards
        exist) and 'date' (ISO-format date string for today).
    """
    paths = _get_paths(user)
    df = load_data(paths["csv"], paths["results"])
    with_price = df[df["Fair Value"].notna() & (df["Fair Value"].astype(float) > 0)]
    if with_price.empty:
        return {"card": None}
    today = datetime.date.today().isoformat()
    records = with_price.fillna("").to_dict(orient="records")
    idx = int(hashlib.md5(today.encode()).hexdigest(), 16) % len(records)
    return {"card": _normalise_row(records[idx]), "date": today}


@router.post("/fetch-image")
def fetch_image(name: str, user: str = DEFAULT_USER):
    """Fetch and cache front and back card images from eBay listing URLs.

    Uses a two-step strategy:
      Step 1 (URL extraction): Parses the eBay CDN image hash directly from
        stored listing URLs — no HTTP request needed.
      Step 2 (page fetch): GETs the first listing page and scans HTML for all
        eBay CDN image hashes; the second unique hash is treated as the card back.
    If the graded card has no image, falls back to the raw (ungraded) version's
    image stored in the results JSON.
    Discovered image URLs are persisted back to the results JSON for caching.

    Args:
        name: Exact card name to fetch images for (query param).
        user: Username whose results JSON to read/write. Defaults to 'admin'.

    Returns:
        Dict with keys 'image_url' (front, may be None) and 'image_url_back'
        (back, may be None).

    Raises:
        HTTPException: 404 if no results data file exists or the card has no
                       results entry.
    """
    paths = _get_paths(user)

    if not os.path.exists(paths["results"]):
        raise HTTPException(status_code=404, detail="No results data found")

    with open(paths["results"], "r", encoding="utf-8") as f:
        results = json.load(f)

    card_result = results.get(name, {})
    if not card_result:
        raise HTTPException(status_code=404, detail="Card not found in results")

    existing_front = card_result.get("image_url")
    existing_back  = card_result.get("image_url_back")

    # Already have both — return immediately
    if existing_front and existing_back:
        return {"image_url": existing_front, "image_url_back": existing_back}

    # ── Step 1: extract front image hash from URL (no HTTP needed) ──────────
    image_url = existing_front
    first_listing_url = None

    for sale in card_result.get("raw_sales", []):
        listing_url = sale.get("listing_url", "")
        if not listing_url:
            continue
        if first_listing_url is None:
            first_listing_url = listing_url
        if image_url is None:
            m = re.search(r'[?&]hash=[^:]+:g:([A-Za-z0-9_-]+)', listing_url)
            if m:
                image_url = f"https://i.ebayimg.com/images/g/{m.group(1)}/s-l400.jpg"

    # ── Step 2: fetch listing page to find back image (second gallery photo) ─
    image_url_back = existing_back
    if not image_url_back and first_listing_url:
        try:
            req = urllib.request.Request(
                first_listing_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                html = resp.read().decode("utf-8", errors="replace")

            # Collect all unique eBay CDN image hashes on the page (order-preserving)
            hashes = list(dict.fromkeys(
                re.findall(r'i\.ebayimg\.com/images/g/([A-Za-z0-9_-]+)/s-l', html)
            ))

            # First hash → front (use as fallback if URL extraction failed)
            if not image_url and hashes:
                image_url = f"https://i.ebayimg.com/images/g/{hashes[0]}/s-l400.jpg"

            # Second hash → back of the card
            if len(hashes) >= 2:
                image_url_back = f"https://i.ebayimg.com/images/g/{hashes[1]}/s-l400.jpg"
        except Exception:
            pass  # page fetch is best-effort

    # ── Step 3: graded card fallback — use raw version's image ──────────────
    # If still no image and the card has a grade (PSA/BGS/CGC/SGC/CSG),
    # look for the ungraded version of the same card in the results JSON.
    if not image_url:
        grade_re = re.compile(r'\s+(PSA|BGS|CGC|SGC|CSG)\s+\d+(?:\.\d+)?\s*$', re.IGNORECASE)
        raw_name = grade_re.sub('', name).strip()
        if raw_name and raw_name != name:
            raw_img = results.get(raw_name, {}).get("image_url")
            if raw_img:
                image_url = raw_img  # fallback — will be saved below

    # ── Step 4: eBay active listings — search + navigate listing page ────────
    # Search current eBay listings, find the first item URL, then navigate to
    # that listing page and extract both front and back image hashes.
    # Active listing images stay live for months. Runs whenever front or back
    # is missing so cards always get both images when available.
    if not image_url or not image_url_back:
        try:
            _hdrs = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            _LOT = re.compile(
                r'\blot\b|bundle|buy\s*\d|\d\s*pack|set of|\bcollection\b',
                re.IGNORECASE,
            )
            # Exclude lot/bundle listings at the eBay search level
            search_q = urllib.parse.quote(f"{name[:100]} -lot -bundle")
            search_url = f"https://www.ebay.com/sch/i.html?_nkw={search_q}&_sacat=0&LH_BIN=1"
            with urllib.request.urlopen(
                urllib.request.Request(search_url, headers=_hdrs), timeout=12
            ) as resp:
                search_html = resp.read().decode("utf-8", errors="replace")

            # Grab first listing URL that doesn't look like a lot/bundle
            # eBay embeds titles in the search HTML alongside item hrefs
            item_m = None
            for m in re.finditer(
                r'href="(https://www\.ebay\.com/itm/(\d+))[^"]*"[^>]*>([^<]*)',
                search_html,
            ):
                title_fragment = m.group(3).strip()
                if not _LOT.search(title_fragment):
                    item_m = m
                    break
            # Fallback: accept first match if every result looked like a lot
            if not item_m:
                item_m = re.search(r'href="(https://www\.ebay\.com/itm/\d+)[^"]*"', search_html)
            if item_m:
                listing_url = item_m.group(1)
                with urllib.request.urlopen(
                    urllib.request.Request(listing_url, headers=_hdrs), timeout=12
                ) as resp2:
                    listing_html = resp2.read().decode("utf-8", errors="replace")
                page_hashes = list(dict.fromkeys(
                    re.findall(r'i\.ebayimg\.com/images/g/([A-Za-z0-9_-]+)/s-l', listing_html)
                ))
                if not image_url and page_hashes:
                    image_url = f"https://i.ebayimg.com/images/g/{page_hashes[0]}/s-l400.jpg"
                if not image_url_back and len(page_hashes) >= 2:
                    image_url_back = f"https://i.ebayimg.com/images/g/{page_hashes[1]}/s-l400.jpg"
            elif not image_url:
                # Fallback: at least grab front from search thumbnails
                th = list(dict.fromkeys(
                    re.findall(r'i\.ebayimg\.com/images/g/([A-Za-z0-9_-]+)/s-l', search_html)
                ))
                if th:
                    image_url = f"https://i.ebayimg.com/images/g/{th[0]}/s-l400.jpg"
        except Exception:
            pass  # best-effort

    # ── Persist results ──────────────────────────────────────────────────────
    changed = False
    if image_url and not existing_front:
        results[name]["image_url"] = image_url
        changed = True
    if image_url_back and not existing_back:
        results[name]["image_url_back"] = image_url_back
        changed = True
    if changed:
        with open(paths["results"], "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

    return {"image_url": image_url, "image_url_back": image_url_back}


@router.post("/bulk-import")
async def bulk_import(file: UploadFile = File(...), user: str = DEFAULT_USER):
    """Import multiple cards from an uploaded CSV file.

    The CSV must contain at least a 'Card Name' column (also accepts
    'card_name', 'cardname', or 'name' as variants). Optionally reads
    'Fair Value', 'Cost Basis', 'Purchase Date', and 'Tags' columns.
    Cards already present in the collection are skipped (not duplicated).

    Args:
        file: Uploaded CSV file (multipart/form-data).
        user: Username whose collection to import into. Defaults to 'admin'.

    Returns:
        Dict with keys 'added' (int count), 'skipped' (int count), and
        'cards' (list of added card name strings).

    Raises:
        HTTPException: 400 if the file cannot be parsed as CSV or lacks a
                       recognisable card name column.
    """
    paths = _get_paths(user)
    df = load_data(paths["csv"], paths["results"])

    content = await file.read()
    try:
        import_df = pd.read_csv(io.StringIO(content.decode("utf-8")))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid CSV: {e}")

    # Normalise column name
    col_map = {c.strip().lower(): c for c in import_df.columns}
    for variant in ("card name", "card_name", "cardname", "name"):
        if variant in col_map:
            import_df = import_df.rename(columns={col_map[variant]: "Card Name"})
            break
    if "Card Name" not in import_df.columns:
        raise HTTPException(status_code=400, detail="CSV must have a 'Card Name' column")

    added, skipped = [], []
    for _, row in import_df.iterrows():
        name = str(row.get("Card Name", "")).strip()
        if not name or name.lower() == "nan":
            continue
        if name in df["Card Name"].values:
            skipped.append(name)
            continue
        new_row = {
            "Card Name":    name,
            "Fair Value":   _safe_float(row.get("Fair Value") or row.get("fair_value")),
            "Cost Basis":   _safe_float(row.get("Cost Basis") or row.get("cost_basis")),
            "Purchase Date": str(row.get("Purchase Date") or row.get("purchase_date") or ""),
            "Tags":          str(row.get("Tags") or row.get("tags") or ""),
            "Trend":         "",
            "Top 3 Prices":  "",
            "Median (All)":  0,
            "Min":           0,
            "Max":           0,
            "Num Sales":     0,
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        added.append(name)

    if added:
        save_data(df, paths["csv"])
    return {"added": len(added), "skipped": len(skipped), "cards": added}


def _safe_float(val):
    """Convert a value to float, stripping currency symbols and commas.

    Args:
        val: Value to convert — may be a number, string like '$12.50', or None.

    Returns:
        Float representation of val, or 0.0 if conversion fails.
    """
    try:
        return float(str(val).replace("$", "").replace(",", "").strip())
    except (ValueError, TypeError):
        return 0.0


@router.post("/scrape")
def scrape_card(name: str, background_tasks: BackgroundTasks, user: str = DEFAULT_USER):
    """Trigger an asynchronous eBay re-scrape for a single card.

    Validates the card exists in the collection, then schedules _do_scrape as a
    FastAPI background task. The response returns immediately while scraping
    continues in the background.

    Args:
        name: Exact card name to scrape (query param).
        background_tasks: FastAPI BackgroundTasks instance for deferred execution.
        user: Username whose collection to update. Defaults to 'admin'.

    Returns:
        Dict with keys 'status' ('queued') and 'card' (the card name).

    Raises:
        HTTPException: 404 if no card with that name exists in the collection.
    """
    card_name = name
    paths = _get_paths(user)
    df = load_data(paths["csv"], paths["results"])
    if df[df["Card Name"] == card_name].empty:
        raise HTTPException(status_code=404, detail="Card not found")
    background_tasks.add_task(_do_scrape, card_name, paths)
    return {"status": "queued", "card": card_name}
