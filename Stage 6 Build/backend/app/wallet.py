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

from dataclasses import dataclass, field
from typing import List

from sqlalchemy.orm import Session

from .models import (
    BuyerRequirement, HarvestPickupRequest, FulfilmentIntake, GradeResult,
    RateConfig, InputOrder, InputOrderStatus, ProductionFormula, Opportunity,
    WalletLedgerEntry, WalletEntryType, WalletSource, OpportunityStatus, DispatchJob, DispatchJobStatus,
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


# ---------------------------------------------------------------------------
# Wallet ledger (CEO demo brief §4.3, decision D4, 11 Oct 2026)
#
# sync_farmer_ledger() posts any movement the farmer's real records imply
# but the ledger doesn't hold yet. It's idempotent ((farmer, source,
# reference) is unique) and never edits or deletes an entry -- a declined
# input order gets a reversal credit, not a removed debit -- so the
# statement is an auditable history, not a recomputed number.
# ---------------------------------------------------------------------------


def _post(db: Session, existing: set, farmer_id: str, entry_type, source, reference: str, amount: float,
          description: str, is_estimate: bool = False) -> bool:
    if (source, reference) in existing or amount <= 0:
        return False
    db.add(WalletLedgerEntry(
        farmer_id=farmer_id, entry_type=entry_type, source=source, reference=reference,
        amount=round(amount, 2), description=description, is_estimate=is_estimate,
    ))
    existing.add((source, reference))
    return True


def sync_farmer_ledger(db: Session, farmer_id: str) -> None:
    existing = {
        (e.source, e.reference)
        for e in db.query(WalletLedgerEntry).filter(WalletLedgerEntry.farmer_id == farmer_id).all()
    }
    margin = _get_rate(db, "trading_margin_pct")
    fee_row = db.query(RateConfig).filter(RateConfig.key == "logistics_fee_per_delivery").first()
    logistics_fee = fee_row.value if fee_row else 0.0
    posted = False

    for opp in db.query(Opportunity).filter(Opportunity.accepted_by == farmer_id, Opportunity.status == OpportunityStatus.ACCEPTED).all():
        gross = opp.quantity_tonnes * opp.price_per_tonne
        posted |= _post(db, existing, farmer_id, WalletEntryType.CREDIT, WalletSource.ESTIMATED_SETTLEMENT, opp.id,
                        gross * (1 - margin),
                        f"Estimated settlement: {opp.quantity_tonnes:g} t for {opp.buyer_name} at GHS {opp.price_per_tonne:,.0f}/t, "
                        f"less {margin * 100:g}% trading margin", is_estimate=True)

    for order in db.query(InputOrder).filter(InputOrder.farmer_id == farmer_id).all():
        posted |= _post(db, existing, farmer_id, WalletEntryType.DEBIT, WalletSource.INPUT_ORDER, order.id,
                        order.total_cost, f"Input order {order.id[:8]}")
        if order.status == InputOrderStatus.DECLINED:
            posted |= _post(db, existing, farmer_id, WalletEntryType.CREDIT, WalletSource.INPUT_ORDER_REVERSAL, order.id,
                            order.total_cost, f"Input order {order.id[:8]} declined by vendor -- refunded")

    delivered_jobs = (
        db.query(DispatchJob)
        .outerjoin(InputOrder, DispatchJob.input_order_id == InputOrder.id)
        .outerjoin(HarvestPickupRequest, DispatchJob.harvest_pickup_request_id == HarvestPickupRequest.id)
        .filter(DispatchJob.status == DispatchJobStatus.DELIVERED)
        .filter((InputOrder.farmer_id == farmer_id) | (HarvestPickupRequest.farmer_id == farmer_id))
        .all()
    )
    for job in delivered_jobs:
        kind = "harvest pickup" if job.harvest_pickup_request_id else "input delivery"
        posted |= _post(db, existing, farmer_id, WalletEntryType.DEBIT, WalletSource.LOGISTICS_FEE, job.id,
                        logistics_fee, f"Logistics fee: {kind}")
    if posted:
        db.commit()


@dataclass
class WalletSummary:
    input_costs: float
    logistics_fees: float
    estimated_settlement: float
    estimated_payout: float
    entries: List[WalletLedgerEntry] = field(default_factory=list)


def wallet_summary(db: Session, farmer_id: str) -> WalletSummary:
    sync_farmer_ledger(db, farmer_id)
    entries = (
        db.query(WalletLedgerEntry).filter(WalletLedgerEntry.farmer_id == farmer_id)
        .order_by(WalletLedgerEntry.created_at.desc()).all()
    )

    def total(*sources):
        return sum(e.amount * (1 if e.entry_type == WalletEntryType.CREDIT else -1)
                   for e in entries if e.source in sources)

    inputs = -total(WalletSource.INPUT_ORDER, WalletSource.INPUT_ORDER_REVERSAL)
    logistics = -total(WalletSource.LOGISTICS_FEE)
    settlement = total(WalletSource.ESTIMATED_SETTLEMENT)
    return WalletSummary(
        input_costs=round(inputs, 2), logistics_fees=round(logistics, 2),
        estimated_settlement=round(settlement, 2),
        estimated_payout=round(settlement - inputs - logistics, 2), entries=entries,
    )
