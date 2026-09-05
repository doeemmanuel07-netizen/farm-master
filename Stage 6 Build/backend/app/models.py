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


# Roles permitted to perform account/role administration and registration
# approval. Deliberately excludes FINANCE -- this is the segregation-of-duties
# rule from PRD Section 5: no role that can move money can also grant
# permissions or approve accounts.
ADMIN_ROLES = {Role.SUPER_ADMIN}

# Roles permitted to perform financial actions (fee capture, settlement/
# payout release). Deliberately excludes SUPER_ADMIN for release actions in
# the general case, though Super Admin can still view everything via the
# audit log -- visibility is not the same as authority to move money.
FINANCE_ROLES = {Role.FINANCE}


class UserStatus(str, enum.Enum):
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
    """
    __tablename__ = "mechanisation_requests"

    id = Column(String, primary_key=True, default=uid)
    vendor_id = Column(String, ForeignKey("users.id"), nullable=False)
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


class RegistrationApproval(Base):
    """Backend counterpart of the Registration Approval Queue screen (IA Section 10)."""
    __tablename__ = "registration_approvals"

    id = Column(String, primary_key=True, default=uid)
    applicant_name = Column(String, nullable=False)
    applicant_type = Column(String, nullable=False)  # e.g. "Private Buyer", "Third-Party Vendor"
    portal = Column(String, nullable=False)  # buyer | vendor
    status = Column(String, nullable=False, default="pending_review")
    reviewed_by = Column(String, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
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
