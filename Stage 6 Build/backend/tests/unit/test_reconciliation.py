"""
Unit tests for app/reconciliation.py's compute_figures -- PRD Section 6
Must-Have #5. This is the single most financially consequential function
in the codebase (commitment fee, farmer settlement, vendor payout, trading
margin all flow through it), so it gets the most exhaustive direct
coverage, independent of the API layer.
"""

import pytest

from app.models import Role, GradeResult
from app.reconciliation import compute_figures
from tests.factories import (
    make_requirement, make_payment, make_accepted_opportunity, make_formula,
    make_confirmed_mechanisation_request, make_delivered_graded_pickup,
    make_product, make_confirmed_input_order,
)

pytestmark = pytest.mark.unit


def test_commitment_fee_only_sums_success_payments(db_session, rate_config, make_user):
    buyer = make_user(Role.BUYER)
    req = make_requirement(db_session, buyer)
    make_payment(db_session, req, amount=450.0)
    figures = compute_figures(db_session, req)
    assert figures.commitment_fee_received == 450.0


def test_no_delivered_tonnage_means_zero_everything_downstream(db_session, rate_config, make_user):
    buyer = make_user(Role.BUYER)
    req = make_requirement(db_session, buyer)
    figures = compute_figures(db_session, req)
    assert figures.accepted_delivered_tonnes == 0
    assert figures.buyer_invoice_value == 0
    assert figures.farmer_settlement_due == 0
    assert figures.vendor_payout_due == 0


def test_reject_graded_tonnage_excluded_from_delivered_total(db_session, rate_config, make_user):
    buyer = make_user(Role.BUYER)
    farmer = make_user(Role.FARMER)
    finance = make_user(Role.FINANCE)
    req = make_requirement(db_session, buyer, price_per_tonne=2200.0)
    make_delivered_graded_pickup(db_session, farmer, finance, requirement=req, weigh_in_kg=1000.0, grade=GradeResult.REJECT)
    figures = compute_figures(db_session, req)
    assert figures.accepted_delivered_tonnes == 0
    assert figures.buyer_invoice_value == 0


def test_grade_1_and_grade_2_both_count_toward_delivered_tonnage(db_session, rate_config, make_user):
    buyer = make_user(Role.BUYER)
    farmer1 = make_user(Role.FARMER)
    farmer2 = make_user(Role.FARMER)
    finance = make_user(Role.FINANCE)
    req = make_requirement(db_session, buyer, price_per_tonne=2000.0)
    make_delivered_graded_pickup(db_session, farmer1, finance, requirement=req, weigh_in_kg=1000.0, grade=GradeResult.GRADE_1)
    make_delivered_graded_pickup(db_session, farmer2, finance, requirement=req, weigh_in_kg=500.0, grade=GradeResult.GRADE_2)
    figures = compute_figures(db_session, req)
    assert figures.accepted_delivered_tonnes == 1.5
    assert figures.buyer_invoice_value == 3000.0  # 1.5t * 2000/t


def test_trading_margin_and_farmer_settlement_split_correctly(db_session, rate_config, make_user):
    buyer = make_user(Role.BUYER)
    farmer = make_user(Role.FARMER)
    finance = make_user(Role.FINANCE)
    req = make_requirement(db_session, buyer, price_per_tonne=2000.0)
    make_delivered_graded_pickup(db_session, farmer, finance, requirement=req, weigh_in_kg=1000.0, grade=GradeResult.GRADE_1)
    figures = compute_figures(db_session, req)
    # trading_margin_pct fixture = 0.15 -> invoice 2000 * 0.15 = 300 margin, 1700 to farmer
    assert figures.buyer_invoice_value == 2000.0
    assert figures.trading_margin_amount == 300.0
    assert figures.farmer_settlement_due == 1700.0


def test_vendor_payout_sums_mechanisation_and_input_order_both(db_session, rate_config, make_user):
    """
    Regression test for the real bug fixed 7 September 2026: vendor payout
    previously only read confirmed MechanisationRequest rows, silently
    excluding a confirmed InputOrder's real cost. This test fails if that
    regresses.
    """
    buyer = make_user(Role.BUYER)
    farmer = make_user(Role.FARMER)
    vendor = make_user(Role.VENDOR)
    req = make_requirement(db_session, buyer)

    make_confirmed_mechanisation_request(db_session, vendor, requirement=req, area_acres=1.5)
    # vendor_service_fee_per_tonne = 60.0/tonne applied per-acre (placeholder) -> 1.5 * 60 = 90

    opp = make_accepted_opportunity(db_session, farmer, requirement=req, quantity_tonnes=5.0)
    formula = make_formula(db_session, opp, farmer)
    product = make_product(db_session, vendor, unit_price=100.0)
    make_confirmed_input_order(db_session, farmer, vendor, product, quantity=5.0, production_formula=formula)
    # 5.0 * 100.0 = 500.0

    figures = compute_figures(db_session, req)
    assert figures.vendor_payout_due == 590.0  # 90 (mechanisation) + 500 (input order)


def test_vendor_payout_excludes_pending_mechanisation_request(db_session, rate_config, make_user):
    """Only CONFIRMED requests count -- a pending one must not leak into the payout figure."""
    from app.models import MechanisationRequest, MechanisationRequestStatus

    buyer = make_user(Role.BUYER)
    vendor = make_user(Role.VENDOR)
    req = make_requirement(db_session, buyer)
    pending = MechanisationRequest(
        vendor_id=vendor.id, buyer_requirement_id=req.id, farmer_name="X", service="Ploughing",
        area_acres=2.0, requested_by_date="2026-09-30", status=MechanisationRequestStatus.PENDING,
    )
    db_session.add(pending)
    db_session.commit()

    figures = compute_figures(db_session, req)
    assert figures.vendor_payout_due == 0


def test_input_order_not_linked_to_this_order_is_excluded(db_session, rate_config, make_user):
    """An InputOrder whose formula traces to a DIFFERENT buyer_requirement_id must not bleed into this order's payout."""
    buyer1 = make_user(Role.BUYER)
    buyer2 = make_user(Role.BUYER)
    farmer = make_user(Role.FARMER)
    vendor = make_user(Role.VENDOR)
    req1 = make_requirement(db_session, buyer1)
    req2 = make_requirement(db_session, buyer2)

    opp_for_req2 = make_accepted_opportunity(db_session, farmer, requirement=req2, quantity_tonnes=3.0)
    formula = make_formula(db_session, opp_for_req2, farmer)
    product = make_product(db_session, vendor, unit_price=50.0)
    make_confirmed_input_order(db_session, farmer, vendor, product, quantity=3.0, production_formula=formula)

    figures_req1 = compute_figures(db_session, req1)
    assert figures_req1.vendor_payout_due == 0

    figures_req2 = compute_figures(db_session, req2)
    assert figures_req2.vendor_payout_due == 150.0
