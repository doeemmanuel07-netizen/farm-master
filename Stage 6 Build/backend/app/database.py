"""
Database engine and session setup.

PostgreSQL (confirmed 3 Sep 2026, per Emmanuel's decision) via SQLAlchemy's
ORM layer + the psycopg (v3) driver, satisfying the PRD's "central
relational database" requirement directly rather than as a future step.
Every model in models.py uses standard SQLAlchemy types with no
dialect-specific features, so this was a connection-string and driver swap
from the local-dev-only SQLite setup, not a model rewrite -- confirmed by
retesting all three flows and every enum-backed field (roles, statuses)
against the real Postgres instance, since Postgres enforces native ENUM
types strictly at the database level where SQLite did not.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.environ.get(
    "FARM_MASTER_DATABASE_URL",
    "postgresql+psycopg://farmmaster:farmmaster_dev_pw@127.0.0.1:5432/farm_master",
)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
