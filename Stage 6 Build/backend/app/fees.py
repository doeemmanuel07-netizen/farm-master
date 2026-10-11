"""
Buyer commitment-fee calculation (CEO demo brief §2D, decision D3).

The fee is a rule, not a constant: the single active CommitmentFeeRule row
says whether it is a rate per tonne or a percentage of order value, and its
minimum. The seeded rule is PRD Section 10's GH₵ 90/tonne with a one-tonne
(GH₵ 90) minimum -- identical to the hard-coded max(rate, qty * rate) this
replaces, so no existing figure changes.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from .models import CommitmentFeeRule, FeeBasis


class FeeRuleMissing(RuntimeError):
    pass


@dataclass
class FeeQuote:
    amount: float
    rule_name: str
    basis: FeeBasis
    rate: float
    minimum_amount: float
    explanation: str


def active_fee_rule(db: Session) -> CommitmentFeeRule:
    rule = db.query(CommitmentFeeRule).filter(CommitmentFeeRule.is_active.is_(True)).first()
    if rule is None:
        raise FeeRuleMissing("No active commitment fee rule is configured.")
    return rule


def compute_fee(rule: CommitmentFeeRule, quantity_tonnes: float, price_per_tonne: float) -> FeeQuote:
    if rule.basis == FeeBasis.PER_TONNE:
        raw = quantity_tonnes * rule.rate
        how = f"GH₵ {rule.rate:,.2f} per tonne × {quantity_tonnes:g} t"
    else:
        raw = quantity_tonnes * price_per_tonne * rule.rate
        how = f"{rule.rate * 100:g}% of order value (GH₵ {quantity_tonnes * price_per_tonne:,.2f})"
    amount = round(max(rule.minimum_amount, raw), 2)
    if amount > round(raw, 2):
        how += f", raised to the GH₵ {rule.minimum_amount:,.2f} minimum"
    return FeeQuote(
        amount=amount, rule_name=rule.name, basis=rule.basis, rate=rule.rate,
        minimum_amount=rule.minimum_amount, explanation=how,
    )


def quote_commitment_fee(db: Session, quantity_tonnes: float, price_per_tonne: float) -> FeeQuote:
    return compute_fee(active_fee_rule(db), quantity_tonnes, price_per_tonne)


def seed_fee_rule(db: Session) -> None:
    if db.query(CommitmentFeeRule).count():
        return
    db.add(CommitmentFeeRule(
        name="PRD §10 provisional: GH₵ 90 per tonne, one-tonne minimum",
        basis=FeeBasis.PER_TONNE, rate=90.0, minimum_amount=90.0, is_active=True,
    ))
    db.commit()
    print("Seeded the default commitment fee rule (GH₵ 90/t, GH₵ 90 minimum).")
