# Farm Master — Stage 6 Build

Backend foundation (RBAC across 7 roles, audit logging, Finance/Super Admin
segregation of duties) plus twenty-three flows, end to end and tested,
covering every screen in the confirmed IA/wireframe/visual scope except
the payment/OTP gateway integration itself (see "8 September 2026" below
for the full list of what this pass added). The original fourteen: Buyer
commitment-fee payment, Farmer opportunity-acceptance + production-formula
receipt, Vendor mechanisation request (including the Super-Admin-approved
date-conflict override), the Matching Queue -- where an Agronomist assigns
a paid buyer requirement to one or more farmers -- the Production Formula
Builder, where an Agronomist turns an assigned requirement into a planting
calendar and input schedule and publishes it to those farmers -- Logistics
Dispatch, where a confirmed vendor mechanisation request, a confirmed
input order, or a farmer's harvest pickup request automatically becomes a
real dispatch job that Logistics assigns a tricycle to and marks
delivered -- Harvest Pickup Request + Fulfilment Centre Intake & Grading,
where a farmer's pickup request (optionally linked to one of their own
accepted buyer orders) flows through dispatch to Finance, who weighs it in
and grades it -- Finance & Reconciliation, where Finance sees the
commitment fee received, farmer settlement due, vendor payout due, and
Farm Master's trading margin for each order, computed live from that real
linked data, and can release settlement/payout -- Order Inputs + Vendor
Product Catalogue, where a Farmer buys seed/fertiliser/crop-protection/
tools from a Vendor's catalogue (quantities pre-filled from their
production formula), and the Vendor confirms or declines the order -- and
MoFA Compliance Report, where Finance sees (and exports as CSV/PDF) one
row per graded delivery linked to a real buyer order: volume, quality
grade, buyer, and delivery date -- and User & Role Admin, where a Super
Admin manages accounts across all four portals: change an internal
staff member's role, suspend/reactivate an external account, review a
pending Buyer/Vendor registration inline, or create a new internal
(Agronomist/Logistics/Finance/Super Admin) account outright.

Logistics Dispatch and Order Inputs together complete PRD Section 6
Must-Have #3 ("Vendor input ordering routed to logistics dispatch") --
Order Inputs is the literal scope (a Farmer buying from a Vendor's Product
Catalogue), Logistics Dispatch's mechanisation-request path is the other
real job source. Harvest Pickup + Fulfilment Intake completes Must-Have
#4, and Finance & Reconciliation completes Must-Have #5, the last of the
pilot's five must-haves -- all five are now built. See "Known limitations"
for the trading-margin rate's business-unconfirmed status.

