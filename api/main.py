"""FastAPI backend for the Card Dashboard React frontend.

Run from the project root (d:/sportscarddb/cardDB):
    uvicorn api.main:app --reload --port 8000

All dashboard_utils helpers are imported directly from the root so no
data logic is duplicated.
"""

import sys
import os
import time
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
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse


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
        if not path.startswith("/api/catalog"):
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

from api.routers import cards, master_db, stats, auth, scan, admin, catalog, collection
from db import get_db

app = FastAPI(title="Card Dashboard API", version="0.1.0")

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
