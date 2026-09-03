// Farm Master — Rates & Formulas: Canonical Reference
//
// This file is the single documented source of truth for the provisional
// numbers used across the three Stage 5 flows. It is NOT loaded by the flow
// HTML files directly — each flow (buyer_commitment_fee_flow.html,
// farmer_opportunity_formula_flow.html, vendor_mechanisation_request_flow.html)
// is a standalone file that gets opened, shared, or downloaded on its own, so
// each one inlines its own small "CONFIG" object near the top of its <script>
// block with these exact values, rather than depending on this file being
// present in the same folder at open time.
//
// When a rate changes: update the value here AND in the matching CONFIG block
// in each affected flow file. Search each flow for "CONFIG:" to find it.
//
// STATUS: PROVISIONAL — every value below is a placeholder pending Emmanuel's
// final business sign-off (see PRD, "Provisional Rates & Formulas").

var FARM_MASTER_RATES_REFERENCE = {
  status: "PROVISIONAL — pending Emmanuel's final business sign-off",

  // Flow 1 — Buyer Commitment-Fee Payment
  buyerCommitmentFeePerTonne: 90, // GHS / tonne

  // Flow 3 — Vendor Mechanisation Request
  // Specified by Emmanuel as GHS 60/tonne. Mechanisation requests are currently
  // captured by area (acres), not tonnage — there is no yield/tonnage field on
  // a request yet. Applied per-acre in the flow as a placeholder wiring pattern
  // (fee = area * rate); this unit mismatch is flagged for Stage 6 data-model
  // review, not silently treated as correct.
  vendorServiceFeePerTonne: 60, // GHS / tonne (see note above — applied per-acre for now)

  // Flow 2 — Farmer Production Formula input scaling
  // AGRONOMICALLY UNVERIFIED. These are illustrative multipliers invented to
  // produce plausible-looking numbers, not a reviewed agronomic formula.
  // Needs sign-off from an agronomist before any real farmer sees these
  // quantities.
  formulaInputScaling: {
    seedKgPerTonne: 1.6,
    npkTonnesPerBag: 2,      // 1 bag per this many tonnes, rounded up
    topDressTonnesPerBag: 4  // 1 bag per this many tonnes, rounded up
  }
};
