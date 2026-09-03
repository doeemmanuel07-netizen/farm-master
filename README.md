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
retrofitted) plus three flows implemented and tested end to end against a
real database and a real frontend:

- Buyer commitment-fee payment
- Farmer opportunity-acceptance + production-formula receipt
- Vendor mechanisation request, including the date-conflict override as a
  real Super-Admin-approved workflow

Not yet built: Farmer/Vendor account management, and the rest of Internal
Operations (Matching Queue, Formula Builder, Logistics Dispatch, Fulfilment
Intake, Finance & Reconciliation, Reporting, MoFA Data Exchange).

## Tech stack

**Backend: Python 3.12 + FastAPI + SQLAlchemy + SQLite.** Not Flask, and not
PostgreSQL yet — this was a deliberate call made when Stage 6 started: this
environment had Python already available but not Node.js, and FastAPI was
picked over Flask for its built-in request/response validation (Pydantic)
and automatic OpenAPI docs, which matter for a project with this many roles
and endpoints. SQLite is the local dev database; every model uses standard
SQLAlchemy types with no SQLite-specific features, so pointing
`FARM_MASTER_DATABASE_URL` at a PostgreSQL instance for production — the
PRD's "central relational database" requirement — is a connection-string
change, not a rewrite. Full reasoning in
[Farm_Master_SDD_Stage6.docx](Farm_Master_SDD_Stage6.docx), Section 2.

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
- <http://127.0.0.1:8000/docs> — interactive Swagger API reference

The first run seeds a SQLite database with one dev user per role (see
[Stage 6 Build/README.md](Stage%206%20Build/README.md) for credentials and
environment variables — all seeded passwords are dev-only, never real
credentials).

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
