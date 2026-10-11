"""
Reference data -- regions, fulfilment centres, crops/varieties, farmer
unions (CEO demo brief §2A-C, §8). Added 11 Oct 2026.

Everything here is data, not code: the pilot configuration (Greater Accra /
Tema, Maize only) is just which rows have is_active / is_active_for_ordering
set, and Super Admin flips them from the admin endpoints with no deploy.
"""

from typing import List

from sqlalchemy.orm import Session

from .models import (
    Region, FulfilmentCentre, Crop, CropVariety, FarmerUnion, FarmerCrop, User, Role,
    BuyerType, VendorOwnership,
)

# name, code, fulfilment-centre town, is_hq, active in pilot
SEED_REGIONS = [
    ("Greater Accra", "GA", "Tema", True, True),
    ("Ashanti", "AS", "Kumasi", False, False),
    ("Northern", "NR", "Tamale", False, False),
    ("Eastern", "ER", "Koforidua", False, False),
    ("Central", "CR", "Cape Coast", False, False),
    ("Western", "WR", "Takoradi", False, False),
    ("Western North", "WN", "Sefwi Wiawso", False, False),
    ("Volta", "VR", "Ho", False, False),
    ("Oti", "OT", "Dambai", False, False),
    ("Bono", "BO", "Sunyani", False, False),
    ("Bono East", "BE", "Techiman", False, False),
    ("Ahafo", "AH", "Goaso", False, False),
    ("Savannah", "SV", "Damongo", False, False),
    ("North East", "NE", "Nalerigu", False, False),
    ("Upper East", "UE", "Bolgatanga", False, False),
    ("Upper West", "UW", "Wa", False, False),
]

# name, slug, icon, active for ordering, reference GHS/tonne, [(variety, description)]
# Reference prices for the inactive crops are PROVISIONAL placeholders
# (BUSINESS-UNCONFIRMED) -- they only pre-fill the buyer's target price once
# Super Admin activates the crop, and are editable from admin.
SEED_CROPS = [
    ("Maize", "maize", "maize", True, 2150.0, [("Obatanpa", "improved")]),
    ("White Rice", "white-rice", "rice", False, 4200.0, [("Jasmine 85", None)]),
    ("Soybean", "soybean", "soybean", False, 3800.0, [("Jenguma", None)]),
    ("Tomato", "tomato", "tomato", False, 3000.0, [("Pectomech", None)]),
]

# Default production-formula steps per variety -- the CEO demo's own checklist
# text, AGRONOMICALLY UNVERIFIED like the rest of the formula maths (PRD 10).
SEED_FORMULA_TEMPLATES = {
    "Obatanpa": [
        "Obatanpa variety, 75cm x 40cm spacing, planted in week {planting_week}",
        "NPK 15-15-15 at planting, top-dress at week {topdress_week}",
        "Harvest around week {harvest_week} at 13% moisture, Grade A bagging",
    ],
    "Jenguma": [
        "Jenguma variety, inoculated seed required",
        "Single basal fertiliser application",
        "Delivery in jute sacks, moisture below 12%",
    ],
    "Pectomech": [
        "Pectomech variety, staked rows",
        "Weekly fungicide rotation per agronomist schedule",
        "Harvest at breaker stage for transport",
    ],
    "Jasmine 85": [
        "Jasmine 85 variety, transplanted at 20cm x 20cm",
        "NPK at transplanting, urea top-dress at week {topdress_week}",
        "Harvest at 20-22% grain moisture, dry to 14% before milling",
    ],
}

SEED_UNIONS = ["Tema Smallholder Farmers Union", "Nsawam Farmer Union"]

# Profile backfill for the seeded accounts -- region/crops/union for farmers,
# buyer type for buyers, ownership for vendors.
SEED_FARMER_PROFILES = {
    # email: (region name, union name or None, [crop names])
    "farmer@farmmaster.test": ("Greater Accra", None, ["Maize"]),
    "kojo.mensah@farmmaster.test": ("Greater Accra", "Tema Smallholder Farmers Union", ["Maize"]),
    "ama.serwaa@farmmaster.test": ("Greater Accra", "Tema Smallholder Farmers Union", ["Maize"]),
}
SEED_BUYER_PROFILES = {
    # email: (buyer type, MoFA-verified)
    "buyer@farmmaster.test": (BuyerType.PRIVATE, False),
    "gsfp@farmmaster.test": (BuyerType.INSTITUTIONAL, True),
    "coastal@farmmaster.test": (BuyerType.PRIVATE, False),
}
SEED_VENDOR_PROFILES = {"vendor@farmmaster.test": VendorOwnership.THIRD_PARTY}


