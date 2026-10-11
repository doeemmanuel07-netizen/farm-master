"""
Payments behind the PaymentProvider interface (CEO demo brief §2D/§5.1):
the new buyer order form, FM-#### references, the commitment fee rule,
webhook-only settlement (signature, idempotency, amount check, decline and
retry), the sandbox simulator's guard rails, and the ops payments list.
"""

from datetime import date, timedelta

import pytest

from app.models import Role
from app.payments.sandbox import SandboxProvider
from tests.conftest import login, auth_headers, sandbox_approve

pytestmark = pytest.mark.integration


def _form(client, token):
    res = client.get("/buyer/order-form", headers=auth_headers(token))
    assert res.status_code == 200, res.text
    return res.json()


def _submit(client, token, qty=120.0, days=60, **extra):
    form = _form(client, token)
    variety = form["crops"][0]["varieties"][0]["id"]
    body = {"crop_variety_id": variety, "quantity_tonnes": qty,
            "delivery_by": (date.today() + timedelta(days=days)).isoformat(),
            "spec_notes": "Grade A, moisture content below 13%, bagged in 50kg sacks."}
    body.update(extra)
    return client.post("/buyer/requirements", json=body, headers=auth_headers(token))


def _pay(client, token, req_id, network="mtn_momo", phone="0241234567"):
    res = client.post(f"/buyer/requirements/{req_id}/pay", json={"network": network, "payer_phone": phone},
                      headers=auth_headers(token))
    assert res.status_code == 200, res.text
    return res.json()


def test_order_form_is_built_from_config_not_hardcoded(client, roles, rate_config):
    form = _form(client, login(client, roles[Role.BUYER].email))
    assert [c["name"] for c in form["crops"]] == ["Maize"]
    assert form["crops"][0]["varieties"][0]["name"] == "Obatanpa"
    assert form["earliest_delivery_by"] == (date.today() + timedelta(days=28)).isoformat()
    labels = [o["label"] for o in form["payment_options"]]
    assert labels == ["MTN MoMo", "Telecel Cash", "AT Money", "Card"]
    assert form["provider"] == "sandbox"


def test_demo_form_submission_gets_sequential_fm_reference_and_reference_price(client, roles, rate_config):
    token = login(client, roles[Role.BUYER].email)
    a = _submit(client, token).json()
    b = _submit(client, token, qty=5).json()
    assert a["reference"].startswith("FM-") and b["reference"].startswith("FM-")
    assert int(b["reference"][3:]) == int(a["reference"][3:]) + 1
    assert a["crop"] == "Maize" and a["variety"] == "Obatanpa"
    assert a["price_per_tonne"] == 2150.0  # Maize reference price (decision D2)
    assert a["commitment_fee_amount"] == 120 * 90.0
    assert a["status_label"] == "Awaiting payment" and a["stage_index"] == 0
    assert a["steps"] == ["Order placed", "Farmer matched", "In production", "Aggregating", "Delivered"]


def test_delivery_date_must_respect_minimum_lead_time(client, roles, rate_config):
    token = login(client, roles[Role.BUYER].email)
    res = _submit(client, token, days=3)
    assert res.status_code == 422 and "on or after" in res.json()["detail"]


def test_inactive_crop_cannot_be_ordered_until_admin_activates_it(client, roles, rate_config, db_session):
    from app.models import Crop
    soy = db_session.query(Crop).filter(Crop.name == "Soybean").first()
    token = login(client, roles[Role.BUYER].email)
    res = _submit(client, token, crop_variety_id=soy.varieties[0].id)
    assert res.status_code == 422 and "isn't open for ordering" in res.json()["detail"]

    admin = login(client, roles[Role.SUPER_ADMIN].email)
    client.put(f"/admin/crops/{soy.id}", json={"is_active_for_ordering": True}, headers=auth_headers(admin))
    res = _submit(client, token, crop_variety_id=soy.varieties[0].id)
    assert res.status_code == 200 and res.json()["crop"] == "Soybean"


def test_fee_quote_and_percent_of_value_rule(client, roles, rate_config):
    token = login(client, roles[Role.BUYER].email)
    q = client.get("/buyer/fee-quote?quantity_tonnes=0.5&price_per_tonne=2000", headers=auth_headers(token)).json()
    assert q["amount"] == 90.0 and "minimum" in q["explanation"]

    admin = login(client, roles[Role.SUPER_ADMIN].email)
    res = client.post("/admin/commitment-fee-rules", json={
        "name": "1.5% of order value, GH₵ 500 minimum", "basis": "percent_of_value", "rate": 0.015, "minimum_amount": 500,
    }, headers=auth_headers(admin))
    assert res.status_code == 200 and res.json()["is_active"]
    rules = client.get("/admin/commitment-fee-rules", headers=auth_headers(admin)).json()
    assert sum(r["is_active"] for r in rules) == 1
    q = client.get("/buyer/fee-quote?quantity_tonnes=120&price_per_tonne=2150", headers=auth_headers(token)).json()
    assert q["amount"] == round(120 * 2150 * 0.015, 2)
    assert _submit(client, token).json()["commitment_fee_amount"] == round(120 * 2150 * 0.015, 2)


@pytest.mark.parametrize("body", [
    {"name": "x", "basis": "percent_of_value", "rate": 1.5, "minimum_amount": 0},
    {"name": "x", "basis": "per_tonne", "rate": 0, "minimum_amount": 0},
    {"name": "x", "basis": "per_tonne", "rate": 90, "minimum_amount": -1},
])
def test_fee_rule_validation(client, roles, rate_config, body):
    admin = login(client, roles[Role.SUPER_ADMIN].email)
    assert client.post("/admin/commitment-fee-rules", json=body, headers=auth_headers(admin)).status_code == 422


