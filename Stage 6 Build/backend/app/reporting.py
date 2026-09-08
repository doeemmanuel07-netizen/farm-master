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

from .models import (
    FulfilmentIntake, HarvestPickupRequest, BuyerRequirement, User, DispatchJob, GradeResult,
    Role, UserStatus, RateConfig, CommitmentFeePayment, PaymentStatus,
    VendorBilling,
)

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


# ---------------------------------------------------------------------------
# Reporting dashboard -- Stage 3 wireframe "Reporting" screen (PRD Section 7:
# the six revenue streams as Phase 1 success metrics, alongside pilot
# operating metrics). Added 8 Sep 2026, closing a gap this session's own
# completeness audit surfaced -- distinct from the MoFA compliance export
# above. Every live figure is computed from real data; the three
# Phase-2/Phase-4-deferred streams (PRD Section 6/8) are shown disabled with
# their deferred phase, not fabricated numbers.
# ---------------------------------------------------------------------------

from sqlalchemy.orm import Session as _Session  # local alias, avoids shadowing above


def get_reporting_dashboard(db: _Session):
    from .schemas import RevenueStreamStat, ReportingDashboardResponse  # avoid import cycle

    def _rate(key: str, default: float) -> float:
        row = db.query(RateConfig).filter(RateConfig.key == key).first()
        return row.value if row else default

    # Aggregation & trade margin, and logistics support fees, are both real
    # per-order figures (reconciliation.py) -- summed here across every
    # order that has at least one graded, non-REJECT delivery (the same
    # scope reconciliation.py itself uses per order).
    from .reconciliation import compute_figures
    reqs = db.query(BuyerRequirement).all()
    trade_margin_total = 0.0
    for req in reqs:
        figures = compute_figures(db, req)
        if figures.accepted_delivered_tonnes > 0:
            trade_margin_total += figures.trading_margin_amount

    delivered_jobs = db.query(DispatchJob).filter(DispatchJob.delivered_at.isnot(None)).count()
    logistics_fee_rate = _rate("logistics_fee_per_delivery", 30.0)
    logistics_fees_total = round(delivered_jobs * logistics_fee_rate, 2)

    vendor_storefronts_billable = db.query(VendorBilling).filter(VendorBilling.status == "active").count()

    revenue_streams = [
        RevenueStreamStat(label="Aggregation & trade margin", value=f"GHS {trade_margin_total:.0f}"),
        RevenueStreamStat(label="Logistics support fees", value=f"GHS {logistics_fees_total:.0f}"),
        RevenueStreamStat(label="Mechanisation support", deferred_phase="Phase 2"),
        RevenueStreamStat(label="Vendor storefront billable (FM-owned)", value=str(vendor_storefronts_billable)),
        RevenueStreamStat(label="Company-owned production", deferred_phase="Phase 4"),
        RevenueStreamStat(label="Consultation services", deferred_phase="Phase 2+"),
    ]

    registered_farmers = db.query(User).filter(User.role == Role.FARMER, User.status == UserStatus.ACTIVE).count()
    active_buyers = db.query(User).filter(User.role == Role.BUYER, User.status == UserStatus.ACTIVE).count()

    all_intakes = db.query(FulfilmentIntake).all()
    volume_tonnes = sum(i.weigh_in_kg for i in all_intakes if i.grade != GradeResult.REJECT) / 1000.0
    compliance_rate = (
        round(100.0 * sum(1 for i in all_intakes if i.grade != GradeResult.REJECT) / len(all_intakes), 1)
        if all_intakes else None
    )

    return ReportingDashboardResponse(
        revenue_streams=revenue_streams,
        registered_farmers=registered_farmers,
        active_buyers=active_buyers,
        volume_aggregated_tonnes=round(volume_tonnes, 3),
        spec_compliance_rate_pct=compliance_rate,
    )
