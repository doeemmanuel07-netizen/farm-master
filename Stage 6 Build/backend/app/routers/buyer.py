"""
Buyer commitment-fee flow -- the real backend behind
buyer_commitment_fee_flow_live.html, replacing the Stage 5 prototype's
local JS state with a real database and real validation.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Role, RateConfig, BuyerRequirement, RequirementStatus, CommitmentFeePayment, PaymentStatus
from ..auth import require_roles, get_current_user
from ..audit import log_audit
from ..schemas import RequirementCreate, RequirementResponse, PaymentRequest, PaymentResponse

router = APIRouter(prefix="/buyer", tags=["buyer"])


def _get_rate(db: Session, key: str) -> float:
    row = db.query(RateConfig).filter(RateConfig.key == key).first()
    if not row:
        raise HTTPException(status_code=500, detail=f"Rate config '{key}' is not seeded.")
    return row.value


@router.post("/requirements", response_model=RequirementResponse)
def submit_requirement(
    payload: RequirementCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.BUYER)),
):
    if payload.quantity_tonnes <= 0:
        raise HTTPException(status_code=422, detail="Quantity must be greater than zero.")
    rate = _get_rate(db, "buyer_commitment_fee_per_tonne")
    fee = round(max(rate, payload.quantity_tonnes * rate), 2)

    req = BuyerRequirement(
        buyer_id=user.id,
        crop="Maize",
        grade=payload.grade,
        quantity_tonnes=payload.quantity_tonnes,
        price_per_tonne=payload.price_per_tonne,
        delivery_location=payload.delivery_location,
        delivery_timeline=payload.delivery_timeline,
        commitment_fee_amount=fee,
        status=RequirementStatus.PENDING_PAYMENT,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


@router.get("/requirements/{requirement_id}", response_model=RequirementResponse)
def get_requirement(
    requirement_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.BUYER)),
):
    req = db.query(BuyerRequirement).filter(BuyerRequirement.id == requirement_id).first()
    if not req or req.buyer_id != user.id:
        raise HTTPException(status_code=404, detail="Requirement not found.")
    return req


VALID_METHODS = {"momo", "vodafone", "airteltigo", "card"}


@router.post("/requirements/{requirement_id}/pay", response_model=PaymentResponse)
def pay_commitment_fee(
    requirement_id: str,
    payload: PaymentRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.BUYER)),
):
    req = db.query(BuyerRequirement).filter(BuyerRequirement.id == requirement_id).first()
    if not req or req.buyer_id != user.id:
        raise HTTPException(status_code=404, detail="Requirement not found.")
    if req.status != RequirementStatus.PENDING_PAYMENT:
        raise HTTPException(status_code=409, detail=f"Requirement is '{req.status.value}', not payable.")
    if payload.method not in VALID_METHODS:
        raise HTTPException(status_code=422, detail=f"Unsupported payment method '{payload.method}'.")
    if payload.method == "card":
        # Real gateway (Paystack/Hubtel) not yet chosen -- PRD Section 1.1.
        raise HTTPException(status_code=501, detail="Card payment gateway not yet selected (Paystack/Hubtel TBD).")

    payment = CommitmentFeePayment(
        requirement_id=req.id,
        amount=req.commitment_fee_amount,
        method=payload.method,
        status=PaymentStatus.SUCCESS,  # mobile money confirmation is simulated -- no real gateway wired yet
        transaction_ref=f"SIM-{req.id[:8]}",
    )
    db.add(payment)
    req.status = RequirementStatus.MATCHING
    db.commit()
    db.refresh(payment)

    log_audit(
        db, user, "commitment_fee_captured",
        f"Requirement {req.id}: GHS {payment.amount} via {payload.method}, ref {payment.transaction_ref}.",
    )
    return payment
