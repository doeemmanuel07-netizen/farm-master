"""
Buyer commitment-fee flow -- the real backend behind
buyer_commitment_fee_flow_live.html, replacing the Stage 5 prototype's
local JS state with a real database and real validation.

Revised 11 Oct 2026 for the CEO platform demo (brief §5): requirements
carry a crop variety, a real delivery-by date, spec notes and an FM-####
reference; the commitment fee comes from the active CommitmentFeeRule; and
paying goes through a PaymentProvider driver -- PENDING until a verified
provider webhook confirms it (app/payments/), never marked paid here.
"""

from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    User, Role, RateConfig, BuyerRequirement, RequirementStatus, CommitmentFeePayment, PaymentStatus,
    HarvestPickupRequest, FulfilmentIntake, GradeResult, DispatchJob, Crop, CropVariety, FulfilmentCentre,
    PaymentNetwork, LogisticsEvent,
)
from ..auth import require_roles, get_current_user
from ..audit import log_audit
from ..fees import quote_commitment_fee, FeeRuleMissing
from ..orders import next_reference, requirement_view, earliest_delivery_date
from ..payments.base import PaymentProviderError
from ..payments.service import (
    start_commitment_fee_payment, LEGACY_METHOD, NETWORK_LABEL, NETWORK_HINT, provider_name,
)
from ..reconciliation import compute_figures
from ..reference import active_crops
from ..schemas import (
    RequirementCreate, RequirementResponse, PaymentRequest, PaymentResponse,
    BuyerDashboardResponse, BuyerDocumentsResponse, BuyerDocumentRow,
    BuyerTrackingResponse, BuyerTrackingLogRow, BuyerInvoiceResponse,
    FeeQuoteResponse, BuyerOrderFormResponse, PaymentOptionResponse, CropResponse,
)

router = APIRouter(prefix="/buyer", tags=["buyer"])


def _get_rate(db: Session, key: str) -> float:
    row = db.query(RateConfig).filter(RateConfig.key == key).first()
    if not row:
        raise HTTPException(status_code=500, detail=f"Rate config '{key}' is not seeded.")
    return row.value


def _quote(db: Session, quantity_tonnes: float, price_per_tonne: float):
    try:
        return quote_commitment_fee(db, quantity_tonnes, price_per_tonne)
    except FeeRuleMissing as exc:
        raise HTTPException(status_code=500, detail=str(exc))


def _payment_view(payment: CommitmentFeePayment, db: Session, display_text: str = None) -> PaymentResponse:
    req = db.query(BuyerRequirement).filter(BuyerRequirement.id == payment.requirement_id).first()
    resp = PaymentResponse.model_validate(payment)
    resp.network_label = NETWORK_LABEL.get(payment.network, payment.method)
    resp.display_text = display_text or getattr(payment, "display_text", None)
    resp.requirement_reference = req.reference if req else None
    resp.sandbox = payment.provider == "sandbox"
    return resp


@router.get("/order-form", response_model=BuyerOrderFormResponse)
def order_form(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.BUYER)),
):
    """Active crops/varieties, the earliest allowed delivery date and the payment options -- the form is built from this."""
    crops = []
    for c in active_crops(db):
        resp = CropResponse.model_validate(c)
        resp.varieties = [v for v in resp.varieties if v.is_active]
        crops.append(resp)
    return BuyerOrderFormResponse(
        crops=crops,
        earliest_delivery_by=earliest_delivery_date(db),
        payment_options=[
            PaymentOptionResponse(network=n, label=NETWORK_LABEL[n], hint=NETWORK_HINT.get(n), needs_phone=n != PaymentNetwork.CARD)
            for n in PaymentNetwork
        ],
        payer_phone=user.phone,
        provider=provider_name(),
    )


@router.get("/fee-quote", response_model=FeeQuoteResponse)
def fee_quote(
    quantity_tonnes: float = Query(..., gt=0),
    price_per_tonne: float = Query(..., gt=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.BUYER)),
):
    q = _quote(db, quantity_tonnes, price_per_tonne)
    return FeeQuoteResponse(amount=q.amount, rule_name=q.rule_name, basis=q.basis, rate=q.rate,
                            minimum_amount=q.minimum_amount, explanation=q.explanation)


def _resolve_variety(db: Session, crop_variety_id) -> CropVariety:
    if crop_variety_id is None:
        # Older clients (the original Stage 6 buyer flow) send no variety --
        # they only ever ordered the pilot crop, so take the first active one.
        crops = active_crops(db)
        varieties = [v for v in (crops[0].varieties if crops else []) if v.is_active]
        if not varieties:
            raise HTTPException(status_code=422, detail="No crop is currently open for ordering.")
        return varieties[0]
    variety = db.query(CropVariety).filter(CropVariety.id == crop_variety_id).first()
    if not variety or not variety.is_active:
        raise HTTPException(status_code=422, detail="That crop variety isn't available.")
    if not variety.crop.is_active_for_ordering:
        raise HTTPException(status_code=422, detail=f"{variety.crop.name} isn't open for ordering yet.")
    return variety


