"""
Shared Listing response-building -- single call site for the vendor's own
listings (routers/vendor.py), the admin approval queue (routers/admin.py),
and the public Farmer/Buyer browse endpoint (routers/listings.py), same
"integrate, don't duplicate" pattern as catalogue.py/formula.py/dispatch.py.

Also home to the small set of status-transition rules shared by more than
one router (what counts as a "core field" edit that must re-route an
already-approved listing back to pending_review, and which statuses a
listing must be in before submission/status-toggle/archive are allowed) --
kept here rather than duplicated between vendor.py's create/update/submit/
toggle endpoints.
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from .models import User, Listing, ListingImage, ListingCategory, ListingStatus
from .schemas import ListingResponse, ListingImageResponse

# Editing any of these fields on an ACTIVE/OUT_OF_STOCK/REJECTED listing
# resets it to PENDING_REVIEW (Emmanuel's decision, 10 Sep 2026) -- images
# are handled separately (upload/delete endpoints trigger the same
# re-review, see routers/vendor.py) since they aren't part of ListingUpdate.
CORE_FIELDS = {"title", "description", "category_id", "listing_type", "price", "unit", "quantity_available", "region"}

# Statuses in which a listing is considered "published" (was, or currently
# is, admin-approved) -- editing a core field from any of these re-triggers
# review. DRAFT and PENDING_REVIEW are excluded: a draft was never reviewed
# yet, and a pending listing simply gets its still-unreviewed content
# updated in place, no reset needed.
REVIEW_RESET_STATUSES = {ListingStatus.ACTIVE, ListingStatus.OUT_OF_STOCK, ListingStatus.REJECTED}


def listing_view(db: Session, listing: Listing) -> ListingResponse:
    vendor = db.query(User).filter(User.id == listing.vendor_id).first()
    category = db.query(ListingCategory).filter(ListingCategory.id == listing.category_id).first()
    images = (
        db.query(ListingImage)
        .filter(ListingImage.listing_id == listing.id)
        .order_by(ListingImage.display_order.asc())
        .all()
    )
    return ListingResponse(
        id=listing.id,
        vendor_id=listing.vendor_id,
        vendor_name=(vendor.organisation_name or vendor.full_name) if vendor else "(vendor removed)",
        category_id=listing.category_id,
        category_name=category.name if category else "(category removed)",
        title=listing.title,
        description=listing.description,
        listing_type=listing.listing_type,
        price=listing.price,
        unit=listing.unit,
        quantity_available=listing.quantity_available,
        region=listing.region,
        status=listing.status,
        rejection_reason=listing.rejection_reason,
        reviewed_by=listing.reviewed_by,
        reviewed_at=listing.reviewed_at,
        images=[
            ListingImageResponse(id=i.id, url=f"/uploads/{i.file_path}", display_order=i.display_order, is_primary=i.is_primary)
            for i in images
        ],
        created_at=listing.created_at,
        updated_at=listing.updated_at,
    )


def apply_core_field_update(listing: Listing, payload) -> bool:
    """
    Applies a ListingUpdate payload's fields onto `listing` and returns
    whether any CORE_FIELDS value actually changed (as opposed to being
    re-submitted unchanged) -- only a real change re-triggers review.
    """
    changed = False
    for field in CORE_FIELDS:
        new_value = getattr(payload, field)
        if getattr(listing, field) != new_value:
            setattr(listing, field, new_value)
            changed = True
    return changed


def maybe_reset_to_pending_review(listing: Listing) -> None:
    if listing.status in REVIEW_RESET_STATUSES:
        listing.status = ListingStatus.PENDING_REVIEW
        listing.rejection_reason = None
        listing.reviewed_by = None
        listing.reviewed_at = None
