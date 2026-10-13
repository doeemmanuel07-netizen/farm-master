"""
Stakeholder feedback (13 Oct 2026): the "Feedback" button on every page
posts here, and Super Admin reviews it at /feedback or as a CSV export.
Posting needs no sign-in, so the public preview can collect comments from
anyone reviewing it; a valid bearer token, when sent, records the author.
"""

import csv
import io
import time
from collections import defaultdict, deque
from datetime import datetime
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import ALGORITHM, SECRET_KEY, require_roles
from ..database import get_db
from ..models import Feedback, Role, User

router = APIRouter(prefix="/api/feedback", tags=["feedback"])

# Which portal a page belongs to, by path prefix (first match wins);
# anything else is one of the internal Control Centre flows.
PORTAL_PREFIXES = [
    ("/farmer", "Farmer"), ("/harvest-pickup", "Farmer"), ("/order-inputs", "Farmer"), ("/ussd-sms", "Farmer"),
    ("/buyer", "Buyer"),
    ("/marketplace", "Vendor"), ("/vendor", "Vendor"),
    ("/register", "Registration"),
    ("/design-system", "Design system"),
]

# A light per-address limit, because the preview link is public.
MAX_PER_HOUR = 30
_recent: dict[str, deque] = defaultdict(deque)


def portal_for(page: str) -> str:
    if page in ("", "/"):
        return "Overview"
    for prefix, portal in PORTAL_PREFIXES:
        if page.startswith(prefix):
            return portal
    return "Control Centre"


def _client_key(request: Request) -> str:
    return request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "unknown")


def _throttle(key: str) -> None:
    now = time.monotonic()
    q = _recent[key]
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= MAX_PER_HOUR:
        raise HTTPException(status_code=429, detail="That's a lot of feedback for one hour. Please try again later.")
    q.append(now)


def _optional_user(request: Request, db: Session) -> Optional[User]:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    try:
        user_id = jwt.decode(header[7:], SECRET_KEY, algorithms=[ALGORITHM]).get("sub")
    except JWTError:
        return None
    return db.query(User).filter(User.id == user_id).first() if user_id else None


class FeedbackCreate(BaseModel):
    page: str = Field(max_length=200)
    category: Literal["suggestion", "problem", "question", "praise"]
    message: str = Field(min_length=3, max_length=2000)
    name: Optional[str] = Field(default=None, max_length=120)


class FeedbackResponse(BaseModel):
    id: str
    portal: str
    page: str
    category: str
    message: str
    name: Optional[str]
    user_name: Optional[str]
    user_role: Optional[str]
    created_at: datetime


def _response(f: Feedback, db: Session) -> FeedbackResponse:
    user = db.get(User, f.user_id) if f.user_id else None
    return FeedbackResponse(
        id=f.id, portal=f.portal, page=f.page, category=f.category, message=f.message,
        name=f.name, user_name=user.full_name if user else None, user_role=f.user_role, created_at=f.created_at,
    )


@router.post("", response_model=FeedbackResponse, status_code=201)
def create_feedback(payload: FeedbackCreate, request: Request, db: Session = Depends(get_db)):
    message = payload.message.strip()
    if len(message) < 3:
        raise HTTPException(status_code=422, detail="Please write a little more.")
    _throttle(_client_key(request))
    page = payload.page.split("?")[0] or "/"
    user = _optional_user(request, db)
    row = Feedback(
        portal=portal_for(page), page=page, category=payload.category, message=message,
        name=(payload.name or "").strip() or None,
        user_id=user.id if user else None, user_role=user.role.value if user else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _response(row, db)


@router.get("", response_model=List[FeedbackResponse])
def list_feedback(db: Session = Depends(get_db), _: User = Depends(require_roles(Role.SUPER_ADMIN))):
    rows = db.query(Feedback).order_by(Feedback.created_at.desc()).all()
    return [_response(f, db) for f in rows]


@router.get("/export.csv")
def export_feedback(db: Session = Depends(get_db), _: User = Depends(require_roles(Role.SUPER_ADMIN))):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Date (UTC)", "Portal", "Page", "Type", "Feedback", "Name given", "Signed-in user", "Role"])
    for f in db.query(Feedback).order_by(Feedback.created_at.desc()).all():
        r = _response(f, db)
        w.writerow([r.created_at.strftime("%Y-%m-%d %H:%M"), r.portal, r.page, r.category, r.message,
                    r.name or "", r.user_name or "", r.user_role or ""])
    return StreamingResponse(
        iter([out.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="farm-master-feedback.csv"'},
    )
