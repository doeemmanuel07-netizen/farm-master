"""
Reporting -- the real backend behind the Stage 3 wireframe "Reporting"
screen (PRD Section 7). Added 8 Sep 2026, closing a gap this session's own
completeness audit surfaced: distinct from the MoFA Compliance Report
(routers/mofa.py), which is an external/buyer-facing export, this is Farm
Master's own internal Phase 1 success-metrics dashboard. Role.FINANCE-gated,
matching the wireframe and IA's confirmed ownership (Reporting stays with
Finance, same as MoFA Data Exchange).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Role
from ..auth import require_roles
from ..reporting import get_reporting_dashboard
from ..schemas import ReportingDashboardResponse

router = APIRouter(prefix="/reporting", tags=["reporting"])


@router.get("/dashboard", response_model=ReportingDashboardResponse)
def reporting_dashboard(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FINANCE)),
):
    return get_reporting_dashboard(db)
