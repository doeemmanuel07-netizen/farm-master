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
    Column, String, Float, Integer, DateTime, ForeignKey, Enum as SAEnum, Text
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
