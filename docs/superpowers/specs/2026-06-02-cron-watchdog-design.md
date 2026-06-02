# Cron Watchdog — design

**Status:** approved
**Date:** 2026-06-02
**Author:** ansvier + claude

## Problem

GitHub Actions self-hosted runners occasionally fail to pick up a queued job even when the runner is online and idle. Observed today: the 04:17 UTC cron triggered a `workflow_dispatch`, the runner showed `status=online, busy=false`, but the job sat in `status=queued` for 1h57m before a human cancelled and re-triggered it. The site missed today's data refresh until the manual intervention.

The existing trigger path (CF Worker → `workflow_dispatch` → GH Actions runner) has no liveness check. We have no automated recovery from a stuck queue.

## Goal

When the daily scrape's `workflow_dispatch` triggered by the CF Worker fails to start picking up within a reasonable window, automatically cancel the stuck run and re-trigger a fresh one. No human intervention required for the typical "GH didn't dispatch to runner" failure mode.

## Decision

### 1. Architecture

Add a second CF Cron Worker that fires 18 minutes after the main trigger and checks whether the run actually started:

```
04:17 UTC — existing cron "17 4 * * *" → triggerScrape()    (fire workflow_dispatch)
04:35 UTC — new cron      "35 4 * * *" → watchdog()         (check + recover)
```

Both share the same `scheduled(event, env, ctx)` handler in `src/worker.js`. We branch on `event.cron` to dispatch to the right function.

### 2. `watchdog(env)` logic

1. `GET /repos/<owner>/<repo>/actions/workflows/daily-scrape.yml/runs?per_page=1` to fetch the most recent run.
2. Compute `age = now - created_at` (in minutes).
3. If `status === "queued"` AND `age > 15`:
   - `POST /repos/<owner>/<repo>/actions/runs/<id>/cancel` to cancel the stuck run.
   - Wait 5 seconds (give GH time to process the cancel).
   - Trigger a fresh `workflow_dispatch` via the existing `triggerScrape()` helper.
   - Log: `watchdog: stuck run <id> cancelled + new run triggered`.
4. Else (status is in_progress, completed, or queued but < 15 min):
   - Log: `watchdog: run <id> status=<s> age=<m>min — no action`.

The threshold of 15 minutes is a safety margin — typical queue pickup is < 30 seconds, so 15 minutes is unambiguously stuck.

### 3. Edge cases

| Case | Behavior |
|---|---|
| 04:35 watchdog fires before 04:17 cron actually ran (CF Cron Workers occasionally delay) | Latest run is yesterday's success → age >> 24h → not queued → no action. Safe. |
| `GITHUB_TOKEN` missing | Same existing guard as `triggerScrape` — `console.error` and return. |
| GH API error (rate limit, network) | `try/catch` around the fetch. Watchdog logs and exits silently. Daily scrape is unaffected — worst case the stuck run stays stuck and human notices tomorrow. |
| `status === "in_progress"` | Don't touch — runner picked it up, it's working. |
| `status === "completed"` | Don't touch — already done (success or failure both OK from watchdog's POV). |
| `status === "queued"` AND age ≤ 15 min | Normal pickup latency — don't trigger. |
| Multiple stuck runs in a row | Watchdog runs once per day at 04:35. If today's recovery also gets stuck, tomorrow's watchdog catches it. No infinite loop. |
| Watchdog itself triggered a workflow_dispatch and that one gets stuck too | Watchdog fires once daily. The follow-up stuck run would be caught by tomorrow's watchdog. Acceptable. |

### 4. Manual test endpoint

To smoke-test the watchdog without waiting for cron, add a debug endpoint:

```
POST /_watchdog/test
Authorization: Bearer <GITHUB_TOKEN>
```

Same Bearer-token gate as existing `/_cron/trigger`. Runs the watchdog function inline and returns 202.

### 5. Configuration

`wrangler.jsonc` `triggers.crons` array gains the second entry:

```jsonc
"triggers": {
  "crons": ["17 4 * * *", "35 4 * * *"]
}
```

CF Workers supports multiple crons natively; both fire `scheduled(event, env, ctx)` with `event.cron` identifying which one.

## Scope

### In scope

- `watchdog(env)` function in `src/worker.js`.
- Updated `scheduled()` handler to branch on `event.cron`.
- New `/_watchdog/test` endpoint with Bearer-token auth (mirroring existing `/_cron/trigger`).
- Second cron entry in `wrangler.jsonc`.
- README subsection describing the watchdog.

### Out of scope

- Slack / email notifications when watchdog fires (would be useful but adds dependencies).
- More frequent checks (every 5 min throughout the day) — overkill for a once-daily scrape.
- Watchdog for other workflows — we only have `daily-scrape.yml`.
- Migrating away from self-hosted runners (the underlying flakiness root cause).
- Retry-on-failure (different problem — failed runs are visible; stuck runs are silent).
- Tests beyond the manual smoke endpoint — CF Worker tooling for unit tests is heavy for this scope.

## Risks

- **CF Cron Worker scheduling drift.** CF doesn't guarantee precise cron firing — schedules can run minutes late under load. If watchdog fires 30+ minutes after main trigger, a still-pending pickup might be misdiagnosed as stuck. Mitigation: threshold of 15 min (> typical drift) keeps false positives rare; manual restart is harmless if mistaken.
- **GH API rate limits.** Watchdog adds 2-3 API calls per day — trivial against the 5000/hour authenticated limit.
- **Watchdog triggers infinite loop.** Avoided by-design: watchdog fires once daily, not in response to each run state.
- **Race with operator.** If the user is mid-manual-intervention (e.g. cancelling the stuck run by hand) when watchdog fires, both might try to cancel. GH API treats double-cancel as idempotent. Then both might re-trigger → two runs, second queues (concurrency: cancel-in-progress: false in workflow). Mild waste, not breakage.

## Files touched

| Path | Change |
|---|---|
| `src/worker.js` | New `watchdog(env)` function (~40 lines); update `scheduled()` to branch on `event.cron`; new `/_watchdog/test` endpoint (~10 lines) |
| `wrangler.jsonc` | Add second cron entry |
| `README.md` | Subsection describing watchdog cron + manual test endpoint |

**Net:** ~50 lines of JS, 1 JSON line, 5 markdown lines. No new dependencies, no Python changes, no test changes.
