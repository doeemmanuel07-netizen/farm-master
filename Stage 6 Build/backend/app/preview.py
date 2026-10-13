"""
Public preview mode (Cloudflare Quick Tunnel, see README "Preview via Cloudflare").

Set FARM_MASTER_PUBLIC_PREVIEW=1 when the app is reachable from the internet.
In that mode the interactive API docs are switched off, CORS only allows the
origins in FARM_MASTER_CORS_ORIGINS (the portals are same-origin, so none are
needed), and startup refuses to run while the JWT secret is the dev default
or any active account still has a weak password. scripts/preview_accounts.py
rotates the seeded dev passwords before the preview starts.
"""

import os

from .auth import SECRET_KEY, verify_password
from .database import SessionLocal
from .models import User, UserStatus

PUBLIC_PREVIEW = os.environ.get("FARM_MASTER_PUBLIC_PREVIEW") == "1"

DEV_JWT_SECRET = "dev-only-insecure-secret-change-me"
# The seeded dev password plus the obvious defaults an admin might set.
WEAK_PASSWORDS = ("password123", "password", "admin123")


def cors_origins() -> list[str]:
    configured = os.environ.get("FARM_MASTER_CORS_ORIGINS", "")
    origins = [o.strip() for o in configured.split(",") if o.strip()]
    if origins:
        return origins
    return [] if PUBLIC_PREVIEW else ["*"]


def users_with_weak_passwords(db) -> list[str]:
    weak = []
    for user in db.query(User).filter(User.status == UserStatus.ACTIVE).all():
        if user.password_hash and any(verify_password(p, user.password_hash) for p in WEAK_PASSWORDS):
            weak.append(user.email)
    return weak


def check_public_preview_safe() -> None:
    if not PUBLIC_PREVIEW:
        return
    if SECRET_KEY == DEV_JWT_SECRET or len(SECRET_KEY) < 32:
        raise RuntimeError("Public preview refused: set FARM_MASTER_JWT_SECRET to a random value of 32+ characters.")
    db = SessionLocal()
    try:
        weak = users_with_weak_passwords(db)
    finally:
        db.close()
    if weak:
        raise RuntimeError(
            "Public preview refused: these active accounts still have a weak or default password: "
            + ", ".join(weak) + ". Run scripts/preview_accounts.py first."
        )
