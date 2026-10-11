"""
Hubtel driver (Ghana: mobile money via Receive Money, card via Online
Checkout).

Written against Hubtel's published API but NOT yet exercised against live
credentials -- the gateway choice is still open (PRD Section 1.1). Hubtel
callbacks carry no signature, so parse_webhook never trusts the callback
body on its own: it re-reads the transaction from Hubtel's Transaction
Status API (server-to-server, authenticated) and uses that answer. Activate
with FARM_MASTER_PAYMENT_PROVIDER=hubtel plus HUBTEL_API_ID, HUBTEL_API_KEY
and HUBTEL_POS_SALES_ID.
"""

import json
import os
from typing import Mapping, Optional

import httpx

from ..models import PaymentNetwork
from .base import (
    InitiateRequest, InitiateResult, PaymentProvider, PaymentProviderError, WebhookEvent,
    WebhookVerificationError,
)

RECEIVE_URL = "https://rmp.hubtel.com/merchantaccount/merchants/{pos}/receive/mobilemoney"
CHECKOUT_URL = "https://payproxyapi.hubtel.com/items/initiate"
STATUS_URL = "https://api-txnstatus.hubtel.com/transactions/{pos}/status"
CHANNEL = {
    PaymentNetwork.MTN_MOMO: "mtn-gh",
    PaymentNetwork.TELECEL_CASH: "vodafone-gh",
    PaymentNetwork.AT_MONEY: "tigo-gh",
}


def _msisdn(phone: Optional[str]) -> str:
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if digits.startswith("0"):
        digits = "233" + digits[1:]
    return digits


class HubtelProvider(PaymentProvider):
    name = "hubtel"

    def __init__(self, api_id: Optional[str] = None, api_key: Optional[str] = None,
                 pos_sales_id: Optional[str] = None, client: Optional[httpx.Client] = None):
        self.api_id = api_id or os.environ.get("HUBTEL_API_ID", "")
        self.api_key = api_key or os.environ.get("HUBTEL_API_KEY", "")
        self.pos = pos_sales_id or os.environ.get("HUBTEL_POS_SALES_ID", "")
        if not (self.api_id and self.api_key and self.pos):
            raise PaymentProviderError("HUBTEL_API_ID, HUBTEL_API_KEY and HUBTEL_POS_SALES_ID must all be set.")
        self.client = client or httpx.Client(timeout=20)
        self.auth = (self.api_id, self.api_key)

    def initiate(self, req: InitiateRequest) -> InitiateResult:
        try:
            if req.network == PaymentNetwork.CARD:
                res = self.client.post(CHECKOUT_URL, auth=self.auth, json={
                    "totalAmount": req.amount, "description": req.description, "callbackUrl": req.callback_url,
                    "returnUrl": req.callback_url, "cancellationUrl": req.callback_url,
                    "merchantAccountNumber": self.pos, "clientReference": req.reference,
                })
            else:
                res = self.client.post(RECEIVE_URL.format(pos=self.pos), auth=self.auth, json={
                    "CustomerMsisdn": _msisdn(req.payer_phone), "CustomerEmail": req.payer_email,
                    "Channel": CHANNEL[req.network], "Amount": req.amount,
                    "PrimaryCallbackUrl": req.callback_url, "Description": req.description,
                    "ClientReference": req.reference,
                })
        except httpx.HTTPError as exc:
            raise PaymentProviderError(f"Hubtel unreachable: {exc}") from exc
        body = res.json() if res.content else {}
        if res.status_code >= 400:
            raise PaymentProviderError(body.get("message") or body.get("Message") or f"Hubtel error {res.status_code}")
        if req.network == PaymentNetwork.CARD:
            url = (body.get("data") or {}).get("checkoutUrl")
            if not url:
                raise PaymentProviderError("Hubtel checkout returned no checkoutUrl.")
            return InitiateResult(provider_ref=req.reference, checkout_url=url,
                                  display_text="Complete the card payment on the Hubtel checkout page.")
        if body.get("ResponseCode") not in ("0001", "0000"):
            return InitiateResult(provider_ref=req.reference, status="failed",
                                  failure_reason=body.get("Message") or "Hubtel declined the request.")
        return InitiateResult(provider_ref=req.reference, display_text="Approve the prompt on your phone to confirm.")

    def _status(self, client_reference: str) -> dict:
        try:
            res = self.client.get(STATUS_URL.format(pos=self.pos), auth=self.auth,
                                  params={"clientReference": client_reference})
        except httpx.HTTPError as exc:
            raise WebhookVerificationError(f"Hubtel status check unreachable: {exc}") from exc
        if res.status_code >= 400:
            raise WebhookVerificationError(f"Hubtel status check failed ({res.status_code}).")
        return (res.json() or {}).get("data") or {}

    def parse_webhook(self, headers: Mapping[str, str], body: bytes) -> WebhookEvent:
        try:
            payload = json.loads(body)
            data = payload.get("Data") or payload.get("data") or {}
            ref = data.get("ClientReference") or data.get("clientReference")
        except ValueError as exc:
            raise WebhookVerificationError(f"Malformed Hubtel callback: {exc}") from exc
        if not ref:
            raise WebhookVerificationError("Hubtel callback has no ClientReference.")
        # Unsigned callback: the authoritative answer comes from the status API.
        confirmed = self._status(ref)
        state = str(confirmed.get("status", "")).lower()
        if state in ("paid", "success", "successful"):
            status = "success"
        elif state in ("unpaid", "failed", "refunded", "cancelled"):
            status = "failed"
        else:
            raise WebhookVerificationError(f"Hubtel transaction {ref} still '{state}'.")
        amount = confirmed.get("amount")
        return WebhookEvent(provider_ref=ref, status=status,
                            amount=float(amount) if amount is not None else None,
                            failure_reason=None if status == "success" else f"Hubtel status '{state}'.",
                            raw={"callback": payload, "status_check": confirmed})
