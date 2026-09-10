# Farm Master — Test Accounts (10 roles)

Reference copy for local testing. Local dev server:
`http://127.0.0.1:8000` + the URL below. All passwords are dev-only —
never reuse as a real credential. Every login is a real two-step flow
(password → OTP), with both OTP codes pre-filled since delivery is
simulated.

Verified live (real login + OTP round trip against the running server)
on 2026-09-10.

| # | Role | URL | Email | Password | Status |
|---|---|---|---|---|---|
| 1 | Farmer | `/farmer-flow` | `farmer@farmmaster.test` | `password123` | ✅ |
| 2 | Buyer | `/buyer-flow` | `buyer@farmmaster.test` | `password123` | ✅ |
| 3 | Vendor | `/vendor-flow` | `vendor@farmmaster.test` | `password123` | ✅ |
| 4 | Agronomist | `/matching-flow` | `agronomist@farmmaster.test` | `password123` | ✅ |
| 5 | Logistics | `/dispatch-flow` | `logistics@farmmaster.test` | `password123` | ✅ |
| 6 | Finance | `/reconciliation-flow` | `finance@farmmaster.test` | `password123` | ✅ |
| 7 | Super Admin | `/user-admin-flow`, `/control-centre-flow` | `emmanuel@farmmaster.test` | `password123` | ✅ |
| 8 | Pilot Operations Coordinator | `/control-centre-flow` | `ops.coordinator@farmmaster.test` | `password123` | ✅ |
| 9 | Logistics/Fleet Coordinator | `/control-centre-flow` | `fleet.coordinator@farmmaster.test` | `password123` | ✅ |
| 10 | Compliance/Reporting Officer | `/control-centre-flow` | `compliance.officer@farmmaster.test` | `password123` | ✅ |

## Notes

- Roles 4–6 (Agronomist, Logistics, Finance) each own more than one
  screen — the URL above is that role's primary/first screen. Other
  screens for the same login:
  - Agronomist: `/formula-builder-flow`, `/visit-logs-flow`
  - Logistics: `/proof-trunking-flow`
  - Finance: `/mofa-report-flow`, `/reporting-flow`
- Role 9 (Logistics/Fleet Coordinator) is a second account under the
  existing `Role.LOGISTICS` — not a separate role in the database. Its
  scope (dispatch, delivery status, fleet tracking, no farmer/buyer
  matching, no admin) already matched what was requested, so no new
  role was added for it.
- Roles 8–10 are new Internal Ops Staff roles added 9 September 2026 —
  see `Farm_Master_SDD_Stage6.docx` Section 29 for the exact
  endpoint-level permissions each was granted (and denied).

## Starting the server

```bash
cd "Stage 6 Build/backend"
python -m uvicorn app.main:app --reload --port 8000
```
