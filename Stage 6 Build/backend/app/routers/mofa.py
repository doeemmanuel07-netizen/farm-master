"""
MoFA Data Exchange -- the real backend behind mofa_compliance_report_flow_live.html.
PRD Section 1.1/9, IA Section 1/6/7: "a generic exportable report (CSV/PDF)
covering volume, quality grade, buyer, and delivery date" -- explicitly a
placeholder pending an actual MoFA data standard, not a finished template.

Scoped to the export half of the Stage 3 wireframe's "MoFA Data Exchange"
screen. The wireframe's other panel -- importing verified institutional
buyer/accreditation data from MoFA -- is a static "no live API yet" stub
even in the wireframe itself (no real MoFA import API exists to call), so
it isn't built here; building a fake import against nothing real would be
decorative, not a real feature. See app/reporting.py for the query and
export-rendering logic this router only wires up to real routes.

Every route is Role.FINANCE-gated, matching the wireframe and IA Section
10's confirmed ownership (Reporting/MoFA Data Exchange stay with Finance,
not Super Admin, since they're external/financial reporting duties).
"""

from typing import List

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Role
from ..auth import require_roles
from ..reporting import get_compliance_rows, to_csv_bytes, to_pdf_bytes
from ..schemas import ComplianceReportRowResponse

router = APIRouter(prefix="/mofa", tags=["mofa"])


@router.get("/compliance-report", response_model=List[ComplianceReportRowResponse])
def list_compliance_report(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FINANCE)),
):
    return get_compliance_rows(db)


@router.get("/compliance-report/export.csv")
def export_compliance_report_csv(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FINANCE)),
):
    csv_bytes = to_csv_bytes(get_compliance_rows(db))
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=mofa_compliance_report.csv"},
    )


@router.get("/compliance-report/export.pdf")
def export_compliance_report_pdf(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FINANCE)),
):
    pdf_bytes = to_pdf_bytes(get_compliance_rows(db))
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=mofa_compliance_report.pdf"},
    )
