# Cron Watchdog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a second CF Worker cron at 04:35 UTC that detects when the daily-scrape `workflow_dispatch` (fired at 04:17) is still stuck in `queued` after 15 min and automatically cancels + re-triggers it.

**Architecture:** New `watchdog(env)` function in `src/worker.js` calls GH API to inspect the latest run; cancels + re-fires `triggerScrape()` if stuck. The existing `scheduled(event, env, ctx)` handler branches on `event.cron` to route the two cron firings. Adds a Bearer-authed `/_watchdog/test` endpoint for manual smoke testing. One new cron entry in `wrangler.jsonc`.

**Tech Stack:** Cloudflare Workers (JS runtime), GitHub REST API. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-02-cron-watchdog-design.md`

---

## File map

| Path | Change | Task |
|---|---|---|
| `src/worker.js` | + `watchdog(env)` function; + cancel-run helper; + scheduled() branching; + `/_watchdog/test` endpoint | Tasks 1–3 |
| `wrangler.jsonc` | + `"35 4 * * *"` in `triggers.crons` | Task 4 |
| `README.md` | + Watchdog subsection in cron / ops section | Task 5 |

No new files. No tests (CF Workers tooling is heavy for this scope; smoke endpoint replaces unit tests).

---

### Task 1: `watchdog(env)` function + GH API helpers

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/src/worker.js`

Add the core watchdog logic plus a cancel-run helper, both near the existing `triggerScrape` function. No behavior change yet — the function is unused until Task 2 wires it into `scheduled()`.

- [ ] **Step 1: Add the cancel-run helper**

Open `/Users/ansvier/ph-heatmap/src/worker.js`. After the existing `triggerScrape` function (line 57), add:

```javascript
async function cancelRun(env, runId) {
  if (!env.GITHUB_TOKEN) {
    console.error("watchdog: GITHUB_TOKEN secret is not set — cannot cancel run");
    return false;
  }
  const url = `https://api.github.com/repos/${GH_OWNER}/${GH_REPO}/actions/runs/${runId}/cancel`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "hotmap-cf-cron",
    },
  });
  // GH returns 202 on accepted cancel, 409 if already terminal (treat as success).
  if (res.status === 202 || res.status === 409) {
    console.log(`watchdog: cancelled run ${runId} (status=${res.status})`);
    return true;
  }
  const text = await res.text();
  console.error(`watchdog: cancel failed runId=${runId} status=${res.status} body=${text.slice(0, 200)}`);
  return false;
}
```

- [ ] **Step 2: Add the watchdog function**

Immediately after `cancelRun`, add:

```javascript
async function watchdog(env) {
  if (!env.GITHUB_TOKEN) {
    console.error("watchdog: GITHUB_TOKEN secret is not set");
    return;
  }
  const STALL_THRESHOLD_MIN = 15;
  const listUrl = `https://api.github.com/repos/${GH_OWNER}/${GH_REPO}/actions/workflows/${GH_WORKFLOW}/runs?per_page=1`;
  let latest;
  try {
    const res = await fetch(listUrl, {
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "hotmap-cf-cron",
      },
    });
    if (!res.ok) {
      const text = await res.text();
      console.error(`watchdog: list-runs failed status=${res.status} body=${text.slice(0, 200)}`);
      return;
    }
    const data = await res.json();
    latest = data.workflow_runs && data.workflow_runs[0];
  } catch (err) {
    console.error(`watchdog: list-runs threw: ${err.message}`);
    return;
  }
  if (!latest) {
    console.log("watchdog: no runs found for daily-scrape.yml — nothing to check");
    return;
  }

  const createdAt = new Date(latest.created_at);
  const ageMin = (Date.now() - createdAt.getTime()) / 60000;

  if (latest.status === "queued" && ageMin > STALL_THRESHOLD_MIN) {
    console.log(`watchdog: run ${latest.id} stuck in queued for ${ageMin.toFixed(1)} min — cancelling + re-triggering`);
    const cancelled = await cancelRun(env, latest.id);
    if (!cancelled) {
      console.error("watchdog: skipping re-trigger because cancel failed");
      return;
    }
    // Give GH a moment to mark the run as cancelled before dispatching a new one.
    await new Promise((resolve) => setTimeout(resolve, 5000));
    await triggerScrape(env);
    console.log(`watchdog: triggered fresh workflow_dispatch after cancelling run ${latest.id}`);
  } else {
    console.log(
      `watchdog: run ${latest.id} status=${latest.status} age=${ageMin.toFixed(1)}min — no action`
    );
  }
}
```

- [ ] **Step 3: Smoke-verify the file still parses**

Run `wrangler` validation locally (does NOT deploy — just dry-run validation):

```bash
cd /Users/ansvier/ph-heatmap
npx wrangler deploy --dry-run 2>&1 | tail -10
```

Expected: prints `Total Upload: ...` or similar success indicator without syntax errors. If there are JS syntax errors, fix them before proceeding.

- [ ] **Step 4: Commit**

```bash
cd /Users/ansvier/ph-heatmap
git add src/worker.js
git commit -m "$(cat <<'EOF'
feat(worker): watchdog + cancelRun helpers for GH Actions queue stalls

