"""Admin endpoints — user management (admin role required)."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import yaml
import bcrypt
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from dashboard_utils import load_users, USERS_YAML
from api.routers.auth import get_current_user

router = APIRouter()

USERS_YAML_PATH = USERS_YAML


def _require_admin(username: str = Depends(get_current_user)):
    users = load_users()
    if users and users.get(username, {}).get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return username


def _save_users(users_dict: dict):
    with open(USERS_YAML_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump({"users": users_dict}, f, default_flow_style=False, allow_unicode=True)


class UserCreate(BaseModel):
    username: str
    password: str
    display_name: str = ""
    role: str = "user"


class PasswordChange(BaseModel):
    password: str


@router.get("/users")
def list_users(_admin: str = Depends(_require_admin)):
    """Return all users (no password hashes)."""
    users = load_users()
    result = [
        {
            "username":     uname,
            "display_name": udata.get("display_name", uname),
            "role":         udata.get("role", "user"),
        }
        for uname, udata in users.items()
    ]
    return {"users": result}


@router.post("/users")
def create_user(body: UserCreate, _admin: str = Depends(_require_admin)):
    """Create a new user."""
    users = load_users()
    if body.username in users:
        raise HTTPException(status_code=409, detail="Username already exists")
    if not body.password:
        raise HTTPException(status_code=400, detail="Password is required")

    pw_hash = bcrypt.hashpw(body.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    users[body.username] = {
        "display_name": body.display_name or body.username,
        "role":         body.role,
        "password_hash": pw_hash,
    }
    _save_users(users)
    return {"status": "created", "username": body.username}


@router.delete("/users/{username}")
def delete_user(username: str, admin: str = Depends(_require_admin)):
    """Delete a user (cannot delete yourself)."""
    if username == admin:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    users = load_users()
    if username not in users:
        raise HTTPException(status_code=404, detail="User not found")
    del users[username]
    _save_users(users)
    return {"status": "deleted"}


@router.patch("/users/{username}/password")
def change_password(username: str, body: PasswordChange, _admin: str = Depends(_require_admin)):
    """Change a user's password."""
    users = load_users()
    if username not in users:
        raise HTTPException(status_code=404, detail="User not found")
    if not body.password:
        raise HTTPException(status_code=400, detail="Password is required")
    pw_hash = bcrypt.hashpw(body.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    users[username]["password_hash"] = pw_hash
    _save_users(users)
    return {"status": "updated"}
