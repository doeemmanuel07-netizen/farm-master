"""
Logistics Dispatch -- the real backend behind logistics_dispatch_flow_live.html.
PRD Section 6 Must-Have #3 ("Vendor input ordering routed to logistics
dispatch") and #4 ("...fulfilment centre intake/grading"); IA Section 3.5,
Fig. 6. Outbound jobs come from a CONFIRMED MechanisationRequest or a
CONFIRMED InputOrder; inbound jobs come from a HarvestPickupRequest -- see
models.DispatchJob for why exactly one of the three source FKs is ever set.

Logistics and field roles are confirmed phone-first (PRD Section 5.1,
Emmanuel, 3 Sep 2026) -- the frontend flow defaults to the phone viewport
rather than desktop for that reason.
"""

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    User, Role, DispatchJob, DispatchJobStatus, MechanisationRequest, HarvestPickupRequest,
    InputOrder, InputOrderLine,
)
from ..auth import require_roles
from ..schemas import DispatchJobResponse, DispatchAssignRequest

router = APIRouter(prefix="/logistics", tags=["logistics"])


def _job_view(job: DispatchJob, db: Session) -> DispatchJobResponse:
    if job.mechanisation_request_id:
        req = db.query(MechanisationRequest).filter(MechanisationRequest.id == job.mechanisation_request_id).first()
        return DispatchJobResponse(
            id=job.id,
            job_type="mechanisation",
            farmer_name=req.farmer_name,
            description=req.service,
            area_acres=req.area_acres,
            confirmed_date=req.confirmed_date,
            direction=job.direction,
            status=job.status,
            tricycle_label=job.tricycle_label,
            delivered_at=job.delivered_at,
        )

    if job.input_order_id:
        order = db.query(InputOrder).filter(InputOrder.id == job.input_order_id).first()
        farmer = db.query(User).filter(User.id == order.farmer_id).first()
        item_count = db.query(InputOrderLine).filter(InputOrderLine.input_order_id == order.id).count()
        return DispatchJobResponse(
            id=job.id,
            job_type="input_order",
            farmer_name=farmer.full_name,
            description=f"Input order ({item_count} item{'s' if item_count != 1 else ''})",
            item_count=item_count,
            total_cost=order.total_cost,
            direction=job.direction,
            status=job.status,
            tricycle_label=job.tricycle_label,
            delivered_at=job.delivered_at,
        )

    req = db.query(HarvestPickupRequest).filter(HarvestPickupRequest.id == job.harvest_pickup_request_id).first()
    farmer = db.query(User).filter(User.id == req.farmer_id).first()
    return DispatchJobResponse(
        id=job.id,
        job_type="harvest_pickup",
        farmer_name=farmer.full_name,
        description="Harvest pickup",
        quantity_tonnes=req.quantity_ready_tonnes,
        preferred_pickup_date=req.preferred_pickup_date,
        direction=job.direction,
        status=job.status,
        tricycle_label=job.tricycle_label,
        delivered_at=job.delivered_at,
    )


@router.get("/jobs", response_model=List[DispatchJobResponse])
def list_jobs(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.LOGISTICS)),
):
    jobs = db.query(DispatchJob).order_by(DispatchJob.created_at.desc()).all()
    return [_job_view(j, db) for j in jobs]


@router.post("/jobs/{job_id}/dispatch", response_model=DispatchJobResponse)
def dispatch_job(
    job_id: str,
    payload: DispatchAssignRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.LOGISTICS)),
):
    job = db.query(DispatchJob).filter(DispatchJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Dispatch job not found.")
    if job.status != DispatchJobStatus.ASSIGNED:
        raise HTTPException(status_code=409, detail=f"Job is '{job.status.value}', not ready to dispatch.")

    job.tricycle_label = payload.tricycle_label
    job.status = DispatchJobStatus.EN_ROUTE
    job.dispatched_by = user.id
    db.commit()
    db.refresh(job)
    return _job_view(job, db)


@router.post("/jobs/{job_id}/deliver", response_model=DispatchJobResponse)
def deliver_job(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.LOGISTICS)),
):
    job = db.query(DispatchJob).filter(DispatchJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Dispatch job not found.")
    if job.status != DispatchJobStatus.EN_ROUTE:
        raise HTTPException(status_code=409, detail=f"Job is '{job.status.value}', not en route.")

    job.status = DispatchJobStatus.DELIVERED
    job.delivered_at = datetime.utcnow()
    db.commit()
    db.refresh(job)
    return _job_view(job, db)
