"""Coverage milestone notifier for CardDB.

Checks current price coverage % and raw history coverage % against the last
notified milestone stored in the DB.  When a new 10% threshold is crossed,
sends a full dashboard status report email.

Creates a tiny `coverage_notifications` table on first run (idempotent).
Run via GH Actions daily — no manual intervention needed.
"""
import os
import sys
from datetime import datetime, timezone
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]

MILESTONE_STEP = 10  # notify every 10%


def set_output(name, value):
    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a") as f:
            delimiter = "EOF"
            f.write(f"{name}<<{delimiter}\n{value}\n{delimiter}\n")
    else:
        print(f"OUTPUT {name}={value}")


def bar(pct, width=20):
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    # Create milestone tracking table (idempotent)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS coverage_notifications (
            id              SERIAL PRIMARY KEY,
            metric          TEXT NOT NULL UNIQUE,
            last_milestone  INT  NOT NULL DEFAULT 0,
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute("""
        INSERT INTO coverage_notifications (metric, last_milestone)
        VALUES ('price', 0), ('history', 0)
        ON CONFLICT (metric) DO NOTHING
    """)

    # ── Overall counts ─────────────────────────────────────────────────────
    cur.execute("SELECT COUNT(*) FROM card_catalog")
    total_cards = cur.fetchone()[0]

    if total_cards == 0:
        print("No cards in catalog — skipping.")
        set_output("should_notify", "false")
        return

    cur.execute("SELECT COUNT(*) FROM market_prices WHERE fair_value > 0 AND NOT ignored")
    priced_cards = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM market_prices WHERE confidence = 'no_market'")
    no_market_cards = cur.fetchone()[0]

    cur.execute("SELECT COUNT(DISTINCT card_catalog_id) FROM market_raw_sales")
    history_cards = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM market_raw_sales")
    total_sales = cur.fetchone()[0]

    price_pct   = priced_cards  / total_cards * 100
    history_pct = history_cards / total_cards * 100

    # ── Scrape velocity ────────────────────────────────────────────────────
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE scraped_at >= NOW() - INTERVAL '24 hours') AS last_24h,
            COUNT(*) FILTER (WHERE scraped_at >= NOW() - INTERVAL '7 days')   AS last_7d,
            COUNT(*) FILTER (WHERE scraped_at >= NOW() - INTERVAL '30 days')  AS last_30d
        FROM market_prices
        WHERE fair_value > 0 AND NOT ignored
    """)
    vel = cur.fetchone()
    vel_24h, vel_7d, vel_30d = vel[0], vel[1], vel[2]
    daily_rate = round(vel_7d / 7) if vel_7d else 0

    # ── Per-tier breakdown ─────────────────────────────────────────────────
    cur.execute("""
        SELECT cc.scrape_tier,
               COUNT(cc.id)                                         AS total,
               COUNT(mp.id) FILTER (WHERE mp.fair_value > 0)       AS priced,
               COUNT(DISTINCT mrs.card_catalog_id)                  AS has_history
        FROM card_catalog cc
        LEFT JOIN market_prices mp     ON mp.card_catalog_id  = cc.id AND NOT COALESCE(mp.ignored, FALSE)
        LEFT JOIN market_raw_sales mrs ON mrs.card_catalog_id = cc.id
        GROUP BY cc.scrape_tier
        ORDER BY
            CASE cc.scrape_tier
                WHEN 'staple'  THEN 1
                WHEN 'premium' THEN 2
                WHEN 'stars'   THEN 3
                WHEN 'base'    THEN 4
                ELSE 5
            END
    """)
    tiers = cur.fetchall()  # (tier, total, priced, has_history)

    # ── Last scrape per sport ──────────────────────────────────────────────
    cur.execute("""
        SELECT cc.sport, MAX(mp.scraped_at)
        FROM market_prices mp
        JOIN card_catalog cc ON cc.id = mp.card_catalog_id
        WHERE mp.scraped_at IS NOT NULL
        GROUP BY cc.sport
        ORDER BY cc.sport
    """)
    last_scraped = cur.fetchall()  # (sport, timestamp)

    # ── Recent scrape runs ─────────────────────────────────────────────────
    cur.execute("""
        SELECT workflow, tier, sport, mode, cards_total, cards_found,
               status, started_at
        FROM scrape_runs
        ORDER BY started_at DESC
        LIMIT 8
    """)
    recent_runs = cur.fetchall()

    # ── Milestone check ────────────────────────────────────────────────────
    cur.execute("SELECT metric, last_milestone FROM coverage_notifications")
    milestones = {row[0]: row[1] for row in cur.fetchall()}

    price_milestone   = int(price_pct   // MILESTONE_STEP) * MILESTONE_STEP
    history_milestone = int(history_pct // MILESTONE_STEP) * MILESTONE_STEP

    price_crossed   = price_milestone   > milestones.get('price',   0)
    history_crossed = history_milestone > milestones.get('history', 0)

    force = os.environ.get("FORCE_NOTIFY", "false").lower() == "true"

    if not price_crossed and not history_crossed and not force:
        print(f"No new milestone. Price: {price_pct:.1f}% (last: {milestones.get('price', 0)}%) "
              f"| History: {history_pct:.1f}% (last: {milestones.get('history', 0)}%)")
        set_output("should_notify", "false")
        return

    if force and not price_crossed and not history_crossed:
        price_milestone   = milestones.get('price',   0)
        history_milestone = milestones.get('history', 0)

    # ── Build subject ──────────────────────────────────────────────────────
    is_test = force and not price_crossed and not history_crossed
    if is_test:
        subject = f"CardDB [TEST] Status Report — {price_pct:.1f}% priced / {history_pct:.1f}% history"
    else:
        milestones_hit = []
        if price_crossed:   milestones_hit.append(f"Price {price_milestone}%")
        if history_crossed: milestones_hit.append(f"History {history_milestone}%")
        subject = f"CardDB Milestone Reached: {' & '.join(milestones_hit)}"

    # ── Build email body ───────────────────────────────────────────────────
    now_str = datetime.now(timezone.utc).strftime("%B %d, %Y at %I:%M %p UTC")

    # Milestone banner
    if is_test:
        banner = "  [TEST SEND — no milestone crossed, showing current state]"
    else:
        hits = []
        if price_crossed:   hits.append(f"  PRICE COVERAGE HIT {price_milestone}%!")
        if history_crossed: hits.append(f"  HISTORY COVERAGE HIT {history_milestone}%!")
        banner = "\n".join(hits)

    # Tier table
    tier_price_lines   = []
    tier_history_lines = []
    for tier, total, priced, has_hist in tiers:
        p_pct = priced   / total * 100 if total else 0
        h_pct = has_hist / total * 100 if total else 0
        cards_left = total - priced
        tier_price_lines.append(
            f"  {tier:<10} {bar(p_pct, 15)}  {p_pct:>5.1f}%  "
            f"({priced:>9,} / {total:>10,})  {cards_left:>9,} remaining"
        )
        tier_history_lines.append(
            f"  {tier:<10} {bar(h_pct, 15)}  {h_pct:>5.1f}%  "
            f"({has_hist:>9,} / {total:>10,})"
        )

    # Sport last-scrape table
    sport_lines = []
    for sport, ts in last_scraped:
        ts_str = ts.strftime("%b %d %Y %I:%M %p UTC") if ts else "never"
        sport_lines.append(f"  {sport:<6}  {ts_str}")

    # Recent runs table
    run_lines = []
    for wf, tier, sport, mode, c_total, c_found, status, started in recent_runs:
        wf_short = wf.replace("catalog_tier_", "").replace(".yml", "").replace("_", " ")
        started_str = started.strftime("%b %d %I:%M%p") if started else "—"
        found_str = f"{c_found:,}" if c_found is not None else "—"
        total_str = f"{c_total:,}" if c_total is not None else "—"
        run_lines.append(
            f"  {wf_short:<18} {(sport or 'ALL'):<5} {(tier or '—'):<10} "
            f"{status:<12} {found_str:>8}/{total_str:<8} {started_str}"
        )

    # Cards needed to hit next milestones
    next_price_pct   = price_milestone   + MILESTONE_STEP
    next_history_pct = history_milestone + MILESTONE_STEP
    need_price   = max(0, round(next_price_pct   / 100 * total_cards) - priced_cards)
    need_history = max(0, round(next_history_pct / 100 * total_cards) - history_cards)
    eta_price    = f"~{need_price   // daily_rate:,}d" if daily_rate > 0 and need_price   > 0 else "—"

    body = f"""CardDB — Database Status Report
