"""
Shared MoFA compliance report computation and export rendering -- PRD
Section 1.1/9 ("no MoFA data standard confirmed yet... design a generic
exportable report (CSV/PDF) covering volume, quality grade, buyer, and
delivery date; refine once an actual MoFA template is available"). Single
call site for the in-app view and both export formats in
routers/mofa.py, same "integrate, don't duplicate" pattern as
reconciliation.py/formula.py/dispatch.py.

Row scope: one row per graded FulfilmentIntake whose HarvestPickupRequest
is linked to a real buyer order (buyer_requirement_id is not null) -- a
pickup with no buyer link has no buyer to report against, so it's
excluded (this is the same exclusion FulfilmentIntake's own docstring
anticipated: "Feeding a graded intake into Buyer Compliance Docs is
Reporting/MoFA Data Exchange scope"). REJECT-graded rows ARE included,
unlike reconciliation.py's farmer-settlement math (which excludes REJECT
for payment purposes) -- quality grade is itself one of the four confirmed
report columns, so a compliance report that only ever showed grade_1/
grade_2 would defeat its own purpose of showing real quality outcomes.

"Delivery date" uses DispatchJob.delivered_at -- produce arriving at Farm
Master's fulfilment centre. No model in this codebase tracks a separate
Farm-Master-to-buyer shipment event (the Business Concept doc's "order
tracking" was never built as a real delivery record), so this is the only
real, timestamped delivery event connected to a graded, buyer-linked
intake. It is guaranteed non-null for every row here: fulfilment.py's
confirm_intake requires the DispatchJob to already be DELIVERED before
grading is allowed at all.
"""

import csv
import io
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from sqlalchemy.orm import Session

from .models import FulfilmentIntake, HarvestPickupRequest, BuyerRequirement, User, DispatchJob, GradeResult

GRADE_LABELS = {
    GradeResult.GRADE_1: "Grade 1",
    GradeResult.GRADE_2: "Grade 2",
    GradeResult.REJECT: "Reject",
}


@dataclass
class ComplianceReportRow:
    farmer_name: str
    crop: str
    buyer_name: str
    grade: str
    volume_kg: float
    delivery_date: Optional[datetime]


def get_compliance_rows(db: Session) -> List[ComplianceReportRow]:
    intakes = (
        db.query(FulfilmentIntake)
        .join(HarvestPickupRequest, FulfilmentIntake.harvest_pickup_request_id == HarvestPickupRequest.id)
        .filter(HarvestPickupRequest.buyer_requirement_id.isnot(None))
        .all()
    )
    rows: List[ComplianceReportRow] = []
    for intake in intakes:
        pickup = db.query(HarvestPickupRequest).filter(HarvestPickupRequest.id == intake.harvest_pickup_request_id).first()
        requirement = db.query(BuyerRequirement).filter(BuyerRequirement.id == pickup.buyer_requirement_id).first()
        if not requirement:
            continue
        farmer = db.query(User).filter(User.id == pickup.farmer_id).first()
        buyer = db.query(User).filter(User.id == requirement.buyer_id).first()
        job = db.query(DispatchJob).filter(DispatchJob.harvest_pickup_request_id == pickup.id).first()
        rows.append(ComplianceReportRow(
            farmer_name=farmer.full_name if farmer else "Unknown",
            crop=requirement.crop,
            buyer_name=(buyer.organisation_name or buyer.full_name) if buyer else "Unknown",
            grade=GRADE_LABELS.get(intake.grade, intake.grade.value),
            volume_kg=intake.weigh_in_kg,
            delivery_date=job.delivered_at if job else None,
        ))
    rows.sort(key=lambda r: r.delivery_date or datetime.min, reverse=True)
    return rows


def _fmt_date(d: Optional[datetime]) -> str:
    return d.strftime("%Y-%m-%d") if d else "—"


# The four confirmed MoFA fields (PRD Section 1.1/9/IA Section 1), in the
# confirmed order -- both exports stick to exactly these, deliberately not
# padded with the extra internal-reference columns the in-app view shows
# (farmer, crop), since this file is the one handed to MoFA.
EXPORT_HEADER = ["Volume (kg)", "Quality Grade", "Buyer", "Delivery Date"]


def _export_row(row: ComplianceReportRow) -> list:
    return [f"{row.volume_kg:.1f}", row.grade, row.buyer_name, _fmt_date(row.delivery_date)]


def to_csv_bytes(rows: List[ComplianceReportRow]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(EXPORT_HEADER)
    for row in rows:
        writer.writerow(_export_row(row))
    return buf.getvalue().encode("utf-8")


def to_pdf_bytes(rows: List[ComplianceReportRow]) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm,
    )
    styles = getSampleStyleSheet()
    elements = [
        Paragraph("Farm Master — MoFA Compliance Report", styles["Title"]),
        Paragraph(
            "Generic export (PRD Section 1.1/9) — template is a placeholder pending an "
            "actual MoFA data standard.",
            styles["Normal"],
        ),
        Spacer(1, 0.5 * cm),
    ]
    table_data = [EXPORT_HEADER] + [_export_row(r) for r in rows]
    table = Table(table_data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F5E3D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDE3D9")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F8F4")]),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (0, -1), "RIGHT"),
    ]))
    elements.append(table)
    doc.build(elements)
    return buf.getvalue()
