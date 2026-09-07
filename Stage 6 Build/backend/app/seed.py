"""
Creates all tables and seeds one user per role plus the provisional rate
config rows. Safe to re-run -- skips seeding if data already exists.

DEV-ONLY CREDENTIALS: every seeded password below is "password123" purely
so the pilot can be exercised locally. This is not a production credential
and must never be reused as one.
"""

from datetime import datetime

from .database import Base, engine, SessionLocal
from .models import (
    User, Role, UserStatus, RateConfig, Opportunity, OpportunityStatus, MechanisationRequest,
    MechanisationRequestStatus, BuyerRequirement, RequirementStatus,
    HarvestPickupRequest, DispatchJobStatus, FulfilmentIntake, GradeResult,
    CommitmentFeePayment, PaymentStatus, Product, ProductCategory, FormulaInputType,
    InputOrder, InputOrderLine, InputOrderStatus,
)
from .auth import hash_password
from .dispatch import create_dispatch_job, create_inbound_dispatch_job, create_input_order_dispatch_job

# Formula Builder demo data -- a requirement already past Matching Queue
# assignment (status PRODUCTION, real Opportunity rows with
# assigned_farmer_id set), so the screen has something real to build a
# formula for on first run, same treatment as SEED_REQUIREMENTS below for
# the Matching Queue.
SEED_ASSIGNED_REQUIREMENT = (
    # buyer_email, grade, quantity_tonnes, price_per_tonne, delivery_location, delivery_timeline
    "buyer@farmmaster.test", "Grade 1", 5.0, 2200, "Tema", "25 Sep 2026",
)
SEED_ASSIGNED_FARMERS = ["kojo.mensah@farmmaster.test", "ama.serwaa@farmmaster.test"]

# Phone numbers added 5 Sep 2026 alongside real-time OTP verification (PRD
# Section 12) -- login OTP is simulated but still generated per real user,
# so every seeded account needs a phone to "send" to, same as it needs an
# email. Dev-only placeholder numbers, Ghanaian mobile format.
SEED_USERS = [
    ("emmanuel@farmmaster.test", "Emmanuel", Role.SUPER_ADMIN, None, "+233241000001"),
    ("finance@farmmaster.test", "Kojo Antwi", Role.FINANCE, None, "+233241000002"),
    ("agronomist@farmmaster.test", "Kwabena Osei", Role.AGRONOMIST, None, "+233241000003"),
    ("logistics@farmmaster.test", "Abena Owusu", Role.LOGISTICS, None, "+233241000004"),
    ("buyer@farmmaster.test", "Tema Grain Processors Ltd.", Role.BUYER, "Tema Grain Processors Ltd.", "+233241000005"),
    ("gsfp@farmmaster.test", "Ghana School Feeding Programme", Role.BUYER, "Ghana School Feeding Programme", "+233241000006"),
    ("coastal@farmmaster.test", "Coastal Feed Mills", Role.BUYER, "Coastal Feed Mills", "+233241000007"),
    ("farmer@farmmaster.test", "Kofi Mensah", Role.FARMER, None, "+233241000008"),
    ("kojo.mensah@farmmaster.test", "Kojo Mensah", Role.FARMER, None, "+233241000009"),
    ("ama.serwaa@farmmaster.test", "Ama Serwaa", Role.FARMER, None, "+233241000010"),
    ("vendor@farmmaster.test", "Kwame's Agro Supplies", Role.VENDOR, "Kwame's Agro Supplies", "+233241000011"),
]

SEED_OPPORTUNITIES = [
    ("Ghana School Feeding Programme", "MoFA-linked", "Grade 1", 4.0, 2100, "12 Sep 2026"),
    ("Tema Grain Processors Ltd.", "Private buyer", "Grade 1", 6.5, 2200, "15 Sep 2026"),
    ("Coastal Feed Mills", "Private buyer", "Grade 2", 2.0, 2050, "18 Sep 2026"),
]

