# SEO baseline — design

**Status:** approved
**Date:** 2026-05-31
**Author:** ansvier + claude

## Problem

The site renders five distinct page-type templates today (home, mode-landing, stats, charts, per-performer). Each one was added at a different time, so each emits its own ad-hoc subset of SEO/social meta tags. The result is uneven coverage:

| Page | og:image | og:type | twitter:image | JSON-LD | canonical → 200? |
|---|---|---|---|---|---|
| `/` | ❌ | ❌ | ❌ | Dataset | ✅ |
| `/p/<slug>` | ✅ avatar | ✅ profile | ❌ | Person | ✅ |
| `/stats/` | ✅ hero | ❌ | ❌ | ❌ | ⚠ canonical points to `/stats`, which 307-redirects to `/stats/` |
| `/charts/` | ❌ | ❌ | ❌ | ❌ | ⚠ same |
| `/rising/`, `/gems/`, `/celebs/` | ❌ | ❌ | ❌ | Dataset (inherits from home template) | ⚠ same |

Concrete consequences:

- Social shares on Twitter / Telegram / Discord render as text-only previews for 5 of the 6 main pages (no `og:image`).
- Google receives `canonical: /stats` for a URL that 307-redirects — ambiguous signal about which URL to index.
- `/stats/` and `/charts/` have zero structured data — no Person, no CollectionPage, no BreadcrumbList — so they're invisible to rich-result eligibility.
- Sitemap has been submitted nowhere. Search engines may not be aware of the 878 URLs at all.

The fix is mostly mechanical (template consolidation + one static asset + a submission checklist). It unblocks the bigger SEO bets that come after — Categories and Countries projects produce dozens of new pages, and every new page must inherit the same complete head block automatically rather than have us re-discover gaps page by page.

## Goal

After this lands, every rendered page on the site has:

1. Title, meta description, canonical that points to the URL that actually serves 200.
2. Complete Open Graph quintet — `og:type`, `og:title`, `og:description`, `og:url`, `og:image` (+ width/height).
3. Complete Twitter Cards triple — `twitter:card`, `twitter:title`, `twitter:image`.
4. JSON-LD: at minimum `WebSite`, plus page-specific (`Dataset` / `Person` / `CollectionPage`) and `BreadcrumbList` for child pages.
5. `<meta name="robots" content="index, follow, max-image-preview:large">`.

