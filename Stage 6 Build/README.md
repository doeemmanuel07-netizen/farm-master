# Farm Master — Stage 6 Build

Backend foundation (RBAC across 7 roles, audit logging, Finance/Super Admin
segregation of duties) plus the Buyer commitment-fee flow, end to end and
tested. See `Farm_Master_SDD_Stage6.docx` (repo root) for architecture and
`Farm_Master_API_Documentation_Stage6.docx` for the API contract.

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

- One user per role (all passwords: `password123` — **dev-only, never reuse
  as a real credential**):
  - `emmanuel@farmmaster.test` — Super Admin
  - `finance@farmmaster.test` — Finance
  - `agronomist@farmmaster.test` — Agronomist
  - `logistics@farmmaster.test` — Logistics
  - `buyer@farmmaster.test` — Buyer (Tema Grain Processors Ltd.)
  - `farmer@farmmaster.test` — Farmer
  - `vendor@farmmaster.test` — Vendor (Kwame's Agro Supplies)
- The five provisional rate config rows from PRD Section 10 (buyer
  commitment fee, vendor service fee, and the three formula-scaling
  constants) — all marked `PROVISIONAL`.

Re-running the seed is safe; it skips seeding if data already exists.

## Running it

- API root: <http://127.0.0.1:8000>
- Live Buyer flow (real backend, not local JS state): <http://127.0.0.1:8000/buyer-flow>
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

Or just open <http://127.0.0.1:8000/buyer-flow> and click through — every
step (login, submit, pay, view status) is a real network call to the backend
above, not a simulation.

## Known limitations of this pass

- Mobile money payment is simulated (marked successful immediately, no real
  gateway call) — no provider is chosen yet (PRD Section 1.1).
- Card payment deliberately returns `501` rather than pretending to work.
- Farmer and Vendor flows, and the rest of Internal Operations, are not yet
  built — see the SDD, Section 8, for the full list.
