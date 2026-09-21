#!/usr/bin/env python3
"""Price the personal portfolio on a GitHub runner and push results to the site.

Why this exists: the site's own server cannot fetch eBay comps (HTML scraping
is 403-blocked from its IP; the Finding API is retired), and GitHub's runners
cannot reach the site's database. So this runs scrape_card_prices.process_card
here, where eBay answers, and POSTs the results to the site's admin API, which
writes them exactly as scraping/daily_scrape.py would have.

Env (GitHub secrets):
  CARDDB_URL       e.g. https://southwestsportscards.ca
  CARDDB_USER      admin username
  CARDDB_PASSWORD  that user's password
Usage:
  python scraping/portfolio_price_push.py --workers 3 [--limit N]
"""
import os, sys, json, time, argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "scraping"))
os.chdir(os.path.join(ROOT, "scraping"))
from scrape_card_prices import process_card   # curl_cffi path

BATCH = 10


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0, help="only the first N cards (testing)")
    ap.add_argument("--card", type=str, default="", help="price just this one card (the ledger's ⟳ button)")
    args = ap.parse_args()

    base = os.environ["CARDDB_URL"].rstrip("/")
    r = requests.post(f"{base}/api/auth/login",
                      json={"username": os.environ["CARDDB_USER"], "password": os.environ["CARDDB_PASSWORD"]},
                      timeout=30)
    r.raise_for_status()
    headers = {"Authorization": "Bearer " + r.json()["token"]}

    cards = requests.get(f"{base}/api/cards/price-jobs/cards", headers=headers, timeout=60).json()["cards"]
    if args.card:
        if args.card not in cards:
            print(f"card not in the ledger: {args.card!r}", flush=True); return 1
        cards = [args.card]
    elif args.limit:
        cards = cards[: args.limit]
    print(f"[{time.strftime('%H:%M:%S')}] pricing {len(cards)} cards with {args.workers} workers", flush=True)

    results, failed = [], 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(process_card, c): c for c in cards}
        for i, fut in enumerate(as_completed(futures), 1):
            card = futures[fut]
            try:
                _, res = fut.result()
                st = res.get("stats", {}) or {}
                results.append({
                    "card_name":    card,
                    "stats":        st,
                    "raw_sales":    res.get("raw_sales") or [],
                    "confidence":   st.get("confidence", "") or res.get("confidence", "") or "",
                    "is_estimated": bool(st.get("is_estimated", False)),
                    "price_source": st.get("price_source", "direct") or "direct",
                    "search_url":   res.get("search_url", "") or "",
                })
                print(f"  [{i}/{len(cards)}] {st.get('num_sales', 0):>3} sales  ${st.get('fair_price', 0):<8} {card[:70]}", flush=True)
            except Exception as e:
                failed += 1
                print(f"  [{i}/{len(cards)}] FAILED {card[:60]}: {type(e).__name__}: {str(e)[:80]}", flush=True)

    updated = 0
    for j in range(0, len(results), BATCH):
        chunk = results[j:j + BATCH]
        final = (j + BATCH) >= len(results)
        resp = requests.post(f"{base}/api/cards/price-jobs/import",
                             json={"cards": chunk, "finalize": final}, headers=headers, timeout=120)
        resp.raise_for_status()
        out = resp.json(); updated += out.get("updated", 0)
        if out.get("snapshot"):
            print("portfolio snapshot:", json.dumps(out["snapshot"]), flush=True)

    print(f"done: {len(results)} priced, {updated} updated with sales, {failed} failed", flush=True)
    return 1 if (failed and not results) else 0


if __name__ == "__main__":
    sys.exit(main())
