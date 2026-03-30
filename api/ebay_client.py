"""eBay API client — inventory item + offer creation, OAuth token management.

Handles:
- Token encryption/decryption (Fernet)
- Auto-refresh of expired access tokens
- Inventory item creation (PUT /sell/inventory/v1/inventory_item/{sku})
- Offer (draft listing) creation (POST /sell/listing/v1_beta/offer)
- Seller policy fetch (fulfillment/payment/return)
"""

import os
import time
import hashlib
import requests
from datetime import datetime, timezone, timedelta
from typing import Optional

from db import get_db

# ── Config ────────────────────────────────────────────────────────────────────

EBAY_ENV         = os.environ.get("EBAY_ENVIRONMENT", "production")
EBAY_BASE_URL    = (
    "https://api.sandbox.ebay.com" if EBAY_ENV == "sandbox"
    else "https://api.ebay.com"
)
EBAY_AUTH_URL    = (
    "https://auth.sandbox.ebay.com" if EBAY_ENV == "sandbox"
    else "https://auth.ebay.com"
)

EBAY_CLIENT_ID     = os.environ.get("EBAY_CLIENT_ID", "")
EBAY_CLIENT_SECRET = os.environ.get("EBAY_CLIENT_SECRET", "")
EBAY_REDIRECT_URI  = os.environ.get("EBAY_REDIRECT_URI", "")
EBAY_RUNAME        = os.environ.get("EBAY_RUNAME", "")
EBAY_MARKETPLACE   = os.environ.get("EBAY_MARKETPLACE_ID", "EBAY_CA")

EBAY_SCOPES = " ".join([
    "https://api.ebay.com/oauth/api_scope",
    "https://api.ebay.com/oauth/api_scope/sell.inventory",
    "https://api.ebay.com/oauth/api_scope/sell.account",
    "https://api.ebay.com/oauth/api_scope/sell.listing",
])

# ── Token encryption ──────────────────────────────────────────────────────────

def _fernet():
    key = os.environ.get("EBAY_TOKEN_ENCRYPTION_KEY", "")
    if not key:
        raise RuntimeError("EBAY_TOKEN_ENCRYPTION_KEY not set")
    from cryptography.fernet import Fernet
    return Fernet(key.encode() if isinstance(key, str) else key)

def _encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()

def _decrypt(value: str) -> str:
    return _fernet().decrypt(value.encode()).decode()

# ── Condition mapping ─────────────────────────────────────────────────────────

CONDITION_MAP = {
    "PSA 10": "2750", "PSA 9": "2750", "PSA 8": "2750", "PSA 7": "2750",
    "BGS 10": "2750", "BGS 9.5": "2750", "BGS 9": "2750", "BGS 8.5": "2750",
    "SGC 10": "2750", "SGC 9": "2750", "SGC 8": "2750",
    "Raw":    "3000",
    "":       "3000",
}

CONDITION_LABELS = {
    "2750": "Graded",
    "3000": "Very Good",
    "4000": "Good",
    "5000": "Acceptable",
}

SPORT_LABELS = {
    "NHL": "Hockey", "NBA": "Basketball",
    "NFL": "Football", "MLB": "Baseball",
}

# ── Token management ──────────────────────────────────────────────────────────

def store_tokens(user_id: str, access_token: str, refresh_token: str,
                 expires_in: int, scope: str = ""):
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in - 60)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ebay_tokens
                    (user_id, access_token, refresh_token, expires_at, scope, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                    access_token = EXCLUDED.access_token,
                    refresh_token = EXCLUDED.refresh_token,
                    expires_at = EXCLUDED.expires_at,
                    scope = EXCLUDED.scope,
                    updated_at = NOW()
            """, (
                user_id,
                _encrypt(access_token),
                _encrypt(refresh_token),
                expires_at,
                scope,
            ))
        conn.commit()


def get_token_row(user_id: str) -> Optional[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT access_token, refresh_token, expires_at, scope
                FROM ebay_tokens WHERE user_id = %s
            """, (user_id,))
            row = cur.fetchone()
    if not row:
        return None
    return {
        "access_token":  row[0],
        "refresh_token": row[1],
        "expires_at":    row[2],
        "scope":         row[3],
    }


def delete_tokens(user_id: str):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM ebay_tokens WHERE user_id = %s", (user_id,))
        conn.commit()


def _refresh_access_token(user_id: str, encrypted_refresh: str) -> str:
    """Exchange refresh token for a new access token. Returns new access token."""
    import base64
    creds = base64.b64encode(f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}".encode()).decode()
    resp = requests.post(
        f"{EBAY_AUTH_URL}/identity/v1/oauth2/token",
        headers={
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type":    "refresh_token",
            "refresh_token": _decrypt(encrypted_refresh),
            "scope":         EBAY_SCOPES,
        },
        timeout=15,
    )
    if resp.status_code != 200:
        raise EbayAuthError(f"Token refresh failed: {resp.text}")
    data = resp.json()
    store_tokens(
        user_id,
        data["access_token"],
        _decrypt(encrypted_refresh),   # reuse existing refresh token
        data["expires_in"],
        data.get("scope", ""),
    )
    return data["access_token"]


