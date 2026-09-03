"""
Audit logging helper. Every financial action and every role/permission
change must call this -- see routers/buyer.py (payment success) and
routers/admin.py (role changes, registration approvals) for the required
call sites.
"""

from sqlalchemy.orm import Session

from .models import AuditLog, User


def log_audit(db: Session, actor: User, action: str, detail: str) -> AuditLog:
    entry = AuditLog(
        actor_user_id=actor.id if actor else None,
        actor_role=actor.role.value if actor else "system",
        action=action,
        detail=detail,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
