# HotMap — Product Design

**Status:** approved 2026-05-27
**Predecessor spec:** [2026-05-27-ph-heatmap-design.md](2026-05-27-ph-heatmap-design.md)

## Summary

Turn the existing local `ph-heatmap` CLI into a public website, **HotMap**, showing a daily-refreshed heatmap of day-over-day view growth for the top-50 Most Viewed Pornstars on Pornhub.

Architecture is intentionally minimal: GitHub Actions runs the scraper daily, commits artifacts back to the same repo, Cloudflare Pages serves the static `public/` directory. No backend, no SPA framework, no external storage.

## Architecture

```
GitHub Actions (cron 04:00 UTC)
        │
        │  python run.py
        ▼
scraper (run.py)
  • fetches top-50 from Pornhub
  • updates data.db (SQLite, repo root)
  • re-renders public/index.html
  • dumps public/data.json
        │
        │  git commit + git push origin main
        ▼
GitHub repo: ansvier/ph-heatmap, branch main
        │
        │  Cloudflare Pages watches main, build output: public/
        ▼
Cloudflare CDN serves https://ph-heatmap.pages.dev (or custom domain)
```

Single branch. Single repo. Single workflow. Zero secrets (workflow uses built-in `GITHUB_TOKEN`).

## Brand

**Name:** HotMap

**Logo:** "HOT" (white sans-serif) followed by "MAP" (black sans-serif on rounded orange pill), on a black background. Implemented as inline SVG in the page template so it (a) renders crisp at any DPI, (b) requires no extra HTTP request, (c) is editable as code.

Faithful SVG reference (to be inlined in the page template):

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 120" role="img" aria-label="HotMap">
  <rect width="480" height="120" fill="#000"/>
  <text x="20" y="92" font-family="-apple-system, Helvetica, Arial, sans-serif"
        font-weight="900" font-size="92" fill="#fff" letter-spacing="-2">HOT</text>
  <rect x="245" y="20" width="220" height="80" rx="16" fill="#ff9000"/>
  <text x="262" y="84" font-family="-apple-system, Helvetica, Arial, sans-serif"
        font-weight="900" font-size="76" fill="#000" letter-spacing="-2">MAP</text>
</svg>
```

(Exact metrics tunable during implementation; this is the structural spec.)

## Page layout

Single HTML page at `public/index.html`. Sections:

1. **Header** — HotMap logo (SVG, ~200px wide), one-line subtitle: *Daily view-growth heatmap of Pornhub's top-50 performers.*
2. **Description** — 1-2 sentences explaining what the colors mean. Brighter = faster growth in cumulative video views from yesterday to today.
3. **Heatmap** — the Plotly figure (current `compute_growth_matrix` + `render_heatmap`, unchanged math, unchanged colorscale `YlOrRd`).
4. **Footer** — last updated timestamp, days of history, performers tracked, link to GitHub source, disclaimer ("data collected from publicly visible profile pages; no video content is hosted here"), `HotMap is an independent project.`

CSS is inline `<style>` in the template (no external stylesheets):
- Body: system font stack, `max-width: 1100px`, centered, generous padding on mobile.
- Background: `#fff`; logo header has its own black background as part of the SVG.
- Footer: small, gray, with link styling matching brand orange `#ff9000` on hover.

The full HTML template lives as a string constant `_PAGE_TEMPLATE` in `heatmap.py` and is filled via `str.format()` with these placeholders:
- `{PLOT_DIV}` — Plotly's `figure.to_html(full_html=False, include_plotlyjs="cdn")` output
- `{LAST_UPDATED_UTC}` — `datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")`
- `{N_DAYS}` — `growth.shape[1]`
- `{N_PERFORMERS}` — `growth.shape[0]`

## Data layout in repo

```
ph-heatmap/                       # repo root
├── run.py                        # orchestration (unchanged structure)
├── scraper.py                    # HTTP + parsing (unchanged)
├── db.py                         # SQLite (unchanged)
├── heatmap.py                    # template + render + json dump (modified)
├── data.db                       # NOT gitignored anymore; committed daily
├── public/                       # served by Cloudflare Pages
│   ├── index.html                # generated on every run
│   └── data.json                 # raw snapshot dump
├── tests/...
├── .github/workflows/daily-scrape.yml
├── docs/superpowers/...
├── requirements.txt
├── README.md
└── .gitignore
```

`.gitignore` removes `data.db` and `heatmap.html` lines. Adds nothing new.

## GitHub Actions workflow

Path: `.github/workflows/daily-scrape.yml`

```yaml
name: daily scrape

on:
  schedule:
    - cron: "0 4 * * *"
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: daily-scrape
  cancel-in-progress: false

jobs:
  scrape:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
          cache: pip
      - run: pip install -r requirements.txt
      - name: Run scraper
        env:
          PYTHONUNBUFFERED: "1"
          PH_IMPERSONATE: ${{ vars.PH_IMPERSONATE || 'chrome120' }}
        run: python run.py
      - name: Commit and push artifacts
        run: |
          git config user.name "hotmap-bot"
          git config user.email "hotmap-bot@users.noreply.github.com"
          git add data.db public/
          if git diff --cached --quiet; then
            echo "No changes to commit"
            exit 0
          fi
          git commit -m "chore(data): daily snapshot $(date -u +%Y-%m-%d)"
          git pull --rebase origin main
          git push
```

