"""
Shared Vendor Payout Statement computation -- Stage 3 wireframe "Payout
Statement" (Vendor Portal). Added 8 Sep 2026, closing a gap this session's
own completeness audit surfaced. Same "integrate, don't duplicate" pattern
as wallet.py/reconciliation.py -- both MechanisationRequest and InputOrder
already scope to a single vendor_id per row, so this is a direct per-order
regrouping of real data reconciliation.py already reads for Finance's own
view, not a new computation.
"""

from dataclasses import dataclass
from typing import List

from sqlalchemy.orm import Session

from .models import (
    BuyerRequirement, RateConfig, MechanisationRequest, MechanisationRequestStatus,
    InputOrder, InputOrderStatus, ProductionFormula, Opportunity, OrderReconciliation,
)


def _get_rate(db: Session, key: str) -> float:
    row = db.query(RateConfig).filter(RateConfig.key == key).first()
    if row is None:
        raise RuntimeError(f"Rate config '{key}' is not seeded.")
    return row.value


@dataclass
class VendorPayoutRow:
    buyer_requirement_id: str
    buyer_name: str
    mechanisation_amount: float
    input_order_amount: float
    total: float
    released: bool
    released_at: object


def compute_vendor_payout_rows(db: Session, vendor_id: str) -> List[VendorPayoutRow]:
    vendor_rate = _get_rate(db, "vendor_service_fee_per_tonne")

    order_ids = set()
    for r in (
        db.query(MechanisationRequest.buyer_requirement_id)
        .filter(MechanisationRequest.vendor_id == vendor_id, MechanisationRequest.buyer_requirement_id.isnot(None))
        .distinct().all()
    ):
        order_ids.add(r[0])
    for r in (
        db.query(Opportunity.buyer_requirement_id)
        .join(ProductionFormula, ProductionFormula.opportunity_id == Opportunity.id)
        .join(InputOrder, InputOrder.production_formula_id == ProductionFormula.id)
        .filter(InputOrder.vendor_id == vendor_id, Opportunity.buyer_requirement_id.isnot(None))
        .distinct().all()
    ):
        order_ids.add(r[0])

    rows: List[VendorPayoutRow] = []
    for order_id in order_ids:
        requirement = db.query(BuyerRequirement).filter(BuyerRequirement.id == order_id).first()
        if not requirement:
            continue

        mech_requests = (
            db.query(MechanisationRequest)
            .filter(
                MechanisationRequest.vendor_id == vendor_id,
                MechanisationRequest.buyer_requirement_id == order_id,
                MechanisationRequest.status == MechanisationRequestStatus.CONFIRMED,
            ).all()
        )
        mechanisation_amount = round(sum(r.area_acres * vendor_rate for r in mech_requests), 2)

        input_orders = (
            db.query(InputOrder)
            .join(ProductionFormula, InputOrder.production_formula_id == ProductionFormula.id)
            .join(Opportunity, ProductionFormula.opportunity_id == Opportunity.id)
            .filter(
                InputOrder.vendor_id == vendor_id,
                InputOrder.status == InputOrderStatus.CONFIRMED,
                Opportunity.buyer_requirement_id == order_id,
            ).all()
        )
        input_order_amount = round(sum(o.total_cost for o in input_orders), 2)

        recon = db.query(OrderReconciliation).filter(OrderReconciliation.buyer_requirement_id == order_id).first()
        buyer_name = requirement.buyer.organisation_name or requirement.buyer.full_name
        rows.append(VendorPayoutRow(
            buyer_requirement_id=order_id, buyer_name=buyer_name,
            mechanisation_amount=mechanisation_amount, input_order_amount=input_order_amount,
            total=round(mechanisation_amount + input_order_amount, 2),
            released=bool(recon and recon.vendor_payout_released),
            released_at=recon.vendor_payout_released_at if recon else None,
        ))
    return rows
