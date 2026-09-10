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
| 6 — Build (Real Code) | ✅ Complete — see below |
| 7 — Testing | ✅ Complete — see below |
| 8–9 | Not started |

**Stage 6 so far:** a real backend (RBAC across 7 roles, audit logging,
Finance/Super Admin segregation of duties, all foundational rather than
retrofitted) plus twenty-three flows implemented and tested end to end
against a real database and a real frontend — every screen in the
confirmed IA/wireframe/visual scope except the payment/OTP gateway
integration itself. All five of PRD Section 6's Must-Haves are now built,
and so is every screen from this session's own 8 September 2026
completeness audit (see "8 September 2026" below). The original fourteen:

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
- Logistics Dispatch (Internal Operations) — a `POST
  /vendor/requests/{id}/confirm`, a Super-Admin override-approval, or a
  confirmed input order (below) automatically creates a real dispatch job,
  which Logistics can then assign a tricycle to and mark delivered.
  Confirmed phone-first per PRD Section 5.1, so this flow opens on the
  phone viewport by default, unlike every other flow.
- Order Inputs + Vendor Product Catalogue (Farmer + Vendor) — completes PRD
  Section 6 Must-Have #3's literal scope: a Farmer buys seed, fertiliser,
  crop-protection, or tools from a Vendor's catalogue, with seed/NPK/top-
  dress quantities pre-filled from their own production formula. Placing an
  order reserves the stock immediately; the Vendor then confirms it (which
  is what actually creates the real Logistics Dispatch job above) or
  declines it (which restores the reservation). Scoped to a single vendor
  per order, mirroring the Vendor mechanisation request's own scoping.
- Harvest Pickup Request + Fulfilment Centre Intake & Grading (Farmer +
  Internal Operations) — completes PRD Section 6 Must-Have #4. A Farmer
  requesting pickup immediately creates a real inbound Logistics Dispatch
  job (no confirmation step needed — nobody has to "accept" your own
  harvest being ready); once Logistics marks it delivered, Finance can
  weigh in and grade it. `DispatchJob` was generalised to carry either a
  mechanisation request or a harvest pickup, so the dispatch queue stays
  one real table instead of two. A pickup can also optionally be linked to
  one of the farmer's own accepted buyer orders, feeding real Order
  Reconciliation (below) once graded.
- Order Reconciliation (Internal Operations, Finance) — completes PRD
  Section 6 Must-Have #5, the last of the pilot's five must-haves.
  Commitment fee received, farmer settlement due, vendor payout due, and
  Farm Master's trading margin are computed live per buyer order from real
  linked data (a real commitment-fee payment, delivered & graded
  non-reject tonnage, confirmed mechanisation requests **and confirmed
  input orders**) rather than the order's originally committed quantity,
  and Finance can release settlement/payout once there's something real to
  release. The trading margin rate itself has no confirmed figure anywhere
  in the PRD or Business Concept doc (unlike the buyer commitment fee and
  vendor service fee) — see "Not yet built" below.
- MoFA Compliance Report (Internal Operations, Finance) — the export half
  of the Stage 3 wireframe's "MoFA Data Exchange" screen (PRD Section
  1.1/9): a generic CSV/PDF export, one row per graded delivery linked to
  a real buyer order, covering exactly the four confirmed fields (volume,
  quality grade, buyer, delivery date) — a placeholder pending an actual
  MoFA data standard. REJECT-graded rows are included deliberately, since
  quality grade is itself one of the confirmed columns.
- User & Role Admin (Super Admin) — built against the confirmed Stage 4
  visual (`internal_operations_visual.html:460-484`), no scope decisions
  needed. Cross-portal account management: change an internal staff
  member's role (already existed), suspend/reactivate an external
  account, review a pending Buyer/Vendor registration inline (reusing the
  existing Registration Approval endpoints), or create a new internal
  (Agronomist/Logistics/Finance/Super Admin) account outright via a real
  "+ Add internal user" action. Every one of those five actions writes a
  real audit-log entry, per the mockup's own caption — verified, not just
  asserted.

