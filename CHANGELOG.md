# Changelog

All notable changes to the Farm Master web app. Dates are when the change was committed. Earlier history (Stages 1–7) is in the git log and `Farm_Master_SDD_Stage6.docx`.

## [Unreleased] — CEO platform demo alignment

### Added
- `docs/reference/Farm_Master_Platform_Demo.html`: the CEO-approved demo, now the target look and flow.
- `docs/ceo-demo-gap-report.md`: feature-by-feature audit, plus decisions D1–D8.
- Design system: `frontend/assets/tokens.css`, `components.css`, `components.js`, a live gallery at `/design-system`, and `docs/design-system.md`.
- `scripts/responsive_check.py`: headless Chromium no-horizontal-scroll check at 390 / 820 / 1400px.
- Alembic schema migrations (decision D6): a baseline revision of the Stage 6 schema, `alembic upgrade head` at startup (replacing `create_all`), automatic baseline stamping for pre-Alembic databases, and a test that fails if the models and migrations disagree.
- Reference data (brief §2A–C): `regions` (16), `fulfilment_centres` (16, Tema HQ), `crops` + `crop_varieties` (Maize, White Rice, Soybean, Tomato), `farmer_unions`, `farmer_crops`; profile columns on `users`. The pilot config is Greater Accra/Tema + Maize active, and everything else can be switched on from `/admin/crops|regions|fulfilment-centres`.
- `GET /api/public/stats|crops|regions` (landing page, no auth) and `GET /auth/me` (portal header line).
- `docs/database-schema.md`: a table reference and Mermaid ERD generated from the models by `scripts/gen_schema_doc.py`.
- Payments behind a `PaymentProvider` interface (brief §2D/§5.1): sandbox driver (default), Paystack and Hubtel drivers (not yet run against live credentials). Payments stay **pending until a verified webhook** confirms them (`POST /payments/webhook/{provider}`), with idempotency and amount checks. Networks are labelled MTN MoMo / Telecel Cash / AT Money / Card.
- Commitment fee is now a configurable rule (`commitment_fee_rules`, per-tonne or % of value, with a minimum), seeded with PRD §10's GH₵ 90/t so existing figures don't change.
- Buyer orders: `FM-####` references, crop variety, `delivery_by` date with a minimum lead time, spec notes, a `delivered` status, and a server-derived stepper/progress. New `GET /buyer/order-form`, `/buyer/fee-quote`, `/buyer/payments/{id}`, `/ops/payments`, `/admin/commitment-fee-rules`.

