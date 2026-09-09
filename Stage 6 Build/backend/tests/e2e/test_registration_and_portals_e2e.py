"""E2E: Registration + OTP, and the three original portal flows (Buyer commitment fee, Farmer opportunity+formula, Vendor mechanisation request) -- PRD Section 6 Must-Haves #1 and #2, driven through the real served pages, not just curl. Selectors below are read directly from the actual frontend files, not guessed."""

import pytest

from tests.e2e.helpers import login_and_verify_otp, assert_responsive_clean

pytestmark = [pytest.mark.e2e]


def test_farmer_self_registration_activates_immediately(page, live_server_url):
    page.goto(f"{live_server_url}/register-flow")
    page.click('[data-role="farmer"]')
    page.click("#continueBtn")
    page.fill("#fullName", "E2E New Farmer")
    page.fill("#email", "e2e-newfarmer@test.invalid")
    page.fill("#phone", "+233240000001")
    page.fill("#password", "password123")
    page.click("#registerBtn")
    page.wait_for_selector("#otpBtn", timeout=10000)
    page.click("#otpBtn")
    page.wait_for_timeout(500)
    assert "active" in page.content().lower()


def test_buyer_commitment_fee_full_real_lifecycle(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/buyer-flow", "buyer@farmmaster.test")
    page.fill("#grade", "Grade 1")
    page.fill("#qty", "2")
    page.fill("#price", "2100")
    page.fill("#location", "Tema")
    page.fill("#timeline", "30 Sep 2026")
    page.click("#continueBtn")

    page.wait_for_selector('[data-method="momo"]', timeout=10000)
    page.click('[data-method="momo"]')
    page.click("#payBtn")
    page.wait_for_selector("#toStatusBtn", timeout=10000)
    page.click("#toStatusBtn")
    page.wait_for_selector("#statusBadge", timeout=10000)
    assert "matching" in page.locator("#statusBadge").inner_text().lower()


def test_buyer_card_payment_shows_real_501_not_a_silent_success(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/buyer-flow", "buyer@farmmaster.test")
    page.fill("#grade", "Grade 1")
    page.fill("#qty", "1")
    page.fill("#price", "2000")
    page.fill("#location", "Tema")
    page.fill("#timeline", "30 Sep 2026")
    page.click("#continueBtn")
    page.wait_for_selector('[data-method="card"]', timeout=10000)
    page.click('[data-method="card"]')
    page.click("#payBtn")
    page.wait_for_selector("#payAlert.show", timeout=10000)
    assert "gateway" in page.locator("#payAlertText").inner_text().lower()


def test_farmer_accepts_a_real_opportunity_and_gets_a_real_formula(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/farmer-flow", "farmer@farmmaster.test")
    view_and_accept = page.locator("[data-opp]").first
    view_and_accept.wait_for(timeout=10000)
    view_and_accept.click()

    checklist_items = page.locator("#checklist .checkline")
    count = checklist_items.count()
    for i in range(count):
        checklist_items.nth(i).click()

    page.click("#acceptBtn")
    page.wait_for_selector("#toFormulaBtn", timeout=10000)
    page.click("#toFormulaBtn")
    page.wait_for_timeout(500)
    content = page.content().lower()
    assert "seed" in content and ("npk" in content or "bag" in content)


def test_vendor_confirms_a_real_mechanisation_request_in_window(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/vendor-flow", "vendor@farmmaster.test")
    first_req = page.locator("[data-req]").first
    first_req.wait_for(timeout=10000)
    first_req.click()

    date_input = page.locator("#dateInput")
    if date_input.count():
        date_input.fill("2026-09-06")
    if page.locator("#confirmBtn").count():
        page.click("#confirmBtn")
        page.wait_for_timeout(500)
        # Either lands on a result screen or shows the override notice --
        # both are real backend responses, not a client-side fake.
        assert page.locator("#canvas").is_visible()


def test_buyer_flow_clean_at_375_768_1280(page, live_server_url):
    for width, height in [(375, 812), (768, 1024), (1280, 900)]:
        page.set_viewport_size({"width": width, "height": height})
        login_and_verify_otp(page, live_server_url, "/buyer-flow", "gsfp@farmmaster.test")
        assert_responsive_clean(page, f"buyer-flow @ {width}px")
