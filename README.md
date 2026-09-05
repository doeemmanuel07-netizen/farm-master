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
retrofitted) plus eight flows implemented and tested end to end against a
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
- Logistics Dispatch (Internal Operations) — completes PRD Section 6
  Must-Have #3 ("Vendor input ordering routed to logistics dispatch") for
  the one real job source that exists: a `POST /vendor/requests/{id}/confirm`
  or Super-Admin override-approval automatically creates a real dispatch
  job, which Logistics can then assign a tricycle to and mark delivered.
  Confirmed phone-first per PRD Section 5.1, so this flow opens on the
  phone viewport by default, unlike every other flow. Real input ordering
  (a Farmer buying seed/fertiliser from a Vendor's Product Catalogue) has
  no backend yet — see "Not yet built" below.
- Harvest Pickup Request + Fulfilment Centre Intake & Grading (Farmer +
  Internal Operations) — completes PRD Section 6 Must-Have #4. A Farmer
  requesting pickup immediately creates a real inbound Logistics Dispatch
  job (no confirmation step needed — nobody has to "accept" your own
  harvest being ready); once Logistics marks it delivered, Finance can
  weigh in and grade it. `DispatchJob` was generalised to carry either a
  mechanisation request or a harvest pickup, so the dispatch queue stays
  one real table instead of two. Feeding a graded intake into buyer
  compliance docs or farmer settlement is PRD Must-Have #5 — not built yet.

Also added 5 September 2026, cutting across every flow above: **real-time
OTP verification** via both phone and email, at both registration and
login, for all seven roles ([PRD](Farm_Master_PRD_Stage1.docx) Section
12) — a new confirmed requirement, not part of the original Stage 1–5
scope. Self-registration (`POST /auth/register`) is new too — it didn't
exist for any role before this pass. Delivery is **SIMULATED**, same
treatment as mobile money: no SMS/email provider is chosen yet, so both
OTP codes are returned directly in the API response instead of actually
being sent.

Not yet built: real input ordering (Farmer Order Inputs, Vendor Product
Catalogue — PRD Must-Have #3's literal scope, as distinct from the
mechanisation-request dispatch that is built), Order Reconciliation (PRD
Must-Have #5), the rest of Internal Operations (Finance & Reconciliation,
Reporting, MoFA Data Exchange), the User & Role Admin screen's
account-creation UI for internal staff, and any real mobile money or OTP
gateway integration.

**Known gap, tracked for a separate task (not this one):** the Matching
Queue records which farmer an Opportunity was assigned to
(`assigned_farmer_id`), but the Farmer flow's opportunity list doesn't yet
filter on it — every active farmer can currently see and accept an
opportunity assigned to someone else. See [Stage 6 Build/README.md](Stage%206%20Build/README.md)
"Known limitations" for detail.

**Responsive QA pass (5 September 2026):** every flow above was verified
at desktop (1280px), tablet (768px), and phone (375px) — no horizontal
page overflow, no interactive element under the PRD Section 5.1-confirmed
44px touch-target minimum. This pass found and fixed a systemic bug: none
of the frontend files had a `<meta name="viewport">` tag, so every
phone/tablet CSS rule built across all of Stage 6 never actually applied
on a real device (real browsers were silently rendering at a ~980px
zoomed-out layout instead). Also fixed: several sub-44px controls (device
toggle, restart button, planting-calendar week inputs, small table-action
buttons), and a real rendering bug in Logistics Dispatch where an inbound
(harvest-pickup) job showed "undefined" and "null acres" because the card
renderer hadn't been updated for the new job type. This check is now
mandatory for every new screen going forward, not retrofitted after.

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

- <http://127.0.0.1:8000/register-flow> — Registration + real-time OTP verification (Farmer/Buyer/Vendor)
- <http://127.0.0.1:8000/buyer-flow>
- <http://127.0.0.1:8000/farmer-flow>
- <http://127.0.0.1:8000/vendor-flow>
- <http://127.0.0.1:8000/matching-flow> — Agronomist Matching Queue (Internal Operations)
- <http://127.0.0.1:8000/formula-builder-flow> — Production Formula Builder (Internal Operations)
- <http://127.0.0.1:8000/dispatch-flow> — Logistics Dispatch (Internal Operations, phone-first)
- <http://127.0.0.1:8000/harvest-pickup-flow> — Farmer Harvest Pickup Request
- <http://127.0.0.1:8000/fulfilment-intake-flow> — Fulfilment Centre Intake & Grading (Internal Operations)
- <http://127.0.0.1:8000/docs> — interactive Swagger API reference

Every flow above now signs in through two steps — password, then an OTP
screen with both codes pre-filled (delivery is simulated, see above).

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
