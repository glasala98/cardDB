"""
Sales Data Quality Analysis — Variant Mismatch Detection

Scans market_raw_sales and flags listings whose eBay title contains keywords
that suggest they belong to a DIFFERENT (superset) variant than the card they
are filed under.

Example: card is "O-Pee-Chee Rainbow" → title contains "Colour Wheel"
→ flagged as mismatch because "Colour Wheel" indicates a more specific parallel.

Outputs:
  - sales_quality_report.csv  — every flagged sale with card name + title
  - sales_quality_summary.csv — per-card mismatch counts + rates

Usage:
  python analyze_sales_quality.py
  python analyze_sales_quality.py --tier staple
  python analyze_sales_quality.py --sport NHL
  python analyze_sales_quality.py --min-sales 5   # only cards with ≥5 stored sales
  python analyze_sales_quality.py --sample 200    # random sample of cards to check
"""

import os
import re
import csv
import argparse
import random
from collections import defaultdict
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]

# ── Superset variant keywords ──────────────────────────────────────────────────
# If a card's name does NOT contain these words but a stored sale title DOES,
# it's likely a wrong-variant match.
#
# Format: (trigger_word, conflicting_words)
# e.g. card is "Rainbow" → reject titles that also say "Colour Wheel"
#      card is "Gold"    → reject titles that say "Gold Vinyl" or "Gold Wave"
#
SUPERSET_CONFLICTS = [
    # O-Pee-Chee / Upper Deck parallels
    ("rainbow",         ["colour wheel", "color wheel"]),
    ("gold",            ["gold vinyl", "gold wave", "gold shimmer", "gold disco"]),
    ("red",             ["red wave", "red shimmer", "red disco", "red vinyl"]),
    ("blue",            ["blue wave", "blue shimmer", "blue disco", "blue vinyl"]),
    ("silver",          ["silver wave", "silver shimmer", "silver disco"]),
    ("black",           ["black wave", "black shimmer", "black disco"]),
    ("purple",          ["purple wave", "purple shimmer", "purple disco"]),
    ("green",           ["green wave", "green shimmer", "green disco"]),
    ("orange",          ["orange wave", "orange shimmer", "orange disco"]),

    # Prizm parallels
    ("prizm",           ["prizm hyper", "prizm disco", "prizm choice", "prizm draft"]),
    ("silver prizm",    ["red white blue prizm", "blue prizm", "red prizm", "gold prizm"]),

    # Chrome parallels
    ("refractor",       ["atomic refractor", "superfractor", "gold refractor",
                         "red refractor", "blue refractor", "orange refractor",
                         "prism refractor", "xfractor"]),

    # Generic subset bleed
    ("auto",            ["rpa", "patch auto", "auto patch"]),
    ("patch",           ["logoman", "laundry tag", "nameplate"]),
]

# Build a fast lookup: for each trigger word → list of conflicting phrases
_CONFLICT_MAP: dict[str, list[str]] = defaultdict(list)
for trigger, conflicts in SUPERSET_CONFLICTS:
    _CONFLICT_MAP[trigger.lower()].extend([c.lower() for c in conflicts])


def _card_tokens(name: str) -> set[str]:
    """Lowercase word tokens from a card name."""
    return set(re.findall(r"[a-z]+", name.lower()))


def _title_has_conflict(card_name: str, title: str) -> list[str]:
    """
    Returns a list of conflict descriptions if the title looks like a
    superset/different variant.  Empty list = no issue detected.
    """
    card_lower = card_name.lower()
    title_lower = title.lower()
    issues = []

    for trigger, conflicts in _CONFLICT_MAP.items():
        # Only apply this rule if the card name contains the trigger word
        if trigger not in card_lower:
            continue
        for conflict_phrase in conflicts:
            # If the title contains the conflict phrase but the card name doesn't
            if conflict_phrase in title_lower and conflict_phrase not in card_lower:
                issues.append(f"title has '{conflict_phrase}' but card is '{trigger}' only")

    return issues


def fetch_cards(conn, args) -> list[dict]:
    cur = conn.cursor()
    conditions = ["1=1"]
    params = []

    if args.tier:
        conditions.append("cc.scrape_tier = %s")
        params.append(args.tier)
    if args.sport:
        conditions.append("cc.sport = %s")
        params.append(args.sport.upper())

    where = " AND ".join(conditions)
    cur.execute(f"""
        SELECT cc.id,
               cc.sport,
               cc.year,
               cc.brand,
               cc.set_name,
               cc.player_name,
               cc.variant,
               cc.scrape_tier,
               COUNT(mrs.id) AS sale_count
        FROM card_catalog cc
        JOIN market_raw_sales mrs ON mrs.card_catalog_id = cc.id
        WHERE {where}
        GROUP BY cc.id, cc.sport, cc.year, cc.brand, cc.set_name,
                 cc.player_name, cc.variant, cc.scrape_tier
        HAVING COUNT(mrs.id) >= %s
        ORDER BY sale_count DESC
    """, params + [args.min_sales])

    cols = [d[0] for d in cur.description]
    cards = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()

    if args.sample and args.sample < len(cards):
        random.shuffle(cards)
        cards = cards[:args.sample]
        print(f"  Sampling {args.sample} cards from {len(cards) + args.sample} total")

    return cards


