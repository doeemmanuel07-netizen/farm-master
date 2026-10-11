"""
Farmer-facing marketplace (CEO demo brief §6.1, decision D1).

Listings are the one catalogue. A cart may mix vendors and kinds; placing
it creates one InputOrder per vendor (sharing a checkout_ref), reserves
stock on stock-tracked inputs, posts the debit to the farmer's wallet
ledger, and turns any agronomist-visit line into an agronomist task. Each
vendor then confirms its own order in the existing back-office queue,
which creates the logistics job -- the same handoff as before.
"""

import uuid
from collections import OrderedDict
from datetime import date, datetime, time, timedelta
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .audit import log_audit
from .models import (
    Listing, ListingKind, ListingStatus, ListingImage, ListingCategory, PricingBasis, User, VendorOwnership,
    InputOrder, InputOrderLine, Product, AgronomistTask, AgronomistTaskKind, Notification, NotificationType,
    RateConfig,
)

KIND_LABEL = {
    ListingKind.INPUT: "Seeds & Inputs",
    ListingKind.EQUIPMENT: "Equipment Rental",
    ListingKind.SERVICE: "Mechanisation Services",
}
BASIS_NOUN = {
    PricingBasis.PER_UNIT: ("unit", "units"),
    PricingBasis.PER_DAY: ("day", "days"),
    PricingBasis.PER_ACRE: ("acre", "acres"),
    PricingBasis.PER_VISIT: ("visit", "visits"),
}
# Icon for a card with no photo, by category name, when the listing sets none.
CATEGORY_ICON = {"seeds": "seed", "fertilizer": "fertiliser", "crop protection": "bottle", "equipment": "tractor", "services": "plough"}
AGRONOMIST_VISIT = "agronomist_visit"


def needs_date(listing: Listing) -> bool:
    return listing.kind in (ListingKind.EQUIPMENT, ListingKind.SERVICE)


def item_view(db: Session, listing: Listing):
    from .schemas import MarketplaceItemResponse

    vendor = db.query(User).filter(User.id == listing.vendor_id).first()
    category = db.query(ListingCategory).filter(ListingCategory.id == listing.category_id).first()
    image = (
        db.query(ListingImage).filter(ListingImage.listing_id == listing.id)
        .order_by(ListingImage.is_primary.desc(), ListingImage.display_order).first()
    )
    icon = listing.icon or CATEGORY_ICON.get((category.name if category else "").lower(), "box")
    return MarketplaceItemResponse(
        id=listing.id, kind=listing.kind, title=listing.title, description=listing.description,
        vendor_id=listing.vendor_id, vendor_name=(vendor.organisation_name or vendor.full_name) if vendor else "",
        vendor_owned=bool(vendor and vendor.vendor_ownership == VendorOwnership.OWNED),
        price=listing.price, unit=listing.unit, pricing_basis=listing.pricing_basis,
        quantity_noun=BASIS_NOUN[listing.pricing_basis][1], needs_date=needs_date(listing),
        icon=icon, image_url=f"/uploads/{image.file_path}" if image and _real_image(image) else None,
        quantity_available=listing.quantity_available, formula_input_type=listing.formula_input_type,
        category=category.name if category else None,
    )


def _real_image(image: ListingImage) -> bool:
    # The seed's 1x1 placeholder PNG would render as an empty box -- prefer the icon.
    return "placeholder" not in image.file_path


def catalogue(db: Session, kind: Optional[ListingKind] = None) -> List[Listing]:
    q = db.query(Listing).filter(Listing.status == ListingStatus.ACTIVE)
    if kind is not None:
        q = q.filter(Listing.kind == kind)
    return q.order_by(Listing.kind, Listing.price).all()


def delivery_sla_days(db: Session) -> int:
    row = db.query(RateConfig).filter(RateConfig.key == "marketplace_delivery_sla_days").first()
    return int(row.value) if row else 2


