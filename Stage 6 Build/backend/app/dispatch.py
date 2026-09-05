"""
Shared dispatch-job creation -- the single call site both of a
MechanisationRequest's two confirmation paths (vendor.py's in-window
confirm, and admin.py's date-conflict override approval) must use, so a
confirmed request always produces exactly one real DispatchJob rather than
each path implementing its own version of "and now notify logistics."
"""

from sqlalchemy.orm import Session

from .models import DispatchJob, DispatchDirection, MechanisationRequest


def create_dispatch_job(db: Session, request: MechanisationRequest) -> DispatchJob:
    job = DispatchJob(
        mechanisation_request_id=request.id,
        direction=DispatchDirection.OUTBOUND,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job
