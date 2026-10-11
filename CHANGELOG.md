# Changelog

All notable changes to the Farm Master web app. Dates are when the change was committed. Earlier history (Stages 1–7) is in the git log and `Farm_Master_SDD_Stage6.docx`.

## [Unreleased] — CEO platform demo alignment

### Added
- `docs/reference/Farm_Master_Platform_Demo.html`: the CEO-approved demo, now the target look and flow.
- `docs/ceo-demo-gap-report.md`: feature-by-feature audit, plus decisions D1–D8.
- Design system: `frontend/assets/tokens.css`, `components.css`, `components.js`, a live gallery at `/design-system`, and `docs/design-system.md`.
- `scripts/responsive_check.py`: headless Chromium no-horizontal-scroll check at 390 / 820 / 1400px.
- Alembic schema migrations (decision D6): a baseline revision of the Stage 6 schema, `alembic upgrade head` at startup (replacing `create_all`), automatic baseline stamping for pre-Alembic databases, and a test that fails if the models and migrations disagree.
