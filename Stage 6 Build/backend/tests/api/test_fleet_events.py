"""
Fleet, logistics events and the public activity feed (CEO demo brief §3/§7):
labels resolve to fleet vehicles, every transition emits an event, intake
drives "Aggregating", the public ticker is anonymised, and orders advance
only along allowed transitions.
"""

import pytest

from app.models import Role, RequirementStatus, FarmerCrop
from tests.conftest import login, auth_headers
from tests.factories import make_confirmed_mechanisation_request, make_requirement, make_undelivered_pickup

pytestmark = pytest.mark.integration


def _farmer_in_greater_accra(db, make_user, name="Kwabena Asante", phone="+233240000777"):
    from app.models import Region, Crop
    farmer = make_user(Role.FARMER, full_name=name, phone=phone)
    farmer.region_id = db.query(Region).filter(Region.name == "Greater Accra").first().id
    db.add(FarmerCrop(farmer_id=farmer.id, crop_id=db.query(Crop).filter(Crop.name == "Maize").first().id))
    db.commit()
    return farmer


def _dispatch_and_deliver(client, token, label):
    job = client.get("/logistics/jobs", headers=auth_headers(token)).json()[0]
    client.post(f"/logistics/jobs/{job['id']}/dispatch", json={"tricycle_label": label}, headers=auth_headers(token))
    client.post(f"/logistics/jobs/{job['id']}/deliver", headers=auth_headers(token))
    return job


def test_dispatch_label_resolves_to_fleet_vehicle_and_releases_it(client, roles, rate_config, db_session, make_user):
    make_confirmed_mechanisation_request(db_session, make_user(Role.VENDOR))
    token = login(client, roles[Role.LOGISTICS].email)
    job = client.get("/logistics/jobs", headers=auth_headers(token)).json()[0]
    client.post(f"/logistics/jobs/{job['id']}/dispatch", json={"tricycle_label": "#1"}, headers=auth_headers(token))
    fleet = {v["code"]: v for v in client.get("/ops/vehicles", headers=auth_headers(token)).json()}
    assert fleet["Tricycle #1"]["status"] == "on_job" and fleet["Vehicle #07"]["vehicle_type"] == "truck"
    client.post(f"/logistics/jobs/{job['id']}/deliver", headers=auth_headers(token))
    fleet = {v["code"]: v for v in client.get("/ops/vehicles", headers=auth_headers(token)).json()}
    assert fleet["Tricycle #1"]["status"] == "available"


def test_public_activity_is_anonymised(client, roles, rate_config, db_session, make_user):
    farmer = _farmer_in_greater_accra(db_session, make_user)
    make_undelivered_pickup(db_session, farmer, quantity_ready_tonnes=2.5)
    _dispatch_and_deliver(client, login(client, roles[Role.LOGISTICS].email), "Tricycle #3")

    feed = client.get("/api/public/activity?limit=10").json()
    texts = " | ".join(i["text"] for i in feed)
    assert "Tricycle #3 collecting a 2.5 t harvest in Greater Accra for Tema fulfilment centre." in texts
    assert "harvest pickup completed — 2.5 t delivered to Tema fulfilment centre." in texts
    assert "Kwabena" not in texts and "Asante" not in texts and "0777" not in texts


def test_intake_moves_order_to_aggregating_and_feeds_daily_aggregation(client, roles, rate_config, db_session, make_user):
    farmer = _farmer_in_greater_accra(db_session, make_user)
    order = make_requirement(db_session, roles[Role.BUYER], status=RequirementStatus.PRODUCTION)
    pickup, _ = make_undelivered_pickup(db_session, farmer, requirement=order, quantity_ready_tonnes=3.8)
    _dispatch_and_deliver(client, login(client, roles[Role.LOGISTICS].email), "#2")

    fin = login(client, roles[Role.FINANCE].email)
    res = client.post(f"/fulfilment/intake/{pickup.id}", json={"weigh_in_kg": 3800, "grade": "grade_1"}, headers=auth_headers(fin))
    assert res.status_code == 200, res.text
    db_session.refresh(order)
    assert order.status == RequirementStatus.AGGREGATION

    agg = client.get("/ops/aggregation", headers=auth_headers(fin)).json()
    assert agg == [{"centre": "Tema Head Office & Fulfilment Centre", "crop": "Maize", "tonnes_today": 3.8}]
    feed = [i["text"] for i in client.get("/api/public/activity").json()]
    assert feed[0] == "Live: Fulfilment centre — Tema has aggregated 3.8 tonnes of maize today."

    buyer = login(client, roles[Role.BUYER].email)
    tracking = client.get(f"/buyer/requirements/{order.id}/tracking", headers=auth_headers(buyer)).json()
    assert any("graded 3.8 t of maize" in r["text"] for r in tracking["log"])


