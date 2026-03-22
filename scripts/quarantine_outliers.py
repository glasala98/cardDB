"""Auto-quarantine outlier prices using a 3× player-median threshold.

Finds market_prices rows where fair_value > 3× the player's median price
(when the median is > $5, to avoid noise on cheap cards).

Borderline cases (3–6× median) are optionally validated by Claude before
being quarantined — pass --ai to enable this. Clear outliers (>6× median)
are quarantined unconditionally.

Usage:
    python quarantine_outliers.py [--ai] [--dry-run] [--threshold FLOAT]
"""

import argparse
import json
import os
import sys

import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("quarantine_outliers: DATABASE_URL not set, skipping")
    sys.exit(0)


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--ai",        action="store_true", help="Use Claude to validate borderline outliers (3–6×)")
    p.add_argument("--dry-run",   action="store_true", help="Print what would be quarantined, don't write")
    p.add_argument("--threshold", type=float, default=3.0, help="Lower outlier multiplier (default 3.0)")
    p.add_argument("--clear-at",  type=float, default=6.0, help="Always-quarantine multiplier (default 6.0)")
    return p.parse_args()


def fetch_outliers(cur, threshold: float):
    """Return all un-ignored prices above `threshold`× player median (median > $5, ≥3 data points)."""
    cur.execute("""
        WITH player_medians AS (
            SELECT cc.player_name,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY mp.fair_value) AS median_val
            FROM market_prices mp
            JOIN card_catalog cc ON cc.id = mp.card_catalog_id
            WHERE mp.fair_value > 0 AND NOT mp.ignored
            GROUP BY cc.player_name
            HAVING COUNT(*) >= 3
        )
        SELECT
            mp.id,
            cc.player_name,
            cc.year,
            cc.set_name,
            cc.card_number,
            cc.sport,
            mp.fair_value,
            pm.median_val,
            ROUND((mp.fair_value / pm.median_val)::numeric, 2) AS ratio
        FROM market_prices mp
        JOIN card_catalog cc ON cc.id = mp.card_catalog_id
        JOIN player_medians pm ON pm.player_name = cc.player_name
        WHERE mp.fair_value > %s * pm.median_val
          AND pm.median_val > 5
          AND NOT mp.ignored
        ORDER BY ratio DESC
        LIMIT 2000
    """, (threshold,))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def claude_validate(borderline: list[dict]) -> set[int]:
    """Ask Claude which borderline prices are genuine outliers vs. legit high-value variants.

    Returns a set of market_prices IDs that Claude flags as outliers.
    """
    try:
        import anthropic
    except ImportError:
        print("  [AI] anthropic not installed, skipping AI validation")
        return set()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("  [AI] ANTHROPIC_API_KEY not set, skipping AI validation")
        return set()

    client = anthropic.Anthropic(api_key=api_key)

    # Build a compact summary for Claude
    card_lines = []
    for r in borderline[:100]:  # cap at 100 per call
        card_lines.append(
            f"ID={r['id']} | {r['player_name']} | {r['year']} {r['set_name']} #{r['card_number']}"
            f" | ${r['fair_value']:.2f} vs median ${r['median_val']:.2f} ({r['ratio']}×)"
        )
    prompt = (
        "You are a sports card pricing expert. Below is a list of eBay price records that are "
        "3–6× above a player's typical card price. Some may be legitimate high-value variants "
        "(autographs, patch cards, 1/1s, superfractors, etc.); others are data errors.\n\n"
        "For each record, reply ONLY with a JSON array of IDs that are genuine pricing errors "
        "or bad data (should be quarantined). Include an ID only if you're confident it's an error. "
        "If unsure, leave it out — false positives are worse than false negatives.\n\n"
        "Cards:\n" + "\n".join(card_lines) + "\n\n"
        "Respond with a JSON array of integer IDs, e.g. [123, 456]. Nothing else."
    )

    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
        ids = json.loads(text)
        if isinstance(ids, list):
            return set(int(i) for i in ids if isinstance(i, int))
    except Exception as e:
        print(f"  [AI] Claude validation error: {e}")

    return set()


def quarantine(cur, ids: list[int], dry_run: bool) -> int:
    if not ids:
        return 0
    if dry_run:
        print(f"  [dry-run] would ignore {len(ids)} prices: {ids[:10]}{'...' if len(ids) > 10 else ''}")
        return len(ids)
    cur.execute(
        "UPDATE market_prices SET ignored = TRUE WHERE id = ANY(%s) AND NOT ignored",
        (ids,)
    )
    return cur.rowcount


def main():
    args = parse_args()

    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()

    print(f"quarantine_outliers: fetching prices >{args.threshold}× player median (median > $5) …")
    rows = fetch_outliers(cur, args.threshold)
    print(f"  found {len(rows)} outlier(s)")

    if not rows:
        cur.close()
        conn.close()
        print("quarantine_outliers: nothing to do")
        return

    # Split into clear outliers (>clear_at×) and borderline (threshold – clear_at×)
    clear     = [r for r in rows if float(r["ratio"]) >= args.clear_at]
    borderline = [r for r in rows if float(r["ratio"]) < args.clear_at]

    print(f"  clear outliers (>={args.clear_at}×): {len(clear)}")
    print(f"  borderline ({args.threshold}–{args.clear_at}×): {len(borderline)}")

    to_quarantine = [r["id"] for r in clear]

    if args.ai and borderline:
        print(f"  [AI] asking Claude about {min(len(borderline), 100)} borderline case(s)…")
        ai_ids = claude_validate(borderline)
        confirmed = [r["id"] for r in borderline if r["id"] in ai_ids]
        print(f"  [AI] Claude flagged {len(confirmed)} borderline case(s) for quarantine")
        to_quarantine.extend(confirmed)

    count = quarantine(cur, to_quarantine, args.dry_run)

    if not args.dry_run:
        conn.commit()
        print(f"quarantine_outliers: quarantined {count} price(s)")
    else:
        conn.rollback()
        print(f"quarantine_outliers: dry-run complete, would quarantine {count} price(s)")

    # Print top 20 for the log
    for r in rows[:20]:
        flag = "[CLEAR]" if float(r["ratio"]) >= args.clear_at else "[borderline]"
        print(f"  {flag} {r['player_name']} | {r['year']} {r['set_name']} #{r['card_number']}"
              f" | ${r['fair_value']:.2f} ({r['ratio']}× median ${r['median_val']:.2f})")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