def get_valid_access_token(user_id: str) -> str:
    """Return a valid access token, refreshing if needed."""
    row = get_token_row(user_id)
    if not row:
        raise EbayAuthError("No eBay token found — user must reconnect")

    expires_at = row["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if datetime.now(timezone.utc) < expires_at - timedelta(minutes=5):
        return _decrypt(row["access_token"])

    # Refresh needed
    return _refresh_access_token(user_id, row["refresh_token"])


# ── Errors ────────────────────────────────────────────────────────────────────

class EbayAuthError(Exception):
    pass

class EbayAPIError(Exception):
    def __init__(self, message: str, status_code: int = 0, raw: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.raw = raw


def _check_ebay_response(resp: requests.Response):
    if resp.status_code in (200, 201, 204):
        return
    try:
        data = resp.json()
        errors = data.get("errors", [])
        msg = errors[0]["message"] if errors else resp.text
    except Exception:
        msg = resp.text
    raise EbayAPIError(msg, resp.status_code, resp.text)


# ── Title builder ─────────────────────────────────────────────────────────────

def build_ebay_title(year: str, brand: str, set_name: str, card_number: str,
                     player_name: str, variant: str, grade: str,
                     serial_number: str, sport: str) -> str:
    parts = []
    if year:       parts.append(str(year))
    if brand:      parts.append(brand)
    if set_name and set_name != brand:
        parts.append(set_name)
    if variant:    parts.append(variant)
    if card_number: parts.append(f"#{card_number}")
    if player_name: parts.append(player_name)
    if grade:      parts.append(grade)
    if serial_number and "/" in str(serial_number):
        parts.append(f"/{serial_number.split('/')[-1]}")
    sport_word = SPORT_LABELS.get(sport, "Sports")
    parts.append(f"{sport_word} Card")
    return " ".join(parts)[:80]


def build_description(player_name: str, year: str, brand: str, set_name: str,
                      card_number: str, variant: str, grade: str) -> str:
    lines = [
        f"{year} {brand} {set_name}".strip(),
    ]
    if card_number:
        lines.append(f"Card #{card_number}")
    if player_name:
        lines.append(f"Player: {player_name}")
    if variant:
        lines.append(f"Variant: {variant}")
    if grade:
        lines.append(f"Grade: {grade}")
    lines.append("")
    lines.append("Please see photos for exact condition. Ships in a top loader with team bag.")
    return "\n".join(lines)


# ── eBay API calls ────────────────────────────────────────────────────────────

def generate_sku(card_name: str) -> str:
    h = hashlib.md5(card_name.encode()).hexdigest()[:8]
    return f"carddb-{h}-{int(time.time())}"


def create_inventory_item(access_token: str, sku: str, payload: dict):
    """PUT /sell/inventory/v1/inventory_item/{sku}"""
    url = f"{EBAY_BASE_URL}/sell/inventory/v1/inventory_item/{sku}"
    resp = requests.put(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type":  "application/json",
            "Content-Language": "en-US",
        },
        json=payload,
        timeout=20,
    )
    _check_ebay_response(resp)


def create_offer(access_token: str, payload: dict) -> dict:
    """POST /sell/listing/v1_beta/offer — returns {offerId, status}"""
    url = f"{EBAY_BASE_URL}/sell/listing/v1_beta/offer"
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type":  "application/json",
            "Content-Language": "en-US",
        },
        json=payload,
        timeout=20,
    )
    _check_ebay_response(resp)
    return resp.json()


def fetch_seller_policies(access_token: str) -> dict:
    """Fetch fulfillment, payment, return policy IDs from seller's account."""
    headers = {"Authorization": f"Bearer {access_token}"}
    policies = {}

    for policy_type in ("fulfillment_policy", "return_policy", "payment_policy"):
        url = f"{EBAY_BASE_URL}/sell/account/v1/{policy_type}?marketplace_id={EBAY_MARKETPLACE}"
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            key = f"{policy_type.split('_')[0]}Policies"
            items = data.get(key, [])
            if items:
                policies[policy_type] = items[0][f"{policy_type.split('_')[0]}PolicyId"]

    return policies