def test_rejected_lot_does_not_aggregate(client, roles, rate_config, db_session, make_user):
    farmer = _farmer_in_greater_accra(db_session, make_user)
    order = make_requirement(db_session, roles[Role.BUYER], status=RequirementStatus.PRODUCTION)
    pickup, _ = make_undelivered_pickup(db_session, farmer, requirement=order)
    _dispatch_and_deliver(client, login(client, roles[Role.LOGISTICS].email), "#2")
    fin = login(client, roles[Role.FINANCE].email)
    client.post(f"/fulfilment/intake/{pickup.id}", json={"weigh_in_kg": 900, "grade": "reject"}, headers=auth_headers(fin))
    db_session.refresh(order)
    assert order.status == RequirementStatus.PRODUCTION


def test_order_advances_only_along_allowed_transitions(client, roles, rate_config, db_session):
    early = make_requirement(db_session, roles[Role.BUYER], status=RequirementStatus.MATCHING)
    ready = make_requirement(db_session, roles[Role.BUYER], status=RequirementStatus.AGGREGATION)
    token = login(client, roles[Role.LOGISTICS].email)
    assert client.post(f"/ops/requirements/{early.id}/advance", json={"status": "delivered"}, headers=auth_headers(token)).status_code == 409
    assert client.post(f"/ops/requirements/{ready.id}/advance", json={"status": "delivered"}, headers=auth_headers(token)).status_code == 409
    r = client.post(f"/ops/requirements/{ready.id}/advance", json={"status": "shipment"}, headers=auth_headers(token))
    assert r.status_code == 200 and r.json()["status_label"] == "In transit"
    r = client.post(f"/ops/requirements/{ready.id}/advance", json={"status": "delivered"}, headers=auth_headers(token))
    assert r.json()["status_label"] == "Delivered" and r.json()["progress_pct"] == 100
    bad = client.post(f"/ops/requirements/{ready.id}/advance", json={"status": "production"}, headers=auth_headers(token))
    assert bad.status_code == 422
    texts = [i["text"] for i in client.get("/api/public/activity").json()]
    assert any("was delivered to its buyer" in t for t in texts)


@pytest.mark.parametrize("role", [Role.BUYER, Role.FARMER, Role.FINANCE, Role.VENDOR])
def test_order_advance_is_logistics_ops_only(client, roles, rate_config, db_session, role):
    ready = make_requirement(db_session, roles[Role.BUYER], status=RequirementStatus.AGGREGATION)
    token = login(client, roles[role].email)
    res = client.post(f"/ops/requirements/{ready.id}/advance", json={"status": "shipment"}, headers=auth_headers(token))
    assert res.status_code == 403


def test_trunking_resolves_truck_and_emits_events(client, roles, rate_config, db_session, make_user):
    from tests.factories import make_delivered_graded_pickup
    make_delivered_graded_pickup(db_session, make_user(Role.FARMER), make_user(Role.FINANCE), weigh_in_kg=3000.0)
    token = login(client, roles[Role.LOGISTICS].email)
    job = client.post("/logistics/trunking", json={"produce_tonnes": 2.0, "destination": "Tema head office", "vehicle_label": "Vehicle #07"},
                      headers=auth_headers(token)).json()
    client.post(f"/logistics/trunking/{job['id']}/dispatch", headers=auth_headers(token))
    texts = [i["text"] for i in client.get("/api/public/activity").json()]
    assert "Live: Vehicle #07 trunking 2 t of graded produce from Tema to Tema head office." in texts