def place_order(db: Session, farmer: User, lines) -> List[InputOrder]:
    if not lines:
        raise HTTPException(status_code=422, detail="Your order is empty.")
    merged = OrderedDict()
    for line in lines:
        if line.quantity is None or line.quantity <= 0:
            raise HTTPException(status_code=422, detail="Every quantity must be greater than zero.")
        listing = db.query(Listing).filter(Listing.id == line.listing_id).first()
        if not listing or listing.status != ListingStatus.ACTIVE:
            raise HTTPException(status_code=404, detail="One of the items is no longer available.")
        if needs_date(listing):
            if line.requested_date is None:
                raise HTTPException(status_code=422, detail=f"Choose a date for '{listing.title}'.")
            if line.requested_date < date.today():
                raise HTTPException(status_code=422, detail=f"The date for '{listing.title}' is in the past.")
        key = (listing.id, line.requested_date)
        if key in merged:
            merged[key][1] += line.quantity
        else:
            merged[key] = [listing, line.quantity, line.requested_date]

    reserved = {}
    for listing, qty, _ in merged.values():
        if listing.quantity_available is not None:
            reserved[listing.id] = reserved.get(listing.id, 0) + qty
            if reserved[listing.id] > listing.quantity_available:
                raise HTTPException(status_code=409, detail=f"'{listing.title}' only has {listing.quantity_available:g} available.")

    by_vendor = OrderedDict()
    for item in merged.values():
        by_vendor.setdefault(item[0].vendor_id, []).append(item)

    checkout_ref = f"MKT-{uuid.uuid4().hex[:8].upper()}"
    orders = []
    for vendor_id, items in by_vendor.items():
        order = InputOrder(
            farmer_id=farmer.id, vendor_id=vendor_id, checkout_ref=checkout_ref,
            total_cost=round(sum(l.price * q for l, q, _ in items), 2),
        )
        db.add(order)
        db.flush()
        for listing, qty, when in items:
            db.add(InputOrderLine(input_order_id=order.id, listing_id=listing.id, quantity=qty,
                                  unit_price=listing.price, requested_date=when))
            if listing.quantity_available is not None:
                listing.quantity_available -= qty
                if listing.quantity_available <= 0:
                    listing.quantity_available = 0
                    listing.status = ListingStatus.OUT_OF_STOCK
            if listing.service_code == AGRONOMIST_VISIT:
                for _ in range(int(round(qty))):
                    db.add(AgronomistTask(
                        kind=AgronomistTaskKind.FARM_VISIT, farmer_id=farmer.id, input_order_id=order.id,
                        summary=f"Farm visit for {farmer.full_name} (booked in the marketplace)",
                        due_at=datetime.combine(when, time(9, 0)),
                    ))
        vendor = db.query(User).filter(User.id == vendor_id).first()
        db.add(Notification(user_id=vendor_id, type=NotificationType.MARKETPLACE_ORDER,
                            message=f"New marketplace order from {farmer.full_name}: GHS {order.total_cost:,.2f}. "
                                    f"Confirm it to hand it to Farm Master logistics."))
        orders.append(order)
    db.commit()
    total = sum(o.total_cost for o in orders)
    log_audit(db, farmer, "marketplace_order_placed",
              f"{checkout_ref}: {len(orders)} vendor order(s), GHS {total:,.2f}.")
    return orders


def restore_listing_stock(db: Session, order: InputOrder) -> None:
    """Undo place_order's reservation when a vendor declines."""
    for line in db.query(InputOrderLine).filter(InputOrderLine.input_order_id == order.id).all():
        if not line.listing_id:
            continue
        listing = db.query(Listing).filter(Listing.id == line.listing_id).first()
        if listing and listing.quantity_available is not None:
            listing.quantity_available += line.quantity
            if listing.status == ListingStatus.OUT_OF_STOCK:
                listing.status = ListingStatus.ACTIVE


def line_label(db: Session, line: InputOrderLine):
    """(name, unit, kind) for an order line from either catalogue."""
    if line.listing_id:
        listing = db.query(Listing).filter(Listing.id == line.listing_id).first()
        if listing:
            return listing.title, listing.unit, listing.kind
        return "(listing removed)", "", None
    product = db.query(Product).filter(Product.id == line.product_id).first() if line.product_id else None
    return (product.name, product.unit, None) if product else ("(product removed)", "", None)


# ---------------------------------------------------------------------------
# Seed: the CEO demo's catalogue (brief §6.1), editable afterwards by the
# vendors themselves and the listing review queue like any other listing.
# ---------------------------------------------------------------------------

