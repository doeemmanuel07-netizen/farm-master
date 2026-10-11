"""
Commitment fee maths (decision D3) and the Paystack / Hubtel drivers against
a mocked HTTP transport. The drivers have NOT been run against live
credentials; these tests pin their request shapes and, above all, their
webhook verification -- a callback that can't be verified is never acted on.
"""

import hashlib
import hmac
import json

import httpx
import pytest

from app.fees import compute_fee
from app.models import CommitmentFeeRule, FeeBasis, PaymentNetwork, RequirementStatus
from app.orders import ORDER_STEPS, order_stage
from app.payments.base import InitiateRequest, WebhookVerificationError
from app.payments.hubtel import HubtelProvider
from app.payments.paystack import PaystackProvider
from app.payments.sandbox import SandboxProvider

pytestmark = pytest.mark.unit


def _rule(basis, rate, minimum):
    return CommitmentFeeRule(name="t", basis=basis, rate=rate, minimum_amount=minimum, is_active=True)


@pytest.mark.parametrize("basis,rate,minimum,qty,price,expected", [
    (FeeBasis.PER_TONNE, 90, 90, 2.0, 2100, 180.0),     # PRD §10: 2 t x GH₵ 90
    (FeeBasis.PER_TONNE, 90, 90, 0.1, 2100, 90.0),      # one-tonne minimum
    (FeeBasis.PER_TONNE, 90, 90, 120, 2150, 10800.0),
    (FeeBasis.PERCENT_OF_VALUE, 0.015, 500, 120, 2150, 3870.0),
    (FeeBasis.PERCENT_OF_VALUE, 0.015, 500, 1, 2150, 500.0),
])
def test_fee_rule_maths(basis, rate, minimum, qty, price, expected):
    assert compute_fee(_rule(basis, rate, minimum), qty, price).amount == expected


def test_every_requirement_status_maps_to_a_stage():
    for status in RequirementStatus:
        idx, label, pct, badge = order_stage(status)
        assert 0 <= idx <= len(ORDER_STEPS) and 0 <= pct <= 100 and label
    assert order_stage(RequirementStatus.DELIVERED) == (5, "Delivered", 100, "delivered")
    assert order_stage(RequirementStatus.MATCHING)[1] == "Matching farmers"


def _req(network=PaymentNetwork.MTN_MOMO):
    return InitiateRequest(reference="FMP-ABC", amount=1800.0, network=network, payer_phone="0241234567",
                           payer_email="b@x.test", description="fee", callback_url="https://x.test/cb")


def test_sandbox_rejects_tampered_body():
    sb = SandboxProvider()
    headers, body = sb.build_webhook("SBX-1", "success", 10.0)
    assert sb.parse_webhook(headers, body).status == "success"
    with pytest.raises(WebhookVerificationError):
        sb.parse_webhook(headers, body.replace(b"10.0", b"99.0"))


def test_paystack_momo_charge_shape_and_signed_webhook():
    seen = {}

    def handler(request: httpx.Request):
        seen["path"], seen["body"] = request.url.path, json.loads(request.content)
        seen["auth"] = request.headers["authorization"]
        return httpx.Response(200, json={"status": True, "data": {"reference": "FMP-ABC", "status": "send_otp", "display_text": "Dial *170#"}})

    ps = PaystackProvider(secret_key="sk_test_x", client=httpx.Client(base_url="https://api.paystack.co", transport=httpx.MockTransport(handler)))
    res = ps.initiate(_req(PaymentNetwork.TELECEL_CASH))
    assert seen["path"] == "/charge" and seen["auth"] == "Bearer sk_test_x"
    assert seen["body"]["amount"] == 180000 and seen["body"]["currency"] == "GHS"
    assert seen["body"]["mobile_money"] == {"phone": "0241234567", "provider": "vod"}
    assert res.status == "pending" and res.display_text == "Dial *170#"

    payload = json.dumps({"event": "charge.success", "data": {"reference": "FMP-ABC", "status": "success", "amount": 180000}}).encode()
    sig = hmac.new(b"sk_test_x", payload, hashlib.sha512).hexdigest()
    ev = ps.parse_webhook({"X-Paystack-Signature": sig}, payload)
    assert ev.status == "success" and ev.amount == 1800.0
    with pytest.raises(WebhookVerificationError):
        ps.parse_webhook({"X-Paystack-Signature": "0" * 128}, payload)


def test_paystack_card_uses_hosted_checkout():
    def handler(request):
        assert request.url.path == "/transaction/initialize"
        assert json.loads(request.content)["channels"] == ["card"]
        return httpx.Response(200, json={"status": True, "data": {"reference": "FMP-ABC", "authorization_url": "https://checkout.paystack.com/x"}})

    ps = PaystackProvider(secret_key="sk", client=httpx.Client(base_url="https://api.paystack.co", transport=httpx.MockTransport(handler)))
    assert ps.initiate(_req(PaymentNetwork.CARD)).checkout_url == "https://checkout.paystack.com/x"


def test_hubtel_receive_money_and_status_checked_callback():
    calls = []

    def handler(request: httpx.Request):
        calls.append(request)
        if "receive/mobilemoney" in str(request.url):
            body = json.loads(request.content)
            assert body["Channel"] == "tigo-gh" and body["CustomerMsisdn"] == "233241234567"
            assert body["ClientReference"] == "FMP-ABC"
            return httpx.Response(200, json={"ResponseCode": "0001", "Data": {"TransactionId": "T1"}})
        assert "status" in str(request.url) and request.url.params["clientReference"] == "FMP-ABC"
        return httpx.Response(200, json={"data": {"status": "Paid", "amount": 1800.0}})

    hb = HubtelProvider(api_id="id", api_key="key", pos_sales_id="POS1", client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert hb.initiate(_req(PaymentNetwork.AT_MONEY)).status == "pending"
    # The callback body itself claims nothing we trust -- the status API decides.
    ev = hb.parse_webhook({}, json.dumps({"ResponseCode": "0000", "Data": {"ClientReference": "FMP-ABC"}}).encode())
    assert ev.status == "success" and ev.amount == 1800.0
    assert any("status" in str(c.url) for c in calls)


def test_hubtel_callback_for_unpaid_transaction_is_not_success():
    def handler(request):
        return httpx.Response(200, json={"data": {"status": "Unpaid"}})

    hb = HubtelProvider(api_id="i", api_key="k", pos_sales_id="P", client=httpx.Client(transport=httpx.MockTransport(handler)))
    ev = hb.parse_webhook({}, json.dumps({"ResponseCode": "0000", "Data": {"ClientReference": "FMP-ABC"}}).encode())
    assert ev.status == "failed"
