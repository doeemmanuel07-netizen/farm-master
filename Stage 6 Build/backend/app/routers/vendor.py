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
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    User, Role, RateConfig, MechanisationRequest, MechanisationRequestStatus,
    Product, InputOrder, InputOrderLine, InputOrderStatus,
)
from ..auth import require_roles
from ..dispatch import create_dispatch_job, create_input_order_dispatch_job
from ..catalogue import product_view, order_view
from ..schemas import (
    MechanisationRequestResponse, ConfirmRequestBody, ProductCreate, ProductResponse,
    InputOrderResponse,
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
