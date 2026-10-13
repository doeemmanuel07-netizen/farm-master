"""
Public preview mode (Cloudflare Quick Tunnel, see README "Preview via Cloudflare").

Set FARM_MASTER_PUBLIC_PREVIEW=1 when the app is reachable from the internet.
In that mode the interactive API docs are switched off, CORS only allows the
origins in FARM_MASTER_CORS_ORIGINS (the portals are same-origin, so none are
needed), and startup refuses to run while the JWT secret is the dev default
or any active account still has a weak password. scripts/preview_accounts.py
rotates the seeded dev passwords before the preview starts.

FARM_MASTER_DEMO_PREFILL=1 (set by the preview launcher, at the owner's
request on 13 Oct 2026) pre-fills every login page with the logins from the
local .preview/credentials.txt and continues past the on-screen one-time code,
so Continue signs straight in. The passwords are injected into the served page
at request time and never committed. With it on, anyone holding the link can
use every portal, Super Admin included.
"""

import json
import os
from pathlib import Path

from .auth import SECRET_KEY, verify_password
from .database import SessionLocal
from .models import User, UserStatus

PUBLIC_PREVIEW = os.environ.get("FARM_MASTER_PUBLIC_PREVIEW") == "1"
DEMO_PREFILL = os.environ.get("FARM_MASTER_DEMO_PREFILL") == "1"
# Set when the permanent workers.dev link fronts the tunnel (preview-worker/).
PROXY_SECRET = os.environ.get("FARM_MASTER_PROXY_SECRET", "") if PUBLIC_PREVIEW else ""
CREDENTIALS_FILE = Path(__file__).resolve().parents[2] / ".preview" / "credentials.txt"

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


def load_credentials(path: Path = CREDENTIALS_FILE) -> dict[str, str]:
    """{email: password} from credentials.txt (lines ending "<email>  <password>")."""
    creds = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) >= 2 and "@" in parts[-2]:
                creds[parts[-2]] = parts[-1]
    return creds


# Flow pages all render their code step with a pre-filled #otpBtn; click it
# once it appears (at most every 3s, so a rejected code can't loop).
_AUTO_OTP_JS = (
    "(function(){var last=0;new MutationObserver(function(){var b=document.getElementById('otpBtn');"
    "if(b&&!b.disabled&&!b.dataset.fmAuto&&Date.now()-last>3000){b.dataset.fmAuto='1';last=Date.now();"
    "setTimeout(function(){b.click();},0);}}).observe(document.documentElement,{childList:true,subtree:true});})();"
)


def inject_demo_logins(html: str) -> str:
    logins = json.dumps(load_credentials()).replace("</", "<\\/")
    snippet = f"<script>window.FM_DEMO_LOGINS={logins};{_AUTO_OTP_JS}</script>"
    # Before the page's own first script, so the logins exist when it runs
    # (the *-flow pages have no <head>).
    at = html.find("<script")
    if at < 0:
        return html + snippet
    return html[:at] + snippet + html[at:]
