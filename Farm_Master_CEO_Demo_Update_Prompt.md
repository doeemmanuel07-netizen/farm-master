# Claude Code Prompt — Farm Master: Align the Web App with the CEO's Platform Demo

> Paste everything below this line into Claude Code, run from the root of the `farm-master` repo (GitHub: `doeemmanuel07-netizen/farm-master`).
> Items marked **[DEFAULT — confirm]** are decisions I've pre-filled with a recommendation; change them before pasting if the CEO wants otherwise.

---

## 0. Context

You are updating the **Farm Master Ghana Limited** web app: an agribusiness aggregation platform (HQ Tema, Greater Accra) connecting **Farmers**, **Buyers** (institutional/MoFA and private) and **Vendors** (agri-inputs, equipment, mechanisation services), coordinated through an internal Farm Master control centre, regional fulfilment centres and a logistics fleet.

**Stack (locked):** Python + FastAPI + PostgreSQL. Keep whatever frontend approach and folder structure the repo already uses. Don't introduce a new framework without flagging it first.

The CEO has approved a clickable HTML demo called **"Farm Master Platform Demo"** (I'll place it at `docs/reference/Farm_Master_Platform_Demo.html`; copy it there if it isn't present). **That demo is now the target for the look, feel and core user flows.** Your job is to bring the real app in line with it while keeping the business rules already locked in the PRD (Stage 1), the Information Architecture (Stage 2) and the Stage 3 wireframes.

### Working rules (apply to every step)
1. **Audit first.** Before changing anything, read the repo (README, SDD, DB schema/migrations, models, routes, templates/static assets) and the reference demo. Write a short gap report to `docs/ceo-demo-gap-report.md` listing the following for each demo feature: *exists / partial / missing / conflicts with PRD*. Commit it.
2. **Commit and push each change** as its own logical commit with a clear message (e.g. `feat(buyer): commitment-fee payment modal`). Push to GitHub after every commit. Don't batch unrelated changes.
3. **Keep every project document in sync** with each change: SDD, README, database schema doc + ERD, API docs/OpenAPI notes, and the CHANGELOG. GitHub and the local disk copy must match at all times.
4. **Responsive from the start:** every screen must work at desktop (≥1180px), tablet (~768–1024px) and mobile (~360–430px) with no horizontal scroll. Verify `document.documentElement.scrollWidth === viewport width` at 390px, 820px and 1400px for every screen, using headless Chromium/Playwright. Remember `min-width: 0` on flex/grid children, and match selector specificity in `@media` overrides.
5. **Make everything configurable, not hard-coded.** Crops, regions, fulfilment centres, fees, rates and payment providers come from the database or settings, never from string literals in templates.
6. When something in the demo conflicts with the locked PRD and isn't resolved in Section 2 below, **stop and list it for me** rather than guessing.

---

## 1. Design system: adopt the demo's visual language (this is Stage 4)

Extract the demo's styling into a shared design-token file (e.g. `static/css/tokens.css`) plus a component stylesheet, and apply it app-wide (public site + all three portals + internal ops).

**Colour tokens (use exactly):**

| Token | Hex | Use |
|---|---|---|
| `--forest-deep` | `#173821` | Primary brand, headings, primary buttons, Farmer role |
| `--forest` | `#1E4620` | Primary hover |
| `--forest-soft` | `#2F5C34` | Focus outlines |
| `--gold` | `#C7912E` | Accent, Buyer role, "current" step |
| `--gold-soft` | `#E4C583` | Pills, text selection |
| `--clay` | `#A65B31` | Vendor role, active category tabs |
| `--cream` | `#F6F1E3` | Page background, input background |
| `--paper` | `#FFFEFA` | Cards, panels |
| `--ink` / `--ink-soft` | `#22261D` / `#5B5F51` | Body / secondary text |
| `--line` / `--line-soft` | `#DEDBC6` / `#EAE7D8` | Borders, dividers |
| `--good` / `--good-bg` | `#2F6B3A` / `#E7F0E3` | Success, "Accepted", "Delivered" |
| `--warn` / `--warn-bg` | `#9A6A18` / `#F7ECD6` | "Open" |
| In-progress badge | `#3D5F8A` on `#E4EBF4` | "Aggregating", "Matching farmers" |

**Typography:** headings in **Fraunces** (600, slight negative letter-spacing), body/UI in **Archivo** (400–800), loaded from Google Fonts with Georgia / Segoe UI fallbacks.

**Shape and elevation:** card radius 14px, chip radius 999px, button radius 9px (7px small), soft forest-tinted shadows (`--shadow-1`, `--shadow-2`).

**Role colour-coding (use everywhere):** Farmer = forest, Buyer = gold, Vendor = clay. It applies to the role chip in each portal header, the top border of the portal cards, and active states.

