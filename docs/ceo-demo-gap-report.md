# CEO Platform Demo: Gap Report

**Date:** 11 Oct 2026
**Reference:** [`docs/reference/Farm_Master_Platform_Demo.html`](reference/Farm_Master_Platform_Demo.html), the CEO-approved clickable demo
**Compared against:** `Stage 6 Build/` at commit `22e4f19` (FastAPI + PostgreSQL backend, 14 routers, 25 standalone `*_flow_live.html` pages), plus the PRD (Stage 1), IA (Stage 2), Stage 3 wireframes and the Stage 4 style guide.

Status key: **exists** = built and matches the demo's behaviour · **partial** = the backend/data exists but the UI, copy or rule differs · **missing** = not built · **conflicts** = the demo contradicts a locked PRD/IA/Stage 3 decision that the brief's Section 2 doesn't resolve (these are listed again under "Decisions needed").

---

## 1. Design system (brief §1)

| Demo feature | Status | Notes |
|---|---|---|
| Colour tokens (`--forest-deep` … `--wait-bg`) | **missing** | Every page has its own inline `:root` copy of the Stage 4 palette (`--primary:#1F5E3D`, `--gold:#E8A83C`, `--bg:#F7F8F4`). No shared stylesheet exists, and the 25 pages have drifted slightly from each other. |
| Fraunces + Archivo typography | **missing** | Pages declare `"Manrope", system-ui` but never load any webfont, so they render in the system font. |
| Radius / shadow scale (14 / 999 / 9 / 7, forest-tinted shadows) | **missing** | Current scale is 10–12px cards, 8px buttons, no shadows. |
| Role colour-coding (Farmer = forest, Buyer = gold, Vendor = clay) | **missing** | No role colours. Gold is used as the *primary button* colour everywhere. |
| Top bar (logo mark, wordmark, tagline, segmented portal switcher, status pill) | **partial** | Each page has a left "rail" plus a green in-canvas app header. There's no cross-portal switcher. |
| Buttons primary / ghost / gold / small / disabled | **partial** | `.btn` / `.btn.primary` / `.btn.block` exist per page. No ghost/gold/small variants. |
| Card + hint line, badges, stepper, progress bar | **partial** | All exist per page with different class names (`.card-label`, `.badge.pending/info/success`, `.step .circ`). There's no progress bar. |
| Form field + hint + focus ring, two-column row that stacks | **partial** | `.field-group` / `.grid.g2` exist per page. |
| Data table with expandable detail row | **missing** | |
| Category pill tabs, product card, sticky cart panel | **partial** | `farmer_order_inputs_flow_live.html` has a catalogue + order summary in a different layout. |
| Toast (bottom-centre, ~2.8s) | **missing** | Feedback is shown inline as screen transitions. |
| Multi-step modal (choose → confirm → success) | **missing** | The buyer flow uses full-page steps, not a modal. |
| "Live" activity ticker | **missing** | |
| `prefers-reduced-motion` | **missing** | |
| Dark mode | **exists (not in demo)** | Every current page supports `prefers-color-scheme: dark`. The demo is light-only. See decision **D7**. |
| SVG icon set in place of emoji | **missing** | |

## 2. Overview / landing page (brief §3)

| Demo feature | Status | Notes |
|---|---|---|
| Public landing page at `/` | **missing** | `/` returns 404. The only entry points are the 25 `/…-flow` routes and `/docs`. |
| Hero headline, lede, two CTAs | **missing** | |
| 4-step "How it works" panel | **missing** | |
| Stats ledger computed from the DB | **missing** | There are no `regions` / `fulfilment_centres` tables to count. |
| Three role-coloured portal cards | **missing** | |
| Live activity ticker fed by real events | **missing** | The events exist only as rows in `dispatch_jobs`, `trunking_jobs` and `fulfilment_intakes`. There's no public, anonymised feed endpoint. |

## 3. Farmer Portal (brief §4)

