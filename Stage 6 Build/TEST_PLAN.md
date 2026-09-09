# Farm Master — Stage 7 Test Plan & Traceability Matrix

Stage 7 (Testing) verifies Stage 6's build against the requirements set in
Stages 1–5. Stages 1–5 are documents, not code — they aren't "tested"
directly; this matrix instead maps every PRD Must-Have and every one of
the 24 screens from the 8 September 2026 expanded-scope pass to the
specific automated test(s) that prove it, so nothing from the confirmed
scope is silently unchecked.

## Layers

| Layer | Location | Tool | What it proves |
|---|---|---|---|
| Unit | `tests/unit/` | pytest | Shared computation modules in isolation — the money/settlement math, formula scaling, dispatch job creation, OTP mechanics, report rendering |
| Integration/API | `tests/api/` | pytest + FastAPI `TestClient`, real Postgres (`farm_master_test`), one rolled-back transaction per test | Every endpoint's happy path, documented 409/422s, and RBAC boundaries, against the real app object and a real database |
| RBAC matrix | `tests/api/test_rbac_matrix.py` | pytest, parametrized | Every GET endpoint × every role, systematically — not spot-checked |
| Simulated integrations | `tests/api/test_simulated_integrations.py` + tests marked `@pytest.mark.simulated` throughout | pytest | OTP/mobile-money/USSD behave correctly **and** stay visibly marked as simulated — includes a source scan asserting no real payment/SMS gateway call exists anywhere in the codebase |
| E2E | `tests/e2e/` | pytest + Playwright (Chromium), a real uvicorn server against `farm_master_test`, real `seed.py` data | Every one of the 24 screens clicked through for real in a browser — real DOM, real fetch calls, real JS — plus responsive/touch-target checks at 375/768/1280px |

Run instructions, the `farm_master_test` database setup, and the dev
dependency file are documented in `Stage 6 Build/README.md`, "Running the
test suite."

## PRD Section 6 Must-Haves → tests

| # | Must-Have | Unit | API | E2E |
|---|---|---|---|---|
| 1 | Buyer commitment-fee payment | — | `test_buyer.py` (fee calc, momo/card, double-pay 409) | `test_registration_and_portals_e2e.py::test_buyer_commitment_fee_full_real_lifecycle`, `::test_buyer_card_payment_shows_real_501_not_a_silent_success` |
| 2 | Farmer opportunity + production formula | `test_formula.py` | `test_farmer.py` (accept, double-accept 409) | `::test_farmer_accepts_a_real_opportunity_and_gets_a_real_formula` |
| 3 | Vendor input ordering → logistics dispatch (both real job sources) | `test_dispatch.py` | `test_vendor.py`, `test_farmer.py` (input orders), `test_logistics.py` (dispatch lifecycle) | `test_order_inputs_catalogue_e2e.py` (all), `test_internal_ops_e2e.py::test_dispatch_*` |
| 4 | Harvest pickup + fulfilment intake/grading | — | `test_farmer.py` (pickup), `test_fulfilment.py` (grading, 409s) | `::test_farmer_requests_harvest_pickup`, `test_internal_ops_e2e.py::test_fulfilment_intake_grades_a_real_delivered_pickup` |
| 5 | Order Reconciliation | `test_reconciliation.py` (full compute_figures suite, incl. the 7 Sep 2026 vendor-payout regression) | `test_reconciliation_api.py` (release actions, 409s) | `test_internal_ops_e2e.py::test_reconciliation_*` |

## The 24 items from the 8 September 2026 completeness-audit pass

| # | Item | Unit | API | E2E |
|---|---|---|---|---|
| 1 | Reporting dashboard | `test_reporting_calc.py` | `test_reporting_api.py` | `test_new_screens_e2e.py::test_reporting_dashboard_shows_real_revenue_streams` |
| 2 | MoFA import | — | `test_mofa.py` | `test_mofa_useradmin_e2e.py::test_mofa_manual_import_creates_a_real_row` |
| 3 | Registration Approval Queue (own screen) | — | `test_auth.py` (approve/reject), `test_admin.py` | `test_new_screens_e2e.py::test_approvals_and_audit_log_screen_shows_real_data` |
| 4 | Field Visit Logs | — | `test_agronomist.py` | `test_new_screens_e2e.py::test_agronomist_logs_and_completes_a_real_field_visit` |
| 5 | Proof of Pickup/Delivery | — | `test_logistics.py` | `::test_logistics_captures_real_gps_proof_of_delivery` |
| 6 | Trunking | — | `test_logistics.py` | `::test_logistics_schedules_and_progresses_a_real_trunking_load` |
| 7 | Buyer Dashboard | — | `test_buyer.py` | `test_new_dashboards_e2e.py::test_buyer_dashboard_opens_a_real_order_across_all_three_tabs` |
| 8 | Buyer Documents | — | `test_buyer.py` | (same test, Documents tab) |
| 9 | Buyer Tracking | — | `test_buyer.py` | (same test, Tracking tab) |
| 10 | Buyer Invoice | — | `test_buyer.py` | (same test, Invoice tab) |
| 11 | Farmer Dashboard | — | `test_farmer.py` | `test_new_dashboards_e2e.py::test_farmer_dashboard_logs_milestone_and_sends_message` |
| 12 | Farmer Milestone Log | — | `test_farmer.py` | (same test) |
| 13 | Agronomist Messaging (both sides) | — | `test_farmer.py`, `test_agronomist.py` | (same test) + `test_new_screens_e2e.py::test_agronomist_replies_to_farmer_message` |
| 14 | Farmer Wallet & Settlement | `test_wallet.py` | `test_farmer.py` | `test_new_dashboards_e2e.py::test_farmer_wallet_shows_real_settlement_figures` |
| 15 | Vendor Dashboard | — | `test_vendor.py` | `test_new_dashboards_e2e.py::test_vendor_dashboard_pays_billing_and_views_payout_handoff` |
| 16 | Vendor Subscription & Billing | — | `test_vendor.py`, `test_simulated_integrations.py` | (same test) + `::test_vendor_billing_card_still_501s_in_the_browser` |
| 17 | Vendor Payout Statement | `test_payout.py` | `test_vendor.py` | (same test) |
| 18 | Vendor Logistics Handoff Status | — | `test_vendor.py` | (same test) |
| 19 | Control Centre Dashboard | — | `test_dashboard.py` (role-tile isolation) | `test_new_screens_e2e.py::test_control_centre_dashboard_shows_role_scoped_tiles` |
| 20 | Audit Log browsing screen | — | `test_admin.py` | `test_new_screens_e2e.py::test_approvals_and_audit_log_screen_shows_real_data` |
| 21–24 | USSD/SMS channel (menu, pickup, payment, SMS log) | — | `test_ussd.py`, `test_simulated_integrations.py` (gateway-scan) | `test_ussd_e2e.py` (all 6, incl. the session-timer regression test) |

