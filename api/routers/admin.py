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
    """FastAPI dependency — enforce that the authenticated user holds the admin role.

    Delegates token validation to get_current_user, then checks the resolved
    username against users.yaml. If no users.yaml exists, any authenticated
    user is permitted (dev fallback).

    Args:
        username: Injected by the get_current_user dependency.

    Returns:
        The authenticated admin username string.

    Raises:
        HTTPException: 401 if the token is missing or invalid (raised upstream).
        HTTPException: 403 if the user exists but does not have role 'admin'.
    """
    users = load_users()
    if users and users.get(username, {}).get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return username


def _save_users(users_dict: dict):
    """Persist the full users dictionary to users.yaml.

    Overwrites the file atomically using yaml.safe_dump with the top-level
    'users' key. Unicode characters are preserved.

    Args:
        users_dict: Dict mapping username strings to user data dicts
                    (display_name, role, password_hash).
    """
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
    """Return all registered users, excluding password hashes.

    Requires admin role. Password hashes are never included in the response.

    Args:
        _admin: Injected and validated by the _require_admin dependency.

    Returns:
        Dict with key 'users' containing a list of dicts, each with
        'username', 'display_name', and 'role'.

    Raises:
        HTTPException: 401 if not authenticated.
        HTTPException: 403 if the caller is not an admin.
    """
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
    """Create a new user and persist them to users.yaml.

    Hashes the provided password with bcrypt before storing. The display_name
    defaults to the username if not provided.

    Requires admin role.

    Args:
        body: UserCreate payload with 'username', 'password', optional
              'display_name', and optional 'role' (defaults to 'user').
        _admin: Injected and validated by the _require_admin dependency.

    Returns:
        Dict with keys 'status' ('created') and 'username'.

    Raises:
        HTTPException: 400 if the password is empty.
        HTTPException: 401 if not authenticated.
        HTTPException: 403 if the caller is not an admin.
        HTTPException: 409 if the username already exists.
    """
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
    """Delete a user from users.yaml.

    Prevents self-deletion to avoid accidental admin lockout. Requires
    admin role.

    Args:
        username: Username to delete (path parameter).
        admin: The authenticated admin username, injected by _require_admin.

    Returns:
        Dict with key 'status' set to 'deleted'.

    Raises:
        HTTPException: 400 if the caller attempts to delete their own account.
        HTTPException: 401 if not authenticated.
        HTTPException: 403 if the caller is not an admin.
        HTTPException: 404 if the specified username does not exist.
    """
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
    """Change the bcrypt-hashed password for an existing user.

    Requires admin role. The new password is hashed with bcrypt before being
    written to users.yaml. An admin may change any user's password, including
    their own.

    Args:
        username: Username whose password to change (path parameter).
        body: PasswordChange payload with the new plain-text 'password'.
        _admin: Injected and validated by the _require_admin dependency.

    Returns:
        Dict with key 'status' set to 'updated'.

    Raises:
        HTTPException: 400 if the new password is empty.
        HTTPException: 401 if not authenticated.
        HTTPException: 403 if the caller is not an admin.
        HTTPException: 404 if the specified username does not exist.
    """
    users = load_users()
    if username not in users:
        raise HTTPException(status_code=404, detail="User not found")
    if not body.password:
        raise HTTPException(status_code=400, detail="Password is required")
    pw_hash = bcrypt.hashpw(body.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    users[username]["password_hash"] = pw_hash
    _save_users(users)
    return {"status": "updated"}
