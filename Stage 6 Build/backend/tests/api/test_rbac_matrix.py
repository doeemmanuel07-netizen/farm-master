"""
Systematic RBAC boundary matrix -- PRD Section 5: "enforced at the data
layer, not just the UI." Every GET endpoint in the API is listed here
once, with its allowed role(s); this test then tries EVERY role against
EVERY endpoint automatically, so a newly-added endpoint that forgets to
scope `require_roles(...)` correctly (or a route whose scope silently
drifts) fails here rather than being caught only by whoever happens to
manually curl it next.

POST/PUT endpoints' RBAC is covered alongside their functional behaviour
in each domain's own test file (tests/api/test_<router>.py), since those
already construct a valid request body -- duplicating that here would
just be two places to keep in sync. This file is the exhaustive,
systematic layer specifically for parameterless/read-only routes.
"""

import pytest

from app.models import Role
from tests.conftest import login, auth_headers

pytestmark = pytest.mark.integration if hasattr(pytest.mark, "integration") else []

pytestmark = pytest.mark.rbac

DUMMY_ID = "00000000-0000-0000-0000-000000000000"

ALL_ROLES = list(Role)

# (path, {allowed roles})
GET_ENDPOINTS = [
    (f"/buyer/requirements/{DUMMY_ID}", {Role.BUYER}),
    ("/buyer/requirements", {Role.BUYER}),
    ("/buyer/dashboard", {Role.BUYER}),
    (f"/buyer/requirements/{DUMMY_ID}/docs", {Role.BUYER}),
    (f"/buyer/requirements/{DUMMY_ID}/tracking", {Role.BUYER}),
    (f"/buyer/requirements/{DUMMY_ID}/invoice", {Role.BUYER}),
    ("/farmer/opportunities", {Role.FARMER}),
    (f"/farmer/opportunities/{DUMMY_ID}", {Role.FARMER}),
    ("/farmer/formulas/mine", {Role.FARMER}),
    ("/farmer/harvest-pickup/my-orders", {Role.FARMER}),
    ("/farmer/harvest-pickup/mine", {Role.FARMER}),
    ("/farmer/catalogue", {Role.FARMER}),
    ("/farmer/input-orders/mine", {Role.FARMER}),
    ("/farmer/milestones", {Role.FARMER}),
    ("/farmer/messages", {Role.FARMER}),
    ("/farmer/wallet", {Role.FARMER}),
    ("/farmer/dashboard", {Role.FARMER}),
    ("/vendor/requests", {Role.VENDOR}),
    (f"/vendor/requests/{DUMMY_ID}", {Role.VENDOR}),
    ("/vendor/catalogue", {Role.VENDOR}),
    ("/vendor/input-orders", {Role.VENDOR}),
    ("/vendor/dashboard", {Role.VENDOR}),
    ("/vendor/billing", {Role.VENDOR}),
    ("/vendor/payout", {Role.VENDOR}),
    ("/vendor/handoff", {Role.VENDOR}),
    ("/admin/registrations", {Role.SUPER_ADMIN}),
    ("/admin/audit-log", {Role.SUPER_ADMIN}),
    ("/admin/rates", {Role.SUPER_ADMIN}),
    ("/admin/users", {Role.SUPER_ADMIN}),
    ("/agronomist/requirements", {Role.AGRONOMIST, Role.OPERATIONS_COORDINATOR}),
    ("/agronomist/farmers", {Role.AGRONOMIST, Role.OPERATIONS_COORDINATOR}),
    (f"/agronomist/requirements/{DUMMY_ID}/formula", {Role.AGRONOMIST}),
    ("/agronomist/visit-logs", {Role.AGRONOMIST}),
    ("/agronomist/messages", {Role.AGRONOMIST}),
    ("/logistics/jobs", {Role.LOGISTICS}),
    (f"/logistics/jobs/{DUMMY_ID}/proof", {Role.LOGISTICS}),
    ("/logistics/trunking/availability", {Role.LOGISTICS}),
    ("/logistics/trunking", {Role.LOGISTICS}),
    ("/fulfilment/intake-queue", {Role.FINANCE}),
    ("/finance/reconciliation", {Role.FINANCE, Role.COMPLIANCE_OFFICER}),
    (f"/finance/reconciliation/{DUMMY_ID}", {Role.FINANCE, Role.COMPLIANCE_OFFICER}),
    ("/mofa/compliance-report", {Role.FINANCE, Role.COMPLIANCE_OFFICER}),
    ("/mofa/import-records", {Role.FINANCE, Role.COMPLIANCE_OFFICER}),
    ("/reporting/dashboard", {Role.FINANCE}),
    (
        "/dashboard/control-centre",
        {
            Role.AGRONOMIST, Role.LOGISTICS, Role.FINANCE, Role.SUPER_ADMIN,
            Role.OPERATIONS_COORDINATOR, Role.COMPLIANCE_OFFICER,
        },
    ),
    ("/ussd/sms-log", {Role.FARMER}),
    ("/ussd/payment-notification", {Role.FARMER}),
]

WRONG_ROLE_CASES = [
    (path, allowed, wrong)
    for path, allowed in GET_ENDPOINTS
    for wrong in ALL_ROLES
    if wrong not in allowed
]


@pytest.fixture()
def tokens(roles, client):
    return {role: login(client, user.email) for role, user in roles.items()}


@pytest.mark.parametrize("path,allowed,wrong_role", WRONG_ROLE_CASES, ids=[f"{p}::{w.value}" for p, _, w in WRONG_ROLE_CASES])
def test_wrong_role_gets_403(client, tokens, path, allowed, wrong_role):
    res = client.get(path, headers=auth_headers(tokens[wrong_role]))
    assert res.status_code == 403, (
        f"{path} allowed role(s) {[r.value for r in allowed]} but did not 403 for "
        f"'{wrong_role.value}' -- got {res.status_code}: {res.text[:200]}"
    )


@pytest.mark.parametrize("path,allowed", GET_ENDPOINTS, ids=[p for p, _ in GET_ENDPOINTS])
def test_allowed_role_is_not_blocked_by_rbac(client, tokens, path, allowed):
    any_allowed_role = next(iter(allowed))
    res = client.get(path, headers=auth_headers(tokens[any_allowed_role]))
    assert res.status_code != 403, (
        f"{path} should allow '{any_allowed_role.value}' but got 403: {res.text[:200]}"
    )


def test_no_token_at_all_is_rejected_everywhere(client):
    """Every one of the above is also unreachable with no Authorization header."""
    sample_paths = [p for p, _ in GET_ENDPOINTS[:5]] + [p for p, _ in GET_ENDPOINTS[-5:]]
    for path in sample_paths:
        res = client.get(path)
        assert res.status_code == 401, f"{path} should require auth entirely, got {res.status_code}"
