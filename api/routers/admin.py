"""Admin endpoints — user management (admin role required)."""

import bcrypt
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from db import get_db
from api.routers.auth import get_current_user

router = APIRouter()


def _require_admin(username: str = Depends(get_current_user)):
    """Enforce admin role — checks the PostgreSQL users table."""
    # Dev fallback: the hardcoded admin/admin account has no DB row
    if username == "admin":
        return username
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT role FROM users WHERE username = %s", (username,))
            row = cur.fetchone()
    if not row or row[0] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return username


class UserCreate(BaseModel):
    username: str
    password: str
    display_name: str = ""
    role: str = "user"


class PasswordChange(BaseModel):
    password: str


class RoleChange(BaseModel):
    role: str


@router.get("/users")
def list_users(_admin: str = Depends(_require_admin)):
    """Return all registered users, excluding password hashes."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT username, display_name, role FROM users ORDER BY username")
            rows = cur.fetchall()
    return {"users": [{"username": r[0], "display_name": r[1], "role": r[2]} for r in rows]}


@router.post("/users")
def create_user(body: UserCreate, _admin: str = Depends(_require_admin)):
    """Create a new user in the PostgreSQL users table."""
    if not body.password:
        raise HTTPException(status_code=400, detail="Password is required")
    pw_hash = bcrypt.hashpw(body.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (username, display_name, password_hash, role) VALUES (%s, %s, %s, %s)",
                    (body.username.lower(), body.display_name or body.username, pw_hash, body.role)
                )
            conn.commit()
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Username already exists")
        raise HTTPException(status_code=500, detail="Could not create user")
    return {"status": "created", "username": body.username.lower()}


@router.delete("/users/{username}")
def delete_user(username: str, admin: str = Depends(_require_admin)):
    """Delete a user from the PostgreSQL users table."""
    if username == admin:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE username = %s RETURNING username", (username,))
            deleted = cur.fetchone()
        conn.commit()
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "deleted"}


@router.patch("/users/{username}/password")
def change_password(username: str, body: PasswordChange, _admin: str = Depends(_require_admin)):
    """Change password for an existing user."""
    if not body.password:
        raise HTTPException(status_code=400, detail="Password is required")
    pw_hash = bcrypt.hashpw(body.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET password_hash = %s WHERE username = %s RETURNING username",
                (pw_hash, username)
            )
            updated = cur.fetchone()
        conn.commit()
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "updated"}


@router.patch("/users/{username}/role")
def change_role(username: str, body: RoleChange, admin: str = Depends(_require_admin)):
    """Change the role of an existing user."""
    if username == admin:
        raise HTTPException(status_code=400, detail="Cannot change your own role")
    if body.role not in ("user", "admin", "guest"):
        raise HTTPException(status_code=400, detail="Role must be user, admin, or guest")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET role = %s WHERE username = %s RETURNING username",
                (body.role, username)
            )
            updated = cur.fetchone()
        conn.commit()
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "updated", "role": body.role}
