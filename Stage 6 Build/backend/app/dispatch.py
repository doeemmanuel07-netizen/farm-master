"""
Shared dispatch-job creation. Both confirmation paths of a
MechanisationRequest (vendor.py's in-window confirm, and admin.py's
date-conflict override approval) call create_dispatch_job, and
HarvestPickupRequest (farmer.py) calls create_inbound_dispatch_job -- one
function per real job source, so no call site reimplements its own version
of "and now notify logistics."
"""

from sqlalchemy.orm import Session

from .models import DispatchJob, DispatchDirection, MechanisationRequest, HarvestPickupRequest


def create_dispatch_job(db: Session, request: MechanisationRequest) -> DispatchJob:
    job = DispatchJob(
        mechanisation_request_id=request.id,
        direction=DispatchDirection.OUTBOUND,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def create_inbound_dispatch_job(db: Session, request: HarvestPickupRequest) -> DispatchJob:
    job = DispatchJob(
        harvest_pickup_request_id=request.id,
        direction=DispatchDirection.INBOUND,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job
