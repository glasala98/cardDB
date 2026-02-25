"""General stats endpoints (market alerts, etc.)."""

from fastapi import APIRouter
from dashboard_utils import get_market_alerts

router = APIRouter()


@router.get("/alerts")
def market_alerts():
    """Return market alerts for tracked cards."""
    try:
        alerts = get_market_alerts()
    except Exception:
        alerts = []
    return {"alerts": alerts}