**User & Role Admin (7 September 2026) closes out this pass's punch
list** -- built against the confirmed Stage 4 visual
(`internal_operations_visual.html:460-484`), which needed no scope
decisions: the "+ Add internal user" action, both tables (internal staff
with change-role; external accounts with suspend/reactivate/review), and
the mockup's own caption requirement that every action here writes to the
Audit Log, are all real and verified -- see "Known limitations" for the
handful of adjacent internal-operations screens (Reporting's own
dashboard, MoFA's import half, and a few Stage 4 screens never in Stage
6's Must-Have scope to begin with) that remain genuinely unbuilt, so nothing
here is overclaimed as "all of internal operations is done."

**Fixed 7 September 2026, same pass as MoFA Compliance Report:** Order
Reconciliation's vendor payout previously only read confirmed
`MechanisationRequest` rows -- any order settled through a confirmed
`InputOrder` (Order Inputs, above) silently under-reported what was
actually owed to the vendor, since `InputOrder` has no direct link to a
buyer order and nothing traced its real `total_cost` into the
computation. Fixed by deriving the link (InputOrder.production_formula_id
-> ProductionFormula.opportunity_id -> Opportunity.buyer_requirement_id)
and summing both real sources. Flagged at the end of the previous pass,
not left as another "flagged but not fixed" note -- see "Known
limitations" for the verified before/after figures.

Added 5 September 2026, cutting across all of the above: real-time OTP
verification via both phone and email, at both registration and login, for
all seven roles (PRD Section 12) -- a new confirmed requirement. Real
self-registration (`POST /auth/register`) exists for the first time as
part of this, scoped to Farmer/Buyer/Vendor; Internal Operations accounts
stay Super-Admin-provisioned and only see the OTP step at login. Delivery
is SIMULATED (see "Known limitations") -- both codes come back in the API
response instead of an actual SMS/email being sent.

A full responsive QA pass (5 September 2026) checked every flow at
desktop/tablet/phone and found a systemic bug -- see "Known limitations."

**8 September 2026 — 24 items closed in one pass, following this
session's own completeness audit.** The audit found the confirmed IA/
Stage 3 wireframe/Stage 4 visual scope included substantially more screens
than the six already being tracked (Reporting dashboard, MoFA import,
Registration Approval Queue as its own screen, Field Visit Logs, Proof of
Pickup/Delivery, Trunking) -- eighteen more screens had been in scope
since Stage 2/3 but were never enumerated as missing anywhere. Emmanuel's
decision: all of it is now in Stage 6 scope, not Phase 2. Built and
verified in this pass:

- **The six previously-tracked items**, now all real: Reporting dashboard
  (`GET /reporting/dashboard` -- PRD Section 7's six revenue streams, three
  live and three shown disabled with their deferred phase); MoFA import
  (`GET`/`POST /mofa/import-records` -- a real manual-entry record, the
  honest equivalent of the wireframe's own "no live API yet" stub); the
  Registration Approval Queue's own dedicated screen
  (`/approvals-flow`, reusing the pre-existing, already-audited
  `GET /admin/registrations` and approve/reject endpoints -- no backend
  change); Field Visit Logs (`GET`/`POST /agronomist/visit-logs`); Proof of
  Pickup/Delivery (`GET`/`POST /logistics/jobs/{id}/proof`, GPS via the
  browser's real Geolocation API with manual fallback); and Trunking
  (`GET`/`POST /logistics/trunking`, a real snapshot of graded produce not
  yet claimed by another load, 409 on over-allocation) -- previously
  entirely absent, no model or stub of any kind.
- **Portal dashboards**: Buyer (`GET /buyer/dashboard`), Farmer
  (`GET /farmer/dashboard`), Vendor (`GET /vendor/dashboard`), and the
  Control Centre Dashboard shared by all four internal roles
  (`GET /dashboard/control-centre` -- a common non-sensitive season
  snapshot plus role-scoped tiles; Finance never sees account-admin
  counts, Super Admin never sees reconciliation figures).
- **Farmer**: Wallet & Settlement (`GET /farmer/wallet`, a farmer's own
  delivered tonnage and settlement, order by order), Milestone Log
  (`GET`/`POST /farmer/milestones`, structure-only -- offline sync
  explicitly out of scope, same treatment as Field Visit Logs), and
  Agronomist Messaging (`GET`/`POST /farmer/messages` -- a single shared
  Agronomy inbox, since the pilot's seed data has exactly one Agronomist).
- **Vendor**: Subscription & Billing (`GET /vendor/billing`,
  `POST .../pay` -- reuses the same simulated MoMo/Vodafone/AirtelTigo
  rails as the Buyer commitment fee, card still 501s), Payout Statement
  (`GET /vendor/payout`, read-only -- release stays Finance-only), and
  Logistics Handoff Status (`GET /vendor/handoff`).
- **Buyer**: Documents (`GET /buyer/requirements/{id}/docs`, built from
  real grading results, not a fabricated certificate system), Tracking
  (`.../tracking`), and Invoice (`.../invoice`, reusing
  `reconciliation.py`'s own compute_figures).
- **The Audit Log's first real browsing screen** -- `GET /admin/audit-log`
  has returned real data since 3 September 2026, but nothing ever
  displayed it until now (folded into `/approvals-flow`).
- **The entire USSD/SMS channel** (`/ussd-sms-flow`) -- the feature-phone
  fallback (PRD Section 8) had a Stage 3 wireframe but no Stage 4 visual
  and zero build of any kind before this pass. A real USSD gateway
  authenticates by phone + PIN, a separate unchosen gateway (same status
  as OTP/payment) -- so this reuses the existing JWT web session instead
  of a second fake auth system: a session-based menu emulator (numbered
  options, a real 45-second inactivity timeout, back navigation) driving
  the exact same real backend/tables as the Farmer Portal --
  `POST /ussd/pickup-confirm` literally calls `farmer.py`'s own
  `request_harvest_pickup` rather than reimplementing it. Every simulated
  SMS push is logged (`GET /ussd/sms-log`) so delivery is an assertable
  fact, not just something the frontend claims happened.

One real bug was found and fixed during browser testing, not merely
flagged: the USSD session emulator's inactivity timer kept counting down
even after showing "SESSION EXPIRED," because the render function called
`startSessionTimer()` unconditionally -- fixed to stop for real on expiry,
with a genuine "type anything to dial in again" recovery path.

Real mobile money/OTP/SMS gateway integration remains simulated -- 
confirmed 8 September 2026 as Emmanuel's deliberate, unchanged decision
("keep it simulated"), not an oversight. It is now the only item left on
Stage 6's "not yet built" list.

See `Farm_Master_SDD_Stage6.docx` (repo root, Sections 13-27) for
architecture and `Farm_Master_API_Documentation_Stage6.docx` for the API
contract.

## Stack

- **Backend:** Python 3.12 + FastAPI + SQLAlchemy + PostgreSQL 17. Both
  confirmed 3 September 2026 — no remaining ambiguity on the stack. Started
  on SQLite for local-dev convenience during early Stage 6 work, then
  migrated to a real PostgreSQL instance once production needed it; no
  model changes were required, but every enum-backed field (roles,
  statuses) was explicitly retested against Postgres's stricter native
  ENUM handling. See the SDD, Sections 2 and 11, for the full reasoning.
- **Frontend:** plain HTML/CSS/JS (no build step), the same visual system as
  Stages 3–5, served by the backend itself.

## Setup

This expects a local PostgreSQL 17 instance with a `farmmaster` role and a
`farm_master` database already created (dev-only credentials — never reuse
these anywhere real):

```
Host:     127.0.0.1
Port:     5432
Database: farm_master
Role:     farmmaster
Password: farmmaster_dev_pw
```

If that role/database don't exist yet, create them once as the Postgres
superuser:

```sql
CREATE ROLE farmmaster WITH LOGIN PASSWORD 'farmmaster_dev_pw';
CREATE DATABASE farm_master OWNER farmmaster;
```

Then:

```bash
cd "Stage 6 Build/backend"
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

The first run creates the tables in `farm_master` and seeds:

- One user per role, plus extra Buyer/Farmer accounts so the Matching Queue
  has real candidates to assign (all passwords: `password123`, all phone
  numbers `+2332410000NN` placeholders — **dev-only, never reuse either as
  a real credential**):
  - `emmanuel@farmmaster.test` — Super Admin
  - `finance@farmmaster.test` — Finance
  - `agronomist@farmmaster.test` — Agronomist
  - `logistics@farmmaster.test` — Logistics
  - `buyer@farmmaster.test` — Buyer (Tema Grain Processors Ltd.)
  - `gsfp@farmmaster.test` — Buyer (Ghana School Feeding Programme)
  - `coastal@farmmaster.test` — Buyer (Coastal Feed Mills)
  - `farmer@farmmaster.test` — Farmer (Kofi Mensah)
  - `kojo.mensah@farmmaster.test` — Farmer (Kojo Mensah)
  - `ama.serwaa@farmmaster.test` — Farmer (Ama Serwaa)
  - `vendor@farmmaster.test` — Vendor (Kwame's Agro Supplies)
- The six provisional rate config rows from PRD Section 10 and this pass
  (buyer commitment fee, vendor service fee, the three formula-scaling
  constants, and `trading_margin_pct`) — all marked `PROVISIONAL` (the last
  one additionally `BUSINESS-UNCONFIRMED` — see "Known limitations").
- Two buyer requirements already past payment (status `MATCHING`) so the
  Matching Queue has something to assign on first run.
- One buyer requirement already assigned to two farmers (status
  `PRODUCTION`, real `Opportunity` rows with `assigned_farmer_id` set, a
  real `CommitmentFeePayment`) so the Production Formula Builder has
  something real to build a formula for, and Finance & Reconciliation has a
  real commitment fee received figure, on first run.
- One mechanisation request already confirmed (within its own requested
  window) with a real `DispatchJob` row, linked to the `PRODUCTION`
  requirement above, so the Logistics Dispatch queue has something to
  assign and deliver, and Finance & Reconciliation has a real vendor payout
  due figure, on first run.
- Three harvest pickup requests, each with a real inbound `DispatchJob`:
  one already `DELIVERED` (so the Fulfilment Intake queue has something to
  grade), one still `ASSIGNED` (so the Logistics Dispatch Inbound tab isn't
  always empty either), and one already `DELIVERED` **and** graded, with
  its farmer's opportunity for the `PRODUCTION` requirement marked
  accepted and the pickup itself linked to that requirement, so Finance &
  Reconciliation has a real, non-zero farmer settlement figure on first
  run.
- Five Product Catalogue items for the seeded vendor -- matching the Stage
  3 wireframe's own five example items exactly (seed, NPK fertiliser,
  top-dress fertiliser, crop-protection, tools) -- so Order Inputs and the
  Vendor Product Catalogue both have real data on first run.
- One input order already confirmed (real seed + NPK, real stock
  decremented, real `DispatchJob`), linked to a real `ProductionFormula`
  for Ama Serwaa (her opportunity for the `PRODUCTION` requirement is
  also marked accepted, mirroring Kojo Mensah's above) so the Vendor's
  order queue, the Farmer's order history, the Logistics Dispatch outbound
  tab's third job type, and the `PRODUCTION` requirement's Order
  Reconciliation vendor payout (now correctly including this order's real
  cost, not just the mechanisation request's) all have real data on first
  run.

Re-running the seed is safe; it skips seeding if data already exists.

## Running it

- API root: <http://127.0.0.1:8000>
- Live Registration + OTP flow: <http://127.0.0.1:8000/register-flow>
- Live Buyer flow: <http://127.0.0.1:8000/buyer-flow>
- Live Farmer flow: <http://127.0.0.1:8000/farmer-flow>
- Live Vendor flow: <http://127.0.0.1:8000/vendor-flow>
- Live Agronomist Matching Queue: <http://127.0.0.1:8000/matching-flow>
- Live Production Formula Builder: <http://127.0.0.1:8000/formula-builder-flow>
- Live Logistics Dispatch: <http://127.0.0.1:8000/dispatch-flow> (opens on
  the phone viewport by default -- confirmed phone-first, PRD Section 5.1)
- Live Farmer Harvest Pickup Request: <http://127.0.0.1:8000/harvest-pickup-flow>
- Live Fulfilment Centre Intake & Grading: <http://127.0.0.1:8000/fulfilment-intake-flow>
- Live Finance & Reconciliation: <http://127.0.0.1:8000/reconciliation-flow>
- Live Farmer Order Inputs: <http://127.0.0.1:8000/order-inputs-flow>
- Live Vendor Product Catalogue: <http://127.0.0.1:8000/vendor-catalogue-flow>
- Live MoFA Compliance Report: <http://127.0.0.1:8000/mofa-report-flow>
- Live User & Role Admin: <http://127.0.0.1:8000/user-admin-flow>
- Live Field Visit Logs & Agronomist Messaging: <http://127.0.0.1:8000/visit-logs-flow>
- Live Proof of Delivery & Trunking: <http://127.0.0.1:8000/proof-trunking-flow>
- Live Reporting Dashboard: <http://127.0.0.1:8000/reporting-flow>
- Live Registration Approval Queue & Audit Log: <http://127.0.0.1:8000/approvals-flow>
- Live Control Centre Dashboard (any internal role): <http://127.0.0.1:8000/control-centre-flow>
- Live Buyer Dashboard, Docs, Tracking & Invoice: <http://127.0.0.1:8000/buyer-dashboard-flow>
- Live Farmer Dashboard, Milestones, Messaging & Wallet: <http://127.0.0.1:8000/farmer-dashboard-flow>
- Live Vendor Dashboard, Billing, Payout & Handoff: <http://127.0.0.1:8000/vendor-dashboard-flow>
- Live USSD/SMS Channel (session emulator): <http://127.0.0.1:8000/ussd-sms-flow>
- Interactive API docs (Swagger UI): <http://127.0.0.1:8000/docs>
- Health check: <http://127.0.0.1:8000/health>

Every one of the `-flow` pages above signs in through two steps now:
password, then a Verify OTP screen with both codes pre-filled (SIMULATED
delivery -- see "Known limitations").

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `FARM_MASTER_DATABASE_URL` | `postgresql+psycopg://farmmaster:farmmaster_dev_pw@127.0.0.1:5432/farm_master` | SQLAlchemy connection string. Override for a different host/role, or to point at a managed Postgres instance in production. |
| `FARM_MASTER_JWT_SECRET` | a dev-only placeholder string | **Must** be overridden with a real secret outside local dev. Never commit a production value. |

## Manual verification (what's already been tested)

Run the server, then:

```bash
# Login as the seeded buyer -- returns an OTP challenge, not a token
curl -s -X POST http://127.0.0.1:8000/auth/login -H "Content-Type: application/json" \
  -d '{"email":"buyer@farmmaster.test","password":"password123"}'

# Verify with the dev_only_phone_code/dev_only_email_code from that response
# to get the real access_token:
curl -s -X POST http://127.0.0.1:8000/auth/login/verify-otp -H "Content-Type: application/json" \
  -d '{"challenge_id":"<from above>","phone_code":"<from above>","email_code":"<from above>"}'

# RBAC: a farmer token gets 403 on a buyer-only route
# Segregation of duties: a finance token gets 403 on any /admin/* route
# Super Admin: can view /admin/audit-log and see the commitment-fee-capture
# entry appear automatically after a successful payment
```

Real-time OTP + registration, specifically: `POST /auth/register` (Farmer/
Buyer/Vendor only -- 422 for internal roles) returns an OTP challenge;
`POST /auth/register/verify-otp` activates a Farmer immediately or moves a
Buyer/Vendor to `pending_review` and creates a real `RegistrationApproval`
row (`GET /admin/registrations` lists it); logging in before verifying, or
before Super Admin approval, both return `403` with a specific reason;
`POST /auth/login` always returns an OTP challenge rather than a token now,
and `POST /auth/login/verify-otp` enforces wrong-code (`401`), reused-
challenge (`409`), and expired-challenge (`410`) correctly. Also clicked
through the full two-step login on all five existing `-flow` pages
(including the Vendor flow's embedded Super-Admin override-approval
control, which also had to be updated to the new login contract) plus the
new `/register-flow` page for both a Farmer (straight to active) and a
Buyer (into the approval queue) registration.

Production Formula Builder, specifically: signed in as the seeded
Agronomist, `GET /agronomist/requirements/{id}/formula` on the seeded
assigned requirement returns the real farmer names and per-farmer tonnage
from the Matching Queue's own `Opportunity` rows plus a RateConfig-computed
input schedule; `PUT .../formula` saves calendar edits; `POST
.../formula/publish` publishes, logs a `formula_published` audit entry, and
locks the plan (a second publish or a post-publish edit both return `409`);
a requirement with no assigned farmers yet returns `409` rather than an
empty formula; a farmer or finance token gets `403` on all three routes
(RBAC + segregation of duties). Also clicked through the full flow in
`/formula-builder-flow` end to end, both the editable (unpublished) and
locked (published) states, at desktop and phone widths.

Logistics Dispatch, specifically: a fresh `POST /vendor/requests/{id}/confirm`
(in-window) and a fresh `POST /admin/vendor-requests/{id}/approve-override`
(out-of-window) both auto-create a real `DispatchJob`, verified by checking
`GET /logistics/jobs` grows by one after each; `POST .../dispatch` moves
`assigned` -> `en_route` and a second call correctly `409`s; `POST
.../deliver` moves `en_route` -> `delivered` and a second call correctly
`409`s; a vendor token gets `403` on all three routes. Also clicked through
the full flow in `/dispatch-flow` at the phone viewport -- sign in, OTP,
dispatch a job, mark it delivered, and confirmed the Inbound tab renders an
honest empty state rather than fake data.

Harvest Pickup + Fulfilment Intake, specifically: `POST /farmer/harvest-pickup`
creates a real inbound `DispatchJob` immediately (verified by checking it
appears on `GET /logistics/jobs` right away, no confirmation step); the
Fulfilment Intake queue (`GET /fulfilment/intake-queue`) correctly excludes
jobs not yet `DELIVERED` and jobs already graded; grading before delivery
returns `409`; `POST /fulfilment/intake/{id}` writes a real
`fulfilment_intake_graded` audit entry; vendor and farmer tokens both get
`403` on every Finance route. Also clicked through both new flows in the
browser end to end -- a farmer requesting pickup in `/harvest-pickup-flow`,
and Finance weighing in and grading it in `/fulfilment-intake-flow`, with
the queue correctly emptying out afterward.

Finance & Reconciliation, specifically: `GET /finance/reconciliation`
lists every buyer order at `MATCHING` status or later; `GET
/finance/reconciliation/{id}` computes commitment fee received, delivered
&amp; graded (non-reject) tonnage, buyer invoice value, trading margin, and
farmer settlement/vendor payout due, all live from real linked
`CommitmentFeePayment`, `FulfilmentIntake`, and `MechanisationRequest`
rows rather than the order's originally committed quantity; releasing
farmer settlement or vendor payout with nothing real to release (zero
delivered tonnage, or zero confirmed vendor requests) returns `409`, as
does releasing either one twice; both releases write a real audit entry
(`farmer_settlement_released`, `vendor_payout_released`); vendor and
farmer tokens get `403` on every route. Also verified `POST
/farmer/harvest-pickup`'s new `buyer_requirement_id` link end to end: `GET
/farmer/harvest-pickup/my-orders` correctly returns only the caller's own
*accepted* opportunities for a real order (not merely assigned ones), and
claiming an order the caller never accepted returns `422`. Also clicked
through the full flow in `/reconciliation-flow` -- sign in, OTP, the
orders list, and a full order detail with both releases -- and confirmed
the Harvest Pickup flow's new order dropdown in `/harvest-pickup-flow`.

Order Inputs + Vendor Product Catalogue, specifically: `POST
/farmer/input-orders` validates every line belongs to the same
`vendor_id` (`422` otherwise), rejects a quantity beyond real
`Product.stock_qty` (`409`), and decrements stock immediately as a real
reservation; `POST /vendor/input-orders/{id}/confirm` creates a real
outbound `DispatchJob` (verified via `GET /logistics/jobs` showing the
new `input_order` job type end to end through dispatch and delivery);
`POST .../decline` restores the reserved stock exactly (verified
before/after); both routes `409` on a non-`PENDING` order; vendor and
farmer tokens each get `403` on the other role's routes. Also clicked
through both new flows in the browser end to end -- a Farmer (with a real
`ProductionFormula`) seeing quantities correctly pre-filled by
`formula_input_type` and placing an order in `/order-inputs-flow`, and a
Vendor adding a catalogue item and confirming an order in
`/vendor-catalogue-flow`.

MoFA Compliance Report, specifically: `GET /mofa/compliance-report`
correctly excludes a graded delivery with no linked buyer order even
after grading it (verified: grading Kofi Mensah's general, unlinked
pickup left the report at the same 2 rows), and correctly *includes* a
REJECT-graded row (verified: grading a second real delivery REJECT added
it to the report, since quality grade is one of the four confirmed
columns, not a filter); `GET .../export.csv` and `GET .../export.pdf`
both return real files (`%PDF-` header verified on the PDF) with exactly
the four confirmed columns, in the confirmed order; vendor and farmer
tokens get `403` on all three routes. Order Reconciliation's vendor-payout
fix, specifically: before the fix, the `PRODUCTION` requirement's vendor
payout was `GHS 90` (mechanisation only); after linking Ama Serwaa's real,
confirmed `InputOrder` (seeded, `GHS 784`) via her `ProductionFormula`, it
correctly became `GHS 874` -- verified via the API before releasing it,
then confirmed the release itself still works and still `409`s on a
second attempt. Also clicked through the full flow in
`/mofa-report-flow` -- sign in, OTP, the report table, and both exports.

User & Role Admin, specifically: `GET /admin/users` returns real internal
staff (with the Stage 4 mockup's own verbatim per-role "Scope" text) and
external accounts, split into the two tables the mockup shows;
`POST /admin/users` creates a real internal account (`422` if the role
isn't Agronomist/Logistics/Finance/Super Admin -- Farmer/Buyer/Vendor
self-register instead; `409` on a duplicate email); `PUT
/admin/users/{id}/role` (pre-existing) and the new `POST .../suspend` /
`.../reactivate` all `409` correctly on a no-op (already that role,
already suspended, not suspended); a suspended account is verified to
actually fail login (`403`) via `POST /auth/login`, not just show a
badge; the inline "Review" action reuses the pre-existing
`POST /admin/registrations/{id}/approve`/`reject`, verified end to end
against a freshly self-registered Vendor (register -> OTP-verify ->
appears `pending_review` with a real `registration_approval_id` -> Review
-> Approve -> `active`, with a Suspend action now available). Every one
of the five actions (internal user creation, role change, suspend,
reactivate, registration approve/reject) writes a real audit-log entry --
confirmed by reading `GET /admin/audit-log` after each, not just asserted
from the code. Finance, Farmer, Vendor, Agronomist, and Logistics tokens
each get `403` on every `/admin/*` route tested (Finance included, per
the standing segregation-of-duties rule -- Finance can move money but
must never also grant its own permissions). Also clicked through the
full flow in `/user-admin-flow` -- sign in, OTP, changing a role,
suspending and reactivating an account, adding a new internal user, and
reviewing a real pending registration to approval, all in the browser.

**Responsive QA pass (5 September 2026, extended 6-7 September 2026):**
every one of the thirteen flows was checked at desktop (1280px), tablet
(768px), and phone (375px) -- programmatically
(`document.documentElement.scrollWidth` vs `clientWidth` for overflow;
`getBoundingClientRect()` on every interactive element for touch-target
size), not just by eye, since a screenshot taken while the browser pane
isn't frontmost (or while the pane has been hidden for a while) was found
to render stale or zero-sized layout data in this environment -- fronting
the tab and taking one screenshot before measuring reliably "wakes" it.
The 5 September pass found and fixed a systemic critical bug -- no file
had a `<meta name="viewport">` tag, so every phone/tablet CSS rule built
across all of Stage 6 never actually applied on a real device (confirmed:
`clientWidth` reported `980` regardless of emulated device width until the
tag was added) -- plus several sub-44px controls and one real functional
bug in Logistics Dispatch's job-card renderer (it still read
`job.service`/`job.area_acres` unconditionally, which are `undefined` for
a harvest-pickup job). The 6 September pass, re-testing Harvest Pickup
after adding its order dropdown, found the Request Pickup step's two-column
layout used a raw inline `grid-template-columns` with no responsive
collapse rule of its own (unlike every other two-column layout in this
codebase, which uses the shared `.grid.g2` class) -- at phone width each
column rendered under 175px wide, readable on screen but real content
squeezed into roughly half the space the shared pattern gives it
elsewhere. Fixed by switching it to the shared `.grid.g2` class -- both new
files this pass used `.grid.g2` from the start. The 7 September pass, while
building the two new flows, found and fixed: a JS quote-mismatch typo in
Logistics Dispatch's job-card renderer would have shown for the new
`input_order` type had it not been caught before testing; two stale UI
strings in Logistics Dispatch (an empty-state caption and a rail note both
still said harvest pickup / input ordering had "no backend yet", though
both had been built in earlier passes); and a real navigation dead-end in
the new Vendor Product Catalogue flow -- Catalogue and Input Orders are
parallel post-login destinations, not a linear sequence, but the shared
rail-navigation pattern only allows clicking already-visited ("done")
steps, so there was no way to ever reach Input Orders. Fixed by letting
those two steps stay rail-clickable any time a session token exists. The
7 September MoFA Compliance Report and User & Role Admin builds
introduced no new responsive issues -- both are purely linear flows using
`.grid.g2` from the start, verified clean at all three breakpoints on
first pass; User & Role Admin has no parallel post-login destinations
either, so the navigation-reachability check from the previous finding
didn't apply. All fourteen flows from that pass passed at all three
breakpoints. **Extended again 8 September 2026**, across all ten
new/touched files in the 24-item expanded-scope pass: every screen reuses
the same shared chrome, `.grid.g2`/g3/g4 patterns, and viewport meta tag
established above, so the systemic bugs found there had no fresh
instances -- verified via live DOM measurement (not stale screenshots) at
375/768/1280px, with the USSD emulator's bespoke phone-frame layout (not
the shared `.grid` pattern) independently checked and confirmed clean at
375px on its own. All twenty-three flows now pass at all three
breakpoints -- see "Known limitations" for the full fix list.

**8 September 2026, the 24-item expanded-scope pass, specifically:** a
full curl RBAC battery confirmed 403 both directions on every new/extended
router (agronomist, logistics, finance/reporting, mofa import, buyer,
farmer, vendor, the shared control-centre dashboard, and ussd), plus real
409s on double-capturing proof of delivery and on scheduling more trunking
tonnage than is really available. Every one of the 24 screens was then
clicked through in the browser end to end, not just curled: submitting the
MoFA manual-import form and watching the new row appear; capturing
GPS-based proof of delivery via the browser's real Geolocation API;
scheduling and dispatching a trunking load; paying (and correctly
501-failing on card) a vendor subscription; opening a buyer order's
Documents/Tracking/Invoice tabs and confirming the figures matched the
API exactly; and running a full USSD session end to end -- main menu,
opportunity alert (a real simulated SMS logged), harvest pickup
confirmation (a real `HarvestPickupRequest` created), payment/balance
check, and the SMS log itself, confirming every "sent" message is really
there. One real bug was found this way, not merely flagged: the USSD
emulator's inactivity timer restarted itself after the session already
showed "SESSION EXPIRED" (`renderUssd()` called `startSessionTimer()`
unconditionally) -- fixed to stop for real on expiry, with a genuine
recovery path to dial back in.

Or just open any of the `-flow` pages above and click through — every step
is a real network call to the backend, not a simulation.

## Running the test suite

Stage 7 (9 September 2026) replaced the manual verification above with an
automated suite: 575 tests, 88% statement coverage on `app/`. See
[TEST_PLAN.md](TEST_PLAN.md) for the full layer breakdown and the
PRD-Must-Have/screen-by-screen traceability matrix.

### One-time setup: the test database

Tests run against a second, real PostgreSQL database — `farm_master_test`
— kept completely separate from the `farm_master` dev database above, so
running tests never touches your local dev/demo data. Create it once, as
the Postgres superuser, after granting the `farmmaster` role permission to
create databases:

```sql
ALTER ROLE farmmaster WITH CREATEDB;
CREATE DATABASE farm_master_test OWNER farmmaster;
```

Docker/CI wiring for this database is deliberately deferred — a real local
Postgres instance is all the current suite needs or assumes.

### Install the dev dependencies

```bash
cd "Stage 6 Build/backend"
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
```

`requirements-dev.txt` layers `pytest`, `pytest-cov`, `httpx`, `playwright`,
and `pytest-playwright` on top of `requirements.txt`. The Playwright
browser install is a one-time step (downloads Chromium; only needed for
the E2E layer).

### Run it

```bash
# Unit tests -- shared computation modules in isolation, no database
python -m pytest tests/unit

# API/integration + RBAC matrix + simulated-integration tests -- real
# Postgres (farm_master_test), one rolled-back transaction per test
python -m pytest tests/api

# End-to-end -- a real uvicorn server + Playwright/Chromium, all 24 screens
python -m pytest tests/e2e

# Everything, with coverage
python -m pytest --cov=app --cov-report=term-missing --cov-report=html
```

`tests/e2e` starts and stops its own uvicorn subprocess per session and
resets `farm_master_test`'s schema before running, so it's safe to run
repeatedly without any manual cleanup. The E2E layer is the slowest
(around 20-25 seconds for 46 tests plus browser startup); `tests/unit` and
`tests/api` together (529 tests) typically finish in a few minutes.

Coverage HTML lands in `htmlcov/index.html` (gitignored, local artifact
only). Current result: **575 passed, 88% coverage** on `app/` — the two
largest reported gaps, `app/seed.py` (8%) and a handful of `app/main.py`
route-registration lines, are demo-data bootstrapping and framework wiring
respectively, both exercised for real by the E2E layer running against a
separate uvicorn subprocess whose execution coverage.py doesn't attribute
back to the pytest process.

### What testing found

One real application defect, found and fixed, not merely flagged: the
USSD phone emulator's input field and Send button were under the 44px
touch-target minimum at 375px (missed by the manual responsive passes
below, which checked the emulator for overflow but not independently for
touch targets) — fixed in `frontend/ussd_sms_flow_live.html` by adding
`min-height:44px` (and `min-width` on the button) to `.phone-keys input`/
`.phone-keys button`. Every other issue found while building the suite was
a test-infrastructure bug, fixed without changing any app behaviour — see
TEST_PLAN.md, "Bugs found during Stage 7," for the full list and how each
was diagnosed.

## Known limitations of this pass

- Mobile money payment is simulated (marked successful immediately, no real
  gateway call) — no provider is chosen yet (PRD Section 1.1).
- Card payment deliberately returns `501` rather than pretending to work.
- The Matching Queue's tonnage split across assigned farmers is an even
  split, a placeholder for real per-farm allocation logic (PRD Section 10).
  The Production Formula Builder inherits this: since every farmer assigned
  to one requirement gets an identical tonnage share by construction, it
  shows and publishes one shared input schedule per requirement rather than
  a genuinely per-farmer one -- correct given today's even split, but it
  will need a per-farmer schedule once real per-farm allocation lands.
- **KNOWN GAP -- tracked, not yet scheduled (confirmed with Emmanuel 5 Sep
  2026, deliberately deferred to its own task):** an `Opportunity` row
  created by the Matching Queue is not restricted to the farmer it was
  assigned to. `assigned_farmer_id` records who it was intended for (and is
  what the Production Formula Builder reads), but `GET /farmer/opportunities`
  still returns every open opportunity to every active farmer, so in
  principle a different farmer could accept an opportunity meant for
  someone else. Pre-existing since the Matching Queue pass, not introduced
  by the Formula Builder. Fix means scoping `list_opportunities` (and
  probably `accept_opportunity`'s 409 check) to `assigned_farmer_id` --
  deliberately not done here to keep it from tangling with unrelated work.
- The planting calendar's five stages/week-offsets are fixed columns (Land
  prep, Planting, Top-dress, Weeding, Harvest), matching the pilot's single
  crop (maize) and the Stage 3/4 wireframes exactly -- not a general
  per-crop stage model, which is out of scope for a single-crop pilot.
- Real-time OTP verification (phone + email, registration + login, all
  seven roles -- PRD Section 12) is real end to end -- generated, stored,
  verified, single-use, expiring -- but delivery is SIMULATED, same
  treatment as mobile money: no SMS/email provider is chosen yet (PRD
  Section 1.1/12), so both codes are returned directly in the API response
  instead of actually being sent.
- **Fixed 7 September 2026 -- User & Role Admin.** Internal Operations
  account creation (Agronomist/Logistics/Finance/Super Admin) previously
  had no UI or endpoint at all -- `seed.py` was the only way one ever came
  into existence. `POST /admin/users` (Super Admin only, 422 for any
  self-registering role) now creates one directly, active immediately, no
  OTP challenge -- consistent with every seeded internal account, which
  never went through a registration OTP either, only ever the login one.
  Built against the confirmed Stage 4 visual
  (`internal_operations_visual.html:460-484`) exactly, including a
  "Reactivate" action for suspended accounts that the static mockup
  doesn't itself depict (it shows only one illustrative Active example
  row) but that a real, working Suspend action needs to not be a
  permanent, un-undoable trap.
- **Fixed 8 September 2026 -- Registration Approval Queue now has its own
  dedicated screen** (`/approvals-flow`), split out of its previous inline
  location on User & Role Admin, per the original IA (Stage 4 visual id
  "approvals"). Reuses the same real, already-audited
  `GET /admin/registrations` and approve/reject endpoints -- no backend
  change, purely a UI move.
- **PRD Section 6 Must-Have #3 is now fully built.** "Vendor input ordering
  routed to logistics dispatch" describes a Farmer buying seed/fertiliser
  from a Vendor's Product Catalogue -- Order Inputs + Vendor Product
  Catalogue (added 7 Sep 2026) is that literal scope; Logistics Dispatch's
  `MechanisationRequest` path (Section 15) is the other real outbound job
  source. `DispatchJob` now carries exactly one of three source FKs (see
  SDD Section 15/20).
- **Order Inputs is scoped to a single vendor per order**, mirroring
  `MechanisationRequest`'s own single-vendor scoping -- every line item
  must belong to the same `vendor_id`. With only one seeded vendor this
  isn't a real limitation for the pilot, but a multi-vendor cart (splitting
  one order across vendors) is not supported.
- **Fixed 8 September 2026 -- input order costs now show as a real
  deduction on the Farmer Wallet & Settlement Statement**
  (`GET /farmer/wallet`), per the Stage 3 wireframe. `InputOrder.total_cost`
  was already real and computed; the Wallet screen now actually surfaces
  it against the same farmer's own real settlement due, rather than
  nothing collecting or displaying it. Confirm/decline are themselves
  still not audited (PRD Section 5's scope is role/permission changes and
  financial actions), same treatment as `MechanisationRequest`
  confirm/decline and dispatch/deliver.
- The Vendor Product Catalogue has no edit or delete endpoint, matching the
  Stage 3 wireframe's own scope (list + "+ Add item" only).
- No audit-log entry is written for dispatch/deliver actions -- they're
  operational, not a role/permission change or a financial action (PRD
  Section 5's audit scope), consistent with how routine state changes are
  treated elsewhere in this codebase. Fulfilment Intake's grading action
  *is* audited (`fulfilment_intake_graded`), since it's Finance-owned and
  feeds settlement.
- A graded Fulfilment Intake now feeds real farmer settlement (Finance &
  Reconciliation, below) when its pickup is linked to a buyer order, and
  (fixed 8 September 2026) also feeds the Buyer's own Documents screen
  (`GET /buyer/requirements/{id}/docs`) as a real grading-result row.
- **Order Reconciliation's trading margin rate is BUSINESS-UNCONFIRMED.**
  Unlike the buyer commitment fee (GHS 90/tonne) and vendor service fee
  (GHS 60/tonne), no rate or formula for what a farmer is actually paid, or
  what percentage Farm Master keeps as margin, exists anywhere in the PRD
  (Section 10) or Business Concept doc -- only the qualitative statement
  "margin applied between farmer settlement price and buyer invoice price."
  Confirmed with Emmanuel (6 Sep 2026): modelled as a flat `trading_margin_pct`
  RateConfig row (provisionally 15%) applied to buyer invoice value on
  delivered, graded (non-reject) tonnage -- farmer settlement is the
  remainder. Changeable via `PUT /admin/rates/trading_margin_pct` with no
  code change, same treatment as every other provisional rate, but pending
  real business sign-off before this number means anything financially.
- **Vendor payout's mechanisation side is still seed-data-only.**
  `MechanisationRequest.buyer_requirement_id` (added for Must-Have #5, so a
  vendor payout can be tied to the order it was for) still has no real
  farmer-facing creation endpoint for a `MechanisationRequest` itself, so
  today this link can only be set by `seed.py`.
- **Fixed 7 September 2026 -- vendor payout was silently excluding
  confirmed input orders.** Flagged at the end of the previous pass, not
  left as another "flagged but not fixed" note. `InputOrder` has no direct
  link to a buyer order, so `app/reconciliation.py` previously summed only
  confirmed `MechanisationRequest` rows -- any order settled through a
  confirmed `InputOrder` was under-reporting real vendor payout by exactly
  that order's `total_cost`. Fixed by deriving the link
  (`InputOrder.production_formula_id` -> `ProductionFormula.opportunity_id`
  -> `Opportunity.buyer_requirement_id`) and summing both real sources --
  an input order not tied to any formula still isn't attributable to a
  specific buyer order, which is correct (it's a general farm-input
  purchase, not tied to fulfilling one). Verified before/after against the
  seeded `PRODUCTION` requirement: GHS 90 -> GHS 874.
- Real settlement math uses the order's actually delivered, graded
  (non-reject) tonnage (via `HarvestPickupRequest.buyer_requirement_id`),
  not its originally committed `quantity_tonnes` -- a farmer's pickup is
  only eligible to link to an order they actually accepted (`GET
  /farmer/harvest-pickup/my-orders`, `POST /farmer/harvest-pickup`
  validates this with a `422`), not merely one the Matching Queue assigned
  them.
- **Fixed 5 September 2026, responsive QA pass:** every frontend file was
  missing `<meta name="viewport">`, so no phone/tablet CSS anywhere in
  Stage 6 had ever actually applied on a real device. Also fixed:
  sub-44px device-toggle/restart/flow-step controls (all files), sub-44px
  planting-calendar week inputs (Formula Builder), sub-44px small action
  buttons (Logistics Dispatch, Fulfilment Intake), and a Logistics
  Dispatch rendering bug where an inbound job showed "undefined" and
  "null acres". Two apparent violations (Matching Queue's farmer-selection
  checkboxes, Harvest Pickup's commitment checklist) were confirmed as
  false positives -- both are wrapped in a `<label>` whose actual clickable
  area is comfortably above 44px.
- **Fixed 6 September 2026, extended QA pass:** Harvest Pickup's Request
  Pickup step used a raw inline two-column grid with no responsive collapse
  of its own (every other two-column layout in this codebase uses the
  shared `.grid.g2` class, which collapses to one column under 768px via a
  container query) -- fixed by switching it to that shared class.
- **Fixed 7 September 2026, Order Inputs build:** a JS quote-mismatch typo
  in Logistics Dispatch's job-card renderer (caught before testing, would
  have broken rendering for the new `input_order` job type); two stale UI
  strings in Logistics Dispatch claiming harvest pickup/input ordering had
  "no backend yet" (both had shipped in earlier passes); and a real
  navigation dead-end in the new Vendor Product Catalogue flow, where
  Catalogue and Input Orders -- parallel post-login destinations, not a
  linear sequence -- had no way to reach the second from the first, since
  the shared rail-navigation pattern only allows clicking already-visited
  steps. Fixed by letting those two steps stay rail-clickable any time a
  session token exists. All fourteen flows now verified at 375/768/1280px
  with no horizontal page overflow, no sub-44px interactive element, and no
  layout that stays cramped multi-column below its container's own
  breakpoint.
- **Fixed 8 September 2026 -- MoFA Data Exchange's import half is now
  real too.** No live MoFA API exists to call (still true -- PRD Section
  1.1/9), so `POST /mofa/import-records` is a real manual-entry record,
  the honest equivalent of the wireframe's own "no live API yet" caption,
  not a fake integration against nothing real. The separate "Reporting"
  screen (revenue-stream + pilot-metrics dashboard, IA Section 6) is also
  now real (`GET /reporting/dashboard`) -- three revenue streams are live,
  three stay shown disabled with their deferred phase (Phase 2/2+/4, PRD
  Section 7), never fabricated.
- Report rows require a graded intake AND a buyer-linked pickup; a
  farmer's general (unlinked) delivery never appears even once graded --
  verified by test, not just asserted (see "Manual verification" above).
  REJECT-graded rows are deliberately included, unlike Order
  Reconciliation's own farmer-settlement math, since quality grade is
  itself one of the four confirmed report columns.
- **Stage 6's build now covers every screen in the confirmed IA/
  wireframe/visual scope.** All five PRD Section 6 Must-Haves, User &
  Role Admin, and (8 September 2026) all 24 items from this session's own
  completeness audit -- the six previously-tracked gaps plus eighteen
  more screens and the full USSD/SMS channel -- are built and tested.
  Real mobile money/OTP/SMS gateway integration is the only item left
  not yet built, confirmed as Emmanuel's deliberate, unchanged decision
  (not an oversight) -- see the SDD status line (Section 26) for the
  exact, non-overclaimed scope of "done" as of this pass.
