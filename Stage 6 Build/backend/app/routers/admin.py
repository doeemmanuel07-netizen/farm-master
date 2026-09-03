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
from ..models import User, Role, AuditLog, RegistrationApproval, RateConfig
from ..auth import require_roles
from ..audit import log_audit
from ..schemas import RoleChangeRequest, AuditLogEntry, RateConfigResponse, RateConfigUpdate

router = APIRouter(prefix="/admin", tags=["admin (Super Admin only)"])


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
    db.commit()
    log_audit(db, admin, "registration_rejected", f"{reg.applicant_name} ({reg.applicant_type}, {reg.portal} portal).")
    return {"id": reg.id, "status": reg.status}


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
