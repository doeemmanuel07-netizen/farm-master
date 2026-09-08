"""
Buyer commitment-fee flow -- the real backend behind
buyer_commitment_fee_flow_live.html, replacing the Stage 5 prototype's
local JS state with a real database and real validation.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    User, Role, RateConfig, BuyerRequirement, RequirementStatus, CommitmentFeePayment, PaymentStatus,
    HarvestPickupRequest, FulfilmentIntake, GradeResult, DispatchJob,
)
from ..auth import require_roles, get_current_user
from ..audit import log_audit
from ..reconciliation import compute_figures
from ..schemas import (
    RequirementCreate, RequirementResponse, PaymentRequest, PaymentResponse,
    BuyerDashboardResponse, BuyerDocumentsResponse, BuyerDocumentRow,
    BuyerTrackingResponse, BuyerTrackingLogRow, BuyerInvoiceResponse,
)

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


# ---------------------------------------------------------------------------
# Buyer Dashboard, Specification & Compliance Documents, Fulfilment &
# Delivery Tracking, Final Invoice & Settlement -- added 8 Sep 2026, closing
# gaps this session's own completeness audit surfaced (Stage 3 wireframe
# screens in scope from day one, never built).
# ---------------------------------------------------------------------------


@router.get("/requirements", response_model=List[RequirementResponse])
def my_requirements(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.BUYER)),
):
    return (
        db.query(BuyerRequirement)
        .filter(BuyerRequirement.buyer_id == user.id)
        .order_by(BuyerRequirement.created_at.desc())
        .all()
    )


def _own_requirement_or_404(db: Session, requirement_id: str, user: User) -> BuyerRequirement:
    req = db.query(BuyerRequirement).filter(BuyerRequirement.id == requirement_id).first()
    if not req or req.buyer_id != user.id:
        raise HTTPException(status_code=404, detail="Requirement not found.")
    return req


@router.get("/dashboard", response_model=BuyerDashboardResponse)
def buyer_dashboard(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.BUYER)),
):
    reqs = db.query(BuyerRequirement).filter(BuyerRequirement.buyer_id == user.id).order_by(BuyerRequirement.created_at.desc()).all()
    fees_due = sum(1 for r in reqs if r.status == RequirementStatus.PENDING_PAYMENT)
    in_transit = sum(r.quantity_tonnes for r in reqs if r.status in (RequirementStatus.AGGREGATION, RequirementStatus.SHIPMENT))

    graded_ids = [r.id for r in reqs]
    intakes = (
        db.query(FulfilmentIntake)
        .join(HarvestPickupRequest, FulfilmentIntake.harvest_pickup_request_id == HarvestPickupRequest.id)
        .filter(HarvestPickupRequest.buyer_requirement_id.in_(graded_ids))
        .all()
    ) if graded_ids else []
    compliance_rate = round(100.0 * sum(1 for i in intakes if i.grade != GradeResult.REJECT) / len(intakes), 1) if intakes else None

    return BuyerDashboardResponse(
        active_orders=len(reqs), commitment_fees_due=fees_due,
        maize_in_transit_tonnes=round(in_transit, 2), spec_compliance_rate_pct=compliance_rate,
        recent_orders=reqs[:5],
    )


@router.get("/requirements/{requirement_id}/docs", response_model=BuyerDocumentsResponse)
def buyer_docs(
    requirement_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.BUYER)),
):
    req = _own_requirement_or_404(db, requirement_id, user)
    intakes = (
        db.query(FulfilmentIntake)
        .join(HarvestPickupRequest, FulfilmentIntake.harvest_pickup_request_id == HarvestPickupRequest.id)
        .filter(HarvestPickupRequest.buyer_requirement_id == req.id)
        .all()
    )
    rows = [
        BuyerDocumentRow(
            label=f"Grading result -- {i.grade.value.replace('_', ' ').title()}",
            doc_type="Inspection", status="verified",
            detail=f"{i.weigh_in_kg:.0f}kg, graded {i.created_at.strftime('%Y-%m-%d')}",
        ) for i in intakes
    ]
    rows.append(BuyerDocumentRow(
        label="MoFA compliance export (CSV/PDF)", doc_type="MoFA report",
        status="not_yet_available" if not intakes else "pending",
        detail="Generated by Farm Master Finance once this order is delivered and graded.",
    ))
    return BuyerDocumentsResponse(buyer_requirement_id=req.id, rows=rows)


@router.get("/requirements/{requirement_id}/tracking", response_model=BuyerTrackingResponse)
def buyer_tracking(
    requirement_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.BUYER)),
):
    req = _own_requirement_or_404(db, requirement_id, user)
    pickups = db.query(HarvestPickupRequest).filter(HarvestPickupRequest.buyer_requirement_id == req.id).all()
    log = []
    delivered_tonnes = 0.0
    for pickup in pickups:
        job = db.query(DispatchJob).filter(DispatchJob.harvest_pickup_request_id == pickup.id).first()
        intake = db.query(FulfilmentIntake).filter(FulfilmentIntake.harvest_pickup_request_id == pickup.id).first()
        if job and job.status.value == "assigned":
            log.append(BuyerTrackingLogRow(text=f"Pickup scheduled, {pickup.preferred_pickup_date}", when=pickup.created_at))
        if job and job.delivered_at:
            log.append(BuyerTrackingLogRow(text="Lot arrived at fulfilment centre", when=job.delivered_at))
        if intake:
            grade_label = intake.grade.value.replace("_", " ").title()
            log.append(BuyerTrackingLogRow(text=f"Lot intake -- graded {grade_label}", when=intake.created_at))
            if intake.grade != GradeResult.REJECT:
                delivered_tonnes += intake.weigh_in_kg / 1000.0
    log.sort(key=lambda r: r.when, reverse=True)
    return BuyerTrackingResponse(
        buyer_requirement_id=req.id, status=req.status,
        accepted_delivered_tonnes=round(delivered_tonnes, 3), target_quantity_tonnes=req.quantity_tonnes,
        log=log,
    )


@router.get("/requirements/{requirement_id}/invoice", response_model=BuyerInvoiceResponse)
def buyer_invoice(
    requirement_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.BUYER)),
):
    req = _own_requirement_or_404(db, requirement_id, user)
    figures = compute_figures(db, req)
    return BuyerInvoiceResponse(
        buyer_requirement_id=req.id, price_per_tonne=req.price_per_tonne,
        accepted_delivered_tonnes=figures.accepted_delivered_tonnes,
        subtotal=figures.buyer_invoice_value,
        commitment_fee_applied=figures.commitment_fee_received,
        net_payable=round(figures.buyer_invoice_value - figures.commitment_fee_received, 2),
    )
