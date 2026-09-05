"""
Vendor mechanisation request flow -- the real backend behind
vendor_mechanisation_request_flow_live.html.

Unlike Opportunity (a shared pool any farmer can accept), a
MechanisationRequest is already directed at a specific vendor, so every
route here scopes to request.vendor_id == caller.id, the same "own only"
pattern as buyer.py's requirements.

The date-conflict override (Emmanuel's decision, 3 Sep 2026) is a real
two-party workflow: confirming a date past requested_by_date does not
finalise anything here -- it sets override_needed and stores the proposal.
Only Super Admin (routers/admin.py) can finalise it. This is stricter than
the Stage 5 prototype, which simulated approval within one session.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Role, RateConfig, MechanisationRequest, MechanisationRequestStatus
from ..auth import require_roles
from ..dispatch import create_dispatch_job
from ..schemas import MechanisationRequestResponse, ConfirmRequestBody

router = APIRouter(prefix="/vendor", tags=["vendor"])


def _get_rate(db: Session, key: str) -> float:
    row = db.query(RateConfig).filter(RateConfig.key == key).first()
    if not row:
        raise HTTPException(status_code=500, detail=f"Rate config '{key}' is not seeded.")
    return row.value


def _with_quote(db: Session, req: MechanisationRequest) -> MechanisationRequest:
    # Suggested quote is computed on read, not stored, so a rate_config
    # change (via PUT /admin/rates/{key}) is reflected immediately.
    rate = _get_rate(db, "vendor_service_fee_per_tonne")
    req.suggested_quote = round(req.area_acres * rate, 2)
    return req


def _own_request(db: Session, request_id: str, user: User) -> MechanisationRequest:
    req = db.query(MechanisationRequest).filter(MechanisationRequest.id == request_id).first()
    if not req or req.vendor_id != user.id:
        raise HTTPException(status_code=404, detail="Request not found.")
    return req


@router.get("/requests", response_model=list[MechanisationRequestResponse])
def list_requests(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.VENDOR)),
):
    reqs = db.query(MechanisationRequest).filter(MechanisationRequest.vendor_id == user.id).all()
    return [_with_quote(db, r) for r in reqs]


@router.get("/requests/{request_id}", response_model=MechanisationRequestResponse)
def get_request(
    request_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.VENDOR)),
):
    return _with_quote(db, _own_request(db, request_id, user))


@router.post("/requests/{request_id}/confirm", response_model=MechanisationRequestResponse)
def confirm_request(
    request_id: str,
    payload: ConfirmRequestBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.VENDOR)),
):
    req = _own_request(db, request_id, user)
    if req.status != MechanisationRequestStatus.PENDING:
        raise HTTPException(status_code=409, detail=f"Request is '{req.status.value}', not confirmable.")

    try:
        confirmed = datetime.strptime(payload.confirmed_date, "%Y-%m-%d").date()
        window_end = datetime.strptime(req.requested_by_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=422, detail="confirmed_date must be an ISO date, e.g. 2026-09-20.")

    if confirmed > window_end:
        # Outside the farmer's requested window: store the proposal, do NOT
        # finalise. The vendor cannot self-approve this -- only Super Admin
        # can, via POST /admin/vendor-requests/{id}/approve-override.
        req.override_needed = True
        req.proposed_date = payload.confirmed_date
        req.proposed_notes = payload.notes
        db.commit()
        db.refresh(req)
        return _with_quote(db, req)

    req.confirmed_date = payload.confirmed_date
    req.notes = payload.notes
    req.status = MechanisationRequestStatus.CONFIRMED
    req.override_needed = False
    db.commit()
    db.refresh(req)
    create_dispatch_job(db, req)
    return _with_quote(db, req)


@router.post("/requests/{request_id}/decline", response_model=MechanisationRequestResponse)
def decline_request(
    request_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.VENDOR)),
):
    req = _own_request(db, request_id, user)
    if req.status != MechanisationRequestStatus.PENDING:
        raise HTTPException(status_code=409, detail=f"Request is '{req.status.value}', not declinable.")
    req.status = MechanisationRequestStatus.DECLINED
    db.commit()
    db.refresh(req)
    return _with_quote(db, req)