def get_or_create_merchant_location(access_token: str) -> Optional[str]:
    """Return the first merchant location key, or None if not set up."""
    url = f"{EBAY_BASE_URL}/sell/inventory/v1/location"
    resp = requests.get(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    if resp.status_code == 200:
        locations = resp.json().get("locations", [])
        if locations:
            return locations[0]["merchantLocationKey"]
    return None


def build_draft(user_id: str, card: dict) -> dict:
    """Main entry point — creates inventory item + offer. Returns offer details."""
    access_token = get_valid_access_token(user_id)
    sku = generate_sku(card["card_name"])

    grade       = card.get("grade", "") or ""
    sport       = card.get("sport", "") or ""
    condition_id = CONDITION_MAP.get(grade, "3000")

    title = build_ebay_title(
        year=str(card.get("year", "")),
        brand=card.get("brand", ""),
        set_name=card.get("set_name", ""),
        card_number=card.get("card_number", ""),
        player_name=card.get("player_name", ""),
        variant=card.get("variant", ""),
        grade=grade,
        serial_number=card.get("serial_number", ""),
        sport=sport,
    )

    description = card.get("description") or build_description(
        player_name=card.get("player_name", ""),
        year=str(card.get("year", "")),
        brand=card.get("brand", ""),
        set_name=card.get("set_name", ""),
        card_number=card.get("card_number", ""),
        variant=card.get("variant", ""),
        grade=grade,
    )

    # Build inventory item payload
    aspects = {}
    if sport:            aspects["Sport"]            = [SPORT_LABELS.get(sport, sport)]
    if card.get("player_name"): aspects["Player/Athlete"] = [card["player_name"]]
    if card.get("year"):        aspects["Season"]          = [str(card["year"])]
    if card.get("set_name"):    aspects["Set"]             = [card["set_name"]]
    if card.get("variant"):     aspects["Parallel/Variety"]= [card["variant"]]
    if card.get("card_number"): aspects["Card Number"]     = [card["card_number"]]
    if grade:                   aspects["Grade"]           = [grade]
    if card.get("brand"):       aspects["Manufacturer"]    = [card["brand"]]
    aspects["Type"] = ["Sports Trading Card"]

    inv_payload = {
        "product": {
            "title":       title,
            "description": description,
            "aspects":     aspects,
        },
        "condition": condition_id,
        "conditionDescription": "See photos for exact condition.",
        "availability": {
            "shipToLocationAvailability": {"quantity": 1}
        },
    }
    image_url = card.get("image_url", "")
    if image_url:
        inv_payload["product"]["imageUrls"] = [image_url]

    create_inventory_item(access_token, sku, inv_payload)

    # Fetch seller policies dynamically
    env_fulfillment = os.environ.get("EBAY_FULFILLMENT_POLICY_ID")
    env_payment     = os.environ.get("EBAY_PAYMENT_POLICY_ID")
    env_return      = os.environ.get("EBAY_RETURN_POLICY_ID")
    env_location    = os.environ.get("EBAY_MERCHANT_LOCATION_KEY")

    if not all([env_fulfillment, env_payment, env_return, env_location]):
        fetched = fetch_seller_policies(access_token)
        env_fulfillment = env_fulfillment or fetched.get("fulfillment_policy")
        env_payment     = env_payment     or fetched.get("payment_policy")
        env_return      = env_return      or fetched.get("return_policy")
        env_location    = env_location    or get_or_create_merchant_location(access_token)

    listing_format = card.get("listing_format", "AUCTION")  # AUCTION or FIXED_PRICE
    price          = float(card.get("price", 0.99))
    auction_days   = int(card.get("auction_days", 7))
    currency       = "CAD" if EBAY_MARKETPLACE == "EBAY_CA" else "USD"

    if listing_format == "AUCTION":
        pricing = {"auctionStartPrice": {"value": f"{price:.2f}", "currency": currency}}
        duration = f"DAYS_{auction_days}"
    else:
        pricing  = {"price": {"value": f"{price:.2f}", "currency": currency}}
        duration = "GTC"  # Good Till Cancelled — standard for fixed price

    offer_payload = {
        "sku":                sku,
        "marketplaceId":      EBAY_MARKETPLACE,
        "format":             listing_format,
        "availableQuantity":  1,
        "categoryId":         "261328",
        "listingDescription": description,
        "pricingSummary":     pricing,
        "listingDuration":    duration,
    }

    listing_policies = {}
    if env_fulfillment: listing_policies["fulfillmentPolicyId"] = env_fulfillment
    if env_payment:     listing_policies["paymentPolicyId"]     = env_payment
    if env_return:      listing_policies["returnPolicyId"]      = env_return
    if listing_policies:
        offer_payload["listingPolicies"] = listing_policies
    if env_location:
        offer_payload["merchantLocationKey"] = env_location

    result = create_offer(access_token, offer_payload)
    offer_id = result.get("offerId", "")

    marketplace_domain = "ebay.ca" if EBAY_MARKETPLACE == "EBAY_CA" else "ebay.com"
    draft_url = f"https://www.{marketplace_domain}/sh/lst/active"

    # Persist draft record
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ebay_drafts
                    (user_id, sku, offer_id, card_name, listing_price, status, ebay_draft_url)
                VALUES (%s, %s, %s, %s, %s, 'draft', %s)
            """, (user_id, sku, offer_id, card["card_name"], starting_bid, draft_url))
        conn.commit()

    return {"offer_id": offer_id, "sku": sku, "draft_url": draft_url}
