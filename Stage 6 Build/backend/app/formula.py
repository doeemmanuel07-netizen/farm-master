"""
Shared production-formula input scaling -- the single source for the
RateConfig-backed math (PRD Section 10, AGRONOMICALLY UNVERIFIED) used by
both a farmer's individual acceptance (routers/farmer.py) and the
Agronomist's Production Formula Builder (routers/agronomist.py), so the two
can never drift apart into two slightly different formulas.
"""

import math
from typing import NamedTuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .models import RateConfig


class FormulaInputs(NamedTuple):
    seed_kg: float
    npk_bags: int
    topdress_bags: int


def _get_rate(db: Session, key: str) -> float:
    row = db.query(RateConfig).filter(RateConfig.key == key).first()
    if not row:
        raise HTTPException(status_code=500, detail=f"Rate config '{key}' is not seeded.")
    return row.value


def compute_formula_inputs(db: Session, quantity_tonnes: float) -> FormulaInputs:
    scaling_seed = _get_rate(db, "formula_seed_kg_per_tonne")
    scaling_npk = _get_rate(db, "formula_npk_tonnes_per_bag")
    scaling_topdress = _get_rate(db, "formula_topdress_tonnes_per_bag")
    return FormulaInputs(
        seed_kg=round(quantity_tonnes * scaling_seed, 1),
        npk_bags=math.ceil(quantity_tonnes / scaling_npk),
        topdress_bags=max(1, math.ceil(quantity_tonnes / scaling_topdress)),
    )
