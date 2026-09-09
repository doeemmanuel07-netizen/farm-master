"""
E2E: the USSD/SMS channel session emulator (8 Sep 2026). This screen is
where the real bug in Stage 6 was found (the inactivity timer restarting
itself after "SESSION EXPIRED") -- these tests specifically re-verify that
fix stays fixed, plus drive the full numbered-menu session for real.
"""

import pytest

from tests.e2e.helpers import login_and_verify_otp, assert_responsive_clean

pytestmark = [pytest.mark.e2e, pytest.mark.simulated]


def _send(page, text):
    page.fill("#ussdInput", text)
    page.click("#ussdSendBtn")
    page.wait_for_timeout(300)


def test_ussd_main_menu_renders_after_login(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/ussd-sms-flow", "kojo.mensah@farmmaster.test")
    content = page.locator("#phoneScreen").inner_text()
    assert "FARM MASTER" in content
    assert "1. Opportunities" in content


def test_ussd_opportunities_menu_lists_real_data_and_pushes_a_real_sms(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/ussd-sms-flow", "kojo.mensah@farmmaster.test")
    _send(page, "1")
    screen = page.locator("#phoneScreen").inner_text()
    assert "0. Back" in screen

    _send(page, "1")  # view first opportunity's detail -- triggers a real push-alert
    page.wait_for_timeout(300)
    sms_panel = page.locator(".sms-panel").inner_text()
    assert "OPPORTUNITY ALERT" in sms_panel.upper() or "opportunity_alert" in sms_panel.lower()


def test_ussd_pickup_confirmation_creates_a_real_pickup_and_sms(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/ussd-sms-flow", "ama.serwaa@farmmaster.test")
    _send(page, "2")
    page.wait_for_selector("#pickupQty", timeout=10000)
    page.fill("#pickupQty", "1.5")
    page.fill("#pickupDate", "2026-09-29")
    page.click("#pickupSendBtn")
    page.wait_for_timeout(500)
    screen = page.locator("#phoneScreen").inner_text()
    assert "Pickup confirmed" in screen
    sms_panel = page.locator(".sms-panel").inner_text()
    assert "PICKUP CONFIRMATION" in sms_panel.upper()


def test_ussd_payment_balance_check_and_sms_log(page, live_server_url):
    login_and_verify_otp(page, live_server_url, "/ussd-sms-flow", "kojo.mensah@farmmaster.test")
    _send(page, "3")
    screen = page.locator("#phoneScreen").inner_text()
    assert "BALANCE" in screen.upper()

    _send(page, "0")
    _send(page, "4")
    screen = page.locator("#phoneScreen").inner_text()
    assert "payment_notification" in screen or "PAYMENT" in screen.upper()


def test_ussd_session_expires_and_recovers_without_restarting_the_timer(page, live_server_url):
    """
    Regression test for the real bug found and fixed in Stage 6: the
    session timer used to keep counting down even after showing
    "SESSION EXPIRED" (renderUssd() called startSessionTimer()
    unconditionally). This confirms the timer actually stops at 0 and
    stays stopped until the farmer deliberately dials back in.
    """
    login_and_verify_otp(page, live_server_url, "/ussd-sms-flow", "kojo.mensah@farmmaster.test")

    # Force expiry deterministically rather than waiting out the real
    # 45-second countdown: drive the countdown down via the page's own
    # setInterval by advancing wall-clock time is not available without a
    # clock mock, so instead assert the invariant directly against the
    # rendered state after actually waiting for it once.
    page.wait_for_timeout(46000)
    screen = page.locator("#phoneScreen").inner_text()
    assert "SESSION EXPIRED" in screen

    timer_text_1 = page.locator("#sessionTimer").inner_text()
    page.wait_for_timeout(2000)
    timer_text_2 = page.locator("#sessionTimer").inner_text()
    assert timer_text_1 == timer_text_2 == "0s", (
        "Session timer must stop at 0s on expiry, not keep counting -- "
        f"got {timer_text_1!r} then {timer_text_2!r}."
    )

    _send(page, "anything")
    screen_after = page.locator("#phoneScreen").inner_text()
    assert "FARM MASTER" in screen_after
    assert "1. Opportunities" in screen_after


def test_ussd_flow_clean_at_375_768_1280(page, live_server_url):
    for width, height in [(375, 812), (768, 1024), (1280, 900)]:
        page.set_viewport_size({"width": width, "height": height})
        login_and_verify_otp(page, live_server_url, "/ussd-sms-flow", "farmer@farmmaster.test")
        assert_responsive_clean(page, f"ussd-sms-flow @ {width}px")
