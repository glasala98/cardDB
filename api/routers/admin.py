"""Admin endpoints — user management (admin role required)."""

import bcrypt
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from db import get_db
from api.routers.auth import get_current_user

router = APIRouter()


def _require_admin(username: str = Depends(get_current_user)):
    """Enforce admin role — checks the PostgreSQL users table."""
    # Dev fallback: the hardcoded admin/admin account has no DB row
    if username == "admin":
        return username
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT role FROM users WHERE username = %s", (username,))
            row = cur.fetchone()
    if not row or row[0] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return username


class UserCreate(BaseModel):
    username: str
    password: str
    display_name: str = ""
    role: str = "user"


class PasswordChange(BaseModel):
    password: str


class RoleChange(BaseModel):
    role: str


@router.get("/users")
def list_users(_admin: str = Depends(_require_admin)):
    """Return all registered users, excluding password hashes."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT username, display_name, role FROM users ORDER BY username")
            rows = cur.fetchall()
    return {"users": [{"username": r[0], "display_name": r[1], "role": r[2]} for r in rows]}


@router.post("/users")
def create_user(body: UserCreate, _admin: str = Depends(_require_admin)):
    """Create a new user in the PostgreSQL users table."""
    if not body.password:
        raise HTTPException(status_code=400, detail="Password is required")
    pw_hash = bcrypt.hashpw(body.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (username, display_name, password_hash, role) VALUES (%s, %s, %s, %s)",
                    (body.username.lower(), body.display_name or body.username, pw_hash, body.role)
                )
            conn.commit()
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Username already exists")
        raise HTTPException(status_code=500, detail="Could not create user")
    return {"status": "created", "username": body.username.lower()}


@router.delete("/users/{username}")
def delete_user(username: str, admin: str = Depends(_require_admin)):
    """Delete a user from the PostgreSQL users table."""
    if username == admin:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE username = %s RETURNING username", (username,))
            deleted = cur.fetchone()
        conn.commit()
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "deleted"}


@router.patch("/users/{username}/password")
def change_password(username: str, body: PasswordChange, _admin: str = Depends(_require_admin)):
    """Change password for an existing user."""
    if not body.password:
        raise HTTPException(status_code=400, detail="Password is required")
    pw_hash = bcrypt.hashpw(body.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET password_hash = %s WHERE username = %s RETURNING username",
                (pw_hash, username)
            )
            updated = cur.fetchone()
        conn.commit()
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "updated"}


@router.patch("/users/{username}/role")
def change_role(username: str, body: RoleChange, admin: str = Depends(_require_admin)):
    """Change the role of an existing user."""
    if username == admin:
        raise HTTPException(status_code=400, detail="Cannot change your own role")
    if body.role not in ("user", "admin", "guest"):
        raise HTTPException(status_code=400, detail="Role must be user, admin, or guest")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET role = %s WHERE username = %s RETURNING username",
                (body.role, username)
            )
            updated = cur.fetchone()
        conn.commit()
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "updated", "role": body.role}


# ── Price quality ──────────────────────────────────────────────────────────────

@router.patch("/market-prices/{price_id}/ignore")
def toggle_ignore(price_id: int, _admin: str = Depends(_require_admin)):
    """Toggle the ignored flag on a market_prices row."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE market_prices SET ignored = NOT ignored WHERE id = %s RETURNING id, ignored",
                (price_id,)
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise HTTPException(status_code=404, detail="Price record not found")
    return {"id": row[0], "ignored": row[1]}


