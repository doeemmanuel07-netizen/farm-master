"""Pydantic request/response schemas -- see API documentation doc for the full contract."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel

from .models import (
    Role, RequirementStatus, PaymentStatus, OpportunityStatus, MechanisationRequestStatus,
    UserStatus, OtpPurpose, DispatchDirection, DispatchJobStatus, GradeResult,
    ProductCategory, FormulaInputType, InputOrderStatus,
)


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Role
    full_name: str


class RegisterRequest(BaseModel):
    email: str
    phone: str
    full_name: str
    password: str
    role: Role
    organisation_name: Optional[str] = None


class OtpChallengeResponse(BaseModel):
    challenge_id: str
    purpose: OtpPurpose
    expires_at: datetime
    message: str
    # SIMULATED delivery -- see models.OtpChallenge. Named dev_only_* so
    # nothing accidentally mistakes this for a real-provider response shape.
    dev_only_phone_code: str
    dev_only_email_code: str


class VerifyOtpRequest(BaseModel):
    challenge_id: str
    phone_code: str
    email_code: str


class RegisterVerifyResponse(BaseModel):
    status: UserStatus
    message: str


class DispatchJobResponse(BaseModel):
    id: str
    job_type: str  # "mechanisation" | "harvest_pickup" | "input_order" -- presentation-only, not a DB column
    farmer_name: str
    description: str
    # Mechanisation-sourced (outbound) fields:
    area_acres: Optional[float] = None
    confirmed_date: Optional[str] = None
    # Harvest-pickup-sourced (inbound) fields:
    quantity_tonnes: Optional[float] = None
    preferred_pickup_date: Optional[str] = None
    # Input-order-sourced (outbound) fields:
    item_count: Optional[int] = None
    total_cost: Optional[float] = None
    direction: DispatchDirection
    status: DispatchJobStatus
    tricycle_label: Optional[str]
    delivered_at: Optional[datetime]

    class Config:
        from_attributes = True


class DispatchAssignRequest(BaseModel):
    tricycle_label: str


class HarvestPickupRequestCreate(BaseModel):
    quantity_ready_tonnes: float
    preferred_pickup_date: str  # ISO date, e.g. "2026-09-20"
    # Optional link to one of the farmer's own ACCEPTED opportunities for a
    # real buyer order (PRD Must-Have #5) -- see routers/farmer.py's
    # validation. Omit for a general "extra produce ready" pickup.
    buyer_requirement_id: Optional[str] = None


class HarvestPickupRequestResponse(BaseModel):
    id: str
    quantity_ready_tonnes: float
    preferred_pickup_date: str
    buyer_requirement_id: Optional[str]
    dispatch_status: DispatchJobStatus
    created_at: datetime

    class Config:
        from_attributes = True


class FarmerOrderOption(BaseModel):
    """One of the caller's own accepted, order-backed opportunities -- the
    dropdown source for HarvestPickupRequestCreate.buyer_requirement_id."""
    buyer_requirement_id: str
    buyer_name: str
    grade: str
    quantity_tonnes: float
    price_per_tonne: float


class FulfilmentIntakeCreate(BaseModel):
    weigh_in_kg: float
    grade: GradeResult


class FulfilmentIntakeResponse(BaseModel):
    id: str
    harvest_pickup_request_id: str
    weigh_in_kg: float
    grade: GradeResult
    created_at: datetime

    class Config:
        from_attributes = True


class FulfilmentQueueEntry(BaseModel):
    harvest_pickup_request_id: str
    farmer_name: str
    quantity_ready_tonnes: float
    delivered_at: Optional[datetime]


class RegistrationApprovalResponse(BaseModel):
    id: str
    applicant_name: str
    applicant_type: str
    portal: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class RequirementCreate(BaseModel):
    grade: str
    quantity_tonnes: float
    price_per_tonne: float
    delivery_location: str
    delivery_timeline: str


class RequirementResponse(BaseModel):
    id: str
    crop: str
    grade: str
    quantity_tonnes: float
    price_per_tonne: float
    delivery_location: str
    delivery_timeline: str
    commitment_fee_amount: float
    status: RequirementStatus
    created_at: datetime

    class Config:
        from_attributes = True


class PaymentRequest(BaseModel):
    method: str


class PaymentResponse(BaseModel):
    id: str
    requirement_id: str
    amount: float
    method: str
    status: PaymentStatus
    transaction_ref: Optional[str]

    class Config:
        from_attributes = True


class OpportunityResponse(BaseModel):
    id: str
    buyer_name: str
    tag: str
    grade: str
    quantity_tonnes: float
    price_per_tonne: float
    deadline: str
    status: OpportunityStatus

    class Config:
        from_attributes = True


class AcceptOpportunityRequest(BaseModel):
    commitments_confirmed: bool


class ProductionFormulaResponse(BaseModel):
    id: str
    opportunity_id: str
    seed_kg: float
    npk_bags: int
    topdress_bags: int
    created_at: datetime

    class Config:
        from_attributes = True


class MechanisationRequestResponse(BaseModel):
    id: str
    farmer_name: str
    service: str
    area_acres: float
    requested_by_date: str
    status: MechanisationRequestStatus
    confirmed_date: Optional[str]
    notes: Optional[str]
    override_needed: bool
    override_approved: bool
    proposed_date: Optional[str]
    proposed_notes: Optional[str]
    suggested_quote: Optional[float] = None

    class Config:
        from_attributes = True


class ConfirmRequestBody(BaseModel):
    confirmed_date: str  # ISO date, e.g. "2026-09-20"
    notes: Optional[str] = None


class RoleChangeRequest(BaseModel):
    new_role: Role


class AuditLogEntry(BaseModel):
    id: str
    actor_role: str
    action: str
    detail: str
    created_at: datetime

    class Config:
        from_attributes = True


class RateConfigResponse(BaseModel):
    key: str
    value: float
    unit: str
    status: str
    note: Optional[str]

    class Config:
        from_attributes = True


class RateConfigUpdate(BaseModel):
    value: float


class AgronomistRequirementResponse(BaseModel):
    id: str
    buyer_name: str
    grade: str
    quantity_tonnes: float
    price_per_tonne: float
    delivery_location: str
    delivery_timeline: str
    status: RequirementStatus
    assigned_farmer_count: int
    formula_published: bool

    class Config:
        from_attributes = True


class FarmerCandidateResponse(BaseModel):
    id: str
    full_name: str
    email: str

    class Config:
        from_attributes = True


class AssignFarmersRequest(BaseModel):
    farmer_ids: List[str]


class FormulaPlanUpdate(BaseModel):
    land_prep_week: int
    planting_week: int
    topdress_week: int
    weeding_week: int
    harvest_week: int


class FormulaPlanResponse(FormulaPlanUpdate):
    published: bool
    published_at: Optional[datetime]

    class Config:
        from_attributes = True


class FormulaBuilderResponse(BaseModel):
    buyer_requirement_id: str
    buyer_name: str
    grade: str
    quantity_tonnes: float
    delivery_timeline: str
    farmer_names: List[str]
    per_farmer_tonnes: float
    seed_kg_per_farmer: float
    npk_bags_per_farmer: int
    topdress_bags_per_farmer: int
    plan: FormulaPlanResponse


class OrderReconciliationSummary(BaseModel):
    buyer_requirement_id: str
    buyer_name: str
    grade: str
    quantity_tonnes: float
    status: RequirementStatus
    accepted_delivered_tonnes: float
    farmer_settlement_released: bool
    vendor_payout_released: bool


class OrderReconciliationResponse(BaseModel):
    buyer_requirement_id: str
    buyer_name: str
    crop: str
    grade: str
    price_per_tonne: float
    commitment_fee_received: float
    accepted_delivered_tonnes: float
    buyer_invoice_value: float
    trading_margin_pct: float
    trading_margin_amount: float
    farmer_settlement_due: float
    vendor_payout_due: float
    farmer_settlement_released: bool
    farmer_settlement_released_at: Optional[datetime]
    vendor_payout_released: bool
    vendor_payout_released_at: Optional[datetime]


class ProductCreate(BaseModel):
    name: str
    category: ProductCategory
    formula_input_type: FormulaInputType = FormulaInputType.OTHER
    unit: str
    unit_price: float
    stock_qty: float


class ProductResponse(BaseModel):
    id: str
    vendor_id: str
    vendor_name: str
    name: str
    category: ProductCategory
    formula_input_type: FormulaInputType
    unit: str
    unit_price: float
    stock_qty: float

    class Config:
        from_attributes = True


class InputOrderLineCreate(BaseModel):
    product_id: str
    quantity: float


class InputOrderCreate(BaseModel):
    vendor_id: str
    production_formula_id: Optional[str] = None
    lines: List[InputOrderLineCreate]


class InputOrderLineResponse(BaseModel):
    product_id: str
    product_name: str
    quantity: float
    unit: str
    unit_price: float
    line_total: float


class InputOrderResponse(BaseModel):
    id: str
    farmer_name: str
    vendor_id: str
    vendor_name: str
    status: InputOrderStatus
    total_cost: float
    lines: List[InputOrderLineResponse]
    dispatch_status: Optional[DispatchJobStatus] = None
    created_at: datetime
