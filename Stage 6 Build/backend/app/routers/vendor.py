"""
Vendor mechanisation request flow -- the real backend behind
vendor_mechanisation_request_flow_live.html -- plus (added 7 Sep 2026)
the Vendor side of the Product Catalogue + Input Orders, the real backend
behind vendor_product_catalogue_flow_live.html (PRD Section 6 Must-Have
#3's literal scope).

Unlike Opportunity (a shared pool any farmer can accept), a
MechanisationRequest is already directed at a specific vendor, so every
route here scopes to request.vendor_id == caller.id, the same "own only"
pattern as buyer.py's requirements -- InputOrder below follows the same
scoping.

The date-conflict override (Emmanuel's decision, 3 Sep 2026) is a real
two-party workflow: confirming a date past requested_by_date does not
finalise anything here -- it sets override_needed and stores the proposal.
Only Super Admin (routers/admin.py) can finalise it. This is stricter than
the Stage 5 prototype, which simulated approval within one session.
"""

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    User, Role, RateConfig, MechanisationRequest, MechanisationRequestStatus,
    Product, InputOrder, InputOrderLine, InputOrderStatus, DispatchJob, DispatchJobStatus,
    VendorBilling, VendorBillingPayment, ProofOfDelivery,
)
from ..auth import require_roles
from ..audit import log_audit
from ..dispatch import create_dispatch_job, create_input_order_dispatch_job
from ..catalogue import product_view, order_view
from ..payout import compute_vendor_payout_rows
from ..schemas import (
    MechanisationRequestResponse, ConfirmRequestBody, ProductCreate, ProductResponse,
    InputOrderResponse, VendorDashboardResponse, VendorBillingResponse, VendorBillingPayRequest,
    PaymentResponse, VendorPayoutRow, VendorHandoffRow,
)

router = APIRouter(prefix="/vendor", tags=["vendor"])


def _get_rate(db: Session, key: str) -> float:
    row = db.query(RateConfig).filter(RateConfig.key == key).first()
    if not row:
        raise HTTPException(status_code=500, detail=f"Rate config '{key}' is not seeded.")
    return row.value


def _with_quote(db: Session, req: MechanisationRequest) -> MechanisationRequest:
    # Suggested quote is computed on read, not stored, so a rate_config
    # change (via PUT /admin/rates/{key}) is reflected immediately.
    rate = _get_rate(db, "vendor_service_fee_per_tonne")
    req.suggested_quote = round(req.area_acres * rate, 2)
    return req


def _own_request(db: Session, request_id: str, user: User) -> MechanisationRequest:
    req = db.query(MechanisationRequest).filter(MechanisationRequest.id == request_id).first()
    if not req or req.vendor_id != user.id:
        raise HTTPException(status_code=404, detail="Request not found.")
    return req


@router.get("/requests", response_model=list[MechanisationRequestResponse])
def list_requests(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.VENDOR)),
):
    reqs = db.query(MechanisationRequest).filter(MechanisationRequest.vendor_id == user.id).all()
    return [_with_quote(db, r) for r in reqs]


@router.get("/requests/{request_id}", response_model=MechanisationRequestResponse)
def get_request(
    request_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.VENDOR)),
):
    return _with_quote(db, _own_request(db, request_id, user))


@router.post("/requests/{request_id}/confirm", response_model=MechanisationRequestResponse)
def confirm_request(
    request_id: str,
    payload: ConfirmRequestBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.VENDOR)),
):
    req = _own_request(db, request_id, user)
    if req.status != MechanisationRequestStatus.PENDING:
        raise HTTPException(status_code=409, detail=f"Request is '{req.status.value}', not confirmable.")

    try:
        confirmed = datetime.strptime(payload.confirmed_date, "%Y-%m-%d").date()
        window_end = datetime.strptime(req.requested_by_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=422, detail="confirmed_date must be an ISO date, e.g. 2026-09-20.")

    if confirmed > window_end:
        # Outside the farmer's requested window: store the proposal, do NOT
        # finalise. The vendor cannot self-approve this -- only Super Admin
        # can, via POST /admin/vendor-requests/{id}/approve-override.
        req.override_needed = True
        req.proposed_date = payload.confirmed_date
        req.proposed_notes = payload.notes
        db.commit()
        db.refresh(req)
        return _with_quote(db, req)

    req.confirmed_date = payload.confirmed_date
    req.notes = payload.notes
    req.status = MechanisationRequestStatus.CONFIRMED
    req.override_needed = False
    db.commit()
    db.refresh(req)
    create_dispatch_job(db, req)
    return _with_quote(db, req)


