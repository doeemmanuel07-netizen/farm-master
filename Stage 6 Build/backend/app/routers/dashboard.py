"""
Control Centre Dashboard -- the real backend behind the Stage 3 wireframe's
"Control Centre Dashboard" (internal_operations_wireframe.html), the shared
entry point for Internal Operations. Added 8 Sep 2026, closing a gap this
session's own completeness audit surfaced: in the confirmed IA/wireframe/
visual scope from day one, never previously built.

"One shared entry point, but the tiles that render depend on the logged-in
role" (wireframe's own caption, citing PRD Section 3.2/Section 5 RBAC) --
modelled here as one endpoint open to every Internal Operations role,
returning a non-sensitive shared season snapshot (registered farmers/
buyers/volume, already visible to Finance via Reporting) plus a `tiles`
dict scoped to the caller's own role's domain only. Finance never sees
account-admin counts; Super Admin never sees reconciliation figures --
same segregation-of-duties principle as everywhere else in this codebase
(PRD Section 5).

Extended 9 Sep 2026 with two new Internal Ops Staff roles, splitting real
pilot job functions out from Super Admin/Agronomist/Finance rather than
having every internal staff member share the one Super Admin login:
OPERATIONS_COORDINATOR (matching farmer candidates to buyer requirements,
tracking requirements end to end -- a narrower slice of Agronomist's own
Matching Queue access, without formulas/visit-logs/messaging) and
COMPLIANCE_OFFICER (MoFA compliance reporting plus read-only reconciliation
visibility -- a narrower slice of Finance's own access, without fee
capture or settlement/payout release authority). Neither gets User & Role
Admin or rate-configuration access -- that stays Super-Admin-only.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    User, Role, UserStatus, FieldVisitLog, FieldVisitStatus, AgronomistMessage,
    DispatchJob, DispatchJobStatus, TrunkingJob, TrunkingStatus,
    BuyerRequirement, RequirementStatus, MofaImportRecord, RegistrationApproval,
    FulfilmentIntake, GradeResult,
)
from ..auth import require_roles
from ..reporting import get_compliance_rows
from ..schemas import ControlCentreDashboardResponse

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/control-centre", response_model=ControlCentreDashboardResponse)
def control_centre_dashboard(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(
        Role.AGRONOMIST, Role.LOGISTICS, Role.FINANCE, Role.SUPER_ADMIN,
        Role.OPERATIONS_COORDINATOR, Role.COMPLIANCE_OFFICER,
    )),
):
    registered_farmers = db.query(User).filter(User.role == Role.FARMER, User.status == UserStatus.ACTIVE).count()
    active_buyers = db.query(User).filter(User.role == Role.BUYER, User.status == UserStatus.ACTIVE).count()
    all_intakes = db.query(FulfilmentIntake).all()
    volume_tonnes = sum(i.weigh_in_kg for i in all_intakes if i.grade != GradeResult.REJECT) / 1000.0

    tiles = {}
    if user.role == Role.AGRONOMIST:
        tiles = {
            "matching_queue_open": db.query(BuyerRequirement).filter(BuyerRequirement.status == RequirementStatus.MATCHING).count(),
            "visits_scheduled": db.query(FieldVisitLog).filter(FieldVisitLog.agronomist_id == user.id, FieldVisitLog.status == FieldVisitStatus.SCHEDULED).count(),
            "unread_messages": db.query(AgronomistMessage).filter(AgronomistMessage.agronomist_id.is_(None)).count(),
        }
    elif user.role == Role.LOGISTICS:
        tiles = {
            "dispatch_jobs_open": db.query(DispatchJob).filter(DispatchJob.status != DispatchJobStatus.DELIVERED).count(),
            "trunking_scheduled": db.query(TrunkingJob).filter(TrunkingJob.status == TrunkingStatus.SCHEDULED).count(),
        }
    elif user.role == Role.FINANCE:
        tiles = {
            "reconciliation_orders": db.query(BuyerRequirement).count(),
            "mofa_import_records": db.query(MofaImportRecord).count(),
        }
    elif user.role == Role.SUPER_ADMIN:
        tiles = {
            "pending_registrations": db.query(RegistrationApproval).filter(RegistrationApproval.status == "pending_review").count(),
            "total_users": db.query(User).count(),
        }
    elif user.role == Role.OPERATIONS_COORDINATOR:
        tiles = {
            "matching_queue_open": db.query(BuyerRequirement).filter(BuyerRequirement.status == RequirementStatus.MATCHING).count(),
            "active_farmer_candidates": db.query(User).filter(User.role == Role.FARMER, User.status == UserStatus.ACTIVE).count(),
        }
    elif user.role == Role.COMPLIANCE_OFFICER:
        tiles = {
            "compliance_report_rows": len(get_compliance_rows(db)),
        }

    return ControlCentreDashboardResponse(
        role=user.role, registered_farmers=registered_farmers, active_buyers=active_buyers,
        volume_aggregated_tonnes=round(volume_tonnes, 3), tiles=tiles,
    )