watchdog() inspects the latest daily-scrape run; cancels + re-triggers
if status is 'queued' and age > 15 min. cancelRun() is the cancel
helper used by it. Both treat missing GITHUB_TOKEN as a no-op with
an error log, matching the existing triggerScrape pattern.

Not yet wired in — Task 2 connects watchdog() to the second cron;
Task 3 exposes it via /_watchdog/test for manual smoke.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Branch `scheduled()` by `event.cron`

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/src/worker.js`

The existing `scheduled()` handler unconditionally calls `triggerScrape()`. After this task, it routes to `watchdog()` when the watchdog cron fires.

- [ ] **Step 1: Update the `scheduled` handler**

In `src/worker.js`, find the existing `scheduled` handler (around line 108):

```javascript
  async scheduled(event, env, ctx) {
    console.log(`scheduled: cron=${event.cron} time=${new Date(event.scheduledTime).toISOString()}`);
    ctx.waitUntil(triggerScrape(env));
  },
```

Replace with:

```javascript
  async scheduled(event, env, ctx) {
    console.log(`scheduled: cron=${event.cron} time=${new Date(event.scheduledTime).toISOString()}`);
    // Two cron entries in wrangler.jsonc:
    //   "17 4 * * *" → fires the daily-scrape workflow_dispatch
    //   "35 4 * * *" → watchdog: cancels + re-triggers if the 04:17 fire is still queued
    if (event.cron === "35 4 * * *") {
      ctx.waitUntil(watchdog(env));
    } else {
      ctx.waitUntil(triggerScrape(env));
    }
  },
```

- [ ] **Step 2: Smoke-verify**

```bash
cd /Users/ansvier/ph-heatmap
npx wrangler deploy --dry-run 2>&1 | tail -5
```

Expected: success, no syntax errors.

- [ ] **Step 3: Commit**

```bash
git add src/worker.js
git commit -m "$(cat <<'EOF'
feat(worker): scheduled() branches by cron string to route to watchdog

The 04:35 UTC cron now dispatches to watchdog(); 04:17 UTC stays on
triggerScrape(). Default (unknown cron) falls through to the trigger
path so a wrangler config drift doesn't accidentally disable the
daily scrape.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `/_watchdog/test` debug endpoint

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/src/worker.js`

Mirror the existing `/_cron/trigger` pattern so the watchdog can be tested manually without waiting for 04:35 UTC.

- [ ] **Step 1: Add the endpoint**

In `src/worker.js`, find the existing `/_cron/trigger` block (around lines 90–97):

```javascript
    if (url.pathname === "/_cron/trigger") {
      const auth = request.headers.get("authorization") || "";
      if (!env.GITHUB_TOKEN || auth !== `Bearer ${env.GITHUB_TOKEN}`) {
        return new Response("Forbidden", { status: 403 });
      }
      ctx.waitUntil(triggerScrape(env));
      return new Response("queued\n", { status: 202 });
    }
