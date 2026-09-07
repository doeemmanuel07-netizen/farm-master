"""
Super Admin endpoints: role assignment, registration approval, audit log
visibility, rate configuration, and (added 7 Sep 2026) User & Role Admin's
account listing/creation/suspension -- the real backend behind
useradmin_flow_live.html, built against the confirmed Stage 4 visual
(internal_operations_visual.html:460-484). Every route here requires
SUPER_ADMIN -- FINANCE is deliberately excluded (segregation of duties,
PRD Section 5/3.2: "no single role can both move money and grant its own
permissions").
"""

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    User, Role, UserStatus, AuditLog, RegistrationApproval, RateConfig,
    MechanisationRequest, MechanisationRequestStatus, SELF_REGISTER_ROLES, INTERNAL_ROLES,
)
from ..auth import require_roles, hash_password
from ..audit import log_audit
from ..dispatch import create_dispatch_job
from ..schemas import (
    RoleChangeRequest, AuditLogEntry, RateConfigResponse, RateConfigUpdate,
    MechanisationRequestResponse, RegistrationApprovalResponse,
    AdminUserResponse, AdminUsersResponse, InternalUserCreate,
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
    create_dispatch_job(db, req)

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


# ---------------------------------------------------------------------------
# User & Role Admin -- the account-listing/creation/suspension screen
# (Stage 4 visual, internal_operations_visual.html:460-484). "Change role"
# above already covered that screen's internal-staff action; the rest is
# here. Every action on this screen writes to the audit log, per the
# mockup's own caption.
# ---------------------------------------------------------------------------

# Verbatim from the confirmed Stage 4 visual's "Scope" column -- a fixed,
# per-role description of what that role's real endpoints permit (matches
# this codebase's actual RBAC), not per-user data.
ROLE_SCOPE_LABEL = {
    Role.AGRONOMIST: "Formulas, visit logs, messaging — Tema",
    Role.LOGISTICS: "Dispatch, proof of pickup/delivery — no financial data",
    Role.FINANCE: "Reconciliation, reporting, MoFA export — no account/role admin",
    Role.SUPER_ADMIN: "Accounts, roles, registration approval, audit log — all four portals",
}


def _user_view(user: User, db: Session) -> AdminUserResponse:
    registration_approval_id = None
    if user.role in SELF_REGISTER_ROLES and user.status == UserStatus.PENDING:
        reg = (
            db.query(RegistrationApproval)
            .filter(RegistrationApproval.user_id == user.id, RegistrationApproval.status == "pending_review")
            .first()
        )
        registration_approval_id = reg.id if reg else None
    return AdminUserResponse(
        id=user.id, full_name=user.full_name, email=user.email, role=user.role,
        status=user.status, organisation_name=user.organisation_name,
        scope=ROLE_SCOPE_LABEL.get(user.role) if user.role in INTERNAL_ROLES else None,
        registration_approval_id=registration_approval_id,
    )


@router.get("/users", response_model=AdminUsersResponse)
def list_users(
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(Role.SUPER_ADMIN)),
):
    users = db.query(User).order_by(User.created_at.asc()).all()
    internal = [_user_view(u, db) for u in users if u.role in INTERNAL_ROLES]
    external = [_user_view(u, db) for u in users if u.role in SELF_REGISTER_ROLES]
    return AdminUsersResponse(internal=internal, external=external)


@router.post("/users", response_model=AdminUserResponse)
def create_internal_user(
    payload: InternalUserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(Role.SUPER_ADMIN)),
):
    """
    The mockup's "+ Add internal user" button. Internal roles only --
    Farmer/Buyer/Vendor self-register through their own OTP + (for Buyer/
    Vendor) approval flow (routers/auth.py); creating one directly here
    would bypass both. Created ACTIVE immediately, no OTP challenge: every
    seeded internal account already works this way (never went through a
    registration OTP, only ever the login one), so this is consistent with
    the confirmed provisioning model (PRD Section 3.2), not a new one.
    """
    if payload.role not in INTERNAL_ROLES:
        raise HTTPException(
            status_code=422,
            detail="Only internal roles (Agronomist, Logistics, Finance, Super Admin) can be "
                   "created here -- Farmer/Buyer/Vendor self-register.",
        )
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    user = User(
        email=payload.email, phone=payload.phone, full_name=payload.full_name,
        role=payload.role, status=UserStatus.ACTIVE,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    log_audit(db, admin, "internal_user_created", f"{user.full_name} ({user.email}): {user.role.value}.")
    return _user_view(user, db)


def _own_user(db: Session, user_id: str) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


@router.post("/users/{user_id}/suspend", response_model=AdminUserResponse)
def suspend_user(
    user_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(Role.SUPER_ADMIN)),
):
    user = _own_user(db, user_id)
    if user.status == UserStatus.SUSPENDED:
        raise HTTPException(status_code=409, detail="This account is already suspended.")
    old_status = user.status.value
    user.status = UserStatus.SUSPENDED
    db.commit()
    log_audit(db, admin, "account_suspended", f"{user.full_name} ({user.email}): {old_status} -> suspended.")
    return _user_view(user, db)


@router.post("/users/{user_id}/reactivate", response_model=AdminUserResponse)
def reactivate_user(
    user_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(Role.SUPER_ADMIN)),
):
    """
    Not shown as its own row in the Stage 4 mockup (which only depicts an
    Active example row, not a Suspended one), but a real, necessary
    complement to suspend -- without it, suspending an account through this
    screen would be a one-way trap with no way back through the UI at all.
    """
    user = _own_user(db, user_id)
    if user.status != UserStatus.SUSPENDED:
        raise HTTPException(status_code=409, detail="This account isn't suspended.")
    user.status = UserStatus.ACTIVE
    db.commit()
    log_audit(db, admin, "account_reactivated", f"{user.full_name} ({user.email}): suspended -> active.")
    return _user_view(user, db)
