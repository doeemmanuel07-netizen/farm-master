"""
Prepares the database for a public preview (README "Preview via Cloudflare").

Applies migrations, loads the seed data, then gives every active account that
still has a weak or default password (the seeded "password123") a strong
random one. The new logins are written to .preview/credentials.txt, which is
git-ignored and never leaves this machine. Accounts already rotated keep
their password, so the logins stay the same across preview restarts.

Run from anywhere:  python "Stage 6 Build/scripts/preview_accounts.py"
"""

import secrets
import sys
from pathlib import Path

BUILD_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BUILD_DIR / "backend"))

from app.auth import hash_password  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.migrate import upgrade_to_head  # noqa: E402
from app.models import User  # noqa: E402
from app.preview import CREDENTIALS_FILE, load_credentials, users_with_weak_passwords  # noqa: E402
from app.seed import seed  # noqa: E402

# The login to hand out for each portal; every other account is listed after.
PORTAL_LOGINS = [
    ("Super Admin (Control Centre)", "emmanuel@farmmaster.test", "/control-centre-flow"),
    ("Farmer", "kojo.mensah@farmmaster.test", "/farmer"),
    ("Buyer", "gsfp@farmmaster.test", "/buyer"),
    ("Vendor", "vendor@farmmaster.test", "/vendor-dashboard-flow"),
]

# No 0/O/1/l/I, so a password read off a phone screen types back correctly.
ALPHABET = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_password() -> str:
    return "-".join("".join(secrets.choice(ALPHABET) for _ in range(4)) for _ in range(4))


def write_credentials(creds: dict[str, str]) -> None:
    CREDENTIALS_FILE.parent.mkdir(exist_ok=True)
    lines = ["Farm Master public preview logins -- LOCAL ONLY, never commit or share publicly.",
             "Sign-in is password, then the one-time code shown on screen.", "",
             "Portal logins"]
    handed_out = set()
    for label, email, path in PORTAL_LOGINS:
        if email in creds:
            lines.append(f"  {label:<30} {path:<24} {email}  {creds[email]}")
            handed_out.add(email)
    lines += ["", "Other accounts"]
    for email in sorted(set(creds) - handed_out):
        lines.append(f"  {email}  {creds[email]}")
    CREDENTIALS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    upgrade_to_head()
    seed()
    creds = load_credentials()
    db = SessionLocal()
    try:
        weak = users_with_weak_passwords(db)
        for email in weak:
            password = new_password()
            db.query(User).filter(User.email == email).update({User.password_hash: hash_password(password)})
            creds[email] = password
        db.commit()
    finally:
        db.close()
    write_credentials(creds)
    print(f"Rotated {len(weak)} weak password(s). Logins: {CREDENTIALS_FILE}")


if __name__ == "__main__":
    main()
