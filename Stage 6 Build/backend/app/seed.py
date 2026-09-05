"""
Creates all tables and seeds one user per role plus the provisional rate
config rows. Safe to re-run -- skips seeding if data already exists.

DEV-ONLY CREDENTIALS: every seeded password below is "password123" purely
so the pilot can be exercised locally. This is not a production credential
and must never be reused as one.
"""

from .database import Base, engine, SessionLocal
from .models import (
    User, Role, UserStatus, RateConfig, Opportunity, MechanisationRequest,
    MechanisationRequestStatus, BuyerRequirement, RequirementStatus,
)
from .auth import hash_password
from .dispatch import create_dispatch_job

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
            if vendor:
                created = []
                for farmer_name, service, area, requested_by in SEED_MECH_REQUESTS:
                    req = MechanisationRequest(
                        vendor_id=vendor.id, farmer_name=farmer_name, service=service,
                        area_acres=area, requested_by_date=requested_by,
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
    finally:
        db.close()


if __name__ == "__main__":
    seed()
