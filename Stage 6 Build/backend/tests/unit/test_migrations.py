"""
Alembic revisions must produce exactly the schema the models declare
(decision D6). Upgrades a throwaway database to head, then asks Alembic's
autogenerate comparator for any remaining difference -- a non-empty diff
means a model changed without a matching revision in migrations/versions/.
"""

import psycopg
import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic import command
from sqlalchemy import create_engine

from app.database import Base, DATABASE_URL
from app.migrate import alembic_config

SCRATCH_DB = "farm_master_migrations_test"


@pytest.fixture(scope="module")
def scratch_url():
    admin_url = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {SCRATCH_DB} WITH (FORCE)")
        conn.execute(f"CREATE DATABASE {SCRATCH_DB}")
    url = DATABASE_URL.rsplit("/", 1)[0] + "/" + SCRATCH_DB
    yield url
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {SCRATCH_DB} WITH (FORCE)")


def test_migrations_match_models(scratch_url):
    engine = create_engine(scratch_url)
    cfg = alembic_config()
    # A plain (not begun) connection: Alembic manages the transaction itself,
    # which revision 0003's ALTER TYPE ... ADD VALUE autocommit block needs.
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
        conn.commit()
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    engine.dispose()
    assert diff == [], f"Models and migrations disagree -- add an Alembic revision: {diff}"
