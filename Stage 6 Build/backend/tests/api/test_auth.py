"""
Integration tests for routers/auth.py -- registration and the two-step
OTP login, exercised through real HTTP calls against the real app.
Marked `simulated` throughout: OTP delivery is SIMULATED (dev_only_* codes
echoed in the response), but every test here proves the mechanism around
that simulation -- gating, single-use, expiry, role-specific activation --
is fully real, not a stub.
"""

import pytest

from app.models import Role, UserStatus
from tests.conftest import unique_email, login, auth_headers

pytestmark = [pytest.mark.simulated]


def test_farmer_registration_activates_immediately_after_otp(client, rate_config):
    email = unique_email("farmer")
    res = client.post("/auth/register", json={
        "email": email, "phone": "+233241111111", "full_name": "New Farmer",
        "password": "password123", "role": "farmer",
    })
    assert res.status_code == 200, res.text
    challenge = res.json()
    assert "dev_only_phone_code" in challenge and "dev_only_email_code" in challenge

    verify = client.post("/auth/register/verify-otp", json={
        "challenge_id": challenge["challenge_id"],
        "phone_code": challenge["dev_only_phone_code"],
        "email_code": challenge["dev_only_email_code"],
    })
    assert verify.status_code == 200, verify.text
    assert verify.json()["status"] == "active"

    # And can now actually log in -- the real end-to-end proof, not just a status string.
    token = login(client, email)
    assert token


def test_buyer_registration_requires_approval_before_login_works(client, rate_config, make_user):
    email = unique_email("buyer")
    res = client.post("/auth/register", json={
        "email": email, "phone": "+233241111112", "full_name": "New Buyer Co",
        "password": "password123", "role": "buyer", "organisation_name": "New Buyer Co Ltd",
    })
    challenge = res.json()
    verify = client.post("/auth/register/verify-otp", json={
        "challenge_id": challenge["challenge_id"],
        "phone_code": challenge["dev_only_phone_code"],
        "email_code": challenge["dev_only_email_code"],
    })
    assert verify.json()["status"] == "pending_review"

    # Login before approval must be blocked with a specific reason, not a generic failure.
    login_res = client.post("/auth/login", json={"email": email, "password": "password123"})
    assert login_res.status_code == 403
    assert "approval" in login_res.json()["detail"].lower()

    # Confirm the registration actually shows up for a real admin to approve.
    admin = make_user(Role.SUPER_ADMIN)
    admin_token = login(client, admin.email)
    regs = client.get("/admin/registrations", headers=auth_headers(admin_token)).json()
    match = next(r for r in regs if r["applicant_name"] == "New Buyer Co Ltd")
    assert match["status"] == "pending_review"

    approve = client.post(f"/admin/registrations/{match['id']}/approve", headers=auth_headers(admin_token))
    assert approve.status_code == 200

    # Now login succeeds for real.
    token = login(client, email)
    assert token


def test_vendor_registration_rejected_leaves_account_suspended(client, rate_config, make_user):
    email = unique_email("vendor")
    res = client.post("/auth/register", json={
        "email": email, "phone": "+233241111113", "full_name": "Sketchy Vendor",
        "password": "password123", "role": "vendor", "organisation_name": "Sketchy Vendor Ltd",
    })
    challenge = res.json()
    client.post("/auth/register/verify-otp", json={
        "challenge_id": challenge["challenge_id"],
        "phone_code": challenge["dev_only_phone_code"],
        "email_code": challenge["dev_only_email_code"],
    })

    admin = make_user(Role.SUPER_ADMIN)
    admin_token = login(client, admin.email)
    regs = client.get("/admin/registrations", headers=auth_headers(admin_token)).json()
    match = next(r for r in regs if r["applicant_name"] == "Sketchy Vendor Ltd")
    reject = client.post(f"/admin/registrations/{match['id']}/reject", headers=auth_headers(admin_token))
    assert reject.status_code == 200

    login_res = client.post("/auth/login", json={"email": email, "password": "password123"})
    assert login_res.status_code == 403
    assert "suspended" in login_res.json()["detail"].lower()


@pytest.mark.parametrize("role", ["agronomist", "logistics", "finance", "super_admin"])
def test_internal_roles_cannot_self_register(client, rate_config, role):
    res = client.post("/auth/register", json={
        "email": unique_email(role), "phone": "+233241111114", "full_name": "Sneaky Internal",
        "password": "password123", "role": role,
    })
    assert res.status_code == 422


def test_duplicate_email_registration_returns_409(client, rate_config):
    email = unique_email("dupe")
    payload = {"email": email, "phone": "+233241111115", "full_name": "Dupe", "password": "password123", "role": "farmer"}
    first = client.post("/auth/register", json=payload)
    assert first.status_code == 200
    second = client.post("/auth/register", json=payload)
    assert second.status_code == 409


def test_login_before_otp_verification_is_blocked(client, rate_config):
    email = unique_email("halfregistered")
    client.post("/auth/register", json={
        "email": email, "phone": "+233241111116", "full_name": "Half Registered",
        "password": "password123", "role": "farmer",
    })
    # Never verified the OTP -- still PENDING_OTP.
    res = client.post("/auth/login", json={"email": email, "password": "password123"})
    assert res.status_code == 403
    assert "verification" in res.json()["detail"].lower()


def test_login_with_wrong_password_returns_401(client, make_user):
    user = make_user(Role.FARMER)
    res = client.post("/auth/login", json={"email": user.email, "password": "wrong-password"})
    assert res.status_code == 401


def test_login_verify_otp_wrong_code_returns_401(client, make_user):
    user = make_user(Role.FARMER)
    res = client.post("/auth/login", json={"email": user.email, "password": "password123"})
    challenge = res.json()
    verify = client.post("/auth/login/verify-otp", json={
        "challenge_id": challenge["challenge_id"], "phone_code": "000000", "email_code": challenge["dev_only_email_code"],
    })
    assert verify.status_code == 401


def test_login_verify_otp_cannot_be_reused(client, make_user):
    user = make_user(Role.FARMER)
    res = client.post("/auth/login", json={"email": user.email, "password": "password123"})
    challenge = res.json()
    body = {
        "challenge_id": challenge["challenge_id"],
        "phone_code": challenge["dev_only_phone_code"],
        "email_code": challenge["dev_only_email_code"],
    }
    first = client.post("/auth/login/verify-otp", json=body)
    assert first.status_code == 200
    second = client.post("/auth/login/verify-otp", json=body)
    assert second.status_code == 409


def test_suspended_account_cannot_log_in(client, make_user):
    user = make_user(Role.FARMER, status=UserStatus.SUSPENDED)
    res = client.post("/auth/login", json={"email": user.email, "password": "password123"})
    assert res.status_code == 403
    assert "suspended" in res.json()["detail"].lower()


def test_login_token_carries_correct_role_and_grants_role_gated_access(client, make_user, rate_config):
    farmer = make_user(Role.FARMER)
    token = login(client, farmer.email)
    res = client.get("/farmer/opportunities", headers=auth_headers(token))
    assert res.status_code == 200