def seed_reference_data(db: Session) -> None:
    if db.query(Region).count() == 0:
        for name, code, town, is_hq, active in SEED_REGIONS:
            region = Region(name=name, code=code, is_active=active)
            db.add(region)
            db.flush()
            centre_name = "Tema Head Office & Fulfilment Centre" if is_hq else f"{town} Fulfilment Centre"
            db.add(FulfilmentCentre(name=centre_name, town=town, region_id=region.id, is_hq=is_hq, is_active=active))
        db.commit()
        print(f"Seeded {len(SEED_REGIONS)} regions and fulfilment centres (Greater Accra/Tema active).")

    if db.query(Crop).count() == 0:
        for i, (name, slug, icon, active, price, varieties) in enumerate(SEED_CROPS):
            crop = Crop(name=name, slug=slug, icon=icon, is_active_for_ordering=active,
                        reference_price_per_tonne=price, display_order=i)
            db.add(crop)
            db.flush()
            for vname, desc in varieties:
                steps = SEED_FORMULA_TEMPLATES.get(vname)
                db.add(CropVariety(crop_id=crop.id, name=vname, description=desc,
                                   default_formula_steps="\n".join(steps) if steps else None))
        db.commit()
        print(f"Seeded {len(SEED_CROPS)} crops (Maize active for ordering).")

    # Backfill templates onto varieties seeded before templates existed.
    for v in db.query(CropVariety).filter(CropVariety.default_formula_steps.is_(None)).all():
        if v.name in SEED_FORMULA_TEMPLATES:
            v.default_formula_steps = "\n".join(SEED_FORMULA_TEMPLATES[v.name])
    db.commit()

    if db.query(FarmerUnion).count() == 0:
        for name in SEED_UNIONS:
            db.add(FarmerUnion(name=name))
        db.commit()

    regions = {r.name: r for r in db.query(Region).all()}
    unions = {u.name: u for u in db.query(FarmerUnion).all()}
    crops = {c.name: c for c in db.query(Crop).all()}
    changed = False
    for email, (region_name, union_name, crop_names) in SEED_FARMER_PROFILES.items():
        user = db.query(User).filter(User.email == email).first()
        if not user or user.region_id:
            continue
        user.region_id = regions[region_name].id
        user.farmer_union_id = unions[union_name].id if union_name else None
        for cname in crop_names:
            db.add(FarmerCrop(farmer_id=user.id, crop_id=crops[cname].id))
        changed = True
    for email, (btype, mofa) in SEED_BUYER_PROFILES.items():
        user = db.query(User).filter(User.email == email).first()
        if user and user.buyer_type is None:
            user.buyer_type, user.mofa_verified = btype, mofa
            changed = True
    for email, ownership in SEED_VENDOR_PROFILES.items():
        user = db.query(User).filter(User.email == email).first()
        if user and user.vendor_ownership is None:
            user.vendor_ownership = ownership
            changed = True
    if changed:
        db.commit()
        print("Backfilled seeded account profiles (region, union, crops, buyer type, vendor ownership).")


# ---------------------------------------------------------------------------
# Query helpers shared by routers
# ---------------------------------------------------------------------------

def active_crops(db: Session) -> List[Crop]:
    return (
        db.query(Crop).filter(Crop.is_active_for_ordering.is_(True))
        .order_by(Crop.display_order, Crop.name).all()
    )


def farmer_crop_ids(db: Session, farmer: User) -> List[str]:
    return [fc.crop_id for fc in db.query(FarmerCrop).filter(FarmerCrop.farmer_id == farmer.id).all()]


def profile_line(user: User) -> str:
    """The portal header's "Signed in as …" line, built from real profile data."""
    if user.role == Role.FARMER:
        parts = [user.full_name]
        if user.farmer_union:
            parts.append(user.farmer_union.name)
        if user.region:
            parts.append(f"{user.region.name} Region")
        return " · ".join(parts)
    if user.role == Role.BUYER:
        kind = {BuyerType.INSTITUTIONAL: "Institutional buyer", BuyerType.PRIVATE: "Private buyer"}.get(user.buyer_type, "Buyer")
        return f"{user.organisation_name or user.full_name} · {kind}"
    if user.role == Role.VENDOR:
        kind = {VendorOwnership.OWNED: "Farm Master-owned vendor", VendorOwnership.THIRD_PARTY: "Third-party vendor"}.get(user.vendor_ownership, "Vendor")
        return f"{user.organisation_name or user.full_name} · {kind}"
    return f"{user.full_name} · {user.role.value.replace('_', ' ').title()}"
