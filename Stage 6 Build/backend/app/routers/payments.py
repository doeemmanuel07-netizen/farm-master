"""
Provider webhooks and the sandbox phone simulator (CEO demo brief §5.1:
"handle pending -> webhook confirmation; never mark an order paid on the
client side").

POST /payments/webhook/{provider} is the only route that settles a payment.
It's unauthenticated by design (the provider calls it), so trust comes
entirely from the driver's signature / server-side status check.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import BuyerRequirement, CommitmentFeePayment, PaymentStatus, Role, User
from ..payments.base import WebhookVerificationError
from ..payments.sandbox import SandboxProvider
from ..payments.service import WebhookMismatch, apply_webhook, get_provider

router = APIRouter(prefix="/payments", tags=["payments"])


def _process(db: Session, provider, headers, body: bytes):
    try:
        event = provider.parse_webhook(headers, body)
    except WebhookVerificationError as exc:
        raise HTTPException(status_code=400, detail=f"Webhook rejected: {exc}")
    try:
        payment = apply_webhook(db, provider, event)
    except WebhookMismatch as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"ok": True, "payment_status": payment.status.value}


@router.post("/webhook/{provider_name}")
async def provider_webhook(provider_name: str, request: Request, db: Session = Depends(get_db)):
    provider = get_provider()
    if provider.name != provider_name:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' is not active.")
    body = await request.body()
    return _process(db, provider, dict(request.headers), body)


@router.post("/sandbox/{provider_ref}/{outcome}")
def sandbox_simulate(
    provider_ref: str, outcome: str,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    """
    Stands in for the payer approving or declining the prompt on their phone.
    Only exists while the sandbox driver is active, only for the paying buyer
    (or Super Admin), and settles the payment through the same signed-webhook
    path a real provider callback uses.
    """
    provider = get_provider()
    if not isinstance(provider, SandboxProvider):
        raise HTTPException(status_code=404, detail="The sandbox simulator is only available with the sandbox provider.")
    if outcome not in ("approve", "decline"):
        raise HTTPException(status_code=404, detail="Outcome must be 'approve' or 'decline'.")
    payment = (
        db.query(CommitmentFeePayment)
        .filter(CommitmentFeePayment.provider == "sandbox", CommitmentFeePayment.provider_ref == provider_ref)
        .first()
    )
    req = db.query(BuyerRequirement).filter(BuyerRequirement.id == payment.requirement_id).first() if payment else None
    if not payment or not req or (req.buyer_id != user.id and user.role != Role.SUPER_ADMIN):
        raise HTTPException(status_code=404, detail="Payment not found.")
    if payment.status != PaymentStatus.PENDING:
        return {"ok": True, "payment_status": payment.status.value}
    headers, body = provider.build_webhook(provider_ref, "success" if outcome == "approve" else "failed", payment.amount)
    return _process(db, provider, headers, body)
