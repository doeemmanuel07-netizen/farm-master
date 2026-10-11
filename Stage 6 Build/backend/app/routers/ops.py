"""
Internal Operations additions for the CEO platform demo (brief §7): the
commitment-fee payments list, and (later in this pass) the agronomist task
queue and marketplace dispatch. Read access follows the existing money
segregation: Finance and Super Admin see payments, and Compliance Officer
gets the same read-only view it already has of reconciliation.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..auth import require_roles
from ..database import get_db
from ..models import BuyerRequirement, CommitmentFeePayment, PaymentStatus, Role, User
from ..payments.service import NETWORK_LABEL
from ..schemas import OpsPaymentRow

router = APIRouter(prefix="/ops", tags=["internal operations"])


@router.get("/payments", response_model=List[OpsPaymentRow])
def list_payments(
    status: Optional[PaymentStatus] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FINANCE, Role.SUPER_ADMIN, Role.COMPLIANCE_OFFICER)),
):
    q = db.query(CommitmentFeePayment)
    if status is not None:
        q = q.filter(CommitmentFeePayment.status == status)
    rows = []
    for p in q.order_by(CommitmentFeePayment.created_at.desc()).limit(500).all():
        req = db.query(BuyerRequirement).filter(BuyerRequirement.id == p.requirement_id).first()
        buyer = req.buyer if req else None
        rows.append(OpsPaymentRow(
            id=p.id, requirement_id=p.requirement_id, requirement_reference=req.reference if req else None,
            buyer_name=(buyer.organisation_name or buyer.full_name) if buyer else "(unknown)",
            amount=p.amount, network_label=NETWORK_LABEL.get(p.network, p.method), provider=p.provider,
            provider_ref=p.provider_ref or p.transaction_ref, status=p.status, failure_reason=p.failure_reason,
            created_at=p.created_at, paid_at=p.paid_at,
        ))
    return rows