OWNED_VENDOR = ("services@farmmaster.test", "Farm Master Services", "+233241000015")
THIRD_PARTY_VENDOR_EMAIL = "vendor@farmmaster.test"
# title, category, kind, basis, price, unit, qty available, icon, formula input, service code, owned?
SEED_MARKETPLACE = [
    ("Improved Maize Seed (Obatanpa)", "Seeds", ListingKind.INPUT, PricingBasis.PER_UNIT, 180.0, "per 10kg bag", 120.0, "seed", None, None, False),
    ("NPK 15-15-15 Fertiliser", "Fertilizer", ListingKind.INPUT, PricingBasis.PER_UNIT, 265.0, "per 50kg bag", 200.0, "fertiliser", "npk", None, False),
    ("Crop Protection — Fungicide", "Crop Protection", ListingKind.INPUT, PricingBasis.PER_UNIT, 95.0, "per litre", 80.0, "bottle", None, None, False),
    ("Tractor with plough — day rate", "Equipment", ListingKind.EQUIPMENT, PricingBasis.PER_DAY, 650.0, "per day", None, "tractor", None, None, True),
    ("Motorised planter — day rate", "Equipment", ListingKind.EQUIPMENT, PricingBasis.PER_DAY, 280.0, "per day", None, "planter", None, None, True),
    ("Water pump set — day rate", "Equipment", ListingKind.EQUIPMENT, PricingBasis.PER_DAY, 150.0, "per day", None, "pump", None, None, True),
    ("Land preparation & ploughing", "Services", ListingKind.SERVICE, PricingBasis.PER_ACRE, 320.0, "per acre", None, "plough", None, None, True),
    ("Mechanised harvesting crew", "Services", ListingKind.SERVICE, PricingBasis.PER_ACRE, 410.0, "per acre", None, "harvester", None, None, True),
    ("Agronomist farm visit", "Services", ListingKind.SERVICE, PricingBasis.PER_VISIT, 120.0, "per visit", None, "clipboard", None, AGRONOMIST_VISIT, True),
]
CATEGORY_KIND = {"equipment": ListingKind.EQUIPMENT, "services": ListingKind.SERVICE}


def seed_marketplace(db: Session) -> None:
    from .auth import hash_password
    from .models import Role, UserStatus, FormulaInputType

    for name in ("Crop Protection",):
        if not db.query(ListingCategory).filter(ListingCategory.name == name).first():
            db.add(ListingCategory(name=name, slug=name.lower().replace(" ", "-")))
    owned = db.query(User).filter(User.email == OWNED_VENDOR[0]).first()
    if owned is None:
        owned = User(email=OWNED_VENDOR[0], full_name=OWNED_VENDOR[1], organisation_name=OWNED_VENDOR[1],
                     phone=OWNED_VENDOR[2], role=Role.VENDOR, status=UserStatus.ACTIVE,
                     password_hash=hash_password("password123"), vendor_ownership=VendorOwnership.OWNED)
        db.add(owned)
    db.commit()

    # Older listings: derive kind / basis from category and unit text.
    for l in db.query(Listing).all():
        cat = db.query(ListingCategory).filter(ListingCategory.id == l.category_id).first()
        kind = CATEGORY_KIND.get((cat.name if cat else "").lower(), ListingKind.INPUT)
        if l.kind != kind and l.kind == ListingKind.INPUT:
            l.kind = kind
        unit = (l.unit or "").lower()
        if l.pricing_basis == PricingBasis.PER_UNIT:
            l.pricing_basis = (PricingBasis.PER_ACRE if "acre" in unit else PricingBasis.PER_DAY if "day" in unit
                               else PricingBasis.PER_VISIT if "visit" in unit else PricingBasis.PER_UNIT)
    db.commit()

    if db.query(Listing).filter(Listing.title == SEED_MARKETPLACE[3][0]).first():
        return
    third_party = db.query(User).filter(User.email == THIRD_PARTY_VENDOR_EMAIL).first()
    reviewer = db.query(User).filter(User.role == Role.SUPER_ADMIN).first()
    cats = {c.name: c for c in db.query(ListingCategory).all()}
    added = 0
    for title, cat, kind, basis, price, unit, qty, icon, ftype, code, is_owned in SEED_MARKETPLACE:
        vendor = owned if is_owned else third_party
        if vendor is None or cat not in cats:
            continue
        db.add(Listing(
            vendor_id=vendor.id, category_id=cats[cat].id, title=title,
            description=f"{title}, delivered to the farm gate by Farm Master logistics.",
            price=price, unit=unit, quantity_available=qty, region="Tema", status=ListingStatus.ACTIVE,
            kind=kind, pricing_basis=basis, icon=icon, service_code=code,
            formula_input_type=FormulaInputType(ftype) if ftype else None,
            reviewed_by=reviewer.id if reviewer else None, reviewed_at=datetime.utcnow(),
        ))
        added += 1
    db.commit()
    print(f"Seeded {added} marketplace listings from the CEO demo catalogue.")