@router.get("/outliers")
def get_outliers(
    limit: int = 50,
    _admin: str = Depends(_require_admin),
):
    """Return market_prices rows that look like outliers.

    An outlier is a price where fair_value > 5× the median fair_value for
    that player across all their cards, and the player median is > $1
    (to avoid false positives on very cheap cards). Results ordered by
    how far above the player median they are (worst first).
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '15s'")
            cur.execute("""
                WITH player_medians AS (
                    SELECT cc.player_name,
                           PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY mp.fair_value) AS median_val
                    FROM market_prices mp
                    JOIN card_catalog cc ON cc.id = mp.card_catalog_id
                    WHERE mp.fair_value > 0 AND mp.ignored = FALSE
                    GROUP BY cc.player_name
                    HAVING COUNT(*) >= 3
                )
                SELECT
                    mp.id,
                    cc.id AS catalog_id,
                    cc.player_name,
                    cc.sport,
                    cc.year,
                    cc.set_name,
                    cc.variant,
                    mp.fair_value,
                    pm.median_val,
                    mp.num_sales,
                    mp.confidence,
                    mp.ignored,
                    ROUND((mp.fair_value / pm.median_val)::numeric, 1) AS ratio
                FROM market_prices mp
                JOIN card_catalog cc ON cc.id = mp.card_catalog_id
                JOIN player_medians pm ON pm.player_name = cc.player_name
                WHERE mp.fair_value > 5 * pm.median_val
                  AND pm.median_val > 1
                ORDER BY ratio DESC
                LIMIT %s
            """, [limit])
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()

    result = []
    for row in rows:
        r = dict(zip(cols, row))
        r["fair_value"]  = float(r["fair_value"])
        r["median_val"]  = float(r["median_val"])
        r["ratio"]       = float(r["ratio"])
        result.append(r)
    return {"outliers": result, "total": len(result)}


@router.get("/pipeline-health")
def pipeline_health(_admin: str = Depends(_require_admin)):
    """Return data quality and coverage stats for the admin dashboard."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '10s'")

            # Total catalog size
            cur.execute("SELECT COUNT(*) FROM card_catalog")
            total_cards = cur.fetchone()[0]

            # Priced cards (have market_prices entry with fair_value > 0)
            cur.execute("SELECT COUNT(*) FROM market_prices WHERE fair_value > 0 AND NOT ignored")
            priced_cards = cur.fetchone()[0]

            # Ignored prices
            cur.execute("SELECT COUNT(*) FROM market_prices WHERE ignored = TRUE")
            ignored_count = cur.fetchone()[0]

            # Outlier count (fair_value > 5× player median)
            cur.execute("""
                WITH pm AS (
                    SELECT cc.player_name,
                           PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY mp.fair_value) AS med
                    FROM market_prices mp
                    JOIN card_catalog cc ON cc.id = mp.card_catalog_id
                    WHERE mp.fair_value > 0 AND NOT mp.ignored
                    GROUP BY cc.player_name HAVING COUNT(*) >= 3
                )
                SELECT COUNT(*) FROM market_prices mp
                JOIN card_catalog cc ON cc.id = mp.card_catalog_id
                JOIN pm ON pm.player_name = cc.player_name
                WHERE mp.fair_value > 5 * pm.med AND pm.med > 1 AND NOT mp.ignored
            """)
            outlier_count = cur.fetchone()[0]

            # Coverage by scrape_tier
            cur.execute("""
                SELECT cc.scrape_tier,
                       COUNT(cc.id)                             AS total,
                       COUNT(mp.id) FILTER (WHERE mp.fair_value > 0) AS priced
                FROM card_catalog cc
                LEFT JOIN market_prices mp ON mp.card_catalog_id = cc.id AND NOT COALESCE(mp.ignored, FALSE)
                GROUP BY cc.scrape_tier
                ORDER BY cc.scrape_tier
            """)
            tiers = [{"tier": r[0], "total": r[1], "priced": r[2]} for r in cur.fetchall()]

            # Last scrape date per sport
            cur.execute("""
                SELECT cc.sport, MAX(mp.scraped_at) AS last_scraped
                FROM market_prices mp
                JOIN card_catalog cc ON cc.id = mp.card_catalog_id
                WHERE mp.scraped_at IS NOT NULL
                GROUP BY cc.sport
                ORDER BY cc.sport
            """)
            last_scraped = {r[0]: r[1].isoformat() if r[1] else None for r in cur.fetchall()}

    return {
        "total_cards":   total_cards,
        "priced_cards":  priced_cards,
        "ignored_count": ignored_count,
        "outlier_count": outlier_count,
        "coverage_pct":  round(priced_cards / total_cards * 100, 1) if total_cards else 0,
        "tiers":         tiers,
        "last_scraped":  last_scraped,
    }


