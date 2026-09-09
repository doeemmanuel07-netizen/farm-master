"""
Composable real-object builders for tests -- the same shapes app/seed.py
builds for the dev demo dataset, but assembled per-test so each test's
data is independent and explicit about what it depends on, rather than
inheriting an implicit, shared, ~20-row demo dataset.
"""

from datetime import datetime

from app.models import (
    BuyerRequirement, RequirementStatus, CommitmentFeePayment, PaymentStatus,
    Opportunity, OpportunityStatus, ProductionFormula, MechanisationRequest,
    MechanisationRequestStatus, HarvestPickupRequest, DispatchJob, DispatchDirection,
    DispatchJobStatus, FulfilmentIntake, GradeResult, Product, ProductCategory,
    FormulaInputType, InputOrder, InputOrderLine, InputOrderStatus,
)
from app.dispatch import create_dispatch_job, create_inbound_dispatch_job, create_input_order_dispatch_job
from app.formula import compute_formula_inputs


def make_requirement(db, buyer, status=RequirementStatus.MATCHING, quantity_tonnes=5.0, price_per_tonne=2200.0, grade="Grade 1", fee=450.0):
    req = BuyerRequirement(
        buyer_id=buyer.id, crop="Maize", grade=grade, quantity_tonnes=quantity_tonnes,
        price_per_tonne=price_per_tonne, delivery_location="Tema", delivery_timeline="30 Sep 2026",
        commitment_fee_amount=fee, status=status,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def make_payment(db, requirement, amount=None, method="momo"):
    payment = CommitmentFeePayment(
        requirement_id=requirement.id, amount=amount if amount is not None else requirement.commitment_fee_amount,
        method=method, status=PaymentStatus.SUCCESS, transaction_ref=f"SIM-{requirement.id[:8]}",
    )
    db.add(payment)
    db.commit()
    return payment


def make_accepted_opportunity(db, farmer, requirement=None, quantity_tonnes=2.0, price_per_tonne=2200.0, grade="Grade 1", buyer_name="Test Buyer"):
    opp = Opportunity(
        buyer_requirement_id=requirement.id if requirement else None,
        buyer_name=buyer_name, tag="Buyer requirement match", grade=grade,
        quantity_tonnes=quantity_tonnes, price_per_tonne=price_per_tonne, deadline="30 Sep 2026",
        status=OpportunityStatus.ACCEPTED, assigned_farmer_id=farmer.id,
        accepted_by=farmer.id, accepted_at=datetime.utcnow(),
    )
    db.add(opp)
    db.commit()
    db.refresh(opp)
    return opp


def make_formula(db, opportunity, farmer):
    inputs = compute_formula_inputs(db, opportunity.quantity_tonnes)
    formula = ProductionFormula(
        opportunity_id=opportunity.id, farmer_id=farmer.id,
        seed_kg=inputs.seed_kg, npk_bags=inputs.npk_bags, topdress_bags=inputs.topdress_bags,
    )
    db.add(formula)
    db.commit()
    db.refresh(formula)
    return formula


def make_confirmed_mechanisation_request(db, vendor, requirement=None, area_acres=1.5, farmer_name="Test Farmer"):
    req = MechanisationRequest(
        vendor_id=vendor.id, buyer_requirement_id=requirement.id if requirement else None,
        farmer_name=farmer_name, service="Ploughing", area_acres=area_acres,
        requested_by_date="2026-09-30", confirmed_date="2026-09-25",
        status=MechanisationRequestStatus.CONFIRMED,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    create_dispatch_job(db, req)
    return req


def make_delivered_graded_pickup(db, farmer, finance_user, requirement=None, weigh_in_kg=1900.0, grade=GradeResult.GRADE_1, quantity_ready_tonnes=2.0):
    pickup = HarvestPickupRequest(
        farmer_id=farmer.id, buyer_requirement_id=requirement.id if requirement else None,
        quantity_ready_tonnes=quantity_ready_tonnes, preferred_pickup_date="2026-09-20",
    )
    db.add(pickup)
    db.commit()
    db.refresh(pickup)
    job = create_inbound_dispatch_job(db, pickup)
    job.tricycle_label = "#1"
    job.status = DispatchJobStatus.DELIVERED
    job.delivered_at = datetime.utcnow()
    db.commit()
    intake = FulfilmentIntake(
        harvest_pickup_request_id=pickup.id, weigh_in_kg=weigh_in_kg, grade=grade, graded_by=finance_user.id,
    )
    db.add(intake)
    db.commit()
    db.refresh(intake)
    return pickup, job, intake


def make_undelivered_pickup(db, farmer, requirement=None, quantity_ready_tonnes=1.0):
    pickup = HarvestPickupRequest(
        farmer_id=farmer.id, buyer_requirement_id=requirement.id if requirement else None,
        quantity_ready_tonnes=quantity_ready_tonnes, preferred_pickup_date="2026-09-22",
    )
    db.add(pickup)
    db.commit()
    db.refresh(pickup)
    job = create_inbound_dispatch_job(db, pickup)
    return pickup, job


def make_product(db, vendor, name="Maize seed", category=ProductCategory.SEED, input_type=FormulaInputType.SEED, unit="kg", unit_price=18.0, stock_qty=200.0):
    product = Product(
        vendor_id=vendor.id, name=name, category=category, formula_input_type=input_type,
        unit=unit, unit_price=unit_price, stock_qty=stock_qty,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def make_confirmed_input_order(db, farmer, vendor, product, quantity=5.0, production_formula=None):
    total_cost = round(quantity * product.unit_price, 2)
    order = InputOrder(
        farmer_id=farmer.id, vendor_id=vendor.id,
        production_formula_id=production_formula.id if production_formula else None,
        total_cost=total_cost, status=InputOrderStatus.CONFIRMED,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    db.add(InputOrderLine(input_order_id=order.id, product_id=product.id, quantity=quantity, unit_price=product.unit_price))
    product.stock_qty -= quantity
    db.commit()
    create_input_order_dispatch_job(db, order)
    return order
