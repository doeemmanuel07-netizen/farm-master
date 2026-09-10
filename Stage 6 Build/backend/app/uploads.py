"""
Real file storage for Listing images -- the first real file upload in this
codebase (see models.ListingImage for why every earlier "photo capture"
flow stayed a boolean flag instead). Stored on local disk under
UPLOADS_DIR/listings/<listing_id>/, served back by main.py's /uploads
StaticFiles mount. No cloud object storage is wired up (no provider chosen,
same "gateway TBD" status as payments/OTP/SMS elsewhere in this codebase) --
swapping this for S3/GCS later only touches this one module.
"""

import os
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

UPLOADS_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"

ALLOWED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB


def save_listing_image(listing_id: str, upload: UploadFile) -> str:
    """
    Validates content-type and size, writes the file to disk, and returns
    the path (relative to UPLOADS_DIR) to store on ListingImage.file_path.
    Raises HTTPException(422) on an invalid file rather than silently
    accepting it -- matches this codebase's existing validate-then-act
    style (e.g. vendor.py's add_catalogue_item price/stock checks).
    """
    ext = ALLOWED_CONTENT_TYPES.get(upload.content_type)
    if not ext:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported image type '{upload.content_type}'. Allowed: JPEG, PNG, WEBP.",
        )

    contents = upload.file.read()
    if len(contents) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=422, detail="Image exceeds the 5 MB limit.")
    if len(contents) == 0:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")

    listing_dir = UPLOADS_DIR / "listings" / listing_id
    listing_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4()}{ext}"
    with open(listing_dir / filename, "wb") as f:
        f.write(contents)

    return f"listings/{listing_id}/{filename}"


def delete_listing_image_file(file_path: str) -> None:
    """Best-effort delete -- a missing file on disk must never block the DB row's own deletion."""
    try:
        os.remove(UPLOADS_DIR / file_path)
    except OSError:
        pass
