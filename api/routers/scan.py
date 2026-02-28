"""Card scanning endpoint — uses Claude Vision to identify cards from images."""

import os
import base64
import json
import re
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException

router = APIRouter()

ALLOWED_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
MAX_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB


def _detect_media_type(image_bytes: bytes) -> str:
    """Detect image media type by inspecting the file's magic bytes.

    Supports PNG (8-byte signature), JPEG (0xFF 0xD8 prefix), and WebP
    (RIFF....WEBP). Falls back to 'image/jpeg' for any unrecognised format.

    Args:
        image_bytes: Raw binary content of the image file.

    Returns:
        MIME type string: 'image/png', 'image/jpeg', or 'image/webp'.
    """
    if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    if image_bytes[:2] == b'\xff\xd8':
        return "image/jpeg"
    if image_bytes[:4] == b'RIFF' and image_bytes[8:12] == b'WEBP':
        return "image/webp"
    return "image/jpeg"


@router.post("/analyze")
async def analyze_card(
    front: UploadFile = File(...),
    back:  Optional[UploadFile] = File(default=None),
):
    """Identify a sports card from uploaded images using Claude Vision.

    Accepts a mandatory front image and an optional back image (multipart
    form-data). Both images are base64-encoded and sent to the Claude
    claude-sonnet-4-6 model with a structured prompt requesting JSON output.
    The raw model response is parsed and validated; on parse failure the
    raw text is returned with 'parse_error' set to True.

    Each image must be JPEG, PNG, or WebP and no larger than 20 MB.

    Args:
        front: Mandatory front-face image of the card (JPEG/PNG/WebP, max 20 MB).
        back: Optional back-face image of the card (JPEG/PNG/WebP, max 20 MB).

    Returns:
        Dict with keys: 'player_name', 'card_number', 'brand', 'subset',
        'parallel', 'serial_number', 'year', 'grade', 'confidence'
        (high|medium|low), 'is_sports_card' (bool), 'validation_reason',
        'raw_text' (raw model output), and 'parse_error' (bool).

    Raises:
        HTTPException: 400 if the front image type is not in ALLOWED_TYPES or
                       either image exceeds MAX_SIZE_BYTES.
        HTTPException: 503 if the anthropic package is not installed or
                       ANTHROPIC_API_KEY is not set in the environment.
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

    if front.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {front.content_type}")

    front_data = await front.read()
    if len(front_data) > MAX_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="Front image too large (max 20MB)")

    front_b64  = base64.standard_b64encode(front_data).decode("utf-8")
    front_type = _detect_media_type(front_data)

    # Build content — label front and back clearly so the model uses both
    content = [
        {"type": "text", "text": "FRONT OF CARD:"},
        {"type": "image", "source": {"type": "base64", "media_type": front_type, "data": front_b64}},
    ]

    if back:
        back_data = await back.read()
        if len(back_data) > MAX_SIZE_BYTES:
            raise HTTPException(status_code=400, detail="Back image too large (max 20MB)")
        back_b64  = base64.standard_b64encode(back_data).decode("utf-8")
        back_type = _detect_media_type(back_data)
        content.append({"type": "text", "text": "BACK OF CARD:"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": back_type, "data": back_b64}})

    content.append({
        "type": "text",
        "text": (
            "Analyze this hockey/sports card and extract the following details.\n"
            "Look at BOTH the front and back of the card carefully.\n\n"
            "The back typically has: card number, set name, year, manufacturer, serial number.\n"
            "The front typically has: player name, team, photo, parallel color/foil name.\n\n"
            "Return ONLY valid JSON with these exact keys:\n"
            "{\n"
            '    "player_name": "Full player name as printed on the card",\n'
            '    "card_number": "Card number only, no # symbol (e.g. 201, RC-15)",\n'
            '    "brand": "Base set brand WITHOUT subset, use short common names '
            '(e.g. \\"Upper Deck Series 1\\", \\"O-Pee-Chee Platinum\\", \\"Topps Chrome\\", '
            '\\"SP Authentic\\", \\"Parkhurst\\")",\n'
            '    "subset": "Named product line within the set if any '
            '(e.g. \\"Young Guns\\", \\"Marquee Rookies\\", \\"Future Watch\\"). '
            'Empty string for true base set cards.",\n'
            '    "parallel": "Parallel or foil variant name if any '
            '(e.g. \\"Red Prism\\", \\"Gold\\", \\"Rainbow Foil\\", \\"Arctic Freeze\\"). '
            'Empty string if this is the base (non-parallel) version.",\n'
            '    "year": "Card year or season (e.g. \\"2023-24\\" or \\"2015\\")",\n'
            '    "serial_number": "Print run if the card is serial-numbered '
            '(e.g. \\"70/99\\", \\"1/250\\", \\"5/10\\"). '
            'Empty string if not numbered. Check back of card carefully.",\n'
            '    "grade": "Grade if card is in a graded slab '
            '(e.g. \\"PSA 10\\", \\"BGS 9.5\\", \\"SGC 9\\"). Empty string if raw/ungraded.",\n'
            '    "confidence": "high, medium, or low",\n'
            '    "is_sports_card": true,\n'
            '    "validation_reason": "Explain why this is or isn\'t a valid sports card"\n'
            "}\n\n"
            "Be precise. If the image is not a sports card, set \"is_sports_card\" to false "
            "and explain why in \"validation_reason\".\n"
            "If you can't determine a field, use your best guess based on visible text, logos, and card design."
        ),
    })

    client  = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=768,
        messages=[{"role": "user", "content": content}],
    )

    raw_text = message.content[0].text.strip()

    _EMPTY = {
        "player_name": "", "card_number": "", "brand": "", "subset": "",
        "parallel": "", "serial_number": "", "year": "", "grade": "",
        "confidence": "low", "is_sports_card": True, "validation_reason": "",
        "raw_text": raw_text, "parse_error": True,
    }

    json_match = re.search(r'\{[^{}]*\}', raw_text, re.DOTALL)
    if not json_match:
        return _EMPTY

    try:
        result = json.loads(json_match.group())
    except json.JSONDecodeError:
        return _EMPTY

    return {
        "player_name":       result.get("player_name", ""),
        "card_number":       result.get("card_number", ""),
        "brand":             result.get("brand", ""),
        "subset":            result.get("subset", ""),
        "parallel":          result.get("parallel", ""),
        "serial_number":     result.get("serial_number", ""),
        "year":              result.get("year", ""),
        "grade":             result.get("grade", ""),
        "confidence":        result.get("confidence", "low"),
        "is_sports_card":    result.get("is_sports_card", True),
        "validation_reason": result.get("validation_reason", ""),
        "raw_text":          raw_text,
        "parse_error":       False,
    }