def test_fee_rules_are_super_admin_only(client, roles, rate_config):
    for role in (Role.FINANCE, Role.BUYER):
        token = login(client, roles[role].email)
        assert client.get("/admin/commitment-fee-rules", headers=auth_headers(token)).status_code == 403


def test_superseded_per_tonne_rate_row_refuses_edits(client, roles, rate_config):
    admin = login(client, roles[Role.SUPER_ADMIN].email)
    res = client.put("/admin/rates/buyer_commitment_fee_per_tonne", json={"value": 50}, headers=auth_headers(admin))
    assert res.status_code == 409 and "commitment-fee-rules" in res.json()["detail"]


def test_webhook_with_bad_signature_is_rejected_and_changes_nothing(client, roles, rate_config):
    token = login(client, roles[Role.BUYER].email)
    req = _submit(client, token).json()
    pay = _pay(client, token, req["id"])
    body = f'{{"event": "payment.success", "reference": "{pay["provider_ref"]}", "amount": {pay["amount"]}}}'
    res = client.post("/payments/webhook/sandbox", content=body, headers={"x-sandbox-signature": "forged"})
    assert res.status_code == 400
    assert client.get(f"/buyer/payments/{pay['id']}", headers=auth_headers(token)).json()["status"] == "pending"


def test_signed_webhook_settles_and_retried_webhook_is_a_no_op(client, roles, rate_config):
    token = login(client, roles[Role.BUYER].email)
    req = _submit(client, token).json()
    pay = _pay(client, token, req["id"])
    headers, body = SandboxProvider().build_webhook(pay["provider_ref"], "success", pay["amount"])
    first = client.post("/payments/webhook/sandbox", content=body, headers=headers)
    second = client.post("/payments/webhook/sandbox", content=body, headers=headers)
    assert first.json()["payment_status"] == "success" and second.json()["payment_status"] == "success"
    admin = login(client, roles[Role.SUPER_ADMIN].email)
    actions = [e["action"] for e in client.get("/admin/audit-log", headers=auth_headers(admin)).json()]
    assert actions.count("commitment_fee_captured") == 1


def test_webhook_amount_mismatch_fails_the_payment(client, roles, rate_config):
    token = login(client, roles[Role.BUYER].email)
    req = _submit(client, token).json()
    pay = _pay(client, token, req["id"])
    headers, body = SandboxProvider().build_webhook(pay["provider_ref"], "success", 1.0)
    assert client.post("/payments/webhook/sandbox", content=body, headers=headers).json()["payment_status"] == "failed"
    assert client.get(f"/buyer/requirements/{req['id']}", headers=auth_headers(token)).json()["status"] == "pending_payment"


def test_webhook_for_inactive_provider_or_unknown_ref_404s(client, roles, rate_config):
    assert client.post("/payments/webhook/paystack", content=b"{}").status_code == 404
    headers, body = SandboxProvider().build_webhook("SBX-NOPE", "success", 1.0)
    assert client.post("/payments/webhook/sandbox", content=body, headers=headers).status_code == 404


def test_declined_payment_can_be_retried_on_another_network(client, roles, rate_config):
    token = login(client, roles[Role.BUYER].email)
    req = _submit(client, token).json()
    first = _pay(client, token, req["id"])
    assert sandbox_approve(client, token, first, "decline")["payment_status"] == "failed"
    failed = client.get(f"/buyer/payments/{first['id']}", headers=auth_headers(token)).json()
    assert failed["failure_reason"]
    second = _pay(client, token, req["id"], network="telecel_cash")
    sandbox_approve(client, token, second)
    order = client.get(f"/buyer/requirements/{req['id']}", headers=auth_headers(token)).json()
    assert order["status"] == "matching" and order["paid"] is True


def test_mobile_money_needs_a_phone_number(client, roles, rate_config, db_session):
    buyer = roles[Role.BUYER]
    buyer.phone = None
    db_session.commit()
    token = login(client, buyer.email)
    req = _submit(client, token).json()
    res = client.post(f"/buyer/requirements/{req['id']}/pay", json={"network": "at_money"}, headers=auth_headers(token))
    assert res.status_code == 422


def test_sandbox_simulator_only_for_the_paying_buyer(client, roles, rate_config, make_user):
    token = login(client, roles[Role.BUYER].email)
    req = _submit(client, token).json()
    pay = _pay(client, token, req["id"])
    other = login(client, make_user(Role.BUYER).email)
    res = client.post(f"/payments/sandbox/{pay['provider_ref']}/approve", headers=auth_headers(other))
    assert res.status_code == 404
    assert client.get(f"/buyer/payments/{pay['id']}", headers=auth_headers(other)).status_code == 404


def test_ops_payments_list_rbac_and_content(client, roles, rate_config):
    token = login(client, roles[Role.BUYER].email)
    req = _submit(client, token).json()
    sandbox_approve(client, token, _pay(client, token, req["id"]))
    for role in (Role.FINANCE, Role.SUPER_ADMIN, Role.COMPLIANCE_OFFICER):
        rows = client.get("/ops/payments", headers=auth_headers(login(client, roles[role].email))).json()
        row = next(r for r in rows if r["requirement_reference"] == req["reference"])
        assert row["status"] == "success" and row["network_label"] == "MTN MoMo"
    for role in (Role.BUYER, Role.FARMER, Role.AGRONOMIST, Role.LOGISTICS):
        assert client.get("/ops/payments", headers=auth_headers(login(client, roles[role].email))).status_code == 403
