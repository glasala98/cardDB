"""Progress report emailer — runs as a Railway background scheduler.

Called every 15 minutes by APScheduler in api/main.py.
Sends email only at meaningful moments (first hour of scrape, noon digest, milestones).
"""
import os
import math
import smtplib
import hashlib
import psycopg2
from datetime import datetime, timezone, date, timedelta
from email.mime.text import MIMEText

BACKFILL_START = date(2026, 3, 22)
TARGET_DAILY   = 270_000   # updated: 24 shards × 4 runs
MILESTONES     = [(25, "25%"), (50, "50%"), (75, "75%"), (90, "90%"), (100, "100%")]

BASE_TARGET = {"NFL": 479_793, "NBA": 298_550, "MLB": 765_186}
TOTAL_BASE_TARGET = sum(BASE_TARGET.values())


def _send_email(subject: str, body: str):
    gmail_user = os.environ.get("NOTIFY_GMAIL_USER")
    gmail_pass = os.environ.get("NOTIFY_GMAIL_APP_PASSWORD")
    to_addr    = os.environ.get("NOTIFY_EMAIL_TO")
    if not all([gmail_user, gmail_pass, to_addr]):
        print("[progress_report] email env vars not set — skipping send")
        return
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"]    = f"CardDB Monitor <{gmail_user}>"
    msg["To"]      = to_addr
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(gmail_user, gmail_pass)
        s.sendmail(gmail_user, [to_addr], msg.as_string())
    print(f"[progress_report] email sent: {subject}")


def run():
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur  = conn.cursor()
        cur.execute("""
            SELECT
              (SELECT reltuples::bigint FROM pg_class WHERE relname = 'card_catalog'),
              (SELECT reltuples::bigint FROM pg_class WHERE relname = 'market_prices'),
              (SELECT reltuples::bigint FROM pg_class WHERE relname = 'market_raw_sales'),
              pg_size_pretty(pg_database_size(current_database()))
        """)
        total_catalog, total_priced, sales_total, db_size = cur.fetchone()
        cur.close(); conn.close()
    except Exception as e:
        print(f"[progress_report] DB error: {e}")
        return

    base_share        = TOTAL_BASE_TARGET / max(total_catalog, 1)
    total_base_priced = int(total_priced * base_share)

    today        = date.today()
    days_elapsed = max((today - BACKFILL_START).days, 1)
    actual_daily = total_base_priced / days_elapsed
    remaining    = TOTAL_BASE_TARGET - total_base_priced
    expected     = min(TOTAL_BASE_TARGET, days_elapsed * TARGET_DAILY)
    delta        = total_base_priced - expected
    delta_pct    = delta / TOTAL_BASE_TARGET * 100
    base_pct     = total_base_priced / TOTAL_BASE_TARGET * 100
    overall_pct  = total_priced / max(total_catalog, 1) * 100

    if actual_daily > 0:
        eta_str = (today + timedelta(days=math.ceil(remaining / actual_daily))).strftime("%b %d, %Y")
    else:
        eta_str = "unknown"

    pace_emoji = "✅" if delta >= 0 else "⚠️"
    pace_label = f"{'+' if delta >= 0 else ''}{delta:,} {'ahead' if delta >= 0 else 'behind'} of schedule ({delta_pct:+.1f}%)"

    # Milestone table
    ms_lines = ["Milestone schedule (NFL/NBA/MLB 2015+):",
                f"  {'Goal':>6}  {'Target date':>12}  {'Cards needed':>13}  Status"]
    for ms_pct, ms_label in MILESTONES:
        ms_cards = TOTAL_BASE_TARGET * ms_pct / 100
        ms_day   = BACKFILL_START + timedelta(days=math.ceil(ms_cards / TARGET_DAILY))
        if total_base_priced >= ms_cards:
            status = "✓ Done"
        elif today > ms_day:
            status = f"⚠ {ms_cards - total_base_priced:,.0f} short"
        else:
            status = f"in {(ms_day - today).days}d"
        ms_lines.append(f"  {ms_label:>6}  {ms_day.strftime('%b %d, %Y'):>12}  {ms_cards:>13,.0f}  {status}")

    now_str = datetime.now(timezone.utc).strftime("%b %d %Y at %H:%M UTC")
    body = f"""CardDB Backfill Progress — {now_str}
{"=" * 60}

PACE  {pace_emoji}  {pace_label}
      Actual rate:   {actual_daily:,.0f} cards/day
      Target rate:   {TARGET_DAILY:,} cards/day
      Projected ETA: {eta_str}

ACTIVE BACKFILL — Base tier NFL/NBA/MLB 2015+
  Total priced: {total_base_priced:,} / {TOTAL_BASE_TARGET:,}  ({base_pct:.1f}%)
  Day {days_elapsed} of backfill — expected {expected:,} by now

{chr(10).join(ms_lines)}

{"─" * 60}
Overall catalog: {total_priced:,} / {total_catalog:,}  ({overall_pct:.1f}%)
Raw sales:       {sales_total:,}
DB size:         {db_size}
"""
    subject = f"CardDB — {base_pct:.1f}% base priced | {pace_emoji} {pace_label[:35]}"

    # Smart send: first hour of scrape (0/6/12/18 UTC), noon digest, milestones
    now_utc = datetime.now(timezone.utc)
    h, m    = now_utc.hour, now_utc.minute
    scrape_hours  = {0, 6, 12, 18}
    is_first_hour = h in scrape_hours or (h % 6 == 1 and m < 15)
    is_noon       = (h == 12 and m < 20)

    milestone_crossed = False
    for ms_pct, ms_label in MILESTONES:
        ms_cards = TOTAL_BASE_TARGET * ms_pct / 100
        if total_base_priced >= ms_cards and (total_base_priced - ms_cards) < TARGET_DAILY:
            milestone_crossed = True
            subject = f"🎯 CardDB — {ms_label} base tier reached! | ETA {eta_str}"
            break

    if is_first_hour or is_noon or milestone_crossed:
        _send_email(subject, body)
    else:
        print(f"[progress_report] skipping send (not first hour/noon/milestone) — {base_pct:.1f}% priced")