@router.post("/requirements", response_model=RequirementResponse)
def submit_requirement(
    payload: RequirementCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.BUYER)),
):
    if payload.quantity_tonnes is None or payload.quantity_tonnes <= 0:
        raise HTTPException(status_code=422, detail="Quantity must be greater than zero.")
    variety = _resolve_variety(db, payload.crop_variety_id)
    crop: Crop = variety.crop

    if payload.delivery_by is not None:
        earliest = earliest_delivery_date(db)
        if payload.delivery_by < earliest:
            raise HTTPException(
                status_code=422,
                detail=f"Delivery date must be on or after {earliest.strftime('%d %b %Y')} "
                       f"(the minimum lead time for a production cycle).",
            )
    elif not payload.delivery_timeline:
        raise HTTPException(status_code=422, detail="A delivery date is required.")

    price = payload.price_per_tonne if payload.price_per_tonne is not None else crop.reference_price_per_tonne
    if price <= 0:
        raise HTTPException(status_code=422, detail="Price per tonne must be greater than zero.")

    hq = db.query(FulfilmentCentre).filter(FulfilmentCentre.is_hq.is_(True)).first()
    quote = _quote(db, payload.quantity_tonnes, price)
    req = BuyerRequirement(
        buyer_id=user.id,
        reference=next_reference(db),
        crop=crop.name,
        crop_variety_id=variety.id,
        grade=(payload.grade or "As per specification").strip(),
        quantity_tonnes=payload.quantity_tonnes,
        price_per_tonne=price,
        delivery_location=payload.delivery_location or (hq.town if hq else "Tema"),
        delivery_by=payload.delivery_by,
        delivery_timeline=payload.delivery_timeline or payload.delivery_by.strftime("%d %b %Y"),
        spec_notes=(payload.spec_notes or "").strip() or None,
        commitment_fee_amount=quote.amount,
        status=RequirementStatus.PENDING_PAYMENT,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    log_audit(db, user, "requirement_submitted",
              f"{req.reference}: {req.quantity_tonnes:g} t {crop.name} ({variety.name}) at GHS {price:,.2f}/t; "
              f"commitment fee GHS {quote.amount:,.2f} ({quote.explanation}).")
    return requirement_view(db, req)


@router.get("/requirements/{requirement_id}", response_model=RequirementResponse)
def get_requirement(
    requirement_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.BUYER)),
):
    req = db.query(BuyerRequirement).filter(BuyerRequirement.id == requirement_id).first()
    if not req or req.buyer_id != user.id:
        raise HTTPException(status_code=404, detail="Requirement not found.")
    return requirement_view(db, req)


@router.post("/requirements/{requirement_id}/pay", response_model=PaymentResponse)
def pay_commitment_fee(
    requirement_id: str,
    payload: PaymentRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.BUYER)),
):
    """
    Starts a commitment-fee payment with the configured provider. Returns it
    PENDING; the order moves to MATCHING only when the provider's verified
    webhook confirms it (POST /payments/webhook/{provider}).
    """
    req = db.query(BuyerRequirement).filter(BuyerRequirement.id == requirement_id).first()
    if not req or req.buyer_id != user.id:
        raise HTTPException(status_code=404, detail="Requirement not found.")
    if req.status != RequirementStatus.PENDING_PAYMENT:
        raise HTTPException(status_code=409, detail=f"Requirement is '{req.status.value}', not payable.")

    network = payload.network or LEGACY_METHOD.get((payload.method or "").lower())
    if network is None:
        raise HTTPException(status_code=422, detail=f"Unsupported payment method '{payload.method}'.")
    phone = (payload.payer_phone or user.phone or "").strip() or None
    if network != PaymentNetwork.CARD and not phone:
        raise HTTPException(status_code=422, detail="A mobile money number is required.")

    pending = (
        db.query(CommitmentFeePayment)
        .filter(CommitmentFeePayment.requirement_id == req.id, CommitmentFeePayment.status == PaymentStatus.PENDING)
        .first()
    )
    if pending:
        raise HTTPException(status_code=409, detail="A payment for this order is already awaiting confirmation.")

    try:
        payment = start_commitment_fee_payment(db, req, user, network, phone)
    except PaymentProviderError as exc:
        raise HTTPException(status_code=502, detail=f"Payment provider error: {exc}")
    return _payment_view(payment, db)


@router.get("/payments/{payment_id}", response_model=PaymentResponse)
def get_payment(
    payment_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.BUYER)),
):
    """Polled by the payment modal while a payment is PENDING."""
    payment = db.query(CommitmentFeePayment).filter(CommitmentFeePayment.id == payment_id).first()
    req = db.query(BuyerRequirement).filter(BuyerRequirement.id == payment.requirement_id).first() if payment else None
    if not payment or not req or req.buyer_id != user.id:
        raise HTTPException(status_code=404, detail="Payment not found.")
    return _payment_view(payment, db)

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
    reqs = (
        db.query(BuyerRequirement)
        .filter(BuyerRequirement.buyer_id == user.id)
        .order_by(BuyerRequirement.created_at.desc())
        .all()
    )
    return [requirement_view(db, r) for r in reqs]


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
    # Logistics events linked to this order (brief §7: events feed Delivery Tracking).
    for ev in db.query(LogisticsEvent).filter(LogisticsEvent.buyer_requirement_id == req.id).all():
        log.append(BuyerTrackingLogRow(text=ev.public_text.removeprefix("Live: "), when=ev.created_at))
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
