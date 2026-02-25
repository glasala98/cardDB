"""FastAPI backend for the Card Dashboard React frontend.

Run from the project root (d:/sportscarddb/cardDB):
    uvicorn api.main:app --reload --port 8000

All dashboard_utils helpers are imported directly from the root so no
data logic is duplicated.
"""

import sys
import os

# Make root project importable from api/
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import cards, master_db, stats

app = FastAPI(title="Card Dashboard API", version="0.1.0")

# CORS: allow Vite dev server in development; update for production domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",      # Vite dev server
        "http://localhost:4173",      # Vite preview
        "https://southwestsportscards.ca",  # production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cards.router,     prefix="/api/cards",     tags=["cards"])
app.include_router(master_db.router, prefix="/api/master-db", tags=["master-db"])
app.include_router(stats.router,     prefix="/api/stats",     tags=["stats"])


@app.get("/api/health")
def health():
    return {"status": "ok"}
