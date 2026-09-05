"""
Fulfilment Centre Intake & Grading -- the back half of PRD Section 6
Must-Have #4, the real backend behind fulfilment_intake_flow_live.html.
The Stage 3 wireframe assigns this screen to "Finance (fulfilment centre
staff)", not Logistics, so every route here is Role.FINANCE-gated, matching
that already-confirmed design.

Intake is gated on the corresponding DispatchJob being DELIVERED --
grading produce that hasn't physically arrived yet would be fiction, not
just an ordering nicety.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Role, DispatchJob, DispatchJobStatus, DispatchDirection, HarvestPickupRequest, FulfilmentIntake
from ..auth import require_roles
from ..audit import log_audit
from ..schemas import FulfilmentQueueEntry, FulfilmentIntakeCreate, FulfilmentIntakeResponse

router = APIRouter(prefix="/fulfilment", tags=["fulfilment"])


@router.get("/intake-queue", response_model=List[FulfilmentQueueEntry])
def list_intake_queue(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FINANCE)),
):
    jobs = (
        db.query(DispatchJob)
        .filter(DispatchJob.direction == DispatchDirection.INBOUND, DispatchJob.status == DispatchJobStatus.DELIVERED)
        .all()
    )
    entries = []
    for job in jobs:
        already_graded = db.query(FulfilmentIntake).filter(FulfilmentIntake.harvest_pickup_request_id == job.harvest_pickup_request_id).first()
        if already_graded:
            continue
        req = db.query(HarvestPickupRequest).filter(HarvestPickupRequest.id == job.harvest_pickup_request_id).first()
        farmer = db.query(User).filter(User.id == req.farmer_id).first()
        entries.append(FulfilmentQueueEntry(
            harvest_pickup_request_id=req.id,
            farmer_name=farmer.full_name,
            quantity_ready_tonnes=req.quantity_ready_tonnes,
            delivered_at=job.delivered_at,
        ))
    return entries


@router.post("/intake/{harvest_pickup_request_id}", response_model=FulfilmentIntakeResponse)
def confirm_intake(
    harvest_pickup_request_id: str,
    payload: FulfilmentIntakeCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FINANCE)),
):
    req = db.query(HarvestPickupRequest).filter(HarvestPickupRequest.id == harvest_pickup_request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Harvest pickup request not found.")

    job = db.query(DispatchJob).filter(DispatchJob.harvest_pickup_request_id == req.id).first()
    if not job or job.status != DispatchJobStatus.DELIVERED:
        raise HTTPException(status_code=409, detail="This pickup hasn't been delivered to the fulfilment centre yet.")

    if db.query(FulfilmentIntake).filter(FulfilmentIntake.harvest_pickup_request_id == req.id).first():
        raise HTTPException(status_code=409, detail="This pickup has already been graded.")

    intake = FulfilmentIntake(
        harvest_pickup_request_id=req.id,
        weigh_in_kg=payload.weigh_in_kg,
        grade=payload.grade,
        graded_by=user.id,
    )
    db.add(intake)
    db.commit()
    db.refresh(intake)

    farmer = db.query(User).filter(User.id == req.farmer_id).first()
    log_audit(
        db, user, "fulfilment_intake_graded",
        f"Harvest pickup {req.id} ({farmer.full_name}, {req.quantity_ready_tonnes}t expected): "
        f"weighed in at {payload.weigh_in_kg}kg, graded {payload.grade.value}.",
    )
    return intake
