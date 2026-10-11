"""
Fleet + logistics events (CEO demo brief §7).

Every logistics state change calls one emit_* function here, which records
a LogisticsEvent with two texts: `detail` (internal, may name people) and
`public_text` (aggregate, anonymised -- region, centre, vehicle code,
tonnes, crop -- never a name or phone number). The public landing-page
ticker serves public_text verbatim, so anonymisation happens once, here.
"""

import re
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import (
    Vehicle, VehicleType, VehicleStatus, LogisticsEvent, LogisticsEventKind, FulfilmentCentre, Crop,
    DispatchJob, MechanisationRequest, HarvestPickupRequest, InputOrder, InputOrderLine, Product, Listing,
    ListingCategory, ListingKind,
    BuyerRequirement, User, TrunkingJob, FulfilmentIntake, FarmerCrop, GradeResult,
)

# code, type -- pilot fleet (PRD 1.1: 3-5 tricycles) plus one trunking truck
SEED_VEHICLES = [
    ("Tricycle #1", VehicleType.TRICYCLE),
    ("Tricycle #2", VehicleType.TRICYCLE),
    ("Tricycle #3", VehicleType.TRICYCLE),
    ("Tricycle #4", VehicleType.TRICYCLE),
    ("Vehicle #07", VehicleType.TRUCK),
]


def seed_vehicles(db: Session) -> None:
    if db.query(Vehicle).count():
        return
    hq = db.query(FulfilmentCentre).filter(FulfilmentCentre.is_hq.is_(True)).first()
    if hq is None:
        return
    for code, vtype in SEED_VEHICLES:
        db.add(Vehicle(code=code, vehicle_type=vtype, home_centre_id=hq.id))
    db.commit()
    print(f"Seeded {len(SEED_VEHICLES)} fleet vehicles at {hq.town}.")


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

def resolve_vehicle(db: Session, label: Optional[str]) -> Optional[Vehicle]:
    """Matches a dispatcher's label ("#1", "Tricycle #1", "Vehicle #07") to a fleet vehicle, if one exists."""
    if not label:
        return None
    label = label.strip()
    v = db.query(Vehicle).filter(func.lower(Vehicle.code) == label.lower()).first()
    if v:
        return v
    m = re.fullmatch(r"#?0*(\d+)", label)
    if m:
        n = int(m.group(1))
        for v in db.query(Vehicle).all():
            vm = re.search(r"#0*(\d+)$", v.code)
            if vm and int(vm.group(1)) == n:
                return v
    return None


def vehicle_name(db: Session, vehicle_id: Optional[str], label: Optional[str]) -> str:
    if vehicle_id:
        v = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
        if v:
            return v.code
    if label:
        return f"Tricycle {label}" if label.startswith("#") else label
    return "A Farm Master vehicle"


def hq_centre(db: Session) -> Optional[FulfilmentCentre]:
    return db.query(FulfilmentCentre).filter(FulfilmentCentre.is_hq.is_(True)).first()


def centre_for_farmer(db: Session, farmer: Optional[User]) -> Optional[FulfilmentCentre]:
    """The farmer's regional centre if it's active, else head office."""
    if farmer and farmer.region_id:
        c = (
            db.query(FulfilmentCentre)
            .filter(FulfilmentCentre.region_id == farmer.region_id, FulfilmentCentre.is_active.is_(True))
            .first()
        )
        if c:
            return c
    return hq_centre(db)


def crop_for_pickup(db: Session, pickup: HarvestPickupRequest) -> Optional[Crop]:
    if pickup.buyer_requirement_id:
        req = db.query(BuyerRequirement).filter(BuyerRequirement.id == pickup.buyer_requirement_id).first()
        if req:
            c = db.query(Crop).filter(Crop.name == req.crop).first()
            if c:
                return c
    fc = db.query(FarmerCrop).filter(FarmerCrop.farmer_id == pickup.farmer_id).first()
    if fc:
        return db.query(Crop).filter(Crop.id == fc.crop_id).first()
    return db.query(Crop).filter(Crop.name == "Maize").first()


def _region_phrase(farmer: Optional[User]) -> str:
    return f" in {farmer.region.name}" if farmer and farmer.region else ""


def _t(x: float) -> str:
    return f"{x:,.1f}".rstrip("0").rstrip(".")


# ---------------------------------------------------------------------------
# Emitters
# ---------------------------------------------------------------------------

def _emit(db: Session, kind: LogisticsEventKind, public_text: str, detail: str, **links) -> LogisticsEvent:
    ev = LogisticsEvent(kind=kind, public_text=public_text, detail=detail, **links)
    db.add(ev)
    db.commit()
    return ev


