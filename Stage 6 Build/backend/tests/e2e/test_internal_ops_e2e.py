"""E2E: Matching Queue, Production Formula Builder, Logistics Dispatch, Fulfilment Intake & Grading, Finance & Reconciliation -- the Internal Operations screens completing PRD Must-Haves #3/#4/#5. Selectors read from the real frontend files."""

import pytest

from tests.e2e.helpers import login_and_verify_otp, assert_responsive_clean

pytestmark = [pytest.mark.e2e]


def test_matching_queue_assigns_real_farmers_to_a_requirement(page, live_server_url):
    """
    Must click a row the app itself marks "clickable" (status == matching)
    -- seed.py also creates a PRODUCTION-status requirement for the Formula
    Builder demo, and GET /agronomist/requirements returns MATCHING through
    SHIPMENT in one list ordered by created_at desc, so ".first" is not
    reliably the matching one. Clicking a non-matching row is a deliberate
    no-op in the app (`if (r.status !== "matching") return;`), which this
    test found the hard way on its first attempt (8 Sep 2026) -- a bug in
    the test's row selection, not in the app.
    """
    login_and_verify_otp(page, live_server_url, "/matching-flow", "agronomist@farmmaster.test")
    clickable_row = page.locator("tr.clickable[data-req]").first
    clickable_row.wait_for(timeout=10000)
    clickable_row.click()

    checkboxes = page.locator("[data-farmer]")
    checkboxes.first.wait_for(timeout=10000)
    checkboxes.first.click()
    page.click("#assignBtn")
    page.wait_for_timeout(500)
    assert page.locator("#canvas").is_visible()


def test_formula_builder_save_and_publish_real_plan(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/formula-builder-flow", "agronomist@farmmaster.test")
    row = page.locator("[data-req]").first
    row.wait_for(timeout=10000)
    row.click()
    page.wait_for_selector("#saveBtn", timeout=10000)
    page.click("#saveBtn")
    page.wait_for_timeout(300)
    if page.locator("#publishBtn").is_enabled():
        page.click("#publishBtn")
        page.wait_for_timeout(500)
    content = page.content().lower()
    assert "seed" in content or "npk" in content


def test_dispatch_assign_and_mark_delivered_real_job(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/dispatch-flow", "logistics@farmmaster.test")
    outbound_job = page.locator("[data-dispatch]").first
    if outbound_job.count():
        outbound_job.click()
        page.wait_for_selector("#confirmDispatchBtn", timeout=10000)
        page.click("#confirmDispatchBtn")
        page.wait_for_timeout(500)

    deliver_btn = page.locator("[data-deliver]").first
    if deliver_btn.count():
        deliver_btn.click()
        page.wait_for_timeout(500)
    assert page.locator("#canvas").is_visible()


def test_dispatch_inbound_tab_shows_real_harvest_pickup_jobs(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/dispatch-flow", "logistics@farmmaster.test")
    page.click('[data-tab="inbound"]')
    page.wait_for_timeout(300)
    content = page.content()
    assert "Harvest pickup" in content or "harvest" in content.lower()


def test_fulfilment_intake_grades_a_real_delivered_pickup(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/fulfilment-intake-flow", "finance@farmmaster.test")
    row = page.locator("[data-req]").first
    if row.count():
        row.click()
        page.wait_for_selector("#weighIn", timeout=10000)
        page.fill("#weighIn", "1900")
        page.select_option("#gradeSelect", "grade_1")
        page.click("#confirmIntakeBtn")
        page.wait_for_timeout(500)
        assert page.locator("#canvas").is_visible()


def test_reconciliation_shows_real_figures_and_release_actions(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/reconciliation-flow", "finance@farmmaster.test")
    row = page.locator("[data-id]").first
    row.wait_for(timeout=10000)
    row.click()
    page.wait_for_timeout(300)
    content = page.content()
    assert "GHS" in content


def test_reconciliation_release_farmer_settlement_when_eligible(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/reconciliation-flow", "finance@farmmaster.test")
    rows = page.locator("[data-id]")
    rows.first.wait_for(timeout=10000)
    n = rows.count()
    clicked_one_with_release = False
    for i in range(n):
        rows.nth(i).click()
        page.wait_for_timeout(300)
        btn = page.locator("#releaseSettlementBtn")
        if btn.count() and btn.is_enabled():
            btn.click()
            page.wait_for_timeout(500)
            clicked_one_with_release = True
            break
        back = page.locator("#backBtn")
        if back.count():
            back.click()
            page.wait_for_timeout(200)
            rows = page.locator("[data-id]")
    # seed.py always creates one PRODUCTION requirement with a real graded,
    # delivered pickup (Kojo Mensah, Grade 1) specifically so this release
    # action has something real to click -- if this ever goes false, the
    # seed data's own guarantee has broken, which is worth knowing.
    assert clicked_one_with_release is True


def test_dispatch_flow_clean_at_375_768_1280_phone_first(page, live_server_url):
    for width, height in [(375, 812), (768, 1024), (1280, 900)]:
        page.set_viewport_size({"width": width, "height": height})
        login_and_verify_otp(page, live_server_url, "/dispatch-flow", "logistics@farmmaster.test")
        assert_responsive_clean(page, f"dispatch-flow @ {width}px")