Generated: {now_str}
{'=' * 65}

{banner}

{'=' * 65}
OVERALL DATABASE HEALTH
{'=' * 65}

  Total Cards in Catalog  : {total_cards:>12,}
  Cards with Price        : {priced_cards:>12,}   ({price_pct:.1f}%)
  Cards confirmed no-sale : {no_market_cards:>12,}
  Cards with Sale History : {history_cards:>12,}   ({history_pct:.1f}%)
  Individual Sales Stored : {total_sales:>12,}   (market_raw_sales)

{'=' * 65}
PRICE COVERAGE BY TIER
{'=' * 65}

  Tier        Progress               Pct      Priced / Total       Remaining
  {'─' * 80}
{chr(10).join(tier_price_lines)}

{'=' * 65}
SALE HISTORY COVERAGE BY TIER  (market_raw_sales)
{'=' * 65}

  Tier        Progress               Pct      Cards w/ History / Total
  {'─' * 60}
{chr(10).join(tier_history_lines)}

{'=' * 65}
SCRAPE VELOCITY
{'=' * 65}

  Last 24 hours  : {vel_24h:>8,} cards priced
  Last 7 days    : {vel_7d:>8,} cards priced
  Last 30 days   : {vel_30d:>8,} cards priced
  Daily avg (7d) : {daily_rate:>8,} cards/day

