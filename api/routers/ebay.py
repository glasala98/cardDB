"""eBay integration endpoints — OAuth flow, prefill, draft listing creation."""

import os
import base64
import datetime
import jwt
import requests
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import Optional

from api.routers.auth import get_current_user, JWT_SECRET, JWT_ALGORITHM
from fastapi import Security


def require_admin(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(403, detail="Admin access required")
    return current_user
from api.ebay_client import (
    EBAY_AUTH_URL, EBAY_BASE_URL, EBAY_CLIENT_ID, EBAY_CLIENT_SECRET,
    EBAY_REDIRECT_URI, EBAY_RUNAME, EBAY_SCOPES, EBAY_MARKETPLACE,
    CONDITION_MAP, CONDITION_LABELS,
    store_tokens, get_token_row, delete_tokens, get_valid_access_token,
    build_draft, build_ebay_title, build_description,
    EbayAuthError, EbayAPIError,
)
from db import get_db

router = APIRouter()

_OAUTH_STATE_EXPIRY_MIN = 10


def _make_state_token(username: str) -> str:
    payload = {
        "sub": username,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=_OAUTH_STATE_EXPIRY_MIN),
        "purpose": "ebay_oauth",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_state_token(state: str) -> Optional[str]:
    try:
        payload = jwt.decode(state, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("purpose") != "ebay_oauth":
            return None
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/status")
def ebay_status(current_user: dict = Depends(require_admin)):
    row = get_token_row(current_user["username"])
    if not row:
        return {"connected": False, "expires_at": None}
    from datetime import timezone
    expires_at = row["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    now = datetime.datetime.now(timezone.utc)
    if now >= expires_at:
        return {"connected": False, "expires_at": None}
    return {"connected": True, "expires_at": expires_at.isoformat()}


# ── OAuth connect ─────────────────────────────────────────────────────────────

@router.get("/connect")
def ebay_connect(current_user: dict = Depends(require_admin)):
    """Redirect user to eBay OAuth consent page."""
    if not EBAY_CLIENT_ID or not EBAY_RUNAME:
        raise HTTPException(503, "eBay credentials not configured")

    state = _make_state_token(current_user["username"])
    params = "&".join([
        f"client_id={EBAY_CLIENT_ID}",
        f"redirect_uri={EBAY_RUNAME}",
        "response_type=code",
        f"scope={requests.utils.quote(EBAY_SCOPES)}",
        f"state={state}",
    ])
    url = f"{EBAY_AUTH_URL}/oauth2/authorize?{params}"
    return RedirectResponse(url)


# ── OAuth callback ────────────────────────────────────────────────────────────

@router.get("/callback")
def ebay_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
):
    """eBay redirects here after user grants/denies access."""
    if error:
        return RedirectResponse(f"/ebay-error?msg={requests.utils.quote(error_description or error)}")

    username = _decode_state_token(state or "")
    if not username:
        return RedirectResponse("/ebay-error?msg=Invalid+or+expired+state")

    if not code:
        return RedirectResponse("/ebay-error?msg=No+authorization+code")

    creds = base64.b64encode(f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}".encode()).decode()
    resp = requests.post(
        f"{EBAY_AUTH_URL}/identity/v1/oauth2/token",
        headers={
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type":   "authorization_code",
            "code":         code,
            "redirect_uri": EBAY_RUNAME,
        },
        timeout=15,
    )

    if resp.status_code != 200:
        return RedirectResponse(f"/ebay-error?msg=Token+exchange+failed")

    data = resp.json()
    store_tokens(
        username,
        data["access_token"],
        data["refresh_token"],
        data["expires_in"],
        data.get("scope", ""),
    )
    return RedirectResponse("/ebay-connected")


# ── Prefill ───────────────────────────────────────────────────────────────────

@router.get("/prefill")
def ebay_prefill(
    card_name: str = Query(...),
    current_user: dict = Depends(require_admin),
):
    """Return suggested title, price, condition for the draft listing form."""
    # Look up card details + fair_value
    card_data = {}
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT cc.player_name, cc.year, cc.brand, cc.set_name,
                       cc.card_number, cc.variant, cc.sport,
                       mp.fair_value, cc.is_rookie
                FROM cards c
                JOIN card_catalog cc ON cc.id = c.card_catalog_id
                LEFT JOIN market_prices mp ON mp.card_catalog_id = cc.id
                WHERE c.card_name = %s AND c.user_id = %s
                LIMIT 1
            """, (card_name, current_user["username"]))
            row = cur.fetchone()

    if row:
        card_data = {
            "player_name": row[0], "year": row[1], "brand": row[2],
            "set_name": row[3], "card_number": row[4], "variant": row[5],
            "sport": row[6], "fair_value": float(row[7]) if row[7] else None,
            "is_rookie": bool(row[8]),
        }

    grade = ""
    condition_id = CONDITION_MAP.get(grade, "3000")

    title = build_ebay_title(
        year=str(card_data.get("year", "")),
        brand=card_data.get("brand", ""),
        set_name=card_data.get("set_name", ""),
        card_number=card_data.get("card_number", ""),
        player_name=card_data.get("player_name", ""),
        variant=card_data.get("variant", ""),
        grade=grade,
        serial_number="",
        sport=card_data.get("sport", ""),
        is_rookie=card_data.get("is_rookie", False),
    )

    description = build_description(
        player_name=card_data.get("player_name", ""),
        year=str(card_data.get("year", "")),
        brand=card_data.get("brand", ""),
        set_name=card_data.get("set_name", ""),
        card_number=card_data.get("card_number", ""),
        variant=card_data.get("variant", ""),
        grade=grade,
    )

    return {
        "suggested_title":   title,
        "suggested_price":   card_data.get("fair_value"),
        "condition_id":      condition_id,
        "condition_label":   CONDITION_LABELS.get(condition_id, "Very Good"),
        "description":       description,
        "sport":             card_data.get("sport", ""),
        "is_rookie":         card_data.get("is_rookie", False),
        "category_id":       "261328",
    }


# ── Create draft ──────────────────────────────────────────────────────────────

class DraftRequest(BaseModel):
    card_name:      str
    player_name:    Optional[str] = ""
    year:           Optional[str] = ""
    brand:          Optional[str] = ""
    set_name:       Optional[str] = ""
    card_number:    Optional[str] = ""
    variant:        Optional[str] = ""
    grade:          Optional[str] = ""
    serial_number:  Optional[str] = ""
    sport:          Optional[str] = ""
    price:          float = 0.99
    listing_format: Optional[str] = "AUCTION"   # AUCTION or FIXED_PRICE
    auction_days:   Optional[int] = 7
    condition_id:   Optional[str] = "3000"
    description:    Optional[str] = ""
    image_url:      Optional[str] = ""
    image_url_back: Optional[str] = ""
    is_rookie:      Optional[bool] = False


@router.post("/create-draft")
def create_draft(
    req: DraftRequest,
    current_user: dict = Depends(require_admin),
):
    user_id = current_user["username"]

    row = get_token_row(user_id)
    if not row:
        raise HTTPException(401, detail="eBay account not connected")

    card = req.dict()
    card["user_id"] = user_id

    try:
        result = build_draft(user_id, card)
    except EbayAuthError as e:
        raise HTTPException(401, detail=str(e))
    except EbayAPIError as e:
        raise HTTPException(502, detail=f"eBay API error: {e}")
    except Exception as e:
        raise HTTPException(500, detail=str(e))

    return {
        "success":   True,
        "offer_id":  result["offer_id"],
        "sku":       result["sku"],
        "draft_url": result["draft_url"],
        "message":   "Draft listing created. Review and publish on eBay.",
    }


# ── List drafts ───────────────────────────────────────────────────────────────

@router.get("/drafts")
def list_drafts(current_user: dict = Depends(require_admin)):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, card_name, listing_price, status,
                       offer_id, ebay_draft_url, created_at
                FROM ebay_drafts
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT 50
            """, (current_user["username"],))
            rows = cur.fetchall()
    return {"drafts": [
        {
            "id": r[0], "card_name": r[1], "listing_price": float(r[2]),
            "status": r[3], "offer_id": r[4], "ebay_draft_url": r[5],
            "created_at": r[6].isoformat(),
        }
        for r in rows
    ]}


# ── Disconnect ────────────────────────────────────────────────────────────────

@router.post("/disconnect")
def ebay_disconnect(current_user: dict = Depends(require_admin)):
    delete_tokens(current_user["username"])
    return {"status": "disconnected"}