**Reusable components to build** (as template partials or components, used everywhere):
- Top bar: leaf logo mark, "Farm Master" wordmark, tagline, segmented portal switcher, status pill
- Buttons: primary / ghost / gold / small / disabled
- Card with title + hint line
- Badges: Open / Accepted / In progress / Delivered
- **Horizontal progress stepper** (done = forest, current = gold, pending = line)
- Progress bar
- Form field with label, hint and focus ring; two-column field row that stacks on mobile
- Data table with expandable detail row
- Category pill tabs
- Product card
- Sticky cart/summary panel
- **Toast notifications** (bottom-centre, ~2.8s)
- **Modal** with multi-step content (choose → confirm → success)
- Fade-rotating **"Live" activity ticker**
- `prefers-reduced-motion` support: all animation off
- Replace the demo's emoji product/crop icons with a consistent SVG icon set, or uploaded product images, in production.

Write the whole system up as `docs/design-system.md` (tokens, components, usage rules), link it from the README, and commit.

---

## 2. Scope decisions where the demo differs from the locked PRD

The demo shows a broader, national picture than the locked pilot. Handle each difference like this:

| # | Demo shows | Locked PRD says | Build instruction |
|---|---|---|---|
| A | Multiple crops (Maize, White Rice, Soybean, Tomato) with varieties | Pilot = maize only | **[DEFAULT — confirm]** Build a full `crops` + `crop_varieties` model and multi-crop UI, seed all four demo crops, and add an admin "active for ordering" flag. At launch only Maize (Obatanpa) is active. Others are switched on from the admin panel, with no code change. |
| B | Farmer in Eastern Region (Nsawam), centres in Kumasi, Tamale, Koforidua; "16 regional fulfilment centres" | Pilot region = Tema, Greater Accra | **[DEFAULT — confirm]** Build `regions` + `fulfilment_centres` tables supporting all 16 regions, with an `is_active` flag. Pilot activates Greater Accra / Tema. Landing-page stats are computed from the DB, not hard-coded. |
| C | Farmer shown as a member of "Nsawam Farmer Union" | Union management deferred to Phase 2 | Add an optional `farmer_union` affiliation (name only, shown in the portal header). **No** union management screens in Phase 1. |
| D | Commitment fee paid by MTN / Vodafone / AirtelTigo MoMo, fixed GH₵ 1,800 | Gateway shortlist Paystack / Hubtel (undecided); MoMo + card options | **[DEFAULT — confirm]** Put all payments behind a `PaymentProvider` interface with a **sandbox/mock driver first**, then add Paystack and Hubtel drivers. In the UI, label networks by current brand names: **MTN MoMo, Telecel Cash (formerly Vodafone Cash), AT Money (formerly AirtelTigo Money)**, plus Card. The fee is a **configurable rule** (e.g. % of order value with a minimum), not a fixed GH₵ 1,800. Seed a default rule and expose it in admin settings. |
| E | "Vendor Portal" is a **marketplace with a cart** (Seeds & Inputs, Equipment Rental day-rates, Mechanisation Services per acre/visit) | Vendor Portal = vendor's own management screens; equipment rental booking calendar deferred; mechanisation = simple request form | **[DEFAULT — confirm]** Keep both sides. (1) **Marketplace / Order Inputs** is the *farmer-facing* shopping experience, built exactly like the demo, reached from the Farmer Portal (and the top-level "Vendor Portal" tab for demos). (2) The **vendor's own back-office** (catalogue management, incoming orders, mechanisation request queue, payouts, subscription) stays as wireframed in Stage 3. Equipment rental and services are bought as **cart line items with a requested date and quantity of days/acres**, with no availability calendar in Phase 1. |
| F | "Agronomist farm visit" sold as a service item | Agronomist messaging in Phase 1 | Add it as a bookable service product **and** keep Agronomist Messaging. A purchased visit creates a task in the internal ops portal. |

---

## 3. Public landing / Overview page (rebuild to match demo)

- **Hero:** headline *"One farm-gate to market platform for Ghana's growers, buyers, and input vendors."*, the lede paragraph from the demo, and two CTAs (*Open Farmer Portal* → login/register as Farmer; *Open Buyer Portal* → login/register as Buyer).
- **"How it works" panel**, 4 numbered steps: Buyer submits demand → Farm Master matches & guides → Vendors supply inputs → Logistics moves the harvest.
- **Stats ledger** (4 tiles, values from the DB): coordinated portals (3), regional fulfilment centres (count of centres), revenue streams (6, from config), head office (Tema).
- **Three portal cards** (Farmer / Buyer / Vendor), role-coloured top borders, each linking to that portal's register/login.
- **Live activity ticker:** rotates every 5s through the latest real events from a `logistics_events` / activity feed (vehicle en route, tonnes aggregated at a centre, trunking to Tema, harvest pickups completed). Show public-safe, anonymised text only (no farmer names or phone numbers). Use a lightweight polling endpoint (`GET /api/public/activity?limit=10`) or SSE.
- Fully responsive. Portal cards stack on mobile, and the ledger becomes 2×2.

