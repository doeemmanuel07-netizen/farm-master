"""
Builds a static, shareable preview of the four CEO-demo portal pages
(Overview, Farmer, Buyer, Marketplace) that runs with no backend.

It signs in to a RUNNING local app, captures the real JSON each page reads,
and writes a folder where an in-browser mock (demo/mock-api.js) answers the
same API calls from that snapshot and simulates the actions (submit + pay,
accept opportunity, place order) in memory. Nothing is persisted and no
money moves. The full app (FastAPI + PostgreSQL) is still the real thing.

    python scripts/build_static_demo.py <out_dir>        # server on 127.0.0.1:8000
"""

import json
import os
import re
import shutil
import sys
from pathlib import Path

import httpx

BASE = os.environ.get("FM_BASE_URL", "http://127.0.0.1:8000")
FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
PAGES = {  # static file -> (source page, role it runs as, demo account)
    "index.html": ("portal_overview.html", None, None),
    "buyer.html": ("portal_buyer.html", "buyer", "gsfp@farmmaster.test"),
    "farmer.html": ("portal_farmer.html", "farmer", "kojo.mensah@farmmaster.test"),
    "marketplace.html": ("portal_marketplace.html", "farmer", "ama.serwaa@farmmaster.test"),
}
ROUTES = {"/": "index.html", "/buyer": "buyer.html", "/farmer": "farmer.html", "/marketplace": "marketplace.html"}
# Shown when the static preview has no snapshot events (fresh pilot database).
SAMPLE_ACTIVITY = [
    "Live: Tricycle #2 en route with seeds and fertilizer for 1 farm in Greater Accra.",
    "Live: Fulfilment centre — Tema has aggregated 3.8 tonnes of maize today.",
    "Live: harvest pickup completed — 2.5 t delivered to Tema fulfilment centre.",
    "Live: Vehicle #07 trunking 2 t of graded produce from Tema to Tema head office.",
]


def token(c, email):
    ch = c.post("/auth/login", json={"email": email, "password": "password123"}).json()
    v = c.post("/auth/login/verify-otp", json={"challenge_id": ch["challenge_id"], "email_code": ch["dev_only_email_code"]}).json()
    return {"Authorization": f"Bearer {v['access_token']}"}


def capture():
    c = httpx.Client(base_url=BASE, timeout=30)
    fx = {"stats": c.get("/api/public/stats").json(), "activity": c.get("/api/public/activity?limit=10").json()}
    if not fx["activity"]:
        fx["activity"] = [{"text": t, "at": None} for t in SAMPLE_ACTIVITY]
    admin = token(c, "emmanuel@farmmaster.test")
    fx["fee_rule"] = next(r for r in c.get("/admin/commitment-fee-rules", headers=admin).json() if r["is_active"])
    b = token(c, "gsfp@farmmaster.test")
    fx["buyer"] = {"me": c.get("/auth/me", headers=b).json(), "order_form": c.get("/buyer/order-form", headers=b).json(),
                   "requirements": c.get("/buyer/requirements", headers=b).json()}
    f = token(c, "kojo.mensah@farmmaster.test")
    fx["farmer"] = {"me": c.get("/auth/me", headers=f).json(), "opps": c.get("/farmer/matched-opportunities", headers=f).json(),
                    "wallet": c.get("/farmer/wallet/summary", headers=f).json()}
    m = token(c, "ama.serwaa@farmmaster.test")
    fx["market"] = {"me": c.get("/auth/me", headers=m).json(), "catalogue": c.get("/farmer/marketplace", headers=m).json(),
                    "prefill": c.get("/farmer/marketplace/formula-prefill", headers=m).json()}
    return fx


def rewrite(html, role, page, is_index):
    html = html.replace("/static/assets/", "assets/")
    for route, target in ROUTES.items():
        html = html.replace(f'href="{route}"', f'href="{target}"')
    # Links to the full app's other screens can't work without the backend.
    html = re.sub(r'href="/[a-z0-9-]+(?:-flow)?"', 'href="#full-app" data-demo-only', html)
    html = html.replace('<script src="assets/components.js"></script>',
                        f'<script src="demo/fixtures.js"></script>\n<script src="demo/mock-api.js" data-role="{role or ""}" data-page="{page}"></script>\n'
                        '<script src="assets/components.js"></script>\n<script src="demo/patch.js"></script>')
    if is_index:  # the published page's own skeleton is added by the host
        for tag in ("<!doctype html>", '<html lang="en">', "<head>", "</head>", "<body>", "</body>", "</html>"):
            html = html.replace(tag, "")
    return html


def main(out):
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    (out / "assets").mkdir(parents=True)
    (out / "demo").mkdir()
    for name in ("tokens.css", "components.css", "components.js"):
        shutil.copy(FRONTEND / "assets" / name, out / "assets" / name)
    for name in ("mock-api.js", "patch.js"):
        shutil.copy(Path(__file__).parent / "static_demo" / name, out / "demo" / name)
    fx = capture()
    (out / "demo" / "fixtures.js").write_text("window.FM_FIXTURES = " + json.dumps(fx, ensure_ascii=False, default=str) + ";\n", encoding="utf-8")
    for target, (src, role, _) in PAGES.items():
        html = (FRONTEND / src).read_text(encoding="utf-8")
        (out / target).write_text(rewrite(html, role, target.removesuffix(".html"), target == "index.html"), encoding="utf-8")
    print(f"Static preview written to {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "static-demo")
