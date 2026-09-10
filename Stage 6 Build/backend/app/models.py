"""
Core data model.

Covers the seven roles confirmed in PRD Section 3.2/5 (Farmer, Buyer, Vendor,
Agronomist, Logistics, Finance, Super Admin), the audit-logging requirement
(PRD Section 5, added 3 Sep 2026), the provisional rates as DB-backed
configuration (PRD Section 10) rather than hard-coded values, and the Buyer
commitment-fee flow (PRD Section 6, Must-Have #1) end to end. Farmer/Vendor
flow tables are intentionally not built out yet -- this pass scopes to
backend foundation + the Buyer flow, per the agreed Stage 6 sequencing.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Float, Integer, Boolean, DateTime, ForeignKey, Enum as SAEnum, Text
)
from sqlalchemy.orm import relationship

from .database import Base


def uid():
    return str(uuid.uuid4())


class Role(str, enum.Enum):
    FARMER = "farmer"
    BUYER = "buyer"
    VENDOR = "vendor"
    AGRONOMIST = "agronomist"
    LOGISTICS = "logistics"
    FINANCE = "finance"
    SUPER_ADMIN = "super_admin"
    # Added 9 Sep 2026: splitting Internal Ops Staff out from Super Admin so
    # real pilot staff can be onboarded into scoped roles instead of sharing
    # the one Super Admin login. Each is a genuinely narrower slice of what
    # Super Admin/Agronomist/Finance could already do, not a relabelling --
    # see routers/dashboard.py, routers/agronomist.py, routers/mofa.py and
    # routers/reconciliation.py for the exact endpoints each is granted.
    OPERATIONS_COORDINATOR = "operations_coordinator"
    COMPLIANCE_OFFICER = "compliance_officer"


# Roles permitted to perform account/role administration and registration
# approval. Deliberately excludes FINANCE -- this is the segregation-of-duties
# rule from PRD Section 5: no role that can move money can also grant
# permissions or approve accounts. Also excludes the two Internal Ops Staff
# roles below (9 Sep 2026) -- their whole point is scoped operational access
# without account/role administration.
ADMIN_ROLES = {Role.SUPER_ADMIN}

# Roles permitted to perform financial actions (fee capture, settlement/
# payout release). Deliberately excludes SUPER_ADMIN for release actions in
# the general case, though Super Admin can still view everything via the
# audit log -- visibility is not the same as authority to move money. Also
# excludes COMPLIANCE_OFFICER (9 Sep 2026): read-only reconciliation
# visibility for reporting, not authority to release money.
FINANCE_ROLES = {Role.FINANCE}

# The three portal roles that self-register (PRD Section 12) -- moved here
# (7 Sep 2026, User & Role Admin) from being a routers/auth.py-local
# constant, since routers/admin.py now needs the same classification (to
# reject creating a Farmer/Buyer/Vendor through the internal-user-creation
# endpoint, which would bypass self-registration's OTP + approval gate).
# Single source of truth rather than two copies that could drift.
SELF_REGISTER_ROLES = {Role.FARMER, Role.BUYER, Role.VENDOR}

# The roles Super-Admin-provisions directly (routers/admin.py's
# POST /admin/users) rather than self-registering -- PRD Section 3.2,
# extended 9 Sep 2026 with the two new Internal Ops Staff roles.
INTERNAL_ROLES = {
    Role.AGRONOMIST, Role.LOGISTICS, Role.FINANCE, Role.SUPER_ADMIN,
    Role.OPERATIONS_COORDINATOR, Role.COMPLIANCE_OFFICER,
}


class UserStatus(str, enum.Enum):
    # New self-registered account, phone/email not yet OTP-verified -- added
    # 5 Sep 2026 with real-time OTP verification (PRD Section 12). Precedes
    # PENDING even for Buyer/Vendor: OTP verification gates entry into the
    # existing Super-Admin Registration Approval Queue, it doesn't replace it.
    PENDING_OTP = "pending_otp_verification"
    PENDING = "pending_review"
    ACTIVE = "active"
    SUSPENDED = "suspended"


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=uid)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    role = Column(SAEnum(Role), nullable=False)
    status = Column(SAEnum(UserStatus), nullable=False, default=UserStatus.ACTIVE)
    password_hash = Column(String, nullable=False)
    organisation_name = Column(String, nullable=True)  # buyer/vendor org name, if applicable
    created_at = Column(DateTime, default=datetime.utcnow)

    requirements = relationship("BuyerRequirement", back_populates="buyer")


class RateConfig(Base):
    """
    DB-backed equivalent of the Stage 5 prototypes' inline CONFIG blocks.
    Same provisional numbers (PRD Section 10), now a one-row-update instead
    of a one-line code edit -- the next step up from "config, not code."
    """
    __tablename__ = "rate_config"

    key = Column(String, primary_key=True)
    value = Column(Float, nullable=False)
    unit = Column(String, nullable=False)
    status = Column(String, nullable=False, default="PROVISIONAL")
    note = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RequirementStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING_PAYMENT = "pending_payment"
    MATCHING = "matching"
    PRODUCTION = "production"
    AGGREGATION = "aggregation"
    SHIPMENT = "shipment"


class BuyerRequirement(Base):
    __tablename__ = "buyer_requirements"

    id = Column(String, primary_key=True, default=uid)
    buyer_id = Column(String, ForeignKey("users.id"), nullable=False)
    crop = Column(String, nullable=False, default="Maize")
    grade = Column(String, nullable=False)
    quantity_tonnes = Column(Float, nullable=False)
    price_per_tonne = Column(Float, nullable=False)
    delivery_location = Column(String, nullable=False)
    delivery_timeline = Column(String, nullable=False)
    commitment_fee_amount = Column(Float, nullable=False)
    status = Column(SAEnum(RequirementStatus), nullable=False, default=RequirementStatus.DRAFT)
    created_at = Column(DateTime, default=datetime.utcnow)

    buyer = relationship("User", back_populates="requirements")
    payments = relationship("CommitmentFeePayment", back_populates="requirement")


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class CommitmentFeePayment(Base):
    __tablename__ = "commitment_fee_payments"

    id = Column(String, primary_key=True, default=uid)
    requirement_id = Column(String, ForeignKey("buyer_requirements.id"), nullable=False)
    amount = Column(Float, nullable=False)
    method = Column(String, nullable=False)  # momo | vodafone | airteltigo | card
    status = Column(SAEnum(PaymentStatus), nullable=False, default=PaymentStatus.PENDING)
    transaction_ref = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    requirement = relationship("BuyerRequirement", back_populates="payments")


class OpportunityStatus(str, enum.Enum):
    OPEN = "open"
    ACCEPTED = "accepted"


class Opportunity(Base):
    """
    Buyer-backed opportunities available for a farmer to accept. PRD Section
    8 confirms Phase 1 matching is manual/agronomist-assisted (no automated
    matching engine), so these are seeded directly rather than derived
    automatically from a BuyerRequirement -- buyer_requirement_id is kept
    nullable for that future linkage.
    """
    __tablename__ = "opportunities"

    id = Column(String, primary_key=True, default=uid)
    buyer_requirement_id = Column(String, ForeignKey("buyer_requirements.id"), nullable=True)
    buyer_name = Column(String, nullable=False)
    tag = Column(String, nullable=False)  # e.g. "MoFA-linked", "Private buyer"
    grade = Column(String, nullable=False)
    quantity_tonnes = Column(Float, nullable=False)
    price_per_tonne = Column(Float, nullable=False)
    deadline = Column(String, nullable=False)
    status = Column(SAEnum(OpportunityStatus), nullable=False, default=OpportunityStatus.OPEN)
    # Set by agronomist.py's assign_farmers -- the farmer the Matching Queue
    # actually assigned this row to, independent of accepted_by (which stays
    # null until that farmer acts on it). Added for the Production Formula
    # Builder, which needs to name the assigned farmers before any of them
    # have accepted. Nullable because pre-Matching-Queue opportunities (the
    # seeded open pool) were never assigned to a specific farmer.
    assigned_farmer_id = Column(String, ForeignKey("users.id"), nullable=True)
    accepted_by = Column(String, ForeignKey("users.id"), nullable=True)
    accepted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ProductionFormula(Base):
    """
    Generated on acceptance. Input quantities are scaled from the accepted
    opportunity's tonnage using the same RateConfig-backed, agronomically
    UNVERIFIED formula as the Stage 5 prototype (PRD Section 10) -- now a
    server-side calculation instead of client-side JS.
    """
    __tablename__ = "production_formulas"

    id = Column(String, primary_key=True, default=uid)
    opportunity_id = Column(String, ForeignKey("opportunities.id"), nullable=False)
    farmer_id = Column(String, ForeignKey("users.id"), nullable=False)
    seed_kg = Column(Float, nullable=False)
    npk_bags = Column(Integer, nullable=False)
    topdress_bags = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class RequirementFormulaPlan(Base):
    """
    Agronomist-built production formula for an assigned buyer requirement --
    backend for the Production Formula Builder screen (IA Section 3.5, Fig. 6;
    Stage 3/4 "Production Formula Builder"). One plan per requirement
    (buyer_requirement_id is unique): every farmer assigned to that
    requirement by the Matching Queue receives an identical tonnage share by
    construction (assign_farmers splits evenly), so one planting calendar and
    one input schedule genuinely covers all of them -- this is not a
    per-farmer table collapsed for convenience, it reflects that the
    Matching Queue's split makes every assigned farmer's share equal.

    The input schedule itself is NOT stored here: it's derived on read from
    the same RateConfig-backed formula used in farmer.py's accept_opportunity
    (see formula.py), so a later rate change is reflected consistently rather
    than frozen at build time for an unpublished plan. Only the planting
    calendar (which has no other source of truth) and the publish decision
    are real editable state.
    """
    __tablename__ = "requirement_formula_plans"

    id = Column(String, primary_key=True, default=uid)
    buyer_requirement_id = Column(String, ForeignKey("buyer_requirements.id"), nullable=False, unique=True)
    land_prep_week = Column(Integer, nullable=False, default=1)
    planting_week = Column(Integer, nullable=False, default=2)
    topdress_week = Column(Integer, nullable=False, default=4)
    weeding_week = Column(Integer, nullable=False, default=6)
    harvest_week = Column(Integer, nullable=False, default=11)
    published = Column(Boolean, nullable=False, default=False)
    published_at = Column(DateTime, nullable=True)
    published_by = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MechanisationRequestStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DECLINED = "declined"


class MechanisationRequest(Base):
    """
    Vendor mechanisation service requests. Unlike Opportunity (a shared pool
    any farmer can accept), a request is already directed at a specific
    vendor -- vendor_id is set at creation, mirroring the real business
    meaning (a farmer or Farm Master routed this request to that vendor).

    The date-conflict override (added 3 Sep 2026, per Emmanuel's decision)
    is modelled as a real two-party workflow, not vendor self-approval:
    confirming a date past requested_by_date sets override_needed=true and
    stores the proposed date/notes without finalising anything; only a
    separate Super Admin-gated endpoint (admin.py) can set
    override_approved=true and finalise the confirmation. This is stricter
    than the Stage 5 prototype, which simulated the approval within the same
    single-user session for demo purposes.

    buyer_requirement_id (added for PRD Section 6 Must-Have #5, Order
    Reconciliation) optionally ties a request to the buyer order the
    farmer's vendor-arranged service was for, so a real vendor payout can be
    computed for that order. Nullable, and seed-data-only for now: there is
    still no real farmer-facing creation endpoint for a MechanisationRequest
    itself -- unlike InputOrder (below), which now has one -- so this link
    can only be set by seed.py today, not by any live flow. See README
    "Not yet built".
    """
    __tablename__ = "mechanisation_requests"

    id = Column(String, primary_key=True, default=uid)
    vendor_id = Column(String, ForeignKey("users.id"), nullable=False)
    buyer_requirement_id = Column(String, ForeignKey("buyer_requirements.id"), nullable=True)
    farmer_name = Column(String, nullable=False)
    service = Column(String, nullable=False)
    area_acres = Column(Float, nullable=False)
    requested_by_date = Column(String, nullable=False)  # ISO date, e.g. "2026-09-08"
    status = Column(SAEnum(MechanisationRequestStatus), nullable=False, default=MechanisationRequestStatus.PENDING)
    confirmed_date = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    override_needed = Column(Boolean, nullable=False, default=False)
    override_approved = Column(Boolean, nullable=False, default=False)
    override_approver_id = Column(String, ForeignKey("users.id"), nullable=True)
    proposed_date = Column(String, nullable=True)
    proposed_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ProductCategory(str, enum.Enum):
    SEED = "seed"
    FERTILISER = "fertiliser"
    CROP_PROTECTION = "crop_protection"
    TOOLS = "tools"


class FormulaInputType(str, enum.Enum):
    """
    Tags a Product as the catalogue item that fulfils one line of a
    ProductionFormula, so the Farmer Order Inputs screen can pre-fill
    quantities from the farmer's own formula (Stage 3 wireframe: "Inputs --
    pre-filled from formula") without fragile name/category string
    matching -- an explicit mapping, same style as RateConfig's explicit
    keys rather than inferring meaning from free text.
    """
    SEED = "seed"
    NPK = "npk"
    TOPDRESS = "topdress"
    OTHER = "other"


class Product(Base):
    """
    Vendor Portal's Product Catalogue (Stage 3 wireframe, PRD Section 6
    Must-Have #3's literal scope) -- seeds, fertiliser, crop-protection, and
    tools, listed by a Vendor and drawn from by the Farmer Portal's Order
    Inputs screen. One vendor's items only per row (vendor_id); the wireframe
    caption confirms this same catalogue "feeds the Farmer Portal 'Order
    Inputs' screen ... and the Buyer/Control Centre input-cost views" -- the
    Buyer/Control Centre view is Reporting scope, not built here.

    stock_qty is a real, live-adjusted quantity: placing an InputOrder
    decrements it immediately (a reservation, not just a display number),
    and declining an order restores it -- see routers/vendor.py and
    routers/farmer.py. No edit/delete endpoint exists yet, matching the
    wireframe's own scope (list + "+ Add item" only).
    """
    __tablename__ = "products"

    id = Column(String, primary_key=True, default=uid)
    vendor_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    category = Column(SAEnum(ProductCategory), nullable=False)
    formula_input_type = Column(SAEnum(FormulaInputType), nullable=False, default=FormulaInputType.OTHER)
    unit = Column(String, nullable=False)  # e.g. "kg", "bag", "litre", "set"
    unit_price = Column(Float, nullable=False)
    stock_qty = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class InputOrderStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DECLINED = "declined"


class InputOrder(Base):
    """
    Farmer Portal's Order Inputs screen (Stage 3 wireframe) -- the real,
    literal scope of PRD Section 6 Must-Have #3 ("Vendor input ordering
    routed to logistics dispatch"), as distinct from the mechanisation-
    request dispatch that already existed (Logistics Dispatch, Section 15).

    Scoped to a single vendor per order (vendor_id), mirroring
    MechanisationRequest's own single-vendor scoping -- every line's
    product must belong to that vendor (routers/farmer.py validates this).
    production_formula_id is nullable and only used to pre-fill the
    frontend's suggested quantities (PRD Section 3 wireframe: "pre-filled
    from the production formula, not a separate errand") -- it is not
    itself validated against the caller owning that formula beyond the
    normal farmer_id scoping, since ordering general inputs unlinked to any
    formula is also a valid case (matches HarvestPickupRequest's own
    optional-link precedent, Section 16).

    Same two-step lifecycle as MechanisationRequest: PENDING on creation
    (stock already decremented -- a real reservation), then the vendor
    either CONFIRMS (creates the real DispatchJob, dispatch.py) or DECLINES
    (restores the reserved stock). Unlike Fulfilment Intake grading or
    Order Reconciliation's releases, confirm/decline here are operational
    fulfilment actions, not Finance-owned financial actions (PRD Section
    5's audit scope) -- not audited, same treatment as MechanisationRequest
    confirm/decline and dispatch/deliver.
    """
    __tablename__ = "input_orders"

    id = Column(String, primary_key=True, default=uid)
    farmer_id = Column(String, ForeignKey("users.id"), nullable=False)
    vendor_id = Column(String, ForeignKey("users.id"), nullable=False)
    production_formula_id = Column(String, ForeignKey("production_formulas.id"), nullable=True)
    status = Column(SAEnum(InputOrderStatus), nullable=False, default=InputOrderStatus.PENDING)
    total_cost = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class InputOrderLine(Base):
    """
    One catalogue item within an InputOrder. unit_price is a snapshot at
    order time (same rationale as CommitmentFeePayment.amount and
    FulfilmentIntake.weigh_in_kg) -- a later catalogue price change must
    never retroactively alter an order already placed.
    """
    __tablename__ = "input_order_lines"

    id = Column(String, primary_key=True, default=uid)
    input_order_id = Column(String, ForeignKey("input_orders.id"), nullable=False)
    product_id = Column(String, ForeignKey("products.id"), nullable=False)
    quantity = Column(Float, nullable=False)
    unit_price = Column(Float, nullable=False)


class DispatchDirection(str, enum.Enum):
    OUTBOUND = "outbound"  # inputs/equipment/service to the farm
    INBOUND = "inbound"  # produce to the fulfilment centre


class DispatchJobStatus(str, enum.Enum):
    ASSIGNED = "assigned"
    EN_ROUTE = "en_route"
    DELIVERED = "delivered"


class DispatchJob(Base):
    """
    Logistics Dispatch (IA Section 3.5, Fig. 6; PRD Section 6 Must-Have #3
    "Vendor input ordering routed to logistics dispatch"). The one real
    outbound job source used to be only a CONFIRMED MechanisationRequest
    (vendor.py's confirm, or admin.py's override approval) -- a CONFIRMED
    InputOrder (vendor.py's confirm_input_order) is now the second, closing
    Must-Have #3's own literal scope: a Farmer buying seed/fertiliser from a
    Vendor's Product Catalogue, routed to dispatch (see models.InputOrder).

    Exactly one of mechanisation_request_id / harvest_pickup_request_id /
    input_order_id is set (application-enforced -- see app/dispatch.py's
    three creation functions -- not a DB constraint, consistent with this
    codebase's existing style of app-level invariants). Added 5 Sep 2026
    alongside HarvestPickupRequest (Must-Have #4) so the Stage 3/4
    wireframes' single dispatch queue, spanning both tabs, is genuinely one
    table rather than two (now three) near-identical ones.
    """
    __tablename__ = "dispatch_jobs"

    id = Column(String, primary_key=True, default=uid)
    mechanisation_request_id = Column(String, ForeignKey("mechanisation_requests.id"), nullable=True)
    harvest_pickup_request_id = Column(String, ForeignKey("harvest_pickup_requests.id"), nullable=True)
    input_order_id = Column(String, ForeignKey("input_orders.id"), nullable=True)
    direction = Column(SAEnum(DispatchDirection), nullable=False, default=DispatchDirection.OUTBOUND)
    status = Column(SAEnum(DispatchJobStatus), nullable=False, default=DispatchJobStatus.ASSIGNED)
    tricycle_label = Column(String, nullable=True)  # e.g. "#1" -- PRD Section 1.1's 3-5 tricycle pilot placeholder
    dispatched_by = Column(String, ForeignKey("users.id"), nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class HarvestPickupRequest(Base):
    """
    Farmer Portal's Harvest Pickup Request screen (Stage 3 wireframe) --
    PRD Section 6 Must-Have #4, the produce-in half of the physical loop.
    Deliberately not linked to a specific Opportunity/ProductionFormula:
    the approved wireframe models this as "I have this much ready, come get
    it" (quantity + preferred date), not an order-specific pickup -- farm
    location isn't captured either, since it isn't captured at
    registration yet (PRD Section 3.1's farm location/GPS KYC field is not
    built -- a pre-existing gap, not introduced here).

    Unlike a MechanisationRequest, there's no vendor-confirmation step: the
    request creates its DispatchJob immediately (app/dispatch.py's
    create_inbound_dispatch_job), since nobody needs to "accept" a
    farmer's own harvest being ready.

    buyer_requirement_id (added for PRD Section 6 Must-Have #5, Order
    Reconciliation) optionally ties this pickup to one of the farmer's own
    ACCEPTED opportunities for a real buyer order, so settlement can be
    computed from real graded/delivered tonnage instead of an estimate --
    see routers/farmer.py's validation that the caller actually accepted
    that order, and routers/reconciliation.py's use of this link. Stays
    nullable: a farmer can still log general "extra produce ready" pickups
    not tied to any specific order, per this model's original design intent
    above.
    """
    __tablename__ = "harvest_pickup_requests"

    id = Column(String, primary_key=True, default=uid)
    farmer_id = Column(String, ForeignKey("users.id"), nullable=False)
    buyer_requirement_id = Column(String, ForeignKey("buyer_requirements.id"), nullable=True)
    quantity_ready_tonnes = Column(Float, nullable=False)
    preferred_pickup_date = Column(String, nullable=False)  # ISO date, e.g. "2026-09-20"
    created_at = Column(DateTime, default=datetime.utcnow)


class GradeResult(str, enum.Enum):
    GRADE_1 = "grade_1"
    GRADE_2 = "grade_2"
    REJECT = "reject"


class FulfilmentIntake(Base):
    """
    Fulfilment Centre Intake & Grading (Stage 3 wireframe) -- the back half
    of PRD Must-Have #4, and the precondition for buyer delivery and farmer
    settlement. Gated on the corresponding DispatchJob being DELIVERED
    (produce has physically arrived) -- see routers/fulfilment.py. The
    wireframe assigns this screen to "Finance (fulfilment centre staff)",
    not Logistics, so intake/grading is Role.FINANCE-gated here, matching
    that already-confirmed design rather than folding it into Logistics.

    One row per HarvestPickupRequest (unique) -- a request can only be
    graded once. Photo capture (shown in the wireframe) is not implemented,
    consistent with no other flow in this codebase doing real file upload.
    A non-REJECT grade on a pickup linked to a buyer order (see
    HarvestPickupRequest.buyer_requirement_id) now feeds real farmer
    settlement in Order Reconciliation (PRD Must-Have #5, models.
    OrderReconciliation) -- REJECT tonnage is excluded from that
    computation. Feeding a graded intake into Buyer Compliance Docs is
    Reporting/MoFA Data Exchange scope -- still out of scope here.
    """
    __tablename__ = "fulfilment_intakes"

    id = Column(String, primary_key=True, default=uid)
    harvest_pickup_request_id = Column(String, ForeignKey("harvest_pickup_requests.id"), nullable=False, unique=True)
    weigh_in_kg = Column(Float, nullable=False)
    grade = Column(SAEnum(GradeResult), nullable=False)
    graded_by = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class OrderReconciliation(Base):
    """
    Finance & Reconciliation (Stage 3 wireframe) -- PRD Section 6 Must-Have
    #5, the last of the five pilot must-haves. Only the two release actions
    are real persisted state here: the GHS figures themselves (commitment
    fee received, farmer settlement due, vendor payout due, trading margin)
    are computed on read in routers/reconciliation.py from real linked data
    (BuyerRequirement, CommitmentFeePayment, graded FulfilmentIntake rows
    reached via HarvestPickupRequest.buyer_requirement_id, and confirmed
    MechanisationRequest rows reached via its own buyer_requirement_id) plus
    the trading_margin_pct RateConfig row -- same "not frozen at build time"
    treatment as RequirementFormulaPlan's input schedule, so a rate change
    is reflected immediately rather than requiring a backfill.

    One row per BuyerRequirement (unique), created lazily on first read
    (see reconciliation.py's _get_or_create) rather than at requirement
    creation, since most requirements never reach this screen.
    """
    __tablename__ = "order_reconciliations"

    id = Column(String, primary_key=True, default=uid)
    buyer_requirement_id = Column(String, ForeignKey("buyer_requirements.id"), nullable=False, unique=True)
    farmer_settlement_released = Column(Boolean, nullable=False, default=False)
    farmer_settlement_released_by = Column(String, ForeignKey("users.id"), nullable=True)
    farmer_settlement_released_at = Column(DateTime, nullable=True)
    vendor_payout_released = Column(Boolean, nullable=False, default=False)
    vendor_payout_released_by = Column(String, ForeignKey("users.id"), nullable=True)
    vendor_payout_released_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class RegistrationApproval(Base):
    """
    Backend counterpart of the Registration Approval Queue screen (IA Section
    10). user_id added 5 Sep 2026 alongside real-time OTP verification (PRD
    Section 12) -- until then nothing in the codebase actually created these
    rows or linked one back to a real account, so approving/rejecting here
    couldn't change anything a Buyer/Vendor could log in with. Now
    auth.py's register/verify-otp creates the row (post-OTP, pre-approval),
    and admin.py's approve/reject actually activates or suspends the
    linked user.
    """
    __tablename__ = "registration_approvals"

    id = Column(String, primary_key=True, default=uid)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    applicant_name = Column(String, nullable=False)
    applicant_type = Column(String, nullable=False)  # e.g. "Private Buyer", "Third-Party Vendor"
    portal = Column(String, nullable=False)  # buyer | vendor
    status = Column(String, nullable=False, default="pending_review")
    reviewed_by = Column(String, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class OtpPurpose(str, enum.Enum):
    REGISTRATION = "registration"
    LOGIN = "login"


class OtpChallenge(Base):
    """
    Real-time OTP verification via email, at both registration and login,
    for all roles -- added 5 Sep 2026 as a new confirmed requirement (PRD
    Section 12), not part of the original Stage 1-5 scope. Originally
    dual-channel (phone + email, both required together); consolidated to
    email-only 10 Sep 2026 for user-friendliness -- one code to read and
    enter instead of two, email being the simpler channel to maintain given
    delivery is already simulated either way. The `phone_code` column this
    table used to carry is gone, not just unused -- see the SDD's Stage 7+
    section for the migration note (existing databases need a real
    ALTER TABLE, not just a model change).

    Delivery is SIMULATED, the same treatment as mobile money payment
    (routers/buyer.py) and for the same reason: no SMS or email gateway has
    been chosen yet (PRD Section 1.1 lists the payment gateway as an open
    decision; the OTP gateway is equally open). The generated code is
    echoed back in the API response instead of actually being sent -- see
    schemas.OtpChallengeResponse's dev_only_email_code field, named to
    make that unmistakable in the API docs and never meant to ship
    unmodified to production.
    """
    __tablename__ = "otp_challenges"

    id = Column(String, primary_key=True, default=uid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    purpose = Column(SAEnum(OtpPurpose), nullable=False)
    email_code = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    consumed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class FieldVisitStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"


class FieldVisitLog(Base):
    """
    Field Visit Logs (Stage 3 wireframe) -- the agronomist's own counterpart
    to the Farmer Portal's Milestone Log (see MilestoneLogEntry below), tied
    to a specific farmer's production-formula checkpoints. Added 8 Sep 2026
    to close a gap this session's own completeness audit surfaced: this
    screen was in the confirmed IA/wireframe/visual scope from the start but
    had never been built. Offline-tolerant capture (per the wireframe's own
    caption) is explicitly out of scope for the pilot build, same treatment
    as Fulfilment Intake's photo capture -- structure only, no real
    on-device queue/sync.
    """
    __tablename__ = "field_visit_logs"

    id = Column(String, primary_key=True, default=uid)
    agronomist_id = Column(String, ForeignKey("users.id"), nullable=False)
    farmer_id = Column(String, ForeignKey("users.id"), nullable=False)
    opportunity_id = Column(String, ForeignKey("opportunities.id"), nullable=True)
    checkpoint_label = Column(String, nullable=False)
    scheduled_date = Column(String, nullable=False)  # ISO date
    status = Column(SAEnum(FieldVisitStatus), nullable=False, default=FieldVisitStatus.SCHEDULED)
    notes = Column(Text, nullable=True)
    logged_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ProofOfDelivery(Base):
    """
    Proof of Pickup/Delivery (Stage 3 wireframe) -- field confirmation
    linked to a DispatchJob, closing the loop for both outbound (input/
    mechanisation delivery to a farm) and inbound (harvest pickup to the
    fulfilment centre) jobs. Added 8 Sep 2026, same audit as FieldVisitLog
    above. One row per DispatchJob (unique) -- a job is confirmed once.

    GPS is captured for real via the browser's Geolocation API where the
    rider's device/browser grants permission (frontend falls back to manual
    lat/lng entry, never silently fakes a value) -- unlike photo/signature,
    which stay boolean "captured" flags, consistent with no other flow in
    this codebase doing real file upload.
    """
    __tablename__ = "proof_of_deliveries"

    id = Column(String, primary_key=True, default=uid)
    dispatch_job_id = Column(String, ForeignKey("dispatch_jobs.id"), nullable=False, unique=True)
    confirmed_by = Column(String, ForeignKey("users.id"), nullable=False)
    gps_lat = Column(Float, nullable=True)
    gps_lng = Column(Float, nullable=True)
    signature_captured = Column(Boolean, nullable=False, default=False)
    photo_captured = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class TrunkingStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    DISPATCHED = "dispatched"
    DELIVERED = "delivered"


class TrunkingJob(Base):
    """
    Trunking (Stage 3 wireframe) -- bulk consolidated movement of graded
    produce out of the Tema fulfilment centre, distinct from last-mile
    tricycle collection (DispatchJob). Added 8 Sep 2026, same audit as
    FieldVisitLog/ProofOfDelivery above -- previously entirely absent (no
    model, no stub, no endpoint), not merely unfinished.

    Deliberately thin per the wireframe's own caption: single origin (Tema),
    no multi-centre routing (Phase 3). tonnes_available_at_creation is a
    real snapshot of graded, non-REJECT FulfilmentIntake weight not yet
    claimed by another TrunkingJob at the moment this one was scheduled --
    shown back to Logistics as the "how much is actually ready" figure the
    wireframe displays, not a fabricated placeholder number.
    """
    __tablename__ = "trunking_jobs"

    id = Column(String, primary_key=True, default=uid)
    produce_tonnes = Column(Float, nullable=False)
    tonnes_available_at_creation = Column(Float, nullable=False)
    destination = Column(String, nullable=False)
    vehicle_label = Column(String, nullable=False)
    status = Column(SAEnum(TrunkingStatus), nullable=False, default=TrunkingStatus.SCHEDULED)
    scheduled_by = Column(String, ForeignKey("users.id"), nullable=False)
    dispatched_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class MofaImportRecord(Base):
    """
    MoFA Data Exchange's import half (Stage 3 wireframe: "Manual import (no
    live API yet)") -- added 8 Sep 2026 alongside the rest of this pass's
    gap-closing. No live MoFA API exists to call (confirmed, PRD Section
    1.1/9), so this is a real manual-entry form and table, not a stub button
    -- the honest equivalent of what the wireframe itself describes, since
    the wireframe's own caption already concedes no live API exists.
    """
    __tablename__ = "mofa_import_records"

    id = Column(String, primary_key=True, default=uid)
    buyer_name = Column(String, nullable=False)
    verified = Column(Boolean, nullable=False, default=False)
    imported_by = Column(String, ForeignKey("users.id"), nullable=False)
    synced_at = Column(DateTime, default=datetime.utcnow)


class MilestoneLogEntry(Base):
    """
    Farmer Portal's Milestone Log (Stage 3 wireframe) -- farmer-side field
    data capture against their own accepted opportunity, the farmer-facing
    counterpart to FieldVisitLog above. Added 8 Sep 2026. Offline-tolerant
    sync is explicitly flagged in the wireframe's own caption as a Stage 6
    build concern deferred to structure-only -- same treatment as
    FieldVisitLog.
    """
    __tablename__ = "milestone_log_entries"

    id = Column(String, primary_key=True, default=uid)
    farmer_id = Column(String, ForeignKey("users.id"), nullable=False)
    opportunity_id = Column(String, ForeignKey("opportunities.id"), nullable=True)
    title = Column(String, nullable=False)
    note = Column(Text, nullable=True)
    logged_at = Column(DateTime, default=datetime.utcnow)


class AgronomistMessage(Base):
    """
    Agronomist Messaging (Stage 3 wireframe) -- "confirmed in Phase 1 pilot
    scope" per the wireframe's own caption. Added 8 Sep 2026. The pilot's
    seed data has exactly one Agronomist account (Kwabena Osei, Tema) and
    PRD Section 1.1 scopes the whole pilot to one region -- so this is
    modelled as a single shared Agronomy inbox (agronomist_id nullable,
    filled in on the agronomist's reply) rather than a farmer-to-a-specific-
    assigned-agronomist thread, since no per-farmer agronomist assignment
    field exists anywhere else in this schema to thread against.
    """
    __tablename__ = "agronomist_messages"

    id = Column(String, primary_key=True, default=uid)
    farmer_id = Column(String, ForeignKey("users.id"), nullable=False)
    agronomist_id = Column(String, ForeignKey("users.id"), nullable=True)
    sender_id = Column(String, ForeignKey("users.id"), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class VendorBilling(Base):
    """
    Vendor Portal's Subscription & Billing (Stage 3 wireframe). Added 8 Sep
    2026. Card payment gateway stays TBD (PRD Section 1.1, same as
    everywhere else in this codebase) -- the subscription fee itself is
    charged through the same simulated MoMo/Vodafone/AirtelTigo rails as
    every other payment here (see VendorBillingPayment), not a new payment
    path. One row per vendor (unique) -- every vendor gets the single
    Farm Master-owned storefront plan for the pilot (PRD Section 6:
    "at least the Farm Master-owned vendor storefront live and billable";
    third-party vendor subscription tiers are Phase 2).
    """
    __tablename__ = "vendor_billing"

    id = Column(String, primary_key=True, default=uid)
    vendor_id = Column(String, ForeignKey("users.id"), nullable=False, unique=True)
    plan = Column(String, nullable=False, default="Farm Master Storefront -- Standard")
    monthly_fee = Column(Float, nullable=False)
    status = Column(String, nullable=False, default="active")  # active | past_due
    last_billed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class VendorBillingPayment(Base):
    __tablename__ = "vendor_billing_payments"

    id = Column(String, primary_key=True, default=uid)
    vendor_id = Column(String, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    method = Column(String, nullable=False)
    status = Column(String, nullable=False, default="success")
    transaction_ref = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class UssdSmsLog(Base):
    """
    Records every simulated SMS/USSD push to a farmer's phone -- added 8 Sep
    2026 specifically so "the SMS was sent" is an assertable, queryable fact
    (GET /ussd/sms-log) rather than something the frontend merely displays
    and no one can verify actually happened. Same SIMULATED-delivery
    treatment as OtpChallenge and mobile money: the message body is real and
    computed from real data, only the carrier hop is not real.
    """
    __tablename__ = "ussd_sms_log"

    id = Column(String, primary_key=True, default=uid)
    farmer_id = Column(String, ForeignKey("users.id"), nullable=False)
    channel = Column(String, nullable=False)  # sms | ussd
    purpose = Column(String, nullable=False)  # opportunity_alert | pickup_confirmation | payment_notification
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    """
    Every role/permission change and every financial action, attributable to
    the acting user -- PRD Section 5, added 3 Sep 2026 as a Stage 6
    architectural requirement from day one. Rows are never updated or
    deleted by application code (see routers -- there is deliberately no
    PATCH/DELETE endpoint for this table, including for Super Admin).
    """
    __tablename__ = "audit_log"

    id = Column(String, primary_key=True, default=uid)
    actor_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    actor_role = Column(String, nullable=False)
    action = Column(String, nullable=False)
    detail = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
