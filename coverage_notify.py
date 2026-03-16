"""Coverage milestone notifier for CardDB.

Checks current price coverage % and raw history coverage % against the last
notified milestone stored in the DB.  When a new 10% threshold is crossed,
outputs GitHub Actions step outputs so the workflow can send an email.

Creates a tiny `coverage_notifications` table on first run (idempotent).
Run via GH Actions daily — no manual intervention needed.
"""
import os
import sys
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]

MILESTONE_STEP = 10  # notify every 10%


def set_output(name, value):
    """Write a GitHub Actions step output."""
    # GH Actions GITHUB_OUTPUT file protocol
    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a") as f:
            # Use delimiter for multi-line values
            delimiter = "EOF"
            f.write(f"{name}<<{delimiter}\n{value}\n{delimiter}\n")
    else:
        print(f"OUTPUT {name}={value}")


def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    # Create milestone tracking table (idempotent)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS coverage_notifications (
            id              SERIAL PRIMARY KEY,
            metric          TEXT NOT NULL UNIQUE,   -- 'price' or 'history'
            last_milestone  INT  NOT NULL DEFAULT 0, -- last % milestone sent (0, 10, 20 ...)
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute("""
        INSERT INTO coverage_notifications (metric, last_milestone)
        VALUES ('price', 0), ('history', 0)
        ON CONFLICT (metric) DO NOTHING
    """)

    # ── Current coverage stats ─────────────────────────────────────────────
    cur.execute("SELECT COUNT(*) FROM card_catalog")
    total_cards = cur.fetchone()[0]

    if total_cards == 0:
        print("No cards in catalog — skipping.")
        set_output("should_notify", "false")
        return

    cur.execute("SELECT COUNT(*) FROM market_prices WHERE fair_value > 0 AND NOT ignored")
    priced_cards = cur.fetchone()[0]

    cur.execute("SELECT COUNT(DISTINCT card_catalog_id) FROM market_raw_sales")
    history_cards = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM market_raw_sales")
    total_sales = cur.fetchone()[0]

    price_pct   = priced_cards  / total_cards * 100
    history_pct = history_cards / total_cards * 100

    # Per-tier breakdown
    cur.execute("""
        SELECT cc.scrape_tier,
               COUNT(cc.id)                                         AS total,
               COUNT(mp.id) FILTER (WHERE mp.fair_value > 0)       AS priced,
               COUNT(DISTINCT mrs.card_catalog_id)                  AS has_history
        FROM card_catalog cc
        LEFT JOIN market_prices mp  ON mp.card_catalog_id  = cc.id AND NOT COALESCE(mp.ignored, FALSE)
        LEFT JOIN market_raw_sales mrs ON mrs.card_catalog_id = cc.id
        GROUP BY cc.scrape_tier
        ORDER BY cc.scrape_tier
    """)
    tiers = cur.fetchall()  # (tier, total, priced, has_history)

    # ── Milestone check ────────────────────────────────────────────────────
    cur.execute("SELECT metric, last_milestone FROM coverage_notifications")
    milestones = {row[0]: row[1] for row in cur.fetchall()}

    price_milestone   = int(price_pct   // MILESTONE_STEP) * MILESTONE_STEP
    history_milestone = int(history_pct // MILESTONE_STEP) * MILESTONE_STEP

    price_crossed   = price_milestone   > milestones.get('price',   0)
    history_crossed = history_milestone > milestones.get('history', 0)

    if not price_crossed and not history_crossed:
        print(f"No new milestone. Price: {price_pct:.1f}% (last notified: {milestones.get('price', 0)}%) "
              f"| History: {history_pct:.1f}% (last notified: {milestones.get('history', 0)}%)")
        set_output("should_notify", "false")
        return

    # ── Build email ────────────────────────────────────────────────────────
    crossed_parts = []
    if price_crossed:
        crossed_parts.append(f"Price Coverage hit {price_milestone}%")
    if history_crossed:
        crossed_parts.append(f"History Coverage hit {history_milestone}%")

    subject = f"CardDB Milestone: {' & '.join(crossed_parts)}"

    tier_lines = []
    for tier, total, priced, has_history in tiers:
        p_pct = round(priced       / total * 100) if total else 0
        h_pct = round(has_history  / total * 100) if total else 0
        tier_lines.append(
            f"  {tier:<10} {p_pct:>3}% priced  |  {h_pct:>3}% history  "
            f"({priced:,} / {total:,} cards)"
        )

    next_price_milestone   = price_milestone   + MILESTONE_STEP
    next_history_milestone = history_milestone + MILESTONE_STEP

    body = f"""CardDB Database Build-Out Update
{'=' * 50}

{chr(10).join(f'  ✓ {p}' for p in crossed_parts)}

OVERALL COVERAGE
  Price Coverage   : {price_pct:.1f}%  ({priced_cards:,} / {total_cards:,} cards)
  History Coverage : {history_pct:.1f}%  ({history_cards:,} / {total_cards:,} cards)
  Sales Stored     : {total_sales:,} individual eBay sale records

COVERAGE BY TIER
{chr(10).join(tier_lines)}

NEXT MILESTONES
  Price   → {next_price_milestone}%
  History → {next_history_milestone}%

View dashboard: https://southwestsportscards.ca
"""

    print(subject)
    print(body)

    # ── Persist new milestones ─────────────────────────────────────────────
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
