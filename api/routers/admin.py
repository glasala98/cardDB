"""Admin endpoints — user management (admin role required)."""

import os
import re
import urllib.request
import json as _json
import bcrypt
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from db import get_db
from api.routers.auth import get_current_user

GITHUB_OWNER = "glasala98"
GITHUB_REPO  = "cardDB"

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

            # Newly scraped this week / month (cards that got a price update)
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE scraped_at >= NOW() - INTERVAL '7 days')  AS priced_7d,
                    COUNT(*) FILTER (WHERE scraped_at >= NOW() - INTERVAL '30 days') AS priced_30d
                FROM market_prices
                WHERE fair_value > 0 AND NOT ignored
            """)
            _fresh = cur.fetchone()
            newly_priced_7d  = _fresh[0]
            newly_priced_30d = _fresh[1]

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
        "total_cards":     total_cards,
        "priced_cards":    priced_cards,
        "ignored_count":   ignored_count,
        "outlier_count":   outlier_count,
        "coverage_pct":    round(priced_cards / total_cards * 100, 1) if total_cards else 0,
        "newly_priced_7d":  newly_priced_7d,
        "newly_priced_30d": newly_priced_30d,
        "tiers":           tiers,
        "last_scraped":    last_scraped,
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
                    COUNT(*) FILTER (WHERE status IN ('error', 'timed_out')) AS error_runs,
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

            # Consecutive errors: last N runs per workflow to count unbroken error streak
            cur.execute("""
                SELECT workflow, status
                FROM (
                    SELECT workflow, status,
                           ROW_NUMBER() OVER (PARTITION BY workflow ORDER BY started_at DESC) AS rn
                    FROM scrape_runs
                    WHERE status IN ('completed', 'error', 'timed_out')
                ) sub
                WHERE rn <= 10
                ORDER BY workflow, rn
            """)
            consec_map: dict[str, int] = {}
            cur_wf = None
            streak = 0
            for wf_name, status in cur.fetchall():
                if wf_name != cur_wf:
                    if cur_wf is not None:
                        consec_map[cur_wf] = streak
                    cur_wf = wf_name
                    streak = 0
                if streak == -1:
                    continue  # already broken
                if status in ('error', 'timed_out'):
                    streak += 1
                else:
                    consec_map[wf_name] = streak
                    streak = -1  # mark broken so we stop counting
            if cur_wf and cur_wf not in consec_map:
                consec_map[cur_wf] = streak if streak != -1 else 0

            cur.execute("""
                SELECT
                    id, workflow, sport, tier, mode,
                    started_at, cards_total, cards_found, cards_delta, errors, status,
                    CASE
                        WHEN status = 'error'      THEN 'run_error'
                        WHEN status = 'timed_out'  THEN 'timed_out'
                        WHEN status = 'completed' AND cards_total > 100
                             AND COALESCE(cards_processed, 0) < cards_total * 0.9
                             THEN 'timed_out'
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
                    OR status = 'timed_out'
                    OR (status = 'completed' AND cards_total > 100
                        AND COALESCE(cards_processed, 0) < cards_total * 0.9)
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
        r['avg_hit_rate']       = float(r['avg_hit_rate'])  if r['avg_hit_rate']  is not None else None
        r['avg_delta']          = int(r['avg_delta'])        if r['avg_delta']     is not None else 0
        r['total_delta']        = int(r['total_delta'])      if r['total_delta']   is not None else 0
        r['total_errors']       = int(r['total_errors'])     if r['total_errors']  is not None else 0
        r['last_run_at']        = r['last_run_at'].isoformat() if r['last_run_at'] else None
        r['success_rate']       = round(r['success_runs'] / r['total_runs'] * 100, 1) if r['total_runs'] else 0
        r['consecutive_errors'] = consec_map.get(r['workflow'], 0)
        workflows.append(r)

    anomalies = []
    for row in anomaly_rows:
        r = dict(zip(anomaly_cols, row))
        r['started_at'] = r['started_at'].isoformat() if r['started_at'] else None
        anomalies.append(r)

    return {"workflows": workflows, "anomalies": anomalies}


