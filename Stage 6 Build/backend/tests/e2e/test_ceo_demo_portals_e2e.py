"""
E2E: the portal pages built to the CEO platform demo (docs/reference/) --
every demo interaction against the real backend (brief §9 checklist):
portal switching, landing CTAs, buyer submit -> payment modal -> success ->
new order row, order row expand/collapse, opportunity select/accept with
wallet recalculation, category tabs, add/remove cart items, place order --
plus overflow and 44px touch targets at three widths.
"""

import re

import pytest

from tests.e2e.helpers import assert_responsive_clean

pytestmark = [pytest.mark.e2e]


def portal_login(page, base_url, path, email, password="password123"):
    """Drives the shared FM.signIn card: password, then the email OTP (dev code shown in-page)."""
    page.goto(f"{base_url}{path}")
    page.fill("#fm-email", email)
    page.fill("#fm-pass", password)
    page.click("#fm-signin-form button[type=submit]")
    code = page.locator(".notice strong").inner_text(timeout=10000)
    page.fill("#fm-otp", code)
    page.click("#fm-otp-form button[type=submit]")
    page.wait_for_selector("#fm-otp-form", state="detached", timeout=10000)
    page.wait_for_load_state("networkidle")


def toast_text(page, startswith=""):
    """Waits for a visible toast (optionally one starting with given text -- an earlier toast may still be up)."""
    page.wait_for_function(
        "(p) => { const t = document.querySelector('.toast.show'); return t && t.textContent.startsWith(p); }",
        arg=startswith, timeout=10000,
    )
    return page.locator(".toast").inner_text()


def test_overview_ledger_cards_and_portal_switching(page, live_server_url):
    page.goto(live_server_url + "/")
    page.wait_for_load_state("networkidle")
    ledger = page.locator(".ledger-num").all_inner_texts()
    assert ledger == ["3", "16", "6", "1"]
    assert "Head office — Tema" in page.locator(".ledger").inner_text()
    page.click("text=Open Buyer Portal")
    page.wait_for_url(re.compile(r"/buyer$"))
    page.click(".fm-tab:has-text('Farmer Portal')")
    page.wait_for_url(re.compile(r"/farmer$"))
    page.click(".fm-tab:has-text('Vendor Portal')")
    page.wait_for_url(re.compile(r"/marketplace$"))
    page.click(".fm-tab:has-text('Overview')")
    page.wait_for_url(re.compile(r"/$"))


def test_buyer_submit_pay_and_new_order_row(page, live_server_url):
    portal_login(page, live_server_url, "/buyer", "gsfp@farmmaster.test")
    assert "Institutional buyer" in page.locator("#who").inner_text()
    page.fill("#b-qty", "20")
    page.wait_for_function("document.querySelector('#fee-amt').textContent.includes('1,800')")
    page.click("#b-submit")
    page.wait_for_selector(".modal h3:has-text('Pay commitment fee')")
    page.click(".pm:has-text('AT Money')")
    page.click("[data-confirm]")
    page.click("[data-approve]")
    page.wait_for_selector(".modal h3:has-text('Payment confirmed')")
    assert "Paid via AT Money" in page.locator(".modal").inner_text()
    page.click("[data-done]")
    assert toast_text(page) == "Request submitted — Farm Master is matching farmers in your target region."
    first = page.locator("#orders-body tr.expandable").first
    assert "Matching farmers" in first.inner_text()
    assert page.locator("#orders-body tr.detail-row.open").count() == 1
    first.click()  # collapse
    assert page.locator("#orders-body tr.detail-row.open").count() == 0
    first.click()  # expand again
    assert "Farmer matched" in page.locator("#orders-body tr.detail-row.open").inner_text()


def test_farmer_selects_and_accepts_an_opportunity(page, live_server_url):
    portal_login(page, live_server_url, "/farmer", "kojo.mensah@farmmaster.test")
    before = page.locator("#w-payout").inner_text()
    open_row = page.locator(".select-row", has=page.locator(".badge.open")).first
    crop = open_row.locator("h4").inner_text().split(" — ")[0]
    open_row.click()
    assert "selected" in open_row.get_attribute("class")
    page.click("#accept-btn")
    for box in page.locator(".commit-list input").all():
        box.check()
    page.click("[data-ok]")
    assert toast_text(page) == f"{crop} opportunity accepted — agronomist will contact you within 48 hours."
    page.wait_for_function("document.querySelector('#accept-btn').textContent.trim() === 'Opportunity accepted'")
    page.wait_for_function(f"document.querySelector('#w-payout').textContent !== {before!r}")


def test_marketplace_tabs_cart_and_place_order(page, live_server_url):
    portal_login(page, live_server_url, "/marketplace", "ama.serwaa@farmmaster.test")
    page.click(".cat-tab:has-text('Seeds & Inputs')")
    page.click(".product-card:has-text('NPK 15-15-15 Fertiliser') button")
    assert toast_text(page) == "NPK 15-15-15 Fertiliser added to your order."
    page.click(".cat-tab:has-text('Mechanisation Services')")
    page.click(".product-card:has-text('Land preparation') button")
    assert page.locator(".cart-line").count() == 2
    page.click(".cart-line:has-text('Land preparation') .rm")
    assert page.locator(".cart-line").count() == 1
    page.click(".cart-line .qty-btn[data-d='1']")
    assert page.locator(".cart-line .name").inner_text().startswith("2 × NPK")
    assert "530" in page.locator("#cart-total").inner_text()
    page.click("#place-order")
    assert toast_text(page, "Order routed") == "Order routed to Farm Master logistics — estimated farm-gate delivery in 2 days."
    assert page.locator(".cart-empty").is_visible()


@pytest.mark.parametrize("path,email", [
    ("/", None), ("/buyer", "gsfp@farmmaster.test"), ("/farmer", "kojo.mensah@farmmaster.test"),
    ("/marketplace", "ama.serwaa@farmmaster.test"),
])
def test_portal_pages_clean_at_375_768_1280(page, live_server_url, path, email):
    if email:
        portal_login(page, live_server_url, path, email)
    for width, height in [(375, 812), (768, 1024), (1280, 900)]:
        page.set_viewport_size({"width": width, "height": height})
        page.goto(live_server_url + path)
        page.wait_for_load_state("networkidle")
        assert_responsive_clean(page, f"{path} @ {width}px")
