# Countries v1 — design

**Status:** approved
**Date:** 2026-06-02
**Author:** ansvier + claude

## Problem

The site indexes 870 performers, sliced by gender and tier — but not by where they come from. Search queries like "Russian pornstars", "Czech pornstars", "Brazilian pornstars" are high-volume and land on Pornhub, never on us. PH profile pages expose performer origin in two `infoPiece` blocks — `Birth Place:` and `Background:` — and we already fetch each profile during the daily scrape. The data is one parser change away.

## Goal

After this lands:

1. Every performer profile that exposes Birth Place or Background gets a `country` value persisted with each daily snapshot.
2. Every country with ≥5 tracked performers gets a `/country/<slug>/` landing page rendering a single-treemap view of those performers (size = % growth, color = acceleration percentile — same metric as the homepage).
3. An index page at `/countries/` lists every qualifying country alphabetically with performer counts.
4. Each `/p/<slug>` page shows a "From: <Country>" cross-link block when the performer's country is known and qualifying.
5. Top-navigation gains a "Countries" entry.
6. Sitemap includes the new index page and all `/country/<slug>/` pages.
7. A one-off backfill script populates `country` for the ~870 currently-tracked slugs.

## Decision

### 1. Data extraction

PH profile pages contain `<div class="infoPiece">` blocks with `Label:Value` text. Verified empirically across 8 sample profiles:

- `Birth Place:Chicago, Illinois, United States of America` — city/state/country triple
- `Birth Place:Russia` — country only
- `Background:Russian` — nationality

Strategy:

1. **Primary:** parse `Birth Place:` → take last comma-segment → canonicalize via `_COUNTRY_ALIASES`.
2. **Fallback:** parse `Background:` → look up nationality in `_NATIONALITY_TO_COUNTRY` → canonicalize.
3. **Neither present, or Background unmapped:** return `None`.

Sample coverage: 5/7 reachable profiles had Birth Place; another 2/7 had only Background. Combined coverage ~85% in test set.

### 2. Country normalization

Two constants in `scraper.py`:

**`_NATIONALITY_TO_COUNTRY`** — maps nationalities (Background values) to canonical country names:

```python
"American" → "United States"
"British" → "United Kingdom"
"Russian" → "Russia"
"Italian" → "Italy"
# ... ~35 entries covering most observed nationalities
```

**`_COUNTRY_ALIASES`** — collapses Birth Place variants to canonical forms:

```python
"United States of America" → "United States"
"USA" → "United States"
"UK" → "United Kingdom"
"Great Britain" → "United Kingdom"
"England" → "United Kingdom"
# ...
```

**Unmapped values pass through as-is.** Backfill script logs every unmapped value once (set-deduped) so we can grow both dicts based on real data. Production scrape silently uses the raw value.

### 3. Storage

Add a `country TEXT` column (nullable) to the existing `snapshots` table. Same denormalized pattern as the existing `gender` column.

Migration (in `init_db` after existing migrations):

```sql
-- Migration 1c: country column
if "country" not in cols:
    conn.execute("ALTER TABLE snapshots ADD COLUMN country TEXT")
```

`Snapshot` dataclass gains `country: str | None = None`. `insert_snapshot` and `load_all_snapshots` handle the new column.

### 4. Scraper changes

In `scraper.py`:

- New module-level constants `_NATIONALITY_TO_COUNTRY`, `_COUNTRY_ALIASES`.
- New helper `_canonicalize_country(name: str) -> str` — applies aliases, defaults to input.
- New helper `extract_country(html: str) -> str | None` — implements the Birth Place + Background strategy.
- Extend `ProfileData` dataclass with `country: str | None = None`.
- Extend `parse_profile(html)` to populate `country` via `extract_country`.

The `fetch_profile(slug)` function and its callers in `run.py` are not changed beyond consuming the new `country` field.

### 5. Backfill (one-off)

New script `scripts/backfill_countries.py`:

