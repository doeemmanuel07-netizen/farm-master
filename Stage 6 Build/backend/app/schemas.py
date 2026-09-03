"""Pydantic request/response schemas -- see API documentation doc for the full contract."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel

from .models import Role, RequirementStatus, PaymentStatus


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