```

Immediately after that block (before `// Everything else → static assets from public/`), add:

```javascript
    // Manual watchdog test — runs the watchdog logic on demand. Same Bearer
    // gate as /_cron/trigger. Useful to verify the watchdog code path after
    // a deploy without waiting for the 04:35 UTC cron.
    if (url.pathname === "/_watchdog/test") {
      const auth = request.headers.get("authorization") || "";
      if (!env.GITHUB_TOKEN || auth !== `Bearer ${env.GITHUB_TOKEN}`) {
        return new Response("Forbidden", { status: 403 });
      }
      ctx.waitUntil(watchdog(env));
      return new Response("watchdog queued\n", { status: 202 });
    }
```

- [ ] **Step 2: Smoke-verify**

```bash
cd /Users/ansvier/ph-heatmap
npx wrangler deploy --dry-run 2>&1 | tail -5
```

Expected: success.

- [ ] **Step 3: Commit**

```bash
git add src/worker.js
git commit -m "$(cat <<'EOF'
feat(worker): /_watchdog/test endpoint for manual smoke

Same Bearer-token gate as /_cron/trigger. POST hits the watchdog
function inline and returns 202 — for verifying the watchdog code
path after deploy without waiting for the 04:35 UTC cron.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Add second cron in `wrangler.jsonc`

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/wrangler.jsonc`

- [ ] **Step 1: Read current state**

```bash
cat /Users/ansvier/ph-heatmap/wrangler.jsonc
```

Expected: shows the existing `triggers` block with `crons: ["17 4 * * *"]`.

- [ ] **Step 2: Add the second cron**

Open `/Users/ansvier/ph-heatmap/wrangler.jsonc`. Find the line:

```jsonc
    "crons": ["17 4 * * *"]
```

Replace with:

```jsonc
    "crons": ["17 4 * * *", "35 4 * * *"]
```

- [ ] **Step 3: Validate config**

```bash
cd /Users/ansvier/ph-heatmap
npx wrangler deploy --dry-run 2>&1 | grep -i "cron"
```

Expected: both cron entries listed in the dry-run output (e.g., `Triggers: ... 17 4 * * * ... 35 4 * * *`).

- [ ] **Step 4: Commit**

```bash
git add wrangler.jsonc
git commit -m "$(cat <<'EOF'
feat(worker): second cron at 04:35 UTC for watchdog

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: README subsection

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/README.md`

- [ ] **Step 1: Find the existing cron/ops section**

Open `/Users/ansvier/ph-heatmap/README.md` and search for "cron" or "Cloudflare Worker". There's likely a section already describing the daily trigger. The watchdog subsection belongs immediately after.

- [ ] **Step 2: Add the watchdog paragraph**

Insert (in the appropriate spot near existing cron docs):

```markdown
**Cron watchdog.** GitHub Actions self-hosted runners occasionally leave a queued
job without picking it up (observed: one job sat queued 1h57m before manual
intervention). A second CF Worker cron fires at 04:35 UTC and checks the latest
`daily-scrape.yml` run via the GitHub API: if status is `queued` and age > 15
minutes, the watchdog cancels the stuck run and triggers a fresh
`workflow_dispatch`. Both cron entries live in `wrangler.jsonc:triggers.crons`.
To smoke-test without waiting:

\`\`\`bash
curl -X POST https://hotmap.cam/_watchdog/test \\
  -H "Authorization: Bearer $GITHUB_TOKEN"
\`\`\`

The endpoint requires the same Bearer-token gate as `/_cron/trigger`.
```

