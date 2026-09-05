"""
Super Admin endpoints: role assignment, registration approval, audit log
visibility, and rate configuration. Every route here requires SUPER_ADMIN --
FINANCE is deliberately excluded (segregation of duties, PRD Section 5/3.2:
"no single role can both move money and grant its own permissions").
"""

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Role, UserStatus, AuditLog, RegistrationApproval, RateConfig, MechanisationRequest, MechanisationRequestStatus
from ..auth import require_roles
from ..audit import log_audit
from ..schemas import (
    RoleChangeRequest, AuditLogEntry, RateConfigResponse, RateConfigUpdate,
    MechanisationRequestResponse, RegistrationApprovalResponse,
)

router = APIRouter(prefix="/admin", tags=["admin (Super Admin only)"])


@router.get("/registrations", response_model=List[RegistrationApprovalResponse])
def list_registrations(
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(Role.SUPER_ADMIN)),
):
    """
    Added 5 Sep 2026 alongside real-time OTP verification (PRD Section 12):
    approve/reject already existed but nothing let a Super Admin discover
    what's pending -- auth.py's register/verify-otp is the first thing that
    actually creates these rows.
    """
    return db.query(RegistrationApproval).order_by(RegistrationApproval.created_at.desc()).all()


@router.put("/users/{user_id}/role")
def change_role(
    user_id: str,
    payload: RoleChangeRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(Role.SUPER_ADMIN)),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    old_role = target.role.value
    target.role = payload.new_role
    db.commit()
    log_audit(db, admin, "role_changed", f"{target.full_name} ({target.email}): {old_role} -> {payload.new_role.value}.")
    return {"id": target.id, "email": target.email, "role": target.role}


@router.post("/registrations/{registration_id}/approve")
def approve_registration(
    registration_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(Role.SUPER_ADMIN)),
):
    reg = db.query(RegistrationApproval).filter(RegistrationApproval.id == registration_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail="Registration not found.")
    reg.status = "approved"
    reg.reviewed_by = admin.id
    reg.reviewed_at = datetime.utcnow()
    if reg.user_id:
        user = db.query(User).filter(User.id == reg.user_id).first()
        if user:
            user.status = UserStatus.ACTIVE
    db.commit()
    log_audit(db, admin, "registration_approved", f"{reg.applicant_name} ({reg.applicant_type}, {reg.portal} portal).")
    return {"id": reg.id, "status": reg.status}


@router.post("/registrations/{registration_id}/reject")
def reject_registration(
    registration_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(Role.SUPER_ADMIN)),
):
    reg = db.query(RegistrationApproval).filter(RegistrationApproval.id == registration_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail="Registration not found.")
    reg.status = "rejected"
    reg.reviewed_by = admin.id
    reg.reviewed_at = datetime.utcnow()
    if reg.user_id:
        user = db.query(User).filter(User.id == reg.user_id).first()
        if user:
            # No dedicated "rejected" UserStatus -- SUSPENDED is the closest
            # existing terminal-negative state, and is equally correct here:
            # either way, this account must not be able to log in.
            user.status = UserStatus.SUSPENDED
    db.commit()
    log_audit(db, admin, "registration_rejected", f"{reg.applicant_name} ({reg.applicant_type}, {reg.portal} portal).")
    return {"id": reg.id, "status": reg.status}


@router.post("/vendor-requests/{request_id}/approve-override", response_model=MechanisationRequestResponse)
def approve_date_override(
    request_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(Role.SUPER_ADMIN)),
):
    """
    Finalises a vendor's date-conflict override. This is the "buyer or admin
    approval" required by Emmanuel's decision (3 Sep 2026) -- scoped to
    Super Admin only for this pass, since a cross-portal Buyer-approval path
    would need a buyer_id link on the request that doesn't exist yet
    (documented as a known scope limit, not silently assumed away).
    """
    req = db.query(MechanisationRequest).filter(MechanisationRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found.")
    if not req.override_needed or req.proposed_date is None:
        raise HTTPException(status_code=409, detail="This request has no pending date-conflict override.")

    req.confirmed_date = req.proposed_date
    req.notes = req.proposed_notes
    req.override_approved = True
    req.override_approver_id = admin.id
    req.status = MechanisationRequestStatus.CONFIRMED
    db.commit()
    db.refresh(req)

    log_audit(
        db, admin, "date_conflict_override_approved",
        f"Mechanisation request {req.id} ({req.farmer_name}, {req.service}): confirmed for "
        f"{req.confirmed_date}, outside requested window (by {req.requested_by_date}).",
    )
    req.suggested_quote = None
    return req


@router.get("/audit-log", response_model=List[AuditLogEntry])
def list_audit_log(
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(Role.SUPER_ADMIN)),
):
    # Read-only by design -- there is deliberately no PUT/DELETE for this
    # table anywhere in the API, including for Super Admin.
    return db.query(AuditLog).order_by(AuditLog.created_at.desc()).all()


@router.get("/rates", response_model=List[RateConfigResponse])
def list_rates(
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(Role.SUPER_ADMIN)),
):
    return db.query(RateConfig).all()


@router.put("/rates/{key}", response_model=RateConfigResponse)
def update_rate(
    key: str,
    payload: RateConfigUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(Role.SUPER_ADMIN)),
):
    row = db.query(RateConfig).filter(RateConfig.key == key).first()
    if not row:
        raise HTTPException(status_code=404, detail="Rate config key not found.")
    old_value = row.value
    row.value = payload.value
    db.commit()
    db.refresh(row)
    log_audit(db, admin, "rate_config_changed", f"{key}: {old_value} -> {payload.value} {row.unit}.")
    return row
