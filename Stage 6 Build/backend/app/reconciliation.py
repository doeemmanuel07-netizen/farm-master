"""
Shared Order Reconciliation computation -- PRD Section 6 Must-Have #5.
Single call site for both the list and detail endpoints in
routers/reconciliation.py, same "integrate, don't duplicate" pattern as
formula.py and dispatch.py.

The GHS figures are computed on read from real linked data, not stored:

- Commitment fee received: sum of SUCCESS CommitmentFeePayment rows for the
  requirement (real, already captured by buyer.py).
- Accepted delivered tonnes: sum of weigh_in_kg (converted to tonnes) across
  every graded, non-REJECT FulfilmentIntake reached via a
  HarvestPickupRequest whose buyer_requirement_id matches this order --
  i.e. what was actually delivered and graded for THIS order, not the
  order's originally committed quantity_tonnes.
- Vendor payout due: sum of (area_acres x vendor_service_fee_per_tonne) over
  every CONFIRMED MechanisationRequest whose buyer_requirement_id matches
  this order -- the same per-acre placeholder formula vendor.py already
  uses for its own suggested_quote (PRD Section 10 flags this as a known
  data-model mismatch, not reintroduced here).
- Trading margin: buyer invoice value (accepted delivered tonnes x
  price_per_tonne) x trading_margin_pct (RateConfig, BUSINESS-UNCONFIRMED --
  see seed.py). Farmer settlement due is the remainder.

trading_margin_pct is read fresh every call, so a rate change via
PUT /admin/rates/{key} is reflected immediately, matching
RequirementFormulaPlan's existing precedent for this codebase.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from .models import (
    BuyerRequirement, CommitmentFeePayment, PaymentStatus, RateConfig,
    HarvestPickupRequest, FulfilmentIntake, GradeResult,
    MechanisationRequest, MechanisationRequestStatus,
)


def _get_rate(db: Session, key: str) -> float:
    row = db.query(RateConfig).filter(RateConfig.key == key).first()
    if row is None:
        raise RuntimeError(f"Rate config '{key}' is not seeded.")
    return row.value


@dataclass
class ReconciliationFigures:
    commitment_fee_received: float
    accepted_delivered_tonnes: float
    buyer_invoice_value: float
    trading_margin_pct: float
    trading_margin_amount: float
    farmer_settlement_due: float
    vendor_payout_due: float


def compute_figures(db: Session, requirement: BuyerRequirement) -> ReconciliationFigures:
    commitment_fee_received = sum(
        p.amount for p in db.query(CommitmentFeePayment)
        .filter(CommitmentFeePayment.requirement_id == requirement.id, CommitmentFeePayment.status == PaymentStatus.SUCCESS)
        .all()
    )

    graded_intakes = (
        db.query(FulfilmentIntake)
        .join(HarvestPickupRequest, FulfilmentIntake.harvest_pickup_request_id == HarvestPickupRequest.id)
        .filter(HarvestPickupRequest.buyer_requirement_id == requirement.id, FulfilmentIntake.grade != GradeResult.REJECT)
        .all()
    )
    accepted_delivered_tonnes = sum(i.weigh_in_kg for i in graded_intakes) / 1000.0

    buyer_invoice_value = round(accepted_delivered_tonnes * requirement.price_per_tonne, 2)
    margin_pct = _get_rate(db, "trading_margin_pct")
    trading_margin_amount = round(buyer_invoice_value * margin_pct, 2)
    farmer_settlement_due = round(buyer_invoice_value - trading_margin_amount, 2)

    vendor_rate = _get_rate(db, "vendor_service_fee_per_tonne")
    confirmed_vendor_requests = (
        db.query(MechanisationRequest)
        .filter(MechanisationRequest.buyer_requirement_id == requirement.id, MechanisationRequest.status == MechanisationRequestStatus.CONFIRMED)
        .all()
    )
    vendor_payout_due = round(sum(r.area_acres * vendor_rate for r in confirmed_vendor_requests), 2)

    return ReconciliationFigures(
        commitment_fee_received=round(commitment_fee_received, 2),
        accepted_delivered_tonnes=round(accepted_delivered_tonnes, 3),
        buyer_invoice_value=buyer_invoice_value,
        trading_margin_pct=margin_pct,
        trading_margin_amount=trading_margin_amount,
        farmer_settlement_due=farmer_settlement_due,
        vendor_payout_due=vendor_payout_due,
    )
