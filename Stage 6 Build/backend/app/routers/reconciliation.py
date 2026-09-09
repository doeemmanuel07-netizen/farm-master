"""
Finance & Reconciliation -- PRD Section 6 Must-Have #5, the real backend
behind finance_reconciliation_flow_live.html. Closes out the pilot's five
must-haves (Section 6): commitment fee, trading margin, farmer settlement,
and vendor payout, computed per order (see app/reconciliation.py).

Scoped to buyer requirements that have actually paid their commitment fee
(status MATCHING or later) -- a DRAFT/PENDING_PAYMENT requirement has
nothing to reconcile yet. Release actions are financial (PRD Section 5),
so both are audited, and both require real underlying activity: settlement
needs at least one graded, non-REJECT delivery against this order; payout
needs at least one CONFIRMED vendor request against this order. Releasing
an order with nothing to release, or releasing twice, is a 409 --
reconciliation should never silently record money moving that has no real
source.

The two read-only routes (list_orders, get_order) are also open to
Role.COMPLIANCE_OFFICER as of 9 Sep 2026 -- the new Compliance/Reporting
Officer role needs order/delivery visibility to produce its MoFA reports,
but never the authority to release money. Both release-* routes below
stay Role.FINANCE-only.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    User, Role, BuyerRequirement, RequirementStatus, OrderReconciliation,
)
from ..auth import require_roles
from ..audit import log_audit
from ..reconciliation import compute_figures
from ..schemas import OrderReconciliationSummary, OrderReconciliationResponse

router = APIRouter(prefix="/finance/reconciliation", tags=["reconciliation"])

RECONCILABLE_STATUSES = [
    RequirementStatus.MATCHING, RequirementStatus.PRODUCTION,
    RequirementStatus.AGGREGATION, RequirementStatus.SHIPMENT,
]


def _get_or_create(db: Session, requirement_id: str) -> OrderReconciliation:
    row = db.query(OrderReconciliation).filter(OrderReconciliation.buyer_requirement_id == requirement_id).first()
    if row is None:
        row = OrderReconciliation(buyer_requirement_id=requirement_id)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _requirement_or_404(db: Session, requirement_id: str) -> BuyerRequirement:
    req = db.query(BuyerRequirement).filter(BuyerRequirement.id == requirement_id).first()
    if not req or req.status not in RECONCILABLE_STATUSES:
        raise HTTPException(status_code=404, detail="Order not found or not yet eligible for reconciliation.")
    return req


def _buyer_name(req: BuyerRequirement) -> str:
    return req.buyer.organisation_name or req.buyer.full_name


@router.get("", response_model=List[OrderReconciliationSummary])
def list_orders(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FINANCE, Role.COMPLIANCE_OFFICER)),
):
    reqs = db.query(BuyerRequirement).filter(BuyerRequirement.status.in_(RECONCILABLE_STATUSES)).all()
    out = []
    for req in reqs:
        figures = compute_figures(db, req)
        recon = db.query(OrderReconciliation).filter(OrderReconciliation.buyer_requirement_id == req.id).first()
        out.append(OrderReconciliationSummary(
            buyer_requirement_id=req.id,
            buyer_name=_buyer_name(req),
            grade=req.grade,
            quantity_tonnes=req.quantity_tonnes,
            status=req.status,
            accepted_delivered_tonnes=figures.accepted_delivered_tonnes,
            farmer_settlement_released=recon.farmer_settlement_released if recon else False,
            vendor_payout_released=recon.vendor_payout_released if recon else False,
        ))
    return out


@router.get("/{buyer_requirement_id}", response_model=OrderReconciliationResponse)
def get_order(
    buyer_requirement_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FINANCE, Role.COMPLIANCE_OFFICER)),
):
    req = _requirement_or_404(db, buyer_requirement_id)
    figures = compute_figures(db, req)
    recon = _get_or_create(db, req.id)
    return OrderReconciliationResponse(
        buyer_requirement_id=req.id,
        buyer_name=_buyer_name(req),
        crop=req.crop,
        grade=req.grade,
        price_per_tonne=req.price_per_tonne,
        commitment_fee_received=figures.commitment_fee_received,
        accepted_delivered_tonnes=figures.accepted_delivered_tonnes,
        buyer_invoice_value=figures.buyer_invoice_value,
        trading_margin_pct=figures.trading_margin_pct,
        trading_margin_amount=figures.trading_margin_amount,
        farmer_settlement_due=figures.farmer_settlement_due,
        vendor_payout_due=figures.vendor_payout_due,
        farmer_settlement_released=recon.farmer_settlement_released,
        farmer_settlement_released_at=recon.farmer_settlement_released_at,
        vendor_payout_released=recon.vendor_payout_released,
        vendor_payout_released_at=recon.vendor_payout_released_at,
    )


@router.post("/{buyer_requirement_id}/release-farmer-settlement", response_model=OrderReconciliationResponse)
def release_farmer_settlement(
    buyer_requirement_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FINANCE)),
):
    req = _requirement_or_404(db, buyer_requirement_id)
    figures = compute_figures(db, req)
    recon = _get_or_create(db, req.id)
    if recon.farmer_settlement_released:
        raise HTTPException(status_code=409, detail="Farmer settlement has already been released for this order.")
    if figures.accepted_delivered_tonnes <= 0:
        raise HTTPException(status_code=409, detail="No graded, non-reject delivery is linked to this order yet -- nothing to settle.")

    from datetime import datetime
    recon.farmer_settlement_released = True
    recon.farmer_settlement_released_by = user.id
    recon.farmer_settlement_released_at = datetime.utcnow()
    db.commit()
    db.refresh(recon)

    log_audit(
        db, user, "farmer_settlement_released",
        f"Order {req.id} ({_buyer_name(req)}): GHS {figures.farmer_settlement_due} released "
        f"for {figures.accepted_delivered_tonnes}t accepted delivered.",
    )
    return get_order(buyer_requirement_id, db, user)


@router.post("/{buyer_requirement_id}/release-vendor-payout", response_model=OrderReconciliationResponse)
def release_vendor_payout(
    buyer_requirement_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FINANCE)),
):
    req = _requirement_or_404(db, buyer_requirement_id)
    figures = compute_figures(db, req)
    recon = _get_or_create(db, req.id)
    if recon.vendor_payout_released:
        raise HTTPException(status_code=409, detail="Vendor payout has already been released for this order.")
    if figures.vendor_payout_due <= 0:
        raise HTTPException(status_code=409, detail="No confirmed vendor request is linked to this order yet -- nothing to pay out.")

    from datetime import datetime
    recon.vendor_payout_released = True
    recon.vendor_payout_released_by = user.id
    recon.vendor_payout_released_at = datetime.utcnow()
    db.commit()
    db.refresh(recon)

    log_audit(
        db, user, "vendor_payout_released",
        f"Order {req.id} ({_buyer_name(req)}): GHS {figures.vendor_payout_due} released to vendor.",
    )
    return get_order(buyer_requirement_id, db, user)