def fetch_titles(conn, card_id: int) -> list[str]:
    cur = conn.cursor()
    cur.execute(
        "SELECT title FROM market_raw_sales WHERE card_catalog_id = %s AND title IS NOT NULL",
        [card_id]
    )
    titles = [r[0] for r in cur.fetchall()]
    cur.close()
    return titles


def build_card_display(card: dict) -> str:
    parts = [str(card["year"]), card["brand"], card["set_name"]]
    if card.get("variant"):
        parts.append(card["variant"])
    parts.append(f"#{card.get('player_name','?')}")
    return " - ".join(parts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tier",       default=None, help="Filter by scrape_tier")
    parser.add_argument("--sport",      default=None, help="Filter by sport")
    parser.add_argument("--min-sales",  type=int, default=3,
                        help="Only analyse cards with at least N stored sales (default: 3)")
    parser.add_argument("--sample",     type=int, default=None,
                        help="Random sample N cards (default: all)")
    args = parser.parse_args()

    conn = psycopg2.connect(DATABASE_URL)

    print("Fetching cards to analyse...")
    cards = fetch_cards(conn, args)
    print(f"  {len(cards)} cards selected")

    flagged_sales   = []   # individual mismatch rows
    card_summary    = []   # per-card summary

    for i, card in enumerate(cards, 1):
        card_name = build_card_display(card)
        titles    = fetch_titles(conn, card["id"])
        if not titles:
            continue

        issues_for_card = []
        for title in titles:
            conflicts = _title_has_conflict(card_name, title)
            for conflict in conflicts:
                flagged_sales.append({
                    "card_id":    card["id"],
                    "sport":      card["sport"],
                    "tier":       card["scrape_tier"],
                    "card_name":  card_name,
                    "title":      title,
                    "issue":      conflict,
                })
                issues_for_card.append(conflict)

        mismatch_count = len(issues_for_card)
        mismatch_rate  = round(mismatch_count / len(titles) * 100, 1) if titles else 0

        if mismatch_count > 0:
            card_summary.append({
                "card_id":       card["id"],
                "sport":         card["sport"],
                "tier":          card["scrape_tier"],
                "card_name":     card_name,
                "total_sales":   len(titles),
                "mismatch_count": mismatch_count,
                "mismatch_rate":  mismatch_rate,
                "issues":        "; ".join(set(issues_for_card)),
            })

        if i % 100 == 0:
            print(f"  {i}/{len(cards)} cards checked — {len(flagged_sales)} issues so far")

    conn.close()

    # ── Write CSV reports ──────────────────────────────────────────────────────
    report_file  = "sales_quality_report.csv"
    summary_file = "sales_quality_summary.csv"

    with open(report_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["card_id","sport","tier","card_name","title","issue"])
        writer.writeheader()
        writer.writerows(flagged_sales)

    card_summary.sort(key=lambda x: x["mismatch_rate"], reverse=True)
    with open(summary_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "card_id","sport","tier","card_name","total_sales","mismatch_count","mismatch_rate","issues"
        ])
        writer.writeheader()
        writer.writerows(card_summary)

    # ── Print summary ──────────────────────────────────────────────────────────
    total_titles   = sum(c["total_sales"]   for c in card_summary) if card_summary else 0
    total_flags    = sum(c["mismatch_count"] for c in card_summary) if card_summary else 0
    cards_affected = len(card_summary)
    overall_rate   = round(total_flags / total_titles * 100, 2) if total_titles else 0

    print("\n" + "="*60)
    print("SALES QUALITY REPORT")
    print("="*60)
    print(f"  Cards analysed:    {len(cards):,}")
    print(f"  Cards with issues: {cards_affected:,}")
    print(f"  Total mismatches:  {total_flags:,}")
    print(f"  Overall flag rate: {overall_rate}%")
    print()
    if card_summary:
        print("Top 10 worst cards by mismatch rate:")
        for c in card_summary[:10]:
            print(f"  [{c['mismatch_rate']}%] {c['card_name']}  ({c['mismatch_count']}/{c['total_sales']} sales)")
    print()
    print(f"  Detailed report:  {report_file}")
    print(f"  Card summary:     {summary_file}")
    print("="*60)


if __name__ == "__main__":
    main()
