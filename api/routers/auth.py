"""Auth endpoints — login, signup, session check, logout."""

import os
import re
import jwt
import datetime
import bcrypt
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from db import get_db

router = APIRouter()
bearer = HTTPBearer(auto_error=False)

JWT_SECRET    = os.environ.get("JWT_SECRET", "dev-secret-change-in-prod")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_H  = 24 * 7  # 7 days


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_token(username: str) -> str:
    payload = {
        "sub": username,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=JWT_EXPIRY_H),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


def _get_user(username: str) -> dict | None:
    """Fetch a user row from the DB. Returns None if not found."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT username, display_name, password_hash, role FROM users WHERE username = %s",
                (username,)
            )
            row = cur.fetchone()
    if not row:
        return None
    return {"username": row[0], "display_name": row[1], "password_hash": row[2], "role": row[3]}


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> str:
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

class SignupRequest(BaseModel):
    username: str
    display_name: str
    password: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/login")
def login(body: LoginRequest):
    user = _get_user(body.username)

    # Fallback: dev mode with no DB users (admin/admin)
    if user is None:
        if body.username == "admin" and body.password == "admin":
            return {"token": _make_token("admin"), "username": "admin"}
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not bcrypt.checkpw(body.password.encode(), user["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return {"token": _make_token(body.username), "username": body.username}


@router.post("/signup")
def signup(body: SignupRequest):
    # Validate username: 3-20 chars, alphanumeric + underscore only
    if not re.match(r'^[a-zA-Z0-9_]{3,20}$', body.username):
        raise HTTPException(status_code=400, detail="Username must be 3-20 characters (letters, numbers, underscore only)")

    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    display_name = body.display_name.strip() or body.username
    password_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (username, display_name, password_hash, role) VALUES (%s, %s, %s, 'user')",
                    (body.username.lower(), display_name, password_hash)
                )
            conn.commit()
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Username already taken")
        raise HTTPException(status_code=500, detail="Could not create account")

    return {"token": _make_token(body.username.lower()), "username": body.username.lower()}


@router.get("/me")
def me(username: str = Depends(get_current_user)):
    user = _get_user(username)
    if user:
        return {
            "username":     user["username"],
            "display_name": user["display_name"],
            "role":         user["role"],
        }
    # Fallback for dev admin/admin
    return {
        "username":     username,
        "display_name": username.capitalize(),
        "role":         "admin" if username == "admin" else "user",
    }


@router.post("/logout")
def logout():
    return {"status": "logged out"}
