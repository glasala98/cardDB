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
    """Create a signed JWT for the given username, valid for JWT_EXPIRY_H hours.

    Args:
        username: The authenticated user's username to embed in the token subject.

    Returns:
        Encoded JWT string.
    """
    payload = {
        "sub": username,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=JWT_EXPIRY_H),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_token(token: str) -> str | None:
    """Decode and verify a JWT, returning the embedded username.

    Args:
        token: Encoded JWT string to decode.

    Returns:
        Username string extracted from the token subject claim, or None if the
        token is invalid, expired, or cannot be decoded.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> str:
    """FastAPI dependency — extract and validate the Bearer token from the request.

    Args:
        credentials: HTTP Authorization header credentials injected by FastAPI.

    Returns:
        The authenticated username embedded in the token.

    Raises:
        HTTPException: 401 if no credentials are provided or the token is invalid/expired.
    """
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
    """Verify credentials and return a signed JWT.

    In development (no users.yaml), accepts the hardcoded admin/admin fallback.
    In production, delegates to verify_password against the users.yaml store.

    Args:
        body: LoginRequest containing username and password.

    Returns:
        Dict with keys 'token' (JWT string) and 'username'.

    Raises:
        HTTPException: 401 if credentials are invalid.
    """
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
    """Return profile data for the currently authenticated user.

    Requires a valid Bearer token. Role defaults to 'admin' for the built-in
    admin account and 'user' for all others when no users.yaml entry is found.

    Args:
        username: Injected by the get_current_user dependency.

    Returns:
        Dict with keys 'username', 'display_name', and 'role'.

    Raises:
        HTTPException: 401 if the token is missing or invalid.
    """
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
    """Invalidate the current session (client-side token discard).

    JWT tokens are stateless; this endpoint signals the client to drop its
    stored token. No server-side token revocation is performed.

    Returns:
        Dict with key 'status' set to 'logged out'.
    """
    return {"status": "logged out"}