And the sitemap has been submitted to Google Search Console and Bing Webmaster Tools (Yandex Webmaster is explicitly skipped because we don't target RF traffic).

## Decision

Four components:

### 1. One static OG image

Generate `public/og.png` (1200×630, ~50KB). HotMap logo + tagline "Live treemap of view-growth momentum on Pornhub." Built once by `scripts/build_og.py`, committed to the repo, served as the default `og:image` on every page that doesn't have a more specific one.

Use Pillow. Add `Pillow` to `requirements.txt` if not already pulled in transitively (the plan task verifies and adds if missing). Simpler than headless-browser screenshot, no kaleido pipeline needed for a one-off.

### 2. Single `_render_seo_head()` helper

New function in `heatmap.py`. Signature:

```python
def _render_seo_head(
    *,
    page_type: Literal["home", "mode", "stats", "charts", "performer"],
    title: str,
    description: str,
    canonical_url: str,           # full https://hotmap.cam/... that 200s
    og_image_url: str | None = None,  # falls back to /og.png
    extra_jsonld: list[dict] | None = None,
    breadcrumbs: list[tuple[str, str]] | None = None,  # [(name, url), ...]
) -> str:
```

Returns a string containing the complete `<head>` SEO/social block: title, meta description, OG quintet, Twitter triple, canonical link, robots meta, and one or more JSON-LD `<script>` blocks (always WebSite; plus BreadcrumbList if `breadcrumbs` given; plus each item in `extra_jsonld`).

All four existing render functions (`render_treemap_page`, `render_performer_page`, `render_stats_page`, `render_charts_page`) call this helper instead of inlining meta tags. The current scattered inline blocks get deleted.

### 3. Page-type matrix

| page_type | og:type | extra_jsonld | breadcrumbs | canonical |
|---|---|---|---|---|
| `home` | `website` | `[Dataset]` | none | `https://hotmap.cam/` |
| `mode` | `website` | `[Dataset]` | `[(HotMap, /), (<Mode>, /<mode>/)]` | `https://hotmap.cam/<mode>/` |
| `stats` | `article` | `[CollectionPage]` | `[(HotMap, /), (Stats, /stats/)]` | `https://hotmap.cam/stats/` |
| `charts` | `website` | `[CollectionPage]` | `[(HotMap, /), (Charts, /charts/)]` | `https://hotmap.cam/charts/` |
| `performer` | `profile` | `[Person]` | `[(HotMap, /), (Charts, /charts/), (<Name>, /p/<slug>)]` | `https://hotmap.cam/p/<slug>` |

Canonical URLs for the directory-style pages (`/stats/`, `/charts/`, `/rising/`, `/gems/`, `/celebs/`) now include the trailing slash to match what Cloudflare Pages serves. Sitemap entries are updated correspondingly. Per-performer URLs (`/p/<slug>`) remain slash-less because they serve as static files at exactly that path.

### 4. Search engine submission

Manual one-time work after the code change deploys:

- **Google Search Console** — add `hotmap.cam` property, verify via Cloudflare DNS TXT record, submit `sitemap.xml`, check coverage report at 24h.
- **Bing Webmaster Tools** — same flow. Bing accepts the GSC verification, so usually one-click after GSC.
- **Yandex Webmaster** — **skipped**. We're not targeting RF; not registering with a Russian agency reduces the personal-attribution surface area discussed earlier.

A checklist file (`docs/seo-submission-checklist.md`) documents the exact steps for future-me, since this can't be automated cheaply.

## Scope

### Changes

**`public/og.png`** — new 1200×630 static asset, committed.

**`scripts/build_og.py`** — new. Generates the static OG image with Pillow. Run once locally; not part of `run.py`. Comment at the top explains how to regenerate if branding changes.

**`heatmap.py`**

- Add `_render_seo_head()` helper described above.
- Replace inline meta-tag blocks in the four `render_*` template strings with calls to `_render_seo_head()`.
- Update canonical URL builders for the four directory-style page types to include the trailing slash.

**`tests/test_heatmap.py`**

- For each of the five `page_type` values, assert that the rendered HTML contains:
  - `<title>`
  - `<meta name="description">`
  - all five `og:*` tags
  - all three `twitter:*` tags
  - `<link rel="canonical">` whose href matches the expected pattern
  - `<meta name="robots">`
  - at least one valid JSON-LD block that parses with `json.loads()`
  - WebSite JSON-LD (always present)
- One test per page_type: assert canonical URL form is the one that returns 200 (i.e., trailing slash where applicable). Use string comparison, not a live HTTP check.
- Update existing fixtures only as needed to match new template output (some existing assertions on substrings may need to widen).

**Sitemap (`heatmap.write_sitemap_and_robots`)** — update the URL emitter so directory-style entries get the trailing slash. Per-performer entries unchanged.

**`docs/seo-submission-checklist.md`** — new. ~20 lines, exact UI steps for GSC + Bing.

**`README.md`** — update SEO section: mention what's covered (`og.png`, full meta on all page types, sitemap submitted) and what isn't (per-page OG image generation is project #4).

### Out of scope

- LCP / CLS / INP performance optimization (Plotly bundle weight, image sizing). Real concern but distinct project.
- Per-page rewriting of titles and descriptions for keyword density. Current copy is acceptable.
- Per-mode / per-page dynamic OG image generation. Explicitly project #4 (the "modernize screenshots" feedback).
- Yandex Webmaster registration.
- Hreflang / multi-locale (site is English-only).
- Schema.org `BreadcrumbList` UI rendering (we emit the JSON-LD only — visible breadcrumbs are a separate UX choice not required for SEO).

## Edge cases

- **avatar URL is NULL** for a freshly-added performer with no scraped photo. `_render_seo_head()` accepts `og_image_url=None` and substitutes `/og.png`. Existing behavior on per-performer pages already does this fallback; the helper centralizes it.
- **JSON-LD escaping** — strings inside JSON-LD must escape `<`, `>`, `&` properly. Helper serializes via `json.dumps(..., ensure_ascii=False)` and inlines into `<script type="application/ld+json">`. Existing per-performer code does this correctly; helper follows the same pattern.
- **Trailing-slash redirect** — Cloudflare Pages 307-redirects bare → trailing form by default. We don't change CF config; we change our own canonical / sitemap to match what's served. The 307 itself stays. Google handles 307s fine as long as the canonical points to a URL that returns 200 directly.
- **Existing sitemap test** — `tests/test_heatmap.py::test_write_sitemap_and_robots` likely asserts on specific URL formats. Update assertions to expect trailing slashes on directory-style entries.

## Risks

- **Template consolidation regressions.** Replacing four inline blocks with one helper risks subtle output drift (extra/missing whitespace, attribute order, etc.). Mitigation: the new tests check for tag presence and content, not byte-equality, so cosmetic drift is fine. Behavioral drift (wrong canonical, missing tag) is caught.
- **Pillow may not be installed.** `requirements.txt` may need a new line. The plan checks `pip show Pillow` before writing the script and adds the dep if missing.
- **GSC verification requires Cloudflare DNS access.** I have it; this is a manual step in the checklist, not a code blocker.
- **No way to automate "did Google index the page."** Coverage shows up days later. Out of scope to verify here.

## Files touched

| Path | LoC est. |
|---|---|
| `public/og.png` | binary, ~50KB |
| `scripts/build_og.py` | ~40 |
| `heatmap.py` | +80 new, -50 inlined-deleted |
| `tests/test_heatmap.py` | +60 |
| `docs/seo-submission-checklist.md` | ~25 |
| `README.md` | ~5 lines updated |
| `requirements.txt` | possibly +1 (Pillow) |

Net: ~150 lines of code change, +1 static asset, +25 lines of human-readable docs.
