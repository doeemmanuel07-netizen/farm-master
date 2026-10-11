"""
Internal Operations additions for the CEO platform demo (brief §7): the
commitment-fee payments list, and (later in this pass) the agronomist task
queue and marketplace dispatch. Read access follows the existing money
segregation: Finance and Super Admin see payments, and Compliance Officer
gets the same read-only view it already has of reconciliation.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..audit import log_audit
from ..auth import require_roles
from ..database import get_db
from ..fleet import aggregated_today, emit_order_progress
from ..models import (
    BuyerRequirement, CommitmentFeePayment, PaymentStatus, RequirementStatus, Role, User, Vehicle,
    AgronomistTask, AgronomistTaskStatus,
)
from ..orders import requirement_view
from ..payments.service import NETWORK_LABEL
from ..schemas import (
    OpsPaymentRow, VehicleResponse, OrderAdvanceRequest, AggregationRow, RequirementResponse,
    AgronomistTaskResponse, AgronomistTaskComplete,
)
from ..state import transition

router = APIRouter(prefix="/ops", tags=["internal operations"])


@router.get("/payments", response_model=List[OpsPaymentRow])
def list_payments(
    status: Optional[PaymentStatus] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FINANCE, Role.SUPER_ADMIN, Role.COMPLIANCE_OFFICER)),
):
    q = db.query(CommitmentFeePayment)
    if status is not None:
        q = q.filter(CommitmentFeePayment.status == status)
    rows = []
    for p in q.order_by(CommitmentFeePayment.created_at.desc()).limit(500).all():
        req = db.query(BuyerRequirement).filter(BuyerRequirement.id == p.requirement_id).first()
        buyer = req.buyer if req else None
        rows.append(OpsPaymentRow(
            id=p.id, requirement_id=p.requirement_id, requirement_reference=req.reference if req else None,
            buyer_name=(buyer.organisation_name or buyer.full_name) if buyer else "(unknown)",
            amount=p.amount, network_label=NETWORK_LABEL.get(p.network, p.method), provider=p.provider,
            provider_ref=p.provider_ref or p.transaction_ref, status=p.status, failure_reason=p.failure_reason,
            created_at=p.created_at, paid_at=p.paid_at,
        ))
    return rows


# ---------------------------------------------------------------------------
# Fleet, order progression and aggregation (brief §7)
# ---------------------------------------------------------------------------

LOGISTICS_OPS = (Role.LOGISTICS, Role.SUPER_ADMIN, Role.OPERATIONS_COORDINATOR)


@router.get("/vehicles", response_model=List[VehicleResponse])
def list_vehicles(db: Session = Depends(get_db), user: User = Depends(require_roles(*LOGISTICS_OPS))):
    return [
        VehicleResponse(id=v.id, code=v.code, vehicle_type=v.vehicle_type.value,
                        home_centre=v.home_centre.town if v.home_centre else "", status=v.status.value)
        for v in db.query(Vehicle).order_by(Vehicle.vehicle_type, Vehicle.code).all()
    ]


@router.get("/aggregation", response_model=List[AggregationRow])
def aggregation_today(db: Session = Depends(get_db), user: User = Depends(require_roles(*LOGISTICS_OPS, Role.FINANCE))):
    return [
        AggregationRow(centre=c.name if c else "(unknown)", crop=cr.name if cr else "(unknown)", tonnes_today=round(t, 3))
        for c, cr, t in aggregated_today(db)
    ]


@router.post("/requirements/{requirement_id}/advance", response_model=RequirementResponse)
def advance_order(
    requirement_id: str, payload: OrderAdvanceRequest,
    db: Session = Depends(get_db), user: User = Depends(require_roles(*LOGISTICS_OPS)),
):
    """Moves an aggregated order on to In transit, then Delivered -- only along the allowed transitions."""
    if payload.status not in (RequirementStatus.SHIPMENT, RequirementStatus.DELIVERED):
        raise HTTPException(status_code=422, detail="Only 'shipment' and 'delivered' are set from here; earlier stages follow payment, matching and intake.")
    req = db.query(BuyerRequirement).filter(BuyerRequirement.id == requirement_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found.")
    transition(req, payload.status)
    db.commit()
    emit_order_progress(db, req, delivered=payload.status == RequirementStatus.DELIVERED)
    log_audit(db, user, "order_advanced", f"{req.reference} -> {payload.status.value}.")
    return requirement_view(db, req)



# ---------------------------------------------------------------------------
# Agronomist task queue (brief §4.2 48h follow-ups, §2F purchased visits)
# ---------------------------------------------------------------------------

AGRONOMY_OPS = (Role.AGRONOMIST, Role.SUPER_ADMIN, Role.OPERATIONS_COORDINATOR)


def _task_view(db: Session, t: AgronomistTask) -> AgronomistTaskResponse:
    farmer = db.query(User).filter(User.id == t.farmer_id).first()
    return AgronomistTaskResponse(
        id=t.id, kind=t.kind.value, status=t.status.value, farmer_name=farmer.full_name if farmer else "(unknown)",
        summary=t.summary, due_at=t.due_at, created_at=t.created_at, completed_at=t.completed_at, notes=t.notes,
        overdue=t.status == AgronomistTaskStatus.OPEN and t.due_at < datetime.utcnow(),
    )


@router.get("/agronomist-tasks", response_model=List[AgronomistTaskResponse])
def list_agronomist_tasks(
    status: Optional[AgronomistTaskStatus] = Query(None),
    db: Session = Depends(get_db), user: User = Depends(require_roles(*AGRONOMY_OPS)),
):
    q = db.query(AgronomistTask)
    if status is not None:
        q = q.filter(AgronomistTask.status == status)
    return [_task_view(db, t) for t in q.order_by(AgronomistTask.status, AgronomistTask.due_at).all()]


@router.post("/agronomist-tasks/{task_id}/complete", response_model=AgronomistTaskResponse)
def complete_agronomist_task(
    task_id: str, payload: AgronomistTaskComplete,
    db: Session = Depends(get_db), user: User = Depends(require_roles(Role.AGRONOMIST, Role.SUPER_ADMIN)),
):
    t = db.query(AgronomistTask).filter(AgronomistTask.id == task_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Task not found.")
    if t.status == AgronomistTaskStatus.DONE:
        raise HTTPException(status_code=409, detail="This task is already done.")
    t.status = AgronomistTaskStatus.DONE
    t.completed_at = datetime.utcnow()
    t.completed_by = user.id
    t.notes = (payload.notes or "").strip() or None
    db.commit()
    log_audit(db, user, "agronomist_task_completed", f"{t.summary} (due {t.due_at:%Y-%m-%d %H:%M}).")
    return _task_view(db, t)
