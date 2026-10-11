# Farm Master Design System

This is the visual language of the CEO-approved platform demo ([`reference/Farm_Master_Platform_Demo.html`](reference/Farm_Master_Platform_Demo.html)), adopted app-wide in October 2026. It supersedes the colour and typography sections of `Farm_Master_Style_Guide_Stage4.docx` (Deep Green & Maize Gold / Manrope). Section 10 of that document records the change.

**Files** (served at `/static/assets/…`):

| File | What it holds |
|---|---|
| [`Stage 6 Build/frontend/assets/tokens.css`](../Stage%206%20Build/frontend/assets/tokens.css) | Colour, radius, shadow, font and layout tokens; the Google Fonts import; derived dark-mode values |
| [`Stage 6 Build/frontend/assets/components.css`](../Stage%206%20Build/frontend/assets/components.css) | Every shared component's styles, plus the responsive and reduced-motion rules |
| [`Stage 6 Build/frontend/assets/components.js`](../Stage%206%20Build/frontend/assets/components.js) | `window.FM`: toast, modal, stepper, checklist, ticker, icons, session/API helpers, sign-in card, top bar |

There's a live gallery of every token and component at **`/design-system`**.

Every page loads the three files in this order:

```html
<link rel="stylesheet" href="/static/assets/tokens.css">
<link rel="stylesheet" href="/static/assets/components.css">
<script src="/static/assets/components.js"></script>
```

---

## 1. Tokens

### Colour

The light values are the demo's exactly. Never hard-code a hex value in a page: always use the token.

| Token | Light | Use |
|---|---|---|
| `--forest-deep` | `#173821` | Primary brand, headings, primary buttons, Farmer role |
| `--forest` | `#1E4620` | Primary hover |
| `--forest-soft` | `#2F5C34` | Focus outlines |
| `--gold` | `#C7912E` | Accent, Buyer role, "current" step |
| `--gold-hover` | `#B47F22` | Gold button hover |
| `--gold-soft` | `#E4C583` | Status pill, text selection |
| `--clay` | `#A65B31` | Vendor role, active category tabs |
| `--cream` | `#F6F1E3` | Page background, input background, hover rows |
| `--paper` | `#FFFEFA` | Cards, panels, modals |
| `--ink` / `--ink-soft` | `#22261D` / `#5B5F51` | Body / secondary text |
| `--line` / `--line-soft` | `#DEDBC6` / `#EAE7D8` | Borders / dividers |
| `--good` / `--good-bg` | `#2F6B3A` / `#E7F0E3` | Success, "Accepted", "Delivered" |
| `--warn` / `--warn-bg` | `#9A6A18` / `#F7ECD6` | "Open" |
| `--info` / `--info-bg` | `#3D5F8A` / `#E4EBF4` | In progress: "Aggregating", "Matching farmers" |
| `--wait` / `--wait-bg` | `#6B6656` / `#EEEAD9` | Pending / waiting |
| `--danger` / `--danger-bg` | `#A33A2B` / `#F5E1DC` | Errors, failed payments (an addition: the demo has no error state) |
| `--on-fill` | `#FFFFFF` | Text on a filled forest / gold / clay surface |

**Dark mode** (decision D7) is applied automatically from `prefers-color-scheme: dark`, or forced with `<html data-theme="dark">` / `data-theme="light"`. The dark values are derived, not part of the demo.

### Role colours

| Role | Token | Applied to |
|---|---|---|
| Farmer | `--role-farmer` → forest-deep | `.role-chip.farmer`, Farmer portal card top border |
| Buyer | `--role-buyer` → gold | `.role-chip.buyer`, Buyer portal card top border |
| Vendor / Marketplace | `--role-vendor` → clay | `.role-chip.vendor`, Vendor card top border, `.cat-tab.active` |

### Typography

- **Headings:** Fraunces 600 (`--font-display`), letter-spacing −0.01em, fallback Georgia.
- **Body and UI:** Archivo 400–800 (`--font-body`), fallback Segoe UI / system-ui.
- **Scale used:** hero 44px · portal title 26px · section 24px · card title 16px · body 14–14.5px · hint 13px · meta 12.5px · badge 11px.

### Shape and elevation

| Token | Value |
|---|---|
| `--radius-card` | 14px |
| `--radius-chip` | 999px |
| `--radius-btn` / `--radius-btn-sm` | 9px / 7px |
| `--shadow-1` | `0 1px 2px rgba(23,56,33,.08), 0 1px 1px rgba(23,56,33,.04)` (resting panels) |
| `--shadow-2` | `0 8px 24px rgba(23,56,33,.14)` (hover cards, toast, modal) |
| `--page-max` / `--gutter` | 1180px / 28px (16px at ≤860px) |

