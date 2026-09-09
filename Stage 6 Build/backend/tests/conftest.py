"""
Stage 7 test infrastructure. See "Stage 6 Build/TEST_PLAN.md" for the
traceability matrix this suite is built against.

Real PostgreSQL, not SQLite and not mocked -- FARM_MASTER_DATABASE_URL is
pointed at a dedicated farm_master_test database (see
"Stage 6 Build/README.md", "Running the test suite") before any `app.*`
module is imported, since app/database.py reads that env var at import
time. Testing against SQLite would hide exactly the class of bug this
project already shipped once: Postgres enforces native ENUM types
strictly where SQLite does not (SDD Section 2/11).

Each test runs inside its own SAVEPOINT that is rolled back afterwards
(the standard SQLAlchemy "join a session into an external transaction"
pattern), so router code calling db.commit() mid-test does not leak state
into the next test, and tests never depend on seed.py's demo dataset or
on each other's ordering.
"""

import os
import uuid

os.environ["FARM_MASTER_DATABASE_URL"] = os.environ.get(
    "FARM_MASTER_TEST_DATABASE_URL",
    "postgresql+psycopg://farmmaster:farmmaster_dev_pw@127.0.0.1:5432/farm_master_test",
)

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database import Base, DATABASE_URL
from app import models  # noqa: F401 -- registers every model on Base.metadata
from app.main import app
from app.database import get_db
from app.auth import hash_password
from fastapi.testclient import TestClient

assert "farm_master_test" in DATABASE_URL, (
    "Refusing to run: FARM_MASTER_DATABASE_URL does not point at farm_master_test. "
    "This suite creates and rolls back real rows -- it must never run against the "
    "farm_master dev database."
)


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(DATABASE_URL)
    Base.metadata.drop_all(bind=eng)
    Base.metadata.create_all(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def db_session(engine):
    connection = engine.connect()
    outer_txn = connection.begin()
    SessionForTest = sessionmaker(bind=connection)
    session = SessionForTest()

    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, trans):
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    try:
        yield session
    finally:
        session.close()
        outer_txn.rollback()
        connection.close()


@pytest.fixture()
def client(db_session):
    """
    Deliberately does NOT let main.py's @app.on_event("startup") handler
    run: that handler calls seed(), which opens its own SessionLocal()
    bound directly to the real engine (not this test's rolled-back
    savepoint) and would permanently commit the full demo dataset into
    farm_master_test on first use -- exactly the seed.py dependency this
    suite's fixtures are built to avoid. Tables are created once per
    session by the `engine` fixture instead.
    """

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    original_startup = list(app.router.on_startup)
    app.router.on_startup.clear()
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.router.on_startup.extend(original_startup)
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Auth helpers -- real OTP flow every time (dev_only_* codes echoed in the
# response, per models.OtpChallenge), never a JWT minted by bypassing login.
# This is the "real logic, simulated delivery" pattern applied to tests
# themselves: the simulation is exercised, not skipped.
# ---------------------------------------------------------------------------


def login(client, email, password="password123"):
    res = client.post("/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    challenge = res.json()
    res2 = client.post(
        "/auth/login/verify-otp",
        json={
            "challenge_id": challenge["challenge_id"],
            "phone_code": challenge["dev_only_phone_code"],
            "email_code": challenge["dev_only_email_code"],
        },
    )
    assert res2.status_code == 200, res2.text
    return res2.json()["access_token"]


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def unique_email(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:10]}@test.farmmaster.invalid"


@pytest.fixture()
def make_user(db_session):
    """
    Inserts a User row directly (mirrors seed.py, not the HTTP layer) --
    used to build test scenarios fast. Registration itself (OTP + approval)
    is exercised for real in tests/api/test_auth.py, not bypassed silently
    here; this fixture is the "reuse a known-good real record" half of the
    pattern, matching how the app's own seed.py provisions internal roles.
    """
    from app.models import User, Role, UserStatus

    created = []

    def _make(role, status=None, email=None, full_name=None, organisation_name=None, phone=None):
        status = status or UserStatus.ACTIVE
        email = email or unique_email(role.value)
        user = User(
            email=email,
            full_name=full_name or f"Test {role.value.title()}",
            phone=phone or "+233240000000",
            role=role,
            status=status,
            password_hash=hash_password("password123"),
            organisation_name=organisation_name,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        created.append(user)
        return user

    return _make


@pytest.fixture()
def rate_config(db_session):
    """Seeds the provisional rate config rows a real request needs -- same values as app/seed.py's SEED_RATES."""
    from app.models import RateConfig

    rows = [
        ("buyer_commitment_fee_per_tonne", 90.0, "GHS/tonne"),
        ("vendor_service_fee_per_tonne", 60.0, "GHS/tonne"),
        ("formula_seed_kg_per_tonne", 1.6, "kg/tonne"),
        ("formula_npk_tonnes_per_bag", 2.0, "tonnes/bag"),
        ("formula_topdress_tonnes_per_bag", 4.0, "tonnes/bag"),
        ("trading_margin_pct", 0.15, "fraction"),
        ("vendor_subscription_fee_monthly", 150.0, "GHS/month"),
        ("logistics_fee_per_delivery", 30.0, "GHS/delivery"),
    ]
    for key, value, unit in rows:
        db_session.add(RateConfig(key=key, value=value, unit=unit, status="PROVISIONAL", note="test fixture"))
    db_session.commit()


@pytest.fixture()
def roles(make_user, rate_config):
    """One ACTIVE user per role, real password hash, ready to log in through the real OTP flow."""
    from app.models import Role

    return {r: make_user(r) for r in Role}