def _job_context(db: Session, job: DispatchJob):
    if job.input_order_id:
        order = db.query(InputOrder).filter(InputOrder.id == job.input_order_id).first()
        farmer = db.query(User).filter(User.id == order.farmer_id).first()
        names = sorted({_line_kind_label(db, line)
                        for line in db.query(InputOrderLine).filter(InputOrderLine.input_order_id == order.id).all()})
        what = " and ".join(names) if names else "farm inputs"
        return "input", farmer, what, None
    if job.mechanisation_request_id:
        req = db.query(MechanisationRequest).filter(MechanisationRequest.id == job.mechanisation_request_id).first()
        return "service", None, f"a {req.service.lower()} crew", req.buyer_requirement_id
    pickup = db.query(HarvestPickupRequest).filter(HarvestPickupRequest.id == job.harvest_pickup_request_id).first()
    farmer = db.query(User).filter(User.id == pickup.farmer_id).first()
    return "pickup", farmer, pickup, pickup.buyer_requirement_id


def _line_kind_label(db: Session, line: InputOrderLine) -> str:
    """Anonymised, generic description of what a line delivers."""
    if line.listing_id:
        listing = db.query(Listing).filter(Listing.id == line.listing_id).first()
        if listing is None:
            return "farm inputs"
        if listing.kind == ListingKind.EQUIPMENT:
            return "rented equipment"
        if listing.kind == ListingKind.SERVICE:
            return "a service crew"
        cat = db.query(ListingCategory).filter(ListingCategory.id == listing.category_id).first()
        return cat.name.lower() if cat else "farm inputs"
    p = db.query(Product).filter(Product.id == line.product_id).first() if line.product_id else None
    return p.category.value.replace("_", " ") if p else "farm inputs"


def emit_dispatch_en_route(db: Session, job: DispatchJob) -> LogisticsEvent:
    kind, farmer, what, req_id = _job_context(db, job)
    v = vehicle_name(db, job.vehicle_id, job.tricycle_label)
    if kind == "pickup":
        centre = centre_for_farmer(db, farmer)
        public = (f"Live: {v} collecting a {_t(what.quantity_ready_tonnes)} t harvest{_region_phrase(farmer)} "
                  f"for {centre.town if centre else 'Tema'} fulfilment centre.")
        detail = f"{v} dispatched to collect {farmer.full_name}'s harvest ({what.quantity_ready_tonnes} t)."
        return _emit(db, LogisticsEventKind.PICKUP_EN_ROUTE, public, detail, dispatch_job_id=job.id,
                     vehicle_id=job.vehicle_id, buyer_requirement_id=req_id, tonnes=what.quantity_ready_tonnes,
                     fulfilment_centre_id=centre.id if centre else None)
    ek = LogisticsEventKind.INPUT_EN_ROUTE if kind == "input" else LogisticsEventKind.SERVICE_EN_ROUTE
    public = f"Live: {v} en route with {what} for 1 farm{_region_phrase(farmer)}."
    detail = f"{v} dispatched with {what}" + (f" for {farmer.full_name}." if farmer else ".")
    return _emit(db, ek, public, detail, dispatch_job_id=job.id, vehicle_id=job.vehicle_id, buyer_requirement_id=req_id)


def emit_dispatch_delivered(db: Session, job: DispatchJob) -> LogisticsEvent:
    kind, farmer, what, req_id = _job_context(db, job)
    v = vehicle_name(db, job.vehicle_id, job.tricycle_label)
    if kind == "pickup":
        centre = centre_for_farmer(db, farmer)
        town = centre.town if centre else "Tema"
        public = f"Live: harvest pickup completed — {_t(what.quantity_ready_tonnes)} t delivered to {town} fulfilment centre."
        detail = f"{v} delivered {farmer.full_name}'s harvest ({what.quantity_ready_tonnes} t) to {town}."
        return _emit(db, LogisticsEventKind.PICKUP_DELIVERED, public, detail, dispatch_job_id=job.id,
                     vehicle_id=job.vehicle_id, buyer_requirement_id=req_id, tonnes=what.quantity_ready_tonnes,
                     fulfilment_centre_id=centre.id if centre else None)
    ek = LogisticsEventKind.INPUT_DELIVERED if kind == "input" else LogisticsEventKind.SERVICE_DELIVERED
    if kind == "input":
        public = f"Live: {what[0].upper() + what[1:]} delivered to the farm gate{_region_phrase(farmer)}."
    else:
        public = f"Live: {what[0].upper() + what[1:]} finished work at a farm{_region_phrase(farmer)}."
    detail = f"{v} delivered {what}" + (f" to {farmer.full_name}." if farmer else ".")
    return _emit(db, ek, public, detail, dispatch_job_id=job.id, vehicle_id=job.vehicle_id, buyer_requirement_id=req_id)