- Loads unique `slug`s from `snapshots`.
- For each slug: `fetch_profile(slug)`, extract country, `UPDATE snapshots SET country = ? WHERE slug = ?` (across all snapshot dates for that slug — country doesn't change over time).
- Polite sleep 1.5s between requests.
- Logs progress every 50 slugs.
- Skips slugs whose country is already non-null unless `--rescrape` flag is passed.
- Logs unmapped Background values to stdout at the end for future dict expansion.
- ~870 slugs × 1.5s ≈ 22 minutes total.
- Run **once** by the user from their Mac (residential IP). Not part of `run.py`.

### 6. Render

Two new functions in `heatmap.py`:

**`render_country_page(snapshots, country_name, output_path)`**

- Filters `snapshots[snapshots["country"] == country_name]`.
- Sorts by `total_views` desc, takes head(50) as the cohort.
- Calls existing `_build_treemap_figure(cohort, window_days=1)` — same metric as homepage.
- Calls `_build_top_performer_card(..., mode="celebs", label_override=f"Top from {country_name}")` for the Spike of the Day card.
- Emits SEO head via `_render_seo_head(page_type="country", ...)` with `CollectionPage` + `BreadcrumbList` JSON-LD.
- Title: `Top {Country} Performers — HotMap`.
- Description: `Top {Country} pornstars ranked by view-growth momentum. N performers tracked. Daily heatmap, updated automatically.`
- Breadcrumbs: `[(HotMap, /), (Countries, /countries/), (Country, /country/<slug>/)]`.
- Layout matches `/stats/` and `/charts/` — header, nav, content, footer.

**`render_countries_index(snapshots, output_path)`**

- Groups by `country`, counts, filters to ≥`_COUNTRY_MIN_PERFORMERS` (=5).
- Alphabetical list of `(Country, count, /country/<slug>/)` links.
- SEO via `_render_seo_head(page_type="country", ...)`.
- Title: `All Countries — HotMap`.
- Breadcrumbs: `[(HotMap, /), (Countries, /countries/)]`.

### 7. SEO helper extension

`_OG_TYPE_BY_PAGE_TYPE` and the `Literal` annotation on `_render_seo_head` gain a `"country"` entry:

```python
"country": "website"
```

Same shape as the existing `"category"` entry added for Trending Categories.

### 8. Cross-link on `/p/<slug>`

`render_performer_page` gains a new block after the existing `<section class="performer-categories">` (or at the same insertion point if categories block is empty):

```html
<section class="performer-country">
  <h3>From</h3>
  <a href="/country/<slug>/"><Country Name></a>
</section>
```

Emitted only when:
- The performer has a non-null `country` value in their latest snapshot, AND
- That country has ≥`_COUNTRY_MIN_PERFORMERS` performers (i.e., a `/country/<slug>/` page exists).

Same CSS pattern as `.performer-categories` (chip-style link, inlined CSS in the conditional block).

### 9. URL structure

- Per-country page: `/country/<slug>/` (singular `country`, trailing slash — matches `/c/<slug>/` pattern but **without the multi-tier nesting** since each performer belongs to exactly one country).
- Countries index: `/countries/` (trailing slash).

Slugs derived via the existing `_normalize_category_slug(name)` helper (lowercase ASCII with dashes).

### 10. `_NAV_ITEMS` + sitemap

`_NAV_ITEMS` gains `("countries", "/countries/", "Countries")` between Categories and Charts.

`write_sitemap_and_robots` emits:
- `<loc>https://hotmap.cam/countries/</loc>`
- One `<loc>https://hotmap.cam/country/<slug>/</loc>` per qualifying country.

### 11. Daily-scrape integration

`run.py` orchestration gains a block after the categories rendering:

1. Compute country counts from `snapshots_df`.
2. Filter to qualifying countries (≥5 performers).
3. `mkdir public/country`, iterate qualifying countries, render each.
4. `mkdir public/countries`, render the index.
5. Pass the qualifying-country set into `render_performer_page` so cross-links only link to existing pages.

No new fetches — country was already extracted during the regular `fetch_profile` call.

## Scope

### In scope

- Birth Place + Background parsing.
- `_NATIONALITY_TO_COUNTRY` and `_COUNTRY_ALIASES` dicts (~35 + ~10 entries).
- `country` column on `snapshots` with migration.
- `extract_country`, `_canonicalize_country` helpers.
- `scripts/backfill_countries.py` — one-off, ~22 min run.
- `render_country_page` and `render_countries_index`.
- Cross-link block on `/p/<slug>`.
- `Countries` nav entry.
- Sitemap expansion.
- 7 new tests (3 scraper + 1 db + 3 heatmap).
- README subsection.

### Out of scope

- Flag emojis (🇷🇺) — visual polish for v2.
- Multi-country support (e.g., performer born in X, currently living in Y).
- Country-level leaderboards or stats pages.
- Country filter on the main treemap.
- Historical country trends (country is static per performer).
- `performer_countries` junction table (overkill for 1-to-1).
- Daily re-scrape of country (it's static; backfill once, propagates via existing daily scrape going forward).

## Edge cases

- **Performer has Birth Place "Russia" and Background "American".** Birth Place wins → `country = "Russia"`. Birth Place is more accurate for "Russian pornstars" queries; Background may reflect ethnic ancestry, not origin.

- **Background "American" but no mapping in `_NATIONALITY_TO_COUNTRY`.** Should be in the dict — flag during code review if not. If genuinely unmapped (e.g., obscure nationality), returns `None` for that performer.

- **PH returns unusual Birth Place format** like `"U.S.A."` not in `_COUNTRY_ALIASES`. Passes through as-is → gets its own slug `u-s-a` → likely below the 5-performer threshold → no page generated. Backfill script logs unmapped values for dict growth.

- **Country with exactly 1 performer.** Below threshold. No `/country/<slug>/` page. Cross-link on that performer's `/p/<slug>` is omitted.

- **Country with 4 performers (just below threshold).** Stored in DB. Future scrapes might push to 5+, at which point the page appears automatically. No special handling needed.

- **Performer with NULL country.** Not in any `/country/<slug>/` page. `/p/<slug>` omits the "From" section.

- **PH profile times out during backfill.** Script catches and logs the failure for that slug, continues. Re-running picks up the failed slugs (idempotent on country IS NULL).

- **`_normalize_category_slug` collision** between two different country canonical names. Extremely unlikely given our curated alias list, but if it happens, the two countries would conflate on the same page. Mitigation: code-review the alias dicts before commit.

## Risks

- **Coverage gap.** Sample showed 5/7 with Birth Place, 7/7 with at least one of the two. Real coverage could be lower if many performers leave both fields blank. Mitigation: log unmapped Background values and skip-NULL counts during backfill, surface for review.

- **PH HTML structure change.** Parser pinned by tests against an HTML fixture. If PH changes `.infoPiece` to something else, tests fail and we update.

- **Nationality dict accuracy.** "British" → "United Kingdom" is unambiguous; "Indian" → "India" likewise; but some entries are debatable (e.g., "American" could also mean Canadian/Brazilian/etc colloquially). We accept the canonical interpretation and document it.

- **Country with too few performers feels empty.** Threshold of 5 keeps pages substantial. Below 5, performers' country is stored but not surfaced as a landing page.

## Files touched

| Path | Change |
|---|---|
| `scraper.py` | New constants `_NATIONALITY_TO_COUNTRY`, `_COUNTRY_ALIASES`; helpers `_canonicalize_country`, `extract_country`; extend `ProfileData` and `parse_profile` |
| `db.py` | Add `country` to `Snapshot` dataclass; ALTER TABLE migration; update `insert_snapshot` and `load_all_snapshots` |
| `scripts/backfill_countries.py` | New, ~90 lines |
| `heatmap.py` | `_OG_TYPE_BY_PAGE_TYPE["country"]` + Literal update; `_COUNTRY_MIN_PERFORMERS` constant; `_COUNTRY_PAGE_TEMPLATE`; `render_country_page`; `render_countries_index`; cross-link block in `render_performer_page`; `_NAV_ITEMS` entry; sitemap extension |
| `run.py` | New rendering block for countries; pass qualifying-country set into performer-page calls |
| `tests/test_scraper.py` | +3 tests |
| `tests/test_db.py` | +1 test |
| `tests/test_heatmap.py` | +3 tests |
| `README.md` | New Countries subsection |

**Total:** ~250 lines of production code, ~120 lines of tests, +90-line backfill script. No new runtime dependencies.
