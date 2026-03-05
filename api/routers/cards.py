"""Card ledger endpoints — personal collection CRUD."""

import io
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
    load_price_history, load_all_price_history, append_price_history,
    load_card_results, load_all_card_results, save_card_results,
    scrape_single_card, MONEY_COLS,
)

router = APIRouter()

DEFAULT_USER = "admin"


def _normalise_row(r: dict) -> dict:
    """Convert a DataFrame row dict to the canonical API card shape."""
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
    """Return all cards in the collection for the ledger table."""
    df = load_data(user)
    return {"cards": [_normalise_row(r) for r in df.fillna("").to_dict(orient="records")]}


@router.get("/portfolio-history")
def portfolio_history(user: str = DEFAULT_USER):
    """Return time-series portfolio value recalculated from per-card price history.

    Dynamically sums fair values from card_price_history for each date, using
    only cards currently in the collection. Archived cards are excluded so a
    card added then removed within a day won't cause a spike. Today's live
    values are always appended as the final data point.
    """
    df = load_data(user)
    current_cards = set(df["Card Name"].tolist())

    price_hist = load_all_price_history(user)

    date_totals: dict = {}
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

    # Always include today's live values as the rightmost point
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
    """Return all soft-deleted (archived) cards."""
    try:
        archive_df = load_archive(user)
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
    """Return full detail for a single card including price history and raw sales."""
    card_name = name
    df = load_data(user)

    match = df[df["Card Name"] == card_name]
    if match.empty:
        raise HTTPException(status_code=404, detail="Card not found")

    card = _normalise_row(match.iloc[0].fillna("").to_dict())

    # Price history — deduplicated by date (keep latest value per date)
    entries = load_price_history(user, card_name)
    seen_dates = {}
    for e in entries:
        d = e.get("date", "")
        if d and e.get("fair_value"):
            seen_dates[d] = e["fair_value"]
    price_history = [{"date": d, "price": p} for d, p in sorted(seen_dates.items())]

    # Raw sales + metadata from card_results
    card_result = load_card_results(user, card_name)
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
        for s in (card_result.get("raw_sales") or [])
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
    """Add a new card to the collection."""
    df = load_data(user)

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
    save_data(df, user)
    return {"status": "ok", "card_name": body.card_name}


@router.patch("/update")
def update_card(name: str, body: CardUpdate, user: str = DEFAULT_USER):
    """Update editable fields on a card."""
    card_name = name
    df = load_data(user)

    match = df[df["Card Name"] == card_name]
    if match.empty:
        raise HTTPException(status_code=404, detail="Card not found")

    i = match.index[0]
    if body.fair_value    is not None: df.at[i, "Fair Value"]    = body.fair_value
    if body.cost_basis    is not None: df.at[i, "Cost Basis"]    = body.cost_basis
    if body.purchase_date is not None: df.at[i, "Purchase Date"] = body.purchase_date
    if body.tags          is not None: df.at[i, "Tags"]          = body.tags

    save_data(df, user)
    return {"status": "ok"}


@router.delete("/archive")
def archive_card_endpoint(name: str, user: str = DEFAULT_USER):
    """Archive (soft-delete) a card, moving it out of the active collection."""
    card_name = name
    df = load_data(user)

    if df[df["Card Name"] == card_name].empty:
        raise HTTPException(status_code=404, detail="Card not found")

    archive_card(df, user, card_name)
    return {"status": "archived"}


@router.post("/restore")
def restore_card_endpoint(name: str, user: str = DEFAULT_USER):
    """Restore a previously archived card back into the active collection."""
    card_name = name
    card_data = restore_card(user, card_name)
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

    df = load_data(user)
    df = pd.concat([df, pd.DataFrame([card_data])], ignore_index=True)
    save_data(df, user)
    return {"status": "restored", "card_name": card_name}


# ── Scrape endpoint ───────────────────────────────────────────────────────────

def _do_scrape(card_name: str, user: str):
    """Background task: scrape eBay sales for one card and persist updated stats."""
    try:
        result = scrape_single_card(card_name, user)
        if not result:
            return
        stats = result
        df = load_data(user)
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
                user, card_name,
                stats.get("fair_price", 0),
                stats.get("num_sales", 0),
            )
        save_data(df, user)
        print(f"[scrape] Done: {card_name} → ${stats.get('fair_price', 0):.2f}")
    except Exception as e:
        print(f"[scrape] Error for {card_name}: {e}")


@router.get("/card-of-the-day")
def card_of_the_day(user: str = DEFAULT_USER):
    """Return a deterministically selected highlighted card for the current day."""
    df = load_data(user)
    with_price = df[df["Fair Value"].notna() & (df["Fair Value"].astype(float) > 0)]
    if with_price.empty:
        return {"card": None}
    today = datetime.date.today().isoformat()
    records = with_price.fillna("").to_dict(orient="records")
    idx = int(hashlib.md5(today.encode()).hexdigest(), 16) % len(records)
    return {"card": _normalise_row(records[idx]), "date": today}