Also added 5 September 2026, cutting across every flow above: **real-time
OTP verification** via both phone and email, at both registration and
login, for all seven roles ([PRD](Farm_Master_PRD_Stage1.docx) Section
12) — a new confirmed requirement, not part of the original Stage 1–5
scope. Self-registration (`POST /auth/register`) is new too — it didn't
exist for any role before this pass. Delivery is **SIMULATED**, same
treatment as mobile money: no SMS/email provider is chosen yet, so both
OTP codes are returned directly in the API response instead of actually
being sent.

**Consolidated to email-only 10 September 2026** for user-friendliness —
one code to read and enter instead of two. The `phone_code` column,
field, and request parameter are gone, not just unused; every OTP
screen across all 23 live flow pages now shows a single Email OTP code
field. Same session, also fixed: navigating the header nav no longer
signs a user out (login now persists across page loads via
`localStorage`, with a real 10-minute inactivity timeout replacing
"logged out on every click"). See
[Farm_Master_SDD_Stage6.docx](Farm_Master_SDD_Stage6.docx) Section 31
for the full account, including one real bug found while building this
(a stale cross-role session breaking a page blank instead of falling
back to login, now fixed).

**8 September 2026 — 24 items closed in one pass.** This session ran its
own fresh completeness audit against the confirmed Stage 1-6 documents
(rather than trusting prior session notes) and found the actual
unbuilt-screen list was longer than the six items already being tracked:
roughly eighteen more IA/wireframe/visual-scoped screens, plus the entire
USSD/SMS channel, had been in scope since Stage 2/3 but were never
enumerated anywhere. Emmanuel's decision: all of it is now in Stage 6
scope, not Phase 2. Built and verified in this pass: the Reporting
dashboard (real revenue-stream + pilot metrics, three streams live and
three shown disabled with their deferred phase); the MoFA import half (a
real manual-entry record, the honest equivalent of the wireframe's own
"no live API yet" caption); the Registration Approval Queue's own
dedicated screen (reusing its pre-existing, already-audited backend);
Field Visit Logs and Proof of Pickup/Delivery (GPS via the browser's real
Geolocation API); Trunking (previously entirely absent — no model, no
stub); all four portal dashboards (Buyer, Farmer, Vendor, and a shared
Control Centre Dashboard for all four internal roles); Farmer Wallet &
Settlement, Milestone Log, and Agronomist Messaging; Vendor Subscription &
Billing, Payout Statement, and Logistics Handoff Status; Buyer Documents,
Tracking, and Invoice; the Audit Log's first real browsing screen; and
the entire USSD/SMS channel — a session-based menu emulator (numbered
options, a real inactivity timeout, back navigation) reusing the existing
web login rather than a second fake auth system, with every simulated SMS
push logged so delivery is an assertable fact. One real bug was found and
fixed during browser testing, not merely flagged: the USSD session
emulator's inactivity timer kept counting down even after the session
showed "SESSION EXPIRED." Real mobile money/OTP/SMS gateway integration
remains simulated — confirmed 8 September 2026 as Emmanuel's deliberate,
unchanged decision, not an oversight, and now the only item left on
Stage 6's "not yet built" list. Order Reconciliation's vendor payout was
also fixed 7 September 2026 to correctly include a confirmed
`InputOrder`'s real cost, not just `MechanisationRequest` rows.

**Known gap, tracked for a separate task (not this one):** the Matching
Queue records which farmer an Opportunity was assigned to
(`assigned_farmer_id`), but the Farmer flow's opportunity list doesn't yet
filter on it — every active farmer can currently see and accept an
opportunity assigned to someone else. A background task to fix this
("Fix farmer opportunity visibility scoping") has been queued but had not
started as of 7 September 2026 — no commits from it exist yet, so this gap
remains open. See [Stage 6 Build/README.md](Stage%206%20Build/README.md)
"Known limitations" for detail.

