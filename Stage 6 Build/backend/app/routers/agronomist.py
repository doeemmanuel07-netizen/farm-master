"""
Matching Queue -- the real backend behind the Agronomist's "assign buyer
requirements to farmers" screen (IA Section 3.5, Fig. 6; Stage 3
internal_operations_wireframe.html, "Matching Queue (Manual)").

PRD Section 8 confirms Phase 1 matching is manual/agronomist-assisted --
there is no automated crop-history scoring engine, so "candidate farmers"
here is genuinely every active Farmer account, not a scored shortlist (the
wireframe's "6 matched by crop history" style copy is Phase 2 scope).
Assigning creates one real Opportunity per selected farmer, splitting the
requirement's tonnage evenly across them -- a documented placeholder for
real per-farm allocation logic, same PROVISIONAL treatment as the other
Stage 6 config values (PRD Section 10) -- and moves the requirement out of
the "needs review" state.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from datetime import datetime

from ..database import get_db
from ..models import (
    User, Role, UserStatus, BuyerRequirement, RequirementStatus,
    Opportunity, OpportunityStatus, RequirementFormulaPlan,
)
from ..auth import require_roles
from ..audit import log_audit
from ..formula import compute_formula_inputs
from ..schemas import (
    AgronomistRequirementResponse, FarmerCandidateResponse, AssignFarmersRequest,
    FormulaBuilderResponse, FormulaPlanUpdate,
)

router = APIRouter(prefix="/agronomist", tags=["agronomist"])

# Requirements visible in the queue once a buyer has paid the commitment fee
# (MATCHING) through however far downstream they've progressed -- the screen
# shows both "needs review" and already-"assigned" rows in one table (Stage 3
# wireframe), it doesn't drop a requirement once matched.
QUEUE_STATUSES = {
    RequirementStatus.MATCHING,
    RequirementStatus.PRODUCTION,
    RequirementStatus.AGGREGATION,
    RequirementStatus.SHIPMENT,
}


def _requirement_view(req: BuyerRequirement, db: Session) -> AgronomistRequirementResponse:
    assigned = db.query(Opportunity).filter(Opportunity.buyer_requirement_id == req.id).count()
    plan = db.query(RequirementFormulaPlan).filter(RequirementFormulaPlan.buyer_requirement_id == req.id).first()
    buyer_name = req.buyer.organisation_name or req.buyer.full_name
    return AgronomistRequirementResponse(
        id=req.id,
        buyer_name=buyer_name,
        grade=req.grade,
        quantity_tonnes=req.quantity_tonnes,
        price_per_tonne=req.price_per_tonne,
        delivery_location=req.delivery_location,
        delivery_timeline=req.delivery_timeline,
        status=req.status,
        assigned_farmer_count=assigned,
        formula_published=bool(plan and plan.published),
    )


def _get_requirement_or_404(requirement_id: str, db: Session) -> BuyerRequirement:
    req = db.query(BuyerRequirement).filter(BuyerRequirement.id == requirement_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found.")
    return req


def _get_or_default_plan(req: BuyerRequirement, db: Session) -> RequirementFormulaPlan:
    """
    Returns the saved plan, or an unsaved (not added to the session) default
    one so the builder screen always has calendar weeks to show -- a
    requirement with no plan yet is not an error, it just hasn't been built.
    """
    plan = db.query(RequirementFormulaPlan).filter(RequirementFormulaPlan.buyer_requirement_id == req.id).first()
    if plan:
        return plan
    # Column(default=...) only applies at INSERT time, not on plain
    # instantiation -- this object is never added/committed, so the
    # standard planting-calendar week defaults must be passed explicitly.
    return RequirementFormulaPlan(
        buyer_requirement_id=req.id,
        land_prep_week=1, planting_week=2, topdress_week=4, weeding_week=6, harvest_week=11,
        published=False, published_at=None,
    )


def _formula_builder_view(req: BuyerRequirement, db: Session) -> FormulaBuilderResponse:
    opportunities = db.query(Opportunity).filter(Opportunity.buyer_requirement_id == req.id).all()
    if not opportunities:
        raise HTTPException(status_code=409, detail="This requirement has no assigned farmers yet -- assign farmers via the Matching Queue first.")

    # Every opportunity from one requirement carries the same tonnage share
    # by construction (agronomist.py's assign_farmers splits evenly) -- read
    # that share rather than re-deriving it, so the Formula Builder can never
    # disagree with what the Matching Queue actually assigned.
    per_farmer_tonnes = opportunities[0].quantity_tonnes
    farmer_ids = [o.assigned_farmer_id for o in opportunities if o.assigned_farmer_id]
    farmers = db.query(User).filter(User.id.in_(farmer_ids)).all() if farmer_ids else []
    farmer_names = sorted(f.full_name for f in farmers) if farmers else [f"{len(opportunities)} farmer(s) assigned"]

    inputs = compute_formula_inputs(db, per_farmer_tonnes)
    buyer_name = req.buyer.organisation_name or req.buyer.full_name
    plan = _get_or_default_plan(req, db)

    return FormulaBuilderResponse(
        buyer_requirement_id=req.id,
        buyer_name=buyer_name,
        grade=req.grade,
        quantity_tonnes=req.quantity_tonnes,
        delivery_timeline=req.delivery_timeline,
        farmer_names=farmer_names,
        per_farmer_tonnes=per_farmer_tonnes,
        seed_kg_per_farmer=inputs.seed_kg,
        npk_bags_per_farmer=inputs.npk_bags,
        topdress_bags_per_farmer=inputs.topdress_bags,
        plan=plan,
    )


@router.get("/requirements", response_model=List[AgronomistRequirementResponse])
def list_requirements(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.AGRONOMIST)),
):
    reqs = (
        db.query(BuyerRequirement)
        .filter(BuyerRequirement.status.in_(QUEUE_STATUSES))
        .order_by(BuyerRequirement.created_at.desc())
        .all()
    )
    return [_requirement_view(r, db) for r in reqs]


@router.get("/farmers", response_model=List[FarmerCandidateResponse])
def list_candidate_farmers(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.AGRONOMIST)),
):
    return (
        db.query(User)
        .filter(User.role == Role.FARMER, User.status == UserStatus.ACTIVE)
        .order_by(User.full_name)
        .all()
    )


@router.post("/requirements/{requirement_id}/assign", response_model=AgronomistRequirementResponse)
def assign_farmers(
    requirement_id: str,
    payload: AssignFarmersRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.AGRONOMIST)),
):
    req = db.query(BuyerRequirement).filter(BuyerRequirement.id == requirement_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found.")
    if req.status != RequirementStatus.MATCHING:
        raise HTTPException(status_code=409, detail=f"Requirement is '{req.status.value}', not open for matching.")
    if not payload.farmer_ids:
        raise HTTPException(status_code=422, detail="Select at least one farmer.")

    unique_ids = set(payload.farmer_ids)
    farmers = (
        db.query(User)
        .filter(User.id.in_(unique_ids), User.role == Role.FARMER, User.status == UserStatus.ACTIVE)
        .all()
    )
    if len(farmers) != len(unique_ids):
        raise HTTPException(status_code=422, detail="One or more selected farmers are invalid or inactive.")

    buyer_name = req.buyer.organisation_name or req.buyer.full_name
    share = round(req.quantity_tonnes / len(farmers), 2)
    for farmer in farmers:
        db.add(Opportunity(
            buyer_requirement_id=req.id,
            buyer_name=buyer_name,
            tag="Buyer requirement match",
            grade=req.grade,
            quantity_tonnes=share,
            price_per_tonne=req.price_per_tonne,
            deadline=req.delivery_timeline,
            status=OpportunityStatus.OPEN,
            assigned_farmer_id=farmer.id,
        ))
    req.status = RequirementStatus.PRODUCTION
    db.commit()
    db.refresh(req)

    log_audit(
        db, user, "requirement_matched",
        f"Requirement {req.id} ({buyer_name}, {req.quantity_tonnes}t {req.grade}): assigned to "
        f"{len(farmers)} farmer(s) ({', '.join(sorted(f.full_name for f in farmers))}), {share}t each.",
    )
    return _requirement_view(req, db)


@router.get("/requirements/{requirement_id}/formula", response_model=FormulaBuilderResponse)
def get_formula_builder(
    requirement_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.AGRONOMIST)),
):
    req = _get_requirement_or_404(requirement_id, db)
    return _formula_builder_view(req, db)


@router.put("/requirements/{requirement_id}/formula", response_model=FormulaBuilderResponse)
def save_formula_plan(
    requirement_id: str,
    payload: FormulaPlanUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.AGRONOMIST)),
):
    req = _get_requirement_or_404(requirement_id, db)
    plan = db.query(RequirementFormulaPlan).filter(RequirementFormulaPlan.buyer_requirement_id == req.id).first()
    if plan and plan.published:
        raise HTTPException(status_code=409, detail="This formula has already been published and can no longer be edited.")

    if not plan:
        plan = RequirementFormulaPlan(buyer_requirement_id=req.id)
        db.add(plan)
    plan.land_prep_week = payload.land_prep_week
    plan.planting_week = payload.planting_week
    plan.topdress_week = payload.topdress_week
    plan.weeding_week = payload.weeding_week
    plan.harvest_week = payload.harvest_week
    db.commit()
    return _formula_builder_view(req, db)


@router.post("/requirements/{requirement_id}/formula/publish", response_model=FormulaBuilderResponse)
def publish_formula_plan(
    requirement_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.AGRONOMIST)),
):
    req = _get_requirement_or_404(requirement_id, db)
    plan = db.query(RequirementFormulaPlan).filter(RequirementFormulaPlan.buyer_requirement_id == req.id).first()
    if not plan:
        raise HTTPException(status_code=409, detail="Save a planting calendar before publishing.")
    if plan.published:
        raise HTTPException(status_code=409, detail="This formula has already been published.")

    plan.published = True
    plan.published_at = datetime.utcnow()
    plan.published_by = user.id
    db.commit()

    view = _formula_builder_view(req, db)
    log_audit(
        db, user, "formula_published",
        f"Requirement {req.id} ({view.buyer_name}, {req.quantity_tonnes}t {req.grade}): production formula "
        f"published to {', '.join(view.farmer_names)} -- {view.seed_kg_per_farmer}kg seed, "
        f"{view.npk_bags_per_farmer} NPK bag(s) (wk {plan.planting_week}), "
        f"{view.topdress_bags_per_farmer} top-dress bag(s) (wk {plan.topdress_week}) per farmer.",
    )
    # Deliberately does not advance req.status: PRODUCTION already covers the
    # whole growing season from assignment through harvest (PRD Section 8/10)
    # -- AGGREGATION is the fulfilment-centre-intake transition, a later and
    # separate event not yet built (see README "Not yet built"), so a
    # published formula is a real milestone within PRODUCTION, not a status
    # change of its own.
    return view
