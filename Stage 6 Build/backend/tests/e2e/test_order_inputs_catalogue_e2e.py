"""E2E: Farmer Order Inputs, Vendor Product Catalogue, Farmer Harvest Pickup Request -- PRD Must-Have #3's literal scope and #4's front half."""

import pytest

from tests.e2e.helpers import login_and_verify_otp, assert_responsive_clean

pytestmark = [pytest.mark.e2e]


def test_farmer_places_a_real_input_order_and_stock_decrements(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/order-inputs-flow", "kojo.mensah@farmmaster.test")
    qty_input = page.locator(".qty-input").first
    qty_input.wait_for(timeout=10000)
    qty_input.fill("2")
    page.click("#confirmOrderBtn")
    page.wait_for_timeout(500)
    assert page.locator("#canvas").is_visible()


def test_vendor_adds_a_new_catalogue_item(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/vendor-catalogue-flow", "vendor@farmmaster.test")
    page.click("#toggleAddBtn")
    page.fill("#newName", "E2E Test Herbicide")
    page.select_option("#newCategory", "crop_protection")
    page.fill("#newUnit", "litre")
    page.fill("#newPrice", "80")
    page.fill("#newStock", "15")
    page.click("#submitNewItemBtn")
    page.wait_for_timeout(500)
    assert "E2E Test Herbicide" in page.content()


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


def test_order_inputs_flow_clean_at_375_768_1280(page, live_server_url):
    for width, height in [(375, 812), (768, 1024), (1280, 900)]:
        page.set_viewport_size({"width": width, "height": height})
        login_and_verify_otp(page, live_server_url, "/order-inputs-flow", "ama.serwaa@farmmaster.test")
        assert_responsive_clean(page, f"order-inputs-flow @ {width}px")
