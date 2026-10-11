"""
Farmer Portal backend (CEO demo brief §4): Phase 1 matching (region + crop,
never another farmer's assignment), opportunity detail with stepper and
formula steps, acceptance side effects (48h agronomist task, in-app + SMS
notification, wallet), wallet ledger maths (decision D4), agronomist
formula-step authoring and the task queue.
"""

from datetime import date, timedelta

import pytest

from app.models import (
    Role, Opportunity, OpportunityStatus, FarmerCrop, Region, Crop, RequirementStatus, DispatchJobStatus,
    InputOrderStatus,
)
from tests.conftest import login, auth_headers
from tests.factories import make_requirement, make_product, make_confirmed_input_order

pytestmark = pytest.mark.integration


def _farmer(db, make_user, region="Greater Accra", crops=("Maize",), name="Kwabena Asante"):
    f = make_user(Role.FARMER, full_name=name)
    f.region_id = db.query(Region).filter(Region.name == region).first().id
    for c in crops:
        db.add(FarmerCrop(farmer_id=f.id, crop_id=db.query(Crop).filter(Crop.name == c).first().id))
    db.commit()
    return f


def _opp(db, crop=None, region=None, assigned=None, requirement=None, qty=4.0, price=2150.0, buyer="Ministry of Food & Agriculture"):
    o = Opportunity(
        buyer_requirement_id=requirement.id if requirement else None, buyer_name=buyer, tag="Buyer requirement match",
        grade="Grade A", quantity_tonnes=qty, price_per_tonne=price, deadline="15 Dec 2026",
        crop_id=db.query(Crop).filter(Crop.name == crop).first().id if crop else None,
        region_id=db.query(Region).filter(Region.name == region).first().id if region else None,
        assigned_farmer_id=assigned.id if assigned else None,
        delivery_by=date.today() + timedelta(weeks=9),
    )
    db.add(o)
    db.commit()
    return o


def _accept(client, token, opp_id):
    return client.post(f"/farmer/opportunities/{opp_id}/accept", json={"commitments_confirmed": True}, headers=auth_headers(token))


def test_phase_1_matching_rule(client, rate_config, db_session, make_user):
    me = _farmer(db_session, make_user)
    other = _farmer(db_session, make_user, name="Other Farmer")
    mine = _opp(db_session, crop="Maize", region="Greater Accra")
    assigned_to_me = _opp(db_session, assigned=me)
    _opp(db_session, assigned=other)                          # someone else's assignment
    _opp(db_session, crop="Maize", region="Eastern")          # wrong region
    _opp(db_session, crop="Soybean", region="Greater Accra")  # crop I don't grow
    legacy_pool = _opp(db_session)                            # unrestricted older row

    token = login(client, me.email)
    ids = {o["id"] for o in client.get("/farmer/matched-opportunities", headers=auth_headers(token)).json()}
    assert ids == {mine.id, assigned_to_me.id, legacy_pool.id}
    legacy_ids = {o["id"] for o in client.get("/farmer/opportunities", headers=auth_headers(token)).json()}
    assert legacy_ids == ids


def test_cannot_accept_another_farmers_assignment(client, rate_config, db_session, make_user):
    me = _farmer(db_session, make_user)
    other = _farmer(db_session, make_user, name="Other Farmer")
    theirs = _opp(db_session, assigned=other)
    assert _accept(client, login(client, me.email), theirs.id).status_code == 404


def test_detail_has_crop_region_weeks_stepper_and_formula_steps(client, roles, rate_config, db_session, make_user):
    me = _farmer(db_session, make_user)
    req = make_requirement(db_session, roles[Role.BUYER], status=RequirementStatus.PRODUCTION)
    req.spec_notes = "Moisture below 13%, 50kg sacks."
    from app.orders import maize_variety_id
    req.crop_variety_id = maize_variety_id(db_session)
    db_session.commit()
    o = _opp(db_session, crop="Maize", region="Greater Accra", requirement=req)

    row = client.get("/farmer/matched-opportunities", headers=auth_headers(login(client, me.email))).json()[0]
    assert row["id"] == o.id and row["crop"] == "Maize" and row["crop_icon"] == "maize"
    assert row["region"] == "Greater Accra" and row["delivery_in_weeks"] == 9
    assert row["steps"] == ["Matched", "Accepted", "In production", "Harvest & delivery"] and row["stage_index"] == 0
    assert row["formula_steps"][0] == "Obatanpa variety, 75cm x 40cm spacing, planted in week 2"
    assert row["formula_steps"][-1] == "Buyer specification: Moisture below 13%, 50kg sacks."


def test_accept_creates_48h_task_notifications_and_wallet_credit(client, roles, rate_config, db_session, make_user):
    me = _farmer(db_session, make_user)
    o = _opp(db_session, crop="Maize", region="Greater Accra", qty=4.0, price=2150.0)
    token = login(client, me.email)
    assert _accept(client, token, o.id).status_code == 200

    row = next(r for r in client.get("/farmer/matched-opportunities", headers=auth_headers(token)).json() if r["id"] == o.id)
    assert row["status"] == "accepted" and row["stage_index"] == 2
    assert any("Inputs for your 4 t" in s for s in row["formula_steps"])

    notes = client.get("/farmer/notifications", headers=auth_headers(token)).json()
    assert "agronomist will contact you within 48 hours" in notes[0]["message"]
    sms = client.get("/ussd/sms-log", headers=auth_headers(token)).json()
    assert any("within 48 hours" in m["body"] for m in sms)

    agro = login(client, roles[Role.AGRONOMIST].email)
    tasks = client.get("/ops/agronomist-tasks?status=open", headers=auth_headers(agro)).json()
    task = next(t for t in tasks if t["farmer_name"] == "Kwabena Asante")
    assert task["kind"] == "acceptance_follow_up" and not task["overdue"]
    from datetime import datetime
    hours = (datetime.fromisoformat(task["due_at"]) - datetime.fromisoformat(task["created_at"])).total_seconds() / 3600
    assert round(hours) == 48

    wallet = client.get("/farmer/wallet/summary", headers=auth_headers(token)).json()
    assert wallet["estimated_settlement"] == round(4 * 2150 * (1 - 0.15), 2)
    assert wallet["estimated_payout"] == wallet["estimated_settlement"]
    assert _accept(client, token, o.id).status_code == 409


