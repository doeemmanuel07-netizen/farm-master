"""
Shared OTP challenge creation/verification -- the single source used by both
registration and login (routers/auth.py), so the two can't drift into two
slightly different OTP mechanisms. See models.OtpChallenge for why delivery
is simulated.
"""

import secrets
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .models import OtpChallenge, OtpPurpose, User

OTP_TTL_MINUTES = 10


def _generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def create_challenge(db: Session, user: User, purpose: OtpPurpose) -> OtpChallenge:
    challenge = OtpChallenge(
        user_id=user.id,
        purpose=purpose,
        email_code=_generate_code(),
        expires_at=datetime.utcnow() + timedelta(minutes=OTP_TTL_MINUTES),
    )
    db.add(challenge)
    db.commit()
    db.refresh(challenge)
    return challenge


def verify_challenge(
    db: Session, challenge_id: str, email_code: str, purpose: OtpPurpose
) -> OtpChallenge:
    challenge = db.query(OtpChallenge).filter(OtpChallenge.id == challenge_id).first()
    if not challenge or challenge.purpose != purpose:
        raise HTTPException(status_code=404, detail="OTP challenge not found.")
    if challenge.consumed_at is not None:
        raise HTTPException(status_code=409, detail="This OTP challenge has already been used.")
    if datetime.utcnow() > challenge.expires_at:
        raise HTTPException(status_code=410, detail="This OTP has expired. Please try again to get a new code.")
    if challenge.email_code != email_code:
        raise HTTPException(status_code=401, detail="The OTP code is incorrect.")

    challenge.consumed_at = datetime.utcnow()
    db.commit()
    db.refresh(challenge)
    return challenge