@router.get("/scrape-runs/summary")
def get_scrape_runs_summary(_admin: str = Depends(_require_admin)):
    """Per-workflow aggregated stats + anomaly detection for the monitoring dashboard."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '15s'")

            cur.execute("""
                SELECT
                    workflow,
                    COUNT(*) AS total_runs,
                    COUNT(*) FILTER (WHERE status = 'completed') AS success_runs,
                    COUNT(*) FILTER (WHERE status = 'error') AS error_runs,
                    COUNT(*) FILTER (
                        WHERE status = 'completed' AND cards_delta = 0 AND cards_total > 0
                    ) AS zero_delta_runs,
                    ROUND(AVG(
                        CASE WHEN cards_total > 0
                             THEN cards_found::float / cards_total * 100
                        END
                    )::numeric, 1) AS avg_hit_rate,
                    ROUND(AVG(cards_delta)::numeric, 0) AS avg_delta,
                    SUM(cards_delta) AS total_delta,
                    SUM(errors) AS total_errors,
                    MAX(started_at) AS last_run_at,
                    (ARRAY_AGG(status ORDER BY started_at DESC NULLS LAST))[1] AS last_run_status
                FROM scrape_runs
                GROUP BY workflow
                ORDER BY last_run_at DESC NULLS LAST
            """)
            wf_cols = [d[0] for d in cur.description]
            wf_rows = cur.fetchall()

            cur.execute("""
                SELECT
                    id, workflow, sport, tier, mode,
                    started_at, cards_total, cards_found, cards_delta, errors, status,
                    CASE
                        WHEN status = 'error' THEN 'run_error'
                        WHEN status = 'completed' AND cards_delta = 0 AND cards_total > 0
                             THEN 'zero_delta'
                        WHEN status = 'completed' AND cards_total > 0
                             AND cards_found::float / cards_total < 0.10
                             THEN 'low_hit_rate'
                        WHEN errors > 10 THEN 'high_errors'
                    END AS reason
                FROM scrape_runs
                WHERE
                    status = 'error'
                    OR (status = 'completed' AND cards_delta = 0 AND cards_total > 0)
                    OR (status = 'completed' AND cards_total > 0
                        AND cards_found::float / cards_total < 0.10)
                    OR errors > 10
                ORDER BY started_at DESC
                LIMIT 50
            """)
            anomaly_cols = [d[0] for d in cur.description]
            anomaly_rows = cur.fetchall()

    workflows = []
    for row in wf_rows:
        r = dict(zip(wf_cols, row))
        r['avg_hit_rate']  = float(r['avg_hit_rate'])  if r['avg_hit_rate']  is not None else None
        r['avg_delta']     = int(r['avg_delta'])        if r['avg_delta']     is not None else 0
        r['total_delta']   = int(r['total_delta'])      if r['total_delta']   is not None else 0
        r['total_errors']  = int(r['total_errors'])     if r['total_errors']  is not None else 0
        r['last_run_at']   = r['last_run_at'].isoformat() if r['last_run_at'] else None
        r['success_rate']  = round(r['success_runs'] / r['total_runs'] * 100, 1) if r['total_runs'] else 0
        workflows.append(r)

    anomalies = []
    for row in anomaly_rows:
        r = dict(zip(anomaly_cols, row))
        r['started_at'] = r['started_at'].isoformat() if r['started_at'] else None
        anomalies.append(r)

    return {"workflows": workflows, "anomalies": anomalies}


@router.get("/scrape-runs")
def get_scrape_runs(
    limit: int = 50,
    workflow: str = None,
    _admin: str = Depends(_require_admin),
):
    """Return recent scrape run history from the scrape_runs table."""
    where_parts, params = [], []
    if workflow:
        where_parts.append("workflow = %s")
        params.append(workflow)
    where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT id, workflow, sport, tier, mode,
                       started_at, finished_at,
                       cards_total, cards_found, cards_delta, errors, status
                FROM scrape_runs
                {where_sql}
                ORDER BY started_at DESC
                LIMIT %s
            """, params + [limit])
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()

    runs = []
    for row in rows:
        r = dict(zip(cols, row))
        r["started_at"]  = r["started_at"].isoformat()  if r["started_at"]  else None
        r["finished_at"] = r["finished_at"].isoformat() if r["finished_at"] else None
        runs.append(r)
    return {"runs": runs}