@router.post("/requests/{request_id}/decline", response_model=MechanisationRequestResponse)
def decline_request(
    request_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.VENDOR)),
):
    req = _own_request(db, request_id, user)
    if req.status != MechanisationRequestStatus.PENDING:
        raise HTTPException(status_code=409, detail=f"Request is '{req.status.value}', not declinable.")
    req.status = MechanisationRequestStatus.DECLINED
    db.commit()
    db.refresh(req)
    return _with_quote(db, req)


# ---------------------------------------------------------------------------
# Product Catalogue + Input Orders -- PRD Section 6 Must-Have #3's literal
# scope ("Vendor input ordering routed to logistics dispatch": a Farmer
# buying seed/fertiliser from a Vendor's Product Catalogue). See
# models.Product / models.InputOrder for the full design rationale.
# ---------------------------------------------------------------------------


@router.get("/catalogue", response_model=List[ProductResponse])
def list_own_catalogue(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.VENDOR)),
):
    products = db.query(Product).filter(Product.vendor_id == user.id).all()
    vendor_name = user.organisation_name or user.full_name
    return [product_view(p, vendor_name) for p in products]


@router.post("/catalogue", response_model=ProductResponse)
def add_catalogue_item(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.VENDOR)),
):
    if payload.unit_price <= 0 or payload.stock_qty < 0:
        raise HTTPException(status_code=422, detail="unit_price must be positive and stock_qty cannot be negative.")
    product = Product(
        vendor_id=user.id, name=payload.name, category=payload.category,
        formula_input_type=payload.formula_input_type, unit=payload.unit,
        unit_price=payload.unit_price, stock_qty=payload.stock_qty,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product_view(product, user.organisation_name or user.full_name)


@router.get("/input-orders", response_model=List[InputOrderResponse])
def list_input_orders(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.VENDOR)),
):
    orders = (
        db.query(InputOrder)
        .filter(InputOrder.vendor_id == user.id)
        .order_by(InputOrder.created_at.desc())
        .all()
    )
    return [order_view(o, db) for o in orders]


def _own_input_order(db: Session, order_id: str, user: User) -> InputOrder:
    order = db.query(InputOrder).filter(InputOrder.id == order_id).first()
    if not order or order.vendor_id != user.id:
        raise HTTPException(status_code=404, detail="Input order not found.")
    return order


@router.post("/input-orders/{order_id}/confirm", response_model=InputOrderResponse)
def confirm_input_order(
    order_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.VENDOR)),
):
    order = _own_input_order(db, order_id, user)
    if order.status != InputOrderStatus.PENDING:
        raise HTTPException(status_code=409, detail=f"Order is '{order.status.value}', not confirmable.")
    order.status = InputOrderStatus.CONFIRMED
    db.commit()
    db.refresh(order)
    create_input_order_dispatch_job(db, order)
    return order_view(order, db)


@router.post("/input-orders/{order_id}/decline", response_model=InputOrderResponse)
def decline_input_order(
    order_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.VENDOR)),
):
    order = _own_input_order(db, order_id, user)
    if order.status != InputOrderStatus.PENDING:
        raise HTTPException(status_code=409, detail=f"Order is '{order.status.value}', not declinable.")
    order.status = InputOrderStatus.DECLINED
    # Restore the reservation made at order time -- see farmer.py's
    # place_input_order, which decrements stock_qty on creation.
    lines = db.query(InputOrderLine).filter(InputOrderLine.input_order_id == order.id).all()
    for line in lines:
        product = db.query(Product).filter(Product.id == line.product_id).first()
        if product:
            product.stock_qty += line.quantity
    db.commit()
    db.refresh(order)
    return order_view(order, db)


# ---------------------------------------------------------------------------
# Vendor Dashboard, Subscription & Billing, Payout Statement, Handoff Status
# -- added 8 Sep 2026, closing gaps this session's own completeness audit
# surfaced (Stage 3 wireframe screens in scope from day one, never built).
# ---------------------------------------------------------------------------


@router.get("/dashboard", response_model=VendorDashboardResponse)
def vendor_dashboard(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.VENDOR)),
):
    pending_mech = (
        db.query(MechanisationRequest)
        .filter(MechanisationRequest.vendor_id == user.id, MechanisationRequest.status == MechanisationRequestStatus.PENDING)
        .count()
    )
    pending_orders = (
        db.query(InputOrder)
        .filter(InputOrder.vendor_id == user.id, InputOrder.status == InputOrderStatus.PENDING)
        .count()
    )
    catalogue = db.query(Product).filter(Product.vendor_id == user.id).all()
    return VendorDashboardResponse(
        pending_mechanisation_requests=pending_mech,
        pending_input_orders=pending_orders,
        catalogue_item_count=len(catalogue),
        catalogue_low_stock_count=sum(1 for p in catalogue if p.stock_qty < 10),
    )