## RBAC — systematic, not spot-checked

`tests/api/test_rbac_matrix.py` parametrizes every GET endpoint against
every one of the 7 roles (44 endpoints × 7 roles), asserting 403 for every
disallowed role and non-403 for the allowed one(s), plus a no-token check.
Every POST/PUT endpoint's RBAC is covered inline in its own domain test
file alongside its functional behaviour (e.g. `test_admin.py`'s
segregation-of-duties parametrization explicitly re-confirms Finance is
blocked from every `/admin/*` route).

## Simulated integrations — tested as simulated

`tests/api/test_simulated_integrations.py` (all tests marked
`@pytest.mark.simulated`, along with related tests in `test_auth.py`,
`test_buyer.py`, `test_vendor.py`, `test_ussd.py`):

- OTP: `dev_only_phone_code`/`dev_only_email_code` field-naming contract, single-use, expiry, wrong-purpose rejection.
- Mobile money: every method returns a `SIM-`-prefixed `transaction_ref`; `card` always 501s, on both the Buyer commitment fee and Vendor subscription.
- USSD/SMS: every simulated push writes a real, queryable `UssdSmsLog` row.
- A source scan (`test_no_real_gateway_import_or_call_in_any_simulated_router`) asserts no real HTTP client call, SDK import, or live API endpoint URL for a payment/SMS provider exists anywhere in `auth.py`, `buyer.py`, `vendor.py`, or `ussd.py` — deliberately does **not** flag the honest UI copy naming Paystack/Hubtel as the still-pending candidates (PRD Section 1.1), only what would indicate an actual wired integration.

## Responsive/touch-target checks

`tests/e2e/helpers.py::assert_responsive_clean` — the same live-DOM
measurement (`scrollWidth`/`clientWidth` for overflow, `getBoundingClientRect()`
for the 44px touch-target minimum) performed manually throughout Stage 6,
now automated. Run at 375/768/1280px against: the buyer, dispatch,
order-inputs, user-admin, new-screens, new-dashboards, and USSD flows —
one representative screen sharing each CSS pattern in the codebase, plus
the USSD emulator's bespoke (non-shared) phone-frame layout checked on
its own.

## Bugs found during Stage 7 and how each was resolved

Reported in full to Emmanuel as they were found — see the SDD's Stage 7
section and the relevant commit messages for the complete writeups. Summary:

| Bug | Real app defect? | Fix |
|---|---|---|
| USSD phone-emulator input/Send button under 44px at 375px | **Yes — real UI bug** | Added `min-height:44px` (and `min-width` on the button) to `.phone-keys input`/`.phone-keys button` in `ussd_sms_flow_live.html` |
| `subprocess.Popen(..., stdout=PIPE)` never read in the E2E server fixture | No — test infrastructure | uvicorn's own access-log lines filled the unread OS pipe buffer, blocking the child process's next stdout write and freezing its event loop after enough requests — this is what caused the initial 41-test E2E cascade. Fixed by redirecting to a real log file instead of a pipe. |
| `login_and_verify_otp` returned once `#canvas` existed, not once post-login content actually rendered | No — test infrastructure | `#canvas` is a static, always-present div; waiting on it proved nothing about the async data-fetch-then-render completing. Fixed to wait for `#otpBtn` to detach, which only happens once the real render() has replaced the canvas. This was also the root cause of several `click_flow_step` failures downstream (flow-rail steps have no click listener until `state.token` triggers a "done" class, which requires that same render to have happened). |
| Matching Queue E2E test clicked `.first` row, which was the non-clickable PRODUCTION-status seed row, not a MATCHING one | No — test bug | Selected `tr.clickable[data-req]` instead, matching the app's own clickability marker |
| `test_harvest_pickup_rejects_order_farmer_never_accepted` used a fabricated string as a real foreign key | No — test bug, and a genuine confirmation that Postgres's FK enforcement works as the SDD says it should (SQLite would not have caught this) | Used a real `BuyerRequirement` row instead |
| Simulated-gateway source scan flagged "paystack"/"hubtel" as forbidden substrings | No — test bug (false positive against honest, correct UI copy naming the still-pending candidates) | Narrowed the scan to actual integration signals (HTTP calls, SDK imports, live API URLs) |
| README path miscalculated by one directory level in a test | No — test bug | Fixed the relative path |
| `test_useradmin_add_internal_user` used a blind 500ms wait after a two-step async action | No — test bug (intermittent race) | Replaced with an active `wait_for` |

## Coverage

See the coverage summary reported alongside this file's commit — generated
via `pytest --cov=app --cov-report=html`, `htmlcov/` (gitignored, local
artifact only).
