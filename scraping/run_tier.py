#!/usr/bin/env python3
"""
run_tier.py — Unified local launcher for tier scrape subprocesses.

Reads per-tier settings from tier_config.json and launches scrape_master_db.py
in parallel (one subprocess per sport × shard). Runs until ALL cards in the
tier are done. Checkpointing is built-in: cards with a recent scraped_at are
skipped on restart via the stale-days gate.

Usage:
    python scraping/run_tier.py staple
    python scraping/run_tier.py premium --sport NFL
    python scraping/run_tier.py base --dry-run
    python scraping/run_tier.py staple --limit 50    # smoke test

Logs are written to scraping/logs/<tier>_<sport>_<shard>of<total>.log
Tail a live log:  tail -f scraping/logs/staple_NFL_0of1.log
"""

import argparse
import json
import os
import subprocess
import sys
import time
import threading
from datetime import datetime
from pathlib import Path

SCRAPING_DIR = Path(__file__).parent.resolve()
CONFIG_PATH  = SCRAPING_DIR / "tier_config.json"
SCRAPER      = SCRAPING_DIR / "scrape_master_db.py"
LOGS_DIR     = SCRAPING_DIR / "logs"


def load_config(tier: str) -> dict:
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    if tier not in config:
        print(f"ERROR: Unknown tier '{tier}'. Valid: {list(config.keys())}", file=sys.stderr)
        sys.exit(1)
    return config[tier]


def build_jobs(tier: str, cfg: dict, sport_filter: str | None, limit: int,
               backfill: bool = False, this_shard: int | None = None) -> list[dict]:
    sports      = [sport_filter.upper()] if sport_filter else cfg["sports"]
    shard_count = cfg["shard_count"]
    mode        = "backfill" if backfill else "raw"
    # If --this-shard is set, only run that one shard index (multi-server mode).
    shard_indexes = [this_shard] if this_shard is not None else range(shard_count)
    jobs = []

    for sport in sports:
        for shard_index in shard_indexes:
            cmd = [
                sys.executable, "-u", str(SCRAPER),
                "--catalog-tier", tier,
                "--sport",        sport,
                "--workers",      str(cfg["workers"]),
                "--shard-index",  str(shard_index),
                "--shard-count",  str(shard_count),
                "--max-hours",    "0",   # no time limit — run until all cards done
            ]
            if backfill:
                cmd += ["--backfill"]
            else:
                cmd += ["--stale-days", str(cfg["stale_days"])]
            if cfg.get("year_from"):
                cmd += ["--year-from", str(cfg["year_from"])]
            if limit:
                cmd += ["--limit", str(limit)]

            shard_label = f"{shard_index}of{shard_count}"
            log_path    = LOGS_DIR / f"{tier}_{sport}_{shard_label}_{mode}.log"
            jobs.append({
                "label":       f"{sport} {mode} shard {shard_label}",
                "sport":       sport,
                "shard_index": shard_index,
                "shard_count": shard_count,
                "cmd":         cmd,
                "log_path":    log_path,
            })
    return jobs


def print_dry_run(jobs: list[dict]) -> None:
    print(f"DRY RUN — {len(jobs)} subprocess(es) would be launched:\n")
    for j in jobs:
        print(f"  [{j['label']}]")
        print(f"    {' '.join(j['cmd'])}")
        print(f"    log -> {j['log_path']}")
        print()
    sys.exit(0)


def _stream_output(job: dict) -> None:
    """Read subprocess stdout line-by-line, print to terminal and write to log."""
    label  = job["label"]
    log    = job["log_handle"]
    prefix = f"[{label}] " if job["_multi"] else ""
    stdout = open(sys.stdout.fileno(), mode="wb", closefd=False)
    for raw in job["proc"].stdout:
        line = raw.decode("utf-8", errors="replace").rstrip()
        log.write(line + "\n")
        log.flush()
        out = (prefix + line + "\n").encode("utf-8", errors="replace")
        stdout.write(out)
        stdout.flush()


