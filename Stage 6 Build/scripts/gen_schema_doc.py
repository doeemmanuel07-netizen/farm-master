"""
Regenerates docs/database-schema.md -- the table reference and a Mermaid ERD
-- straight from the SQLAlchemy models, so the schema doc can't drift from
the code. Run after any model change (and commit the result with it):

    python scripts/gen_schema_doc.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Stage 6 Build" / "backend"))

from sqlalchemy import Enum as SAEnum  # noqa: E402

from app.database import Base  # noqa: E402
from app import models  # noqa: E402,F401

OUT = ROOT / "docs" / "database-schema.md"


def col_type(col):
    t = col.type
    if isinstance(t, SAEnum):
        return f"enum({', '.join(v.lower() for v in t.enums)})"
    return type(t).__name__.lower()


def main():
    tables = sorted(Base.metadata.tables.values(), key=lambda t: t.name)
    lines = [
        "# Database Schema",
        "",
        "_Generated from the SQLAlchemy models by `Stage 6 Build/scripts/gen_schema_doc.py`. Do not edit by hand._",
        "",
        "PostgreSQL. Migrations are Alembic revisions in `Stage 6 Build/backend/migrations/versions/`, applied "
        "automatically at startup (`app/migrate.py`). `tests/unit/test_migrations.py` fails if a model changes "
        "without a matching revision.",
        "",
        "## Entity-relationship diagram",
        "",
        "```mermaid",
        "erDiagram",
    ]
    for t in tables:
        for fk in sorted(t.foreign_keys, key=lambda f: f.parent.name):
            target = fk.column.table.name
            lines.append(f'    {target} ||--o{{ {t.name} : "{fk.parent.name}"')
    for t in tables:
        lines.append(f"    {t.name} {{")
        for c in t.columns:
            key = " PK" if c.primary_key else (" FK" if c.foreign_keys else "")
            typ = "enum" if isinstance(c.type, SAEnum) else type(c.type).__name__.lower()
            lines.append(f"        {typ} {c.name}{key}")
        lines.append("    }")
    lines += ["```", "", "## Tables", ""]
    for t in tables:
        lines += [f"### `{t.name}`", "", "| Column | Type | Null | Key / default |", "|---|---|---|---|"]
        for c in t.columns:
            keys = []
            if c.primary_key:
                keys.append("PK")
            for fk in c.foreign_keys:
                keys.append(f"FK → `{fk.column.table.name}.{fk.column.name}`")
            if c.unique:
                keys.append("unique")
            if c.server_default is not None:
                keys.append(f"server default `{c.server_default.arg}`")
            lines.append(f"| `{c.name}` | {col_type(c)} | {'yes' if c.nullable else 'no'} | {', '.join(keys)} |")
        lines.append("")
    seqs = sorted(Base.metadata._sequences.values(), key=lambda s: s.name)
    if seqs:
        lines += ["## Sequences", ""]
        for s in seqs:
            lines.append(f"- `{s.name}` (starts at {s.start})")
        lines.append("")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT} ({len(tables)} tables)")


if __name__ == "__main__":
    main()