VENDOR_SUBSCRIPTION_FEE = "vendor_subscription_fee_monthly"
VALID_BILLING_METHODS = {"momo", "vodafone", "airteltigo", "card"}


def _get_or_create_billing(db: Session, user: User) -> VendorBilling:
    billing = db.query(VendorBilling).filter(VendorBilling.vendor_id == user.id).first()
    if billing:
        return billing
    fee_row = db.query(RateConfig).filter(RateConfig.key == VENDOR_SUBSCRIPTION_FEE).first()
    billing = VendorBilling(vendor_id=user.id, monthly_fee=fee_row.value if fee_row else 150.0)
    db.add(billing)
    db.commit()
    db.refresh(billing)
    return billing


@router.get("/billing", response_model=VendorBillingResponse)
def get_billing(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.VENDOR)),
):
    billing = _get_or_create_billing(db, user)
    history = (
        db.query(VendorBillingPayment)
        .filter(VendorBillingPayment.vendor_id == user.id)
        .order_by(VendorBillingPayment.created_at.desc())
        .all()
    )
    return VendorBillingResponse(
        plan=billing.plan, monthly_fee=billing.monthly_fee, status=billing.status,
        last_billed_at=billing.last_billed_at,
        history=[
            PaymentResponse(id=p.id, requirement_id="", amount=p.amount, method=p.method, status=p.status, transaction_ref=p.transaction_ref)
            for p in history
        ],
    )


@router.post("/billing/pay", response_model=VendorBillingResponse)
def pay_billing(
    payload: VendorBillingPayRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.VENDOR)),
):
    if payload.method not in VALID_BILLING_METHODS:
        raise HTTPException(status_code=422, detail=f"Unsupported payment method '{payload.method}'.")
    if payload.method == "card":
        raise HTTPException(status_code=501, detail="Card payment gateway not yet selected (Paystack/Hubtel TBD).")

    billing = _get_or_create_billing(db, user)
    payment = VendorBillingPayment(
        vendor_id=user.id, amount=billing.monthly_fee, method=payload.method,
        status="success", transaction_ref=f"SIM-{user.id[:8]}",
    )
    db.add(payment)
    billing.status = "active"
    billing.last_billed_at = datetime.utcnow()
    db.commit()

    log_audit(db, user, "vendor_subscription_paid", f"{user.organisation_name or user.full_name}: GHS {payment.amount} via {payload.method}, ref {payment.transaction_ref}.")
    return get_billing(db, user)


@router.get("/payout", response_model=List[VendorPayoutRow])
def vendor_payout(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.VENDOR)),
):
    rows = compute_vendor_payout_rows(db, user.id)
    return [
        VendorPayoutRow(
            buyer_requirement_id=r.buyer_requirement_id, buyer_name=r.buyer_name,
            mechanisation_amount=r.mechanisation_amount, input_order_amount=r.input_order_amount,
            total=r.total, released=r.released, released_at=r.released_at,
        ) for r in rows
    ]


@router.get("/handoff", response_model=List[VendorHandoffRow])
def vendor_handoff_status(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.VENDOR)),
):
    """
    Order -> Logistics Handoff Status (Stage 3 wireframe): tracks a
    confirmed vendor-sourced job (mechanisation or input order) from vendor
    confirmation through Logistics pickup to delivery confirmation.
    """
    mech_ids = [r.id for r in db.query(MechanisationRequest).filter(MechanisationRequest.vendor_id == user.id).all()]
    order_ids = [o.id for o in db.query(InputOrder).filter(InputOrder.vendor_id == user.id).all()]
    conditions = []
    if mech_ids:
        conditions.append(DispatchJob.mechanisation_request_id.in_(mech_ids))
    if order_ids:
        conditions.append(DispatchJob.input_order_id.in_(order_ids))
    jobs = (
        db.query(DispatchJob).filter(or_(*conditions)).order_by(DispatchJob.created_at.desc()).all()
        if conditions else []
    )

    rows = []
    for job in jobs:
        if job.mechanisation_request_id:
            mech = db.query(MechanisationRequest).filter(MechanisationRequest.id == job.mechanisation_request_id).first()
            description = f"{mech.service} -- {mech.farmer_name}" if mech else "Mechanisation job"
        else:
            order = db.query(InputOrder).filter(InputOrder.id == job.input_order_id).first()
            description = f"Input order -- {order.total_cost} GHS" if order else "Input order"
        proof = db.query(ProofOfDelivery).filter(ProofOfDelivery.dispatch_job_id == job.id).first()
        rows.append(VendorHandoffRow(
            dispatch_job_id=job.id, description=description, status=job.status,
            tricycle_label=job.tricycle_label, delivered_at=job.delivered_at,
            proof_captured=bool(proof),
        ))
    return rows
