"""
Shared Farmer Wallet & Settlement computation -- Stage 3 wireframe "Wallet &
Settlement Statement" (Farmer Portal). Added 8 Sep 2026, closing a gap this
session's own completeness audit surfaced. Same "integrate, don't duplicate"
pattern as reconciliation.py/formula.py/dispatch.py -- reuses the exact same
real, linked data reconciliation.py already computes at the order level,
just re-scoped to one farmer's own share of each order rather than Finance's
whole-order view.

Unlike reconciliation.py (which computes one order's total settlement across
every farmer assigned to it), a farmer's own delivered tonnage is already
directly attributable: HarvestPickupRequest.farmer_id scopes each pickup to
exactly one farmer, so "this farmer's own graded, non-REJECT tonnage against
this order" needs no proportional splitting -- it's a real, direct sum.
"""

from dataclasses import dataclass
from typing import List

from sqlalchemy.orm import Session

from .models import (
    BuyerRequirement, HarvestPickupRequest, FulfilmentIntake, GradeResult,
    RateConfig, InputOrder, InputOrderStatus, ProductionFormula, Opportunity,
)


def _get_rate(db: Session, key: str) -> float:
    row = db.query(RateConfig).filter(RateConfig.key == key).first()
    if row is None:
        raise RuntimeError(f"Rate config '{key}' is not seeded.")
    return row.value


@dataclass
class FarmerWalletRow:
    buyer_requirement_id: str
    buyer_name: str
    own_delivered_tonnes: float
    own_settlement_due: float
    input_order_costs: float


def compute_farmer_wallet(db: Session, farmer_id: str) -> List[FarmerWalletRow]:
    margin_pct = _get_rate(db, "trading_margin_pct")

    order_ids = [
        r.buyer_requirement_id for r in
        db.query(HarvestPickupRequest.buyer_requirement_id)
        .filter(HarvestPickupRequest.farmer_id == farmer_id, HarvestPickupRequest.buyer_requirement_id.isnot(None))
        .distinct()
        .all()
    ]

    rows: List[FarmerWalletRow] = []
    for order_id in order_ids:
        requirement = db.query(BuyerRequirement).filter(BuyerRequirement.id == order_id).first()
        if not requirement:
            continue

        graded = (
            db.query(FulfilmentIntake)
            .join(HarvestPickupRequest, FulfilmentIntake.harvest_pickup_request_id == HarvestPickupRequest.id)
            .filter(
                HarvestPickupRequest.farmer_id == farmer_id,
                HarvestPickupRequest.buyer_requirement_id == order_id,
                FulfilmentIntake.grade != GradeResult.REJECT,
            )
            .all()
        )
        own_delivered_tonnes = sum(i.weigh_in_kg for i in graded) / 1000.0
        own_invoice_value = own_delivered_tonnes * requirement.price_per_tonne
        own_settlement_due = round(own_invoice_value * (1 - margin_pct), 2)

        input_order_costs = sum(
            o.total_cost for o in
            db.query(InputOrder)
            .join(ProductionFormula, InputOrder.production_formula_id == ProductionFormula.id)
            .join(Opportunity, ProductionFormula.opportunity_id == Opportunity.id)
            .filter(
                InputOrder.farmer_id == farmer_id,
                InputOrder.status == InputOrderStatus.CONFIRMED,
                Opportunity.buyer_requirement_id == order_id,
            )
            .all()
        )

        buyer_name = requirement.buyer.organisation_name or requirement.buyer.full_name
        rows.append(FarmerWalletRow(
            buyer_requirement_id=order_id, buyer_name=buyer_name,
            own_delivered_tonnes=round(own_delivered_tonnes, 3),
            own_settlement_due=own_settlement_due,
            input_order_costs=round(input_order_costs, 2),
        ))
    return rows
