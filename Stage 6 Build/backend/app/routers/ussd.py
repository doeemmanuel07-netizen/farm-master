"""
USSD/SMS channel -- Stage 3 wireframe (ussd_sms_flow_wireframe.html), the
feature-phone fallback for a Farmer with no smartphone (PRD Section 8: "the
responsive web app plus USSD/SMS fallback is the full Phase 1 channel
strategy"). Added 8 Sep 2026, closing a gap this session's own completeness
audit surfaced: this wireframe had no Stage 4 visual and zero Stage 6 build
at all -- not merely unfinished, entirely absent.

Real USSD/SMS gateways authenticate by phone number + a short PIN, not a web
session -- building a second, parallel PIN-auth system for a pilot channel
whose real gateway is itself unchosen (PRD Section 1.1/12, same open
decision as the OTP/payment gateways) would be a fake integration on top of
a fake integration. Instead, this reuses the same JWT session as the rest of
the app: the frontend's USSD *session emulator* runs after the farmer's
normal web login, and every action below reads or writes the exact same
real tables the Farmer Portal does -- create_pickup_via_ussd calls
farmer.py's own request_harvest_pickup directly rather than reimplementing
it, so a pickup made through USSD is indistinguishable in the database from
one made through the web (PRD Must-Have #4 either way).

Delivery is SIMULATED, the same treatment as OtpChallenge and mobile money:
each SMS/USSD push's real, computed body is logged to UssdSmsLog so "the
farmer was notified" is an assertable fact (GET /ussd/sms-log), not merely
something the frontend displays and no one can verify happened.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Role, Opportunity, OpportunityStatus, UssdSmsLog
from ..auth import require_roles
from ..wallet import compute_farmer_wallet
from .farmer import request_harvest_pickup
from ..schemas import (
    UssdOpportunityAlert, UssdPickupConfirmRequest, UssdPaymentNotification,
    UssdSmsLogEntry, HarvestPickupRequestCreate, HarvestPickupRequestResponse,
)

router = APIRouter(prefix="/ussd", tags=["ussd"])


def _log_sms(db: Session, farmer_id: str, purpose: str, body: str, channel: str = "sms") -> UssdSmsLog:
    entry = UssdSmsLog(farmer_id=farmer_id, channel=channel, purpose=purpose, body=body)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.post("/opportunities/{opportunity_id}/push-alert", response_model=UssdOpportunityAlert)
def push_opportunity_alert(
    opportunity_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FARMER)),
):
    """PRD Touchpoint 1 -- 'Opportunity Alert'. Mirrors the Farmer Portal's Opportunity Board for a feature-phone farmer."""
    opp = db.query(Opportunity).filter(Opportunity.id == opportunity_id, Opportunity.status == OpportunityStatus.OPEN).first()
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found or no longer open.")

    sms_text = (
        f"Farm Master: New order from {opp.buyer_name} -- {opp.quantity_tonnes}t {opp.grade} maize, "
        f"GHS {opp.price_per_tonne}/t. Dial *920# to view and accept."
    )
    ussd_detail_text = (
        f"{opp.buyer_name}\n{opp.grade} - {opp.quantity_tonnes}t\nGHS {opp.price_per_tonne}/tonne\n"
        f"Deadline: {opp.deadline}\n1. Accept  0. Back"
    )
    _log_sms(db, user.id, "opportunity_alert", sms_text)
    return UssdOpportunityAlert(opportunity_id=opp.id, sms_text=sms_text, ussd_detail_text=ussd_detail_text)


@router.post("/pickup-confirm", response_model=HarvestPickupRequestResponse)
def confirm_pickup_via_ussd(
    payload: UssdPickupConfirmRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FARMER)),
):
    """PRD Touchpoint 2 -- 'Harvest Pickup Confirmation'. Reuses farmer.py's real creation logic (see module docstring)."""
    create_payload = HarvestPickupRequestCreate(
        quantity_ready_tonnes=payload.quantity_ready_tonnes,
        preferred_pickup_date=payload.preferred_pickup_date,
        buyer_requirement_id=payload.buyer_requirement_id,
    )
    result = request_harvest_pickup(create_payload, db, user)
    sms_text = (
        f"Farm Master: Pickup confirmed for {payload.quantity_ready_tonnes}t on {payload.preferred_pickup_date}. "
        f"A rider will contact you. Reply 1 for status."
    )
    _log_sms(db, user.id, "pickup_confirmation", sms_text)
    return result


@router.get("/payment-notification", response_model=UssdPaymentNotification)
def payment_notification(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FARMER)),
):
    """PRD Touchpoint 3 -- 'Payment Notification' + optional USSD balance check, mirroring the Wallet & Settlement screen."""
    rows = compute_farmer_wallet(db, user.id)
    net_due = round(sum(r.own_settlement_due for r in rows) - sum(r.input_order_costs for r in rows), 2)
    sms_text = f"Farm Master: Your net settlement balance is GHS {net_due:.2f} across {len(rows)} order(s). Dial *920# for details."
    balance_text = "\n".join(f"{r.buyer_name}: GHS {r.own_settlement_due - r.input_order_costs:.2f}" for r in rows) or "No settled orders yet."
    _log_sms(db, user.id, "payment_notification", sms_text)
    return UssdPaymentNotification(sms_text=sms_text, balance_text=balance_text)


@router.get("/sms-log", response_model=List[UssdSmsLogEntry])
def my_sms_log(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FARMER)),
):
    """Asserts what was actually 'sent' -- see module docstring."""
    logs = db.query(UssdSmsLog).filter(UssdSmsLog.farmer_id == user.id).order_by(UssdSmsLog.created_at.desc()).all()
    return [UssdSmsLogEntry(id=l.id, channel=l.channel, purpose=l.purpose, body=l.body, created_at=l.created_at) for l in logs]
