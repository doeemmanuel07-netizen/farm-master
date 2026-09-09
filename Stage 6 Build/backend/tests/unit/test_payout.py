"""
Unit tests for app/payout.py's compute_vendor_payout_rows -- the Vendor
Payout Statement's backend (Stage 6, added 8 Sep 2026). Mirrors
test_wallet.py's isolation checks but for the vendor side: one vendor's
payout rows must never include another vendor's mechanisation/input-order
activity, even against the same buyer order.
"""

import pytest

from app.models import Role
from app.payout import compute_vendor_payout_rows
from tests.factories import (
    make_requirement, make_confirmed_mechanisation_request, make_accepted_opportunity,
    make_formula, make_product, make_confirmed_input_order,
)

pytestmark = pytest.mark.unit


def test_no_activity_means_empty_payout_list(db_session, rate_config, make_user):
    vendor = make_user(Role.VENDOR)
    rows = compute_vendor_payout_rows(db_session, vendor.id)
    assert rows == []


def test_mechanisation_only_payout(db_session, rate_config, make_user):
    buyer = make_user(Role.BUYER)
    vendor = make_user(Role.VENDOR)
    req = make_requirement(db_session, buyer)
    make_confirmed_mechanisation_request(db_session, vendor, requirement=req, area_acres=2.0)
    rows = compute_vendor_payout_rows(db_session, vendor.id)
    assert len(rows) == 1
    assert rows[0].mechanisation_amount == 120.0  # 2.0 acres * 60 GHS/tonne placeholder rate
    assert rows[0].input_order_amount == 0
    assert rows[0].total == 120.0
    assert rows[0].released is False


def test_two_vendors_same_order_do_not_see_each_others_payout(db_session, rate_config, make_user):
    buyer = make_user(Role.BUYER)
    vendor_a = make_user(Role.VENDOR)
    vendor_b = make_user(Role.VENDOR)
    req = make_requirement(db_session, buyer)

    make_confirmed_mechanisation_request(db_session, vendor_a, requirement=req, area_acres=1.0)
    make_confirmed_mechanisation_request(db_session, vendor_b, requirement=req, area_acres=3.0)

    rows_a = compute_vendor_payout_rows(db_session, vendor_a.id)
    rows_b = compute_vendor_payout_rows(db_session, vendor_b.id)

    assert len(rows_a) == 1 and rows_a[0].total == 60.0
    assert len(rows_b) == 1 and rows_b[0].total == 180.0


def test_input_order_amount_included_via_formula_chain(db_session, rate_config, make_user):
    buyer = make_user(Role.BUYER)
    farmer = make_user(Role.FARMER)
    vendor = make_user(Role.VENDOR)
    req = make_requirement(db_session, buyer)

    opp = make_accepted_opportunity(db_session, farmer, requirement=req, quantity_tonnes=4.0)
    formula = make_formula(db_session, opp, farmer)
    product = make_product(db_session, vendor, unit_price=25.0)
    make_confirmed_input_order(db_session, farmer, vendor, product, quantity=4.0, production_formula=formula)

    rows = compute_vendor_payout_rows(db_session, vendor.id)
    assert len(rows) == 1
    assert rows[0].input_order_amount == 100.0
    assert rows[0].mechanisation_amount == 0
    assert rows[0].total == 100.0


def test_released_flag_reflects_real_order_reconciliation_row(db_session, rate_config, make_user):
    from app.models import OrderReconciliation
    from datetime import datetime

    buyer = make_user(Role.BUYER)
    vendor = make_user(Role.VENDOR)
    req = make_requirement(db_session, buyer)
    make_confirmed_mechanisation_request(db_session, vendor, requirement=req, area_acres=1.0)

    recon = OrderReconciliation(
        buyer_requirement_id=req.id, vendor_payout_released=True,
        vendor_payout_released_by=vendor.id, vendor_payout_released_at=datetime.utcnow(),
    )
    db_session.add(recon)
    db_session.commit()

    rows = compute_vendor_payout_rows(db_session, vendor.id)
    assert len(rows) == 1
    assert rows[0].released is True
    assert rows[0].released_at is not None