| Demo feature | Status | Notes |
|---|---|---|
| Header "Signed in as {name} · {union} · {region}" | **partial** | The name exists. `users` has no region or union columns. |
| Matched opportunities list (crop icon, qty, buyer, region, weeks to delivery, badge) | **partial** | `GET /farmer/opportunities` returns **every OPEN opportunity to every farmer** (a first-come pool), with no region or crop filter. `Opportunity.deadline` is a free-text string ("12 Sep 2026"), so "Delivery in N weeks" can't be computed reliably. There's no crop field: everything is implicitly maize. |
| Select row → detail panel | **partial** | The live page is a multi-step flow (Board → Detail → Commitments → Formula), not a two-column list/detail. |
| Stepper Matched → Accepted → In production → Harvest & delivery | **partial** | `OpportunityStatus` only has `open` / `accepted`. Production and harvest state live on other tables (`requirement_formula_plans`, `harvest_pickup_requests`) and would have to be derived. |
| Production-formula checklist (variety/spacing, fertiliser, protection, harvest) | **partial** | `ProductionFormula` stores computed input quantities (`seed_kg`, `npk_bags`, `topdress_bags`), and `RequirementFormulaPlan` stores a week-by-week calendar. Neither holds free-text agronomist-authored steps (`formula_steps`). |
| Accept opportunity (single button) | **partial** / **conflicts** | `POST /farmer/opportunities/{id}/accept` exists, including a real 409 for a second acceptance. It **requires `commitments_confirmed: true`**, a Stage 3/5 commitments checklist the demo skips. See **D5**. |
| On accept: 48h agronomist task, SMS/in-app notification, toast, wallet recalc | **missing** | There's no task table. `notifications` exists but only has listing types. `UssdSmsLog` exists for simulated SMS. |
| Wallet & settlement card (input costs, logistics fees, estimated payout) | **partial** / **conflicts** | `app/wallet.py` + `GET /farmer/wallet` compute settlement from **delivered, graded tonnes × price × (1 − trading margin)**, minus confirmed input orders. The brief asks for **accepted tonnes × price − inputs − logistics** with no margin. See **D4**. There's no `wallet_ledger` table: figures are computed on the fly, not stored as movements. |
| Other Stage 3 screens (Registration & KYC, Milestone Log, Agronomist Messaging, Harvest Pickup) | **exists** | Built and tested. They need restyling only. |

## 4. Buyer Portal (brief §5)

| Demo feature | Status | Notes |
|---|---|---|
| Header "Signed in as {organisation} · {Institutional / Private} buyer" | **partial** | `organisation_name` exists. There's no buyer-type field (MoFA linkage is only a free-text `Opportunity.tag`). |
| Crop & variety select (active crops only) | **missing** | `BuyerRequirement.crop` is hard-coded to `"Maize"` in the router. There are no crop or variety tables. |
| Quantity, delivery-by date, grading/spec notes | **partial** / **conflicts** | The current form takes `grade`, `quantity_tonnes`, **`price_per_tonne`**, `delivery_location` and a free-text `delivery_timeline`. The demo has no price or location field, and has spec notes instead of grade. Price per tonne drives farmer settlement and reconciliation. See **D2**. |
| Commitment fee: computed, configurable | **partial** | Already configurable: `RateConfig.buyer_commitment_fee_per_tonne` = GH₵ 90/t, minimum one tonne's worth (PRD §10). The demo shows a fixed GH₵ 1,800. The brief asks for "% of order value with a minimum". See **D3**. |
| Payment modal: provider selector → confirm → success | **partial** | `POST /buyer/requirements/{id}/pay` accepts `momo` / `vodafone` / `airteltigo` / `card`, but **marks the payment SUCCESS synchronously** (simulated), and card returns 501. There's no provider interface, pending state or webhook. The labels use the old brand names. |
| `FM-####` sequential order reference | **missing** | IDs are UUIDs. |
| Orders table with status badge + progress bar + expandable stepper | **partial** | `GET /buyer/requirements` and `/tracking` exist. `RequirementStatus` (`draft` → `pending_payment` → `matching` → `production` → `aggregation` → `shipment`) maps cleanly onto the demo's five steps, except that **there is no `delivered` state**. |
| Toast copy | **missing** | |
| Other Stage 3 screens (verification tracks, compliance docs, MoFA export, tracking, invoice) | **exists** | They need restyling only. |

