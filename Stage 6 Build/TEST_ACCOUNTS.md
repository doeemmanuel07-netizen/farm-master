# Farm Master — Test Accounts (10 roles)

Reference copy for local testing. All passwords are dev-only — never
reuse as a real credential. Every login is a real two-step flow
(password → OTP), with both OTP codes pre-filled since delivery is
simulated.

Verified live (real login + OTP round trip against the running server)
on 2026-09-10.

| # | Role | URL | Email | Password |
|---|---|---|---|---|
| 1 | Farmer | http://127.0.0.1:8000/farmer-flow  | farmer@farmmaster.test | password123 |
| 2 | Buyer | http://127.0.0.1:8000/buyer-flow  | buyer@farmmaster.test | password123 |
| 3 | Vendor | http://127.0.0.1:8000/vendor-flow  | vendor@farmmaster.test | password123 |
| 4 | Agronomist | http://127.0.0.1:8000/matching-flow  |  agronomist@farmmaster.test | password123 |
| 5 | Logistics | http://127.0.0.1:8000/dispatch-flow  | logistics@farmmaster.test | password123 |
| 6 | Finance | http://127.0.0.1:8000/reconciliation-flow  | finance@farmmaster.test | password123 |
| 7 | Super Admin | http://127.0.0.1:8000/user-admin-flow,  http://127.0.0.1:8000/control-centre-flow  | emmanuel@farmmaster.test | password123 |
| 8 | Pilot Operations Coordinator | http://127.0.0.1:8000/control-centre-flow  | ops.coordinator@farmmaster.test | password123 |
| 9 | Logistics/Fleet Coordinator | http://127.0.0.1:8000/control-centre-flow | fleet.coordinator@farmmaster.test  | password123 |
| 10 | Compliance/Reporting Officer | http://127.0.0.1:8000/control-centre-flow  | compliance.officer@farmmaster.test  | password123 |

## Notes

- Roles 4–6 (Agronomist, Logistics, Finance) each own more than one
  screen — the URL above is that role's primary/first screen. Other
  screens for the same login:
  - Agronomist: http://127.0.0.1:8000/formula-builder-flow, http://127.0.0.1:8000/visit-logs-flow
  - Logistics: http://127.0.0.1:8000/proof-trunking-flow
  - Finance: http://127.0.0.1:8000/mofa-report-flow, http://127.0.0.1:8000/reporting-flow
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