**Responsive QA pass (5 September 2026, extended 6–7 September 2026):**
every flow above was verified at desktop (1280px), tablet (768px), and
phone (375px) — no horizontal page overflow, no interactive element under
the PRD Section 5.1-confirmed 44px touch-target minimum. The 5 September
pass found and fixed a systemic bug: none of the frontend files had a
`<meta name="viewport">` tag, so every phone/tablet CSS rule built across
all of Stage 6 never actually applied on a real device (real browsers were
silently rendering at a ~980px zoomed-out layout instead). Also fixed:
several sub-44px controls (device toggle, restart button, planting-calendar
week inputs, small table-action buttons), and a real rendering bug in
Logistics Dispatch where an inbound (harvest-pickup) job showed "undefined"
and "null acres" because the card renderer hadn't been updated for the new
job type. The 6 September pass, re-testing Harvest Pickup after adding its
new order-selection dropdown, found its two-column layout used a raw
inline grid with no responsive collapse rule (unlike the shared pattern
every other two-column layout in this codebase uses), so it stayed
two-column and cramped below tablet width instead of stacking — fixed by
switching it to the shared, already-responsive `.grid.g2` class. The 7
September pass (building Order Inputs + Vendor Product Catalogue) caught a
JS quote-mismatch typo before it ever reached testing, fixed two stale UI
strings claiming already-shipped features had "no backend yet," and found
a real navigation dead-end in the new Vendor flow (two parallel post-login
destinations with no way to reach the second). The MoFA Compliance Report
and User & Role Admin builds (also 7 September) introduced no new issues
-- both are purely linear flows using `.grid.g2` from the start, with no
parallel post-login destinations to re-check for reachability either.
**Extended again 8 September 2026** across all ten new/touched files in
the 24-item expanded-scope pass: every screen reuses the same shared
chrome and responsive patterns established above, so no fresh instances
of the earlier systemic bugs turned up — verified via live DOM
measurement at 375/768/1280px, including the USSD emulator's bespoke
phone-frame layout, independently checked and clean. All twenty-three
flows now pass at all three breakpoints. See [Stage 6 Build/README.md](Stage%206%20Build/README.md)
for the full writeup. This check is mandatory for every new screen going
forward, not retrofitted after — and, per this pass, applies again
whenever an existing screen is substantively re-touched.

**Stage 7 — Testing (9 September 2026, complete).** Every claim above is
now backed by an automated test suite rather than only narrative
verification: 575 tests (pytest for unit/API/RBAC/simulated-integration,
Playwright for end-to-end across all 24 Stage 6 screens), 88% statement
coverage on the backend, run against a real PostgreSQL test database
(`farm_master_test`), not mocks or SQLite. Full traceability — every PRD
Must-Have and every one of the 24 screens mapped to its specific test — is
in [Stage 6 Build/TEST_PLAN.md](Stage%206%20Build/TEST_PLAN.md). One real
application defect was found and fixed during this pass: the USSD phone
emulator's input field and Send button fell under the 44px touch-target
minimum at 375px (missed by the manual responsive passes above, which
checked the emulator for overflow but not independently for touch
targets). Every other issue found while building the suite was a
test-infrastructure bug (a blocked subprocess pipe, an async-render race
in a test helper, a wrong row selector, a fabricated foreign key, a false
positive in a source scan, a wrong file path, a blind timeout) — fixed
without changing any app behaviour; see TEST_PLAN.md for the full,
honest account of each. See [Stage 6 Build/README.md](Stage%206%20Build/README.md)
"Running the test suite" for how to run it yourself.

**Internal Ops Staff roles (9 September 2026).** Before onboarding real
pilot staff, Control Centre access was split into scoped roles instead of
every internal user sharing the one Super Admin login. Worth noting: the
premise that only Super Admin could reach Control Centre wasn't accurate
even before this change — Agronomist, Logistics, and Finance have had
their own role-scoped tiles there since the 8 September 2026 pass. Two
genuinely new roles were added on top of the existing seven: **Pilot
Operations Coordinator** (Matching Queue access — assigning farmers to
buyer requirements — without Formula Builder, visit logs, messaging, or
any account/role administration) and **Compliance/Reporting Officer**
(MoFA compliance report generation plus read-only order/reconciliation
visibility, without fee capture or settlement/payout release authority).
**Logistics/Fleet Coordinator** reuses the existing Logistics role
unchanged — its scope (dispatch, delivery status, fleet tracking, no
farmer/buyer matching, no admin) already matched exactly, so no new role
was needed, only a persona-named seed account. Full detail, including why
farmer "onboarding approval" isn't a real gate in this codebase (farmer
accounts activate automatically on OTP verification — only Buyer/Vendor
registrations go through Super Admin review), is in
[Farm_Master_SDD_Stage6.docx](Farm_Master_SDD_Stage6.docx) Section 29.