# Matching Queue demo data -- buyer requirements that have already paid their
# commitment fee (status MATCHING) and are waiting for an Agronomist to
# assign farmers. Distinct tonnage/price from SEED_OPPORTUNITIES above so
# assigning them doesn't read as a duplicate of an opportunity that's
# already open (these are new, separate orders from repeat buyers).
SEED_REQUIREMENTS = [
    # buyer_email, grade, quantity_tonnes, price_per_tonne, delivery_location, delivery_timeline
    ("gsfp@farmmaster.test", "Grade 1", 3.0, 2150, "Tema", "20 Sep 2026"),
    ("coastal@farmmaster.test", "Grade 2", 1.5, 2075, "Tema", "22 Sep 2026"),
]

SEED_MECH_REQUESTS = [
    # farmer_name, service, area_acres, requested_by_date (5/3/7 days from 3 Sep 2026, matching Stage 5)
    ("Kojo Mensah", "Ploughing", 1.5, "2026-09-08"),
    ("Ama Serwaa", "Ridging", 1.0, "2026-09-06"),
    ("Yaw Boateng", "Harrowing", 2.2, "2026-09-10"),
]

# Fulfilment Intake / Logistics inbound demo data -- one pickup already
# DELIVERED (so the Fulfilment Intake queue has something to grade) and one
# still ASSIGNED (so the Logistics Dispatch inbound tab isn't always empty
# either), same treatment as every other screen's seed data.
SEED_HARVEST_PICKUPS = [
    # farmer_email, quantity_ready_tonnes, preferred_pickup_date, deliver_immediately
    ("farmer@farmmaster.test", 3.8, "2026-09-12", True),
    ("kojo.mensah@farmmaster.test", 2.5, "2026-09-14", False),
]

# Vendor Product Catalogue demo data -- matches the Stage 3 wireframe's own
# five example items exactly (name, category, unit price, stock). Three
# carry a formula_input_type so the Farmer Order Inputs screen can pre-fill
# quantities from a real ProductionFormula (seed_kg -> SEED, npk_bags ->
# NPK, topdress_bags -> TOPDRESS); the other two are OTHER (not part of the
# production formula, ordered freely).
SEED_PRODUCTS = [
    # name, category, formula_input_type, unit, unit_price, stock_qty
    ("Maize seed — improved variety", ProductCategory.SEED, FormulaInputType.SEED, "kg", 18.0, 240.0),
    ("NPK Fertiliser 15-15-15", ProductCategory.FERTILISER, FormulaInputType.NPK, "bag", 320.0, 85.0),
    ("Sulphate of Ammonia", ProductCategory.FERTILISER, FormulaInputType.TOPDRESS, "bag", 210.0, 60.0),
    ("Pre-emergence herbicide", ProductCategory.CROP_PROTECTION, FormulaInputType.OTHER, "litre", 95.0, 30.0),
    ("Hand tools bundle", ProductCategory.TOOLS, FormulaInputType.OTHER, "set", 140.0, 22.0),
]