(Adjust the surrounding markdown headers/indent to match the file's existing structure.)

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "$(cat <<'EOF'
docs: README subsection describing the cron watchdog

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Deploy + manual smoke

**Files:** none (operational only).

- [ ] **Step 1: Deploy the Worker**

```bash
cd /Users/ansvier/ph-heatmap
npx wrangler deploy 2>&1 | tail -8
```

Expected: lines including `Total Upload: ...`, `Deployed ... triggers ... crons:`, listing both `17 4 * * *` and `35 4 * * *`. No errors.

- [ ] **Step 2: Smoke-test the new endpoint**

Use the same `GITHUB_TOKEN` Bearer value already used for `/_cron/trigger`:

```bash
GITHUB_TOKEN_VALUE="<paste your GH PAT here>"
curl -s -X POST https://hotmap.cam/_watchdog/test \
  -H "Authorization: Bearer $GITHUB_TOKEN_VALUE" \
  -w "\nHTTP %{http_code}\n"
```

Expected: response body `watchdog queued`, HTTP 202.

- [ ] **Step 3: Tail Worker logs to confirm execution**

In a separate terminal:

```bash
cd /Users/ansvier/ph-heatmap
npx wrangler tail src/worker.js
```

Re-fire the manual endpoint from Step 2. Within ~5 seconds, the tail should show one of:
- `watchdog: run <id> status=completed age=<N>min — no action` (most likely — yesterday's run was probably last, fully completed)
- `watchdog: run <id> status=in_progress age=<N>min — no action` (if a fresh run is currently going)
- `watchdog: run <id> stuck in queued for <N> min — cancelling + re-triggering` (only if we actually had a stuck run when invoked)

The first two are normal smoke outcomes — they verify the function ran, hit GH API, parsed the response correctly, and decided no action.

- [ ] **Step 4: If logs show success, push to git**

```bash
git push 2>&1 | tail -3
```

Expected: push succeeds.

- [ ] **Step 5: First real watchdog firing**

Tomorrow at 04:35 UTC the watchdog fires automatically. Today's deploy is live so tomorrow's 04:17 UTC daily-scrape gets the safety net. If the daily-scrape runs normally (no stall), the watchdog logs the no-action path and exits. If it stalls again, the watchdog recovers it.

No further action needed — the watchdog is now part of the daily infrastructure.

---

## Self-review checklist (filled out by plan author)

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| `watchdog(env)` function with 15-min threshold | Task 1 |
| `cancelRun(env, runId)` helper | Task 1 |
| `scheduled()` branches on `event.cron` | Task 2 |
| `/_watchdog/test` debug endpoint with Bearer auth | Task 3 |
| Second cron entry `"35 4 * * *"` in `wrangler.jsonc` | Task 4 |
| README subsection | Task 5 |
| Deploy + smoke verification | Task 6 |
| GH API rate-limit caveat (try/catch) | Task 1 (covered by try/catch around list-runs fetch) |
| Missing `GITHUB_TOKEN` is a no-op error log | Task 1 (covered in both `watchdog` and `cancelRun`) |
| 5-second wait between cancel and re-trigger | Task 1 (covered by `await new Promise(setTimeout(5000))`) |

No gaps.

**Placeholder scan:** No TBD / TODO / "similar to". Every step has the actual code or the exact command.

**Type consistency:** `watchdog(env)` and `cancelRun(env, runId)` signatures are defined in Task 1 and consumed in Task 2 (scheduled handler) and Task 3 (endpoint). Function name `watchdog` is used consistently across all tasks. The cron strings `"17 4 * * *"` and `"35 4 * * *"` match between Task 2 (handler comparison), Task 4 (config), and Task 5 (docs).

**Conditional note:** Task 6 Step 2 requires the user's actual `GITHUB_TOKEN` PAT value. The plan tells them to paste it — the engineer running the plan should treat that value as a secret (don't commit it anywhere).
