/*
 * Static-preview API mock (scripts/build_static_demo.py). Answers the
 * portal pages' fetch() calls from a snapshot of the real app
 * (window.FM_FIXTURES) and simulates the demo actions in memory. Nothing
 * persists past a page load and no payment provider is called.
 */
(function () {
  "use strict";
  var F = window.FM_FIXTURES;
  var role = (document.currentScript && document.currentScript.getAttribute("data-role")) || "";
  var page = (document.currentScript && document.currentScript.getAttribute("data-page")) || "";
  var who = role === "buyer" ? F.buyer.me : (page === "marketplace" ? F.market.me : F.farmer.me);

  // Signed in as the page's demo account from the start.
  if (role) {
    try {
      localStorage.setItem("farmmaster_session", JSON.stringify({ token: "demo", role: who.role, fullName: who.full_name, lastActivityAt: Date.now() }));
    } catch (e) {}
  }

  var clone = function (x) { return JSON.parse(JSON.stringify(x)); };
  var orders = clone(F.buyer.requirements);
  var payments = {};
  var opps = clone(F.farmer.opps);
  var wallet = clone(F.farmer.wallet);
  var catalogue = clone(F.market.catalogue);
  var margin = 0.15;
  var seq = 0;
  orders.forEach(function (o) { var n = parseInt(String(o.reference || "").replace("FM-", ""), 10); if (n > seq) seq = n; });

  function json(status, body) {
    return Promise.resolve(new Response(JSON.stringify(body), { status: status, headers: { "Content-Type": "application/json" } }));
  }
  function err(status, detail) { return json(status, { detail: detail }); }

  function quote(qty, price) {
    var r = F.fee_rule;
    var raw = r.basis === "per_tonne" ? qty * r.rate : qty * price * r.rate;
    var amt = Math.round(Math.max(r.minimum_amount, raw) * 100) / 100;
    var how = r.basis === "per_tonne" ? "GH₵ " + r.rate.toFixed(2) + " per tonne × " + qty + " t" : (r.rate * 100) + "% of order value";
    if (amt > raw) how += ", raised to the GH₵ " + r.minimum_amount.toFixed(2) + " minimum";
    return { amount: amt, explanation: how, rule_name: r.name, basis: r.basis, rate: r.rate, minimum_amount: r.minimum_amount };
  }
  function stage(o, idx, label, pct, badge) { o.stage_index = idx; o.status_label = label; o.progress_pct = pct; o.badge = badge; }

  function route(method, path, body) {
    var u = new URL(path, location.href), p = u.pathname.replace(/^.*?(\/(api|auth|buyer|farmer|payments)\/)/, "$1");
    if (method === "GET" && p === "/api/public/stats") return json(200, F.stats);
    if (method === "GET" && p === "/api/public/activity") return json(200, F.activity);
    if (p === "/auth/login") return json(200, { challenge_id: "demo", dev_only_email_code: "123456", purpose: "login" });
    if (p === "/auth/login/verify-otp") return json(200, { access_token: "demo", role: who.role, full_name: who.full_name });
    if (p === "/auth/me") return json(200, who);

    // Buyer
    if (method === "GET" && p === "/buyer/order-form") return json(200, F.buyer.order_form);
    if (method === "GET" && p === "/buyer/fee-quote") return json(200, quote(+u.searchParams.get("quantity_tonnes"), +u.searchParams.get("price_per_tonne")));
    if (method === "GET" && p === "/buyer/requirements") return json(200, orders);
    if (method === "POST" && p === "/buyer/requirements") {
      var crop, variety;
      F.buyer.order_form.crops.forEach(function (c) { c.varieties.forEach(function (v) { if (v.id === body.crop_variety_id) { crop = c; variety = v; } }); });
      if (!crop) return err(422, "That crop variety isn't available.");
      if (!(body.quantity_tonnes > 0)) return err(422, "Quantity must be greater than zero.");
      if (body.delivery_by < F.buyer.order_form.earliest_delivery_by) return err(422, "Delivery date is earlier than the minimum lead time.");
      seq += 1;
      var o = {
        id: "demo-" + seq, reference: "FM-" + seq, crop: crop.name, crop_icon: crop.icon, variety: variety.name,
        crop_variety_id: variety.id, grade: "As per specification", quantity_tonnes: body.quantity_tonnes,
        price_per_tonne: body.price_per_tonne, delivery_location: "Tema", delivery_by: body.delivery_by,
        delivery_timeline: body.delivery_by, spec_notes: body.spec_notes, status: "pending_payment",
        commitment_fee_amount: quote(body.quantity_tonnes, body.price_per_tonne).amount, paid: false,
        steps: ["Order placed", "Farmer matched", "In production", "Aggregating", "Delivered"], created_at: new Date().toISOString()
      };
      stage(o, 0, "Awaiting payment", 5, "open");
      orders.unshift(o);
      return json(200, o);
    }
    var m = p.match(/^\/buyer\/requirements\/([^/]+)\/pay$/);
    if (method === "POST" && m) {
      var ord = orders.filter(function (x) { return x.id === m[1]; })[0];
      var label = { mtn_momo: "MTN MoMo", telecel_cash: "Telecel Cash", at_money: "AT Money", card: "Card" }[body.network];
      var pay = { id: "pay-" + m[1] + "-" + Date.now(), requirement_id: m[1], amount: ord.commitment_fee_amount, method: body.network,
        network: body.network, network_label: label, status: "pending", provider: "sandbox", provider_ref: "SBX-DEMO-" + Date.now(),
        transaction_ref: null, sandbox: true,
        display_text: body.network === "card" ? "Sandbox card checkout opened. Complete it to confirm the payment."
          : "A payment prompt was sent to " + (body.payer_phone || "your phone") + ". Approve it on the phone to confirm." };
      payments[pay.id] = pay;
      return json(200, pay);
    }
    m = p.match(/^\/payments\/sandbox\/([^/]+)\/(approve|decline)$/);
    if (method === "POST" && m) {
      var pm = Object.keys(payments).map(function (k) { return payments[k]; }).filter(function (x) { return x.provider_ref === m[1]; })[0];
      pm.status = m[2] === "approve" ? "success" : "failed";
      if (pm.status === "failed") pm.failure_reason = "Declined on the payer's phone (sandbox).";
      else {
        var od = orders.filter(function (x) { return x.id === pm.requirement_id; })[0];
        od.status = "matching"; od.paid = true; stage(od, 1, "Matching farmers", 20, "progress");
      }
      return json(200, { ok: true, payment_status: pm.status });
    }
    m = p.match(/^\/buyer\/payments\/([^/]+)$/);
    if (method === "GET" && m) return json(200, payments[m[1]]);

    // Farmer
    if (method === "GET" && p === "/farmer/matched-opportunities") return json(200, opps);
    if (method === "GET" && p === "/farmer/wallet/summary") return json(200, wallet);
    m = p.match(/^\/farmer\/opportunities\/([^/]+)\/accept$/);
    if (method === "POST" && m) {
      var op = opps.filter(function (x) { return x.id === m[1]; })[0];
      if (!op || op.status !== "open") return err(409, "This opportunity has already been accepted.");
      op.status = "accepted"; op.stage_index = 2;
      var credit = op.quantity_tonnes * op.price_per_tonne * (1 - margin);
      wallet.estimated_settlement += credit; wallet.estimated_payout += credit;
      return json(200, { id: "formula-" + op.id, opportunity_id: op.id });
    }

    // Marketplace
    if (method === "GET" && p === "/farmer/marketplace") return json(200, catalogue);
    if (method === "GET" && p === "/farmer/marketplace/formula-prefill") return json(200, F.market.prefill);
    if (method === "POST" && p === "/farmer/marketplace/orders") {
      if (!body.lines || !body.lines.length) return err(422, "Your order is empty.");
      body.lines.forEach(function (l) {
        var it = catalogue.items.filter(function (i) { return i.id === l.listing_id; })[0];
        if (it && it.quantity_available !== null && it.quantity_available !== undefined) it.quantity_available -= l.quantity;
      });
      return json(200, { checkout_ref: "MKT-DEMO", orders: [], total: 0, delivery_sla_days: catalogue.delivery_sla_days,
        message: "Order routed to Farm Master logistics — estimated farm-gate delivery in " + catalogue.delivery_sla_days + " days." });
    }
    return err(404, "Not available in the static preview.");
  }

  var realFetch = window.fetch;
  window.fetch = function (input, init) {
    var url = typeof input === "string" ? input : input.url;
    if (/^(https?:)?\/\//.test(url) && url.indexOf(location.host) < 0) return realFetch.apply(this, arguments);
    var method = (init && init.method) || "GET";
    var body = init && init.body ? JSON.parse(init.body) : undefined;
    return route(method, url, body);
  };
})();
