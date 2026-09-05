# Farm Master

A single digital platform connecting Ghanaian farmers, institutional buyers,
and agri-input vendors — turning fragmented smallholder agriculture into a
coordinated, demand-driven supply chain.

Farm Master is an agribusiness aggregation company building a digital
ecosystem around three interlinked portals — **Farmer**, **Buyer**, and
**Vendor** — coordinated by Farm Master as aggregator, agronomy authority,
and logistics operator, backed by a network of regional fulfilment centres
and a tricycle/vehicle logistics fleet. The pilot is scoped to Tema,
Greater Accra, on a single crop (maize). See
[Farm_Master_Website_Business_Concept.docx](Farm_Master_Website_Business_Concept.docx)
for the full concept and [Farm_Master_PRD_Stage1.docx](Farm_Master_PRD_Stage1.docx)
for the confirmed pilot scope.

## Project status

Following the 9-stage workflow in
[Farm_Master_Web_App_Project_Workflow_and_Documentation_Guide.docx](Farm_Master_Web_App_Project_Workflow_and_Documentation_Guide.docx):

| Stage | Status |
|---|---|
| 1 — Discovery & Scope | ✅ Confirmed |
| 2 — Information Architecture | ✅ Confirmed |
| 3 — Low-Fi Wireframes | ✅ All four portals + USSD/SMS flow |
| 4 — Visual UI Design | ✅ Deep Green & Maize Gold system, all four portals |
| 5 — Interactive Prototype | ✅ All three highest-stakes flows built and tested |
| 6 — Build (Real Code) | 🔶 **In progress** — see below |
| 7–9 | Not started |

**Stage 6 so far:** a real backend (RBAC across 7 roles, audit logging,
Finance/Super Admin segregation of duties, all foundational rather than
retrofitted) plus five flows implemented and tested end to end against a
real database and a real frontend:

- Buyer commitment-fee payment
- Farmer opportunity-acceptance + production-formula receipt
- Vendor mechanisation request, including the date-conflict override as a
  real Super-Admin-approved workflow
- Matching Queue (Internal Operations) — an Agronomist assigns a paid
  buyer requirement to one or more active farmers, creating real
  Opportunity rows a farmer can then accept through the existing Farmer flow
- Production Formula Builder (Internal Operations) — an Agronomist turns an
  assigned requirement into a planting calendar and a RateConfig-derived
  input schedule, then publishes it. Reads its per-farmer tonnage and
  farmer list directly from the Opportunity rows the Matching Queue already
  created rather than re-deriving them, and reuses the exact input-schedule
  math from the Farmer flow (see `app/formula.py`) rather than duplicating it.

Not yet built: Farmer/Vendor account management, and the rest of Internal
Operations (Logistics Dispatch, Fulfilment Intake, Finance &
Reconciliation, Reporting, MoFA Data Exchange).

## Tech stack

**Backend: Python 3.12 + FastAPI + SQLAlchemy + PostgreSQL 17.** Both
confirmed, no remaining ambiguity on the stack. FastAPI was picked over
Flask for its built-in request/response validation (Pydantic) and automatic
OpenAPI docs, which matter for a project with this many roles and
endpoints — reversion was assessed and explicitly declined, since it would
only change how the same logic is expressed, not any behaviour. The
database started on SQLite for local-dev convenience and was migrated to a
real PostgreSQL instance on 3 September 2026, satisfying the PRD's "central
relational database" requirement directly rather than as a future step; no
model changes were needed, but every enum-backed field (roles, statuses)
was explicitly retested against Postgres's stricter native ENUM handling.
Full reasoning and migration details in
[Farm_Master_SDD_Stage6.docx](Farm_Master_SDD_Stage6.docx), Section 2 and
Section 11.

**Frontend:** plain HTML/CSS/JS, no build step or framework — the same
visual design system approved in Stage 4, now calling real endpoints
instead of local JS state.

## Running it locally

```bash
cd "Stage 6 Build/backend"
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

Then open:

- <http://127.0.0.1:8000/buyer-flow>
- <http://127.0.0.1:8000/farmer-flow>
- <http://127.0.0.1:8000/vendor-flow>
- <http://127.0.0.1:8000/matching-flow> — Agronomist Matching Queue (Internal Operations)
- <http://127.0.0.1:8000/formula-builder-flow> — Production Formula Builder (Internal Operations)
- <http://127.0.0.1:8000/docs> — interactive Swagger API reference

This expects a local PostgreSQL instance (see
[Stage 6 Build/README.md](Stage%206%20Build/README.md) for the connection
string and dev-only credentials). The first run creates the tables and
seeds one dev user per role — all seeded passwords are dev-only, never real
credentials.

## Repo structure

There's no `/docs` folder — every stage's documents live at the repo root,
named `Farm_Master_<Deliverable>_Stage<N>.docx`, alongside the actual app
code and wireframes:

```
Farm_Master_PRD_Stage1.docx                    Stage 1 deliverable
Farm_Master_IA_Stage2.docx                      Stage 2 deliverable
Stage 3 Wireframes/                             Stage 3 deliverable (4 portals + USSD/SMS)
Farm_Master_Style_Guide_Stage4.docx             Stage 4 deliverable
Stage 4 Visual Design/                          Stage 4 deliverable (4 portals)
Stage 5 Interactive Prototype/                  Stage 5 deliverable (3 flows)
Farm_Master_SDD_Stage6.docx                     Stage 6 deliverable
Farm_Master_API_Documentation_Stage6.docx       Stage 6 deliverable
Stage 6 Build/                                  Stage 6 deliverable — the actual app
  backend/    FastAPI app, models, routers
  frontend/   Live HTML pages calling the backend
  README.md   Setup, env vars, manual verification steps
```

## Key documents

- [PRD (Stage 1)](Farm_Master_PRD_Stage1.docx) — problem, scope, roles, provisional rates
- [Information Architecture (Stage 2)](Farm_Master_IA_Stage2.docx) — sitemaps, user flows, device requirements
- [Style Guide (Stage 4)](Farm_Master_Style_Guide_Stage4.docx) — color/type/component system, and the running log of what's built
- [Software/System Design Document (Stage 6)](Farm_Master_SDD_Stage6.docx) — architecture, database schema, RBAC, audit logging
- [API Documentation (Stage 6)](Farm_Master_API_Documentation_Stage6.docx) — endpoint reference
- [Stage 6 Build/README.md](Stage%206%20Build/README.md) — setup, environment variables, manual verification
