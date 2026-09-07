"""
Shared dispatch-job creation. All three confirmation paths -- a
MechanisationRequest (vendor.py's in-window confirm, and admin.py's
date-conflict override approval), a HarvestPickupRequest (farmer.py), and
an InputOrder (vendor.py's confirm_input_order) -- call one function each
here, so no call site reimplements its own version of "and now notify
logistics."
"""

from sqlalchemy.orm import Session

from .models import DispatchJob, DispatchDirection, MechanisationRequest, HarvestPickupRequest, InputOrder


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


def create_input_order_dispatch_job(db: Session, order: InputOrder) -> DispatchJob:
    job = DispatchJob(
        input_order_id=order.id,
        direction=DispatchDirection.OUTBOUND,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job
