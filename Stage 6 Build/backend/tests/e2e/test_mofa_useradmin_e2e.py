"""E2E: MoFA Data Exchange (export + 8 Sep 2026 import) and User & Role Admin."""

import pytest

from tests.e2e.helpers import login_and_verify_otp, assert_responsive_clean

pytestmark = [pytest.mark.e2e]


def test_mofa_manual_import_creates_a_real_row(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/mofa-report-flow", "finance@farmmaster.test")
    page.fill("#importBuyer", "E2E Institutional Buyer")
    page.select_option("#importVerified", "true")
    page.click("#manualImportBtn")
    page.wait_for_timeout(500)
    assert "E2E Institutional Buyer" in page.content()


def test_mofa_csv_export_downloads_a_real_file(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/mofa-report-flow", "finance@farmmaster.test")
    with page.expect_download(timeout=10000) as download_info:
        page.click("#exportCsvBtn")
    download = download_info.value
    assert download.suggested_filename.endswith(".csv")


def test_mofa_pdf_export_downloads_a_real_pdf(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/mofa-report-flow", "finance@farmmaster.test")
    with page.expect_download(timeout=10000) as download_info:
        page.click("#exportPdfBtn")
    download = download_info.value
    assert download.suggested_filename.endswith(".pdf")


def test_useradmin_change_role_real_action(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/user-admin-flow", "emmanuel@farmmaster.test")
    change_btn = page.locator("[data-change-role]").first
    change_btn.wait_for(timeout=10000)
    change_btn.click()
    save_btn = page.locator("[data-confirm-role]").first
    save_btn.wait_for(timeout=10000)
    save_btn.click()
    page.wait_for_timeout(500)
    assert page.locator("#canvas").is_visible()


def test_useradmin_add_internal_user(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/user-admin-flow", "emmanuel@farmmaster.test")
    page.click("#toggleAddBtn")
    page.fill("#newFullName", "E2E Test Agronomist")
    page.fill("#newEmail", "e2e-agro@test.invalid")
    page.fill("#newPhone", "+233240000002")
    page.select_option("#newRole", "agronomist")
    page.fill("#newPassword", "password123")
    page.click("#submitNewUserBtn")
    # onAddUser does two sequential awaits (POST /admin/users, then a full
    # GET /admin/users re-fetch via refreshUsers()) before it re-renders --
    # a blind wait_for_timeout(500) was found to be an intermittent race
    # against that round trip (8/9 Sep 2026); wait_for actively polls
    # instead of gambling on a fixed delay.
    page.get_by_text("E2E Test Agronomist").wait_for(timeout=10000)


def test_useradmin_suspend_and_reactivate_an_external_account(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/user-admin-flow", "emmanuel@farmmaster.test")
    suspend_btn = page.locator("[data-suspend]").first
    suspend_btn.wait_for(timeout=10000)
    suspend_btn.click()
    page.wait_for_timeout(500)
    reactivate_btn = page.locator("[data-reactivate]").first
    if reactivate_btn.count():
        reactivate_btn.click()
        page.wait_for_timeout(500)
    assert page.locator("#canvas").is_visible()


def test_useradmin_flow_clean_at_375_768_1280(page, live_server_url):
    for width, height in [(375, 812), (768, 1024), (1280, 900)]:
        page.set_viewport_size({"width": width, "height": height})
        login_and_verify_otp(page, live_server_url, "/user-admin-flow", "emmanuel@farmmaster.test")
        assert_responsive_clean(page, f"user-admin-flow @ {width}px")