## 5. Vendor Marketplace + back-office (brief §6)

| Demo feature | Status | Notes |
|---|---|---|
| Category pill tabs: Seeds & Inputs · Equipment Rental · Mechanisation Services | **partial** / **conflicts** | There are **two parallel catalogues** today. (1) `products` (`seed` / `fertiliser` / `crop_protection` / `tools`, with stock, formula pre-fill, and `input_orders` → dispatch) powers Order Inputs. (2) `listings` (product/service, approval workflow, images, region, added in the last three commits) powers Vendor Listings and Listing Review. Neither has equipment-rental day-rates. Mechanisation is a separate request form (`mechanisation_requests`) with date-conflict override. See **D1**. |
| Product grid with vendor name, price + unit, Add to order | **partial** | `GET /farmer/catalogue` returns vendor name, price and unit. |
| Sticky cart: qty × name, remove, total, gold Place order | **partial** | Order Inputs has a summary panel. **Orders are limited to a single vendor** (a deliberate Stage 6 decision). The brief asks to split a multi-vendor cart into per-vendor orders. |
| Requested date + days/acres for equipment/services | **missing** | |
| Place order → per-vendor orders, wallet debit, logistics job, toast with SLA days | **partial** | An order is created as `pending`. The vendor's *confirm* creates the dispatch job. There's no wallet debit and no SLA setting. |
| Agronomist farm visit as a bookable service → ops task | **missing** | `field_visit_logs` exists (agronomist-scheduled). Nothing links a purchase to it. |
| Vendor back-office (catalogue CRUD, mechanisation queue, incoming orders, handoff, billing, payout) | **exists** | They need restyling only. |

## 6. Logistics & ops (brief §7)

