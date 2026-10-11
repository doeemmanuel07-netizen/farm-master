/* Static-preview adjustments: portal links point at the static files, and a slim banner says what this is. */
(function () {
  "use strict";
  FM.PORTALS = [
    { id: "overview", label: "Overview", href: "index.html" },
    { id: "farmer", label: "Farmer Portal", href: "farmer.html" },
    { id: "buyer", label: "Buyer Portal", href: "buyer.html" },
    { id: "vendor", label: "Vendor Portal", href: "marketplace.html" }
  ];
  function banner() {
    var b = document.createElement("div");
    b.setAttribute("role", "note");
    b.style.cssText = "background:var(--gold-soft);color:var(--ink);font-size:12.5px;text-align:center;padding:8px 16px;line-height:1.4";
    b.textContent = "Preview with a snapshot of pilot data. Actions run in your browser only: no real payments, nothing is saved.";
    document.body.insertBefore(b, document.body.firstChild);
    document.addEventListener("click", function (e) {
      var a = e.target.closest && e.target.closest("[data-demo-only]");
      if (!a) return;
      e.preventDefault();
      FM.toast("That screen is part of the full app (FastAPI + PostgreSQL), not this preview.");
    });
  }
  if (document.body) banner(); else document.addEventListener("DOMContentLoaded", banner);
})();
