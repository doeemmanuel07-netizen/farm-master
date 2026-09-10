"""
Farmer/Buyer-facing Vendor Listing browse + search -- added 10 Sep 2026
alongside the Vendor Listing approval workflow (see models.Listing).

Gated to Role.FARMER/Role.BUYER rather than left truly unauthenticated,
matching this codebase's own RBAC-everywhere convention (PRD Section 5:
"enforced at the data layer, not just the UI") -- no route anywhere else in
this API skips authentication either. Category listing is opened to Vendor
too, since the same category set feeds the "Add New Listing" category
picker (routers/vendor.py's create_listing).

Every query here reads straight from the database on each request -- no
caching layer of any kind exists anywhere in this codebase, so an admin
approval/rejection or a vendor's own status toggle is reflected on this
endpoint's very next call, with nothing to invalidate.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Role, Listing, ListingStatus, ListingCategory
from ..auth import require_roles
from ..listings import listing_view
from ..schemas import ListingResponse, ListingCategoryResponse

router = APIRouter(prefix="/listings", tags=["listings (Farmer/Buyer browse)"])


@router.get("/categories", response_model=List[ListingCategoryResponse])
def list_active_categories(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FARMER, Role.BUYER, Role.VENDOR)),
):
    return db.query(ListingCategory).filter(ListingCategory.active.is_(True)).order_by(ListingCategory.name.asc()).all()


@router.get("", response_model=List[ListingResponse])
def browse_listings(
    category_id: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    vendor_id: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    q: Optional[str] = Query(None, description="Keyword search over title and description."),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FARMER, Role.BUYER)),
):
    """
    Only ever returns ACTIVE listings -- draft/pending/rejected/out-of-stock/
    archived rows are never visible here, regardless of filters. A listing
    marked OUT_OF_STOCK deliberately still won't show, since it isn't
    currently available to buy, matching a real Jiji-style browse's own
    behaviour for a sold-out ad.
    """
    query = db.query(Listing).filter(Listing.status == ListingStatus.ACTIVE)
    if category_id:
        query = query.filter(Listing.category_id == category_id)
    if region:
        query = query.filter(Listing.region.ilike(f"%{region}%"))
    if vendor_id:
        query = query.filter(Listing.vendor_id == vendor_id)
    if min_price is not None:
        query = query.filter(Listing.price >= min_price)
    if max_price is not None:
        query = query.filter(Listing.price <= max_price)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Listing.title.ilike(like), Listing.description.ilike(like)))

    listings = query.order_by(Listing.updated_at.desc()).all()
    return [listing_view(db, l) for l in listings]


@router.get("/{listing_id}", response_model=ListingResponse)
def get_listing(
    listing_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FARMER, Role.BUYER)),
):
    listing = db.query(Listing).filter(Listing.id == listing_id, Listing.status == ListingStatus.ACTIVE).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found.")
    return listing_view(db, listing)
