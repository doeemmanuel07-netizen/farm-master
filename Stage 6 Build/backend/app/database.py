"""
Database engine and session setup.

Uses SQLite for local pilot development (zero-install, file-based) via
SQLAlchemy's ORM layer. Every model in models.py uses standard SQLAlchemy
types with no SQLite-specific features, so moving to PostgreSQL for
production later (per PRD's "central relational database" requirement) is a
one-line change to DATABASE_URL plus swapping the driver -- not a rewrite.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.environ.get("FARM_MASTER_DATABASE_URL", "sqlite:///./farm_master.db")

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
