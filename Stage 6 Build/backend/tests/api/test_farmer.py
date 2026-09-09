"""Integration tests for routers/farmer.py -- PRD Section 6 Must-Have #2 (opportunity + formula), #3's literal scope (Order Inputs), #4 (Harvest Pickup), plus 8 Sep 2026's Dashboard/Milestones/Messaging/Wallet."""

import pytest

from app.models import Role, OpportunityStatus
from tests.conftest import login, auth_headers
from tests.factories import make_product


pytestmark = pytest.mark.integration


def _seed_opportunity(db_session, buyer_requirement_id=None):
    from app.models import Opportunity

    opp = Opportunity(
        buyer_requirement_id=buyer_requirement_id, buyer_name="Test Buyer", tag="Private buyer",
        grade="Grade 1", quantity_tonnes=4.0, price_per_tonne=2100.0, deadline="20 Sep 2026",
    )
    db_session.add(opp)
    db_session.commit()
    db_session.refresh(opp)
    return opp


def test_accept_opportunity_creates_real_formula_from_rate_config(client, roles, rate_config, db_session):
    opp = _seed_opportunity(db_session)
    token = login(client, roles[Role.FARMER].email)
    res = client.post(f"/farmer/opportunities/{opp.id}/accept", json={"commitments_confirmed": True}, headers=auth_headers(token))
    assert res.status_code == 200, res.text
    formula = res.json()
    assert formula["seed_kg"] == round(4.0 * 1.6, 1)


def test_accept_opportunity_requires_commitments_confirmed(client, roles, rate_config, db_session):
    opp = _seed_opportunity(db_session)
    token = login(client, roles[Role.FARMER].email)
    res = client.post(f"/farmer/opportunities/{opp.id}/accept", json={"commitments_confirmed": False}, headers=auth_headers(token))
    assert res.status_code == 422


def test_second_farmer_cannot_accept_an_already_accepted_opportunity(client, roles, rate_config, db_session, make_user):
    opp = _seed_opportunity(db_session)
    token_a = login(client, roles[Role.FARMER].email)
    ok = client.post(f"/farmer/opportunities/{opp.id}/accept", json={"commitments_confirmed": True}, headers=auth_headers(token_a))
    assert ok.status_code == 200

    farmer_b = make_user(Role.FARMER)
    token_b = login(client, farmer_b.email)
    blocked = client.post(f"/farmer/opportunities/{opp.id}/accept", json={"commitments_confirmed": True}, headers=auth_headers(token_b))
    assert blocked.status_code == 409


def test_harvest_pickup_creates_real_dispatch_job_immediately(client, roles, rate_config):
    token = login(client, roles[Role.FARMER].email)
    res = client.post("/farmer/harvest-pickup", json={
        "quantity_ready_tonnes": 2.0, "preferred_pickup_date": "2026-09-25",
    }, headers=auth_headers(token))
    assert res.status_code == 200, res.text
    assert res.json()["dispatch_status"] == "assigned"


def test_harvest_pickup_rejects_order_farmer_never_accepted(client, roles, rate_config, db_session, make_user):
    """
    A real BuyerRequirement row is required here, not a fabricated string
    id -- Opportunity.buyer_requirement_id is a real foreign key, and
    Postgres correctly rejects an insert against a row that doesn't exist
    (unlike SQLite, which wouldn't enforce this by default). The 422 under
    test is farmer.py's own ownership check, which only ever runs once the
    id refers to something real.
    """
    from tests.factories import make_requirement

    other_buyer = make_user(Role.BUYER)
    real_requirement = make_requirement(db_session, other_buyer)
    opp = _seed_opportunity(db_session, buyer_requirement_id=real_requirement.id)
    token = login(client, roles[Role.FARMER].email)
    res = client.post("/farmer/harvest-pickup", json={
        "quantity_ready_tonnes": 1.0, "preferred_pickup_date": "2026-09-25",
        "buyer_requirement_id": real_requirement.id,
    }, headers=auth_headers(token))
    assert res.status_code == 422


def test_order_inputs_rejects_line_from_a_different_vendor(client, roles, rate_config, db_session, make_user):
    vendor_a = make_user(Role.VENDOR)
    vendor_b = make_user(Role.VENDOR)
    product_b = make_product(db_session, vendor_b)

    token = login(client, roles[Role.FARMER].email)
    res = client.post("/farmer/input-orders", json={
        "vendor_id": vendor_a.id,
        "lines": [{"product_id": product_b.id, "quantity": 1.0}],
    }, headers=auth_headers(token))
    assert res.status_code == 422


def test_order_inputs_rejects_quantity_beyond_stock_and_reserves_on_success(client, roles, rate_config, db_session, make_user):
    vendor = make_user(Role.VENDOR)
    product = make_product(db_session, vendor, stock_qty=5.0, unit_price=10.0)
    token = login(client, roles[Role.FARMER].email)

    too_much = client.post("/farmer/input-orders", json={
        "vendor_id": vendor.id, "lines": [{"product_id": product.id, "quantity": 999.0}],
    }, headers=auth_headers(token))
    assert too_much.status_code == 409

    ok = client.post("/farmer/input-orders", json={
        "vendor_id": vendor.id, "lines": [{"product_id": product.id, "quantity": 3.0}],
    }, headers=auth_headers(token))
    assert ok.status_code == 200
    assert ok.json()["total_cost"] == 30.0
    db_session.refresh(product)
    assert product.stock_qty == 2.0


def test_milestone_log_round_trip(client, roles, rate_config):
    token = login(client, roles[Role.FARMER].email)
    res = client.post("/farmer/milestones", json={"title": "Planting complete", "note": "on schedule"}, headers=auth_headers(token))
    assert res.status_code == 200, res.text
    listed = client.get("/farmer/milestones", headers=auth_headers(token)).json()
    assert any(m["title"] == "Planting complete" for m in listed)


def test_milestone_rejects_opportunity_not_owned_by_caller(client, roles, rate_config, db_session):
    opp = _seed_opportunity(db_session)  # not accepted by anyone
    token = login(client, roles[Role.FARMER].email)
    res = client.post("/farmer/milestones", json={"title": "X", "opportunity_id": opp.id}, headers=auth_headers(token))
    assert res.status_code == 422


def test_messaging_round_trip_and_dashboard_flags_unread(client, roles, rate_config, make_user, db_session):
    agronomist = roles[Role.AGRONOMIST]
    farmer_token = login(client, roles[Role.FARMER].email)

    sent = client.post("/farmer/messages", json={"body": "When is top-dress?"}, headers=auth_headers(farmer_token))
    assert sent.status_code == 200

    agro_token = login(client, agronomist.email)
    reply = client.post(
        f"/agronomist/messages/{roles[Role.FARMER].id}/reply",
        json={"body": "Next week."}, headers=auth_headers(agro_token),
    )
    assert reply.status_code == 200

    dash = client.get("/farmer/dashboard", headers=auth_headers(farmer_token)).json()
    assert dash["unread_message_note"] is not None


def test_wallet_empty_when_nothing_delivered(client, roles, rate_config):
    token = login(client, roles[Role.FARMER].email)
    wallet = client.get("/farmer/wallet", headers=auth_headers(token)).json()
    assert wallet["rows"] == []
    assert wallet["net_due"] == 0
