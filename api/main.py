"""FastAPI backend for the Card Dashboard React frontend.

Run from the project root (d:/sportscarddb/cardDB):
    uvicorn api.main:app --reload --port 8000

All dashboard_utils helpers are imported directly from the root so no
data logic is duplicated.
"""

import sys
import os
import math
import time
import threading
from collections import defaultdict, deque

# Make root project importable from api/
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Load .env from project root for local dev (no-op if file doesn't exist)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass

import pathlib
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse


class RateLimitMiddleware:
    """Simple sliding-window rate limiter for public catalog endpoints.

    Limits per IP:
      - /api/catalog/ai-search  → 10 requests / 60 s
      - /api/catalog/*          → 120 requests / 60 s
    Admin and auth routes are never rate-limited.
    """

    _AI_LIMIT     = 10
    _PUBLIC_LIMIT = 120
    _WINDOW       = 60  # seconds

    def __init__(self, app):
        self.app = app
        self._buckets: dict[str, deque] = defaultdict(deque)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not (path.startswith("/api/catalog") or path.startswith("/api/search")):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        ip = (request.client.host if request.client else "unknown")
        limit = self._AI_LIMIT if path == "/api/catalog/ai-search" else self._PUBLIC_LIMIT

        now = time.monotonic()
        bucket = self._buckets[f"{ip}|{limit}"]
        while bucket and bucket[0] < now - self._WINDOW:
            bucket.popleft()

        if len(bucket) >= limit:
            response = JSONResponse(
                {"detail": "Rate limit exceeded — please slow down."},
                status_code=429,
                headers={"Retry-After": str(self._WINDOW)},
            )
            await response(scope, receive, send)
            return

        bucket.append(now)
        await self.app(scope, receive, send)

from api.routers import cards, master_db, stats, auth, scan, admin, catalog, collection, search, ai, ebay
from db import get_db
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Progress report emails disabled — running local backfill overnight.
    # Re-enable by restoring: scheduler.add_job(_progress_run, "cron", minute="0,15,30,45")
    yield


app = FastAPI(title="Card Dashboard API", version="0.1.0", lifespan=lifespan)

app.add_middleware(RateLimitMiddleware)

# CORS: allow Vite dev server in development + production domains
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",              # Vite dev server
        "http://localhost:4173",              # Vite preview
        "https://southwestsportscards.ca",    # custom domain
        "https://*.up.railway.app",           # Railway deployment
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,      prefix="/api/auth",      tags=["auth"])
app.include_router(cards.router,     prefix="/api/cards",     tags=["cards"])
app.include_router(master_db.router, prefix="/api/master-db", tags=["master-db"])
app.include_router(stats.router,     prefix="/api/stats",     tags=["stats"])
app.include_router(scan.router,      prefix="/api/scan",      tags=["scan"])
app.include_router(admin.router,     prefix="/api/admin",     tags=["admin"])
app.include_router(catalog.router,     prefix="/api/catalog",     tags=["catalog"])
app.include_router(collection.router,  prefix="/api/collection",  tags=["collection"])
app.include_router(search.router,      prefix="/api/search",      tags=["search"])
app.include_router(ai.router,          prefix="/api/ai",           tags=["ai"])
app.include_router(ebay.router,        prefix="/api/ebay",          tags=["ebay"])


@app.get("/api/health")
def health():
    db_ok = False
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        db_ok = True
    except Exception:
        pass
    return {"status": "ok" if db_ok else "degraded", "db": db_ok}


# ── SEO: robots.txt + sitemap.xml ─────────────────────────────────────────────
SITE_URL = os.environ.get("SITE_URL", "https://southwestsportscards.ca")

@app.get("/robots.txt", response_class=PlainTextResponse)
def robots_txt():
    return f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n"

_SITEMAP_PAGE_SIZE = 45000  # well under Google's 50K limit per file

# In-memory sitemap ID cache — loaded once, shared across all shard requests.
# Avoids 14 simultaneous DB queries when Google fetches all shards at once.
_sitemap_ids: list = []
_sitemap_ids_loaded = False
_sitemap_lock = threading.Lock()

def _load_sitemap_ids():
    """Load all priced card IDs into memory (called once, ~2MB for 676K ints)."""
    global _sitemap_ids, _sitemap_ids_loaded
    with _sitemap_lock:
        if _sitemap_ids_loaded:
            return
        try:
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("SET statement_timeout = '20s'")
                    cur.execute("""
                        SELECT card_catalog_id FROM market_prices
                        WHERE fair_value > 0
                        ORDER BY card_catalog_id
                    """)
                    _sitemap_ids = [row[0] for row in cur.fetchall()]
            _sitemap_ids_loaded = True
        except Exception:
            _sitemap_ids = []


@app.get("/sitemap.xml")
def sitemap_index():
    """Sitemap index — points to sitemap-static.xml + sitemap-cards-N.xml shards."""
    from fastapi.responses import Response as FastAPIResponse
    _load_sitemap_ids()
    num_shards = max(1, math.ceil(len(_sitemap_ids) / _SITEMAP_PAGE_SIZE))
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        f'  <sitemap><loc>{SITE_URL}/sitemap-static.xml</loc></sitemap>',
    ]
    for i in range(num_shards):
        parts.append(f'  <sitemap><loc>{SITE_URL}/sitemap-cards-{i}.xml</loc></sitemap>')
    parts.append('</sitemapindex>')
    return FastAPIResponse('\n'.join(parts), media_type='application/xml')


@app.get("/sitemap-static.xml")
def sitemap_static():
    """Sitemap for main site pages."""
    from fastapi.responses import Response as FastAPIResponse
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        f'  <url><loc>{SITE_URL}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>',
        f'  <url><loc>{SITE_URL}/catalog</loc><changefreq>daily</changefreq><priority>0.9</priority></url>',
        f'  <url><loc>{SITE_URL}/trending</loc><changefreq>daily</changefreq><priority>0.8</priority></url>',
        f'  <url><loc>{SITE_URL}/sets</loc><changefreq>weekly</changefreq><priority>0.7</priority></url>',
        f'  <url><loc>{SITE_URL}/releases</loc><changefreq>weekly</changefreq><priority>0.6</priority></url>',
        '</urlset>',
    ]
    return FastAPIResponse('\n'.join(parts), media_type='application/xml')


@app.get("/sitemap-cards-{shard}.xml")
def sitemap_cards(shard: int):
    """Sitemap shard for card detail pages — served from in-memory cache."""
    from fastapi.responses import Response as FastAPIResponse
    _load_sitemap_ids()
    start = shard * _SITEMAP_PAGE_SIZE
    ids = _sitemap_ids[start: start + _SITEMAP_PAGE_SIZE]
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for cid in ids:
        parts.append(f'  <url><loc>{SITE_URL}/catalog/{cid}</loc><changefreq>weekly</changefreq><priority>0.6</priority></url>')
    parts.append('</urlset>')
    return FastAPIResponse('\n'.join(parts), media_type='application/xml')


# Serve React frontend for all non-API routes (SPA support)
_dist = pathlib.Path(__file__).parent.parent / "frontend" / "dist"
if _dist.exists():
    # Serve /assets/* and other static files directly
    app.mount("/assets", StaticFiles(directory=str(_dist / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        """Serve index.html for all non-API routes so React Router handles navigation."""
        file = _dist / full_path
        if file.is_file():
            return FileResponse(str(file))
        return FileResponse(str(_dist / "index.html"))
