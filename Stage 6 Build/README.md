# Farm Master — Stage 6 Build

Backend foundation (RBAC across 7 roles, audit logging, Finance/Super Admin
segregation of duties) plus the Buyer commitment-fee flow, end to end and
tested. See `Farm_Master_SDD_Stage6.docx` (repo root) for architecture and
`Farm_Master_API_Documentation_Stage6.docx` for the API contract.

## Stack

- **Backend:** Python 3.12 + FastAPI + SQLAlchemy + SQLite (dev).
  Node.js is not installed in the reference environment this was built in —
  Python was already available, so that's what's used. See the SDD, Section 2,
  for the full reasoning; the API is framework-agnostic if a Node/React stack
  is preferred later.
- **Frontend:** plain HTML/CSS/JS (no build step), the same visual system as
  Stages 3–5, served by the backend itself.

## Setup

```bash
cd "Stage 6 Build/backend"
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

The first run creates `farm_master.db` (SQLite) next to the app and seeds:

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
| `FARM_MASTER_DATABASE_URL` | `sqlite:///./farm_master.db` | SQLAlchemy connection string. Point this at a PostgreSQL URL for production — no code change needed. |
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
