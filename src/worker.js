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
 *
 * Scheduled cron:
 *   Daily at 04:17 UTC — fires a workflow_dispatch on the daily-scrape.yml
 *   GitHub Action. GitHub's own cron is unreliable (skips runs under load,
 *   delays under no guarantee), so we use Cloudflare's industrial-grade
 *   scheduler as the primary trigger. The GH-side schedule stays as a
 *   secondary backup; concurrency: cancel-in-progress: false in the workflow
 *   prevents double runs if both fire within minutes.
 *
 * Required secret:
 *   GITHUB_TOKEN — fine-grained PAT with Actions:write on ansvier/ph-heatmap
 *   Set via:  npx wrangler secret put GITHUB_TOKEN
 */

const PH_PROFILE_BASE = "https://www.pornhub.com/pornstar/";
const SLUG_RE = /^[a-z0-9][a-z0-9-]{0,80}$/;

const GH_OWNER = "ansvier";
const GH_REPO = "ph-heatmap";
const GH_WORKFLOW = "daily-scrape.yml";

async function triggerScrape(env) {
  if (!env.GITHUB_TOKEN) {
    console.error("scheduled: GITHUB_TOKEN secret is not set — cannot trigger workflow");
    return;
  }
  const url = `https://api.github.com/repos/${GH_OWNER}/${GH_REPO}/actions/workflows/${GH_WORKFLOW}/dispatches`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "hotmap-cf-cron",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ref: "main" }),
  });
  if (res.status === 204) {
    console.log("scheduled: triggered daily-scrape.yml on main");
  } else {
    const text = await res.text();
    console.error(`scheduled: workflow_dispatch failed status=${res.status} body=${text.slice(0, 200)}`);
  }
}

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

    // Manual trigger endpoint — useful for testing the cron without waiting.
    // Requires the same Authorization: Bearer header (using the GH token) so
    // randoms can't spam the workflow.
    if (url.pathname === "/_cron/trigger") {
      const auth = request.headers.get("authorization") || "";
      if (!env.GITHUB_TOKEN || auth !== `Bearer ${env.GITHUB_TOKEN}`) {
        return new Response("Forbidden", { status: 403 });
      }
      ctx.waitUntil(triggerScrape(env));
      return new Response("queued\n", { status: 202 });
    }

    // Everything else → static assets from public/
    return env.ASSETS.fetch(request);
  },

  /**
   * Cloudflare Cron handler — fires on the schedules in wrangler.jsonc
   * `triggers.crons`. We dispatch the GitHub Action; the actual scraping
   * still runs on GitHub-hosted runners because curl-cffi needs Python.
   */
  async scheduled(event, env, ctx) {
    console.log(`scheduled: cron=${event.cron} time=${new Date(event.scheduledTime).toISOString()}`);
    ctx.waitUntil(triggerScrape(env));
  },
};
