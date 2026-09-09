"""Integration tests for routers/reconciliation.py -- PRD Section 6 Must-Have #5, the release actions specifically (compute_figures itself is covered in tests/unit/test_reconciliation.py)."""

import pytest

from app.models import Role, GradeResult, RequirementStatus
from tests.conftest import login, auth_headers
from tests.factories import make_requirement, make_delivered_graded_pickup, make_confirmed_mechanisation_request

pytestmark = pytest.mark.integration


def test_release_farmer_settlement_requires_real_delivered_tonnage(client, roles, rate_config, db_session, make_user):
    buyer = make_user(Role.BUYER)
    req = make_requirement(db_session, buyer, status=RequirementStatus.MATCHING)
    token = login(client, roles[Role.FINANCE].email)
    res = client.post(f"/finance/reconciliation/{req.id}/release-farmer-settlement", headers=auth_headers(token))
    assert res.status_code == 409


def test_release_farmer_settlement_succeeds_then_409s_on_second_release(client, roles, rate_config, db_session, make_user):
    buyer = make_user(Role.BUYER)
    farmer = make_user(Role.FARMER)
    finance = roles[Role.FINANCE]
    req = make_requirement(db_session, buyer, status=RequirementStatus.MATCHING)
    make_delivered_graded_pickup(db_session, farmer, finance, requirement=req, weigh_in_kg=1000.0, grade=GradeResult.GRADE_1)

    token = login(client, finance.email)
    first = client.post(f"/finance/reconciliation/{req.id}/release-farmer-settlement", headers=auth_headers(token))
    assert first.status_code == 200, first.text
    assert first.json()["farmer_settlement_released"] is True

    second = client.post(f"/finance/reconciliation/{req.id}/release-farmer-settlement", headers=auth_headers(token))
    assert second.status_code == 409


def test_release_vendor_payout_requires_real_confirmed_vendor_activity(client, roles, rate_config, db_session, make_user):
    buyer = make_user(Role.BUYER)
    req = make_requirement(db_session, buyer, status=RequirementStatus.MATCHING)
    token = login(client, roles[Role.FINANCE].email)
    res = client.post(f"/finance/reconciliation/{req.id}/release-vendor-payout", headers=auth_headers(token))
    assert res.status_code == 409


def test_release_vendor_payout_succeeds_then_409s_on_second_release(client, roles, rate_config, db_session, make_user):
    buyer = make_user(Role.BUYER)
    vendor = make_user(Role.VENDOR)
    req = make_requirement(db_session, buyer, status=RequirementStatus.MATCHING)
    make_confirmed_mechanisation_request(db_session, vendor, requirement=req, area_acres=1.0)

    token = login(client, roles[Role.FINANCE].email)
    first = client.post(f"/finance/reconciliation/{req.id}/release-vendor-payout", headers=auth_headers(token))
    assert first.status_code == 200, first.text
    second = client.post(f"/finance/reconciliation/{req.id}/release-vendor-payout", headers=auth_headers(token))
    assert second.status_code == 409


def test_order_not_yet_eligible_returns_404(client, roles, rate_config, db_session, make_user):
    buyer = make_user(Role.BUYER)
    req = make_requirement(db_session, buyer, status=RequirementStatus.DRAFT)
    token = login(client, roles[Role.FINANCE].email)
    res = client.get(f"/finance/reconciliation/{req.id}", headers=auth_headers(token))
    assert res.status_code == 404


def test_list_orders_only_shows_matching_or_later(client, roles, rate_config, db_session, make_user):
    buyer = make_user(Role.BUYER)
    make_requirement(db_session, buyer, status=RequirementStatus.DRAFT)
    eligible = make_requirement(db_session, buyer, status=RequirementStatus.MATCHING)
    token = login(client, roles[Role.FINANCE].email)
    orders = client.get("/finance/reconciliation", headers=auth_headers(token)).json()
    assert [o["buyer_requirement_id"] for o in orders] == [eligible.id]


@pytest.mark.parametrize("wrong_role", [Role.LOGISTICS, Role.VENDOR, Role.FARMER, Role.SUPER_ADMIN, Role.AGRONOMIST])
def test_release_endpoints_blocked_for_non_finance_roles(client, roles, rate_config, db_session, make_user, wrong_role):
    buyer = make_user(Role.BUYER)
    req = make_requirement(db_session, buyer, status=RequirementStatus.MATCHING)
    token = login(client, roles[wrong_role].email)
    res = client.post(f"/finance/reconciliation/{req.id}/release-farmer-settlement", headers=auth_headers(token))
    assert res.status_code == 403
