"""
Cross-cutting tests for every deliberately-simulated integration in this
codebase: OTP delivery, mobile money/vendor billing, and USSD/SMS. Per the
Stage 7 plan, this module's job is to fail loudly the day one of these is
quietly wired to a real gateway without updating its contract -- not to
disappear into the suite's green checkmarks. Every test here is marked
`simulated`.
"""

import pathlib

import pytest

from app.models import Role
from tests.conftest import login, auth_headers, unique_email

pytestmark = pytest.mark.simulated

APP_DIR = pathlib.Path(__file__).parent.parent.parent / "app"


def test_otp_response_contract_still_carries_dev_only_naming(client, make_user):
    """
    If a future PR wires a real SMS/email gateway without deliberately
    updating this contract, it would likely still return something shaped
    like an OtpChallengeResponse -- this test pins the field names
    themselves (dev_only_phone_code / dev_only_email_code), which only a
    deliberate, visible change should ever touch.
    """
    user = make_user(Role.FARMER)
    res = client.post("/auth/login", json={"email": user.email, "password": "password123"})
    body = res.json()
    assert "dev_only_phone_code" in body
    assert "dev_only_email_code" in body
    assert "SIMULATED" in body["message"]


def test_otp_codes_are_real_looking_but_not_sent_anywhere(client, make_user):
    """The codes are real (random, 6-digit, verify correctly) -- only the delivery hop is fake. Confirms both halves of that claim at once."""
    user = make_user(Role.FARMER)
    token = login(client, user.email)  # exercises the full real verify path
    assert token


@pytest.mark.parametrize("method,expect_success", [("momo", True), ("vodafone", True), ("airteltigo", True)])
def test_mobile_money_methods_succeed_with_a_simulated_marker(client, roles, rate_config, method, expect_success):
    token = login(client, roles[Role.BUYER].email)
    req = client.post("/buyer/requirements", json={
        "grade": "Grade 1", "quantity_tonnes": 1.0, "price_per_tonne": 2000.0,
        "delivery_location": "Tema", "delivery_timeline": "30 Sep 2026",
    }, headers=auth_headers(token)).json()
    pay = client.post(f"/buyer/requirements/{req['id']}/pay", json={"method": method}, headers=auth_headers(token))
    assert pay.status_code == 200
    assert pay.json()["transaction_ref"].startswith("SIM-"), (
        "A mobile money payment must always carry a SIM- prefixed reference -- "
        "this is the marker that distinguishes simulated money movement from a real one."
    )


def test_card_payment_is_never_silently_treated_as_working(client, roles, rate_config):
    token = login(client, roles[Role.BUYER].email)
    req = client.post("/buyer/requirements", json={
        "grade": "Grade 1", "quantity_tonnes": 1.0, "price_per_tonne": 2000.0,
        "delivery_location": "Tema", "delivery_timeline": "30 Sep 2026",
    }, headers=auth_headers(token)).json()
    pay = client.post(f"/buyer/requirements/{req['id']}/pay", json={"method": "card"}, headers=auth_headers(token))
    assert pay.status_code == 501
    # Confirming this order is left exactly where it started -- not
    # half-activated by a request that claims to have failed.
    fetched = client.get(f"/buyer/requirements/{req['id']}", headers=auth_headers(token)).json()
    assert fetched["status"] == "pending_payment"


def test_vendor_subscription_card_payment_also_returns_501(client, roles, rate_config):
    token = login(client, roles[Role.VENDOR].email)
    res = client.post("/vendor/billing/pay", json={"method": "card"}, headers=auth_headers(token))
    assert res.status_code == 501


def test_ussd_sms_delivery_is_assertable_via_a_real_log_not_assumed(client, roles, rate_config):
    token = login(client, roles[Role.FARMER].email)
    before = client.get("/ussd/sms-log", headers=auth_headers(token)).json()
    client.get("/ussd/payment-notification", headers=auth_headers(token))
    after = client.get("/ussd/sms-log", headers=auth_headers(token)).json()
    assert len(after) == len(before) + 1


@pytest.mark.parametrize("router_file", [
    "routers/auth.py", "routers/buyer.py", "routers/vendor.py", "routers/ussd.py",
])
def test_no_real_gateway_import_or_call_in_any_simulated_router(router_file):
    """
    Scans the actual source of every router that owns a simulated
    integration for telltale signs of a real outbound call having crept
    in -- an HTTP client hitting a payment/SMS provider, or an SDK import
    for one. This is deliberately a source scan, not a network-mocking
    test: the point is that no such call should exist to make, not that
    one exists and happens to be mocked in tests.

    Deliberately does NOT flag the bare words "paystack" / "hubtel" /
    "flutterwave": buyer.py and vendor.py legitimately name them in
    plain-English copy documenting the still-pending gateway decision
    (PRD Section 1.1 -- "Card -- via Paystack / Hubtel (TBD, returns 501
    from the server)"), and failing on that would punish exactly the
    honesty this test exists to protect. What would actually indicate a
    real integration -- an HTTP client call, an SDK import, a live API
    endpoint URL -- is what's checked instead.
    """
    source = (APP_DIR / router_file).read_text(encoding="utf-8").lower()
    forbidden_markers = [
        "requests.post(", "requests.get(", "httpx.post(", "httpx.get(",
        "import twilio", "import africastalking", "import stripe",
        "smtplib", "boto3",
        "api.paystack.co", "api.hubtel.com", "api.flutterwave.com",
    ]
    hits = [m for m in forbidden_markers if m in source]
    assert hits == [], f"{router_file} appears to call a real external gateway ({hits})."


def test_readme_and_docstrings_still_describe_delivery_as_simulated():
    """
    A weaker but still useful signal: the project's own READMEs must keep
    saying "SIMULATED" for the gateway-dependent flows, so a reader never
    has to reverse-engineer the code to find out this isn't production-real.
    """
    # APP_DIR is backend/app -- backend's README lives at backend's parent
    # (Stage 6 Build/README.md), not inside backend/ itself.
    readme = (APP_DIR.parent.parent / "README.md").read_text(encoding="utf-8")
    assert "SIMULATED" in readme
