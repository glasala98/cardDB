"""AI-powered endpoints — grading advisor, market digest, etc.

All endpoints require authentication. Rate-limited at the middleware layer.
"""

import os
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from api.routers.auth import get_current_user

router = APIRouter()


class GradingAdviceRequest(BaseModel):
    card_name: str
    raw_value: float
    psa9:  Optional[float] = None
    psa10: Optional[float] = None
    bgs95: Optional[float] = None
    bgs10: Optional[float] = None
    psa_fee: float = 35.0
    bgs_fee: float = 18.0


@router.post("/grading-advice")
async def grading_advice(
    req: GradingAdviceRequest,
    current_user: dict = Depends(get_current_user),
):
    """Return plain-English grading advice for a card using Claude.

    Reads the pre-computed ROI data from the frontend and asks Claude to
    interpret it with market context and a clear recommendation.
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

    # Build a compact data summary for the prompt
    lines = [f"Card: {req.card_name}", f"Raw (ungraded) market value: ${req.raw_value:.2f} CAD"]
    has_graded_data = False
    if req.psa9 and req.psa9 > 0:
        roi = req.psa9 - req.raw_value - req.psa_fee
        lines.append(f"PSA 9 market value: ${req.psa9:.2f} (fee ${req.psa_fee:.0f}, net ROI ${roi:+.2f})")
        has_graded_data = True
    if req.psa10 and req.psa10 > 0:
        roi = req.psa10 - req.raw_value - req.psa_fee
        lines.append(f"PSA 10 market value: ${req.psa10:.2f} (fee ${req.psa_fee:.0f}, net ROI ${roi:+.2f})")
        has_graded_data = True
    if req.bgs95 and req.bgs95 > 0:
        roi = req.bgs95 - req.raw_value - req.bgs_fee
        lines.append(f"BGS 9.5 market value: ${req.bgs95:.2f} (fee ${req.bgs_fee:.0f}, net ROI ${roi:+.2f})")
        has_graded_data = True
    if req.bgs10 and req.bgs10 > 0:
        roi = req.bgs10 - req.raw_value - req.bgs_fee
        lines.append(f"BGS 10 market value: ${req.bgs10:.2f} (fee ${req.bgs_fee:.0f}, net ROI ${roi:+.2f})")
        has_graded_data = True

    if not has_graded_data:
        lines.append("No PSA or BGS market comps available for this card.")

    data_summary = "\n".join(lines)

    prompt = f"""You are a sports card grading advisor. A collector is deciding whether to send a card to PSA or BGS for grading.

Here is the market data for their card:

{data_summary}

Give a short, direct grading recommendation (3-5 sentences). Cover:
1. Whether grading is worth it financially based on the ROI numbers
2. Which grading company (PSA or BGS) offers the better return if applicable
3. One brief note about card condition risk (grading is a gamble — only pristine cards hit PSA 10)
4. Your bottom-line verdict: Grade it, Skip it, or Maybe

Be conversational and specific to this card's numbers. Don't repeat back all the data — just interpret it."""

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )

    advice = message.content[0].text.strip()
    return {"advice": advice}
