/*
 * Farm Master shared component behaviour -- toast, multi-step modal, stepper,
 * activity ticker, SVG icon set, API + session helpers and the top bar.
 * Vanilla JS, no build step. Exposes a single global: window.FM.
 * See docs/design-system.md.
 */
(function () {
  "use strict";

  var FM = {};

  /* ---------------- Utilities ---------------- */
  FM.esc = function (s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  };
  FM.$ = function (sel, ctx) { return (ctx || document).querySelector(sel); };
  FM.$$ = function (sel, ctx) { return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); };
  FM.money = function (n) {
    var v = Number(n || 0);
    return "GH₵ " + v.toLocaleString("en-GH", { minimumFractionDigits: v % 1 ? 2 : 0, maximumFractionDigits: 2 });
  };
  FM.reducedMotion = function () {
    return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  };

  /* ---------------- Icons (replace the demo's emoji) ---------------- */
  var ICON_PATHS = {
    leaf: '<path d="M12 2C12 2 6 6.5 6 12.5C6 16.6 8.7 20 12 20C15.3 20 18 16.6 18 12.5C18 6.5 12 2 12 2Z"/><path d="M12 20V13"/>',
    check: '<path d="M5 12.5L10 17L19 7"/>',
    maize: '<path d="M12 3c2.5 0 4 3 4 7.5S14.5 19 12 19s-4-4-4-8.5S9.5 3 12 3z"/><path d="M10 7h4M9.5 10h5M9.5 13h5M10 16h4"/><path d="M8 13c-3 1-4 4-4 8 3-1 6-3 8-2M16 13c3 1 4 4 4 8-3-1-6-3-8-2"/>',
    rice: '<path d="M12 21V9"/><path d="M12 9c0-3 2-5 4-6M12 12c-2-1-4-1-6 0M12 15c2-1 4-1 6 0M12 9c-1-2-3-3-5-3"/><circle cx="16.5" cy="3.5" r="1"/><circle cx="6" cy="12" r="1"/><circle cx="18" cy="15" r="1"/><circle cx="6.5" cy="6" r="1"/>',
    soybean: '<path d="M7 4c4-1 8 1 10 5s1 9-3 11-8-1-9-5 0-10 2-11z"/><circle cx="10" cy="9" r="1.6"/><circle cx="12.5" cy="13" r="1.6"/><circle cx="13" cy="17" r="1.3"/>',
    tomato: '<circle cx="12" cy="13.5" r="7"/><path d="M12 6.5V3M9 5.5l3 1 3-1M8.5 7.5c1 .6 2.2.9 3.5.9s2.5-.3 3.5-.9"/>',
    seed: '<path d="M12 21v-8"/><path d="M12 13c0-4 3-6 7-6 0 4-3 6-7 6zM12 13c0-3-2.5-5-6-5 0 3 2.5 5 6 5z"/><path d="M8 21h8"/>',
    fertiliser: '<path d="M6 7h12l-1 13H7L6 7z"/><path d="M8 7V4h8v3"/><path d="M10 12h4M10 15h4"/>',
    bottle: '<path d="M10 2h4v4l2 3v12H8V9l2-3V2z"/><path d="M8 13h8"/>',
    tractor: '<circle cx="7" cy="16" r="4"/><circle cx="18" cy="17" r="2.5"/><path d="M7 12V6h5l2 6h4.5a1.5 1.5 0 0 1 1.5 1.5v3"/><path d="M14 12H7"/>',
    planter: '<path d="M3 15h18M6 15V9h12v6"/><circle cx="7" cy="18" r="2"/><circle cx="17" cy="18" r="2"/><path d="M9 9V6M15 9V6"/>',
    pump: '<path d="M4 18h10V8H4v10z"/><path d="M14 11h3a3 3 0 0 1 3 3v4"/><path d="M7 8V5h4v3"/><path d="M20 21a1.5 1.5 0 0 0 1.5-1.5c0-1-1.5-2.5-1.5-2.5s-1.5 1.5-1.5 2.5A1.5 1.5 0 0 0 20 21z"/>',
    plough: '<path d="M3 6h7l4 6h5"/><path d="M14 12l-3 6h8l-2-6"/><path d="M3 20h18"/>',
    harvester: '<path d="M2 14h6l2-5h7l3 5v3H2v-3z"/><circle cx="6" cy="18" r="2"/><circle cx="16" cy="18" r="2"/><path d="M2 10l3-3M5 10l3-3"/>',
    clipboard: '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V3h6v1"/><path d="M8.5 11l2 2 4-4M8.5 17h7"/>',
    truck: '<rect x="1" y="7" width="13" height="8" rx="1.5"/><path d="M14 10H17.5L21 13.5V15H14V10Z"/><circle cx="5.5" cy="17" r="1.6"/><circle cx="17.5" cy="17" r="1.6"/>',
    box: '<path d="M3 7l9-4 9 4v10l-9 4-9-4V7z"/><path d="M3 7l9 4 9-4M12 11v10"/>'
  };
  FM.icon = function (name, size) {
    var s = size || 20;
    var p = ICON_PATHS[name] || ICON_PATHS.box;
    return '<svg width="' + s + '" height="' + s + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + p + "</svg>";
  };
  FM.iconNames = Object.keys(ICON_PATHS);

  /* ---------------- Toast ---------------- */
  var toastTimer;
  FM.toast = function (msg, opts) {
    var el = document.getElementById("fm-toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "fm-toast";
      el.className = "toast";
      el.setAttribute("role", "status");
      el.setAttribute("aria-live", "polite");
      document.body.appendChild(el);
    }
    el.textContent = msg;
    el.classList.toggle("error", !!(opts && opts.error));
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.classList.remove("show"); }, (opts && opts.ms) || 2800);
  };

  /* ---------------- Modal ----------------
   * FM.modal.open(renderFn) -- renderFn(modalEl, api) fills the modal and wires
   * its own buttons; api.close() / api.render(nextFn) move between steps.
   */
  FM.modal = (function () {
    var veil, box, lastFocus;
    function ensure() {
      if (veil) return;
      veil = document.createElement("div");
      veil.className = "modal-veil";
      box = document.createElement("div");
      box.className = "modal";
      box.setAttribute("role", "dialog");
      box.setAttribute("aria-modal", "true");
      veil.appendChild(box);
      document.body.appendChild(veil);
      document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && veil.classList.contains("show") && !veil.dataset.locked) api.close();
      });
    }
    var api = {
      open: function (renderFn) {
        ensure();
        lastFocus = document.activeElement;
        veil.classList.add("show");
        api.render(renderFn);
      },
      render: function (renderFn) {
        box.innerHTML = "";
        renderFn(box, api);
        var focusable = box.querySelector("button, [href], input, select, textarea");
        if (focusable) focusable.focus();
      },
      lock: function (on) { if (veil) { if (on) veil.dataset.locked = "1"; else delete veil.dataset.locked; } },
      close: function () {
        if (!veil) return;
        veil.classList.remove("show");
        delete veil.dataset.locked;
        if (lastFocus && lastFocus.focus) lastFocus.focus();
      }
    };
    return api;
  })();

  /* ---------------- Stepper ---------------- */
  FM.stepper = function (labels, currentIndex) {
    return '<div class="stepper" role="list">' + labels.map(function (s, i) {
      var cls = i < currentIndex ? "done" : (i === currentIndex ? "current" : "");
      var state = i < currentIndex ? "completed" : (i === currentIndex ? "current step" : "pending");
      return '<div class="step ' + cls + '" role="listitem" aria-label="' + FM.esc(s + ", " + state) + '"><div class="dot"></div><small>' + FM.esc(s) + "</small></div>";
    }).join("") + "</div>";
  };

  FM.checklist = function (items) {
    return '<ul class="check-list">' + items.map(function (t) {
      return "<li>" + FM.icon("check", 14) + "<span>" + FM.esc(t) + "</span></li>";
    }).join("") + "</ul>";
  };

  /* ---------------- Ticker ---------------- */
  FM.ticker = function (el, fetchMessages, opts) {
    var interval = (opts && opts.interval) || 5000;
    var refresh = (opts && opts.refresh) || 60000;
    var msgs = [], idx = 0;
    var txt = el.querySelector(".txt");
    function load() {
      return Promise.resolve(fetchMessages()).then(function (m) {
        if (m && m.length) { msgs = m; if (idx >= msgs.length) idx = 0; txt.textContent = msgs[idx]; }
      }).catch(function () {});
    }
    load();
    setInterval(load, refresh);
    setInterval(function () {
      if (msgs.length < 2) return;
      idx = (idx + 1) % msgs.length;
      if (FM.reducedMotion()) { txt.textContent = msgs[idx]; return; }
      txt.style.opacity = 0;
      setTimeout(function () { txt.textContent = msgs[idx]; txt.style.opacity = 1; }, 300);
    }, interval);
  };

  /* ---------------- Session + API ----------------
   * Shares the "farmmaster_session" key with every existing *_flow_live page,
   * including its 10-minute inactivity logout, so a sign-in carries across.
   */
  var SESSION_KEY = "farmmaster_session";
  var INACTIVITY_LIMIT_MS = 10 * 60 * 1000;
  FM.session = {
    get: function () {
      try {
        var raw = localStorage.getItem(SESSION_KEY);
        if (!raw) return null;
        var s = JSON.parse(raw);
        if (!s.token || (Date.now() - s.lastActivityAt) > INACTIVITY_LIMIT_MS) { localStorage.removeItem(SESSION_KEY); return null; }
        return s;
      } catch (e) { return null; }
    },
    save: function (token, extra) {
      try {
        var s = { token: token, lastActivityAt: Date.now() };
        if (extra) for (var k in extra) s[k] = extra[k];
        localStorage.setItem(SESSION_KEY, JSON.stringify(s));
      } catch (e) {}
    },
    touch: function () {
      try {
        var raw = localStorage.getItem(SESSION_KEY);
        if (!raw) return;
        var s = JSON.parse(raw);
        s.lastActivityAt = Date.now();
        localStorage.setItem(SESSION_KEY, JSON.stringify(s));
      } catch (e) {}
    },
    clear: function () { try { localStorage.removeItem(SESSION_KEY); } catch (e) {} }
  };
  var lastTouch = 0;
  ["mousemove", "keydown", "click", "scroll", "touchstart"].forEach(function (evt) {
    document.addEventListener(evt, function () {
      var now = Date.now();
      if (now - lastTouch > 5000) { lastTouch = now; FM.session.touch(); }
    }, { passive: true });
  });

  FM.api = function (method, path, body) {
    var s = FM.session.get();
    var headers = {};
    if (s) headers["Authorization"] = "Bearer " + s.token;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    return fetch(path, { method: method, headers: headers, body: body === undefined ? undefined : JSON.stringify(body) })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (data) {
          if (!res.ok) {
            var detail = data.detail;
            if (Array.isArray(detail)) detail = detail.map(function (d) { return d.msg; }).join("; ");
            var err = new Error(detail || ("Request failed: " + res.status));
            err.status = res.status;
            throw err;
          }
          return data;
        });
      });
  };
  FM.get = function (p) { return FM.api("GET", p); };
  FM.post = function (p, b) { return FM.api("POST", p, b === undefined ? {} : b); };
  FM.put = function (p, b) { return FM.api("PUT", p, b); };

  /* ---------------- Sign-in card ----------------
   * FM.signIn(container, { role, demoEmail, onDone }) renders the two-step
   * email/password -> email OTP sign-in used by every portal page.
   */
  FM.signIn = function (container, opts) {
    var state = { email: opts.demoEmail || "", password: "", challengeId: null, devCode: "" };
    function render(step, error) {
      var html = '<div class="card" style="max-width:440px;margin:40px auto;">';
      if (step === "creds") {
        html += "<h3>Sign in to the " + FM.esc(opts.portalName) + "</h3>" +
          '<div class="hint">' + FM.esc(opts.hint || "Use your Farm Master account. A one-time code is sent to your email.") + "</div>" +
          (error ? '<div class="notice error">' + FM.esc(error) + "</div>" : "") +
          '<form id="fm-signin-form"><div class="field"><label for="fm-email">Email</label><input id="fm-email" type="email" autocomplete="username" required value="' + FM.esc(state.email) + '"></div>' +
          '<div class="field"><label for="fm-pass">Password</label><input id="fm-pass" type="password" autocomplete="current-password" required></div>' +
          '<button class="btn btn-primary btn-block" type="submit">Continue</button></form>';
        if (opts.registerHref) html += '<a class="card-link" href="' + FM.esc(opts.registerHref) + '">New to Farm Master? Register →</a>';
      } else {
        html += "<h3>Enter your one-time code</h3>" +
          '<div class="hint">We sent a 6-digit code to ' + FM.esc(state.email) + ".</div>" +
          (state.devCode ? '<div class="notice">Development build: your code is <strong>' + FM.esc(state.devCode) + "</strong></div>" : "") +
          (error ? '<div class="notice error">' + FM.esc(error) + "</div>" : "") +
          '<form id="fm-otp-form"><div class="field"><label for="fm-otp">Code</label><input id="fm-otp" inputmode="numeric" autocomplete="one-time-code" required maxlength="6"></div>' +
          '<button class="btn btn-primary btn-block" type="submit">Sign in</button></form>';
      }
      container.innerHTML = html + "</div>";
      var f1 = FM.$("#fm-signin-form", container);
      if (f1) f1.addEventListener("submit", function (e) {
        e.preventDefault();
        state.email = FM.$("#fm-email", container).value.trim();
        state.password = FM.$("#fm-pass", container).value;
        FM.post("/auth/login", { email: state.email, password: state.password }).then(function (r) {
          state.challengeId = r.challenge_id;
          state.devCode = r.dev_only_email_code || "";
          render("otp");
        }).catch(function (err) { render("creds", err.message); });
      });
      var f2 = FM.$("#fm-otp-form", container);
      if (f2) f2.addEventListener("submit", function (e) {
        e.preventDefault();
        FM.post("/auth/login/verify-otp", { challenge_id: state.challengeId, email_code: FM.$("#fm-otp", container).value.trim() }).then(function (r) {
          if (opts.role && r.role !== opts.role) {
            render("creds", "That account is a " + r.role.replace(/_/g, " ") + " account. Sign in with a " + opts.role + " account to use this portal.");
            return;
          }
          FM.session.save(r.access_token, { role: r.role, fullName: r.full_name });
          opts.onDone(r);
        }).catch(function (err) { render("otp", err.message); });
      });
    }
    render("creds");
  };

  /* ---------------- Top bar ----------------
   * FM.topbar(el, { active }) -- leaf mark, wordmark, tagline, segmented
   * portal switcher (real navigation), status pill / sign-out.
   */
  FM.PORTALS = [
    { id: "overview", label: "Overview", href: "/" },
    { id: "farmer", label: "Farmer Portal", href: "/farmer" },
    { id: "buyer", label: "Buyer Portal", href: "/buyer" },
    { id: "vendor", label: "Vendor Portal", href: "/marketplace" }
  ];
  FM.topbar = function (el, opts) {
    var s = FM.session.get();
    var right = s
      ? '<button class="fm-pill" type="button" id="fm-signout" title="Sign out"><span class="dot"></span>' + FM.esc(s.fullName || "Signed in") + " · Sign out</button>"
      : '<span class="fm-pill"><span class="dot"></span>' + FM.esc((opts && opts.pill) || "Pilot · Tema") + "</span>";
    el.className = "fm-topbar";
    el.innerHTML =
      '<a class="fm-brand" href="/"><span class="fm-brand-mark"><svg viewBox="0 0 24 24" fill="none"><path d="M12 2C12 2 6 6.5 6 12.5C6 16.6 8.7 20 12 20C15.3 20 18 16.6 18 12.5C18 6.5 12 2 12 2Z" stroke="white" stroke-width="1.6" stroke-linejoin="round"/><path d="M12 20V13" stroke="white" stroke-width="1.6" stroke-linecap="round"/></svg></span>' +
      '<span><span class="fm-brand-name" style="display:block">Farm Master</span><span class="fm-brand-tag" style="display:block">Farm-gate to market, Ghana</span></span></a>' +
      '<nav class="fm-tabs" aria-label="Portal switcher">' + FM.PORTALS.map(function (p) {
        return '<a class="fm-tab' + (opts && opts.active === p.id ? " active" : "") + '" href="' + p.href + '"' + (opts && opts.active === p.id ? ' aria-current="page"' : "") + ">" + p.label + "</a>";
      }).join("") + "</nav>" + right;
    var so = FM.$("#fm-signout", el);
    if (so) so.addEventListener("click", function () { FM.session.clear(); window.location.reload(); });
  };

  window.FM = FM;
})();
