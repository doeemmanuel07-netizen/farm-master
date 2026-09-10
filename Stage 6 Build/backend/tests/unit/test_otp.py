"""
Unit tests for app/otp.py -- the single OTP mechanism shared by
registration and login. Marked `simulated`: delivery is SIMULATED (no real
email gateway chosen, PRD Section 1.1/12), but the challenge/verify logic
itself must be fully real -- single-use, expiring. Consolidated to a
single email channel 10 Sep 2026 (was phone + email, both required
together); these tests exercise the real post-consolidation logic
directly.
"""

from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

from app.models import Role, OtpPurpose
from app.otp import create_challenge, verify_challenge

pytestmark = [pytest.mark.unit, pytest.mark.simulated]


def test_challenge_generates_a_six_digit_code(db_session, make_user):
    user = make_user(Role.FARMER)
    challenge = create_challenge(db_session, user, OtpPurpose.LOGIN)
    assert len(challenge.email_code) == 6 and challenge.email_code.isdigit()
    assert challenge.consumed_at is None
    assert challenge.expires_at > datetime.utcnow()


def test_verify_succeeds_with_correct_code(db_session, make_user):
    user = make_user(Role.FARMER)
    challenge = create_challenge(db_session, user, OtpPurpose.LOGIN)
    verified = verify_challenge(db_session, challenge.id, challenge.email_code, OtpPurpose.LOGIN)
    assert verified.consumed_at is not None


def test_verify_rejects_wrong_email_code(db_session, make_user):
    user = make_user(Role.FARMER)
    challenge = create_challenge(db_session, user, OtpPurpose.LOGIN)
    with pytest.raises(HTTPException) as exc:
        verify_challenge(db_session, challenge.id, "000000", OtpPurpose.LOGIN)
    assert exc.value.status_code == 401


def test_verify_rejects_reused_challenge(db_session, make_user):
    user = make_user(Role.FARMER)
    challenge = create_challenge(db_session, user, OtpPurpose.LOGIN)
    verify_challenge(db_session, challenge.id, challenge.email_code, OtpPurpose.LOGIN)
    with pytest.raises(HTTPException) as exc:
        verify_challenge(db_session, challenge.id, challenge.email_code, OtpPurpose.LOGIN)
    assert exc.value.status_code == 409


def test_verify_rejects_expired_challenge(db_session, make_user):
    user = make_user(Role.FARMER)
    challenge = create_challenge(db_session, user, OtpPurpose.LOGIN)
    challenge.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db_session.commit()
    with pytest.raises(HTTPException) as exc:
        verify_challenge(db_session, challenge.id, challenge.email_code, OtpPurpose.LOGIN)
    assert exc.value.status_code == 410


def test_verify_rejects_wrong_purpose(db_session, make_user):
    """A registration challenge must not verify against a login check, or vice versa."""
    user = make_user(Role.FARMER)
    challenge = create_challenge(db_session, user, OtpPurpose.REGISTRATION)
    with pytest.raises(HTTPException) as exc:
        verify_challenge(db_session, challenge.id, challenge.email_code, OtpPurpose.LOGIN)
    assert exc.value.status_code == 404


def test_verify_rejects_unknown_challenge_id(db_session):
    with pytest.raises(HTTPException) as exc:
        verify_challenge(db_session, "not-a-real-id", "123456", OtpPurpose.LOGIN)
    assert exc.value.status_code == 404