SEED_RATES = [
    ("buyer_commitment_fee_per_tonne", 90.0, "GHS/tonne",
     "Buyer commitment fee. Matches Stage 5 prototype and PRD Section 10."),
    ("vendor_service_fee_per_tonne", 60.0, "GHS/tonne",
     "Vendor mechanisation service fee. Applied per-acre in the Stage 5 prototype pending a tonnage "
     "field on mechanisation requests -- see PRD Section 10."),
    ("formula_seed_kg_per_tonne", 1.6, "kg/tonne",
     "Farmer production formula input scaling. AGRONOMICALLY UNVERIFIED -- see PRD Section 10."),
    ("formula_npk_tonnes_per_bag", 2.0, "tonnes/bag",
     "1 NPK bag per this many tonnes, rounded up. AGRONOMICALLY UNVERIFIED."),
    ("formula_topdress_tonnes_per_bag", 4.0, "tonnes/bag",
     "1 top-dress bag per this many tonnes, rounded up. AGRONOMICALLY UNVERIFIED."),
    ("trading_margin_pct", 0.15, "fraction",
     "Farm Master's aggregation & trade margin, as a fraction of buyer invoice value on delivered, "
     "graded (non-reject) tonnage. BUSINESS-UNCONFIRMED, pending Emmanuel's sign-off -- no rate or "
     "formula for this exists anywhere in the PRD (Section 10) or Business Concept doc; see "
     "Farm_Master_SDD_Stage6.docx Section 18."),
]


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            for email, name, role, org, phone in SEED_USERS:
                db.add(User(
                    email=email,
                    full_name=name,
                    phone=phone,
                    role=role,
                    status=UserStatus.ACTIVE,
                    password_hash=hash_password("password123"),
                    organisation_name=org,
                ))
            db.commit()
            print(f"Seeded {len(SEED_USERS)} users (all passwords: password123 -- dev only).")
        else:
            print("Users already exist, skipping user seed.")

        if db.query(RateConfig).count() == 0:
            for key, value, unit, note in SEED_RATES:
                db.add(RateConfig(key=key, value=value, unit=unit, status="PROVISIONAL", note=note))
            db.commit()
            print(f"Seeded {len(SEED_RATES)} rate config rows (all PROVISIONAL).")
        else:
            print("Rate config already exists, skipping rate seed.")

        if db.query(BuyerRequirement).count() == 0:
            fee_rate = db.query(RateConfig).filter(RateConfig.key == "buyer_commitment_fee_per_tonne").first()
            rate = fee_rate.value if fee_rate else 90.0
            for buyer_email, grade, qty, price, location, timeline in SEED_REQUIREMENTS:
                buyer = db.query(User).filter(User.email == buyer_email).first()
                if not buyer:
                    continue
                db.add(BuyerRequirement(
                    buyer_id=buyer.id, crop="Maize", grade=grade, quantity_tonnes=qty,
                    price_per_tonne=price, delivery_location=location, delivery_timeline=timeline,
                    commitment_fee_amount=round(max(rate, qty * rate), 2),
                    status=RequirementStatus.MATCHING,
                ))
            db.commit()
            print(f"Seeded {len(SEED_REQUIREMENTS)} buyer requirements (Matching Queue demo data).")
        else:
            print("Buyer requirements already exist, skipping requirement seed.")

        if db.query(Opportunity).count() == 0:
            for buyer_name, tag, grade, qty, price, deadline in SEED_OPPORTUNITIES:
                db.add(Opportunity(
                    buyer_name=buyer_name, tag=tag, grade=grade,
                    quantity_tonnes=qty, price_per_tonne=price, deadline=deadline,
                ))
            db.commit()
            print(f"Seeded {len(SEED_OPPORTUNITIES)} opportunities.")
        else:
            print("Opportunities already exist, skipping opportunity seed.")

        # Gated on BuyerRequirement, not Opportunity -- this block adds its
        # own Opportunity rows (for the assigned farmers), which must not be
        # mistaken by the pool-opportunity block above for "already seeded".
        # Keeping this block after that one keeps their count() == 0 checks
        # from cross-contaminating each other.
        if db.query(BuyerRequirement).filter(BuyerRequirement.status == RequirementStatus.PRODUCTION).count() == 0:
            buyer_email, grade, qty, price, location, timeline = SEED_ASSIGNED_REQUIREMENT
            buyer = db.query(User).filter(User.email == buyer_email).first()
            fee_rate = db.query(RateConfig).filter(RateConfig.key == "buyer_commitment_fee_per_tonne").first()
            rate = fee_rate.value if fee_rate else 90.0
            if buyer:
                req = BuyerRequirement(
                    buyer_id=buyer.id, crop="Maize", grade=grade, quantity_tonnes=qty,
                    price_per_tonne=price, delivery_location=location, delivery_timeline=timeline,
                    commitment_fee_amount=round(max(rate, qty * rate), 2),
                    status=RequirementStatus.PRODUCTION,
                )
                db.add(req)
                db.commit()
                db.refresh(req)

                # A real CommitmentFeePayment, not just the commitment_fee_amount
                # field -- this requirement skips buyer.py's own pay flow (it's
                # created pre-assigned, for Formula Builder demo purposes), but
                # Order Reconciliation (PRD Must-Have #5) reads "commitment fee
                # received" from real payment rows, so without this it would
                # show GHS 0 for the one order with real settlement data too.
                db.add(CommitmentFeePayment(
                    requirement_id=req.id, amount=req.commitment_fee_amount, method="momo",
                    status=PaymentStatus.SUCCESS, transaction_ref=f"SIM-{req.id[:8]}",
                ))
                db.commit()

                farmers = db.query(User).filter(User.email.in_(SEED_ASSIGNED_FARMERS)).all()
                share = round(qty / len(farmers), 2) if farmers else qty
                buyer_name = buyer.organisation_name or buyer.full_name
                for farmer in farmers:
                    db.add(Opportunity(
                        buyer_requirement_id=req.id, buyer_name=buyer_name,
                        tag="Buyer requirement match", grade=grade, quantity_tonnes=share,
                        price_per_tonne=price, deadline=timeline, assigned_farmer_id=farmer.id,
                    ))
                db.commit()
                print("Seeded 1 assigned buyer requirement (Formula Builder demo data).")
        else:
            print("An assigned (PRODUCTION) requirement already exists, skipping Formula Builder seed.")

        if db.query(MechanisationRequest).count() == 0:
            vendor = db.query(User).filter(User.role == Role.VENDOR).first()
            # Kojo Mensah's Ploughing request (first in SEED_MECH_REQUESTS)
            # is linked to the PRODUCTION requirement below -- he's one of
            # SEED_ASSIGNED_FARMERS for it, so a real vendor payout can be
            # computed for that order (PRD Must-Have #5, Order
            # Reconciliation demo data).
            production_req = db.query(BuyerRequirement).filter(BuyerRequirement.status == RequirementStatus.PRODUCTION).first()
            if vendor:
                created = []
                for i, (farmer_name, service, area, requested_by) in enumerate(SEED_MECH_REQUESTS):
                    req = MechanisationRequest(
                        vendor_id=vendor.id, farmer_name=farmer_name, service=service,
                        area_acres=area, requested_by_date=requested_by,
                        buyer_requirement_id=production_req.id if i == 0 and production_req else None,
                    )
                    db.add(req)
                    created.append(req)
                db.commit()
                print(f"Seeded {len(SEED_MECH_REQUESTS)} mechanisation requests.")

                # Logistics Dispatch demo data -- confirm the first request
                # (within its own requested window, so no override needed)
                # so the dispatch queue has something real on first run, same
                # treatment as the Matching Queue/Formula Builder seed data
                # above.
                first = created[0]
                db.refresh(first)
                first.confirmed_date = first.requested_by_date
                first.status = MechanisationRequestStatus.CONFIRMED
                db.commit()
                db.refresh(first)
                create_dispatch_job(db, first)
                print("Confirmed 1 mechanisation request and seeded its dispatch job (Logistics Dispatch demo data).")
        else:
            print("Mechanisation requests already exist, skipping seed.")

        if db.query(HarvestPickupRequest).count() == 0:
            for farmer_email, qty, preferred_date, deliver_now in SEED_HARVEST_PICKUPS:
                farmer = db.query(User).filter(User.email == farmer_email).first()
                if not farmer:
                    continue
                req = HarvestPickupRequest(
                    farmer_id=farmer.id, quantity_ready_tonnes=qty, preferred_pickup_date=preferred_date,
                )
                db.add(req)
                db.commit()
                db.refresh(req)
                job = create_inbound_dispatch_job(db, req)
                if deliver_now:
                    job.tricycle_label = "#2"
                    job.status = DispatchJobStatus.DELIVERED
                    job.delivered_at = datetime.utcnow()
                    db.commit()
            print(f"Seeded {len(SEED_HARVEST_PICKUPS)} harvest pickup requests (Fulfilment Intake / Logistics inbound demo data).")
        else:
            print("Harvest pickup requests already exist, skipping seed.")

        # Order Reconciliation demo data (PRD Must-Have #5) -- a pickup
        # linked to the PRODUCTION requirement, already delivered AND
        # graded, so Finance & Reconciliation has real, non-zero farmer
        # settlement/vendor payout figures on first run. Gated on this
        # specific linkage (not HarvestPickupRequest.count(), which the
        # block above already owns) so re-running seed() doesn't duplicate it.
        if db.query(HarvestPickupRequest).filter(HarvestPickupRequest.buyer_requirement_id.isnot(None)).count() == 0:
            production_req = db.query(BuyerRequirement).filter(BuyerRequirement.status == RequirementStatus.PRODUCTION).first()
            kojo = db.query(User).filter(User.email == "kojo.mensah@farmmaster.test").first()
            finance = db.query(User).filter(User.role == Role.FINANCE).first()
            if production_req and kojo and finance:
                # Kojo's opportunity for this requirement was only ASSIGNED
                # by the Matching Queue seed above (assigned_farmer_id), not
                # ACCEPTED -- but farmer.py's real harvest-pickup validation
                # requires an accepted_by match (a farmer can only claim a
                # delivery against an order they actually accepted). Marking
                # it accepted here keeps this seed data consistent with what
                # a real farmer would have to do first, rather than linking
                # the pickup in a state the live API would itself reject.
                kojo_opp = db.query(Opportunity).filter(
                    Opportunity.buyer_requirement_id == production_req.id,
                    Opportunity.assigned_farmer_id == kojo.id,
                ).first()
                if kojo_opp and kojo_opp.accepted_by is None:
                    kojo_opp.status = OpportunityStatus.ACCEPTED
                    kojo_opp.accepted_by = kojo.id
                    kojo_opp.accepted_at = datetime.utcnow()
                    db.commit()

                pickup = HarvestPickupRequest(
                    farmer_id=kojo.id, quantity_ready_tonnes=2.0, preferred_pickup_date="2026-09-16",
                    buyer_requirement_id=production_req.id,
                )
                db.add(pickup)
                db.commit()
                db.refresh(pickup)
                job = create_inbound_dispatch_job(db, pickup)
                job.tricycle_label = "#3"
                job.status = DispatchJobStatus.DELIVERED
                job.delivered_at = datetime.utcnow()
                db.commit()
                db.add(FulfilmentIntake(
                    harvest_pickup_request_id=pickup.id, weigh_in_kg=1950,
                    grade=GradeResult.GRADE_1, graded_by=finance.id,
                ))
                db.commit()
                print("Seeded 1 order-linked, delivered & graded harvest pickup (Order Reconciliation demo data).")
        else:
            print("An order-linked harvest pickup already exists, skipping Order Reconciliation seed.")

        if db.query(Product).count() == 0:
            vendor = db.query(User).filter(User.role == Role.VENDOR).first()
            if vendor:
                for name, category, input_type, unit, price, stock in SEED_PRODUCTS:
                    db.add(Product(
                        vendor_id=vendor.id, name=name, category=category,
                        formula_input_type=input_type, unit=unit, unit_price=price, stock_qty=stock,
                    ))
                db.commit()
                print(f"Seeded {len(SEED_PRODUCTS)} product catalogue items (Order Inputs / Vendor Catalogue demo data).")
        else:
            print("Product catalogue already exists, skipping catalogue seed.")

        # Order Inputs demo data (PRD Must-Have #3's literal scope) -- Ama
        # Serwaa orders seed + NPK from the seeded catalogue, the vendor
        # confirms it, and a real outbound DispatchJob is created, so the
        # Vendor's input-order queue, the Farmer's order history, and the
        # Logistics Dispatch outbound tab (third job_type) all have real
        # data on first run, same treatment as every other feature above.
        if db.query(InputOrder).count() == 0:
            ama = db.query(User).filter(User.email == "ama.serwaa@farmmaster.test").first()
            vendor = db.query(User).filter(User.role == Role.VENDOR).first()
            seed_product = db.query(Product).filter(Product.formula_input_type == FormulaInputType.SEED).first()
            npk_product = db.query(Product).filter(Product.formula_input_type == FormulaInputType.NPK).first()
            if ama and vendor and seed_product and npk_product:
                seed_qty, npk_qty = 8.0, 2.0
                order = InputOrder(
                    farmer_id=ama.id, vendor_id=vendor.id,
                    total_cost=round(seed_qty * seed_product.unit_price + npk_qty * npk_product.unit_price, 2),
                )
                db.add(order)
                db.commit()
                db.refresh(order)
                db.add(InputOrderLine(input_order_id=order.id, product_id=seed_product.id, quantity=seed_qty, unit_price=seed_product.unit_price))
                db.add(InputOrderLine(input_order_id=order.id, product_id=npk_product.id, quantity=npk_qty, unit_price=npk_product.unit_price))
                seed_product.stock_qty -= seed_qty
                npk_product.stock_qty -= npk_qty
                order.status = InputOrderStatus.CONFIRMED
                db.commit()
                db.refresh(order)
                create_input_order_dispatch_job(db, order)
                print("Seeded 1 confirmed input order with a real dispatch job (Order Inputs demo data).")
        else:
            print("Input orders already exist, skipping Order Inputs seed.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
