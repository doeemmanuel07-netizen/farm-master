"""
Farmer-facing opportunity matching, production-formula steps and the
acceptance side effects (CEO demo brief §4.1, §4.2).

Phase 1 match rule: a farmer sees an opportunity if it was assigned to
them, or if it is unassigned and its region and crop (when set) are the
farmer's own region and a crop they're registered to grow. Opportunities
assigned to another farmer are never shown.
"""

from datetime import date, datetime, timedelta
from typing import List, Optional

from sqlalchemy import or_, and_, false
from sqlalchemy.orm import Session

from .models import (
    Opportunity, OpportunityStatus, BuyerRequirement, RequirementStatus, RequirementFormulaPlan, FormulaStep,
    CropVariety, Crop, Region, User, HarvestPickupRequest, AgronomistTask, AgronomistTaskKind, Notification,
    NotificationType, UssdSmsLog, RateConfig, ProductionFormula,
)
from .reference import farmer_crop_ids

OPPORTUNITY_STEPS = ["Matched", "Accepted", "In production", "Harvest & delivery"]


def visible_opportunities_query(db: Session, farmer: User):
    crops = farmer_crop_ids(db, farmer)
    unassigned_match = and_(
        Opportunity.assigned_farmer_id.is_(None),
        or_(Opportunity.region_id.is_(None), Opportunity.region_id == farmer.region_id),
        or_(Opportunity.crop_id.is_(None), Opportunity.crop_id.in_(crops) if crops else false()),
    )
    return db.query(Opportunity).filter(or_(Opportunity.assigned_farmer_id == farmer.id, unassigned_match))


def matched_opportunities(db: Session, farmer: User) -> List[Opportunity]:
    """Open matches plus this farmer's own accepted ones, newest first."""
    rows = (
        visible_opportunities_query(db, farmer)
        .filter(or_(Opportunity.status == OpportunityStatus.OPEN, Opportunity.accepted_by == farmer.id))
        .order_by(Opportunity.created_at.desc())
        .all()
    )
    return rows


def _plan_weeks(db: Session, req: Optional[BuyerRequirement]) -> dict:
    plan = (
        db.query(RequirementFormulaPlan).filter(RequirementFormulaPlan.buyer_requirement_id == req.id).first()
        if req else None
    )
    return {
        "planting_week": plan.planting_week if plan else 2,
        "topdress_week": plan.topdress_week if plan else 4,
        "harvest_week": plan.harvest_week if plan else 11,
    }


def formula_steps(db: Session, req: Optional[BuyerRequirement]) -> List[str]:
    """Agronomist-saved steps if any, else a draft from the variety template + the buyer's spec notes."""
    if req is not None:
        saved = (
            db.query(FormulaStep).filter(FormulaStep.buyer_requirement_id == req.id)
            .order_by(FormulaStep.position).all()
        )
        if saved:
            return [s.text for s in saved]
    variety = (
        db.query(CropVariety).filter(CropVariety.id == req.crop_variety_id).first()
        if req is not None and req.crop_variety_id else None
    )
    weeks = _plan_weeks(db, req)
    steps = []
    if variety and variety.default_formula_steps:
        for line in variety.default_formula_steps.splitlines():
            try:
                steps.append(line.format(**weeks))
            except (KeyError, IndexError, ValueError):
                steps.append(line)
    if req is not None and req.spec_notes:
        steps.append(f"Buyer specification: {req.spec_notes}")
    return steps


def opportunity_stage(db: Session, opp: Opportunity) -> int:
    if opp.status == OpportunityStatus.OPEN:
        return 0
    req = db.query(BuyerRequirement).filter(BuyerRequirement.id == opp.buyer_requirement_id).first() if opp.buyer_requirement_id else None
    harvesting = bool(
        db.query(HarvestPickupRequest)
        .filter(HarvestPickupRequest.farmer_id == opp.accepted_by,
                HarvestPickupRequest.buyer_requirement_id == opp.buyer_requirement_id)
        .first()
    ) if opp.buyer_requirement_id else False
    if harvesting or (req and req.status in (RequirementStatus.AGGREGATION, RequirementStatus.SHIPMENT, RequirementStatus.DELIVERED)):
        return 3
    return 2


def weeks_until(d: Optional[date], today: Optional[date] = None) -> Optional[int]:
    if d is None:
        return None
    return max(0, round(((d - (today or date.today())).days) / 7))


