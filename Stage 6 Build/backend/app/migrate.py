"""
Schema migrations at startup (decision D6, docs/ceo-demo-gap-report.md).

Replaces the old Base.metadata.create_all() call, which could create new
tables but never add a column or an enum value to an existing one. Every
schema change from here on is an Alembic revision in migrations/versions/.

A database created before Alembic was introduced (by create_all) has every
baseline table but no alembic_version row. It is stamped at the baseline
revision first, so only the revisions after it run.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from .database import engine

BACKEND_DIR = Path(__file__).resolve().parent.parent
BASELINE_REVISION = "0001_baseline"


def alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.attributes["configure_logger"] = False
    return cfg


def upgrade_to_head() -> None:
    cfg = alembic_config()
    tables = set(inspect(engine).get_table_names())
    if "alembic_version" not in tables and "users" in tables:
        command.stamp(cfg, BASELINE_REVISION)
    command.upgrade(cfg, "head")
