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
    InputOrder, InputOrderLine, ProofOfDelivery, TrunkingJob, TrunkingStatus,
    FulfilmentIntake, GradeResult,
)
from ..auth import require_roles
from ..schemas import (
    DispatchJobResponse, DispatchAssignRequest,
    ProofOfDeliveryCreate, ProofOfDeliveryResponse,
    TrunkingJobCreate, TrunkingJobResponse, TrunkingAvailabilityResponse,
)

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


# ---------------------------------------------------------------------------
# Proof of Pickup/Delivery -- Stage 3 wireframe. Added 8 Sep 2026, closing a
# gap this session's own completeness audit surfaced. Captured for a job
# already DELIVERED (see models.ProofOfDelivery) -- additive to the existing,
# already-tested "Mark delivered" action above, not a replacement for it.
# ---------------------------------------------------------------------------


def _proof_view(p: ProofOfDelivery, db: Session) -> ProofOfDeliveryResponse:
    confirmer = db.query(User).filter(User.id == p.confirmed_by).first()
    return ProofOfDeliveryResponse(
        id=p.id, dispatch_job_id=p.dispatch_job_id,
        confirmed_by_name=confirmer.full_name if confirmer else "Unknown",
        gps_lat=p.gps_lat, gps_lng=p.gps_lng,
        signature_captured=p.signature_captured, photo_captured=p.photo_captured, created_at=p.created_at,
    )


@router.get("/jobs/{job_id}/proof", response_model=ProofOfDeliveryResponse)
def get_proof(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.LOGISTICS)),
):
    proof = db.query(ProofOfDelivery).filter(ProofOfDelivery.dispatch_job_id == job_id).first()
    if not proof:
        raise HTTPException(status_code=404, detail="No proof captured for this job yet.")
    return _proof_view(proof, db)


@router.post("/jobs/{job_id}/proof", response_model=ProofOfDeliveryResponse)
def capture_proof(
    job_id: str,
    payload: ProofOfDeliveryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.LOGISTICS)),
):
    job = db.query(DispatchJob).filter(DispatchJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Dispatch job not found.")
    if job.status != DispatchJobStatus.DELIVERED:
        raise HTTPException(status_code=409, detail=f"Job is '{job.status.value}', not yet delivered -- mark delivered first.")
    if db.query(ProofOfDelivery).filter(ProofOfDelivery.dispatch_job_id == job_id).first():
        raise HTTPException(status_code=409, detail="Proof has already been captured for this job.")

    proof = ProofOfDelivery(
        dispatch_job_id=job_id, confirmed_by=user.id,
        gps_lat=payload.gps_lat, gps_lng=payload.gps_lng,
        signature_captured=payload.signature_captured, photo_captured=payload.photo_captured,
    )
    db.add(proof)
    db.commit()
    db.refresh(proof)
    return _proof_view(proof, db)


# ---------------------------------------------------------------------------
# Trunking -- Stage 3 wireframe. Added 8 Sep 2026, same audit. Previously
# entirely absent (no model, no stub, no endpoint). Deliberately thin per
# the wireframe's own caption: single origin (Tema), no multi-centre routing
# (Phase 3) -- see models.TrunkingJob.
# ---------------------------------------------------------------------------


def _tonnes_available(db: Session) -> float:
    graded_kg = sum(
        i.weigh_in_kg for i in
        db.query(FulfilmentIntake).filter(FulfilmentIntake.grade != GradeResult.REJECT).all()
    )
    already_trunked = sum(j.produce_tonnes for j in db.query(TrunkingJob).all())
    return round(graded_kg / 1000.0 - already_trunked, 3)


@router.get("/trunking/availability", response_model=TrunkingAvailabilityResponse)
def trunking_availability(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.LOGISTICS)),
):
    return TrunkingAvailabilityResponse(tonnes_available=_tonnes_available(db))


@router.get("/trunking", response_model=List[TrunkingJobResponse])
def list_trunking_jobs(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.LOGISTICS)),
):
    return db.query(TrunkingJob).order_by(TrunkingJob.created_at.desc()).all()


@router.post("/trunking", response_model=TrunkingJobResponse)
def schedule_trunking_job(
    payload: TrunkingJobCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.LOGISTICS)),
):
    available = _tonnes_available(db)
    if payload.produce_tonnes <= 0:
        raise HTTPException(status_code=422, detail="produce_tonnes must be greater than zero.")
    if payload.produce_tonnes > available:
        raise HTTPException(status_code=409, detail=f"Only {available}t of graded produce is ready -- cannot trunk {payload.produce_tonnes}t.")

    job = TrunkingJob(
        produce_tonnes=payload.produce_tonnes, tonnes_available_at_creation=available,
        destination=payload.destination, vehicle_label=payload.vehicle_label, scheduled_by=user.id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@router.post("/trunking/{job_id}/dispatch", response_model=TrunkingJobResponse)
def dispatch_trunking_job(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.LOGISTICS)),
):
    job = db.query(TrunkingJob).filter(TrunkingJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Trunking job not found.")
    if job.status != TrunkingStatus.SCHEDULED:
        raise HTTPException(status_code=409, detail=f"Job is '{job.status.value}', not ready to dispatch.")
    job.status = TrunkingStatus.DISPATCHED
    job.dispatched_at = datetime.utcnow()
    db.commit()
    db.refresh(job)
    return job


@router.post("/trunking/{job_id}/deliver", response_model=TrunkingJobResponse)
def deliver_trunking_job(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.LOGISTICS)),
):
    job = db.query(TrunkingJob).filter(TrunkingJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Trunking job not found.")
    if job.status != TrunkingStatus.DISPATCHED:
        raise HTTPException(status_code=409, detail=f"Job is '{job.status.value}', not dispatched.")
    job.status = TrunkingStatus.DELIVERED
    job.delivered_at = datetime.utcnow()
    db.commit()
    db.refresh(job)
    return job
