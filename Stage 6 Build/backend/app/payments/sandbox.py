"""
Sandbox payment driver -- the default until a gateway is contracted (PRD
Section 1.1: Paystack vs Hubtel undecided).

It behaves like a real asynchronous gateway: initiate() only ever returns
PENDING, and the payment is settled later by a signed webhook. Instead of a
real phone prompt, the sandbox simulator endpoint
(POST /payments/sandbox/{provider_ref}/approve|decline, enabled only while
this driver is active) builds that webhook, signs it with the sandbox secret
and passes it through exactly the same verification and processing path a
real provider callback takes.
"""

import hashlib
import hmac
import json
import os
import uuid
from typing import Mapping

from ..models import PaymentNetwork
from .base import InitiateRequest, InitiateResult, PaymentProvider, WebhookEvent, WebhookVerificationError

SANDBOX_SECRET = os.environ.get("FARM_MASTER_SANDBOX_WEBHOOK_SECRET", "dev-only-sandbox-webhook-secret")
SIGNATURE_HEADER = "x-sandbox-signature"


def sign(body: bytes, secret: str = SANDBOX_SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class SandboxProvider(PaymentProvider):
    name = "sandbox"

    def initiate(self, req: InitiateRequest) -> InitiateResult:
        ref = f"SBX-{uuid.uuid4().hex[:12].upper()}"
        if req.network == PaymentNetwork.CARD:
            text = "Sandbox card checkout opened. Complete it to confirm the payment."
        else:
            text = f"A payment prompt was sent to {req.payer_phone}. Approve it on the phone to confirm."
        return InitiateResult(provider_ref=ref, display_text=text, checkout_url=None)

    def build_webhook(self, provider_ref: str, status: str, amount: float) -> tuple[dict, bytes]:
        body = json.dumps({"event": f"payment.{status}", "reference": provider_ref, "amount": amount}).encode()
        return {SIGNATURE_HEADER: sign(body)}, body

    def parse_webhook(self, headers: Mapping[str, str], body: bytes) -> WebhookEvent:
        given = {k.lower(): v for k, v in headers.items()}.get(SIGNATURE_HEADER, "")
        if not hmac.compare_digest(given, sign(body)):
            raise WebhookVerificationError("Bad sandbox signature.")
        try:
            data = json.loads(body)
            event, ref = data["event"], data["reference"]
        except (ValueError, KeyError) as exc:
            raise WebhookVerificationError(f"Malformed sandbox webhook: {exc}") from exc
        status = {"payment.success": "success", "payment.failed": "failed"}.get(event)
        if status is None:
            raise WebhookVerificationError(f"Unknown sandbox event '{event}'.")
        return WebhookEvent(
            provider_ref=ref, status=status, amount=data.get("amount"),
            failure_reason="Declined on the payer's phone (sandbox)." if status == "failed" else None,
            raw=data,
        )
