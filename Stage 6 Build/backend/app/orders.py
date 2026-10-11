"""
Buyer order presentation (CEO demo brief §5): FM-#### references and the
status → stepper / badge / progress mapping, derived from the order's real
RequirementStatus rather than stored as free text. Also the requirement →
response builder shared by the buyer and ops routers.
"""

from datetime import date, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    BuyerRequirement, RequirementStatus, REQUIREMENT_REF_SEQ, CropVariety, Crop, CommitmentFeePayment,
    PaymentStatus, RateConfig,
)

ORDER_STEPS = ["Order placed", "Farmer matched", "In production", "Aggregating", "Delivered"]

# status -> (index of the *current* step, buyer-facing label, progress %, badge class)
# An index of len(ORDER_STEPS) means every step is done.
_STAGE = {
    RequirementStatus.DRAFT: (0, "Draft", 0, "waiting"),
    RequirementStatus.PENDING_PAYMENT: (0, "Awaiting payment", 5, "open"),
    RequirementStatus.MATCHING: (1, "Matching farmers", 20, "progress"),
    RequirementStatus.PRODUCTION: (2, "In production", 45, "progress"),
    RequirementStatus.AGGREGATION: (3, "Aggregating", 70, "progress"),
    RequirementStatus.SHIPMENT: (4, "In transit", 90, "progress"),
    RequirementStatus.DELIVERED: (5, "Delivered", 100, "delivered"),
}


def order_stage(status: RequirementStatus):
    return _STAGE[status]


def next_reference(db: Session) -> str:
    return f"FM-{db.execute(select(REQUIREMENT_REF_SEQ.next_value())).scalar_one()}"


def rate_value(db: Session, key: str, default: float) -> float:
    row = db.query(RateConfig).filter(RateConfig.key == key).first()
    return row.value if row else default


def earliest_delivery_date(db: Session, today: Optional[date] = None) -> date:
    days = int(rate_value(db, "buyer_min_lead_time_days", 28))
    return (today or date.today()) + timedelta(days=days)


def requirement_view(db: Session, req: BuyerRequirement):
    from .schemas import RequirementResponse

    idx, label, pct, badge = order_stage(req.status)
    variety = db.query(CropVariety).filter(CropVariety.id == req.crop_variety_id).first() if req.crop_variety_id else None
    crop = db.query(Crop).filter(Crop.id == variety.crop_id).first() if variety else None
    latest = (
        db.query(CommitmentFeePayment).filter(CommitmentFeePayment.requirement_id == req.id)
        .order_by(CommitmentFeePayment.created_at.desc()).first()
    )
    return RequirementResponse(
        id=req.id, reference=req.reference, crop=req.crop, crop_icon=crop.icon if crop else "maize",
        crop_variety_id=req.crop_variety_id, variety=variety.name if variety else None,
        grade=req.grade, quantity_tonnes=req.quantity_tonnes, price_per_tonne=req.price_per_tonne,
        delivery_location=req.delivery_location, delivery_timeline=req.delivery_timeline,
        delivery_by=req.delivery_by, spec_notes=req.spec_notes,
        commitment_fee_amount=req.commitment_fee_amount, status=req.status, created_at=req.created_at,
        status_label=label, stage_index=idx, progress_pct=pct, badge=badge, steps=ORDER_STEPS,
        latest_payment_status=latest.status if latest else None,
        latest_payment_id=latest.id if latest else None,
        paid=bool(latest and latest.status == PaymentStatus.SUCCESS),
    )


def maize_variety_id(db: Session) -> Optional[str]:
    """The pilot crop's first variety -- what every pre-11-Oct-2026 requirement was implicitly ordering."""
    v = (
        db.query(CropVariety).join(Crop, CropVariety.crop_id == Crop.id)
        .filter(Crop.name == "Maize").order_by(CropVariety.created_at).first()
    )
    return v.id if v else None


def backfill_requirements(db: Session) -> None:
    """
    One-time, idempotent: gives requirements created before references and
    varieties existed an FM-#### reference (in creation order) and the maize
    variety. Also marks the old per-tonne fee rate row as superseded.
    """
    missing = db.query(BuyerRequirement).filter(BuyerRequirement.reference.is_(None)).order_by(BuyerRequirement.created_at).all()
    maize = maize_variety_id(db)
    for req in missing:
        req.reference = next_reference(db)
        if req.crop_variety_id is None and req.crop == "Maize":
            req.crop_variety_id = maize
    old_rate = db.query(RateConfig).filter(RateConfig.key == "buyer_commitment_fee_per_tonne").first()
    if old_rate and old_rate.status != "SUPERSEDED":
        old_rate.status = "SUPERSEDED"
        old_rate.note = ("Superseded 11 Oct 2026 by the commitment_fee_rules table (decision D3). "
                         "Kept for history; no calculation reads it.")
    if missing or old_rate:
        db.commit()
    if missing:
        print(f"Backfilled FM-#### references on {len(missing)} existing buyer requirement(s).")
