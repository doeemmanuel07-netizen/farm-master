"""Integration tests for routers/buyer.py -- PRD Section 6 Must-Have #1, plus the 8 Sep 2026 Dashboard/Docs/Tracking/Invoice screens."""

import pytest

from app.models import Role, GradeResult
from tests.conftest import login, auth_headers
from tests.factories import make_delivered_graded_pickup

pytestmark = pytest.mark.integration


def _submit_requirement(client, token, **overrides):
    payload = {
        "grade": "Grade 1", "quantity_tonnes": 2.0, "price_per_tonne": 2100.0,
        "delivery_location": "Tema", "delivery_timeline": "30 Sep 2026",
    }
    payload.update(overrides)
    res = client.post("/buyer/requirements", json=payload, headers=auth_headers(token))
    assert res.status_code == 200, res.text
    return res.json()


def test_submit_requirement_computes_commitment_fee_from_rate_config(client, roles, rate_config):
    token = login(client, roles[Role.BUYER].email)
    req = _submit_requirement(client, token, quantity_tonnes=2.0)
    assert req["commitment_fee_amount"] == 180.0  # 2.0 * 90.0
    assert req["status"] == "pending_payment"


def test_submit_requirement_enforces_minimum_fee_floor(client, roles, rate_config):
    """max(rate, qty * rate) -- a tiny order still pays at least one tonne's worth."""
    token = login(client, roles[Role.BUYER].email)
    req = _submit_requirement(client, token, quantity_tonnes=0.1)
    assert req["commitment_fee_amount"] == 90.0


def test_submit_requirement_rejects_zero_quantity(client, roles, rate_config):
    token = login(client, roles[Role.BUYER].email)
    res = client.post("/buyer/requirements", json={
        "grade": "Grade 1", "quantity_tonnes": 0, "price_per_tonne": 2100.0,
        "delivery_location": "Tema", "delivery_timeline": "30 Sep 2026",
    }, headers=auth_headers(token))
    assert res.status_code == 422


def test_pay_momo_succeeds_and_activates_matching(client, roles, rate_config):
    token = login(client, roles[Role.BUYER].email)
    req = _submit_requirement(client, token)
    pay = client.post(f"/buyer/requirements/{req['id']}/pay", json={"method": "momo"}, headers=auth_headers(token))
    assert pay.status_code == 200, pay.text
    assert pay.json()["status"] == "success"
    assert pay.json()["transaction_ref"].startswith("SIM-")

    fetched = client.get(f"/buyer/requirements/{req['id']}", headers=auth_headers(token))
    assert fetched.json()["status"] == "matching"


@pytest.mark.simulated
def test_pay_card_returns_501_not_a_silent_success(client, roles, rate_config):
    token = login(client, roles[Role.BUYER].email)
    req = _submit_requirement(client, token)
    pay = client.post(f"/buyer/requirements/{req['id']}/pay", json={"method": "card"}, headers=auth_headers(token))
    assert pay.status_code == 501
    assert "gateway" in pay.json()["detail"].lower()


def test_pay_unsupported_method_returns_422(client, roles, rate_config):
    token = login(client, roles[Role.BUYER].email)
    req = _submit_requirement(client, token)
    pay = client.post(f"/buyer/requirements/{req['id']}/pay", json={"method": "bitcoin"}, headers=auth_headers(token))
    assert pay.status_code == 422


def test_pay_twice_returns_409(client, roles, rate_config):
    token = login(client, roles[Role.BUYER].email)
    req = _submit_requirement(client, token)
    client.post(f"/buyer/requirements/{req['id']}/pay", json={"method": "momo"}, headers=auth_headers(token))
    second = client.post(f"/buyer/requirements/{req['id']}/pay", json={"method": "momo"}, headers=auth_headers(token))
    assert second.status_code == 409


def test_buyer_cannot_see_another_buyers_requirement(client, roles, rate_config, make_user):
    token_a = login(client, roles[Role.BUYER].email)
    req = _submit_requirement(client, token_a)

    buyer_b = make_user(Role.BUYER)
    token_b = login(client, buyer_b.email)
    res = client.get(f"/buyer/requirements/{req['id']}", headers=auth_headers(token_b))
    assert res.status_code == 404


def test_dashboard_reflects_real_stats(client, roles, rate_config):
    token = login(client, roles[Role.BUYER].email)
    _submit_requirement(client, token, quantity_tonnes=1.0)
    _submit_requirement(client, token, quantity_tonnes=2.0)
    dash = client.get("/buyer/dashboard", headers=auth_headers(token)).json()
    assert dash["active_orders"] == 2
    assert dash["commitment_fees_due"] == 2
    assert len(dash["recent_orders"]) == 2


def test_docs_tracking_invoice_reflect_real_graded_delivery(client, roles, rate_config, db_session, make_user):
    from tests.factories import make_requirement

    buyer = roles[Role.BUYER]
    farmer = make_user(Role.FARMER)
    finance = make_user(Role.FINANCE)
    req = make_requirement(db_session, buyer, price_per_tonne=2000.0, fee=180.0)
    make_delivered_graded_pickup(db_session, farmer, finance, requirement=req, weigh_in_kg=1000.0, grade=GradeResult.GRADE_1)

    token = login(client, buyer.email)
    docs = client.get(f"/buyer/requirements/{req.id}/docs", headers=auth_headers(token)).json()
    assert any(r["status"] == "verified" for r in docs["rows"])

    tracking = client.get(f"/buyer/requirements/{req.id}/tracking", headers=auth_headers(token)).json()
    assert tracking["accepted_delivered_tonnes"] == 1.0
    assert len(tracking["log"]) > 0

    invoice = client.get(f"/buyer/requirements/{req.id}/invoice", headers=auth_headers(token)).json()
    assert invoice["subtotal"] == 2000.0


def test_docs_for_nonexistent_order_returns_404(client, roles, rate_config):
    token = login(client, roles[Role.BUYER].email)
    res = client.get("/buyer/requirements/does-not-exist/docs", headers=auth_headers(token))
    assert res.status_code == 404


@pytest.mark.parametrize("wrong_role", [Role.FARMER, Role.VENDOR, Role.FINANCE, Role.SUPER_ADMIN])
def test_submit_requirement_blocked_for_non_buyer_roles(client, roles, rate_config, wrong_role):
    token = login(client, roles[wrong_role].email)
    res = client.post("/buyer/requirements", json={
        "grade": "Grade 1", "quantity_tonnes": 1.0, "price_per_tonne": 2000.0,
        "delivery_location": "Tema", "delivery_timeline": "30 Sep 2026",
    }, headers=auth_headers(token))
    assert res.status_code == 403
