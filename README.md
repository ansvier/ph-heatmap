# HotMap

A daily-refreshed heatmap of day-over-day view growth for the top-50 Most Viewed Pornstars on Pornhub.

**Live site:** https://hotmap.cam

## How it works

1. A GitHub Actions cron job runs `python run.py` at 04:00 UTC daily.
2. The script scrapes the public top-50 list and each performer's profile page, stores cumulative `Video views` in `data.db` (SQLite, one row per `(date, slug)`).
3. It regenerates `public/index.html` (Plotly heatmap wrapped in the HotMap page template) and `public/data.json` (raw snapshot dump).
4. Action commits `data.db` and `public/` to `main`.
5. Cloudflare Pages watches `main` and redeploys the static site.

## Local development

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/pytest -v               # 15 tests
./venv/bin/python run.py           # one full scrape + render
open public/index.html             # eyeball the result
```

Environment variables:
- `PH_IMPERSONATE` — `curl-cffi` browser fingerprint. Default `chrome120`. Override if Cloudflare starts rejecting that profile.

## Deployment

### GitHub Actions (scraper)

Already configured at [.github/workflows/daily-scrape.yml](.github/workflows/daily-scrape.yml). Schedule: `17 4 * * *` UTC (off the round-hour to avoid GitHub's scheduler congestion), plus manual trigger via the Actions tab.

To override the curl-cffi fingerprint at the workflow level:
Settings → Secrets and variables → Actions → Variables → add `PH_IMPERSONATE`.

### Cloudflare Pages (web hosting)

One-time setup in the Cloudflare dashboard:

1. **Workers & Pages** → **Create** → **Pages** → **Connect to Git**.
2. Authorize Cloudflare on your GitHub account, then pick `ansvier/ph-heatmap`.
3. Build settings:
   - **Framework preset:** `None`
   - **Build command:** (leave blank)
   - **Build output directory:** `public`
   - **Root directory:** (leave blank)
4. **Production branch:** `main`.
5. **Save and Deploy.** First deploy completes in ~30 seconds at `https://ph-heatmap.pages.dev`.
6. (Optional) **Custom domains** → add a CNAME for your own domain.

Every subsequent push to `main` (including the daily scraper commits) triggers an auto-redeploy.

## Project layout

| File | Responsibility |
|------|----------------|
| `run.py` | Orchestration: scrape → store → render → dump |
| `scraper.py` | HTTP via `curl-cffi` + HTML parsing via `selectolax` |
| `db.py` | SQLite schema and queries |
| `heatmap.py` | Growth-matrix math + HotMap page template + Plotly figure + JSON dump |
| `public/` | Static site served by Cloudflare Pages |
| `data.db` | SQLite store of all daily snapshots, committed to the repo |
| `.github/workflows/daily-scrape.yml` | GH Actions cron + commit/push job |

## Troubleshooting

- **Workflow fails with 403 on scrape step:** Cloudflare is rejecting the GH-runner IP/TLS fingerprint. Add a repo variable `PH_IMPERSONATE=chrome119` (or `chrome116`) and re-run. If still blocked, switch to a self-hosted runner or add a residential proxy via `HTTPS_PROXY` secret.
- **`Could not find 'Video Views'` ValueError:** Pornhub changed the profile-page markup. Fetch one profile in a browser, inspect the new structure, and update `_extract_video_views` in `scraper.py`. The current parser reads from `<div class="videoViews" data-title="Video views: 123,456">`.
- **Heatmap is mostly blank:** First column is always blank (no prior day to diff against). After 2+ days you should see colored cells. If still blank, check action logs for `WARN: skipping <slug>` lines — those rows go in as NaN.
- **Pages deploy is stale:** Cloudflare caches for ~1 minute. Hard-refresh, or check the Pages dashboard for the latest deploy status.

## Disclaimer

HotMap is an independent project. Data is collected from publicly visible Pornhub profile pages; no video content is hosted here.