---

## 4. Farmer Portal

Header: *"Signed in as {name} · {union, if any} · {region}"* + forest "Farmer view" chip.

**4.1 Matched opportunities (left column)**
- List of opportunities published by Farm Master for this farmer, filtered by the farmer's **region and farm history** (crops grown, past performance). Phase 1 rule: same active region + crop the farmer has registered to grow.
- Each row: crop icon, `{Crop} — {qty} tonnes`, buyer name, region, "Delivery in N weeks" (computed from the requirement's delivery date), and an **Open / Accepted** badge.
- Clicking a row selects it (left border highlight) and loads the detail panel.

**4.2 Opportunity detail / production formula (right column)**
- Title `{Crop} — production formula`, sub-line *"Issued by Farm Master agronomy for {buyer}"*.
- **Stepper:** Matched → Accepted → In production → Harvest & delivery, driven by the opportunity's real status.
- Checklist of **production-formula steps** (variety and spacing, fertiliser schedule, crop protection, harvest/moisture/grading/bagging), authored by an agronomist in the ops portal and derived from the buyer's grading notes.
- **Accept opportunity** button. It's disabled with the label "Opportunity accepted" once accepted. On accept:
  - set the farmer's allocation to `accepted`,
  - create an agronomist follow-up task (SLA **48 hours**) in the ops portal,
  - send the farmer an SMS/in-app notification,
  - toast: *"{Crop} opportunity accepted — agronomist will contact you within 48 hours."*
  - recalculate the wallet.

**4.3 Wallet & settlement** (card under the grid)
- Rows: **Input costs** (sum of this farmer's marketplace orders, shown as a deduction), **Logistics fees** (deduction), **Estimated payout this season** (bold total).
- Payout = Σ(accepted allocation tonnes × agreed price per tonne) − input costs − logistics fees. **Don't** reuse the demo's flat GH₵ 2,150-per-opportunity placeholder. Store every movement in a `wallet_ledger` table (credit/debit, source, reference) so the statement is auditable.
- Link through to the full Wallet & Settlement Statement screen from Stage 3.

The other Stage 3 farmer screens (Registration & KYC, Milestone Log, Agronomist Messaging, Harvest Pickup Request) stay in scope and get restyled to the new design system.

---

## 5. Buyer Portal

Header: *"Signed in as {organisation} · {Institutional | Private} buyer"* + gold "Buyer view" chip. Example institutional buyer: Ministry of Food & Agriculture.

**5.1 Submit a crop requirement** (left card)
- Fields: **Crop & variety** (active crops/varieties only), **Quantity (tonnes)** (min 1), **Delivery by** (date, must be in the future and respect a configurable minimum lead time), **Grading / specification notes** (textarea, hint: *"This becomes the production formula your matched farmers follow."*).
- Button **"Submit request & pay commitment fee"** opens the **payment modal**:
  1. *Pay commitment fee:* show the computed fee and the explanation *"activates Farm Master's aggregation effort for this order"*, a provider selector (MTN MoMo / Telecel Cash / AT Money / Card) and Cancel / Confirm.
  2. On confirm, call the payment provider (sandbox first), then handle pending → webhook confirmation. Never mark an order paid on the client side.
  3. *Payment confirmed* screen: tick icon and *"Paid via {provider}. Farm Master will begin matching farmers to this order."* + Done.
- After payment: create the order (`FM-####` sequential reference), set status **Matching farmers**, insert it at the top of the orders table with its detail row expanded, and toast *"Request submitted — Farm Master is matching farmers in your target region."*
- The requirement appears in the internal ops portal for agronomy (to author the production formula) and matching (to publish opportunities to farmers).

**5.2 Your orders** (right card)
- Table: Order ID, Crop, Qty, Status badge, progress bar.
- Clicking a row expands/collapses a detail row with the **stepper: Order placed → Farmer matched → In production → Aggregating → Delivered**.
- Progress % and status are derived from the order's state, not stored as free text.

Keep the other Stage 3 buyer screens (Registration & Verification with Institutional/MoFA vs Private tracks, Compliance Documents incl. MoFA export, Delivery Tracking, Final Invoice), restyled.

---

## 6. Vendor Marketplace (farmer-facing) + Vendor back-office

**6.1 Marketplace (as in demo)**
- Header: *"Marketplace for inputs, equipment and mechanisation services"* + clay "Marketplace view" chip.
- **Category pill tabs:** Seeds & Inputs · Equipment Rental · Mechanisation Services.
- **Product grid** (3 cols desktop / 2 tablet / 1–2 mobile): image/icon, name, price + unit, and an **Add to order** button with the toast *"{item} added to your order."*
- Seed catalogue (from demo; prices in GH₵, all editable by vendors/admin):
  - Inputs: Improved Maize Seed (Obatanpa) 180/10kg bag · NPK 15-15-15 265/50kg bag · Fungicide 95/litre
  - Equipment: Tractor with plough 650/day · Motorised planter 280/day · Water pump set 150/day
  - Services: Land preparation & ploughing 320/acre · Mechanised harvesting crew 410/acre · Agronomist farm visit 120/visit
- Each product belongs to a **vendor** (Farm Master-owned or third-party). Show the vendor name on the card.
- **Sticky "Your order" cart:** lines `{qty} × {name}` with a line total and a remove (×) button, a running **Total**, and a gold **Place order** button disabled while empty. Add a qty stepper (the demo only increments on re-add), and capture the requested date for equipment/services.
- **Place order:** create the order and its lines, split per vendor, debit the farmer's wallet (or take payment), create a **logistics job** for farm-gate delivery, then clear the cart and toast *"Order routed to Farm Master logistics — estimated farm-gate delivery in {N} days."* N comes from a configurable SLA (default 2).

**6.2 Vendor back-office:** keep the Stage 3 Vendor Portal screens (Registration & Storefront Setup with Owned/Third-Party tabs, Dashboard, Product Catalogue CRUD feeding 6.1, Mechanisation Service Requests queue, Incoming Orders / Fulfilment Queue, Order → Logistics Handoff stepper, Subscription & Billing, Payout Statement), restyled.

---

## 7. Logistics & internal ops (needed to make the demo real)

- **Fleet:** `vehicles` table (type: tricycle / truck, code like "Tricycle #14", "Vehicle #07", home centre, status). Pilot seed: 3–5 tricycles at Tema.
- **Logistics jobs:** input delivery (vendor → farm gate), harvest pickup (farm → fulfilment centre), trunking (centre → Tema HQ). Each job emits `logistics_events`, which feed the buyer's Delivery Tracking, the vendor's handoff stepper, and the public ticker.
- **Fulfilment-centre aggregation:** record tonnes received per crop per centre per day, which drives the "Aggregating" order state and the ticker line *"Fulfilment centre — {name} has aggregated {n} tonnes of {crop} today."*
- **Ops portal additions:** commitment-fee payments list, production-formula editor per requirement, opportunity publishing/matching, agronomist task queue (48h SLA), marketplace order dispatch, fee/SLA/crop/region settings.

---

## 8. Data model (minimum additions/changes — reconcile with the existing schema)

`regions`, `fulfilment_centres`, `crops`, `crop_varieties`, `farmer_unions` (name only), `farmers` (+ region, union_id nullable), `buyers` (type: institutional/private, MoFA-verified flag), `crop_requirements` (buyer order: variety, tonnes, delivery_by, spec_notes, status, reference `FM-####`), `commitment_fee_rules`, `payments` (provider, network, amount, status, provider_ref, webhook payloads), `production_formulas` + `formula_steps`, `opportunities` / `farmer_allocations` (tonnes, price/tonne, status), `vendors` (owned/third-party), `catalogue_items` (category: input/equipment/service, unit, price, vendor_id, active), `marketplace_orders` + `marketplace_order_lines`, `wallet_ledger`, `vehicles`, `logistics_jobs`, `logistics_events`, `agronomist_tasks`, `notifications`.

Use proper status enums and state-transition functions for orders, allocations and jobs (no free-text statuses). Write Alembic (or the repo's existing tool) migrations and a seed script reproducing the demo data for staging. Update the schema doc + ERD.

---

## 9. Acceptance checklist (verify all before finishing)

- [ ] Every demo interaction works end-to-end against the real backend: portal switching, landing CTAs, opportunity select/accept, wallet recalculation, buyer submit → payment modal → success → new order row, order row expand/collapse, category tabs, add/remove cart items, place order.
- [ ] Toast messages and copy match the demo wording.
- [ ] Design tokens, fonts, role colours and components match the demo.
- [ ] No hard-coded crops, regions, fees, prices or counts.
- [ ] Pilot config active: Maize + Tema only, everything else switchable in admin (per Section 2 decisions).
- [ ] Responsive check passes at 390 / 820 / 1400px for every screen; reduced-motion respected.
- [ ] Automated tests for: fee calculation, payment webhook handling, opportunity acceptance, wallet ledger maths, marketplace order splitting, state transitions.
- [ ] Gap report, SDD, README, schema/ERD, design-system doc, API docs and CHANGELOG updated. Every change committed and pushed. GitHub matches local.
- [ ] Finish with a summary of what was built, what's still mocked (e.g. sandbox payments), and any open questions.