@router.get("/data-quality")
def get_data_quality(_admin: str = Depends(_require_admin)):
    """Data quality metrics: freshness, confidence, gaps."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '20s'")

            # Global freshness / confidence stats
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE scraped_at < NOW() - INTERVAL '30 days')  AS stale_30,
                    COUNT(*) FILTER (WHERE scraped_at < NOW() - INTERVAL '60 days')  AS stale_60,
                    COUNT(*) FILTER (WHERE scraped_at < NOW() - INTERVAL '90 days')  AS stale_90,
                    COUNT(*) FILTER (WHERE scraped_at IS NULL)                        AS never_scraped,
                    COUNT(*) FILTER (WHERE num_sales = 1)                             AS single_sale,
                    COUNT(*) FILTER (WHERE COALESCE(num_sales, 0) <= 2)               AS low_confidence,
                    COUNT(*) FILTER (WHERE COALESCE(fair_value, 0) = 0)               AS zero_price
                FROM market_prices
                WHERE NOT COALESCE(ignored, FALSE)
            """)
            row = cur.fetchone()
            stats = {
                'stale_30':       row[0], 'stale_60':       row[1],
                'stale_90':       row[2], 'never_scraped':  row[3],
                'single_sale':    row[4], 'low_confidence': row[5],
                'zero_price':     row[6],
            }

            # Freshness breakdown by tier
            cur.execute("""
                SELECT
                    cc.scrape_tier,
                    COUNT(mp.id)                                                                      AS total,
                    COUNT(mp.id) FILTER (WHERE mp.scraped_at >= NOW() - INTERVAL '7 days')           AS fresh_7d,
                    COUNT(mp.id) FILTER (WHERE mp.scraped_at >= NOW() - INTERVAL '30 days'
                                           AND mp.scraped_at <  NOW() - INTERVAL '7 days')           AS fresh_30d,
                    COUNT(mp.id) FILTER (WHERE mp.scraped_at <  NOW() - INTERVAL '30 days'
                                           OR  mp.scraped_at IS NULL)                                AS stale
                FROM market_prices mp
                JOIN card_catalog cc ON cc.id = mp.card_catalog_id
                WHERE NOT COALESCE(mp.ignored, FALSE)
                GROUP BY cc.scrape_tier
                ORDER BY cc.scrape_tier
            """)
            freshness_by_tier = [
                {'tier': r[0], 'total': r[1], 'fresh_7d': r[2], 'fresh_30d': r[3], 'stale': r[4]}
                for r in cur.fetchall()
            ]

            # Priority stale cards (staple/premium, >30 days old, still have value)
            cur.execute("""
                SELECT
                    cc.player_name, cc.sport, cc.year, cc.set_name, cc.variant,
                    mp.fair_value, mp.num_sales, mp.scraped_at, cc.scrape_tier
                FROM market_prices mp
                JOIN card_catalog cc ON cc.id = mp.card_catalog_id
                WHERE (mp.scraped_at < NOW() - INTERVAL '30 days' OR mp.scraped_at IS NULL)
                  AND cc.scrape_tier IN ('staple', 'premium')
                  AND NOT COALESCE(mp.ignored, FALSE)
                  AND mp.fair_value > 0
                ORDER BY mp.scraped_at ASC NULLS FIRST
                LIMIT 50
            """)
            cols = [d[0] for d in cur.description]
            stale_cards = []
            for row in cur.fetchall():
                r = dict(zip(cols, row))
                r['fair_value'] = float(r['fair_value']) if r['fair_value'] else 0
                r['scraped_at'] = r['scraped_at'].isoformat() if r['scraped_at'] else None
                stale_cards.append(r)

            # Low-confidence cards (1 sale, value > $5 — most likely to be wrong)
            cur.execute("""
                SELECT
                    cc.player_name, cc.sport, cc.year, cc.set_name, cc.variant,
                    mp.fair_value, mp.num_sales, mp.scraped_at, cc.scrape_tier
                FROM market_prices mp
                JOIN card_catalog cc ON cc.id = mp.card_catalog_id
                WHERE mp.num_sales = 1
                  AND mp.fair_value > 5
                  AND NOT COALESCE(mp.ignored, FALSE)
                ORDER BY mp.fair_value DESC
                LIMIT 50
            """)
            cols = [d[0] for d in cur.description]
            low_conf_cards = []
            for row in cur.fetchall():
                r = dict(zip(cols, row))
                r['fair_value'] = float(r['fair_value']) if r['fair_value'] else 0
                r['scraped_at'] = r['scraped_at'].isoformat() if r['scraped_at'] else None
                low_conf_cards.append(r)

    return {
        'stats':              stats,
        'freshness_by_tier':  freshness_by_tier,
        'stale_cards':        stale_cards,
        'low_confidence_cards': low_conf_cards,
    }


