"""Integration tests for routers/agronomist.py -- the Matching Queue, Production Formula Builder, and (8 Sep 2026) Field Visit Logs + Agronomist Messaging."""

import pytest

from app.models import Role, RequirementStatus
from tests.conftest import login, auth_headers
from tests.factories import make_requirement

pytestmark = pytest.mark.integration


def test_assign_farmers_splits_tonnage_evenly_and_advances_status(client, roles, rate_config, db_session, make_user):
    buyer = make_user(Role.BUYER)
    req = make_requirement(db_session, buyer, status=RequirementStatus.MATCHING, quantity_tonnes=6.0)
    farmer_a = make_user(Role.FARMER)
    farmer_b = make_user(Role.FARMER)

    token = login(client, roles[Role.AGRONOMIST].email)
    res = client.post(
        f"/agronomist/requirements/{req.id}/assign",
        json={"farmer_ids": [farmer_a.id, farmer_b.id]},
        headers=auth_headers(token),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["assigned_farmer_count"] == 2
    assert body["status"] == "production"


def test_assign_farmers_requires_at_least_one(client, roles, rate_config, db_session, make_user):
    buyer = make_user(Role.BUYER)
    req = make_requirement(db_session, buyer, status=RequirementStatus.MATCHING)
    token = login(client, roles[Role.AGRONOMIST].email)
    res = client.post(f"/agronomist/requirements/{req.id}/assign", json={"farmer_ids": []}, headers=auth_headers(token))
    assert res.status_code == 422


def test_assign_farmers_rejects_a_requirement_not_open_for_matching(client, roles, rate_config, db_session, make_user):
    buyer = make_user(Role.BUYER)
    req = make_requirement(db_session, buyer, status=RequirementStatus.PRODUCTION)
    farmer = make_user(Role.FARMER)
    token = login(client, roles[Role.AGRONOMIST].email)
    res = client.post(f"/agronomist/requirements/{req.id}/assign", json={"farmer_ids": [farmer.id]}, headers=auth_headers(token))
    assert res.status_code == 409


def test_assign_farmers_rejects_inactive_farmer(client, roles, rate_config, db_session, make_user):
    from app.models import UserStatus

    buyer = make_user(Role.BUYER)
    req = make_requirement(db_session, buyer, status=RequirementStatus.MATCHING)
    suspended_farmer = make_user(Role.FARMER, status=UserStatus.SUSPENDED)
    token = login(client, roles[Role.AGRONOMIST].email)
    res = client.post(f"/agronomist/requirements/{req.id}/assign", json={"farmer_ids": [suspended_farmer.id]}, headers=auth_headers(token))
    assert res.status_code == 422


def test_formula_builder_needs_assigned_farmers_first(client, roles, rate_config, db_session, make_user):
    buyer = make_user(Role.BUYER)
    req = make_requirement(db_session, buyer, status=RequirementStatus.MATCHING)
    token = login(client, roles[Role.AGRONOMIST].email)
    res = client.get(f"/agronomist/requirements/{req.id}/formula", headers=auth_headers(token))
    assert res.status_code == 409


def test_formula_builder_save_and_publish_lifecycle(client, roles, rate_config, db_session, make_user):
    buyer = make_user(Role.BUYER)
    req = make_requirement(db_session, buyer, status=RequirementStatus.MATCHING, quantity_tonnes=4.0)
    farmer = make_user(Role.FARMER)
    token = login(client, roles[Role.AGRONOMIST].email)
    client.post(f"/agronomist/requirements/{req.id}/assign", json={"farmer_ids": [farmer.id]}, headers=auth_headers(token))

    save = client.put(f"/agronomist/requirements/{req.id}/formula", json={
        "land_prep_week": 1, "planting_week": 2, "topdress_week": 4, "weeding_week": 6, "harvest_week": 11,
    }, headers=auth_headers(token))
    assert save.status_code == 200
    assert save.json()["plan"]["published"] is False

    publish = client.post(f"/agronomist/requirements/{req.id}/formula/publish", headers=auth_headers(token))
    assert publish.status_code == 200
    assert publish.json()["plan"]["published"] is True

    # A published plan can no longer be edited.
    edit_after_publish = client.put(f"/agronomist/requirements/{req.id}/formula", json={
        "land_prep_week": 1, "planting_week": 3, "topdress_week": 4, "weeding_week": 6, "harvest_week": 11,
    }, headers=auth_headers(token))
    assert edit_after_publish.status_code == 409

    second_publish = client.post(f"/agronomist/requirements/{req.id}/formula/publish", headers=auth_headers(token))
    assert second_publish.status_code == 409


def test_publish_without_saved_plan_returns_409(client, roles, rate_config, db_session, make_user):
    buyer = make_user(Role.BUYER)
    req = make_requirement(db_session, buyer, status=RequirementStatus.MATCHING)
    farmer = make_user(Role.FARMER)
    token = login(client, roles[Role.AGRONOMIST].email)
    client.post(f"/agronomist/requirements/{req.id}/assign", json={"farmer_ids": [farmer.id]}, headers=auth_headers(token))
    res = client.post(f"/agronomist/requirements/{req.id}/formula/publish", headers=auth_headers(token))
    assert res.status_code == 409


def test_visit_log_schedule_and_complete_lifecycle(client, roles, rate_config, make_user):
    farmer = make_user(Role.FARMER)
    token = login(client, roles[Role.AGRONOMIST].email)
    create = client.post("/agronomist/visit-logs", json={
        "farmer_id": farmer.id, "checkpoint_label": "Top-dress checkpoint", "scheduled_date": "2026-09-20",
    }, headers=auth_headers(token))
    assert create.status_code == 200, create.text
    visit_id = create.json()["id"]
    assert create.json()["status"] == "scheduled"

    complete = client.post(f"/agronomist/visit-logs/{visit_id}/complete", json={}, headers=auth_headers(token))
    assert complete.status_code == 200
    assert complete.json()["status"] == "completed"

    second_complete = client.post(f"/agronomist/visit-logs/{visit_id}/complete", json={}, headers=auth_headers(token))
    assert second_complete.status_code == 409


def test_visit_log_rejects_non_farmer_id(client, roles, rate_config, make_user):
    not_a_farmer = make_user(Role.BUYER)
    token = login(client, roles[Role.AGRONOMIST].email)
    res = client.post("/agronomist/visit-logs", json={
        "farmer_id": not_a_farmer.id, "checkpoint_label": "X", "scheduled_date": "2026-09-20",
    }, headers=auth_headers(token))
    assert res.status_code == 422


def test_messages_shared_inbox_visible_to_agronomist(client, roles, rate_config, make_user):
    farmer = make_user(Role.FARMER)
    farmer_token = login(client, farmer.email)
    client.post("/farmer/messages", json={"body": "Question?"}, headers=auth_headers(farmer_token))

    agro_token = login(client, roles[Role.AGRONOMIST].email)
    msgs = client.get("/agronomist/messages", headers=auth_headers(agro_token)).json()
    assert any(m["body"] == "Question?" for m in msgs)


def test_reply_to_farmer_rejects_empty_body(client, roles, rate_config, make_user):
    farmer = make_user(Role.FARMER)
    token = login(client, roles[Role.AGRONOMIST].email)
    res = client.post(f"/agronomist/messages/{farmer.id}/reply", json={"body": "   "}, headers=auth_headers(token))
    assert res.status_code == 422


def test_reply_to_nonexistent_farmer_returns_404(client, roles, rate_config):
    token = login(client, roles[Role.AGRONOMIST].email)
    res = client.post("/agronomist/messages/does-not-exist/reply", json={"body": "Hello"}, headers=auth_headers(token))
    assert res.status_code == 404
