"""General stats endpoints (market alerts, scrape trigger, etc.)."""

import os
import math
import urllib.request
import urllib.error
import json as _json

from fastapi import APIRouter, HTTPException
from dashboard_utils import get_market_alerts, load_data, get_user_paths

router = APIRouter()

GITHUB_OWNER    = "glasala98"
GITHUB_REPO     = "cardDB"
WORKFLOW_FILE   = "daily_scrape.yml"
WORKERS         = 3   # must match --workers in the workflow


@router.get("/alerts")
def market_alerts():
    """Return market alerts for tracked cards."""
    try:
        alerts = get_market_alerts()
    except Exception:
        alerts = []
    return {"alerts": alerts}


@router.post("/trigger-scrape")
def trigger_scrape():
    """Dispatch the daily_scrape GitHub Actions workflow manually.

    Requires a GITHUB_TOKEN env var — a Personal Access Token with
    the 'workflow' scope.
    """
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise HTTPException(
            status_code=503,
            detail="GITHUB_TOKEN not configured on the server. Set it as an environment variable."
        )

    url = (
        f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
        f"/actions/workflows/{WORKFLOW_FILE}/dispatches"
    )
    payload = _json.dumps({"ref": "main"}).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            if resp.status not in (200, 204):
                raise HTTPException(status_code=502, detail="GitHub API rejected the dispatch")
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise HTTPException(status_code=502, detail=f"GitHub API error {e.code}: {body}")
    except urllib.error.URLError as e:
        raise HTTPException(status_code=502, detail=f"Could not reach GitHub: {e.reason}")

    # Estimate runtime based on card count and worker parallelism
    try:
        paths = get_user_paths("admin")
        df = load_data(paths["csv"], paths["results"])
        n_cards = len(df)
    except Exception:
        n_cards = 0

    startup_secs = 120                          # GitHub Actions spin-up + Chrome install
    secs_per_card = 45                          # average per card inc. browser overhead
    scrape_secs = math.ceil(n_cards / WORKERS) * secs_per_card
    estimated_mins = math.ceil((startup_secs + scrape_secs) / 60)

    return {
        "status": "dispatched",
        "card_count": n_cards,
        "estimated_minutes": estimated_mins,
    }


@router.get("/scrape-status")
def scrape_status():
    """Poll the latest GitHub Actions workflow run for the daily scrape."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise HTTPException(status_code=503, detail="GITHUB_TOKEN not configured")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # Get latest run for the workflow
    runs_url = (
        f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
        f"/actions/workflows/{WORKFLOW_FILE}/runs?per_page=1"
    )
    try:
        req = urllib.request.Request(runs_url, headers=headers)
        with urllib.request.urlopen(req) as resp:
            data = _json.loads(resp.read().decode())
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {e}")

    runs = data.get("workflow_runs", [])
    if not runs:
        return {"status": "no_runs"}

    run = runs[0]
    run_id = run["id"]

    # Get job steps for the run (for the log view)
    steps = []
    jobs_url = (
        f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
        f"/actions/runs/{run_id}/jobs"
    )
    try:
        req = urllib.request.Request(jobs_url, headers=headers)
        with urllib.request.urlopen(req) as resp:
            jobs_data = _json.loads(resp.read().decode())
        for job in jobs_data.get("jobs", []):
            for step in job.get("steps", []):
                steps.append({
                    "name":       step.get("name", ""),
                    "status":     step.get("status", ""),
                    "conclusion": step.get("conclusion"),
                    "started_at": step.get("started_at"),
                })
    except Exception:
        pass  # steps are best-effort

    return {
        "status":      run["status"],          # queued | in_progress | completed
        "conclusion":  run.get("conclusion"),  # success | failure | cancelled | None
        "started_at":  run.get("run_started_at"),
        "updated_at":  run.get("updated_at"),
        "html_url":    run.get("html_url"),
        "run_number":  run.get("run_number"),
        "steps":       steps,
    }
