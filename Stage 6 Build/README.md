# Farm Master — Stage 6 Build

Backend foundation (RBAC across 7 roles, audit logging, Finance/Super Admin
segregation of duties) plus four flows, end to end and tested: Buyer
commitment-fee payment, Farmer opportunity-acceptance + production-formula
receipt, Vendor mechanisation request (including the Super-Admin-approved
date-conflict override), and the Matching Queue -- the first Internal
Operations screen, where an Agronomist assigns a paid buyer requirement to
one or more farmers. See `Farm_Master_SDD_Stage6.docx` (repo root) for
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
  has real candidates to assign (all passwords: `password123` — **dev-only,
  never reuse as a real credential**):
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

Re-running the seed is safe; it skips seeding if data already exists.

## Running it

- API root: <http://127.0.0.1:8000>
- Live Buyer flow: <http://127.0.0.1:8000/buyer-flow>
- Live Farmer flow: <http://127.0.0.1:8000/farmer-flow>
- Live Vendor flow: <http://127.0.0.1:8000/vendor-flow>
- Live Agronomist Matching Queue: <http://127.0.0.1:8000/matching-flow>
- Interactive API docs (Swagger UI): <http://127.0.0.1:8000/docs>
- Health check: <http://127.0.0.1:8000/health>

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `FARM_MASTER_DATABASE_URL` | `postgresql+psycopg://farmmaster:farmmaster_dev_pw@127.0.0.1:5432/farm_master` | SQLAlchemy connection string. Override for a different host/role, or to point at a managed Postgres instance in production. |
| `FARM_MASTER_JWT_SECRET` | a dev-only placeholder string | **Must** be overridden with a real secret outside local dev. Never commit a production value. |

## Manual verification (what's already been tested)

Run the server, then:

```bash
# Login as the seeded buyer
curl -s -X POST http://127.0.0.1:8000/auth/login -H "Content-Type: application/json" \
  -d '{"email":"buyer@farmmaster.test","password":"password123"}'

# RBAC: a farmer token gets 403 on a buyer-only route
# Segregation of duties: a finance token gets 403 on any /admin/* route
# Super Admin: can view /admin/audit-log and see the commitment-fee-capture
# entry appear automatically after a successful payment
```

Or just open any of the `-flow` pages above and click through — every step
is a real network call to the backend, not a simulation.

## Known limitations of this pass

- Mobile money payment is simulated (marked successful immediately, no real
  gateway call) — no provider is chosen yet (PRD Section 1.1).
- Card payment deliberately returns `501` rather than pretending to work.
- The Matching Queue's tonnage split across assigned farmers is an even
  split, a placeholder for real per-farm allocation logic (PRD Section 10).
- Farmer/Vendor account management, and the rest of Internal Operations
  (Formula Builder, Logistics Dispatch, Fulfilment Intake, Finance &
  Reconciliation, Reporting, MoFA Data Exchange), are not yet built — see
  the SDD, Section 8, for the full list.