Notes:
- `PH_IMPERSONATE` env override is a free hedge against future Cloudflare TLS-fingerprint blocks.
- `git pull --rebase` before push handles the case where a human pushed to main while the action was running.
- `concurrency` prevents overlapping runs from racing.

## Cloudflare Pages binding (one-time manual setup)

Steps (done by user after MVP is implemented):
1. dash.cloudflare.com → Workers & Pages → Create → Pages → Connect to Git → select `ansvier/ph-heatmap`.
2. Build settings:
   - Framework preset: **None**
   - Build command: *(empty)*
   - Build output directory: `public`
   - Root directory: *(empty)*
3. Production branch: `main`
4. Deploy. Site is live at `https://ph-heatmap.pages.dev` within ~30s.
5. (Optional) Custom domain wired via Pages → Custom domains → CNAME.

No CLI is provided by Cloudflare for this step; it stays a manual one-time setup.

## Code changes (delta from current state)

**`heatmap.py`:**
- Add `_PAGE_TEMPLATE` HTML string constant (logo SVG + structure above).
- Modify `render_heatmap(snapshots, output_path)`:
  - Generate plot via `figure.to_html(include_plotlyjs="cdn", full_html=False)`.
  - Compute `last_updated`, `n_days`, `n_performers` from `growth` matrix.
  - Write `_PAGE_TEMPLATE.format(...)` to `output_path`.
- Add `dump_json(snapshots, output_path)` that writes snapshot rows as JSON array with ISO date strings.

**`run.py`:**
- Replace `HTML_PATH = PROJECT_ROOT / "heatmap.html"` with:
  - `PUBLIC_DIR = PROJECT_ROOT / "public"`
  - `HTML_PATH = PUBLIC_DIR / "index.html"`
  - `JSON_PATH = PUBLIC_DIR / "data.json"`
- `PUBLIC_DIR.mkdir(exist_ok=True)` before write.
- Call `dump_json(snapshots_df, JSON_PATH)` after `render_heatmap`.

**`scraper.py`:**
- Replace `_IMPERSONATE = "chrome120"` with `_IMPERSONATE = os.environ.get("PH_IMPERSONATE", "chrome120")` and `import os`.

**`.gitignore`:**
- Remove `data.db` and `heatmap.html` lines.

**`tests/test_heatmap.py`:**
- Extend `test_render_heatmap_writes_html` to assert presence of `"HotMap"`, `"<svg"`, `"<footer"`, `"Pornhub"`.
- Add `test_dump_json_round_trip(tmp_path)` writing then re-reading the JSON.

**`.github/workflows/daily-scrape.yml`:** new file per spec above.

**`README.md`:**
- Rename top heading to `# HotMap`.
- Add public site URL section.
- Replace local-cron section with a pointer to the workflow file.
- Add Cloudflare Pages setup section.

Estimated diff: ~120 lines added (mostly HTML template), ~15 lines modified, 1 new file (the workflow).

## Failure modes and mitigation

| Failure | Detection | Mitigation |
|---|---|---|
| Cloudflare 403 against GH runner | `run.py` exits 1, action fails | Manual `workflow_dispatch` with `PH_IMPERSONATE=chrome119`; if persistent, add residential proxy via `HTTPS_PROXY` secret (deferred until first occurrence) |
| Top-list returns < 50 slugs | Logged in `run.py` | Save what was returned, continue |
| Individual profile 404 | `WARN: skipping <slug>` | NaN cell in heatmap, no failure |
| Empty result set | `run.py` exits 1 | Action fails, no commit, site stays at yesterday's state |
| Pornhub HTML layout change | All profile parses fail → exit 1 | Workflow failure notification (built-in GH email); operator updates `_extract_video_views` |
| Concurrent push from human + bot | `git push` non-fast-forward | `git pull --rebase origin main` handles it; bad rebase logs and skips this run |
| Corrupted `data.db` | `pd.read_sql_query` raises | `git revert <bad-commit>` |
| Cloudflare Pages build fails | Email from CF | Previous build remains served; no user impact |

## Out of scope (explicit YAGNI)

- Backend (FastAPI, etc.) — static is sufficient.
- SPA framework (React/Next/etc.) — Plotly is already self-contained.
- `/about`, `/history`, `/api` separate pages — single-page is enough for v1.
- `data.csv` alongside `data.json` — add if requested.
- Dark mode — Plotly is responsive enough; add if requested.
- User accounts, auth, billing — not a SaaS.
- Multiple platforms (xvideos, etc.) — single-source for now.
- Notifications (Telegram bot pinging on top-mover) — could be a fun follow-up.

## Acceptance criteria

1. Pushing to `main` causes Cloudflare Pages to redeploy with the new HTML.
2. The scheduled workflow runs at 04:00 UTC, completes within 15 minutes, and produces a commit `chore(data): daily snapshot YYYY-MM-DD`.
3. Visiting the deployed URL shows the HotMap logo, the heatmap, and a footer with the correct "last updated" timestamp.
4. `https://<site>/data.json` returns a parseable JSON array of snapshot rows.
5. Existing 13 pytest tests still pass; 2-3 new tests added for the template and JSON dump.
