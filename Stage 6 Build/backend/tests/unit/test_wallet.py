"""
Unit tests for app/wallet.py's compute_farmer_wallet -- the Farmer Wallet &
Settlement Statement's backend (Stage 6, added 8 Sep 2026). A farmer's own
delivered tonnage is directly attributable via HarvestPickupRequest.farmer_id,
so these tests specifically check that one farmer's wallet never leaks
another farmer's share of a shared order.
"""

import pytest

from app.models import Role, GradeResult
from app.wallet import compute_farmer_wallet
from tests.factories import (
    make_requirement, make_accepted_opportunity, make_formula,
    make_delivered_graded_pickup, make_product, make_confirmed_input_order,
)

pytestmark = pytest.mark.unit


def test_empty_wallet_for_farmer_with_no_order_linked_pickups(db_session, rate_config, make_user):
    farmer = make_user(Role.FARMER)
    rows = compute_farmer_wallet(db_session, farmer.id)
    assert rows == []


def test_own_settlement_uses_own_delivered_tonnage_only(db_session, rate_config, make_user):
    buyer = make_user(Role.BUYER)
    farmer_a = make_user(Role.FARMER)
    farmer_b = make_user(Role.FARMER)
    finance = make_user(Role.FINANCE)
    req = make_requirement(db_session, buyer, price_per_tonne=2000.0)

    # Two farmers deliver against the SAME shared order.
    make_delivered_graded_pickup(db_session, farmer_a, finance, requirement=req, weigh_in_kg=1000.0, grade=GradeResult.GRADE_1)
    make_delivered_graded_pickup(db_session, farmer_b, finance, requirement=req, weigh_in_kg=2000.0, grade=GradeResult.GRADE_1)

    rows_a = compute_farmer_wallet(db_session, farmer_a.id)
    rows_b = compute_farmer_wallet(db_session, farmer_b.id)

    assert len(rows_a) == 1
    assert rows_a[0].own_delivered_tonnes == 1.0
    # trading_margin_pct 0.15 -> 1.0t * 2000 * 0.85 = 1700
    assert rows_a[0].own_settlement_due == 1700.0

    assert len(rows_b) == 1
    assert rows_b[0].own_delivered_tonnes == 2.0
    assert rows_b[0].own_settlement_due == 3400.0


def test_reject_graded_pickup_excluded_from_own_delivered_tonnage(db_session, rate_config, make_user):
    buyer = make_user(Role.BUYER)
    farmer = make_user(Role.FARMER)
    finance = make_user(Role.FINANCE)
    req = make_requirement(db_session, buyer)
    make_delivered_graded_pickup(db_session, farmer, finance, requirement=req, weigh_in_kg=1000.0, grade=GradeResult.REJECT)
    rows = compute_farmer_wallet(db_session, farmer.id)
    assert len(rows) == 1
    assert rows[0].own_delivered_tonnes == 0


def test_input_order_costs_scoped_to_this_farmer_and_this_order(db_session, rate_config, make_user):
    buyer = make_user(Role.BUYER)
    farmer = make_user(Role.FARMER)
    finance = make_user(Role.FINANCE)
    vendor = make_user(Role.VENDOR)
    req = make_requirement(db_session, buyer)

    make_delivered_graded_pickup(db_session, farmer, finance, requirement=req, weigh_in_kg=1000.0, grade=GradeResult.GRADE_1)
    opp = make_accepted_opportunity(db_session, farmer, requirement=req, quantity_tonnes=1.0)
    formula = make_formula(db_session, opp, farmer)
    product = make_product(db_session, vendor, unit_price=40.0)
    make_confirmed_input_order(db_session, farmer, vendor, product, quantity=10.0, production_formula=formula)

    rows = compute_farmer_wallet(db_session, farmer.id)
    assert len(rows) == 1
    assert rows[0].input_order_costs == 400.0


def test_unlinked_pickup_no_buyer_requirement_id_produces_no_row(db_session, rate_config, make_user):
    """A general 'extra produce ready' pickup with no buyer_requirement_id must not fabricate a wallet row."""
    from tests.factories import make_undelivered_pickup

    farmer = make_user(Role.FARMER)
    make_undelivered_pickup(db_session, farmer, requirement=None)
    rows = compute_farmer_wallet(db_session, farmer.id)
    assert rows == []
