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

from ..database import get_db
from ..models import (
    User, Role, UserStatus, BuyerRequirement, RequirementStatus,
    Opportunity, OpportunityStatus,
)
from ..auth import require_roles
from ..audit import log_audit
from ..schemas import AgronomistRequirementResponse, FarmerCandidateResponse, AssignFarmersRequest

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
