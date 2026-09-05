# Farm Master — Stage 6 Build

Backend foundation (RBAC across 7 roles, audit logging, Finance/Super Admin
segregation of duties) plus five flows, end to end and tested: Buyer
commitment-fee payment, Farmer opportunity-acceptance + production-formula
receipt, Vendor mechanisation request (including the Super-Admin-approved
date-conflict override), the Matching Queue -- where an Agronomist assigns
a paid buyer requirement to one or more farmers -- and the Production
Formula Builder, where an Agronomist turns an assigned requirement into a
planting calendar and input schedule and publishes it to those farmers.

Added 5 September 2026, cutting across all of the above: real-time OTP
verification via both phone and email, at both registration and login, for
all seven roles (PRD Section 12) -- a new confirmed requirement. Real
self-registration (`POST /auth/register`) exists for the first time as
part of this, scoped to Farmer/Buyer/Vendor; Internal Operations accounts
stay Super-Admin-provisioned and only see the OTP step at login. Delivery
is SIMULATED (see "Known limitations") -- both codes come back in the API
response instead of an actual SMS/email being sent.

See `Farm_Master_SDD_Stage6.docx` (repo root, Sections 13-14) for
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
- The five provisional rate config rows from PRD Section 10 (buyer
  commitment fee, vendor service fee, and the three formula-scaling
  constants) — all marked `PROVISIONAL`.
- Two buyer requirements already past payment (status `MATCHING`) so the
  Matching Queue has something to assign on first run.
- One buyer requirement already assigned to two farmers (status
  `PRODUCTION`, real `Opportunity` rows with `assigned_farmer_id` set) so
  the Production Formula Builder has something real to build a formula for
  on first run.

Re-running the seed is safe; it skips seeding if data already exists.

## Running it

- API root: <http://127.0.0.1:8000>
- Live Registration + OTP flow: <http://127.0.0.1:8000/register-flow>
- Live Buyer flow: <http://127.0.0.1:8000/buyer-flow>
- Live Farmer flow: <http://127.0.0.1:8000/farmer-flow>
- Live Vendor flow: <http://127.0.0.1:8000/vendor-flow>
- Live Agronomist Matching Queue: <http://127.0.0.1:8000/matching-flow>
- Live Production Formula Builder: <http://127.0.0.1:8000/formula-builder-flow>
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

Or just open any of the `-flow` pages above and click through — every step
is a real network call to the backend, not a simulation.

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
- Internal Operations account creation (Agronomist/Logistics/Finance/Super
  Admin) still has no UI -- these roles are Super-Admin-provisioned per PRD
  Section 3.2, and today that only happens via `seed.py`; `PUT
  /admin/users/{id}/role` can change an existing account's role but there's
  no "create an internal account" endpoint yet.
- The rest of Internal Operations (Logistics Dispatch, Fulfilment Intake,
  Finance & Reconciliation, Reporting, MoFA Data Exchange) is not yet
  built — see the SDD, Section 8, for the full list.
