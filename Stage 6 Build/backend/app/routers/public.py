"""
Public, unauthenticated endpoints behind the landing page (CEO demo brief §3).
Everything here is aggregate or reference data -- never a person's name,
phone number or any per-account figure.
"""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import FulfilmentCentre, RateConfig, Region, SELF_REGISTER_ROLES
from ..reference import active_crops
from ..schemas import CropResponse, RegionResponse, PublicStatsResponse

router = APIRouter(prefix="/api/public", tags=["public"])


@router.get("/stats", response_model=PublicStatsResponse)
def stats(db: Session = Depends(get_db)):
    hq = db.query(FulfilmentCentre).filter(FulfilmentCentre.is_hq.is_(True)).first()
    streams = db.query(RateConfig).filter(RateConfig.key == "revenue_streams_count").first()
    return PublicStatsResponse(
        coordinated_portals=len(SELF_REGISTER_ROLES),
        fulfilment_centres=db.query(FulfilmentCentre).count(),
        active_fulfilment_centres=db.query(FulfilmentCentre).filter(FulfilmentCentre.is_active.is_(True)).count(),
        revenue_streams=int(streams.value) if streams else 0,
        head_office=hq.town if hq else "",
    )


@router.get("/crops", response_model=List[CropResponse])
def crops(db: Session = Depends(get_db)):
    """Crops currently open for ordering, with their active varieties only."""
    out = []
    for c in active_crops(db):
        resp = CropResponse.model_validate(c)
        resp.varieties = [v for v in resp.varieties if v.is_active]
        out.append(resp)
    return out


@router.get("/regions", response_model=List[RegionResponse])
def regions(db: Session = Depends(get_db)):
    return db.query(Region).filter(Region.is_active.is_(True)).order_by(Region.name).all()
