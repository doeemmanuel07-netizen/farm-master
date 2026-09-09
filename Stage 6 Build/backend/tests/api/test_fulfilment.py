"""Integration tests for routers/fulfilment.py -- the back half of PRD Section 6 Must-Have #4."""

import pytest

from app.models import Role
from tests.conftest import login, auth_headers
from tests.factories import make_undelivered_pickup, make_delivered_graded_pickup

pytestmark = pytest.mark.integration


def test_intake_queue_excludes_undelivered_and_already_graded(client, roles, rate_config, db_session, make_user):
    farmer = make_user(Role.FARMER)
    finance = make_user(Role.FINANCE)
    make_undelivered_pickup(db_session, farmer)  # not delivered -- excluded
    make_delivered_graded_pickup(db_session, farmer, finance)  # already graded -- excluded

    token = login(client, roles[Role.FINANCE].email)
    queue = client.get("/fulfilment/intake-queue", headers=auth_headers(token)).json()
    assert queue == []


def test_intake_queue_includes_delivered_ungraded_pickup(client, roles, rate_config, db_session, make_user):
    from app.models import HarvestPickupRequest, DispatchJobStatus
    from app.dispatch import create_inbound_dispatch_job
    from datetime import datetime

    farmer = make_user(Role.FARMER)
    pickup = HarvestPickupRequest(farmer_id=farmer.id, quantity_ready_tonnes=2.0, preferred_pickup_date="2026-09-20")
    db_session.add(pickup)
    db_session.commit()
    db_session.refresh(pickup)
    job = create_inbound_dispatch_job(db_session, pickup)
    job.status = DispatchJobStatus.DELIVERED
    job.delivered_at = datetime.utcnow()
    db_session.commit()

    token = login(client, roles[Role.FINANCE].email)
    queue = client.get("/fulfilment/intake-queue", headers=auth_headers(token)).json()
    assert len(queue) == 1
    assert queue[0]["harvest_pickup_request_id"] == pickup.id


def test_grade_before_delivery_returns_409(client, roles, rate_config, db_session, make_user):
    farmer = make_user(Role.FARMER)
    pickup, job = make_undelivered_pickup(db_session, farmer)
    token = login(client, roles[Role.FINANCE].email)
    res = client.post(f"/fulfilment/intake/{pickup.id}", json={"weigh_in_kg": 1000.0, "grade": "grade_1"}, headers=auth_headers(token))
    assert res.status_code == 409


def test_grade_twice_returns_409(client, roles, rate_config, db_session, make_user):
    from app.models import HarvestPickupRequest, DispatchJobStatus
    from app.dispatch import create_inbound_dispatch_job
    from datetime import datetime

    farmer = make_user(Role.FARMER)
    pickup = HarvestPickupRequest(farmer_id=farmer.id, quantity_ready_tonnes=1.0, preferred_pickup_date="2026-09-20")
    db_session.add(pickup)
    db_session.commit()
    db_session.refresh(pickup)
    job = create_inbound_dispatch_job(db_session, pickup)
    job.status = DispatchJobStatus.DELIVERED
    job.delivered_at = datetime.utcnow()
    db_session.commit()

    token = login(client, roles[Role.FINANCE].email)
    first = client.post(f"/fulfilment/intake/{pickup.id}", json={"weigh_in_kg": 950.0, "grade": "grade_1"}, headers=auth_headers(token))
    assert first.status_code == 200, first.text
    second = client.post(f"/fulfilment/intake/{pickup.id}", json={"weigh_in_kg": 950.0, "grade": "grade_1"}, headers=auth_headers(token))
    assert second.status_code == 409


def test_grade_nonexistent_pickup_returns_404(client, roles, rate_config):
    token = login(client, roles[Role.FINANCE].email)
    res = client.post("/fulfilment/intake/does-not-exist", json={"weigh_in_kg": 1000.0, "grade": "grade_1"}, headers=auth_headers(token))
    assert res.status_code == 404


@pytest.mark.parametrize("wrong_role", [Role.LOGISTICS, Role.VENDOR, Role.FARMER, Role.SUPER_ADMIN])
def test_intake_queue_blocked_for_non_finance_roles(client, roles, rate_config, wrong_role):
    token = login(client, roles[wrong_role].email)
    res = client.get("/fulfilment/intake-queue", headers=auth_headers(token))
    assert res.status_code == 403