@router.post("/fetch-image")
def fetch_image(name: str, user: str = DEFAULT_USER):
    """Fetch and cache front and back card images from eBay listing URLs."""
    card_result = load_card_results(user, name)
    if not card_result and not card_result.get("raw_sales"):
        # Try loading df to confirm card exists
        df = load_data(user)
        if df[df["Card Name"] == name].empty:
            raise HTTPException(status_code=404, detail="Card not found in results")

    existing_front = card_result.get("image_url")
    existing_back  = card_result.get("image_url_back")

    # Already have both — return immediately
    if existing_front and existing_back:
        return {"image_url": existing_front, "image_url_back": existing_back}

    # ── Step 1: extract front image hash from URL (no HTTP needed) ──────────
    image_url = existing_front
    first_listing_url = None

    for sale in (card_result.get("raw_sales") or []):
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

            hashes = list(dict.fromkeys(
                re.findall(r'i\.ebayimg\.com/images/g/([A-Za-z0-9_-]+)/s-l', html)
            ))

            if not image_url and hashes:
                image_url = f"https://i.ebayimg.com/images/g/{hashes[0]}/s-l400.jpg"

            if len(hashes) >= 2:
                image_url_back = f"https://i.ebayimg.com/images/g/{hashes[1]}/s-l400.jpg"
        except Exception:
            pass  # page fetch is best-effort

    # ── Step 3: graded card fallback — use raw version's image ──────────────
    if not image_url:
        grade_re = re.compile(r'\s+(PSA|BGS|CGC|SGC|CSG)\s+\d+(?:\.\d+)?\s*$', re.IGNORECASE)
        raw_name = grade_re.sub('', name).strip()
        if raw_name and raw_name != name:
            raw_result = load_card_results(user, raw_name)
            raw_img = raw_result.get("image_url")
            if raw_img:
                image_url = raw_img

    # ── Step 4: eBay active listings — search + navigate listing page ────────
    if not image_url or not image_url_back:
        try:
            _hdrs = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            _LOT = re.compile(
                r'\blot\b|bundle|buy\s*\d|\d\s*pack|set of|\bcollection\b',
                re.IGNORECASE,
            )
            search_q = urllib.parse.quote(f"{name[:100]} -lot -bundle")
            search_url_fetch = f"https://www.ebay.com/sch/i.html?_nkw={search_q}&_sacat=0&LH_BIN=1"
            with urllib.request.urlopen(
                urllib.request.Request(search_url_fetch, headers=_hdrs), timeout=12
            ) as resp:
                search_html = resp.read().decode("utf-8", errors="replace")

            item_m = None
            for m in re.finditer(
                r'href="(https://www\.ebay\.com/itm/(\d+))[^"]*"[^>]*>([^<]*)',
                search_html,
            ):
                title_fragment = m.group(3).strip()
                if not _LOT.search(title_fragment):
                    item_m = m
                    break
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
                th = list(dict.fromkeys(
                    re.findall(r'i\.ebayimg\.com/images/g/([A-Za-z0-9_-]+)/s-l', search_html)
                ))
                if th:
                    image_url = f"https://i.ebayimg.com/images/g/{th[0]}/s-l400.jpg"
        except Exception:
            pass  # best-effort

    # ── Persist results ──────────────────────────────────────────────────────
    if (image_url and not existing_front) or (image_url_back and not existing_back):
        save_card_results(
            user, name,
            raw_sales=card_result.get("raw_sales") or [],
            scraped_at=card_result.get("scraped_at") or "",
            confidence=card_result.get("confidence") or "",
            image_url=image_url or "",
            image_hash=card_result.get("image_hash") or "",
            image_url_back=image_url_back or "",
            search_url=card_result.get("search_url") or "",
            is_estimated=bool(card_result.get("is_estimated", False)),
            price_source=card_result.get("price_source") or "direct",
        )

    return {"image_url": image_url, "image_url_back": image_url_back}


@router.post("/bulk-import")
async def bulk_import(file: UploadFile = File(...), user: str = DEFAULT_USER):
    """Import multiple cards from an uploaded CSV file."""
    df = load_data(user)

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
        save_data(df, user)
    return {"added": len(added), "skipped": len(skipped), "cards": added}


def _safe_float(val):
    try:
        return float(str(val).replace("$", "").replace(",", "").strip())
    except (ValueError, TypeError):
        return 0.0


@router.post("/scrape")
def scrape_card(name: str, background_tasks: BackgroundTasks, user: str = DEFAULT_USER):
    """Trigger an asynchronous eBay re-scrape for a single card."""
    card_name = name
    df = load_data(user)
    if df[df["Card Name"] == card_name].empty:
        raise HTTPException(status_code=404, detail="Card not found")
    background_tasks.add_task(_do_scrape, card_name, user)
    return {"status": "queued", "card": card_name}
