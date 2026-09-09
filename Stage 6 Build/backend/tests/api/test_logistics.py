"""Integration tests for routers/logistics.py -- Dispatch (Must-Have #3/#4), plus 8 Sep 2026's Proof of Pickup/Delivery and Trunking."""

import pytest

from app.models import Role, GradeResult
from tests.conftest import login, auth_headers
from tests.factories import make_confirmed_mechanisation_request, make_delivered_graded_pickup, make_undelivered_pickup

pytestmark = pytest.mark.integration


def test_dispatch_then_deliver_lifecycle_and_double_action_409s(client, roles, rate_config, db_session, make_user):
    vendor = make_user(Role.VENDOR)
    make_confirmed_mechanisation_request(db_session, vendor)
    token = login(client, roles[Role.LOGISTICS].email)

    jobs = client.get("/logistics/jobs", headers=auth_headers(token)).json()
    assert len(jobs) == 1
    job_id = jobs[0]["id"]
    assert jobs[0]["job_type"] == "mechanisation"

    dispatch = client.post(f"/logistics/jobs/{job_id}/dispatch", json={"tricycle_label": "#1"}, headers=auth_headers(token))
    assert dispatch.status_code == 200
    assert dispatch.json()["status"] == "en_route"

    dispatch_again = client.post(f"/logistics/jobs/{job_id}/dispatch", json={"tricycle_label": "#2"}, headers=auth_headers(token))
    assert dispatch_again.status_code == 409

    deliver = client.post(f"/logistics/jobs/{job_id}/deliver", headers=auth_headers(token))
    assert deliver.status_code == 200
    assert deliver.json()["status"] == "delivered"

    deliver_again = client.post(f"/logistics/jobs/{job_id}/deliver", headers=auth_headers(token))
    assert deliver_again.status_code == 409


def test_deliver_before_dispatch_returns_409(client, roles, rate_config, db_session, make_user):
    vendor = make_user(Role.VENDOR)
    make_confirmed_mechanisation_request(db_session, vendor)
    token = login(client, roles[Role.LOGISTICS].email)
    jobs = client.get("/logistics/jobs", headers=auth_headers(token)).json()
    res = client.post(f"/logistics/jobs/{jobs[0]['id']}/deliver", headers=auth_headers(token))
    assert res.status_code == 409


def test_capture_proof_requires_delivered_status_and_is_single_use(client, roles, rate_config, db_session, make_user):
    farmer = make_user(Role.FARMER)
    finance = make_user(Role.FINANCE)
    pickup, job, intake = make_delivered_graded_pickup(db_session, farmer, finance)
    token = login(client, roles[Role.LOGISTICS].email)

    proof = client.post(f"/logistics/jobs/{job.id}/proof", json={
        "gps_lat": 5.65, "gps_lng": 0.01, "signature_captured": True, "photo_captured": True,
    }, headers=auth_headers(token))
    assert proof.status_code == 200, proof.text

    second = client.post(f"/logistics/jobs/{job.id}/proof", json={"signature_captured": True, "photo_captured": True}, headers=auth_headers(token))
    assert second.status_code == 409

    fetched = client.get(f"/logistics/jobs/{job.id}/proof", headers=auth_headers(token))
    assert fetched.status_code == 200
    assert fetched.json()["gps_lat"] == 5.65


def test_capture_proof_before_delivery_returns_409(client, roles, rate_config, db_session, make_user):
    farmer = make_user(Role.FARMER)
    pickup, job = make_undelivered_pickup(db_session, farmer)
    token = login(client, roles[Role.LOGISTICS].email)
    res = client.post(f"/logistics/jobs/{job.id}/proof", json={"signature_captured": True, "photo_captured": True}, headers=auth_headers(token))
    assert res.status_code == 409


def test_get_proof_for_job_never_captured_returns_404(client, roles, rate_config, db_session, make_user):
    farmer = make_user(Role.FARMER)
    pickup, job = make_undelivered_pickup(db_session, farmer)
    token = login(client, roles[Role.LOGISTICS].email)
    res = client.get(f"/logistics/jobs/{job.id}/proof", headers=auth_headers(token))
    assert res.status_code == 404


def test_trunking_availability_reflects_real_graded_non_reject_tonnage(client, roles, rate_config, db_session, make_user):
    farmer = make_user(Role.FARMER)
    finance = make_user(Role.FINANCE)
    make_delivered_graded_pickup(db_session, farmer, finance, weigh_in_kg=2000.0, grade=GradeResult.GRADE_1)
    make_delivered_graded_pickup(db_session, farmer, finance, weigh_in_kg=1000.0, grade=GradeResult.REJECT)

    token = login(client, roles[Role.LOGISTICS].email)
    avail = client.get("/logistics/trunking/availability", headers=auth_headers(token)).json()
    assert avail["tonnes_available"] == 2.0


def test_schedule_trunking_over_available_tonnage_returns_409(client, roles, rate_config, db_session, make_user):
    farmer = make_user(Role.FARMER)
    finance = make_user(Role.FINANCE)
    make_delivered_graded_pickup(db_session, farmer, finance, weigh_in_kg=1000.0, grade=GradeResult.GRADE_1)
    token = login(client, roles[Role.LOGISTICS].email)

    over = client.post("/logistics/trunking", json={"produce_tonnes": 5.0, "destination": "X", "vehicle_label": "Truck 1"}, headers=auth_headers(token))
    assert over.status_code == 409

    ok = client.post("/logistics/trunking", json={"produce_tonnes": 1.0, "destination": "X", "vehicle_label": "Truck 1"}, headers=auth_headers(token))
    assert ok.status_code == 200
    assert ok.json()["status"] == "scheduled"


def test_schedule_trunking_rejects_non_positive_tonnage(client, roles, rate_config):
    token = login(client, roles[Role.LOGISTICS].email)
    res = client.post("/logistics/trunking", json={"produce_tonnes": 0, "destination": "X", "vehicle_label": "Truck 1"}, headers=auth_headers(token))
    assert res.status_code == 422


def test_trunking_dispatch_then_deliver_lifecycle(client, roles, rate_config, db_session, make_user):
    farmer = make_user(Role.FARMER)
    finance = make_user(Role.FINANCE)
    make_delivered_graded_pickup(db_session, farmer, finance, weigh_in_kg=3000.0, grade=GradeResult.GRADE_1)
    token = login(client, roles[Role.LOGISTICS].email)
    job = client.post("/logistics/trunking", json={"produce_tonnes": 2.0, "destination": "X", "vehicle_label": "Truck 1"}, headers=auth_headers(token)).json()

    deliver_too_early = client.post(f"/logistics/trunking/{job['id']}/deliver", headers=auth_headers(token))
    assert deliver_too_early.status_code == 409

    dispatch = client.post(f"/logistics/trunking/{job['id']}/dispatch", headers=auth_headers(token))
    assert dispatch.status_code == 200
    assert dispatch.json()["status"] == "dispatched"

    deliver = client.post(f"/logistics/trunking/{job['id']}/deliver", headers=auth_headers(token))
    assert deliver.status_code == 200
    assert deliver.json()["status"] == "delivered"