| Demo feature | Status | Notes |
|---|---|---|
| Fleet / `vehicles` table | **missing** | Vehicles are free-text labels (`DispatchJob.tricycle_label`, `TrunkingJob.vehicle_label`). |
| Logistics jobs (input delivery, harvest pickup, trunking) | **exists** | `dispatch_jobs` (outbound/inbound) + `trunking_jobs`, with proof of delivery. |
| `logistics_events` feeding tracking, handoff, ticker | **missing** | Status changes overwrite in place, so there's no event history. |
| Fulfilment-centre aggregation per crop/centre/day | **partial** | `fulfilment_intakes` records weigh-in + grade, but has no centre or crop columns (it's implicitly Tema / maize). |
| Ops: payments list, formula editor, matching, task queue, dispatch, settings | **partial** | Matching Queue, Formula Builder, Dispatch, Rates (admin `/admin/rates`) and the Control Centre exist. There's no payments list, agronomist task queue, or crop/region/SLA settings screen. |

## 7. Data model (brief §8)

| Table | Status |
|---|---|
| `regions`, `fulfilment_centres`, `crops`, `crop_varieties`, `farmer_unions` | missing |
| `farmers` (+region, union) / `buyers` (+type, MoFA flag) | partial: single `users` table, role-discriminated |
| `crop_requirements` | exists as `buyer_requirements` (no variety FK, spec notes, `delivery_by` date or reference) |
| `commitment_fee_rules` | partial: one `rate_configs` row |
| `payments` | partial: `commitment_fee_payments` (no provider/network split, provider ref or webhook payload) |
| `production_formulas` + `formula_steps` | partial: no steps table |
| `opportunities` / `farmer_allocations` | partial: `opportunities` doubles as the allocation (`assigned_farmer_id`, `accepted_by`) |
| `vendors` (owned / third-party) | partial: vendor `users` rows. Owned vs third-party is only on `registration_approvals.applicant_type` |
| `catalogue_items` | partial: `products` **and** `listings` (see **D1**) |
| `marketplace_orders` + lines | partial: `input_orders` + `input_order_lines` |
| `wallet_ledger` | missing |
| `vehicles`, `logistics_events`, `agronomist_tasks` | missing |
| `logistics_jobs` | exists as `dispatch_jobs` + `trunking_jobs` |
| `notifications` | partial: listing-only types |
| Migrations | **missing**. The repo uses `Base.metadata.create_all()` + idempotent seed backfills. It has no Alembic, so new **columns** on existing tables and new **enum values** won't apply to an existing database. See **D6**. |

## 8. Documentation

| Item | Status |
|---|---|
| SDD, API docs, Style Guide | exist as `.docx` at the repo root |
| Schema doc + ERD | partial: the schema is described in SDD §(database). There's no standalone ERD. |
| CHANGELOG | missing |
| `docs/design-system.md` | missing |

---

## Decisions needed (conflicts not resolved by brief §2)

- **D1 — Which catalogue powers the marketplace?** `products` (stock, formula pre-fill, wired to orders → dispatch) or `listings` (approval workflow, images, product/service type, the newest work)? *Recommendation:* make **`listings`** the single marketplace catalogue. It already has vendor-managed CRUD, admin approval, images and a product/service type. Add a `kind` (input / equipment / service), a pricing basis (per unit / per day / per acre / per visit) and an optional link to a formula input type. Then point marketplace orders at listings and retire `products` once Order Inputs is migrated.
- **D2 — Buyer price per tonne.** The demo form has no price field, but price per tonne drives farmer settlement, reconciliation and the invoice. *Recommendation:* keep a "Target price per tonne (GH₵)" field on the buyer form, pre-filled from a configurable per-crop reference price.
- **D3 — Commitment fee rule.** PRD §10 says GH₵ 90 per tonne (minimum one tonne's worth). The brief says "% of order value with a minimum". *Recommendation:* add a `commitment_fee_rules` table that supports both `per_tonne` and `percent_of_value` (each with a minimum), seeded with the PRD's per-tonne rule so today's figures don't change.
- **D4 — "Estimated payout" maths.** `wallet.py` applies the PRD trading margin to *delivered, graded* tonnes. The brief's formula uses *accepted* tonnes with no margin. *Recommendation:* show **estimated payout = accepted tonnes × price × (1 − trading margin) − inputs − logistics fees** (a forecast), keep the existing delivered/graded figure as the actual settlement on the full statement, and back both with `wallet_ledger` entries.
- **D5 — Commitments checklist on accept.** Stage 3/5 requires the farmer to tick commitment items before accepting. The demo has a single button. *Recommendation:* keep the checklist as a short confirm step inside the detail panel (one click opens it, one click accepts), so the business rule stays.
- **D6 — Migrations.** There's no migration tool. *Recommendation:* introduce **Alembic** (a new dependency, flagged per brief §0) with a baseline revision of the current schema, then one revision per change. The alternative is a small hand-written `ALTER … IF NOT EXISTS` upgrade step at startup.
- **D7 — Dark mode.** Every current page supports dark mode and the demo is light-only. *Recommendation:* keep dark mode by deriving dark values for the new tokens, with the light theme matching the demo exactly.
- **D8 — Front-end shape.** The demo is one page with three portal tabs. The app is 25 standalone pages, each with a developer "flow rail". *Recommendation:* add real portal pages (`/`, `/farmer`, `/buyer`, `/marketplace`) built from the shared component CSS/JS (vanilla, no new framework), and restyle the existing flow pages onto the same tokens, keeping their routes working.

---

## Decisions taken (11 Oct 2026)

| # | Decision |
|---|---|
| D1 | **Listings** become the single marketplace catalogue (gains `kind` = input / equipment / service, a pricing basis and an optional formula input type). Marketplace orders reuse `input_orders` / `input_order_lines`, with lines pointing at a listing, so reconciliation, wallet, dispatch and vendor payout keep working. `products` is retired once Order Inputs is moved over. |
| D2 | Keep a **target price per tonne** field on the buyer form, pre-filled from a configurable per-crop reference price. |
| D3 | `commitment_fee_rules` table supporting `per_tonne` and `percent_of_value` (each with a minimum), seeded with PRD §10's GH₵ 90/t rule. |
| D4 | **Estimated payout = accepted t × price × (1 − trading margin) − input costs − logistics fees.** Actual settlement stays on delivered/graded tonnes. Both are backed by `wallet_ledger`. |
| D5 | Keep the commitments checklist as a short confirm step inside the accept action. |
| D6 | Introduce **Alembic** with a baseline revision. |
| D7 | Keep dark mode: the light theme matches the demo exactly, and dark values are derived. |
| D8 | Vanilla HTML/CSS/JS portal pages (`/`, `/farmer`, `/buyer`, `/marketplace`) on shared component files. Existing flow pages are restyled onto the same tokens. |


---

## Implementation status (11 Oct 2026, end of day)

### Finished (built, tested, committed)

| Brief § | Feature | Where |
|---|---|---|
| §1 | Design system: tokens, components, icons, toast, modal, stepper, ticker, 44px touch targets, reduced motion | `frontend/assets/`, `docs/design-system.md`, `/design-system` |
| §2A–C | Crops/varieties, 16 regions and centres, unions, profile fields; pilot = Maize + Greater Accra/Tema | `app/reference.py`, `/admin/crops`, `/admin/regions`, `/admin/fulfilment-centres` |
| §2D | Payments behind `PaymentProvider` (sandbox default; Paystack/Hubtel drivers), webhook-only settlement, configurable fee rule, rebranded networks | `app/payments/`, `app/fees.py` |
| §2E / D1 | Marketplace on listings, per-vendor checkout, products retired, formula pre-fill | `app/marketplace.py`, `/marketplace` |
| §2F | Agronomist visit as a service that creates an agronomist task | marketplace + `/ops/agronomist-tasks` |
| §3 | Public landing page with DB-computed ledger and live anonymised ticker | `/`, `/api/public/*` |
| §4 | Farmer Portal: matching, stepper, formula steps, accept (48h task + SMS/in-app), wallet ledger | `/farmer` |
| §5 | Buyer Portal: order form from config, payment modal, FM-#### orders, derived stepper/progress | `/buyer` |
| §6.1 | Marketplace page: tabs, cards, sticky cart, qty stepper, dates, place order | `/marketplace` |
| §7 | Fleet, logistics events, aggregation, order advance, payments list (API), task queue (API) | `app/fleet.py`, `/ops/*` |
| §8 | Alembic migrations 0001–0007, transition tables for every status | `migrations/`, `app/state.py` |
| §9 | E2E suite for every demo interaction + responsive/touch checks; static shareable preview | `tests/e2e/test_ceo_demo_portals_e2e.py`, `scripts/build_static_demo.py` |

Shareable preview (static, snapshot data, no backend): https://claude.ai/artifact/VJ3eaUesdjfFBKRhtPQvQX

### Still in progress

- **Ops page (`/ops`).** The backend is done (payments list, agronomist task queue, formula-step editor API, fleet, aggregation, order advance, fee/crop/region/SLA settings). The page itself isn't built yet, so the landing page's "Operations" link 404s until it is. The existing internal flow pages (Matching Queue, Formula Builder, Dispatch, Intake, Reconciliation, Approvals, User Admin) still work.
- **Restyling the 24 older `*-flow` pages** onto the new tokens (brief §1, "app-wide"). They work but still use the Stage 4 look.
- **Staging seed that reproduces the demo's own people and records** (Kwabena Asante / Nsawam union / Eastern Region, MoFA as buyer, FreshMart, AgriProcess, rice/soybean/tomato orders). The pilot seed and the demo catalogue are done.
- **Full regression run** of all suites after the final commits. Every suite touched by a change was run at the time it changed, and the whole 617-test unit+API suite passed after the Alembic change.

### Open questions for the CEO

1. Brief §6.1 says placing a marketplace order creates the logistics job. The app keeps the existing vendor confirmation step, and confirming creates the job, so vendors can still decline. Keep it, or auto-confirm Farm Master-owned vendors?
2. Provisional values to confirm: reference prices for rice/soybean/tomato, 28-day minimum buyer lead time, 2-day marketplace SLA, 48h agronomist SLA, 6 revenue streams, GH₵ 30 logistics fee.
3. Payment gateway: Paystack or Hubtel? Both drivers exist, but neither has been run against live credentials.