@router.get("/snapshot-audit")
def get_snapshot_audit(
    tier:  str = "staple",
    sport: str = None,
    limit: int = 25,
    _admin: str = Depends(_require_admin),
):
    """Return the last 5 price snapshots per card for ETL Type-2 integrity review.

    Shows recently scraped cards with their full price history so admins can
    verify prices are moving correctly and history is accumulating as expected.

    Args:
        tier:  scrape_tier filter (staple/premium/stars/base).
        sport: Optional sport filter.
        limit: Max cards to return (default 25).

    Returns:
        Dict with key 'cards', each entry containing card metadata plus a
        'snapshots' list of the last 5 {scraped_at, fair_value, num_sales}.
    """
    from typing import Optional as Opt

    where_parts = ["cc.scrape_tier = %s", "NOT COALESCE(mp.ignored, FALSE)", "mp.fair_value > 0"]
    params: list = [tier]

    if sport:
        where_parts.append("cc.sport = %s")
        params.append(sport.upper())

    where_sql = " AND ".join(where_parts)

    with get_db() as conn:
        cur = conn.cursor()

        # Fetch recently scraped cards for this tier
        cur.execute(f"""
            SELECT
                cc.id, cc.player_name, cc.set_name, cc.year, cc.sport,
                cc.scrape_tier, cc.variant,
                mp.fair_value  AS current_value,
                mp.prev_value,
                mp.scraped_at  AS last_scraped
            FROM card_catalog cc
            JOIN market_prices mp ON mp.card_catalog_id = cc.id
            WHERE {where_sql}
            ORDER BY mp.scraped_at DESC NULLS LAST
            LIMIT %s
        """, params + [limit])
        card_rows = cur.fetchall()

        if not card_rows:
            return {"cards": []}

        card_ids = [r[0] for r in card_rows]

        # Fetch last 5 snapshots for each card
        cur.execute("""
            SELECT card_catalog_id, scraped_at, fair_value, num_sales
            FROM (
                SELECT
                    card_catalog_id, scraped_at, fair_value, num_sales,
                    ROW_NUMBER() OVER (
                        PARTITION BY card_catalog_id ORDER BY scraped_at DESC
                    ) AS rn
                FROM market_price_history
                WHERE card_catalog_id = ANY(%s)
            ) sub
            WHERE rn <= 5
            ORDER BY card_catalog_id, scraped_at DESC
        """, [card_ids])
        snap_rows = cur.fetchall()

    snaps_by_id: dict = {}
    for cid, snap_at, fv, ns in snap_rows:
        snaps_by_id.setdefault(cid, []).append({
            "scraped_at": snap_at.isoformat() if snap_at else None,
            "fair_value": float(fv) if fv is not None else None,
            "num_sales":  ns,
        })

    cards = []
    for row in card_rows:
        cid, player, set_name, year, sport_v, tier_v, variant, curr, prev, last_scraped = row
        cards.append({
            "id":            cid,
            "player_name":   player,
            "set_name":      set_name,
            "year":          year,
            "sport":         sport_v,
            "scrape_tier":   tier_v,
            "variant":       variant,
            "current_value": float(curr) if curr is not None else None,
            "prev_value":    float(prev) if prev is not None else None,
            "last_scraped":  last_scraped.isoformat() if last_scraped else None,
            "snapshots":     snaps_by_id.get(cid, []),
        })

    return {"cards": cards}


@router.get("/scrape-runs/{run_id}/errors")
def get_scrape_run_errors(run_id: int, limit: int = 100, _admin: str = Depends(_require_admin)):
    """Return per-card errors logged for a specific scrape run."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT sel.id, sel.card_catalog_id, sel.card_name,
                       sel.error_type, sel.error_msg, sel.occurred_at
                FROM scrape_error_log sel
                WHERE sel.run_id = %s
                ORDER BY sel.occurred_at DESC
                LIMIT %s
            """, [run_id, limit])
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
    errors = []
    for row in rows:
        r = dict(zip(cols, row))
        r["occurred_at"] = r["occurred_at"].isoformat() if r["occurred_at"] else None
        errors.append(r)
    return {"errors": errors, "run_id": run_id}


