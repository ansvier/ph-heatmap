# Trending Categories — design

**Status:** approved
**Date:** 2026-06-01
**Author:** ansvier + claude

## Problem

The site indexes individual performers and their view-growth momentum. There's no surface for the **other** half of the underlying data — categories themselves. Users searching "what kind of porn is trending" find Pornhub itself, never us. We have no analytical lens on category-level dynamics.

A previous attempt (Categories v1) failed because PH doesn't expose per-performer-category metadata. Tonight we discovered that PH's `/categories` page embeds a full JSON catalog of ~189 categories with real, non-capped video counts. One HTTP GET per day captures the full snapshot. This unblocks a different (and arguably more interesting) product: track which categories are accumulating videos fastest.

## Goal

A daily-updated `/categories/` page showing all ~189 PH categories as a treemap. Tile size encodes total `video_count`. Tile color encodes today's growth rate. After ~7 days of accumulated history, the page tells a real story: which categories are accelerating, which are flat, which are declining (videos getting removed faster than added).

## Decision

### 1. Data source

- **URL:** `https://www.pornhub.com/categories` (a single GET, ~880 KB HTML).
- **Format:** embedded JSON blobs of shape `{"id":..., "name":..., "slug":..., "video_count":..., "points":..., "status":...}`. Verified ~189 hits per page across 36 reconnaissance fetches.
- **Cost:** 1 request/day. No per-category fetches. No proxy / rate-limit risk beyond what daily-scrape already absorbs.
- **`video_count` is real and uncapped** (verified examples: MILF 199,835; Anal 142,217; 18-25 289,620; Big Tits 305,412; Hentai 24,655). Not the `20000` display cap that appeared on `/categories/<slug>` listings.

### 2. Storage

New SQLite table `category_snapshots`, parallel to existing `snapshots`:

```sql
CREATE TABLE category_snapshots (
    snapshot_date  TEXT    NOT NULL,
    category_id    INTEGER NOT NULL,
    slug           TEXT    NOT NULL,
    name           TEXT    NOT NULL,
    video_count    INTEGER NOT NULL,
    points         INTEGER,
    PRIMARY KEY (snapshot_date, category_id)
);
CREATE INDEX idx_cs_date     ON category_snapshots(snapshot_date);
CREATE INDEX idx_cs_category ON category_snapshots(category_id);
```

