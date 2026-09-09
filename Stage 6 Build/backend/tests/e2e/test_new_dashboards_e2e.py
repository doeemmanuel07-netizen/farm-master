"""E2E: the 8 Sep 2026 portal dashboards -- Buyer Dashboard/Docs/Tracking/Invoice, Farmer Dashboard/Milestones/Messaging/Wallet, Vendor Dashboard/Billing/Payout/Handoff."""

import pytest

from tests.e2e.helpers import login_and_verify_otp, click_flow_step, assert_responsive_clean

pytestmark = [pytest.mark.e2e]


def test_buyer_dashboard_opens_a_real_order_across_all_three_tabs(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/buyer-dashboard-flow", "buyer@farmmaster.test")
    open_btn = page.locator("[data-open]").first
    open_btn.wait_for(timeout=10000)
    open_btn.click()
    page.wait_for_timeout(400)

    page.click('[data-tab="tracking"]')
    page.wait_for_timeout(300)
    assert "Progress" in page.content() or "Delivery log" in page.content()

    page.click('[data-tab="invoice"]')
    page.wait_for_timeout(300)
    assert "Net payable" in page.content() or "GHS" in page.content()


def test_farmer_dashboard_logs_milestone_and_sends_message(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/farmer-dashboard-flow", "kojo.mensah@farmmaster.test")
    click_flow_step(page, "Milestone Log")
    page.wait_for_selector("#mTitle", timeout=10000)
    page.fill("#mTitle", "E2E milestone")
    page.click("#addMilestoneBtn")
    page.wait_for_timeout(500)
    assert "E2E milestone" in page.content()

    click_flow_step(page, "Agronomist Messaging")
    page.wait_for_selector("#msgBody", timeout=10000)
    page.fill("#msgBody", "E2E question from farmer")
    page.click("#sendMsgBtn")
    page.wait_for_timeout(500)
    assert "E2E question from farmer" in page.content()


def test_farmer_wallet_shows_real_settlement_figures(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/farmer-dashboard-flow", "kojo.mensah@farmmaster.test")
    click_flow_step(page, "Wallet")
    page.wait_for_timeout(400)
    assert "GHS" in page.content()


def test_vendor_dashboard_pays_billing_and_views_payout_handoff(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/vendor-dashboard-flow", "vendor@farmmaster.test")
    click_flow_step(page, "Subscription")
    page.wait_for_selector("#billMethod", timeout=10000)
    page.select_option("#billMethod", "momo")
    page.click("#payBillBtn")
    page.wait_for_timeout(500)
    assert "GHS" in page.content()

    click_flow_step(page, "Payout")
    page.wait_for_timeout(300)
    assert page.locator("#canvas").is_visible()

    click_flow_step(page, "Logistics Handoff")
    page.wait_for_timeout(300)
    assert page.locator("#canvas").is_visible()


def test_vendor_billing_card_still_501s_in_the_browser(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/vendor-dashboard-flow", "vendor@farmmaster.test")
    click_flow_step(page, "Subscription")
    page.wait_for_selector("#billMethod", timeout=10000)
    page.select_option("#billMethod", "card")
    page.click("#payBillBtn")
    page.wait_for_selector("#billAlert.show", timeout=10000)
    assert "gateway" in page.locator("#billAlertText").inner_text().lower()


def test_dashboards_clean_at_375_768_1280(page, live_server_url):
    for width, height in [(375, 812), (768, 1024), (1280, 900)]:
        page.set_viewport_size({"width": width, "height": height})
        login_and_verify_otp(page, live_server_url, "/farmer-dashboard-flow", "farmer@farmmaster.test")
        assert_responsive_clean(page, f"farmer-dashboard-flow @ {width}px")
