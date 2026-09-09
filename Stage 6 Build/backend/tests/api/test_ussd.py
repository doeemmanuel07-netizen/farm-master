"""
Integration tests for routers/ussd.py -- the USSD/SMS channel (8 Sep 2026).
Marked `simulated` throughout: delivery is SIMULATED, but every real
property claimed for it must hold -- a pickup made through USSD is a real
HarvestPickupRequest indistinguishable from one made through the web, and
every "sent" SMS is a real, queryable UssdSmsLog row, not merely displayed.
"""

import pytest

from app.models import Role, OpportunityStatus
from tests.conftest import login, auth_headers

pytestmark = [pytest.mark.integration, pytest.mark.simulated]


def _seed_opportunity(db_session):
    from app.models import Opportunity

    opp = Opportunity(
        buyer_name="Ghana School Feeding Programme", tag="MoFA-linked", grade="Grade 1",
        quantity_tonnes=4.0, price_per_tonne=2100.0, deadline="20 Sep 2026",
    )
    db_session.add(opp)
    db_session.commit()
    db_session.refresh(opp)
    return opp


def test_push_alert_logs_a_real_sms_row(client, roles, rate_config, db_session):
    opp = _seed_opportunity(db_session)
    token = login(client, roles[Role.FARMER].email)
    res = client.post(f"/ussd/opportunities/{opp.id}/push-alert", headers=auth_headers(token))
    assert res.status_code == 200, res.text
    assert opp.buyer_name in res.json()["sms_text"]

    log = client.get("/ussd/sms-log", headers=auth_headers(token)).json()
    assert len(log) == 1
    assert log[0]["purpose"] == "opportunity_alert"
    assert opp.buyer_name in log[0]["body"]


def test_push_alert_404s_for_no_longer_open_opportunity(client, roles, rate_config, db_session):
    opp = _seed_opportunity(db_session)
    opp.status = OpportunityStatus.ACCEPTED
    db_session.commit()
    token = login(client, roles[Role.FARMER].email)
    res = client.post(f"/ussd/opportunities/{opp.id}/push-alert", headers=auth_headers(token))
    assert res.status_code == 404


def test_pickup_confirm_creates_a_real_indistinguishable_harvest_pickup(client, roles, rate_config):
    token = login(client, roles[Role.FARMER].email)
    res = client.post("/ussd/pickup-confirm", json={
        "quantity_ready_tonnes": 1.5, "preferred_pickup_date": "2026-09-28",
    }, headers=auth_headers(token))
    assert res.status_code == 200, res.text
    assert res.json()["dispatch_status"] == "assigned"

    # Shows up in the exact same "mine" listing the web Farmer Portal reads.
    mine = client.get("/farmer/harvest-pickup/mine", headers=auth_headers(token)).json()
    assert any(p["quantity_ready_tonnes"] == 1.5 for p in mine)

    log = client.get("/ussd/sms-log", headers=auth_headers(token)).json()
    assert any(l["purpose"] == "pickup_confirmation" for l in log)


def test_pickup_confirm_enforces_the_same_ownership_rule_as_the_web_endpoint(client, roles, rate_config, db_session):
    """Reuses farmer.py's request_harvest_pickup directly -- confirms the 422 for an order the farmer never accepted carries through the USSD path too."""
    opp = _seed_opportunity(db_session)
    token = login(client, roles[Role.FARMER].email)
    res = client.post("/ussd/pickup-confirm", json={
        "quantity_ready_tonnes": 1.0, "preferred_pickup_date": "2026-09-28",
        "buyer_requirement_id": "some-order-never-accepted",
    }, headers=auth_headers(token))
    assert res.status_code == 422


def test_payment_notification_reflects_real_wallet_and_logs_sms(client, roles, rate_config, db_session, make_user):
    from tests.factories import make_requirement, make_delivered_graded_pickup
    from app.models import GradeResult

    buyer = make_user(Role.BUYER)
    farmer = roles[Role.FARMER]
    finance = make_user(Role.FINANCE)
    req = make_requirement(db_session, buyer, price_per_tonne=2000.0)
    make_delivered_graded_pickup(db_session, farmer, finance, requirement=req, weigh_in_kg=1000.0, grade=GradeResult.GRADE_1)

    token = login(client, farmer.email)
    res = client.get("/ussd/payment-notification", headers=auth_headers(token))
    assert res.status_code == 200
    assert "1700.00" in res.json()["sms_text"] or "1700" in res.json()["balance_text"]

    log = client.get("/ussd/sms-log", headers=auth_headers(token)).json()
    assert any(l["purpose"] == "payment_notification" for l in log)


def test_sms_log_scoped_to_caller_only(client, roles, rate_config, make_user, db_session):
    farmer_a_token = login(client, roles[Role.FARMER].email)
    client.get("/ussd/payment-notification", headers=auth_headers(farmer_a_token))

    farmer_b = make_user(Role.FARMER)
    farmer_b_token = login(client, farmer_b.email)
    log_b = client.get("/ussd/sms-log", headers=auth_headers(farmer_b_token)).json()
    assert log_b == []


def test_no_real_gateway_call_exists_anywhere_in_the_codebase():
    """
    Hard rule from the Stage 7 plan: simulated integrations must never
    silently grow a real outbound call. Scans the actual source for
    telltale signs of a wired SMS/USSD gateway (Twilio, Africa's Talking,
    Hubtel SMS, a raw requests/httpx call inside ussd.py) so this fails
    loudly the day someone adds one without updating this test and the
    "SIMULATED" documentation deliberately.
    """
    import pathlib

    ussd_source = (pathlib.Path(__file__).parent.parent.parent / "app" / "routers" / "ussd.py").read_text(encoding="utf-8")
    forbidden_markers = ["requests.", "httpx.", "twilio", "africastalking", "hubtel", "smtplib", "boto3"]
    lowered = ussd_source.lower()
    hits = [m for m in forbidden_markers if m in lowered]
    assert hits == [], f"ussd.py appears to call a real external gateway ({hits}) -- delivery must stay SIMULATED until a provider is actually chosen (PRD Section 1.1/12)."


@pytest.mark.parametrize("wrong_role", [Role.BUYER, Role.VENDOR, Role.AGRONOMIST, Role.LOGISTICS, Role.FINANCE, Role.SUPER_ADMIN])
def test_ussd_routes_blocked_for_non_farmer_roles(client, roles, rate_config, wrong_role):
    token = login(client, roles[wrong_role].email)
    res = client.get("/ussd/sms-log", headers=auth_headers(token))
    assert res.status_code == 403
