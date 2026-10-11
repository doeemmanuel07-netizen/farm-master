"""Pydantic request/response schemas -- see API documentation doc for the full contract."""

from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel

from .models import (
    Role, RequirementStatus, PaymentStatus, OpportunityStatus, MechanisationRequestStatus,
    UserStatus, OtpPurpose, DispatchDirection, DispatchJobStatus, GradeResult,
    ProductCategory, FormulaInputType, InputOrderStatus, FieldVisitStatus, TrunkingStatus,
    ListingType, ListingStatus, NotificationType, PaymentNetwork, FeeBasis, ListingKind, PricingBasis,
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
    # Email-only as of 10 Sep 2026 -- dev_only_phone_code was removed, not
    # just stopped being read; see models.OtpChallenge for the consolidation.
    dev_only_email_code: str


class VerifyOtpRequest(BaseModel):
    challenge_id: str
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
    """
    CEO demo form (brief §5.1): crop_variety_id, quantity_tonnes, delivery_by,
    spec_notes, plus the target price per tonne (decision D2; defaults to the
    crop's reference price). grade / delivery_location / delivery_timeline are
    the original Stage 6 fields, still accepted from older clients and
    defaulted when omitted.
    """
    quantity_tonnes: float
    crop_variety_id: Optional[str] = None
    delivery_by: Optional[date] = None
    spec_notes: Optional[str] = None
    price_per_tonne: Optional[float] = None
    grade: Optional[str] = None
    delivery_location: Optional[str] = None
    delivery_timeline: Optional[str] = None


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
    # Added 11 Oct 2026 (CEO demo brief §5) -- defaults keep every older
    # response that validates straight from an ORM row working unchanged.
    reference: Optional[str] = None
    crop_icon: str = "maize"
    crop_variety_id: Optional[str] = None
    variety: Optional[str] = None
    delivery_by: Optional[date] = None
    spec_notes: Optional[str] = None
    status_label: Optional[str] = None
    stage_index: Optional[int] = None
    progress_pct: Optional[int] = None
    badge: Optional[str] = None
    steps: List[str] = []
    latest_payment_status: Optional[PaymentStatus] = None
    latest_payment_id: Optional[str] = None
    paid: bool = False

    class Config:
        from_attributes = True


class PaymentRequest(BaseModel):
    """network is the current field; method is the pre-rebrand legacy one (momo | vodafone | airteltigo | card)."""
    network: Optional[PaymentNetwork] = None
    method: Optional[str] = None
    payer_phone: Optional[str] = None


class PaymentResponse(BaseModel):
    id: str
    requirement_id: str
    amount: float
    method: str
    status: PaymentStatus
    transaction_ref: Optional[str]
    network: Optional[PaymentNetwork] = None
    network_label: Optional[str] = None
    provider: Optional[str] = None
    provider_ref: Optional[str] = None
    checkout_url: Optional[str] = None
    display_text: Optional[str] = None
    failure_reason: Optional[str] = None
    paid_at: Optional[datetime] = None
    requirement_reference: Optional[str] = None
    sandbox: bool = False

    class Config:
        from_attributes = True


class FeeQuoteResponse(BaseModel):
    amount: float
    rule_name: str
    basis: FeeBasis
    rate: float
    minimum_amount: float
    explanation: str


class PaymentOptionResponse(BaseModel):
    network: PaymentNetwork
    label: str
    hint: Optional[str] = None
    needs_phone: bool


class BuyerOrderFormResponse(BaseModel):
    """Everything the Submit-a-requirement card needs, none of it hard-coded in the page."""
    crops: List["CropResponse"]
    earliest_delivery_by: date
    payment_options: List[PaymentOptionResponse]
    payer_phone: Optional[str] = None
    provider: str


class CommitmentFeeRuleResponse(BaseModel):
    id: str
    name: str
    basis: FeeBasis
    rate: float
    minimum_amount: float
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class CommitmentFeeRuleCreate(BaseModel):
    name: str
    basis: FeeBasis
    rate: float
    minimum_amount: float = 0.0


class OpsPaymentRow(BaseModel):
    id: str
    requirement_id: str
    requirement_reference: Optional[str]
    buyer_name: str
    amount: float
    network_label: str
    provider: Optional[str]
    provider_ref: Optional[str]
    status: PaymentStatus
    failure_reason: Optional[str]
    created_at: datetime
    paid_at: Optional[datetime]


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
    reference: Optional[str] = None  # FM-####, added 11 Oct 2026
    crop: Optional[str] = None
    spec_notes: Optional[str] = None

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
    product_id: Optional[str]  # legacy catalogue line
    product_name: str  # display name from whichever catalogue the line came from
    quantity: float
    unit: str
    unit_price: float
    line_total: float
    listing_id: Optional[str] = None  # marketplace line (decision D1)
    kind: Optional[ListingKind] = None
    requested_date: Optional[date] = None


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
    checkout_ref: Optional[str] = None


class ComplianceReportRowResponse(BaseModel):
    farmer_name: str
    crop: str
    buyer_name: str
    grade: str
    volume_kg: float
    delivery_date: Optional[datetime]


class AdminUserResponse(BaseModel):
    id: str
    full_name: str
    email: str
    role: Role
    status: UserStatus
    organisation_name: Optional[str] = None
    # Internal-staff rows only (Stage 4 visual's "Scope" column) -- a fixed,
    # per-role description of what that role's real endpoints permit, not
    # per-user data. Null for external accounts, which show their portal
    # (the role itself) instead, matching the mockup's two distinct tables.
    scope: Optional[str] = None
    # External-account rows only, and only while status is "pending_review"
    # -- the RegistrationApproval row the "Review ->" action acts on.
    registration_approval_id: Optional[str] = None


class AdminUsersResponse(BaseModel):
    internal: List[AdminUserResponse]
    external: List[AdminUserResponse]


class InternalUserCreate(BaseModel):
    full_name: str
    email: str
    phone: str
    role: Role
    password: str


# ---------------------------------------------------------------------------
# Field Visit Logs + Agronomist Messaging + Milestone Log -- added 8 Sep 2026
# closing gaps this session's own completeness audit surfaced (Stage 3
# wireframe screens that had never been built).
# ---------------------------------------------------------------------------


class FieldVisitLogCreate(BaseModel):
    farmer_id: str
    checkpoint_label: str
    scheduled_date: str  # ISO date
    opportunity_id: Optional[str] = None
    notes: Optional[str] = None


class FieldVisitLogCompleteRequest(BaseModel):
    notes: Optional[str] = None


class FieldVisitLogResponse(BaseModel):
    id: str
    farmer_name: str
    checkpoint_label: str
    scheduled_date: str
    status: FieldVisitStatus
    notes: Optional[str]
    logged_at: Optional[datetime]
    created_at: datetime


class AgronomistMessageCreate(BaseModel):
    body: str


class AgronomistMessageResponse(BaseModel):
    id: str
    sender_name: str
    sender_role: Role
    body: str
    created_at: datetime


class MilestoneLogEntryCreate(BaseModel):
    title: str
    note: Optional[str] = None
    opportunity_id: Optional[str] = None


class MilestoneLogEntryResponse(BaseModel):
    id: str
    title: str
    note: Optional[str]
    opportunity_id: Optional[str]
    logged_at: datetime


# ---------------------------------------------------------------------------
# Proof of Pickup/Delivery + Trunking -- added 8 Sep 2026, same audit.
# ---------------------------------------------------------------------------


class ProofOfDeliveryCreate(BaseModel):
    gps_lat: Optional[float] = None
    gps_lng: Optional[float] = None
    signature_captured: bool = False
    photo_captured: bool = False


class ProofOfDeliveryResponse(BaseModel):
    id: str
    dispatch_job_id: str
    confirmed_by_name: str
    gps_lat: Optional[float]
    gps_lng: Optional[float]
    signature_captured: bool
    photo_captured: bool
    created_at: datetime


class TrunkingJobCreate(BaseModel):
    produce_tonnes: float
    destination: str
    vehicle_label: str


class TrunkingJobResponse(BaseModel):
    id: str
    produce_tonnes: float
    tonnes_available_at_creation: float
    destination: str
    vehicle_label: str
    status: TrunkingStatus
    dispatched_at: Optional[datetime]
    delivered_at: Optional[datetime]
    created_at: datetime


class TrunkingAvailabilityResponse(BaseModel):
    tonnes_available: float


# ---------------------------------------------------------------------------
# Reporting dashboard + MoFA import -- added 8 Sep 2026, same audit.
# ---------------------------------------------------------------------------


class RevenueStreamStat(BaseModel):
    label: str
    value: Optional[str] = None
    deferred_phase: Optional[str] = None


class ReportingDashboardResponse(BaseModel):
    revenue_streams: List[RevenueStreamStat]
    registered_farmers: int
    active_buyers: int
    volume_aggregated_tonnes: float
    spec_compliance_rate_pct: Optional[float]


class MofaImportCreate(BaseModel):
    buyer_name: str
    verified: bool = False


class MofaImportRecordResponse(BaseModel):
    id: str
    buyer_name: str
    verified: bool
    imported_by_name: str
    synced_at: datetime


# ---------------------------------------------------------------------------
# Portal dashboards + Buyer Docs/Tracking/Invoice + Vendor Billing/Payout/
# Handoff + Farmer Wallet -- added 8 Sep 2026, same audit.
# ---------------------------------------------------------------------------


class BuyerDashboardResponse(BaseModel):
    active_orders: int
    commitment_fees_due: int
    maize_in_transit_tonnes: float
    spec_compliance_rate_pct: Optional[float]
    recent_orders: List[RequirementResponse]


class BuyerDocumentRow(BaseModel):
    label: str
    doc_type: str
    status: str  # verified | pending | not_yet_available
    detail: Optional[str] = None


class BuyerDocumentsResponse(BaseModel):
    buyer_requirement_id: str
    rows: List[BuyerDocumentRow]


class BuyerTrackingLogRow(BaseModel):
    text: str
    when: datetime


class BuyerTrackingResponse(BaseModel):
    buyer_requirement_id: str
    status: RequirementStatus
    accepted_delivered_tonnes: float
    target_quantity_tonnes: float
    log: List[BuyerTrackingLogRow]


class BuyerInvoiceResponse(BaseModel):
    buyer_requirement_id: str
    price_per_tonne: float
    accepted_delivered_tonnes: float
    subtotal: float
    commitment_fee_applied: float
    net_payable: float


class VendorDashboardResponse(BaseModel):
    pending_mechanisation_requests: int
    pending_input_orders: int
    catalogue_item_count: int
    catalogue_low_stock_count: int


class VendorBillingResponse(BaseModel):
    plan: str
    monthly_fee: float
    status: str
    last_billed_at: Optional[datetime]
    history: List[PaymentResponse]


class VendorBillingPayRequest(BaseModel):
    method: str


class VendorPayoutRow(BaseModel):
    buyer_requirement_id: str
    buyer_name: str
    mechanisation_amount: float
    input_order_amount: float
    total: float
    released: bool
    released_at: Optional[datetime]


class VendorHandoffRow(BaseModel):
    dispatch_job_id: str
    description: str
    status: DispatchJobStatus
    tricycle_label: Optional[str]
    delivered_at: Optional[datetime]
    proof_captured: bool


class FarmerWalletOrderRow(BaseModel):
    buyer_requirement_id: str
    buyer_name: str
    own_delivered_tonnes: float
    own_settlement_due: float
    input_order_costs: float


class FarmerWalletResponse(BaseModel):
    rows: List[FarmerWalletOrderRow]
    total_settlement_due: float
    total_input_order_costs: float
    net_due: float


class FarmerDashboardResponse(BaseModel):
    open_opportunities: int
    accepted_opportunities: int
    pending_pickups: int
    unread_message_note: Optional[str] = None


class ControlCentreDashboardResponse(BaseModel):
    role: Role
    registered_farmers: int
    active_buyers: int
    volume_aggregated_tonnes: float
    tiles: dict


# ---------------------------------------------------------------------------
# USSD/SMS channel -- added 8 Sep 2026, same audit. A browser-based session
# emulator drives these against real farmer data; delivery is SIMULATED, the
# same treatment as OtpChallenge -- see models.UssdSmsLog.
# ---------------------------------------------------------------------------


class UssdOpportunityAlert(BaseModel):
    opportunity_id: str
    sms_text: str
    ussd_detail_text: str


class UssdPickupConfirmRequest(BaseModel):
    quantity_ready_tonnes: float
    preferred_pickup_date: str
    buyer_requirement_id: Optional[str] = None


class UssdPaymentNotification(BaseModel):
    sms_text: str
    balance_text: str


class UssdSmsLogEntry(BaseModel):
    id: str
    channel: str
    purpose: str
    body: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Vendor Product/Service Listing -- added 10 Sep 2026. See models.Listing
# for the full design rationale and status-lifecycle rules.
# ---------------------------------------------------------------------------


class ListingCategoryResponse(BaseModel):
    id: str
    name: str
    slug: str
    active: bool

    class Config:
        from_attributes = True


class ListingCategoryCreate(BaseModel):
    name: str


class ListingImageResponse(BaseModel):
    id: str
    url: str
    display_order: int
    is_primary: bool


class ListingCreate(BaseModel):
    category_id: str
    title: str
    description: str = ""
    listing_type: ListingType = ListingType.PRODUCT
    price: float
    unit: str
    quantity_available: Optional[float] = None
    region: str


class ListingUpdate(ListingCreate):
    pass


class ListingResponse(BaseModel):
    id: str
    vendor_id: str
    vendor_name: str
    category_id: str
    category_name: str
    title: str
    description: str
    listing_type: ListingType
    price: float
    unit: str
    quantity_available: Optional[float]
    region: str
    status: ListingStatus
    rejection_reason: Optional[str]
    reviewed_by: Optional[str]
    reviewed_at: Optional[datetime]
    images: List[ListingImageResponse]
    created_at: datetime
    updated_at: datetime


class ListingRejectRequest(BaseModel):
    rejection_reason: str


class ListingStatusToggleRequest(BaseModel):
    # Restricted server-side to {active, out_of_stock} -- see
    # routers/vendor.py's toggle_listing_status. Archiving is its own
    # DELETE endpoint, not a status-toggle value, since it's reachable from
    # any status while this toggle only applies to an already-approved one.
    status: ListingStatus


class NotificationResponse(BaseModel):
    id: str
    type: NotificationType
    message: str
    listing_id: Optional[str]
    read_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Reference data + profile (CEO platform demo alignment, 11 Oct 2026)
# ---------------------------------------------------------------------------

class CropVarietyResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True


class CropResponse(BaseModel):
    id: str
    name: str
    slug: str
    icon: str
    is_active_for_ordering: bool
    reference_price_per_tonne: float
    varieties: List[CropVarietyResponse]

    class Config:
        from_attributes = True


class CropUpdate(BaseModel):
    is_active_for_ordering: Optional[bool] = None
    reference_price_per_tonne: Optional[float] = None


class CropVarietyCreate(BaseModel):
    name: str
    description: Optional[str] = None


class RegionResponse(BaseModel):
    id: str
    name: str
    code: str
    is_active: bool

    class Config:
        from_attributes = True


class FulfilmentCentreResponse(BaseModel):
    id: str
    name: str
    town: str
    region_id: str
    region_name: str
    is_hq: bool
    is_active: bool


class ActiveToggle(BaseModel):
    is_active: bool


class PublicStatsResponse(BaseModel):
    coordinated_portals: int
    fulfilment_centres: int
    active_fulfilment_centres: int
    revenue_streams: int
    head_office: str


class MeResponse(BaseModel):
    id: str
    full_name: str
    email: str
    role: Role
    profile_line: str
    organisation_name: Optional[str] = None
    region: Optional[str] = None
    farmer_union: Optional[str] = None
    buyer_type: Optional[str] = None
    mofa_verified: bool = False
    vendor_ownership: Optional[str] = None
    crops: List[str] = []


BuyerOrderFormResponse.model_rebuild()


class VehicleResponse(BaseModel):
    id: str
    code: str
    vehicle_type: str
    home_centre: str
    status: str


class OrderAdvanceRequest(BaseModel):
    status: RequirementStatus


class AggregationRow(BaseModel):
    centre: str
    crop: str
    tonnes_today: float


class MatchedOpportunityResponse(BaseModel):
    """Farmer Portal opportunity row + detail panel (brief §4.1/§4.2)."""
    id: str
    buyer_name: str
    tag: str
    grade: str
    quantity_tonnes: float
    price_per_tonne: float
    deadline: str
    status: OpportunityStatus
    crop: str
    crop_icon: str
    variety: Optional[str] = None
    region: Optional[str] = None
    delivery_by: Optional[date] = None
    delivery_in_weeks: Optional[int] = None
    stage_index: int
    steps: List[str]
    formula_steps: List[str]
    buyer_requirement_id: Optional[str] = None


class WalletEntryResponse(BaseModel):
    id: str
    entry_type: str
    source: str
    reference: str
    amount: float
    description: str
    is_estimate: bool
    created_at: datetime

    class Config:
        from_attributes = True


class FarmerWalletSummaryResponse(BaseModel):
    input_costs: float
    logistics_fees: float
    estimated_settlement: float
    estimated_payout: float
    entries: List[WalletEntryResponse]


class FarmerNotificationResponse(BaseModel):
    id: str
    type: NotificationType
    message: str
    read_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class FormulaStepsResponse(BaseModel):
    buyer_requirement_id: str
    steps: List[str]
    authored: bool  # False = still the variety template + spec-notes draft


class FormulaStepsUpdate(BaseModel):
    steps: List[str]


class AgronomistTaskResponse(BaseModel):
    id: str
    kind: str
    status: str
    farmer_name: str
    summary: str
    due_at: datetime
    overdue: bool
    created_at: datetime
    completed_at: Optional[datetime] = None
    notes: Optional[str] = None


class AgronomistTaskComplete(BaseModel):
    notes: Optional[str] = None



class MarketplaceItemResponse(BaseModel):
    id: str
    kind: ListingKind
    title: str
    description: str
    vendor_id: str
    vendor_name: str
    vendor_owned: bool
    price: float
    unit: str
    pricing_basis: PricingBasis
    quantity_noun: str
    needs_date: bool
    icon: str
    image_url: Optional[str] = None
    quantity_available: Optional[float] = None
    formula_input_type: Optional[FormulaInputType] = None
    category: Optional[str] = None


class MarketplaceTab(BaseModel):
    kind: ListingKind
    label: str


class MarketplaceCatalogueResponse(BaseModel):
    tabs: List[MarketplaceTab]
    items: List[MarketplaceItemResponse]
    delivery_sla_days: int


class MarketplaceLineCreate(BaseModel):
    listing_id: str
    quantity: float
    requested_date: Optional[date] = None


class MarketplaceOrderCreate(BaseModel):
    lines: List[MarketplaceLineCreate]
    production_formula_id: Optional[str] = None  # links the orders to a buyer order for reconciliation


class MarketplaceOrderResult(BaseModel):
    checkout_ref: str
    orders: List[InputOrderResponse]
    total: float
    delivery_sla_days: int
    message: str



class FormulaPrefillLine(BaseModel):
    listing_id: str
    title: str
    quantity: float
    reason: str


class FormulaPrefillResponse(BaseModel):
    production_formula_id: Optional[str]
    label: Optional[str]
    lines: List[FormulaPrefillLine]
