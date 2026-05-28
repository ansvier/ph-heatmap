/**
 * HotMap Cloudflare Worker
 *
 * Routes:
 *   /r/<slug>  → 302 redirect to https://www.pornhub.com/pornstar/<slug>
 *               (logged for click-tracking; future affiliate-tag insertion point)
 *   anything else → serve from public/ static assets binding (ASSETS)
 *
 * The redirect is intentionally a thin layer right now — no affiliate tag yet.
 * When the Paxum / TrafficJunky / Pornhub Premium PPS wiring is in place,
 * change the target URL builder to append the appropriate tracking param.
 * No frontend change required at that point.
 */

const PH_PROFILE_BASE = "https://www.pornhub.com/pornstar/";
const SLUG_RE = /^[a-z0-9][a-z0-9-]{0,80}$/;

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // /r/<slug> → outbound profile redirect
    if (url.pathname.startsWith("/r/")) {
      const rest = url.pathname.slice(3).replace(/\/+$/, "");
      if (!SLUG_RE.test(rest)) {
        return new Response("Invalid slug", { status: 400 });
      }
      const target = PH_PROFILE_BASE + rest;

      // Lightweight click log (visible in CF Workers tail).
      const referer = request.headers.get("referer") || "-";
      const ua = (request.headers.get("user-agent") || "-").slice(0, 80);
      console.log(`click slug=${rest} ref=${referer} ua=${ua}`);

      return new Response(null, {
        status: 302,
        headers: {
          Location: target,
          "Cache-Control": "no-store",
          // Help search engines know this is an outbound bounce, not content
          "X-Robots-Tag": "noindex, nofollow",
        },
      });
    }

    // Everything else → static assets from public/
    return env.ASSETS.fetch(request);
  },
};
