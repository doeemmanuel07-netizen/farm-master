"""
Registration and login, both gated by real-time OTP verification via phone
and email -- added 5 Sep 2026 as a new confirmed requirement (PRD Section
12), applying to all seven roles at both events. See models.OtpChallenge
for why delivery is simulated rather than wired to a real SMS/email gateway.

Self-registration (POST /register) is only offered for Farmer, Buyer, and
Vendor -- Internal Operations accounts (Agronomist, Logistics, Finance,
Super Admin) are Super-Admin-provisioned per PRD Section 3.2, not
self-registered, so they only ever go through the login OTP step, never
the registration one.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Role, UserStatus, OtpPurpose, RegistrationApproval, SELF_REGISTER_ROLES
from ..auth import verify_password, hash_password, create_access_token
from ..audit import log_audit
from ..otp import create_challenge, verify_challenge
from ..schemas import (
    LoginRequest, LoginResponse, RegisterRequest, OtpChallengeResponse,
    VerifyOtpRequest, RegisterVerifyResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])

APPLICANT_TYPE = {Role.BUYER: "Private Buyer", Role.VENDOR: "Third-Party Vendor"}

OTP_MESSAGE = (
    "SIMULATED delivery -- no SMS/email gateway is integrated yet (PRD Section 1.1/12). "
    "Both codes are echoed in this response for demo purposes; enter them both to continue."
)


@router.post("/register", response_model=OtpChallengeResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    if payload.role not in SELF_REGISTER_ROLES:
        raise HTTPException(
            status_code=422,
            detail="Self-registration is only available for Farmer, Buyer, and Vendor accounts.",
        )
    if payload.role in (Role.BUYER, Role.VENDOR) and not payload.organisation_name:
        raise HTTPException(status_code=422, detail="organisation_name is required for Buyer/Vendor registration.")
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    user = User(
        email=payload.email,
        phone=payload.phone,
        full_name=payload.full_name,
        role=payload.role,
        status=UserStatus.PENDING_OTP,
        password_hash=hash_password(payload.password),
        organisation_name=payload.organisation_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    challenge = create_challenge(db, user, OtpPurpose.REGISTRATION)
    return OtpChallengeResponse(
        challenge_id=challenge.id,
        purpose=challenge.purpose,
        expires_at=challenge.expires_at,
        message=OTP_MESSAGE,
        dev_only_phone_code=challenge.phone_code,
        dev_only_email_code=challenge.email_code,
    )


@router.post("/register/verify-otp", response_model=RegisterVerifyResponse)
def verify_registration_otp(payload: VerifyOtpRequest, db: Session = Depends(get_db)):
    challenge = verify_challenge(db, payload.challenge_id, payload.phone_code, payload.email_code, OtpPurpose.REGISTRATION)
    user = db.query(User).filter(User.id == challenge.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Account not found.")

    if user.role == Role.FARMER:
        # No Super Admin review step for Farmers today (RegistrationApproval
        # is scoped to buyer|vendor -- PRD Section 3.2/IA Section 10), so
        # OTP verification is the whole gate for a Farmer account.
        user.status = UserStatus.ACTIVE
        message = "Phone and email verified. Your account is active -- you can log in now."
    else:
        user.status = UserStatus.PENDING
        db.add(RegistrationApproval(
            user_id=user.id,
            applicant_name=user.organisation_name or user.full_name,
            applicant_type=APPLICANT_TYPE[user.role],
            portal=user.role.value,
            status="pending_review",
        ))
        message = "Phone and email verified. Your registration now awaits Super Admin approval before you can log in."
    db.commit()

    log_audit(db, user, "account_registered", f"{user.full_name} ({user.email}, {user.role.value}): OTP-verified, status -> {user.status.value}.")
    return RegisterVerifyResponse(status=user.status, message=message)


@router.post("/login", response_model=OtpChallengeResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    if user.status == UserStatus.PENDING_OTP:
        raise HTTPException(status_code=403, detail="Finish registration verification before logging in.")
    if user.status == UserStatus.PENDING:
        raise HTTPException(status_code=403, detail="Your registration is awaiting Super Admin approval.")
    if user.status == UserStatus.SUSPENDED:
        raise HTTPException(status_code=403, detail="This account has been suspended.")

    challenge = create_challenge(db, user, OtpPurpose.LOGIN)
    return OtpChallengeResponse(
        challenge_id=challenge.id,
        purpose=challenge.purpose,
        expires_at=challenge.expires_at,
        message=OTP_MESSAGE,
        dev_only_phone_code=challenge.phone_code,
        dev_only_email_code=challenge.email_code,
    )


@router.post("/login/verify-otp", response_model=LoginResponse)
def verify_login_otp(payload: VerifyOtpRequest, db: Session = Depends(get_db)):
    challenge = verify_challenge(db, payload.challenge_id, payload.phone_code, payload.email_code, OtpPurpose.LOGIN)
    user = db.query(User).filter(User.id == challenge.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Account not found.")

    token = create_access_token(user)
    return LoginResponse(access_token=token, role=user.role, full_name=user.full_name)