def opportunity_view(db: Session, opp: Opportunity):
    from .schemas import MatchedOpportunityResponse

    req = db.query(BuyerRequirement).filter(BuyerRequirement.id == opp.buyer_requirement_id).first() if opp.buyer_requirement_id else None
    crop = db.query(Crop).filter(Crop.id == opp.crop_id).first() if opp.crop_id else None
    if crop is None and req is not None:
        crop = db.query(Crop).filter(Crop.name == req.crop).first()
    region = db.query(Region).filter(Region.id == opp.region_id).first() if opp.region_id else None
    delivery_by = opp.delivery_by or (req.delivery_by if req else None)
    formula = db.query(ProductionFormula).filter(ProductionFormula.opportunity_id == opp.id).first()
    steps = formula_steps(db, req)
    if formula:
        steps = steps + [f"Inputs for your {opp.quantity_tonnes:g} t: {formula.seed_kg:g} kg seed, "
                         f"{formula.npk_bags} NPK bag(s), {formula.topdress_bags} top-dress bag(s)"]
    return MatchedOpportunityResponse(
        id=opp.id, buyer_name=opp.buyer_name, tag=opp.tag, grade=opp.grade,
        quantity_tonnes=opp.quantity_tonnes, price_per_tonne=opp.price_per_tonne, deadline=opp.deadline,
        status=opp.status, crop=crop.name if crop else "Maize", crop_icon=crop.icon if crop else "maize",
        variety=(db.query(CropVariety).filter(CropVariety.id == req.crop_variety_id).first().name
                 if req is not None and req.crop_variety_id else None),
        region=region.name if region else None, delivery_by=delivery_by,
        delivery_in_weeks=weeks_until(delivery_by), stage_index=opportunity_stage(db, opp),
        steps=OPPORTUNITY_STEPS, formula_steps=steps, buyer_requirement_id=opp.buyer_requirement_id,
    )


def _rate(db: Session, key: str, default: float) -> float:
    row = db.query(RateConfig).filter(RateConfig.key == key).first()
    return row.value if row else default


def on_opportunity_accepted(db: Session, opp: Opportunity, farmer: User, crop_name: str) -> AgronomistTask:
    """Brief §4.2: a 48-hour agronomist follow-up task plus an in-app and SMS notification."""
    sla_hours = _rate(db, "agronomist_task_sla_hours", 48)
    task = AgronomistTask(
        kind=AgronomistTaskKind.ACCEPTANCE_FOLLOW_UP, farmer_id=farmer.id, opportunity_id=opp.id,
        summary=f"Follow up with {farmer.full_name}: accepted {opp.quantity_tonnes:g} t {crop_name} for {opp.buyer_name}",
        due_at=datetime.utcnow() + timedelta(hours=sla_hours),
    )
    db.add(task)
    message = (f"{crop_name} opportunity accepted ({opp.quantity_tonnes:g} t for {opp.buyer_name}). "
               f"A Farm Master agronomist will contact you within {sla_hours:g} hours.")
    db.add(Notification(user_id=farmer.id, type=NotificationType.OPPORTUNITY_ACCEPTED, message=message))
    # SMS delivery is simulated, same as every other SMS in the pilot (UssdSmsLog).
    db.add(UssdSmsLog(farmer_id=farmer.id, channel="sms", purpose="opportunity_accepted", body=message))
    db.commit()
    return task


def backfill_opportunities(db: Session) -> None:
    """
    Opportunities created before crop/region existed were all pilot rows:
    maize in Greater Accra. Stamp them so the match filter and the portal
    show real values (idempotent; only touches NULLs).
    """
    maize = db.query(Crop).filter(Crop.name == "Maize").first()
    region = db.query(Region).filter(Region.name == "Greater Accra").first()
    rows = db.query(Opportunity).filter(Opportunity.crop_id.is_(None)).all()
    for o in rows:
        o.crop_id = maize.id if maize else None
        if o.region_id is None:
            o.region_id = region.id if region else None
        if o.delivery_by is None and o.buyer_requirement_id:
            req = db.query(BuyerRequirement).filter(BuyerRequirement.id == o.buyer_requirement_id).first()
            o.delivery_by = req.delivery_by if req else None
    if rows:
        db.commit()
        print(f"Backfilled crop/region on {len(rows)} pre-existing opportunit{'y' if len(rows) == 1 else 'ies'}.")
