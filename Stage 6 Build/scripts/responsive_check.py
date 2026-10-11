"""
Responsive overflow check (CEO demo brief, working rule 4).

Loads each page at 390 / 820 / 1400px in headless Chromium and fails if
document.documentElement.scrollWidth exceeds the viewport width (i.e. the
page scrolls horizontally). Optionally signs in first so portal pages are
checked in their real, data-filled state rather than the sign-in card.

Usage (server must already be running):
    python scripts/responsive_check.py                 # default page list
    python scripts/responsive_check.py /buyer /farmer  # specific paths
    FM_BASE_URL=http://127.0.0.1:8000 python scripts/responsive_check.py

Exit code 0 = every page passed at every width.
"""

import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.environ.get("FM_BASE_URL", "http://127.0.0.1:8000")
WIDTHS = [390, 820, 1400]

# path -> demo account to sign in as before measuring (None = public page)
DEFAULT_PAGES = {
    "/": None,
    "/design-system": None,
    "/farmer": "kojo.mensah@farmmaster.test",
    "/buyer": "gsfp@farmmaster.test",
    "/marketplace": "kojo.mensah@farmmaster.test",
    "/ops": "emmanuel@farmmaster.test",
}


def sign_in(page, email):
    """Signs in through the real API and stores the shared session key."""
    r = page.request.post(f"{BASE}/auth/login", data={"email": email, "password": "password123"})
    assert r.ok, f"login failed for {email}: {r.status}"
    ch = r.json()
    v = page.request.post(f"{BASE}/auth/login/verify-otp",
                          data={"challenge_id": ch["challenge_id"], "email_code": ch["dev_only_email_code"]})
    assert v.ok, f"OTP verify failed for {email}: {v.status}"
    tok = v.json()
    page.goto(f"{BASE}/health")
    page.evaluate(
        """(t) => localStorage.setItem('farmmaster_session', JSON.stringify({
              token: t.access_token, role: t.role, fullName: t.full_name, lastActivityAt: Date.now()}))""",
        tok,
    )


def main(argv):
    pages = {p: DEFAULT_PAGES.get(p) for p in argv} if argv else DEFAULT_PAGES
    failures = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for path, account in pages.items():
            for w in WIDTHS:
                ctx = browser.new_context(viewport={"width": w, "height": 900})
                page = ctx.new_page()
                if account:
                    sign_in(page, account)
                page.goto(f"{BASE}{path}")
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(300)
                sw, vw = page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
                ok = sw <= vw
                print(f"{'PASS' if ok else 'FAIL'}  {path:<28} {w:>5}px  scrollWidth={sw}")
                if not ok:
                    offenders = page.evaluate(
                        """(vw) => Array.from(document.querySelectorAll('body *'))
                              .filter(e => e.getBoundingClientRect().right > vw + 1)
                              .slice(0, 5).map(e => e.tagName + '.' + e.className)""",
                        vw,
                    )
                    failures.append((path, w, sw, offenders))
                ctx.close()
        browser.close()
    for path, w, sw, offenders in failures:
        print(f"  {path} @ {w}px overflows to {sw}px; widest elements: {offenders}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
