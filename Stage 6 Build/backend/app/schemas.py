"""Pydantic request/response schemas -- see API documentation doc for the full contract."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel

from .models import Role, RequirementStatus, PaymentStatus, OpportunityStatus, MechanisationRequestStatus


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Role
    full_name: str


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
