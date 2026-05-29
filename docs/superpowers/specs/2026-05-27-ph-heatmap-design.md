# ph-heatmap — Design

**Date:** 2026-05-27
**Status:** Approved, ready for implementation planning

## Goal

Daily-snapshot heatmap of view-count growth across the top-50 most-viewed pornstars on Pornhub. Each cell shows day-over-day percentage growth in an actress's cumulative "Video Views" counter. The output is a single interactive HTML file that updates after each scheduled run.

## Scope

In scope:
- One scraper that grabs the current top-50 list from the site's "Most Viewed Pornstars" page and the per-profile `Video Views` counter.
- SQLite storage of all snapshots (no deletion of historical data).
- Static HTML heatmap regenerated on every run.
- Cron-friendly entry point.

Out of scope:
- Categories, tags, videos, or any axis other than actress × date.
- Web UI / server / filtering controls.
- Historical backfill — the dataset begins at first run.
- Notifications, alerts, or trend detection beyond the visual heatmap.

## Data model

Single table:

```sql
CREATE TABLE snapshots (
    snapshot_date TEXT NOT NULL,    -- ISO date, one row per (date, slug)
    slug          TEXT NOT NULL,    -- stable identifier from profile URL
    name          TEXT NOT NULL,    -- display name (may change over time)
    total_views   INTEGER NOT NULL, -- cumulative Video Views from profile
    rank          INTEGER NOT NULL, -- 1..50 within that snapshot
    PRIMARY KEY (snapshot_date, slug)
);
```

`slug` is the identity (URL slugs are stable; display names can be edited by the site/actress). `name` is stored each time so the latest is available for rendering.

## Architecture

```
ph-heatmap/
├── run.py            # entry point: scrape → store → render
├── scraper.py        # top-list fetch + profile parse
├── db.py             # SQLite open/migrate/insert/query
├── heatmap.py        # build dataframe, render plotly HTML
├── data.db           # SQLite, created on first run
├── heatmap.html      # rendered output
├── requirements.txt
└── README.md
```

Four small modules, each independently testable:

- **scraper.py**: pure I/O against the site. Exposes `fetch_top_pornstars() -> list[Pornstar]` and `fetch_total_views(slug) -> int`. Handles HTTP, parsing, retries.
- **db.py**: thin SQLite wrapper. `init_db()`, `insert_snapshot(rows)`, `load_all_snapshots() -> DataFrame`. No business logic.
- **heatmap.py**: pure transform + render. Takes the DataFrame, computes day-over-day deltas, emits `heatmap.html` via Plotly.
- **run.py**: orchestration only. Sequence: init db → fetch top-list → for each actress fetch profile views → insert snapshot → render heatmap.

## Scraping approach

**Library:** `curl-cffi` with Chrome TLS impersonation (`impersonate="chrome120"`). Pornhub sits behind Cloudflare and rejects vanilla Python HTTP clients on TLS fingerprint; `curl-cffi` is the cheapest workaround that still uses plain HTTP semantics.

**Fallback (not implemented up front):** if `curl-cffi` starts failing, swap `scraper.py` for a Playwright-based version. The module boundary is designed to make this a localized change.

**Targets:**
- Top list: `https://www.pornhub.com/pornstars?o=mv` (Most Viewed, default sort).
- Profile: `https://www.pornhub.com/pornstar/<slug>` — the page contains a `Video Views` figure in the bio sidebar; parse with `selectolax` (fast, lenient).

**Throttling:** 1.5 s sleep between profile requests, jittered ±0.5 s. One User-Agent string per run, matched to the impersonated Chrome version. Single sequential pass — no concurrency.

**Total runtime:** ~1.5 minutes per run (50 profiles × ~1.8 s).

## Error handling

- **Profile fetch/parse fails for one actress:** log to stderr with slug, skip that row, continue. The snapshot for that day will have <50 rows; the heatmap renders the missing cell as a gap.
- **Top-list fetch fails entirely:** exit with non-zero status. Cron's MAILTO will surface this. No partial snapshot is written.
- **DB write fails:** exit non-zero, no heatmap regen. The previous `heatmap.html` stays valid.
- **Plotly render fails:** snapshot is already persisted; log and exit non-zero. Next run will pick up.

No automatic retries within a run — if Cloudflare is blocking us today, retrying won't help and just makes us look more like a bot. Cron will try again tomorrow.

## Heatmap rendering

- **X axis:** snapshot dates (chronological, left to right).
- **Y axis:** union of all slugs ever seen in any snapshot. Sorted by `total_views` from the most recent snapshot, descending. Slugs not seen in the latest snapshot fall to the bottom.
- **Cell value:** `(total_views[d] - total_views[d-1]) / total_views[d-1] * 100`, computed per slug.
- **Missing data:** if a slug is absent from snapshot `d` or `d-1`, the cell at `d` is NaN → rendered as a neutral grey gap.
- **Color scale:** sequential warm scale (e.g. `Plasma` or `YlOrRd`), 0% = light, higher = darker. No diverging scale — `total_views` is monotonic, deltas are ≥ 0 modulo site corrections.
- **Hover tooltip:** display name, date, absolute `total_views`, absolute delta, percentage delta.
- **Output:** standalone `heatmap.html` via `plotly.offline.plot(..., include_plotlyjs="cdn")`. Open the file directly in a browser.

## Run schedule

Cron, daily at 04:00 local time (low-traffic window for the site):

```
0 4 * * * cd /path/to/ph-heatmap && ./venv/bin/python run.py >> run.log 2>&1
```

First run produces a single snapshot and a heatmap with no colored cells (no prior snapshot to diff against). Second run is the first one that shows growth.

## Dependencies

```
curl-cffi
selectolax
plotly
pandas
```

No test framework chosen yet — leave that for the implementation plan.

## Open risks

1. **Cloudflare escalation.** If they tighten checks (JS challenge, hCaptcha), `curl-cffi` stops working and we move to Playwright. Mitigation: keep `scraper.py` behind a narrow interface so the swap is local.
2. **Profile page layout change.** The CSS selector for `Video Views` may shift. Mitigation: parser failures are per-actress, surfaced in logs; we'll notice within a day.
3. **Site ToS / robots.** Personal-use, low-volume, throttled scraping of public pages. We respect `robots.txt` for the top-list and profile paths; if either is disallowed, the project stops.

## Success criteria

- After 7+ daily runs, opening `heatmap.html` shows a populated heatmap with one column per day and rows for ~50–80 distinct actresses.
- A run that hits an empty/blocked top-list page exits non-zero and leaves DB and HTML untouched.
- Adding a new column on day N+1 takes under 3 minutes wall-clock from cron trigger to file write.