def test_wallet_ledger_maths_inputs_reversal_and_logistics(client, roles, rate_config, db_session, make_user):
    me = _farmer(db_session, make_user)
    o = _opp(db_session, crop="Maize", region="Greater Accra", qty=2.0, price=2000.0)
    token = login(client, me.email)
    _accept(client, token, o.id)

    vendor = make_user(Role.VENDOR)
    product = make_product(db_session, vendor, unit_price=100.0)
    order = make_confirmed_input_order(db_session, me, vendor, product, quantity=3.0)  # GHS 300, dispatched
    declined = make_confirmed_input_order(db_session, me, vendor, product, quantity=1.0)
    declined.status = InputOrderStatus.DECLINED
    from app.models import DispatchJob
    job = db_session.query(DispatchJob).filter(DispatchJob.input_order_id == order.id).first()
    job.status = DispatchJobStatus.DELIVERED
    db_session.commit()

    w = client.get("/farmer/wallet/summary", headers=auth_headers(token)).json()
    settlement = round(2 * 2000 * 0.85, 2)
    assert w["input_costs"] == 300.0           # 300 + 100 - 100 reversal
    assert w["logistics_fees"] == 30.0         # one delivered job x GHS 30
    assert w["estimated_payout"] == round(settlement - 300 - 30, 2)
    kinds = sorted((e["source"], e["entry_type"]) for e in w["entries"])
    assert ("input_order_reversal", "credit") in kinds
    # Re-reading never double-posts.
    again = client.get("/farmer/wallet/summary", headers=auth_headers(token)).json()
    assert len(again["entries"]) == len(w["entries"])


def test_agronomist_authors_formula_steps_that_farmers_see(client, roles, rate_config, db_session, make_user):
    me = _farmer(db_session, make_user)
    req = make_requirement(db_session, roles[Role.BUYER], status=RequirementStatus.PRODUCTION)
    _opp(db_session, crop="Maize", region="Greater Accra", requirement=req)
    agro = login(client, roles[Role.AGRONOMIST].email)
    draft = client.get(f"/agronomist/requirements/{req.id}/formula-steps", headers=auth_headers(agro)).json()
    assert draft["authored"] is False
    res = client.put(f"/agronomist/requirements/{req.id}/formula-steps",
                     json={"steps": ["Obatanpa, 75 x 40cm", "  ", "NPK at planting"]}, headers=auth_headers(agro))
    assert res.json() == {"buyer_requirement_id": req.id, "steps": ["Obatanpa, 75 x 40cm", "NPK at planting"], "authored": True}
    assert client.put(f"/agronomist/requirements/{req.id}/formula-steps", json={"steps": []}, headers=auth_headers(agro)).status_code == 422
    row = client.get("/farmer/matched-opportunities", headers=auth_headers(login(client, me.email))).json()[0]
    assert row["formula_steps"] == ["Obatanpa, 75 x 40cm", "NPK at planting"]


def test_task_completion_and_rbac(client, roles, rate_config, db_session, make_user):
    me = _farmer(db_session, make_user)
    o = _opp(db_session, crop="Maize", region="Greater Accra")
    _accept(client, login(client, me.email), o.id)
    agro = login(client, roles[Role.AGRONOMIST].email)
    task = client.get("/ops/agronomist-tasks", headers=auth_headers(agro)).json()[0]
    done = client.post(f"/ops/agronomist-tasks/{task['id']}/complete", json={"notes": "Called, visit booked"}, headers=auth_headers(agro))
    assert done.json()["status"] == "done"
    assert client.post(f"/ops/agronomist-tasks/{task['id']}/complete", json={}, headers=auth_headers(agro)).status_code == 409
    for role in (Role.FARMER, Role.BUYER, Role.FINANCE, Role.LOGISTICS):
        assert client.get("/ops/agronomist-tasks", headers=auth_headers(login(client, roles[role].email))).status_code == 403


def test_matching_queue_assignment_stamps_crop_region_and_date(client, roles, rate_config, db_session, make_user):
    me = _farmer(db_session, make_user)
    buyer = login(client, roles[Role.BUYER].email)
    form = client.get("/buyer/order-form", headers=auth_headers(buyer)).json()
    req = client.post("/buyer/requirements", json={
        "crop_variety_id": form["crops"][0]["varieties"][0]["id"], "quantity_tonnes": 6,
        "delivery_by": (date.today() + timedelta(days=70)).isoformat(),
    }, headers=auth_headers(buyer)).json()
    from app.models import BuyerRequirement
    r = db_session.query(BuyerRequirement).filter(BuyerRequirement.id == req["id"]).first()
    r.status = RequirementStatus.MATCHING
    db_session.commit()
    agro = login(client, roles[Role.AGRONOMIST].email)
    assert client.post(f"/agronomist/requirements/{r.id}/assign", json={"farmer_ids": [me.id]}, headers=auth_headers(agro)).status_code == 200
    row = client.get("/farmer/matched-opportunities", headers=auth_headers(login(client, me.email))).json()[0]
    assert row["crop"] == "Maize" and row["region"] == "Greater Accra" and row["delivery_in_weeks"] == 10
