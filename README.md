# HotMap

**A daily treemap of view-growth momentum across the top-500 performers on Pornhub.**

[![Live site](https://img.shields.io/badge/live-hotmap.cam-ff9000?style=flat-square)](https://hotmap.cam)
[![daily scrape](https://img.shields.io/github/actions/workflow/status/ansvier/ph-heatmap/daily-scrape.yml?branch=main&label=daily%20scrape&style=flat-square)](https://github.com/ansvier/ph-heatmap/actions/workflows/daily-scrape.yml)
[![tests](https://img.shields.io/badge/tests-21%20passing-brightgreen?style=flat-square)](#testing)
[![license](https://img.shields.io/badge/data-CC0-blue?style=flat-square)](#license)

🔗 **Live site:** [hotmap.cam](https://hotmap.cam) · 📦 **Raw data:** [hotmap.cam/data.json](https://hotmap.cam/data.json)

---

## What it shows

The site is one interactive page with three tiers of performers, ranked by view-growth momentum rather than raw popularity:

| Mode | Cohort | Best for |
|------|--------|----------|
| **Rising Stars** | Ranks 51–250 (middle-tier) | Spotting next-cohort performers gaining traction |
| **Hidden Gems** | Ranks 251–500 (smaller accounts, 8M–200M views) | Discovery of niche/early performers |
| **Celebrities** | Top 50 by total views | Tracking the established names |

Each tier is sliced by **gender** (All / Female / Male) and **window** (1d / 7d / 30d). The treemap colors performers by percentile rank within the cohort — bright green = running ahead of the pack, red = falling behind. Tile size encodes absolute views gained in the window.

A "Top Performer of the Day" card surfaces the strongest mover for the current cohort. Clicking any tile opens the performer's profile.

## How it works

1. **Daily cron** (`17 4 * * *` UTC) — GitHub Actions runs [`run.py`](run.py).
2. **Scrape** — `scraper.py` paginates the public top-500 list per gender via `curl-cffi` (Chrome TLS impersonation to pass Cloudflare), fetches each profile for exact view counts and avatar URLs.
3. **Store** — `db.py` writes snapshots to SQLite (`data.db`, committed to the repo for full history).
4. **Render** — `heatmap.py` computes per-window growth, applies tier filters, builds 27 precomputed Plotly treemaps (3 modes × 3 genders × 3 windows), and writes the static page.
5. **Deploy** — workflow commits `data.db`, `public/index.html`, `public/data.json`, and any new avatars back to `main`. Cloudflare Pages auto-deploys on push.

Everything runs on free tiers — GitHub Actions (public repo = unlimited minutes), Cloudflare Pages (static hosting), Cloudflare's automatic SSL. The only ongoing cost is the domain (~$15/year).

## Tech stack

- **Python 3.13** — scraper, data, render
- [`curl-cffi`](https://github.com/lexiforest/curl_cffi) — TLS fingerprint impersonation
- [`selectolax`](https://github.com/rushter/selectolax) — fast HTML parsing
- [`pandas`](https://pandas.pydata.org/) — growth-window math
- [`plotly`](https://plotly.com/python/) — treemap rendering
- [`pytest`](https://docs.pytest.org/) — 21 tests, run on every change
- **GitHub Actions** — daily cron + commit/push
- **Cloudflare Pages** — static hosting + CDN + SSL

## Local development

```bash
git clone https://github.com/ansvier/ph-heatmap
cd ph-heatmap
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

./venv/bin/pytest -q                # 21 tests, ~1 sec
./venv/bin/python run.py            # full scrape + render (~40 min for top-500)
open public/index.html              # eyeball locally
```

Environment variables:
- `PH_IMPERSONATE` — `curl-cffi` browser fingerprint. Default `chrome120`. Override (`chrome119`, `chrome116`) if PH starts rejecting that profile.

## Project layout

| Path | Responsibility |
|------|---------------|
| [`run.py`](run.py) | Orchestration: scrape → store → render → dump |
| [`scraper.py`](scraper.py) | HTTP + paginated top-list + profile parsing + avatar extraction |
| [`db.py`](db.py) | SQLite schema, migrations, and queries |
| [`heatmap.py`](heatmap.py) | Tier filters + treemap figures + page template + JSON dump |
| [`public/`](public/) | Static site served by Cloudflare Pages |
| [`public/avatars/`](public/avatars/) | Cached performer avatars (PH blocks hotlinking) |
| [`data.db`](data.db) | SQLite store of all daily snapshots |
| [`.github/workflows/daily-scrape.yml`](.github/workflows/daily-scrape.yml) | Cron + commit/push automation |
| [`tests/`](tests/) | Pytest suite covering db, scraper, render, and growth math |

## Troubleshooting

- **403 on scrape:** Cloudflare/PH is rejecting the GH runner's TLS fingerprint. Set a repo variable `PH_IMPERSONATE=chrome119` (or `chrome116`) in Settings → Secrets and variables → Actions → Variables.
- **`Could not find 'Video Views'`:** PH changed profile markup. Inspect a profile in browser, update `_extract_video_views` in `scraper.py`. Current parser reads `<div class="videoViews" data-title="Video views: 123,456">`.
- **Avatars missing on a tile:** PH layouts differ; `_extract_photo_url` falls back through `#getAvatar` and `.topProfileHeader img`. New profiles may need a parser tweak.
- **Workflow didn't fire on schedule:** GH cron can be delayed during peak hours. We use `:17` minute to avoid the busy round-hour slot. Manual trigger via Actions tab if needed.

## Data

Snapshot rows are published as JSON at [`/data.json`](https://hotmap.cam/data.json). Each row:

```json
{
  "snapshot_date": "2026-05-28",
  "slug": "lana-rhoades",
  "name": "Lana Rhoades",
  "total_views": 2123456789,
  "rank": 11,
  "gender": "female"
}
```

Free to use under [CC0](https://creativecommons.org/publicdomain/zero/1.0/). Attribution appreciated but not required. If you build something interesting, let me know.

## Disclaimer

HotMap is an independent analytics project. Data is collected from publicly visible Pornhub profile pages via polite (1.5s jittered) scraping. No video content is hosted here. No affiliation with Pornhub or any performer.
