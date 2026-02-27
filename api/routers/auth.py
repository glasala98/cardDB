"""Auth endpoints — login, session check, logout."""

import os
import jwt
import datetime
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from dashboard_utils import verify_password, load_users

router = APIRouter()
bearer = HTTPBearer(auto_error=False)

# Secret key — override via JWT_SECRET env var in production
JWT_SECRET    = os.environ.get("JWT_SECRET", "dev-secret-change-in-prod")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_H  = 24  # hours


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_token(username: str) -> str:
    payload = {
        "sub": username,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=JWT_EXPIRY_H),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_token(token: str) -> str | None:
    """Decode and verify token. Returns username or None."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> str:
    """FastAPI dependency — extracts and validates the Bearer token."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    username = _decode_token(credentials.credentials)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return username


# ── Request bodies ────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/login")
def login(body: LoginRequest):
    """Verify credentials and return a JWT token."""
    users = load_users()

    # Dev fallback: if no users.yaml exists, accept admin / admin
    if not users:
        if body.username == "admin" and body.password == "admin":
            return {"token": _make_token("admin"), "username": "admin"}
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(body.username, body.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return {"token": _make_token(body.username), "username": body.username}


@router.get("/me")
def me(username: str = Depends(get_current_user)):
    """Return the currently authenticated user."""
    users = load_users()
    user_data = users.get(username, {}) if users else {}
    default_role = "admin" if username == "admin" else "user"
    return {
        "username":    username,
        "display_name": user_data.get("display_name", username),
        "role":        user_data.get("role", default_role),
    }


@router.post("/logout")
def logout():
    """Logout — client should discard the token."""
    return {"status": "logged out"}
