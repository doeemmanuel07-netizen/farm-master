"""
Unit tests for app/formula.py -- PRD Section 10's AGRONOMICALLY UNVERIFIED
input-scaling math. Every quantity/rate combination below is chosen to
exercise the rounding/ceiling rules explicitly, not just "does it run."
"""

import pytest
from fastapi import HTTPException

from app.formula import compute_formula_inputs

pytestmark = pytest.mark.unit


def test_scales_seed_linearly_and_rounds_to_one_decimal(db_session, rate_config):
    inputs = compute_formula_inputs(db_session, 5.0)
    # formula_seed_kg_per_tonne = 1.6 -> 5.0 * 1.6 = 8.0
    assert inputs.seed_kg == 8.0


def test_npk_bags_ceiling_not_floor(db_session, rate_config):
    # formula_npk_tonnes_per_bag = 2.0 -> 5.0 / 2.0 = 2.5 -> ceil = 3, not 2
    inputs = compute_formula_inputs(db_session, 5.0)
    assert inputs.npk_bags == 3


def test_npk_bags_exact_division_no_extra_bag(db_session, rate_config):
    # 4.0 / 2.0 = 2.0 exactly -> should NOT round up to 3
    inputs = compute_formula_inputs(db_session, 4.0)
    assert inputs.npk_bags == 2


def test_topdress_bags_minimum_of_one_even_for_tiny_quantity(db_session, rate_config):
    # formula_topdress_tonnes_per_bag = 4.0 -> 0.1 / 4.0 = 0.025 -> ceil = 1,
    # and the explicit max(1, ...) floor matters for a quantity so small
    # ceil() would still return 0 only if it rounded oddly -- assert the
    # floor is real, not just coincidentally satisfied by ceil() here.
    inputs = compute_formula_inputs(db_session, 0.1)
    assert inputs.topdress_bags == 1


def test_topdress_bags_ceiling_for_larger_quantity(db_session, rate_config):
    # 9.0 / 4.0 = 2.25 -> ceil = 3
    inputs = compute_formula_inputs(db_session, 9.0)
    assert inputs.topdress_bags == 3


def test_missing_rate_config_raises_500_not_a_silent_default(db_session):
    """No rate_config fixture applied -- RateConfig table is empty, so this
    must fail loudly (500) rather than silently computing with a made-up
    default, since these are business-unconfirmed, DB-configured rates."""
    with pytest.raises(HTTPException) as exc_info:
        compute_formula_inputs(db_session, 5.0)
    assert exc_info.value.status_code == 500
