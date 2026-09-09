"""Integration tests for routers/admin.py -- role changes, registration approval, rate config, and User & Role Admin (account creation/suspend/reactivate). Every action here should write a real audit-log entry, per PRD Section 5."""

import pytest

from app.models import Role, UserStatus
from tests.conftest import login, auth_headers, unique_email

pytestmark = pytest.mark.integration


def _audit_actions(client, token):
    return [e["action"] for e in client.get("/admin/audit-log", headers=auth_headers(token)).json()]


def test_change_role_writes_audit_entry(client, roles, rate_config, make_user):
    target = make_user(Role.LOGISTICS)
    token = login(client, roles[Role.SUPER_ADMIN].email)
    res = client.put(f"/admin/users/{target.id}/role", json={"new_role": "agronomist"}, headers=auth_headers(token))
    assert res.status_code == 200
    assert res.json()["role"] == "agronomist"
    assert "role_changed" in _audit_actions(client, token)


def test_create_internal_user_rejects_self_registering_role(client, roles, rate_config):
    token = login(client, roles[Role.SUPER_ADMIN].email)
    res = client.post("/admin/users", json={
        "full_name": "Sneaky", "email": unique_email("sneaky"), "phone": "+233240000099",
        "role": "farmer", "password": "password123",
    }, headers=auth_headers(token))
    assert res.status_code == 422


def test_create_internal_user_active_immediately_no_otp_and_audited(client, roles, rate_config):
    token = login(client, roles[Role.SUPER_ADMIN].email)
    email = unique_email("newfinance")
    res = client.post("/admin/users", json={
        "full_name": "New Finance", "email": email, "phone": "+233240000098",
        "role": "finance", "password": "password123",
    }, headers=auth_headers(token))
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "active"
    assert "internal_user_created" in _audit_actions(client, token)

    # Can log in immediately -- login itself is still OTP-gated, but no
    # registration OTP was ever required to reach ACTIVE.
    from tests.conftest import login as do_login

    login_token = do_login(client, email)
    assert login_token


def test_create_internal_user_duplicate_email_returns_409(client, roles, rate_config, make_user):
    existing = make_user(Role.FINANCE)
    token = login(client, roles[Role.SUPER_ADMIN].email)
    res = client.post("/admin/users", json={
        "full_name": "Dup", "email": existing.email, "phone": "+233240000097",
        "role": "finance", "password": "password123",
    }, headers=auth_headers(token))
    assert res.status_code == 409


def test_suspend_then_reactivate_lifecycle_and_no_op_409s(client, roles, rate_config, make_user):
    target = make_user(Role.FARMER)
    token = login(client, roles[Role.SUPER_ADMIN].email)

    suspend = client.post(f"/admin/users/{target.id}/suspend", headers=auth_headers(token))
    assert suspend.status_code == 200
    assert suspend.json()["status"] == "suspended"

    suspend_again = client.post(f"/admin/users/{target.id}/suspend", headers=auth_headers(token))
    assert suspend_again.status_code == 409

    reactivate = client.post(f"/admin/users/{target.id}/reactivate", headers=auth_headers(token))
    assert reactivate.status_code == 200
    assert reactivate.json()["status"] == "active"

    reactivate_again = client.post(f"/admin/users/{target.id}/reactivate", headers=auth_headers(token))
    assert reactivate_again.status_code == 409

    actions = _audit_actions(client, token)
    assert "account_suspended" in actions
    assert "account_reactivated" in actions


def test_suspended_account_actually_fails_login_not_just_a_badge(client, roles, rate_config, make_user):
    target = make_user(Role.FARMER)
    token = login(client, roles[Role.SUPER_ADMIN].email)
    client.post(f"/admin/users/{target.id}/suspend", headers=auth_headers(token))

    login_attempt = client.post("/auth/login", json={"email": target.email, "password": "password123"})
    assert login_attempt.status_code == 403


def test_users_list_splits_internal_and_external_correctly(client, roles, rate_config):
    token = login(client, roles[Role.SUPER_ADMIN].email)
    listing = client.get("/admin/users", headers=auth_headers(token)).json()
    internal_roles = {u["role"] for u in listing["internal"]}
    external_roles = {u["role"] for u in listing["external"]}
    assert internal_roles.issubset({
        "agronomist", "logistics", "finance", "super_admin",
        "operations_coordinator", "compliance_officer",
    })
    assert external_roles.issubset({"farmer", "buyer", "vendor"})


def test_users_list_carries_verbatim_scope_label_for_internal_roles(client, roles, rate_config):
    token = login(client, roles[Role.SUPER_ADMIN].email)
    listing = client.get("/admin/users", headers=auth_headers(token)).json()
    finance_row = next(u for u in listing["internal"] if u["role"] == "finance")
    assert finance_row["scope"] == "Reconciliation, reporting, MoFA export — no account/role admin"


def test_rate_update_writes_audit_entry_and_is_reflected_immediately(client, roles, rate_config):
    token = login(client, roles[Role.SUPER_ADMIN].email)
    res = client.put("/admin/rates/trading_margin_pct", json={"value": 0.2}, headers=auth_headers(token))
    assert res.status_code == 200
    assert res.json()["value"] == 0.2
    assert "rate_config_changed" in _audit_actions(client, token)


def test_rate_update_unknown_key_returns_404(client, roles, rate_config):
    token = login(client, roles[Role.SUPER_ADMIN].email)
    res = client.put("/admin/rates/not_a_real_rate", json={"value": 1.0}, headers=auth_headers(token))
    assert res.status_code == 404


def test_audit_log_has_no_write_endpoints(client, roles, rate_config):
    """Read-only by design -- there is deliberately no PUT/DELETE anywhere for this table."""
    import inspect
    from app.routers import admin as admin_router

    methods = {route.path: route.methods for route in admin_router.router.routes}
    audit_methods = methods.get("/admin/audit-log", set())
    assert audit_methods == {"GET"}


@pytest.mark.parametrize("wrong_role", [Role.FINANCE, Role.LOGISTICS, Role.VENDOR, Role.FARMER, Role.AGRONOMIST])
def test_finance_and_every_other_non_admin_role_blocked_from_admin_routes(client, roles, rate_config, wrong_role):
    """Explicit segregation-of-duties check: Finance can move money but must never also grant permissions."""
    token = login(client, roles[wrong_role].email)
    for path in ["/admin/users", "/admin/registrations", "/admin/audit-log", "/admin/rates"]:
        res = client.get(path, headers=auth_headers(token))
        assert res.status_code == 403, f"{wrong_role.value} should be 403 on {path}"
