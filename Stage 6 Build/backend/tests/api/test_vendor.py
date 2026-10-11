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


def test_add_catalogue_item_is_retired(client, roles, rate_config):
    token = login(client, roles[Role.VENDOR].email)
    res = client.post("/vendor/catalogue", json={
        "name": "Any item", "category": "seed", "unit": "kg", "unit_price": 10, "stock_qty": 10,
    }, headers=auth_headers(token))
    assert res.status_code == 410 and "/vendor/listings" in res.json()["detail"]


def _marketplace_order(client, farmer, listing, qty):
    res = client.post("/farmer/marketplace/orders", json={"lines": [{"listing_id": listing.id, "quantity": qty}]},
                      headers=auth_headers(login(client, farmer.email)))
    assert res.status_code == 200, res.text
    return res.json()["orders"][0]


def test_decline_input_order_restores_stock(client, roles, rate_config, db_session, make_user):
    from tests.factories import make_listing
    vendor = roles[Role.VENDOR]
    listing = make_listing(db_session, vendor, quantity_available=10.0, price=20.0)
    order = _marketplace_order(client, make_user(Role.FARMER), listing, 4.0)
    db_session.refresh(listing)
    assert listing.quantity_available == 6.0

    vendor_token = login(client, vendor.email)
    decline = client.post(f"/vendor/input-orders/{order['id']}/decline", headers=auth_headers(vendor_token))
    assert decline.status_code == 200
    db_session.refresh(listing)
    assert listing.quantity_available == 10.0


def test_confirm_input_order_creates_dispatch_job(client, roles, rate_config, db_session, make_user):
    from tests.factories import make_listing
    vendor = roles[Role.VENDOR]
    listing = make_listing(db_session, vendor, quantity_available=10.0, price=15.0)
    order = _marketplace_order(client, make_user(Role.FARMER), listing, 2.0)

    vendor_token = login(client, vendor.email)
    confirm = client.post(f"/vendor/input-orders/{order['id']}/confirm", headers=auth_headers(vendor_token))
    assert confirm.status_code == 200
    assert confirm.json()["dispatch_status"] == "assigned"


def test_dashboard_counts_listings_not_retired_products(client, roles, rate_config, db_session):
    from tests.factories import make_listing
    vendor = roles[Role.VENDOR]
    make_listing(db_session, vendor, quantity_available=5.0)
    make_listing(db_session, vendor, title="Pump hire", quantity_available=None)
    dash = client.get("/vendor/dashboard", headers=auth_headers(login(client, vendor.email))).json()
    assert dash["catalogue_item_count"] == 2 and dash["catalogue_low_stock_count"] == 1


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
