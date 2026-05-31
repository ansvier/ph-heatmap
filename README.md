# HotMap

**A daily treemap of view-growth momentum across the top-500 performers on Pornhub.**

[![Live site](https://img.shields.io/badge/live-hotmap.cam-ff9000?style=flat-square)](https://hotmap.cam)
[![daily scrape](https://img.shields.io/github/actions/workflow/status/ansvier/ph-heatmap/daily-scrape.yml?branch=main&label=daily%20scrape&style=flat-square)](https://github.com/ansvier/ph-heatmap/actions/workflows/daily-scrape.yml)
[![tests](https://img.shields.io/badge/tests-26%20passing-brightgreen?style=flat-square)](#testing)
[![license](https://img.shields.io/badge/data-CC0-blue?style=flat-square)](#license)

🔗 **Live site:** [hotmap.cam](https://hotmap.cam) · 📦 **Raw data:** [hotmap.cam/data.json](https://hotmap.cam/data.json)

---

## Pages

| URL | What |
|------|------|
| [`/`](https://hotmap.cam) (also `/rising`) | Treemap, default view (Rising Stars × Female × 1d) |
| [`/gems`](https://hotmap.cam/gems) | Hidden Gems tier (ranks 251–500) pre-selected |
| [`/celebs`](https://hotmap.cam/celebs) | Celebrities tier (top 50 by views) pre-selected |
| [`/stats`](https://hotmap.cam/stats) | Single-page summary: hero numbers + biggest mover + leaderboards (female-focused) |
| [`/charts`](https://hotmap.cam/charts) | A–Z performer index with search + gender filter |
| [`/p/<slug>`](https://hotmap.cam/p/lana-rhoades) | Per-performer page with sparkline + 1d/7d/30d growth + share buttons |
| `/r/<slug>` | CF Worker outbound redirect (click tracking, future affiliate slot) |
| [`/data.json`](https://hotmap.cam/data.json) | Full snapshot dataset, CC0 |
| [`/sitemap.xml`](https://hotmap.cam/sitemap.xml) | All 874+ URLs for search engines |

## What the treemap shows

Three tiers of performers, ranked by view-growth momentum rather than raw popularity:

| Mode | Cohort | Best for |
|------|--------|----------|
| **Rising Stars** | Ranks 51–250 (middle-tier) | Spotting next-cohort performers gaining traction |
| **Hidden Gems** | Ranks 251–500 (smaller accounts) | Discovery of niche / early performers |
| **Celebrities** | Top 50 by total views | Tracking the established names |

Each tier is sliced by **gender** (All / Female / Male) and **window** (1d / 7d / 30d). The treemap colors performers by percentile rank within the cohort — bright green = running ahead of the pack, red = falling behind. Tile size encodes **% view growth** over the window (performers with under 1M baseline views are filtered out to keep the visual focused on meaningful movers). Hover any tile to see both the absolute and percent numbers.

A "Top Performer of the Day" card surfaces the strongest mover for the current cohort. Clicking any tile opens the performer's profile (via tracked `/r/<slug>` redirect).

## How it works

1. **Daily cron** (`17 4 * * *` UTC) — GitHub Actions runs [`run.py`](run.py).
2. **Scrape** — `scraper.py` paginates the top-500 list per gender via `curl-cffi` (Chrome TLS impersonation to pass Cloudflare), fetches each profile for exact view counts and avatar URLs, with retry + auto-backfill for transient failures.
3. **Store** — `db.py` writes snapshots to SQLite (`data.db`, committed to the repo for full history).
4. **Render** — `heatmap.py` computes per-window growth, builds 27 precomputed Plotly treemaps (3 modes × 3 genders × 3 windows), the stats and charts pages, and a per-performer page for every slug ever seen.
5. **Deploy** — workflow commits artifacts back to `main`. Cloudflare Pages auto-deploys on push; the Worker handles `/r/<slug>` outbound redirects.

Everything runs on free tiers — GitHub Actions (public repo = unlimited minutes), Cloudflare Pages + Worker (static + edge logic), Cloudflare's automatic SSL. The only ongoing cost is the domain (~$15/year).

**SEO:** Every rendered page emits a complete head block — title, meta description, canonical, Open Graph quintet, Twitter Cards triple, robots meta, and JSON-LD (`WebSite` + `BreadcrumbList` + page-specific `Dataset` / `Person` / `CollectionPage`). Default OG image is `/og.png` (1200×630); per-performer and stats pages use avatar fallbacks. Sitemap submitted to Google Search Console and Bing Webmaster Tools (Yandex skipped — not targeting RF). See [`docs/seo-submission-checklist.md`](docs/seo-submission-checklist.md) for the submission steps.

## Tech stack

- **Python 3.13** — scraper, data, render
- [`curl-cffi`](https://github.com/lexiforest/curl_cffi) — TLS fingerprint impersonation
- [`selectolax`](https://github.com/rushter/selectolax) — fast HTML parsing
- [`pandas`](https://pandas.pydata.org/) — growth-window math
- [`plotly`](https://plotly.com/python/) — treemap and sparkline rendering
- [`pytest`](https://docs.pytest.org/) — 26 tests
- **Cloudflare Workers** — `/r/<slug>` outbound redirect with click logging
- **GitHub Actions** — daily cron + commit/push
- **Cloudflare Pages** — static hosting + CDN + SSL

## Local development

```bash
git clone https://github.com/ansvier/ph-heatmap
cd ph-heatmap
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

./venv/bin/pytest -q                # 26 tests, ~1 sec
./venv/bin/python run.py            # full scrape + render (~40 min for top-500)
open public/index.html              # eyeball locally
```

Environment variables:
- `PH_IMPERSONATE` — `curl-cffi` browser fingerprint. Default `chrome120`. Override (`chrome119`, `chrome116`) if PH starts rejecting that profile.

If HotMap branding changes (logo, tagline, color), regenerate the default Open Graph image:

```bash
./venv/bin/python scripts/build_og.py   # rewrites public/og.png (1200×630)
```

## Project layout

| Path | Responsibility |
|------|---------------|
| [`run.py`](run.py) | Orchestration: scrape → store → render every page → dump |
| [`scraper.py`](scraper.py) | HTTP + paginated top-list + profile + avatar parsing |
| [`db.py`](db.py) | SQLite schema, migrations, queries |
| [`heatmap.py`](heatmap.py) | Tier filters + treemap + stats + charts + performer page templates |
| [`src/worker.js`](src/worker.js) | Cloudflare Worker — `/r/<slug>` redirect with click logging |
| [`wrangler.jsonc`](wrangler.jsonc) | Worker / Pages configuration |
| [`public/`](public/) | Static site served by Cloudflare Pages |
| [`public/avatars/`](public/avatars/) | Cached performer avatars (PH blocks hotlinking) |
| [`data.db`](data.db) | SQLite store of all daily snapshots, committed to the repo |
| [`.github/workflows/daily-scrape.yml`](.github/workflows/daily-scrape.yml) | Cron + commit/push automation |
| [`tests/`](tests/) | Pytest suite covering db, scraper, render, and growth math |

## Troubleshooting

- **403 on scrape:** Cloudflare/PH is rejecting the GH runner's TLS fingerprint. Set a repo variable `PH_IMPERSONATE=chrome119` (or `chrome116`) in Settings → Secrets and variables → Actions → Variables.
- **`Could not find 'Video Views'`:** PH changed profile markup. Inspect a profile in browser, update `_extract_video_views` in `scraper.py`.
- **Avatars missing on a tile:** PH layouts differ; `_extract_photo_url` falls back through `#getAvatar` and `.topProfileHeader img`. The next daily run auto-backfills NULL `photo_url` rows.
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