{'=' * 65}
LAST SCRAPE BY SPORT
{'=' * 65}

{chr(10).join(sport_lines) if sport_lines else "  No data yet"}

{'=' * 65}
RECENT SCRAPE RUNS  (last 8)
{'=' * 65}

  Workflow            Sport  Tier        Status       Found    Total    Started
  {'─' * 80}
{chr(10).join(run_lines) if run_lines else "  No runs recorded yet"}

{'=' * 65}
NEXT MILESTONES
{'=' * 65}

  Price Coverage   → {next_price_pct}%   (need {need_price:,} more cards  {eta_price} at current rate)
  History Coverage → {next_history_pct}%   (need {need_history:,} more cards  — run backfill workflow)

  View full dashboard : https://southwestsportscards.ca
  GitHub Actions      : https://github.com/glasala98/cardDB/actions

{'=' * 65}
"""

    print(subject)
    print(body)

    # ── Persist milestones (skip on test sends) ────────────────────────────
    if is_test:
        print("Test send — milestones not updated in DB.")
    else:
        if price_crossed:
            cur.execute("""
                UPDATE coverage_notifications
                SET last_milestone = %s, updated_at = NOW()
                WHERE metric = 'price'
            """, (price_milestone,))
        if history_crossed:
            cur.execute("""
                UPDATE coverage_notifications
                SET last_milestone = %s, updated_at = NOW()
                WHERE metric = 'history'
            """, (history_milestone,))

    set_output("should_notify", "true")
    set_output("subject", subject)
    set_output("body", body)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"coverage_notify ERROR: {e}", file=sys.stderr)
        set_output("should_notify", "false")
        sys.exit(1)
