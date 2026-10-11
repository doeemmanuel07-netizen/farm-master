"""
Payment orchestration -- the only code that changes a payment's status.

start_commitment_fee_payment() asks the configured driver to initiate and
records a PENDING payment. apply_webhook() is the single place a payment
becomes SUCCESS or FAILED, and it runs only on an event the driver has
verified. It is idempotent: a provider retrying a callback, or a late
callback for an already-settled payment, changes nothing.
"""

import json
import os
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from ..audit import log_audit
from ..models import (
    BuyerRequirement, CommitmentFeePayment, PaymentNetwork, PaymentStatus, RequirementStatus, User,
)
from .base import InitiateRequest, PaymentProvider, WebhookEvent
from ..state import transition

NETWORK_LABEL = {
    PaymentNetwork.MTN_MOMO: "MTN MoMo",
    PaymentNetwork.TELECEL_CASH: "Telecel Cash",
    PaymentNetwork.AT_MONEY: "AT Money",
    PaymentNetwork.CARD: "Card",
}
NETWORK_HINT = {
    PaymentNetwork.TELECEL_CASH: "formerly Vodafone Cash",
    PaymentNetwork.AT_MONEY: "formerly AirtelTigo Money",
}
# Pre-rebrand method names the original buyer flow sent; still accepted.
LEGACY_METHOD = {
    "momo": PaymentNetwork.MTN_MOMO,
    "vodafone": PaymentNetwork.TELECEL_CASH,
    "airteltigo": PaymentNetwork.AT_MONEY,
    "card": PaymentNetwork.CARD,
}

_provider_override: Optional[PaymentProvider] = None


def provider_name() -> str:
    return os.environ.get("FARM_MASTER_PAYMENT_PROVIDER", "sandbox").lower()


def get_provider() -> PaymentProvider:
    if _provider_override is not None:
        return _provider_override
    name = provider_name()
    if name == "paystack":
        from .paystack import PaystackProvider
        return PaystackProvider()
    if name == "hubtel":
        from .hubtel import HubtelProvider
        return HubtelProvider()
    from .sandbox import SandboxProvider
    return SandboxProvider()


def set_provider_override(provider: Optional[PaymentProvider]) -> None:
    """Test hook: route get_provider() to a specific driver instance."""
    global _provider_override
    _provider_override = provider


def public_base_url() -> str:
    return os.environ.get("FARM_MASTER_PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def start_commitment_fee_payment(
    db: Session, requirement: BuyerRequirement, buyer: User, network: PaymentNetwork, payer_phone: Optional[str],
) -> CommitmentFeePayment:
    provider = get_provider()
    our_ref = f"FMP-{uuid.uuid4().hex[:12].upper()}"
    result = provider.initiate(InitiateRequest(
        reference=our_ref, amount=requirement.commitment_fee_amount, network=network,
        payer_phone=payer_phone, payer_email=buyer.email,
        description=f"Farm Master commitment fee {requirement.reference or requirement.id[:8]}",
        callback_url=f"{public_base_url()}/payments/webhook/{provider.name}",
    ))
    payment = CommitmentFeePayment(
        requirement_id=requirement.id, amount=requirement.commitment_fee_amount,
        method=network.value, network=network, payer_phone=payer_phone, provider=provider.name,
        provider_ref=result.provider_ref, transaction_ref=result.provider_ref, checkout_url=result.checkout_url,
        status=PaymentStatus.FAILED if result.status == "failed" else PaymentStatus.PENDING,
        failure_reason=result.failure_reason,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    payment.display_text = result.display_text  # transient, for the response only
    log_audit(db, buyer, "commitment_fee_initiated",
              f"Requirement {requirement.reference}: GHS {payment.amount} via {NETWORK_LABEL[network]} "
              f"({provider.name}), ref {payment.provider_ref}, status {payment.status.value}.")
    return payment


class WebhookMismatch(RuntimeError):
    pass


def apply_webhook(db: Session, provider: PaymentProvider, event: WebhookEvent) -> CommitmentFeePayment:
    payment = (
        db.query(CommitmentFeePayment)
        .filter(CommitmentFeePayment.provider == provider.name, CommitmentFeePayment.provider_ref == event.provider_ref)
        .first()
    )
    if payment is None:
        raise WebhookMismatch(f"No {provider.name} payment with reference {event.provider_ref}.")
    if payment.status != PaymentStatus.PENDING:
        return payment  # already settled -- a retried or late callback is a no-op

    requirement = db.query(BuyerRequirement).filter(BuyerRequirement.id == payment.requirement_id).first()
    payment.webhook_payload = json.dumps(dict(event.raw), default=str)[:20000]

    if event.status == "success":
        if event.amount is not None and abs(event.amount - payment.amount) > 0.005:
            payment.status = PaymentStatus.FAILED
            payment.failure_reason = f"Amount mismatch: provider reported GHS {event.amount}, expected GHS {payment.amount}."
            db.commit()
            log_audit(db, None, "commitment_fee_amount_mismatch", f"Payment {payment.provider_ref}: {payment.failure_reason}")
            return payment
        payment.status = PaymentStatus.SUCCESS
        payment.paid_at = datetime.utcnow()
        if requirement and requirement.status == RequirementStatus.PENDING_PAYMENT:
            transition(requirement, RequirementStatus.MATCHING)
        db.commit()
        log_audit(db, None, "commitment_fee_captured",
                  f"Requirement {requirement.reference if requirement else payment.requirement_id}: GHS {payment.amount} "
                  f"via {NETWORK_LABEL.get(payment.network, payment.method)} ({provider.name}), ref {payment.provider_ref}.")
    else:
        payment.status = PaymentStatus.FAILED
        payment.failure_reason = event.failure_reason or "Payment failed."
        db.commit()
        log_audit(db, None, "commitment_fee_failed", f"Payment {payment.provider_ref}: {payment.failure_reason}")
    db.refresh(payment)
    return payment
