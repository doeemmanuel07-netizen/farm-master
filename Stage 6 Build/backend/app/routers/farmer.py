"""
Farmer opportunity-acceptance + production-formula flow -- the real backend
behind farmer_opportunity_formula_flow_live.html -- plus Harvest Pickup
Request and (added 7 Sep 2026) Order Inputs, the real backend behind
farmer_order_inputs_flow_live.html (PRD Section 6 Must-Have #3's literal
scope: a Farmer buying seed/fertiliser from a Vendor's Product Catalogue).

Closes a gap flagged during the Stage 5 retrospective: the USSD/SMS design
noted "whichever channel accepts first wins" for opportunity acceptance but
the interactive prototype couldn't actually enforce it (single-user, no
server). This backend does -- see accept_opportunity's status check, which
is a real 409 for a second acceptance attempt, not just a documented intent.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    User, Role, Opportunity, OpportunityStatus, ProductionFormula, HarvestPickupRequest, DispatchJob,
    DispatchJobStatus, Product, InputOrder, InputOrderLine, InputOrderStatus,
    MilestoneLogEntry, AgronomistMessage, FulfilmentIntake, GradeResult,
)
from ..auth import require_roles
from ..formula import compute_formula_inputs
from ..dispatch import create_inbound_dispatch_job
from ..catalogue import product_view, order_view
from ..wallet import compute_farmer_wallet
from ..schemas import (
    OpportunityResponse, AcceptOpportunityRequest, ProductionFormulaResponse,
    HarvestPickupRequestCreate, HarvestPickupRequestResponse, FarmerOrderOption,
    ProductResponse, InputOrderCreate, InputOrderResponse,
    MilestoneLogEntryCreate, MilestoneLogEntryResponse,
    AgronomistMessageCreate, AgronomistMessageResponse,
    FarmerWalletResponse, FarmerDashboardResponse,
)

router = APIRouter(prefix="/farmer", tags=["farmer"])


@router.get("/opportunities", response_model=List[OpportunityResponse])
def list_opportunities(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FARMER)),
):
    return db.query(Opportunity).filter(Opportunity.status == OpportunityStatus.OPEN).all()


@router.get("/opportunities/{opportunity_id}", response_model=OpportunityResponse)
def get_opportunity(
    opportunity_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FARMER)),
):
    opp = db.query(Opportunity).filter(Opportunity.id == opportunity_id).first()
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found.")
    return opp


@router.post("/opportunities/{opportunity_id}/accept", response_model=ProductionFormulaResponse)
def accept_opportunity(
    opportunity_id: str,
    payload: AcceptOpportunityRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FARMER)),
):
    if not payload.commitments_confirmed:
        raise HTTPException(status_code=422, detail="All commitment items must be confirmed before accepting.")

    opp = db.query(Opportunity).filter(Opportunity.id == opportunity_id).first()
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found.")
    if opp.status != OpportunityStatus.OPEN:
        # This is the real enforcement of "whichever channel accepts first wins"
        # flagged as untested in the Stage 5 retrospective -- a second farmer
        # (or the same farmer via a second tab/channel) genuinely cannot accept
        # an opportunity that's already gone.
        raise HTTPException(status_code=409, detail="This opportunity has already been accepted.")

    opp.status = OpportunityStatus.ACCEPTED
    opp.accepted_by = user.id
    from datetime import datetime
    opp.accepted_at = datetime.utcnow()

    inputs = compute_formula_inputs(db, opp.quantity_tonnes)
    formula = ProductionFormula(
        opportunity_id=opp.id,
        farmer_id=user.id,
        seed_kg=inputs.seed_kg,
        npk_bags=inputs.npk_bags,
        topdress_bags=inputs.topdress_bags,
    )
    db.add(formula)
    db.commit()
    db.refresh(formula)
    return formula


@router.get("/formulas/mine", response_model=List[ProductionFormulaResponse])
def my_formulas(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FARMER)),
):
    return db.query(ProductionFormula).filter(ProductionFormula.farmer_id == user.id).order_by(ProductionFormula.created_at.desc()).all()


def _pickup_view(req: HarvestPickupRequest, db: Session) -> HarvestPickupRequestResponse:
    job = db.query(DispatchJob).filter(DispatchJob.harvest_pickup_request_id == req.id).first()
    return HarvestPickupRequestResponse(
        id=req.id,
        quantity_ready_tonnes=req.quantity_ready_tonnes,
        preferred_pickup_date=req.preferred_pickup_date,
        buyer_requirement_id=req.buyer_requirement_id,
        dispatch_status=job.status,
        created_at=req.created_at,
    )


@router.get("/harvest-pickup/my-orders", response_model=List[FarmerOrderOption])
def my_order_options(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FARMER)),
):
    """
    The caller's own accepted, order-backed opportunities -- eligible
    targets for HarvestPickupRequestCreate.buyer_requirement_id (PRD Must-
    Have #5). Opportunities from the seeded open pool (no
    buyer_requirement_id) are excluded: there's no real order to reconcile
    against.
    """
    opps = (
        db.query(Opportunity)
        .filter(Opportunity.accepted_by == user.id, Opportunity.buyer_requirement_id.isnot(None))
        .all()
    )
    return [
        FarmerOrderOption(
            buyer_requirement_id=opp.buyer_requirement_id,
            buyer_name=opp.buyer_name,
            grade=opp.grade,
            quantity_tonnes=opp.quantity_tonnes,
            price_per_tonne=opp.price_per_tonne,
        )
        for opp in opps
    ]


@router.post("/harvest-pickup", response_model=HarvestPickupRequestResponse)
def request_harvest_pickup(
    payload: HarvestPickupRequestCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FARMER)),
):
    """
    PRD Section 6 Must-Have #4. Unlike a vendor mechanisation request,
    there's no confirmation step -- nobody needs to "accept" a farmer's own
    harvest being ready, so this creates the real DispatchJob immediately
    (Stage 3 wireframe: "Once confirmed, this pickup appears on the
    Logistics dispatch board").

    buyer_requirement_id, if given, must be one of the caller's own
    accepted opportunities for that order (PRD Must-Have #5) -- a farmer
    can't claim a delivery against an order they never accepted.
    """
    if payload.buyer_requirement_id:
        owns_it = (
            db.query(Opportunity)
            .filter(
                Opportunity.accepted_by == user.id,
                Opportunity.buyer_requirement_id == payload.buyer_requirement_id,
            )
            .first()
        )
        if not owns_it:
            raise HTTPException(status_code=422, detail="That order isn't one of your accepted opportunities.")

    req = HarvestPickupRequest(
        farmer_id=user.id,
        quantity_ready_tonnes=payload.quantity_ready_tonnes,
        preferred_pickup_date=payload.preferred_pickup_date,
        buyer_requirement_id=payload.buyer_requirement_id,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    create_inbound_dispatch_job(db, req)
    return _pickup_view(req, db)


@router.get("/harvest-pickup/mine", response_model=List[HarvestPickupRequestResponse])
def my_harvest_pickups(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FARMER)),
):
    reqs = db.query(HarvestPickupRequest).filter(HarvestPickupRequest.farmer_id == user.id).order_by(HarvestPickupRequest.created_at.desc()).all()
    return [_pickup_view(r, db) for r in reqs]


# ---------------------------------------------------------------------------
# Order Inputs -- PRD Section 6 Must-Have #3's literal scope ("Vendor input
# ordering routed to logistics dispatch": a Farmer buying seed/fertiliser
# from a Vendor's Product Catalogue). See models.Product / models.InputOrder.
# ---------------------------------------------------------------------------


@router.get("/catalogue", response_model=List[ProductResponse])
def browse_catalogue(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FARMER)),
):
    products = db.query(Product).all()
    views = []
    for p in products:
        vendor = db.query(User).filter(User.id == p.vendor_id).first()
        views.append(product_view(p, vendor.organisation_name or vendor.full_name))
    return views


@router.post("/input-orders", response_model=InputOrderResponse)
def place_input_order(
    payload: InputOrderCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FARMER)),
):
    if not payload.lines:
        raise HTTPException(status_code=422, detail="An input order needs at least one line item.")

    if payload.production_formula_id:
        formula = (
            db.query(ProductionFormula)
            .filter(ProductionFormula.id == payload.production_formula_id, ProductionFormula.farmer_id == user.id)
            .first()
        )
        if not formula:
            raise HTTPException(status_code=422, detail="That production formula isn't one of your own.")

    products_by_id = {}
    total_cost = 0.0
    for line in payload.lines:
        if line.quantity <= 0:
            raise HTTPException(status_code=422, detail="Every line's quantity must be greater than zero.")
        product = db.query(Product).filter(Product.id == line.product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"Product {line.product_id} not found.")
        if product.vendor_id != payload.vendor_id:
            raise HTTPException(status_code=422, detail="All line items must belong to the same vendor as vendor_id.")
        if line.quantity > product.stock_qty:
            raise HTTPException(status_code=409, detail=f"'{product.name}' only has {product.stock_qty} {product.unit} in stock.")
        products_by_id[line.product_id] = product
        total_cost += line.quantity * product.unit_price

    order = InputOrder(
        farmer_id=user.id,
        vendor_id=payload.vendor_id,
        production_formula_id=payload.production_formula_id,
        total_cost=round(total_cost, 2),
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    for line in payload.lines:
        product = products_by_id[line.product_id]
        db.add(InputOrderLine(
            input_order_id=order.id, product_id=product.id,
            quantity=line.quantity, unit_price=product.unit_price,
        ))
        # Reserve the stock immediately -- restored if the vendor later
        # declines (routers/vendor.py's decline_input_order).
        product.stock_qty -= line.quantity
    db.commit()

    return order_view(order, db)


@router.get("/input-orders/mine", response_model=List[InputOrderResponse])
def my_input_orders(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FARMER)),
):
    orders = (
        db.query(InputOrder)
        .filter(InputOrder.farmer_id == user.id)
        .order_by(InputOrder.created_at.desc())
        .all()
    )
    return [order_view(o, db) for o in orders]


# ---------------------------------------------------------------------------
# Milestone Log, Agronomist Messaging, Wallet & Settlement, Dashboard --
# added 8 Sep 2026, closing gaps this session's own completeness audit
# surfaced (Stage 3 wireframe screens in scope from day one, never built).
# ---------------------------------------------------------------------------


@router.get("/milestones", response_model=List[MilestoneLogEntryResponse])
def list_milestones(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FARMER)),
):
    entries = (
        db.query(MilestoneLogEntry)
        .filter(MilestoneLogEntry.farmer_id == user.id)
        .order_by(MilestoneLogEntry.logged_at.desc())
        .all()
    )
    return entries


@router.post("/milestones", response_model=MilestoneLogEntryResponse)
def add_milestone(
    payload: MilestoneLogEntryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FARMER)),
):
    if not payload.title.strip():
        raise HTTPException(status_code=422, detail="A milestone needs a title.")
    if payload.opportunity_id:
        owns_it = (
            db.query(Opportunity)
            .filter(Opportunity.id == payload.opportunity_id, Opportunity.accepted_by == user.id)
            .first()
        )
        if not owns_it:
            raise HTTPException(status_code=422, detail="That opportunity isn't one of your own.")
    entry = MilestoneLogEntry(
        farmer_id=user.id, opportunity_id=payload.opportunity_id, title=payload.title, note=payload.note,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/messages", response_model=List[AgronomistMessageResponse])
def my_messages(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FARMER)),
):
    msgs = (
        db.query(AgronomistMessage)
        .filter(AgronomistMessage.farmer_id == user.id)
        .order_by(AgronomistMessage.created_at.asc())
        .all()
    )
    views = []
    for m in msgs:
        sender = db.query(User).filter(User.id == m.sender_id).first()
        views.append(AgronomistMessageResponse(
            id=m.id, sender_name=sender.full_name if sender else "Unknown",
            sender_role=sender.role if sender else Role.FARMER, body=m.body, created_at=m.created_at,
        ))
    return views


@router.post("/messages", response_model=AgronomistMessageResponse)
def send_message(
    payload: AgronomistMessageCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FARMER)),
):
    if not payload.body.strip():
        raise HTTPException(status_code=422, detail="Message body cannot be empty.")
    msg = AgronomistMessage(farmer_id=user.id, sender_id=user.id, body=payload.body)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return AgronomistMessageResponse(
        id=msg.id, sender_name=user.full_name, sender_role=user.role, body=msg.body, created_at=msg.created_at,
    )


@router.get("/wallet", response_model=FarmerWalletResponse)
def my_wallet(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FARMER)),
):
    rows = compute_farmer_wallet(db, user.id)
    total_settlement = round(sum(r.own_settlement_due for r in rows), 2)
    total_costs = round(sum(r.input_order_costs for r in rows), 2)
    return FarmerWalletResponse(
        rows=[
            dict(
                buyer_requirement_id=r.buyer_requirement_id, buyer_name=r.buyer_name,
                own_delivered_tonnes=r.own_delivered_tonnes, own_settlement_due=r.own_settlement_due,
                input_order_costs=r.input_order_costs,
            ) for r in rows
        ],
        total_settlement_due=total_settlement,
        total_input_order_costs=total_costs,
        net_due=round(total_settlement - total_costs, 2),
    )


@router.get("/dashboard", response_model=FarmerDashboardResponse)
def my_dashboard(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FARMER)),
):
    open_count = db.query(Opportunity).filter(Opportunity.status == OpportunityStatus.OPEN).count()
    accepted_count = db.query(Opportunity).filter(Opportunity.accepted_by == user.id).count()
    pending_pickups = (
        db.query(HarvestPickupRequest)
        .join(DispatchJob, DispatchJob.harvest_pickup_request_id == HarvestPickupRequest.id)
        .filter(HarvestPickupRequest.farmer_id == user.id, DispatchJob.status != DispatchJobStatus.DELIVERED)
        .count()
    )
    last_msg = (
        db.query(AgronomistMessage)
        .filter(AgronomistMessage.farmer_id == user.id, AgronomistMessage.sender_id != user.id)
        .order_by(AgronomistMessage.created_at.desc())
        .first()
    )
    return FarmerDashboardResponse(
        open_opportunities=open_count, accepted_opportunities=accepted_count,
        pending_pickups=pending_pickups,
        unread_message_note=f"New reply from Farm Master agronomy" if last_msg else None,
    )