@router.get("/sealed-products/quality")
def sealed_quality(_admin: str = Depends(_require_admin)):
    """Data quality report for sealed_products: sport mismatches, bad MSRPs, duplicates."""
    SPORT_SIGNALS = {
        "NHL": ["%hockey%", "%nhl %"],
        "NBA": ["%basketball%", "%nba %"],
        "NFL": ["%football%", "%nfl %", "%gridiron%"],
        "MLB": ["%baseball%", "%mlb %", "%bowman%"],
    }

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '10s'")

            # Sport mismatches: set name signals a different sport than stored
            mismatches = []
            for correct_sport, patterns in SPORT_SIGNALS.items():
                for pattern in patterns:
                    cur.execute("""
                        SELECT id, sport, year, set_name, product_type, msrp
                        FROM sealed_products
                        WHERE sport != %s AND set_name ILIKE %s
                        ORDER BY sport, year DESC, set_name
                        LIMIT 100
                    """, [correct_sport, pattern])
                    cols = [d[0] for d in cur.description]
                    for row in cur.fetchall():
                        r = dict(zip(cols, row))
                        r["correct_sport"] = correct_sport
                        r["msrp"] = float(r["msrp"]) if r["msrp"] else None
                        mismatches.append(r)

            # Bad MSRPs: suspiciously low (< $3) or zero
            cur.execute("""
                SELECT id, sport, year, set_name, product_type, msrp
                FROM sealed_products
                WHERE msrp IS NOT NULL AND msrp < 3
                ORDER BY msrp ASC, sport, set_name
                LIMIT 100
            """)
            cols = [d[0] for d in cur.description]
            bad_msrp = []
            for row in cur.fetchall():
                r = dict(zip(cols, row))
                r["msrp"] = float(r["msrp"]) if r["msrp"] else None
                bad_msrp.append(r)

            # Duplicates: same (year, set_name, product_type) under multiple sports
            cur.execute("""
                SELECT year, set_name, product_type, array_agg(sport ORDER BY sport) AS sports,
                       COUNT(*) AS cnt
                FROM sealed_products
                GROUP BY year, set_name, product_type
                HAVING COUNT(*) > 1
                ORDER BY cnt DESC, set_name
                LIMIT 100
            """)
            duplicates = [
                {"year": r[0], "set_name": r[1], "product_type": r[2],
                 "sports": r[3], "count": r[4]}
                for r in cur.fetchall()
            ]

            # Summary counts
            cur.execute("SELECT COUNT(*) FROM sealed_products")
            total = cur.fetchone()[0]

    return {
        "total":       total,
        "mismatches":  mismatches,
        "bad_msrp":    bad_msrp,
        "duplicates":  duplicates,
        "issues":      len(mismatches) + len(bad_msrp) + len(duplicates),
    }


@router.delete("/sealed-products/mismatches")
def delete_sport_mismatches(_admin: str = Depends(_require_admin)):
    """Delete sealed_products rows where set name clearly indicates a different sport."""
    RULES = [
        ("NFL", "%football%"), ("NFL", "%gridiron%"),
        ("MLB", "%baseball%"), ("MLB", "%bowman%"),
        ("NBA", "%basketball%"),
        ("NHL", "%hockey%"),
    ]
    total = 0
    with get_db() as conn:
        with conn.cursor() as cur:
            for correct_sport, pattern in RULES:
                cur.execute(
                    "DELETE FROM sealed_products WHERE sport != %s AND set_name ILIKE %s",
                    [correct_sport, pattern],
                )
                total += cur.rowcount
        conn.commit()
    return {"deleted": total}


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
                       cards_total, cards_processed, cards_found, cards_delta, errors, status
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


# ── Sealed Products Manager ────────────────────────────────────────────────────

class SealedProductPatch(BaseModel):
    msrp: float | None = None
    cards_per_pack: int | None = None
    packs_per_box: int | None = None
    release_date: str | None = None  # ISO date string


