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

The three Matching Queue endpoints (list_requirements, list_candidate_
farmers, assign_farmers) are also open to Role.OPERATIONS_COORDINATOR as
of 9 Sep 2026 -- the new Pilot Operations Coordinator / Field-Farmer
Liaison role's real job is exactly this matching duty. Formula Builder,
Field Visit Logs, and Messaging below stay Agronomist-only: those are
crop-science duties the Coordinator role was never asked to cover, not an
oversight.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from datetime import datetime

from ..database import get_db
from ..models import (
    User, Role, UserStatus, BuyerRequirement, RequirementStatus,
    Opportunity, OpportunityStatus, RequirementFormulaPlan,
    FieldVisitLog, FieldVisitStatus, AgronomistMessage,
)
from ..auth import require_roles
from ..audit import log_audit
from ..formula import compute_formula_inputs
from ..schemas import (
    AgronomistRequirementResponse, FarmerCandidateResponse, AssignFarmersRequest,
    FormulaBuilderResponse, FormulaPlanUpdate,
    FieldVisitLogCreate, FieldVisitLogCompleteRequest, FieldVisitLogResponse,
    AgronomistMessageCreate, AgronomistMessageResponse,
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
    user: User = Depends(require_roles(Role.AGRONOMIST, Role.OPERATIONS_COORDINATOR)),
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
    user: User = Depends(require_roles(Role.AGRONOMIST, Role.OPERATIONS_COORDINATOR)),
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
    user: User = Depends(require_roles(Role.AGRONOMIST, Role.OPERATIONS_COORDINATOR)),
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


# ---------------------------------------------------------------------------
# Field Visit Logs -- Stage 3 wireframe "Field Visit Logs", the agronomist's
# own counterpart to the Farmer Portal's Milestone Log. Added 8 Sep 2026,
# closing a gap this session's own completeness audit surfaced: in the
# confirmed IA/wireframe/visual scope from day one, never previously built.
# Offline-tolerant capture is explicitly out of scope for the pilot build
# (see models.FieldVisitLog).
# ---------------------------------------------------------------------------


def _visit_view(v: FieldVisitLog, db: Session) -> FieldVisitLogResponse:
    farmer = db.query(User).filter(User.id == v.farmer_id).first()
    return FieldVisitLogResponse(
        id=v.id, farmer_name=farmer.full_name if farmer else "Unknown",
        checkpoint_label=v.checkpoint_label, scheduled_date=v.scheduled_date,
        status=v.status, notes=v.notes, logged_at=v.logged_at, created_at=v.created_at,
    )


@router.get("/visit-logs", response_model=List[FieldVisitLogResponse])
def list_visit_logs(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.AGRONOMIST)),
):
    logs = (
        db.query(FieldVisitLog)
        .filter(FieldVisitLog.agronomist_id == user.id)
        .order_by(FieldVisitLog.scheduled_date.asc())
        .all()
    )
    return [_visit_view(v, db) for v in logs]


@router.post("/visit-logs", response_model=FieldVisitLogResponse)
def schedule_visit_log(
    payload: FieldVisitLogCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.AGRONOMIST)),
):
    farmer = db.query(User).filter(User.id == payload.farmer_id, User.role == Role.FARMER).first()
    if not farmer:
        raise HTTPException(status_code=422, detail="farmer_id must be a real Farmer account.")
    visit = FieldVisitLog(
        agronomist_id=user.id, farmer_id=payload.farmer_id, opportunity_id=payload.opportunity_id,
        checkpoint_label=payload.checkpoint_label, scheduled_date=payload.scheduled_date,
        notes=payload.notes,
    )
    db.add(visit)
    db.commit()
    db.refresh(visit)
    return _visit_view(visit, db)


@router.post("/visit-logs/{visit_id}/complete", response_model=FieldVisitLogResponse)
def complete_visit_log(
    visit_id: str,
    payload: FieldVisitLogCompleteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.AGRONOMIST)),
):
    visit = db.query(FieldVisitLog).filter(FieldVisitLog.id == visit_id, FieldVisitLog.agronomist_id == user.id).first()
    if not visit:
        raise HTTPException(status_code=404, detail="Visit log not found.")
    if visit.status == FieldVisitStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="This visit is already logged as completed.")
    visit.status = FieldVisitStatus.COMPLETED
    visit.logged_at = datetime.utcnow()
    if payload.notes:
        visit.notes = payload.notes
    db.commit()
    db.refresh(visit)
    return _visit_view(visit, db)


# ---------------------------------------------------------------------------
# Agronomist Messaging -- Stage 3 wireframe, "confirmed in Phase 1 pilot
# scope" per its own caption. Added 8 Sep 2026, same audit as above. Single
# shared Agronomy inbox -- see models.AgronomistMessage for why.
# ---------------------------------------------------------------------------


def _message_view(m: AgronomistMessage, db: Session) -> AgronomistMessageResponse:
    sender = db.query(User).filter(User.id == m.sender_id).first()
    return AgronomistMessageResponse(
        id=m.id, sender_name=sender.full_name if sender else "Unknown",
        sender_role=sender.role if sender else Role.AGRONOMIST, body=m.body, created_at=m.created_at,
    )


@router.get("/messages", response_model=List[AgronomistMessageResponse])
def list_all_messages(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.AGRONOMIST)),
):
    msgs = db.query(AgronomistMessage).order_by(AgronomistMessage.created_at.asc()).all()
    return [_message_view(m, db) for m in msgs]


@router.post("/messages/{farmer_id}/reply", response_model=AgronomistMessageResponse)
def reply_to_farmer(
    farmer_id: str,
    payload: AgronomistMessageCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.AGRONOMIST)),
):
    farmer = db.query(User).filter(User.id == farmer_id, User.role == Role.FARMER).first()
    if not farmer:
        raise HTTPException(status_code=404, detail="Farmer not found.")
    if not payload.body.strip():
        raise HTTPException(status_code=422, detail="Message body cannot be empty.")
    msg = AgronomistMessage(farmer_id=farmer_id, agronomist_id=user.id, sender_id=user.id, body=payload.body)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return _message_view(msg, db)