---

## 2. Components

| Component | Markup / API | Notes |
|---|---|---|
| Top bar | `<header id="topbar">` + `FM.topbar(el, {active: "farmer"})` | Leaf mark, wordmark, tagline, segmented portal switcher (real links: `/`, `/farmer`, `/buyer`, `/marketplace`), and a status pill that becomes "Name · Sign out" when signed in. The switcher becomes a full-width scrollable row at ≤860px. |
| Buttons | `.btn` + `.btn-primary` / `.btn-ghost` / `.btn-gold`, modifiers `.btn-sm`, `.btn-block`; `disabled` | Minimum 44px tap target (36px small). Gold is reserved for the money-committing action on a screen (e.g. Place order). |
| Portal header | `.portal-head` > `h2` + `.sub`, plus `.role-chip.{farmer|buyer|vendor}` | "Signed in as …" line goes in `.sub`. |
| Card | `.card` > `h3` + `.hint` | `.card-link` for "View full statement →" style links. |
| Badges | `.badge.open` · `.accepted` / `.delivered` · `.progress` · `.waiting` · `.danger` | Map statuses through one function per page, never ad hoc. |
| Stepper | `FM.stepper(labels, currentIndex)` | done = forest, current = gold, pending = line. Exposes `role="list"` with per-step state labels. |
| Progress bar | `.progress-track > .progress-fill[style=width:N%]` | Width comes from the server-derived `progress_pct`. |
| Checklist | `FM.checklist(items)` | Production-formula steps. |
| Key/value rows | `.kv-row` (last one `.kv-row.total`) | Wallet and settlement lines. |
| Form field | `.field` > `label` + control + `.fhint` / `.ferror`; `.field.invalid` | `.field-row` gives two columns and stacks at ≤860px. |
| Data table | `.table-wrap > table.data`; `tr.expandable` + `tr.detail-row(.open)` | Expandable rows are focusable and toggle on Enter/Space too. |
| Select rows | `button.select-row(.selected)` > `.icon-tile` + `.body` | Opportunity list. |
| Category tabs | `.cat-tabs > button.cat-tab(.active)` | Clay active state. |
| Product card | `.product-grid > .product-card` (`.product-icon`, `h4`, `.vendor`, `.price .unit`, button) | 3 columns ≥1025px, 2 at tablet, 1 at ≤480px. |
| Cart panel | `.card.cart-panel` > `.cart-line` (`.name`, `.ctl` with `.qty-btn` / `.rm`), `.cart-total` | Sticky on desktop, static at ≤860px. |
| Toast | `FM.toast(msg, {error})` | Bottom-centre, 2.8s, `role=status`. |
| Modal | `FM.modal.open((box, api) => …)`; `api.render(next)`, `api.close()`, `api.lock(true)` | Multi-step choose → confirm → (pending) → success. Esc closes unless locked (e.g. while a payment is pending). |
| Ticker | `.ticker > svg + .txt` + `FM.ticker(el, fetchFn)` | Rotates every 5s and refetches every 60s. Shows public-safe text only. |
| Sign-in card | `FM.signIn(el, {portalName, role, demoEmail, onDone})` | Email + password → email OTP. Shares the `farmmaster_session` key and 10-minute inactivity logout with every existing flow page. |
| Icons | `FM.icon(name, size)` | Stroke SVG set that replaces the demo's emoji: `leaf, check, maize, rice, soybean, tomato, seed, fertiliser, bottle, tractor, planter, pump, plough, harvester, clipboard, truck, box`. Uploaded listing images take precedence on product cards. |

## 3. Usage rules

1. **Tokens only.** No hex values or font names in page CSS.
2. **Role colour is identity, not decoration.** Only use forest, gold or clay for the role they belong to, the primary action (forest) and the money action (gold).
3. **Copy comes from the server.** Crops, regions, fees, prices, counts and SLA days are never typed into a page; they come from the API.
4. **Responsive is part of done.** Every page must pass `python "Stage 6 Build/scripts/responsive_check.py"` (no horizontal scroll at 390 / 820 / 1400px). Give flex/grid children `min-width: 0`, and match the selector specificity of the rule you're overriding inside `@media`.
5. **Motion respects `prefers-reduced-motion`.** All animation and transition is disabled under it, and the ticker swaps text without fading.
6. **Accessible by default.** Focus rings use `--forest-soft`. Interactive rows are buttons or have `tabindex` plus key handlers. Toasts are live regions.
