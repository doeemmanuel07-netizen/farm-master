# Changelog

All notable changes to the Farm Master web app. Dates are when the change was committed. Earlier history (Stages 1–7) is in the git log and `Farm_Master_SDD_Stage6.docx`.

## [Unreleased] — CEO platform demo alignment

### Added
- `docs/reference/Farm_Master_Platform_Demo.html`: the CEO-approved demo, now the target look and flow.
- `docs/ceo-demo-gap-report.md`: feature-by-feature audit, plus decisions D1–D8.
- Design system: `frontend/assets/tokens.css`, `components.css`, `components.js`, a live gallery at `/design-system`, and `docs/design-system.md`.
- `scripts/responsive_check.py`: headless Chromium no-horizontal-scroll check at 390 / 820 / 1400px.
- Alembic schema migrations (decision D6): a baseline revision of the Stage 6 schema, `alembic upgrade head` at startup (replacing `create_all`), automatic baseline stamping for pre-Alembic databases, and a test that fails if the models and migrations disagree.
- Reference data (brief §2A–C): `regions` (16), `fulfilment_centres` (16, Tema HQ), `crops` + `crop_varieties` (Maize, White Rice, Soybean, Tomato), `farmer_unions`, `farmer_crops`; profile columns on `users`. The pilot config is Greater Accra/Tema + Maize active, and everything else can be switched on from `/admin/crops|regions|fulfilment-centres`.
- `GET /api/public/stats|crops|regions` (landing page, no auth) and `GET /auth/me` (portal header line).
- `docs/database-schema.md`: a table reference and Mermaid ERD generated from the models by `scripts/gen_schema_doc.py`.
- Payments behind a `PaymentProvider` interface (brief §2D/§5.1): sandbox driver (default), Paystack and Hubtel drivers (not yet run against live credentials). Payments stay **pending until a verified webhook** confirms them (`POST /payments/webhook/{provider}`), with idempotency and amount checks. Networks are labelled MTN MoMo / Telecel Cash / AT Money / Card.
- Commitment fee is now a configurable rule (`commitment_fee_rules`, per-tonne or % of value, with a minimum), seeded with PRD §10's GH₵ 90/t so existing figures don't change.
- Buyer orders: `FM-####` references, crop variety, `delivery_by` date with a minimum lead time, spec notes, a `delivered` status, and a server-derived stepper/progress. New `GET /buyer/order-form`, `/buyer/fee-quote`, `/buyer/payments/{id}`, `/ops/payments`, `/admin/commitment-fee-rules`.

### Changed
- `POST /buyer/requirements/{id}/pay` returns `pending` instead of `success`; card no longer returns 501. The `/buyer-flow` page waits for the webhook (sandbox phone approval).
- **Buyer Portal** at `/buyer`, built to the CEO demo: a requirement form generated from `/buyer/order-form` (active crops/varieties, earliest delivery date, reference price, live fee quote), the choose → pending → confirmed payment modal (with a sandbox phone simulator and a retry on failure), and an orders table with expandable stepper rows and a Pay action for unpaid orders. Copy matches the demo.