### Changed
- `POST /buyer/requirements/{id}/pay` returns `pending` instead of `success`; card no longer returns 501. The `/buyer-flow` page waits for the webhook (sandbox phone approval).
- **Buyer Portal** at `/buyer`, built to the CEO demo: a requirement form generated from `/buyer/order-form` (active crops/varieties, earliest delivery date, reference price, live fee quote), the choose → pending → confirmed payment modal (with a sandbox phone simulator and a retry on failure), and an orders table with expandable stepper rows and a Pay action for unpaid orders. Copy matches the demo.
- Logistics foundation (brief §7): `vehicles` (pilot fleet Tricycle #1–#4 + Vehicle #07 at Tema), an append-only `logistics_events` history emitted at every dispatch/delivery/intake/trunking/order step, intakes recorded per centre and crop, and the first graded lot moving an order to **Aggregating**. New `GET /api/public/activity` (anonymised ticker feed), `/ops/vehicles`, `/ops/aggregation`, `POST /ops/requirements/{id}/advance`. Buyer Delivery Tracking now includes the order's logistics events.
- `app/state.py`: one transition table for buyer orders, dispatch/trunking jobs, opportunities and input orders. Illegal moves are a 409 everywhere.
- `migrations/fix_autogen.py`: names autogenerate's unnamed foreign keys and drops leftover ENUM types so revisions round-trip.
- **Public landing page** at `/` (brief §3): the demo's hero, CTAs and "How it works" panel; a stats ledger from `/api/public/stats`; role-coloured portal cards; and a live ticker from `/api/public/activity` that rotates every 5s and refreshes every minute. The ledger becomes 2×2 and the cards stack on mobile.
- Farmer backend (brief §4): Phase 1 matching (region + registered crop; another farmer's assignment is never shown), `GET /farmer/matched-opportunities` with crop, region, "delivery in N weeks", stepper stage and formula steps. Accepting creates a **48-hour agronomist task** and an in-app + SMS notification and posts to the wallet. New `wallet_ledger` (estimated settlement, input orders + reversals, logistics fees) behind `GET /farmer/wallet/summary` (decision D4). Agronomist-authored `formula_steps` (draft from per-variety templates + the buyer's spec notes), `/ops/agronomist-tasks` queue, `GET /farmer/notifications`.

### Changed
- `GET /farmer/opportunities` and `/farmer/opportunities/{id}` are filtered to the farmer's own matches. Previously they returned every open row, including opportunities assigned to other farmers.
- **Farmer Portal** at `/farmer`, built to the CEO demo: the matched-opportunity list (crop icon, tonnes, buyer, region, delivery in N weeks, Open/Accepted), a detail panel with the four-step stepper and formula checklist, the Accept button behind a one-step commitments confirmation (decision D5) with the demo's toast, and the wallet card from the ledger. Pre-existing opportunities are backfilled to Maize / Greater Accra.
- Marketplace backend on **listings** (decision D1, brief §6.1): listings gain `kind` (input / equipment / service), `pricing_basis`, `formula_input_type`, `service_code` and `icon`. The CEO demo's nine-item catalogue is seeded across the third-party vendor and a new Farm Master-owned vendor, "Farm Master Services" (`services@farmmaster.test`). `GET /farmer/marketplace` and `POST /farmer/marketplace/orders`: the cart is split per vendor under one checkout ref; equipment and services need a requested date; stock is reserved (listing goes out of stock at 0) and restored on decline; the cost is debited to the wallet ledger; an agronomist-visit line creates a farm-visit task; the vendor gets an in-app notification. Vendor confirmation still creates the logistics job.
- **Marketplace page** at `/marketplace` (the demo's "Vendor Portal" tab, for farmers): category pill tabs from the API, product cards with the vendor name, SVG icon or photo and stock, "Add to order" with the demo's toast, and a sticky cart grouped by vendor with a qty stepper, remove, a needed-on date for equipment and services, and a total. Place order shows the demo's toast with the configured SLA.
- Products retired into listings (decision D1, part 2): each product is copied into an active listing (recorded on `products.listing_id`, stock moved). Order Inputs' formula pre-fill is now `GET /farmer/marketplace/formula-prefill`, plus an "Add to order" banner on `/marketplace`. Marketplace orders accept `production_formula_id`, so reconciliation links are kept. `/order-inputs-flow` redirects to the marketplace; the vendor catalogue screen and dashboard counts show listings.

### Removed
- `frontend/farmer_order_inputs_flow_live.html`. `GET /farmer/catalogue`, `POST /farmer/input-orders` and `POST /vendor/catalogue` now return **410 Gone** with a pointer to the replacement. `GET /vendor/catalogue` stays read-only for history.
- E2E suite for the portal pages (`tests/e2e/test_ceo_demo_portals_e2e.py`): every demo interaction from brief §9 against a live server, plus overflow and 44px touch-target checks at 375/768/1280px.

### Fixed
- Touch targets: the demo's compact buttons, tabs, steppers, links and form fields now all meet PRD §5.1's 44px minimum without changing their look.
- A fresh database crashed at startup on Windows consoles (cp1252), because a seed log line printed "₵". Startup output is now ASCII.
- After signing in on `/marketplace`, the Place order button lost its handler. It's now bound after sign-in.
- `GET /ops/requirements?status=` (Logistics, Super Admin, Operations Coordinator): buyer orders in the given stages, by default the ones logistics can advance. Agronomist requirement rows now include the FM reference, crop and spec notes. `FM.portal()` accepts several roles, ready for the Ops page.
- `scripts/build_static_demo.py`: a static, backend-free preview of the four portal pages built from a snapshot of the running app, with an in-browser mock for submit/pay, accept and place order. It's published as a private shareable link, and the gap report gained an implementation-status section.