def emit_intake_graded(db: Session, intake: FulfilmentIntake, pickup: HarvestPickupRequest) -> Optional[LogisticsEvent]:
    if intake.grade == GradeResult.REJECT:
        return None
    centre = db.query(FulfilmentCentre).filter(FulfilmentCentre.id == intake.fulfilment_centre_id).first()
    crop = db.query(Crop).filter(Crop.id == intake.crop_id).first()
    tonnes = intake.weigh_in_kg / 1000.0
    crop_name = crop.name.lower() if crop else "produce"
    town = centre.town if centre else "Tema"
    public = f"Live: Fulfilment centre — {town} graded {_t(tonnes)} t of {crop_name} into stock."
    return _emit(db, LogisticsEventKind.INTAKE_GRADED, public,
                 f"Intake {intake.id}: {tonnes} t {crop_name}, grade {intake.grade.value}, at {town}.",
                 fulfilment_centre_id=intake.fulfilment_centre_id, crop_id=intake.crop_id, tonnes=tonnes,
                 buyer_requirement_id=pickup.buyer_requirement_id)


def emit_trunking(db: Session, job: TrunkingJob, delivered: bool) -> LogisticsEvent:
    origin = db.query(FulfilmentCentre).filter(FulfilmentCentre.id == job.origin_centre_id).first() or hq_centre(db)
    v = vehicle_name(db, job.vehicle_id, job.vehicle_label)
    if delivered:
        public = f"Live: {_t(job.produce_tonnes)} t of graded produce arrived at {job.destination}."
        kind = LogisticsEventKind.TRUNKING_DELIVERED
    else:
        public = (f"Live: {v} trunking {_t(job.produce_tonnes)} t of graded produce from "
                  f"{origin.town if origin else 'Tema'} to {job.destination}.")
        kind = LogisticsEventKind.TRUNKING_DISPATCHED
    return _emit(db, kind, public, f"Trunking job {job.id}: {public[6:]}", trunking_job_id=job.id,
                 vehicle_id=job.vehicle_id, tonnes=job.produce_tonnes,
                 fulfilment_centre_id=origin.id if origin else None)


def emit_order_progress(db: Session, req: BuyerRequirement, delivered: bool) -> LogisticsEvent:
    crop = req.crop.lower()
    if delivered:
        kind, public = LogisticsEventKind.ORDER_DELIVERED, f"Live: a {_t(req.quantity_tonnes)} t {crop} order was delivered to its buyer."
    else:
        kind, public = LogisticsEventKind.ORDER_SHIPPED, f"Live: a {_t(req.quantity_tonnes)} t {crop} order is in transit to its buyer."
    return _emit(db, kind, public, f"{req.reference}: {public[6:]}", buyer_requirement_id=req.id, tonnes=req.quantity_tonnes)


# ---------------------------------------------------------------------------
# Public feed
# ---------------------------------------------------------------------------

def aggregated_today(db: Session, today: Optional[datetime] = None):
    """Tonnes graded (non-reject) per centre per crop since midnight -- the brief's aggregation record."""
    start = (today or datetime.utcnow()).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = (
        db.query(FulfilmentIntake.fulfilment_centre_id, FulfilmentIntake.crop_id, func.sum(FulfilmentIntake.weigh_in_kg))
        .filter(FulfilmentIntake.created_at >= start, FulfilmentIntake.grade != GradeResult.REJECT)
        .group_by(FulfilmentIntake.fulfilment_centre_id, FulfilmentIntake.crop_id)
        .all()
    )
    out = []
    for centre_id, crop_id, kg in rows:
        centre = db.query(FulfilmentCentre).filter(FulfilmentCentre.id == centre_id).first() if centre_id else hq_centre(db)
        crop = db.query(Crop).filter(Crop.id == crop_id).first() if crop_id else None
        out.append((centre, crop, (kg or 0) / 1000.0))
    return out


def public_activity(db: Session, limit: int = 10) -> List[dict]:
    lines = []
    for centre, crop, tonnes in aggregated_today(db):
        if tonnes > 0:
            lines.append({
                "text": f"Live: Fulfilment centre — {centre.town if centre else 'Tema'} has aggregated "
                        f"{_t(tonnes)} tonnes of {crop.name.lower() if crop else 'produce'} today.",
                "at": datetime.utcnow(),
            })
    hour_ago = datetime.utcnow() - timedelta(hours=1)
    recent_pickups = (
        db.query(LogisticsEvent)
        .filter(LogisticsEvent.kind == LogisticsEventKind.PICKUP_DELIVERED, LogisticsEvent.created_at >= hour_ago)
        .count()
    )
    if recent_pickups > 1:
        lines.append({"text": f"Live: {recent_pickups} harvest pickups completed in the last hour.", "at": datetime.utcnow()})
    for ev in db.query(LogisticsEvent).order_by(LogisticsEvent.created_at.desc()).limit(limit).all():
        lines.append({"text": ev.public_text, "at": ev.created_at})
    return lines[:limit]
