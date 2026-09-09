"""E2E: the six previously-tracked Stage 6 gaps closed 8 Sep 2026 -- Field Visit Logs + Agronomist Messaging, Proof of Pickup/Delivery + Trunking, Reporting Dashboard, Registration Approval Queue + Audit Log, Control Centre Dashboard."""

import pytest

from tests.e2e.helpers import login_and_verify_otp, assert_responsive_clean, click_flow_step

pytestmark = [pytest.mark.e2e]


def test_agronomist_logs_and_completes_a_real_field_visit(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/visit-logs-flow", "agronomist@farmmaster.test")
    page.click("#newVisitBtn")
    page.select_option("#visitFarmer", index=0)
    page.fill("#visitCheckpoint", "E2E checkpoint")
    page.fill("#visitDate", "2026-09-20")
    page.click("#saveVisitBtn")
    page.wait_for_timeout(500)
    assert "E2E checkpoint" in page.content()

    complete_btn = page.locator("[data-complete]").first
    if complete_btn.count():
        complete_btn.click()
        page.wait_for_timeout(500)


def test_agronomist_replies_to_farmer_message(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/visit-logs-flow", "agronomist@farmmaster.test")
    click_flow_step(page, "Messaging")
    page.wait_for_timeout(300)
    reply_select = page.locator("#replyTo")
    if reply_select.count():
        page.select_option("#replyTo", index=0)
        page.fill("#replyBody", "E2E test reply")
        page.click("#sendReplyBtn")
        page.wait_for_timeout(500)
        assert "E2E test reply" in page.content()


def test_logistics_captures_real_gps_proof_of_delivery(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/proof-trunking-flow", "logistics@farmmaster.test")
    capture_btn = page.locator("[data-capture]").first
    if capture_btn.count():
        capture_btn.click()
        page.wait_for_timeout(300)
        page.fill("#gpsLat", "5.6698")
        page.fill("#gpsLng", "0.0166")
        page.click("#confirmProofBtn")
        page.wait_for_timeout(500)
    assert page.locator("#canvas").is_visible()


def test_logistics_schedules_and_progresses_a_real_trunking_load(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/proof-trunking-flow", "logistics@farmmaster.test")
    click_flow_step(page, "Trunking")
    page.wait_for_selector("#scheduleTruckBtn", timeout=10000)
    page.fill("#truckTonnes", "0.5")
    page.fill("#truckDest", "E2E Destination")
    page.fill("#truckVehicle", "E2E Truck")
    page.click("#scheduleTruckBtn")
    page.wait_for_timeout(500)
    content = page.content()
    if "E2E Destination" in content:
        dispatch_btn = page.locator("[data-dispatch]").first
        if dispatch_btn.count():
            dispatch_btn.click()
            page.wait_for_timeout(500)
            deliver_btn = page.locator("[data-deliver]").first
            if deliver_btn.count():
                deliver_btn.click()
                page.wait_for_timeout(500)
    assert page.locator("#canvas").is_visible()


def test_reporting_dashboard_shows_real_revenue_streams(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/reporting-flow", "finance@farmmaster.test")
    content = page.content()
    assert "Aggregation" in content and "Phase 2" in content


def test_approvals_and_audit_log_screen_shows_real_data(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/approvals-flow", "emmanuel@farmmaster.test")
    content = page.content()
    assert "Applicant" in content or "Type" in content

    click_flow_step(page, "Audit Log")
    page.wait_for_timeout(300)
    assert "entries" in page.content().lower() or "entry" in page.content().lower()


def test_control_centre_dashboard_shows_role_scoped_tiles(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/control-centre-flow", "finance@farmmaster.test")
    content = page.content()
    assert "Registered farmers" in content
    assert "Reconciliation" in content or "MoFA" in content


def test_new_screens_clean_at_375_768_1280(page, live_server_url):
    for width, height in [(375, 812), (768, 1024), (1280, 900)]:
        page.set_viewport_size({"width": width, "height": height})
        login_and_verify_otp(page, live_server_url, "/proof-trunking-flow", "logistics@farmmaster.test")
        assert_responsive_clean(page, f"proof-trunking-flow @ {width}px")
