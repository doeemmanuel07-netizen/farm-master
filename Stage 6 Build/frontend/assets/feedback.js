/* Farm Master feedback button (13 Oct 2026).
 * The server adds this script to every page it serves (app/main.py
 * _flow_page), so the Overview, all four portals and every flow screen get
 * a "Feedback" button. It posts to POST /api/feedback; Super Admin reads
 * the results at /feedback. Self-contained: no dependency on components.js,
 * because the *-flow pages don't load it.
 */
(function () {
  if (window.__fmFeedback) return;
  window.__fmFeedback = true;

  var CSS =
    ".fmfb-btn{position:fixed;right:16px;bottom:16px;z-index:9998;display:inline-flex;align-items:center;gap:8px;min-height:44px;padding:0 18px;border:0;border-radius:999px;background:#1F5E3D;color:#fff;font:600 14px/1 system-ui,-apple-system,'Segoe UI',sans-serif;box-shadow:0 6px 20px rgba(20,61,40,.28);cursor:pointer}" +
    ".fmfb-btn:hover{background:#143D28}.fmfb-btn:focus-visible{outline:3px solid #E8A83C;outline-offset:2px}" +
    ".fmfb-back{position:fixed;inset:0;z-index:9999;background:rgba(26,31,27,.45);display:flex;align-items:flex-end;justify-content:center;padding:16px}" +
    "@media(min-width:640px){.fmfb-back{align-items:center}}" +
    ".fmfb-card{width:100%;max-width:440px;max-height:calc(100vh - 32px);overflow:auto;background:#FFFDF7;color:#1A1F1B;border-radius:16px;padding:20px;box-shadow:0 20px 50px rgba(0,0,0,.25);font:14px/1.45 system-ui,-apple-system,'Segoe UI',sans-serif}" +
    ".fmfb-card h2{margin:0 0 4px;font-size:18px;color:#143D28}.fmfb-card p{margin:0 0 14px;color:#5B6B5E}" +
    ".fmfb-card label{display:block;font-weight:600;margin:12px 0 6px}" +
    ".fmfb-types{display:flex;flex-wrap:wrap;gap:8px}" +
    ".fmfb-types button{min-height:40px;padding:0 14px;border-radius:999px;border:1px solid #CFD8CF;background:#fff;color:#1A1F1B;font:inherit;cursor:pointer}" +
    ".fmfb-types button[aria-pressed=true]{background:#1F5E3D;border-color:#1F5E3D;color:#fff}" +
    ".fmfb-card textarea,.fmfb-card input{width:100%;box-sizing:border-box;border:1px solid #CFD8CF;border-radius:10px;padding:10px 12px;font:inherit;background:#fff;color:#1A1F1B}" +
    ".fmfb-card textarea{min-height:120px;resize:vertical}" +
    ".fmfb-row{display:flex;gap:10px;justify-content:flex-end;margin-top:16px}" +
    ".fmfb-row button{min-height:44px;padding:0 18px;border-radius:10px;font:600 14px/1 system-ui,sans-serif;cursor:pointer}" +
    ".fmfb-cancel{background:transparent;border:1px solid #CFD8CF;color:#1A1F1B}.fmfb-send{background:#1F5E3D;border:0;color:#fff}" +
    ".fmfb-send[disabled]{opacity:.6;cursor:default}" +
    ".fmfb-msg{margin-top:10px;font-weight:600}.fmfb-msg.err{color:#A3312A}.fmfb-msg.ok{color:#1F5E3D}";

  var TYPES = [["suggestion", "Suggestion"], ["problem", "Something's wrong"], ["question", "Question"], ["praise", "I like this"]];

  function token() {
    try { var s = JSON.parse(localStorage.getItem("farmmaster_session") || "null"); return s && s.token; } catch (e) { return null; }
  }

  function el(tag, attrs, text) {
    var n = document.createElement(tag);
    for (var k in attrs) n.setAttribute(k, attrs[k]);
    if (text) n.textContent = text;
    return n;
  }

  function open(trigger) {
    var type = "suggestion";
    var back = el("div", { "class": "fmfb-back" });
    var card = el("div", { "class": "fmfb-card", role: "dialog", "aria-modal": "true", "aria-labelledby": "fmfb-title" });
    card.innerHTML =
      '<h2 id="fmfb-title">Share your feedback</h2>' +
      "<p>Tell the Farm Master team what you think of this page: ideas, problems or questions.</p>" +
      '<label id="fmfb-type-l">Type</label><div class="fmfb-types" role="group" aria-labelledby="fmfb-type-l"></div>' +
      '<label for="fmfb-text">Your feedback</label><textarea id="fmfb-text" maxlength="2000" required></textarea>' +
      '<label for="fmfb-name">Your name and organisation (optional)</label><input id="fmfb-name" maxlength="120" autocomplete="name">' +
      '<div class="fmfb-msg" role="status" aria-live="polite"></div>' +
      '<div class="fmfb-row"><button type="button" class="fmfb-cancel">Close</button><button type="button" class="fmfb-send">Send feedback</button></div>';
    var group = card.querySelector(".fmfb-types");
    TYPES.forEach(function (t) {
      var b = el("button", { type: "button", "aria-pressed": String(t[0] === type) }, t[1]);
      b.addEventListener("click", function () {
        type = t[0];
        Array.prototype.forEach.call(group.children, function (c) { c.setAttribute("aria-pressed", String(c === b)); });
      });
      group.appendChild(b);
    });
    back.appendChild(card);
    document.body.appendChild(back);
    var text = card.querySelector("#fmfb-text"), msg = card.querySelector(".fmfb-msg"), send = card.querySelector(".fmfb-send");
    try { card.querySelector("#fmfb-name").value = localStorage.getItem("fmfb_name") || ""; } catch (e) {}
    text.focus();

    function close() { document.removeEventListener("keydown", onKey); back.remove(); trigger.focus(); }
    function onKey(e) { if (e.key === "Escape") close(); }
    document.addEventListener("keydown", onKey);
    back.addEventListener("click", function (e) { if (e.target === back) close(); });
    card.querySelector(".fmfb-cancel").addEventListener("click", close);

    send.addEventListener("click", function () {
      var body = text.value.trim(), name = card.querySelector("#fmfb-name").value.trim();
      if (body.length < 3) { msg.className = "fmfb-msg err"; msg.textContent = "Please write a little more."; text.focus(); return; }
      send.disabled = true; send.textContent = "Sending…"; msg.textContent = "";
      var headers = { "Content-Type": "application/json" }, t = token();
      if (t) headers.Authorization = "Bearer " + t;
      fetch("/api/feedback", { method: "POST", headers: headers,
        body: JSON.stringify({ page: location.pathname, category: type, message: body, name: name || null }) })
        .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.detail && j.detail.substring ? j.detail : "Couldn't send. Please try again."); }); })
        .then(function () {
          try { localStorage.setItem("fmfb_name", name); } catch (e) {}
          msg.className = "fmfb-msg ok"; msg.textContent = "Thank you! Your feedback has been sent.";
          text.value = ""; send.textContent = "Send more";
          send.disabled = false;
          setTimeout(function () { if (document.body.contains(back)) close(); }, 1800);
        })
        .catch(function (err) { msg.className = "fmfb-msg err"; msg.textContent = err.message; send.disabled = false; send.textContent = "Send feedback"; });
    });
  }

  function init() {
    var style = el("style", {}); style.textContent = CSS; document.head.appendChild(style);
    var btn = el("button", { type: "button", "class": "fmfb-btn", "aria-haspopup": "dialog" });
    btn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 5h16v11H8l-4 4V5z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>Feedback';
    btn.addEventListener("click", function () { open(btn); });
    document.body.appendChild(btn);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