@router.get("/sealed-products")
def list_sealed_products(
    sport: str = None,
    year: str = None,
    set_name: str = None,
    page: int = 1,
    per_page: int = 50,
    _admin: str = Depends(_require_admin),
):
    """Return paginated sealed_products rows with nested odds."""
    where_parts, params = [], []
    if sport:
        where_parts.append("sp.sport = %s")
        params.append(sport.upper())
    if year:
        where_parts.append("sp.year ILIKE %s")
        params.append(f"%{year}%")
    if set_name:
        where_parts.append("sp.set_name ILIKE %s")
        params.append(f"%{set_name}%")
    where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
    offset = (page - 1) * per_page

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM sealed_products sp {where_sql}", params)
            total = cur.fetchone()[0]

            cur.execute(f"""
                SELECT sp.id, sp.sport, sp.year, sp.set_name, sp.brand,
                       sp.product_type, sp.msrp, sp.cards_per_pack, sp.packs_per_box,
                       sp.release_date, sp.source_url, sp.updated_at
                FROM sealed_products sp
                {where_sql}
                ORDER BY sp.year DESC, sp.sport, sp.set_name, sp.product_type
                LIMIT %s OFFSET %s
            """, params + [per_page, offset])
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()

            # Fetch odds for returned products
            ids = [r[0] for r in rows]
            odds_by_id: dict = {}
            if ids:
                cur.execute("""
                    SELECT sealed_product_id, card_type, odds_ratio
                    FROM sealed_product_odds
                    WHERE sealed_product_id = ANY(%s)
                    ORDER BY sealed_product_id, card_type
                """, [ids])
                for pid, card_type, odds_ratio in cur.fetchall():
                    odds_by_id.setdefault(pid, []).append({"card_type": card_type, "odds_ratio": odds_ratio})

    products = []
    for row in rows:
        r = dict(zip(cols, row))
        r["msrp"] = float(r["msrp"]) if r["msrp"] is not None else None
        r["release_date"] = r["release_date"].isoformat() if r["release_date"] else None
        r["updated_at"] = r["updated_at"].isoformat() if r["updated_at"] else None
        r["odds"] = odds_by_id.get(r["id"], [])
        products.append(r)

    return {"products": products, "total": total, "pages": -(-total // per_page)}


@router.patch("/sealed-products/{product_id}")
def update_sealed_product(
    product_id: int,
    body: SealedProductPatch,
    _admin: str = Depends(_require_admin),
):
    """Update MSRP, pack config, or release date for a sealed product."""
    sets, params = [], []
    if body.msrp is not None:
        sets.append("msrp = %s"); params.append(body.msrp)
    if body.cards_per_pack is not None:
        sets.append("cards_per_pack = %s"); params.append(body.cards_per_pack)
    if body.packs_per_box is not None:
        sets.append("packs_per_box = %s"); params.append(body.packs_per_box)
    if body.release_date is not None:
        sets.append("release_date = %s"); params.append(body.release_date or None)
    if not sets:
        raise HTTPException(status_code=400, detail="No fields to update")
    sets.append("updated_at = NOW()")
    params.append(product_id)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                UPDATE sealed_products
                SET {', '.join(sets)}
                WHERE id = %s
                RETURNING id, msrp, cards_per_pack, packs_per_box, release_date
            """, params)
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Product not found")
        conn.commit()

    pid, msrp, cpp, ppb, rd = row
    return {
        "id": pid,
        "msrp": float(msrp) if msrp is not None else None,
        "cards_per_pack": cpp,
        "packs_per_box": ppb,
        "release_date": rd.isoformat() if rd else None,
    }


class WorkflowTrigger(BaseModel):
    workflow_file: str   # e.g. "catalog_tier_staple.yml"
    inputs: dict = {}    # optional workflow_dispatch inputs


@router.post("/trigger-workflow")
def trigger_workflow(
    body: WorkflowTrigger,
    _admin: str = Depends(_require_admin),
):
    """Dispatch any GitHub Actions workflow via workflow_dispatch.

    Only .yml files in the repo's .github/workflows/ directory are allowed.
    Requires GITHUB_TOKEN env var with repo + workflow scopes.
    """
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise HTTPException(status_code=503, detail="GITHUB_TOKEN not configured")

    # Validate: only plain filenames ending in .yml, no path traversal
    if not re.fullmatch(r"[\w\-]+\.yml", body.workflow_file):
        raise HTTPException(status_code=400, detail="Invalid workflow filename")

    url = (
        f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
        f"/actions/workflows/{body.workflow_file}/dispatches"
    )
    payload = _json.dumps({"ref": "main", "inputs": body.inputs}).encode()
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
        body_txt = e.read().decode(errors="replace")
        raise HTTPException(status_code=502, detail=f"GitHub API error {e.code}: {body_txt}")
    except urllib.error.URLError as e:
        raise HTTPException(status_code=502, detail=f"Could not reach GitHub: {e.reason}")

    return {"status": "dispatched", "workflow": body.workflow_file}


class BulkIgnoreBody(BaseModel):
    ids: list[int]


@router.post("/outliers/bulk-ignore")
def bulk_ignore_outliers(
    body: BulkIgnoreBody,
    _admin: str = Depends(_require_admin),
):
    """Ignore multiple market_prices records at once."""
    if not body.ids:
        return {"ignored": 0}
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE market_prices SET ignored = TRUE WHERE id = ANY(%s) AND NOT ignored",
                (body.ids,)
            )
            count = cur.rowcount
        conn.commit()
    return {"ignored": count}