- `category_id` is PH's stable internal identifier — primary key over `slug` because slugs can change.
- `INSERT OR REPLACE` semantics for daily upsert.
- `points` is reserved for future use (PH's popularity metric); we store it but don't render it in v1.
- New `CategorySnapshot` frozen dataclass in `db.py` parallel to `Snapshot`.

### 3. Scraper

In `scraper.py`:

```python
def parse_category_catalog(html: str) -> list[dict]:
    """Extract [{id, slug, name, video_count, points}, ...] from embedded
    JSON on PH's /categories page. Deduplicates by id. Filters to status=='active'."""

def fetch_category_catalog() -> list[dict]:
    """One GET to https://www.pornhub.com/categories + parse."""
```

- Regex-based JSON extraction (the catalog blobs are isolatable as standalone JSON objects).
- Defensive dedup by `id` — the page rendered with duplicates in cross-category panels.
- Filter on `status == "active"` to skip soft-deleted categories.

### 4. Daily integration

In `run.py`, **prepend** a 5-line block before the existing performer scrape:

```python
categories = fetch_category_catalog()
print(f"fetched {len(categories)} categories", flush=True)
insert_category_snapshot(conn, today, categories)
```

- ~5 seconds total. Doesn't affect the ~45-minute performer flow.
- If `fetch_category_catalog` raises or returns empty: log WARN, continue to performer scrape. One missing day is acceptable.

### 5. Render

New function in `heatmap.py`:

```python
def render_categories_treemap(
    category_snapshots: pd.DataFrame,
    output_path: Path | str,
) -> None:
```

- **Tile size** = `video_count` from latest snapshot.
- **Tile color** = percentile rank of 1-day growth (today_count − yesterday_count). When yesterday's snapshot is missing (first day), color is neutral grey.
- **Tile label** = three lines: `Name`, `count` (compact e.g. "199K"), `+delta today` or `—` when no baseline.
- **Hover** = name, full count, absolute and percentage delta.

The visual reuses the existing `_build_treemap_figure` pattern. New constants (a categories-specific `_CATEGORIES_PAGE_TEMPLATE`) house the page chrome.

### 6. UI on `/categories/`

```
HotMap nav (+ Categories item)
─────────────────────────────────────
Trending categories on Pornhub
189 categories tracked · Updated XX:XX UTC

[Treemap — full width]

Footer
```

- No toggle (1d/7d/30d).
- No mode/gender filter.
- No share button (MVP).
- No per-category pages (deferred).

### 7. SEO

- New `page_type="category"` in `_OG_TYPE_BY_PAGE_TYPE` (→ `og:type="website"`) and `Literal` annotation.
- Title: `Trending Pornhub Categories — Daily Growth Heatmap | HotMap`.
- Meta description: `N PH categories ranked by daily video-count growth. Real numbers, updated automatically.` (N filled at render time.)
- Breadcrumbs: `HotMap → Categories`.
- JSON-LD: `CollectionPage` + `BreadcrumbList` via `_render_seo_head`.
- Canonical: `https://hotmap.cam/categories/` (trailing slash).

### 8. Nav + sitemap

- `_NAV_ITEMS` gains `("categories", "/categories/", "Categories")` between Stats and Charts.
- `write_sitemap_and_robots` emits `<loc>https://hotmap.cam/categories/</loc>`.

### 9. Bootstrap

To avoid showing a "no growth data" page on first deploy, the implementation runs `fetch_category_catalog()` + `insert_category_snapshot()` **once as an explicit pre-push step** (immediately before the E2E re-render and push commit). This writes today's snapshot to `data.db` so the deployed page already shows real counts. The first daily-scrape (tomorrow 04:17 UTC) writes the second snapshot. By tomorrow ~05:00 UTC the page renders with real 1-day deltas.

## Scope

### In scope

- `parse_category_catalog` + `fetch_category_catalog` in scraper.
- `category_snapshots` table + dataclass + insert/load helpers in db.
- `render_categories_treemap` in heatmap.
- `page_type="category"` + nav entry + sitemap entry.
- `run.py` integration (5 lines).
- 6 new tests (2 scraper + 2 db + 2 heatmap).
- HTML fixture from real `/categories` HTML.
- Bootstrap snapshot during implementation.
- README subsection.

### Out of scope

- Per-category landing pages (`/c/<slug>/`).
- Cross-link from `/p/<slug>` to categories.
- Toggle UI (1d/7d/30d).
- Sparklines / history charts on the page.
- Search / filter UI on `/categories/`.
- Per-category leaderboards or stats.
- Spike-of-the-Day card for categories.
- Using the `points` field for display (stored but not rendered).
- Performer×category junction (the failed Categories v1 approach).

## Edge cases

- **First day post-deploy** — no baseline → all tiles neutral grey, deltas show `—`. Honest empty state, not a bug.
- **Category disappears from PH** (deleted / renamed) — absent from today's snapshot → just doesn't appear in today's treemap. History rows retained.
- **`points` field absent in some JSON blobs** — store as NULL. Doesn't affect rendering.
- **PH HTML structure change breaks regex** — parser returns empty list. `run.py` logs WARN, continues with performer scrape. The category-snapshot table simply misses a day; render still works against prior data if any.
- **Category with `video_count` order-of-magnitude larger** than others (e.g. 18-25 at 25M vs Virtual Reality at 4.6K) — Plotly Treemap handles this fine; the small ones become tiny tiles but stay visible. Log-scale option deferred to v2.
- **Duplicate category objects in HTML** (PH renders cross-category panels) — dedup by `id` in `parse_category_catalog`.
- **0 categories returned** — `render_categories_treemap` raises `ValueError` (caller handles by skipping render that day, matching the existing pattern in other renderers).

## Risks

- **PH changes the embedded JSON shape.** Mitigation: parser pinned by an HTML fixture test. If real /categories changes, the test fails, we fix the parser. Tracking via the WARN log in production.
- **Tile labels overflow on narrow tiles** for long category names (e.g. `Popular With Women`). Plotly truncates with ellipsis — acceptable for v1.
- **Day-to-day delta is tiny in absolute terms** (~10-100 videos out of 200K = +0.005%). Color encoding (percentile rank within today's cohort) keeps the visual spread useful even when raw deltas are small.

## Files touched

| Path | Change |
|---|---|
| `db.py` | + `CategorySnapshot` dataclass, table schema, `insert_category_snapshot`, `load_all_category_snapshots` |
| `scraper.py` | + `parse_category_catalog`, `fetch_category_catalog` |
| `heatmap.py` | + `_OG_TYPE_BY_PAGE_TYPE["category"]`, `Literal` update, `_CATEGORIES_PAGE_TEMPLATE`, `render_categories_treemap`, `_NAV_ITEMS` entry, sitemap extension |
| `run.py` | + 3-line fetch+insert block; + 1-line render call |
| `tests/test_scraper.py` | + 2 tests (parse_catalog happy + dedup) |
| `tests/test_db.py` | + 2 tests (schema + round trip) |
| `tests/test_heatmap.py` | + 2 tests (render writes html + empty-state) |
| `tests/fixtures/categories_catalog.html` | new, small extract of real PH HTML |
| `README.md` | + Categories subsection |

**Total:** ~150-200 lines of production code, ~100 lines of tests, 1 fixture file. No new dependencies.