**Real automatic responsive design (9 September 2026).** The manual
Desktop/Tablet/Phone preview toggle every flow page shipped with since
Stage 6 is gone. Layouts now respond to the browser's actual width, the
same as any production site — no toggle, no dev-tools requirement, no
approximation. The existing `@container` breakpoints (767px/1023px) were
always correct; the bug was that the canvas's width was pinned by the
toggle's JS-set class instead of tracking the real viewport, so it never
saw those breakpoints on an actual device. Fixed by making the canvas
fluid, and by replacing the old one-off 860px "flatten the sidebar" rule
with a real hamburger-triggered off-canvas drawer for the rail navigation
below 768px, matching this codebase's own breakpoint convention. Verified
live (not just read from the CSS) across all 23 flow pages at 375/800/1280px
real browser widths — see [Farm_Master_SDD_Stage6.docx](Farm_Master_SDD_Stage6.docx)
Section 30 for the full account, including which single file needed an
extra fix. **To check it yourself:** just drag the browser window
narrower on any flow page — the rail sidebar should narrow, then (below
roughly 768px) collapse behind a hamburger button that opens as a sliding
drawer.

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
- <http://127.0.0.1:8000/reconciliation-flow> — Finance & Reconciliation (Internal Operations)
- <http://127.0.0.1:8000/order-inputs-flow> — Farmer Order Inputs
- <http://127.0.0.1:8000/vendor-catalogue-flow> — Vendor Product Catalogue
- <http://127.0.0.1:8000/mofa-report-flow> — MoFA Compliance Report (Internal Operations)
- <http://127.0.0.1:8000/user-admin-flow> — User & Role Admin (Super Admin)
- <http://127.0.0.1:8000/visit-logs-flow> — Field Visit Logs & Agronomist Messaging (Agronomist)
- <http://127.0.0.1:8000/proof-trunking-flow> — Proof of Delivery & Trunking (Logistics)
- <http://127.0.0.1:8000/reporting-flow> — Reporting Dashboard (Finance)
- <http://127.0.0.1:8000/approvals-flow> — Registration Approval Queue & Audit Log (Super Admin)
- <http://127.0.0.1:8000/control-centre-flow> — Control Centre Dashboard (any internal role)
- <http://127.0.0.1:8000/buyer-dashboard-flow> — Buyer Dashboard, Docs, Tracking & Invoice
- <http://127.0.0.1:8000/farmer-dashboard-flow> — Farmer Dashboard, Milestones, Messaging & Wallet
- <http://127.0.0.1:8000/vendor-dashboard-flow> — Vendor Dashboard, Billing, Payout & Handoff
- <http://127.0.0.1:8000/ussd-sms-flow> — USSD/SMS Channel (session emulator, Farmer)
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
  backend/tests/  Stage 7 automated test suite (unit, API, RBAC, e2e)
  frontend/   Live HTML pages calling the backend
  README.md   Setup, env vars, manual verification steps
  TEST_PLAN.md  Stage 7 deliverable — test plan & traceability matrix
```

## Key documents

- [PRD (Stage 1)](Farm_Master_PRD_Stage1.docx) — problem, scope, roles, provisional rates
- [Information Architecture (Stage 2)](Farm_Master_IA_Stage2.docx) — sitemaps, user flows, device requirements
- [Style Guide (Stage 4)](Farm_Master_Style_Guide_Stage4.docx) — color/type/component system, and the running log of what's built
- [Software/System Design Document (Stage 6)](Farm_Master_SDD_Stage6.docx) — architecture, database schema, RBAC, audit logging
- [API Documentation (Stage 6)](Farm_Master_API_Documentation_Stage6.docx) — endpoint reference
- [Stage 6 Build/TEST_PLAN.md](Stage%206%20Build/TEST_PLAN.md) — Stage 7 test plan & traceability matrix
- [Stage 6 Build/README.md](Stage%206%20Build/README.md) — setup, environment variables, manual verification, running the test suite
