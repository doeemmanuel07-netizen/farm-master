"""Integration tests for routers/vendor.py -- mechanisation requests + the date-conflict override, Product Catalogue/Input Orders (Must-Have #3's literal scope), plus 8 Sep 2026's Dashboard/Billing/Payout/Handoff."""

import pytest

from app.models import Role
from tests.conftest import login, auth_headers
from tests.factories import make_product

pytestmark = pytest.mark.integration


def _seed_mech_request(db_session, vendor, requested_by_date="2026-09-30"):
    from app.models import MechanisationRequest

    req = MechanisationRequest(
        vendor_id=vendor.id, farmer_name="Kojo Mensah", service="Ploughing",
        area_acres=1.5, requested_by_date=requested_by_date,
    )
    db_session.add(req)
    db_session.commit()
    db_session.refresh(req)
    return req


def test_confirm_within_window_creates_real_dispatch_job(client, roles, rate_config, db_session):
    req = _seed_mech_request(db_session, roles[Role.VENDOR])
    token = login(client, roles[Role.VENDOR].email)
    res = client.post(f"/vendor/requests/{req.id}/confirm", json={"confirmed_date": "2026-09-20"}, headers=auth_headers(token))
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "confirmed"

    logi_token = login(client, roles[Role.LOGISTICS].email)
    jobs = client.get("/logistics/jobs", headers=auth_headers(logi_token)).json()
    assert any(j["job_type"] == "mechanisation" for j in jobs)


def test_confirm_outside_window_needs_override_not_finalised(client, roles, rate_config, db_session):
    req = _seed_mech_request(db_session, roles[Role.VENDOR], requested_by_date="2026-09-20")
    token = login(client, roles[Role.VENDOR].email)
    res = client.post(f"/vendor/requests/{req.id}/confirm", json={"confirmed_date": "2026-10-05"}, headers=auth_headers(token))
    assert res.status_code == 200
    body = res.json()
    assert body["override_needed"] is True
    assert body["status"] == "pending"  # NOT confirmed by the vendor's own action


def test_vendor_cannot_approve_its_own_override(client, roles, rate_config, db_session):
    """There is no vendor-facing override-approval route at all -- only /admin/vendor-requests/.../approve-override, Super Admin only."""
    req = _seed_mech_request(db_session, roles[Role.VENDOR], requested_by_date="2026-09-20")
    token = login(client, roles[Role.VENDOR].email)
    client.post(f"/vendor/requests/{req.id}/confirm", json={"confirmed_date": "2026-10-05"}, headers=auth_headers(token))
    blocked = client.post(f"/admin/vendor-requests/{req.id}/approve-override", headers=auth_headers(token))
    assert blocked.status_code == 403


def test_super_admin_approves_override_and_creates_dispatch_job(client, roles, rate_config, db_session):
    req = _seed_mech_request(db_session, roles[Role.VENDOR], requested_by_date="2026-09-20")
    vendor_token = login(client, roles[Role.VENDOR].email)
    client.post(f"/vendor/requests/{req.id}/confirm", json={"confirmed_date": "2026-10-05"}, headers=auth_headers(vendor_token))

    admin_token = login(client, roles[Role.SUPER_ADMIN].email)
    approve = client.post(f"/admin/vendor-requests/{req.id}/approve-override", headers=auth_headers(admin_token))
    assert approve.status_code == 200, approve.text
    assert approve.json()["status"] == "confirmed"
    assert approve.json()["confirmed_date"] == "2026-10-05"


def test_confirm_already_confirmed_request_returns_409(client, roles, rate_config, db_session):
    req = _seed_mech_request(db_session, roles[Role.VENDOR])
    token = login(client, roles[Role.VENDOR].email)
    client.post(f"/vendor/requests/{req.id}/confirm", json={"confirmed_date": "2026-09-20"}, headers=auth_headers(token))
    second = client.post(f"/vendor/requests/{req.id}/confirm", json={"confirmed_date": "2026-09-21"}, headers=auth_headers(token))
    assert second.status_code == 409


def test_add_catalogue_item_rejects_non_positive_price(client, roles, rate_config):
    token = login(client, roles[Role.VENDOR].email)
    res = client.post("/vendor/catalogue", json={
        "name": "Bad item", "category": "seed", "unit": "kg", "unit_price": 0, "stock_qty": 10,
    }, headers=auth_headers(token))
    assert res.status_code == 422


def test_decline_input_order_restores_stock(client, roles, rate_config, db_session, make_user):
    vendor = roles[Role.VENDOR]
    farmer = make_user(Role.FARMER)
    product = make_product(db_session, vendor, stock_qty=10.0, unit_price=20.0)

    farmer_token = login(client, farmer.email)
    order = client.post("/farmer/input-orders", json={
        "vendor_id": vendor.id, "lines": [{"product_id": product.id, "quantity": 4.0}],
    }, headers=auth_headers(farmer_token)).json()
    db_session.refresh(product)
    assert product.stock_qty == 6.0

    vendor_token = login(client, vendor.email)
    decline = client.post(f"/vendor/input-orders/{order['id']}/decline", headers=auth_headers(vendor_token))
    assert decline.status_code == 200
    db_session.refresh(product)
    assert product.stock_qty == 10.0


def test_confirm_input_order_creates_dispatch_job(client, roles, rate_config, db_session, make_user):
    vendor = roles[Role.VENDOR]
    farmer = make_user(Role.FARMER)
    product = make_product(db_session, vendor, stock_qty=10.0, unit_price=15.0)
    farmer_token = login(client, farmer.email)
    order = client.post("/farmer/input-orders", json={
        "vendor_id": vendor.id, "lines": [{"product_id": product.id, "quantity": 2.0}],
    }, headers=auth_headers(farmer_token)).json()

    vendor_token = login(client, vendor.email)
    confirm = client.post(f"/vendor/input-orders/{order['id']}/confirm", headers=auth_headers(vendor_token))
    assert confirm.status_code == 200
    assert confirm.json()["dispatch_status"] == "assigned"


def test_dashboard_billing_payout_handoff_are_real(client, roles, rate_config, db_session, make_user):
    vendor = roles[Role.VENDOR]
    token = login(client, vendor.email)

    dash = client.get("/vendor/dashboard", headers=auth_headers(token)).json()
    assert dash["catalogue_item_count"] == 0

    billing = client.get("/vendor/billing", headers=auth_headers(token)).json()
    assert billing["monthly_fee"] == 150.0
    assert billing["history"] == []

    payout = client.get("/vendor/payout", headers=auth_headers(token)).json()
    assert payout == []

    handoff = client.get("/vendor/handoff", headers=auth_headers(token)).json()
    assert handoff == []


@pytest.mark.simulated
def test_billing_pay_momo_succeeds_card_returns_501(client, roles, rate_config):
    token = login(client, roles[Role.VENDOR].email)
    momo = client.post("/vendor/billing/pay", json={"method": "momo"}, headers=auth_headers(token))
    assert momo.status_code == 200
    assert momo.json()["history"][0]["transaction_ref"].startswith("SIM-")

    card = client.post("/vendor/billing/pay", json={"method": "card"}, headers=auth_headers(token))
    assert card.status_code == 501