def launch_all(jobs: list[dict], stream: bool = False) -> list[dict]:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    env   = os.environ.copy()
    multi = len(jobs) > 1

    for j in jobs:
        j["_multi"]     = multi
        j["log_handle"] = open(j["log_path"], "w", buffering=1, encoding="utf-8")
        if stream:
            j["proc"] = subprocess.Popen(
                j["cmd"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
            )
            t = threading.Thread(target=_stream_output, args=(j,), daemon=True)
            t.start()
            j["_stream_thread"] = t
        else:
            j["proc"] = subprocess.Popen(
                j["cmd"],
                stdout=j["log_handle"],
                stderr=subprocess.STDOUT,
                env=env,
            )
        print(f"  [{j['label']:24s}]  pid={j['proc'].pid}  log={j['log_path'].name}")

    return jobs


def monitor(jobs: list[dict], interval: int = 30, stream: bool = False) -> None:
    start = time.time()
    while True:
        running = [j for j in jobs if j["proc"].poll() is None]
        elapsed = (time.time() - start) / 60
        ts      = datetime.now().strftime("%H:%M:%S")

        if not running:
            # Wait for stream threads to drain before printing summary
            for j in jobs:
                t = j.get("_stream_thread")
                if t:
                    t.join(timeout=5)
            print(f"\n[{ts}] All {len(jobs)} subprocesses finished ({elapsed:.1f}m elapsed)")
            break

        if not stream:
            labels = ", ".join(j["label"] for j in running)
            print(f"[{ts}]  {len(running)}/{len(jobs)} running  {elapsed:.1f}m  —  {labels}", flush=True)
        time.sleep(interval)


def print_summary(jobs: list[dict]) -> int:
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    any_failed = False
    for j in jobs:
        rc = j["proc"].returncode
        try:
            j["log_handle"].close()
        except Exception:
            pass
        status = "OK" if rc == 0 else f"FAILED (exit {rc})"
        print(f"  [{j['label']:24s}]  {status}")
        print(f"    log: {j['log_path']}")
        if rc != 0:
            any_failed = True
    print(f"{'='*60}")
    return 1 if any_failed else 0


def main():
    parser = argparse.ArgumentParser(
        description="Launch scrape_master_db.py subprocesses for one tier until done."
    )
    parser.add_argument("tier",
                        help="Tier to scrape: staple | premium | stars | base")
    parser.add_argument("--sport", default=None,
                        help="Restrict to one sport (NHL|NBA|NFL|MLB). Default: all.")
    parser.add_argument("--backfill", action="store_true",
                        help="Run in backfill mode: capture full 90-day raw sales history "
                             "for cards with no market_raw_sales rows. Does not overwrite prices.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print commands without launching anything.")
    parser.add_argument("--limit", type=int, default=0,
                        help="Forward --limit N to each subprocess (0=all). For smoke tests.")
    parser.add_argument("--stream", action="store_true",
                        help="Print subprocess output live to terminal (teed to log). "
                             "Best for single-subprocess runs; with multiple shards output interleaves.")
    parser.add_argument("--workers", type=int, default=None,
                        help="Override workers from tier_config.json (e.g. --workers 25 on a server).")
    parser.add_argument("--shards", type=int, default=None,
                        help="Override shard_count from tier_config.json (e.g. --shards 3 for 3-server setup).")
    parser.add_argument("--this-shard", type=int, default=None, dest="this_shard",
                        help="Run only this shard index (0-based). Used in multi-server mode: "
                             "each server sets --shards N --this-shard <its index>.")
    args = parser.parse_args()

    cfg  = load_config(args.tier)
    if args.workers is not None:
        cfg["workers"] = args.workers
    if args.shards is not None:
        cfg["shard_count"] = args.shards
    jobs = build_jobs(args.tier, cfg, args.sport, args.limit,
                      backfill=args.backfill, this_shard=args.this_shard)

    sports_in_run = [args.sport.upper()] if args.sport else cfg["sports"]
    n_procs = len(jobs)
    mode_label = "BACKFILL (90-day history capture)" if args.backfill else "RAW (prices + recent sales)"
    print(f"\nTier:      {args.tier}")
    print(f"Mode:      {mode_label}")
    print(f"Sports:    {', '.join(sports_in_run)}")
    if args.this_shard is not None:
        print(f"Shards:    this server = shard {args.this_shard} of {cfg['shard_count']}")
    else:
        print(f"Shards:    {cfg['shard_count']} per sport  ({n_procs} total subprocesses)")
    print(f"Workers:   {cfg['workers']} per subprocess")
    if not args.backfill:
        print(f"Stale:     {cfg['stale_days']}d")
    if cfg.get("year_from"):
        print(f"Year from: {cfg['year_from']}")
    print(f"Logs dir:  {LOGS_DIR}")
    print()

    if args.dry_run:
        print_dry_run(jobs)

    jobs = launch_all(jobs, stream=args.stream)
    if not args.stream:
        print(f"\nAll {n_procs} subprocess(es) launched. Monitoring every 30s...\n")
    monitor(jobs, stream=args.stream)
    rc = print_summary(jobs)
    sys.exit(rc)


if __name__ == "__main__":
    main()
