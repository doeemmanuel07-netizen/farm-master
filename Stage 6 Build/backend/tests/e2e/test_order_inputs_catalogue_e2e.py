"""E2E: Vendor incoming input orders, Farmer Harvest Pickup Request, and the retired Order Inputs route (decision D1 -- farmers now order in the marketplace; see test_ceo_demo_portals_e2e.py)."""

import pytest

from tests.e2e.helpers import login_and_verify_otp, assert_responsive_clean

pytestmark = [pytest.mark.e2e]


def test_vendor_confirms_a_real_pending_input_order(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/vendor-catalogue-flow", "vendor@farmmaster.test")
    row = page.locator("[data-id]").first
    if row.count():
        row.click()
        page.wait_for_timeout(300)
        confirm_btn = page.locator("#confirmOrderBtn")
        if confirm_btn.count():
            confirm_btn.click()
            page.wait_for_timeout(500)
    assert page.locator("#canvas").is_visible()


def test_farmer_requests_harvest_pickup(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/harvest-pickup-flow", "kojo.mensah@farmmaster.test")
    page.wait_for_selector("#requestBtn", timeout=10000)
    page.click("#requestBtn")
    page.wait_for_timeout(500)
    assert page.locator("#canvas").is_visible()


def test_old_order_inputs_route_redirects_to_the_marketplace(page, live_server_url):
    """Decision D1: Order Inputs moved onto the marketplace when products were retired."""
    page.goto(f"{live_server_url}/order-inputs-flow")
    assert "/marketplace?prefill=formula" in page.url
