"""
Farmer opportunity-acceptance + production-formula flow -- the real backend
behind farmer_opportunity_formula_flow_live.html.

Closes a gap flagged during the Stage 5 retrospective: the USSD/SMS design
noted "whichever channel accepts first wins" for opportunity acceptance but
the interactive prototype couldn't actually enforce it (single-user, no
server). This backend does -- see accept_opportunity's status check, which
is a real 409 for a second acceptance attempt, not just a documented intent.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Role, RateConfig, Opportunity, OpportunityStatus, ProductionFormula
from ..auth import require_roles
from ..schemas import OpportunityResponse, AcceptOpportunityRequest, ProductionFormulaResponse

router = APIRouter(prefix="/farmer", tags=["farmer"])


def _get_rate(db: Session, key: str) -> float:
    row = db.query(RateConfig).filter(RateConfig.key == key).first()
    if not row:
        raise HTTPException(status_code=500, detail=f"Rate config '{key}' is not seeded.")
    return row.value


@router.get("/opportunities", response_model=List[OpportunityResponse])
def list_opportunities(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FARMER)),
):
    return db.query(Opportunity).filter(Opportunity.status == OpportunityStatus.OPEN).all()


@router.get("/opportunities/{opportunity_id}", response_model=OpportunityResponse)
def get_opportunity(
    opportunity_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FARMER)),
):
    opp = db.query(Opportunity).filter(Opportunity.id == opportunity_id).first()
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found.")
    return opp


@router.post("/opportunities/{opportunity_id}/accept", response_model=ProductionFormulaResponse)
def accept_opportunity(
    opportunity_id: str,
    payload: AcceptOpportunityRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FARMER)),
):
    if not payload.commitments_confirmed:
        raise HTTPException(status_code=422, detail="All commitment items must be confirmed before accepting.")

    opp = db.query(Opportunity).filter(Opportunity.id == opportunity_id).first()
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found.")
    if opp.status != OpportunityStatus.OPEN:
        # This is the real enforcement of "whichever channel accepts first wins"
        # flagged as untested in the Stage 5 retrospective -- a second farmer
        # (or the same farmer via a second tab/channel) genuinely cannot accept
        # an opportunity that's already gone.
        raise HTTPException(status_code=409, detail="This opportunity has already been accepted.")

    opp.status = OpportunityStatus.ACCEPTED
    opp.accepted_by = user.id
    from datetime import datetime
    opp.accepted_at = datetime.utcnow()

    scaling_seed = _get_rate(db, "formula_seed_kg_per_tonne")
    scaling_npk = _get_rate(db, "formula_npk_tonnes_per_bag")
    scaling_topdress = _get_rate(db, "formula_topdress_tonnes_per_bag")

    import math
    formula = ProductionFormula(
        opportunity_id=opp.id,
        farmer_id=user.id,
        seed_kg=round(opp.quantity_tonnes * scaling_seed, 1),
        npk_bags=math.ceil(opp.quantity_tonnes / scaling_npk),
        topdress_bags=max(1, math.ceil(opp.quantity_tonnes / scaling_topdress)),
    )
    db.add(formula)
    db.commit()
    db.refresh(formula)
    return formula


@router.get("/formulas/mine", response_model=List[ProductionFormulaResponse])
def my_formulas(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FARMER)),
):
    return db.query(ProductionFormula).filter(ProductionFormula.farmer_id == user.id).order_by(ProductionFormula.created_at.desc()).all()
