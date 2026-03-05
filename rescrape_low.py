"""Re-scrape all low-confidence cards and update batch_price_output.csv.
Keeps the old result if the new one is no better.
"""
import csv, re
from concurrent.futures import ThreadPoolExecutor, as_completed
from scrape_card_prices import process_card, NUM_WORKERS

CONF_RANK = {"high": 4, "medium": 3, "low": 2, "estimated": 1, "none": 0, "error": -1, "manual": 5}

def parse_price(val):
    if not val: return None
    m = re.search(r"[\d.]+", str(val).replace(",", ""))
    return float(m.group()) if m else None

# Load CSV
rows = []
with open("batch_price_output.csv", encoding="utf-8", newline="") as f:
    rows = list(csv.DictReader(f))
fieldnames = list(rows[0].keys())

# Unique low-conf cards
low_cards = list(dict.fromkeys(
    r["Card Name"] for r in rows if r.get("Confidence", "").lower() == "low"
))
print(f"Re-scraping {len(low_cards)} low-confidence cards "
      f"(up to {min(NUM_WORKERS, len(low_cards))} parallel workers)\n{'='*70}")

new_results = {}
completed = 0
total = len(low_cards)

with ThreadPoolExecutor(max_workers=min(NUM_WORKERS, total)) as executor:
    futures = {executor.submit(process_card, card): card for card in low_cards}
    for future in as_completed(futures):
        card = futures[future]
        completed += 1
        try:
            name, result = future.result()
            new_results[name] = result
            stats = result.get("stats", {})
            print(f"[{completed}/{total}] {name[:65]}")
            print(f"         → {result.get('estimated_value')} | "
                  f"conf: {result.get('confidence')} | "
                  f"sales: {stats.get('num_sales', 0)}")
        except Exception as e:
            new_results[card] = None
            print(f"[{completed}/{total}] ERROR: {card[:65]} — {e}")

# Update CSV — only replace if new confidence is strictly better
improved, kept, worsened = [], [], []
for row in rows:
    if row.get("Confidence", "").lower() != "low":
        continue
    name   = row["Card Name"]
    nr     = new_results.get(name)
    if nr is None:
        kept.append((name, "error on retry"))
        continue

    old_conf  = row.get("Confidence", "low").lower()
    new_conf  = nr.get("confidence", "low") or "low"
    new_price = nr.get("estimated_value")
    new_stats = nr.get("stats", {})
    new_sales = new_stats.get("num_sales", 0)
    old_price = row.get("Fair Value", "")

    if CONF_RANK.get(new_conf, 0) > CONF_RANK.get(old_conf, 0):
        # Improved — update
        row["Fair Value"]   = new_price or old_price
        row["Confidence"]   = new_conf
        row["Num Sales"]    = new_sales
        row["Top 3 Prices"] = " | ".join(new_stats.get("top_3_prices", []))
        row["Min"]          = f"${new_stats['min']}" if new_stats.get("min") else ""
        row["Max"]          = f"${new_stats['max']}" if new_stats.get("max") else ""
        row["Median"]       = f"${new_stats['median']}" if new_stats.get("median") else ""
        improved.append((name, old_conf, old_price, new_conf, new_price))
    elif CONF_RANK.get(new_conf, 0) < CONF_RANK.get(old_conf, 0):
        kept.append((name, f"new was worse ({new_conf})"))
        worsened.append((name, old_conf, old_price, new_conf, new_price))
    else:
        # Same confidence — update price/sales if new has more sales
        old_sales = int(row.get("Num Sales", 0) or 0)
        if new_sales > old_sales and new_price:
            row["Fair Value"]   = new_price
            row["Num Sales"]    = new_sales
            row["Top 3 Prices"] = " | ".join(new_stats.get("top_3_prices", []))
            row["Min"]          = f"${new_stats['min']}" if new_stats.get("min") else ""
            row["Max"]          = f"${new_stats['max']}" if new_stats.get("max") else ""
            row["Median"]       = f"${new_stats['median']}" if new_stats.get("median") else ""
            kept.append((name, f"same conf but more sales ({old_sales}→{new_sales}), price updated"))
        else:
            kept.append((name, f"same/less data — original kept"))

with open("batch_price_output.csv", "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

# Summary
print(f"\n{'='*70}")
print(f"IMPROVED ({len(improved)} cards — confidence went up):")
for name, oc, op, nc, np_ in improved:
    print(f"  {oc:8s} → {nc:8s}  {op:>10} → {np_:>10}  {name[:60]}")

print(f"\nSTILL LOW / KEPT ({len(kept)} cards):")
for name, reason in kept:
    print(f"  {reason:45s}  {name[:55]}")

if worsened:
    print(f"\nNOTE — new scrape was worse for {len(worsened)} (originals kept):")
    for name, oc, op, nc, np_ in worsened:
        print(f"  {oc} → {nc}  {name[:60]}")

# Recalculate grand total
total_v = 0.0
for row in rows:
    p = parse_price(row.get("Fair Value", ""))
    if p:
        total_v += p
print(f"\nUpdated Grand Total: ${total_v:,.2f} USD")
