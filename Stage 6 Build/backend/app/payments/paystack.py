"""
Paystack driver (Ghana: GHS, mobile money + card).

Written against Paystack's published API -- Charge API for mobile money,
Transaction Initialize for card (hosted checkout), HMAC-SHA512
x-paystack-signature webhooks -- but NOT yet exercised against live or test
credentials: the gateway choice is still open (PRD Section 1.1). Tests
cover it with a mocked HTTP transport only. Activate with
FARM_MASTER_PAYMENT_PROVIDER=paystack and PAYSTACK_SECRET_KEY.
"""

import hashlib
import hmac
import json
import os
from typing import Mapping, Optional

import httpx

from ..models import PaymentNetwork
from .base import (
    InitiateRequest, InitiateResult, PaymentProvider, PaymentProviderError, WebhookEvent,
    WebhookVerificationError,
)

API = "https://api.paystack.co"
MOMO_PROVIDER_CODE = {
    PaymentNetwork.MTN_MOMO: "mtn",
    PaymentNetwork.TELECEL_CASH: "vod",  # Paystack still uses the Vodafone-era code
    PaymentNetwork.AT_MONEY: "atl",
}


class PaystackProvider(PaymentProvider):
    name = "paystack"

    def __init__(self, secret_key: Optional[str] = None, client: Optional[httpx.Client] = None):
        self.secret_key = secret_key or os.environ.get("PAYSTACK_SECRET_KEY", "")
        if not self.secret_key:
            raise PaymentProviderError("PAYSTACK_SECRET_KEY is not set.")
        self.client = client or httpx.Client(base_url=API, timeout=20)

    def _post(self, path: str, payload: dict) -> dict:
        try:
            res = self.client.post(path, json=payload, headers={"Authorization": f"Bearer {self.secret_key}"})
        except httpx.HTTPError as exc:
            raise PaymentProviderError(f"Paystack unreachable: {exc}") from exc
        body = res.json() if res.content else {}
        if res.status_code >= 400 or not body.get("status"):
            raise PaymentProviderError(body.get("message") or f"Paystack error {res.status_code}")
        return body["data"]

    def initiate(self, req: InitiateRequest) -> InitiateResult:
        pesewas = int(round(req.amount * 100))
        if req.network == PaymentNetwork.CARD:
            data = self._post("/transaction/initialize", {
                "email": req.payer_email, "amount": pesewas, "currency": "GHS",
                "reference": req.reference, "callback_url": req.callback_url, "channels": ["card"],
            })
            return InitiateResult(
                provider_ref=data.get("reference", req.reference), checkout_url=data["authorization_url"],
                display_text="Complete the card payment on the Paystack checkout page.",
            )
        data = self._post("/charge", {
            "email": req.payer_email, "amount": pesewas, "currency": "GHS", "reference": req.reference,
            "mobile_money": {"phone": req.payer_phone, "provider": MOMO_PROVIDER_CODE[req.network]},
        })
        if data.get("status") == "failed":
            return InitiateResult(provider_ref=req.reference, status="failed",
                                  failure_reason=data.get("gateway_response") or "Charge failed.")
        return InitiateResult(
            provider_ref=data.get("reference", req.reference),
            display_text=data.get("display_text") or "Approve the prompt on your phone to confirm.",
        )

    def parse_webhook(self, headers: Mapping[str, str], body: bytes) -> WebhookEvent:
        given = {k.lower(): v for k, v in headers.items()}.get("x-paystack-signature", "")
        expected = hmac.new(self.secret_key.encode(), body, hashlib.sha512).hexdigest()
        if not hmac.compare_digest(given, expected):
            raise WebhookVerificationError("Bad Paystack signature.")
        try:
            payload = json.loads(body)
            data = payload["data"]
            ref = data["reference"]
        except (ValueError, KeyError) as exc:
            raise WebhookVerificationError(f"Malformed Paystack webhook: {exc}") from exc
        event = payload.get("event")
        if event == "charge.success" and data.get("status") == "success":
            status = "success"
        elif data.get("status") in ("failed", "abandoned", "reversed"):
            status = "failed"
        else:
            raise WebhookVerificationError(f"Ignored Paystack event '{event}' / status '{data.get('status')}'.")
        amount = data.get("amount")
        return WebhookEvent(
            provider_ref=ref, status=status,
            amount=(amount / 100.0) if isinstance(amount, (int, float)) else None,
            failure_reason=data.get("gateway_response") if status == "failed" else None, raw=payload,
        )
