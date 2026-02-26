"""Card scanning endpoint — uses Claude Vision to identify cards from images."""

import os
import base64
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException

router = APIRouter()

ALLOWED_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
MAX_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB


def _encode_image(data: bytes, content_type: str) -> tuple[str, str]:
    """Return (base64_data, media_type) ready for the Anthropic API."""
    # Normalize content type
    media_type = content_type if content_type in ("image/jpeg", "image/png", "image/webp", "image/gif") else "image/jpeg"
    return base64.standard_b64encode(data).decode("utf-8"), media_type


@router.post("/analyze")
async def analyze_card(
    front: UploadFile = File(...),
    back:  Optional[UploadFile] = File(default=None),
):
    """
    Accept one or two card images and return extracted card details via Claude Vision.

    Returns:
        player_name, card_number, card_set, year, subset, raw_text
    """
    try:
        import anthropic
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Anthropic SDK not installed. Run: pip install anthropic"
        )

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY environment variable not set"
        )

    # Validate and read files
    if front.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {front.content_type}")

    front_data = await front.read()
    if len(front_data) > MAX_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="Front image too large (max 20MB)")

    front_b64, front_type = _encode_image(front_data, front.content_type)

    # Build message content
    content = []

    content.append({
        "type": "image",
        "source": {"type": "base64", "media_type": front_type, "data": front_b64},
    })

    if back:
        back_data = await back.read()
        if len(back_data) > MAX_SIZE_BYTES:
            raise HTTPException(status_code=400, detail="Back image too large (max 20MB)")
        back_b64, back_type = _encode_image(back_data, back.content_type or "image/jpeg")
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": back_type, "data": back_b64},
        })

    content.append({
        "type": "text",
        "text": (
            "This is a hockey trading card. Please extract the following details:\n"
            "1. Player Name (full name)\n"
            "2. Card Number (e.g. 201, RC-15, etc.)\n"
            "3. Card Set / Series (e.g. 'Upper Deck Series 1 Young Guns', 'Upper Deck AHL', etc.)\n"
            "4. Season / Year (e.g. '2024-25', '2023-24')\n"
            "5. Subset / Variant (e.g. 'Young Guns', 'Canvas', 'French', 'SP', or blank if base)\n"
            "6. Team\n\n"
            "Respond ONLY in this exact JSON format (no markdown, no extra text):\n"
            '{"player_name":"","card_number":"","card_set":"","year":"","subset":"","team":""}'
        ),
    })

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[{"role": "user", "content": content}],
    )

    raw_text = message.content[0].text.strip()

    # Parse JSON response
    import json, re
    try:
        # Strip markdown code fences if model added them
        clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw_text).strip()
        result = json.loads(clean)
    except json.JSONDecodeError:
        # Return raw text so the frontend can show it and let user fill manually
        return {
            "player_name": "",
            "card_number": "",
            "card_set":    "",
            "year":        "",
            "subset":      "",
            "team":        "",
            "raw_text":    raw_text,
            "parse_error": True,
        }

    return {
        "player_name": result.get("player_name", ""),
        "card_number": result.get("card_number", ""),
        "card_set":    result.get("card_set", ""),
        "year":        result.get("year", ""),
        "subset":      result.get("subset", ""),
        "team":        result.get("team", ""),
        "raw_text":    raw_text,
        "parse_error": False,
    }
