// Permanent front door for the Farm Master public preview (README
// "Preview via Cloudflare"): https://farm-master.doeemmanuel07.workers.dev.
// It forwards each request to the current Quick Tunnel, whose address
// start-preview.ps1 writes to KV under "tunnel_url" every time the tunnel
// restarts (and deletes on --stop, so the link shows "offline").
// Optional hardening: protect the Worker with Cloudflare Access, set the
// PROXY_SECRET Worker secret and FARM_MASTER_PROXY_SECRET in
// .preview/secret.env, and the app then refuses requests that skip it.

export default {
  async fetch(request, env) {
    const target = await env.PREVIEW.get("tunnel_url");
    if (!target) {
      return new Response("The Farm Master preview is offline right now. Please try again later.", {
        status: 503, headers: { "content-type": "text/plain; charset=utf-8", "retry-after": "60" },
      });
    }
    const incoming = new URL(request.url);
    const url = new URL(incoming.pathname + incoming.search, target);
    const headers = new Headers(request.headers);
    headers.set("x-fm-proxy-secret", env.PROXY_SECRET);
    headers.set("x-forwarded-host", incoming.host);
    let response;
    try {
      response = await fetch(url, {
        method: request.method,
        headers,
        body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
        redirect: "manual",
      });
    } catch (err) {
      return new Response("The Farm Master preview is restarting. Please try again in a minute.", {
        status: 502, headers: { "content-type": "text/plain; charset=utf-8" },
      });
    }
    // Keep absolute redirects on this address rather than the tunnel's.
    const location = response.headers.get("location");
    if (location && location.startsWith(target)) {
      const out = new Response(response.body, response);
      out.headers.set("location", location.slice(target.length) || "/");
      return out;
    }
    return response;
  },
};
