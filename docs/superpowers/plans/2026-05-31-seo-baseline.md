# SEO baseline — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every rendered page on hotmap.cam has a complete, consistent head block — title/desc/canonical, full Open Graph quintet, full Twitter triple, robots meta, and `WebSite` + page-specific + `BreadcrumbList` JSON-LD — produced by a single `_render_seo_head()` helper. Sitemap + canonical URLs match the URL form Cloudflare Pages actually serves. Sitemap is submitted to GSC + Bing.

**Architecture:** Introduce one helper in `heatmap.py` that all four `render_*` functions call instead of inlining meta tags. A static `public/og.png` (1200×630) generated once by `scripts/build_og.py` covers every page that lacks a specific avatar fallback. Submission to GSC + Bing is documented in a checklist, not automated.

**Tech Stack:** Python 3.13, Pillow (new), pytest. No JS / no new runtime services.

**Spec:** `docs/superpowers/specs/2026-05-31-seo-baseline-design.md`

---

## File map

| File | Purpose | Touched in |
|---|---|---|
| `requirements.txt` | Add `Pillow` if missing | Task 1 |
| `scripts/build_og.py` | One-off: render `public/og.png` (1200×630, HotMap logo + tagline) | Task 1 |
| `public/og.png` | Static 1200×630 default OG image, ~50KB, committed | Task 1 |
| `heatmap.py` | New `_render_seo_head()` + refactor 4 render functions + sitemap-writer URL form | Tasks 2–7 |
| `tests/test_heatmap.py` | New helper tests + per-page-type SEO coverage tests + sitemap trailing-slash test | Tasks 2–7 |
| `docs/seo-submission-checklist.md` | GSC + Bing submission steps | Task 8 |
| `README.md` | SEO section update + add Pillow note in local-dev block | Task 8 |

No DB / scraper / worker.js / CF Pages config changes.

---

### Task 1: Static OG image + Pillow dep

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/requirements.txt`
- Create: `/Users/ansvier/ph-heatmap/scripts/build_og.py`
- Create: `/Users/ansvier/ph-heatmap/public/og.png` (generated, then committed)

- [ ] **Step 1: Check whether Pillow is already installed**

```bash
cd /Users/ansvier/ph-heatmap
./venv/bin/pip show Pillow 2>&1 | head -2
```

If output starts with `Name: Pillow`, skip Step 2. Otherwise proceed.

- [ ] **Step 2: Add Pillow to requirements**

Open `/Users/ansvier/ph-heatmap/requirements.txt`. Append a line:

```
Pillow>=10.0
```

Then install:

```bash
./venv/bin/pip install -q -r requirements.txt
```

- [ ] **Step 3: Confirm there's a logo asset**

```bash
ls /Users/ansvier/ph-heatmap/public/ | grep -E "favicon|logo|hotmap" | head -5
```

Expected: at least one of `favicon.svg`, `favicon-32.png`, `apple-touch-icon.png` exists. The script in Step 4 uses one of these as the visual element. If none exists, STOP and report — we need the logo source first.

- [ ] **Step 4: Write `scripts/build_og.py`**

Create `/Users/ansvier/ph-heatmap/scripts/build_og.py`:

```python
"""Generate public/og.png — the default 1200×630 Open Graph image.

Run once: `./venv/bin/python scripts/build_og.py`. Output is committed to the
repo. Re-run only if HotMap branding changes (logo, tagline, color).

Layout:
  - Black background (#0a0a0a, matches site)
  - HotMap orange wordmark centered horizontally, upper-third
  - Tagline below, centered
  - Optional accent block in HotMap orange (#ff9000) along bottom
"""
from __future__ import annotations
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT_PATH = Path(__file__).resolve().parent.parent / "public" / "og.png"
SIZE = (1200, 630)
BG = (10, 10, 10)             # #0a0a0a, matches --bg
FG = (245, 245, 245)          # #f5f5f5, matches --fg
ORANGE = (255, 144, 0)        # #ff9000, brand

WORDMARK = "HotMap"
TAGLINE = "Live treemap of view-growth momentum on Pornhub"


def _load_font(preferred_paths: list[Path], size: int) -> ImageFont.FreeTypeFont:
    """Try a list of font paths; fall back to PIL's default if all fail."""
    for p in preferred_paths:
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def main() -> None:
    img = Image.new("RGB", SIZE, BG)
    draw = ImageDraw.Draw(img)

    # System fonts on macOS / Linux GitHub runners. Helvetica/Arial fallbacks
    # for macOS; DejaVu/Liberation for Linux.
    bold_candidates = [
        Path("/System/Library/Fonts/Helvetica.ttc"),
        Path("/Library/Fonts/Arial Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ]
    regular_candidates = [
        Path("/System/Library/Fonts/Helvetica.ttc"),
        Path("/Library/Fonts/Arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    ]
    wordmark_font = _load_font(bold_candidates, size=180)
    tagline_font = _load_font(regular_candidates, size=42)

    # Wordmark — "Hot" white, "Map" orange (matches site logo treatment).
    hot_w = draw.textlength("Hot", font=wordmark_font)
    map_w = draw.textlength("Map", font=wordmark_font)
    total_w = hot_w + map_w
    wm_x = (SIZE[0] - total_w) / 2
    wm_y = 180
    draw.text((wm_x, wm_y), "Hot", font=wordmark_font, fill=FG)
    draw.text((wm_x + hot_w, wm_y), "Map", font=wordmark_font, fill=ORANGE)

    # Tagline
    tag_w = draw.textlength(TAGLINE, font=tagline_font)
    draw.text(((SIZE[0] - tag_w) / 2, 420), TAGLINE, font=tagline_font, fill=FG)

    # Orange accent bar along bottom, like the .top-perf border-left.
    draw.rectangle([(0, 610), (SIZE[0], 630)], fill=ORANGE)

    img.save(OUT_PATH, "PNG", optimize=True)
    print(f"wrote {OUT_PATH} ({OUT_PATH.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run the generator**

```bash
cd /Users/ansvier/ph-heatmap
./venv/bin/python scripts/build_og.py
```

Expected: `wrote .../public/og.png (NNNN bytes)`. The file size should be 30–100KB.

- [ ] **Step 6: Verify dimensions**

```bash
./venv/bin/python -c "from PIL import Image; im = Image.open('public/og.png'); print(im.size, im.mode)"
```

Expected: `(1200, 630) RGB`. If different, the script has a bug — STOP.

- [ ] **Step 7: Visual eyeball (optional)**

```bash
open /Users/ansvier/ph-heatmap/public/og.png
```

Expected: black background, "HotMap" wordmark with "Hot" in white and "Map" in orange, tagline below, orange bar along bottom. If fonts fell back to PIL default (tiny, blocky), the truetype paths in `_load_font` may need adjustment for the local machine. Not a blocker — the image is functional even with the fallback — but worth re-running on a machine with proper system fonts.

- [ ] **Step 8: Commit**

```bash
cd /Users/ansvier/ph-heatmap
git add requirements.txt scripts/build_og.py public/og.png
git commit -m "$(cat <<'EOF'
feat(seo): static og.png + Pillow dep

Default 1200x630 Open Graph image for pages that don't have a more
specific avatar fallback. Generator script is one-off; the PNG is
committed to the repo.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `_render_seo_head()` helper

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/heatmap.py` — add helper near other rendering utilities (around line 600, after `_format_views`)
- Modify: `/Users/ansvier/ph-heatmap/tests/test_heatmap.py` — append helper tests at the end

This is the core building block. Implements the page-type matrix from the spec.

- [ ] **Step 1: Write failing tests for helper signature and basic output**

Append to `/Users/ansvier/ph-heatmap/tests/test_heatmap.py`:

```python
import json as _json
import re as _re
from heatmap import _render_seo_head


def _extract_jsonld_blocks(html: str) -> list[dict]:
    """Parse all <script type="application/ld+json"> blocks from rendered HTML."""
    pattern = _re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\']>(.*?)</script>',
        _re.DOTALL,
    )
    out = []
    for raw in pattern.findall(html):
        out.append(_json.loads(raw.strip()))
    return out


def test_render_seo_head_home_emits_all_required_tags():
    """Home page gets the full SEO/social/JSON-LD block."""
    head = _render_seo_head(
        page_type="home",
        title="HotMap — who's growing fastest on Pornhub",
        description="Live heatmap of view growth across the top-500 performers.",
        canonical_url="https://hotmap.cam/",
    )

    # Core meta
    assert "<title>HotMap — who&#39;s growing fastest on Pornhub</title>" in head \
        or "<title>HotMap — who's growing fastest on Pornhub</title>" in head
    assert 'name="description"' in head
    assert 'rel="canonical"' in head and 'href="https://hotmap.cam/"' in head
    assert 'name="robots"' in head and 'index, follow' in head

    # OG quintet
    assert 'property="og:type" content="website"' in head
    assert 'property="og:title"' in head
    assert 'property="og:description"' in head
    assert 'property="og:url" content="https://hotmap.cam/"' in head
    assert 'property="og:image" content="https://hotmap.cam/og.png"' in head, \
        "home should fall back to /og.png when no og_image_url provided"

    # Twitter triple
    assert 'name="twitter:card" content="summary_large_image"' in head
    assert 'name="twitter:title"' in head
    assert 'name="twitter:image" content="https://hotmap.cam/og.png"' in head

    # JSON-LD: WebSite always, plus no extras for bare home call
    blocks = _extract_jsonld_blocks(head)
    types = {b.get("@type") for b in blocks}
    assert "WebSite" in types, f"expected WebSite JSON-LD; got types={types}"


def test_render_seo_head_uses_explicit_og_image_when_given():
    """When og_image_url is explicit (e.g. an avatar), helper uses it."""
    head = _render_seo_head(
        page_type="performer",
        title="Lana Rhoades — HotMap",
        description="Lana Rhoades stats.",
        canonical_url="https://hotmap.cam/p/lana-rhoades",
        og_image_url="https://hotmap.cam/avatars/lana-rhoades.jpg",
    )
    assert 'property="og:image" content="https://hotmap.cam/avatars/lana-rhoades.jpg"' in head
    assert 'name="twitter:image" content="https://hotmap.cam/avatars/lana-rhoades.jpg"' in head
    assert 'property="og:image" content="https://hotmap.cam/og.png"' not in head


def test_render_seo_head_og_type_per_page_type():
    """og:type matches the page_type matrix in the spec."""
    expected = {
        "home": "website",
        "mode": "website",
        "stats": "article",
        "charts": "website",
        "performer": "profile",
    }
    for page_type, og_type in expected.items():
        head = _render_seo_head(
            page_type=page_type,
            title="T",
            description="D",
            canonical_url="https://hotmap.cam/x",
        )
        assert f'property="og:type" content="{og_type}"' in head, \
            f"page_type={page_type}: expected og:type={og_type}"


def test_render_seo_head_emits_breadcrumbs_when_given():
    """BreadcrumbList JSON-LD is emitted when breadcrumbs param is non-empty."""
    head = _render_seo_head(
        page_type="performer",
        title="Lana Rhoades — HotMap",
        description="Lana Rhoades stats.",
        canonical_url="https://hotmap.cam/p/lana-rhoades",
        breadcrumbs=[
            ("HotMap", "https://hotmap.cam/"),
            ("Charts", "https://hotmap.cam/charts/"),
            ("Lana Rhoades", "https://hotmap.cam/p/lana-rhoades"),
        ],
    )
    blocks = _extract_jsonld_blocks(head)
    bc = next((b for b in blocks if b.get("@type") == "BreadcrumbList"), None)
    assert bc is not None, "expected BreadcrumbList JSON-LD"
    items = bc["itemListElement"]
    assert len(items) == 3
    assert items[0]["position"] == 1
    assert items[0]["name"] == "HotMap"
    assert items[0]["item"] == "https://hotmap.cam/"
    assert items[2]["name"] == "Lana Rhoades"


def test_render_seo_head_emits_extra_jsonld():
    """extra_jsonld list is appended verbatim as additional <script> blocks."""
    person_ld = {"@context": "https://schema.org", "@type": "Person", "name": "Lana Rhoades"}
    head = _render_seo_head(
        page_type="performer",
        title="Lana Rhoades — HotMap",
        description="…",
        canonical_url="https://hotmap.cam/p/lana-rhoades",
        extra_jsonld=[person_ld],
    )
    blocks = _extract_jsonld_blocks(head)
    types = {b.get("@type") for b in blocks}
    assert "WebSite" in types  # always
    assert "Person" in types   # from extra


def test_render_seo_head_jsonld_escapes_safely():
    """Strings inside JSON-LD must survive json.loads, including apostrophes."""
    head = _render_seo_head(
        page_type="home",
        title="HotMap — who's growing fastest",
        description="Tile size = % growth; color = rank.",
        canonical_url="https://hotmap.cam/",
    )
    # Must not throw
    blocks = _extract_jsonld_blocks(head)
    assert all(isinstance(b, dict) for b in blocks)
```

- [ ] **Step 2: Run tests to confirm RED**

```bash
cd /Users/ansvier/ph-heatmap
./venv/bin/pytest tests/test_heatmap.py -k render_seo_head -v
```

Expected: 6 errors (`ImportError: cannot import name '_render_seo_head'`).

- [ ] **Step 3: Implement the helper**

Open `/Users/ansvier/ph-heatmap/heatmap.py`. Find a good spot for the helper — recommended: after the `_format_views` function (around line 596), before `_build_treemap_figure`.

Add:

```python
import html as _html
import json as _json

_SITE_NAME = "HotMap"
_DEFAULT_OG_IMAGE = "https://hotmap.cam/og.png"
_TWITTER_CARD = "summary_large_image"

_OG_TYPE_BY_PAGE_TYPE = {
    "home": "website",
    "mode": "website",
    "stats": "article",
    "charts": "website",
    "performer": "profile",
}


def _website_jsonld() -> dict:
    """The WebSite block, emitted on every page. Carries the search action hint
    that Google uses to enable site-search sitelinks."""
    return {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": _SITE_NAME,
        "url": "https://hotmap.cam/",
        "potentialAction": {
            "@type": "SearchAction",
            "target": "https://hotmap.cam/charts/?q={search_term_string}",
            "query-input": "required name=search_term_string",
        },
    }


def _breadcrumb_jsonld(items: list[tuple[str, str]]) -> dict:
    """BreadcrumbList — items is [(name, url), ...] in display order."""
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": i + 1,
                "name": name,
                "item": url,
            }
            for i, (name, url) in enumerate(items)
        ],
    }


def _render_seo_head(
    *,
    page_type: str,
    title: str,
    description: str,
    canonical_url: str,
    og_image_url: str | None = None,
    extra_jsonld: list[dict] | None = None,
    breadcrumbs: list[tuple[str, str]] | None = None,
) -> str:
    """Produce the complete SEO + social + JSON-LD block for one rendered page.

    All four render_* functions call this exactly once and inject the result
    into their template's <head>. Consolidating here is the only way to keep
    coverage consistent as new page types are added (categories, countries…).

    Args:
        page_type: one of 'home', 'mode', 'stats', 'charts', 'performer'.
            Drives og:type via _OG_TYPE_BY_PAGE_TYPE.
        title: <title> and og:title and twitter:title.
        description: meta description, og:description, twitter:description.
        canonical_url: full https://hotmap.cam/... URL that returns 200 directly
            (no redirects). This goes into <link rel="canonical">, og:url, and
            the @id of WebSite JSON-LD.
        og_image_url: full URL to the social-share image. None falls back to
            /og.png (the static default).
        extra_jsonld: zero or more schema.org JSON-LD dicts appended as
            additional <script> blocks (Person, Dataset, CollectionPage…).
        breadcrumbs: zero or more (name, url) tuples in display order. If
            non-empty, a BreadcrumbList JSON-LD block is emitted.

    Returns:
        A string of HTML to be inserted between <head> tags.
    """
    og_type = _OG_TYPE_BY_PAGE_TYPE[page_type]
    image = og_image_url or _DEFAULT_OG_IMAGE

    title_esc = _html.escape(title, quote=True)
    desc_esc = _html.escape(description, quote=True)

    jsonld_blocks: list[dict] = [_website_jsonld()]
    if breadcrumbs:
        jsonld_blocks.append(_breadcrumb_jsonld(breadcrumbs))
    if extra_jsonld:
        jsonld_blocks.extend(extra_jsonld)

    jsonld_html = "\n".join(
        f'  <script type="application/ld+json">{_json.dumps(b, ensure_ascii=False)}</script>'
        for b in jsonld_blocks
    )

    return (
        f'  <title>{title_esc}</title>\n'
        f'  <meta name="description" content="{desc_esc}">\n'
        f'  <link rel="canonical" href="{canonical_url}">\n'
        f'  <meta name="robots" content="index, follow, max-image-preview:large">\n'
        f'  <meta property="og:type" content="{og_type}">\n'
        f'  <meta property="og:title" content="{title_esc}">\n'
        f'  <meta property="og:description" content="{desc_esc}">\n'
        f'  <meta property="og:url" content="{canonical_url}">\n'
        f'  <meta property="og:image" content="{image}">\n'
        f'  <meta property="og:image:width" content="1200">\n'
        f'  <meta property="og:image:height" content="630">\n'
        f'  <meta property="og:site_name" content="{_SITE_NAME}">\n'
        f'  <meta name="twitter:card" content="{_TWITTER_CARD}">\n'
        f'  <meta name="twitter:title" content="{title_esc}">\n'
        f'  <meta name="twitter:description" content="{desc_esc}">\n'
        f'  <meta name="twitter:image" content="{image}">\n'
        f'{jsonld_html}\n'
    )
```

The two `import` lines at the top should be added near the existing imports at the top of `heatmap.py` (not inside the function).

- [ ] **Step 4: Run the helper tests to confirm GREEN**

```bash
./venv/bin/pytest tests/test_heatmap.py -k render_seo_head -v
```

Expected: 6 passed.

- [ ] **Step 5: Run full suite (regression check)**

```bash
./venv/bin/pytest -q
```

Expected: all tests still pass — at this point we only added new code, didn't touch existing renderers.

- [ ] **Step 6: Commit**

```bash
git add heatmap.py tests/test_heatmap.py
git commit -m "$(cat <<'EOF'
feat(seo): add _render_seo_head() helper

Single source of truth for <head> SEO/social/JSON-LD blocks. The four
render_* functions will be migrated to call this in subsequent commits.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Refactor `render_treemap_page` (home + mode landings)

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/heatmap.py` — `_PAGE_TEMPLATE` (around lines 74–108) + `render_treemap_page` body (around lines 866–945) + `_MODE_LANDING_META` (lines 846–862)
- Modify: `/Users/ansvier/ph-heatmap/tests/test_heatmap.py`

- [ ] **Step 1: Update `_MODE_LANDING_META` (the home description still describes the OLD metric)**

Open `heatmap.py`. Find `_MODE_LANDING_META` (line 846). Replace the `home` entry's description because we shipped the %-growth change yesterday but this string still says "tile size = views gained":

Replace:

```python
    "home": {
        "title": "HotMap — who's growing fastest on Pornhub",
        "description": "Live heatmap of view growth: tile size = views gained in the window, color = growth pace relative to the median.",
    },
```

With:

```python
    "home": {
        "title": "HotMap — who's growing fastest on Pornhub",
        "description": "Live heatmap of view-growth momentum across the top-500 performers. Tile size = % growth in the window, color = rank within the cohort. Updated daily.",
    },
```

- [ ] **Step 2: Write failing test asserting home page has full SEO block**

Append to `tests/test_heatmap.py`:

```python
def test_render_treemap_page_emits_full_seo_block(tmp_path):
    """Home page output contains the full SEO/social/JSON-LD set."""
    df = _snapshot_rows()
    out = tmp_path / "out.html"
    render_treemap_page(df, out, default_mode="rising", canonical_path="/", seo_key="home")
    content = out.read_text()

    # Canonical now uses the trailing-slash form (already does for home).
    assert 'rel="canonical" href="https://hotmap.cam/"' in content
    # OG image must default to /og.png
    assert 'property="og:image" content="https://hotmap.cam/og.png"' in content
    # Twitter image must match
    assert 'name="twitter:image" content="https://hotmap.cam/og.png"' in content
    # og:type=website on home
    assert 'property="og:type" content="website"' in content
    # Robots meta
    assert 'name="robots" content="index, follow' in content

    blocks = _extract_jsonld_blocks(content)
    types = {b.get("@type") for b in blocks}
    assert "WebSite" in types and "Dataset" in types, f"got types={types}"


def test_render_treemap_page_mode_landing_has_breadcrumbs_and_trailing_slash(tmp_path):
    """Mode landings (/rising/, /gems/, /celebs/) emit BreadcrumbList JSON-LD
    and canonical URLs include the trailing slash that CF Pages serves."""
    df = _snapshot_rows()
    out = tmp_path / "rising.html"
    render_treemap_page(df, out, default_mode="rising", canonical_path="/rising/", seo_key="rising")
    content = out.read_text()

    assert 'rel="canonical" href="https://hotmap.cam/rising/"' in content
    blocks = _extract_jsonld_blocks(content)
    types = {b.get("@type") for b in blocks}
    assert "BreadcrumbList" in types, f"got types={types}"

    # The breadcrumb should reflect the navigation: HotMap -> Rising Stars
    bc = next(b for b in blocks if b.get("@type") == "BreadcrumbList")
    names = [item["name"] for item in bc["itemListElement"]]
    assert names == ["HotMap", "Rising Stars"], f"got names={names}"
```

- [ ] **Step 3: Run tests to confirm RED**

```bash
./venv/bin/pytest tests/test_heatmap.py -k "render_treemap_page_emits_full_seo_block or render_treemap_page_mode_landing" -v
```

Expected: 2 failures — missing `og:image`, missing `BreadcrumbList`, etc.

- [ ] **Step 4: Rewrite `_PAGE_TEMPLATE` head**

In `heatmap.py`, find `_PAGE_TEMPLATE` (line 74). Replace the entire head section from `<head>` through the closing of the `</script>` block at line 107 (the Dataset JSON-LD) with:

```python
_PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
{seo_head}
  <link rel="icon" type="image/svg+xml" href="/favicon.svg">
  <link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png">
  <link rel="icon" type="image/png" sizes="16x16" href="/favicon-16.png">
  <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
  <link rel="shortcut icon" href="/favicon.ico">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js" defer></script>
"""
```

(Keep everything after the html2canvas line unchanged — the `<style>` block etc.)

The `{seo_head}` placeholder will be filled by the call to `_render_seo_head()`. The old inline `<title>`, OG, canonical, and Dataset `<script>` blocks are removed.

- [ ] **Step 5: Wire `_render_seo_head()` into `render_treemap_page`**

In `render_treemap_page` (line 866), find the block around line 921:

```python
    meta = _MODE_LANDING_META.get(seo_key, _MODE_LANDING_META["home"])
    page = _PAGE_TEMPLATE.format(
        panels="\n    ".join(panels_html_parts),
        ...
```

Replace the `meta = ...` line and add `seo_head` computation before the `_PAGE_TEMPLATE.format(...)` call. Insert this block right before `page = _PAGE_TEMPLATE.format(...)`:

```python
    meta = _MODE_LANDING_META.get(seo_key, _MODE_LANDING_META["home"])
    canonical_url = f"https://hotmap.cam{canonical_path}"

    # Mode landings get a BreadcrumbList; home doesn't (it IS the root).
    breadcrumbs = None
    page_type = "home"
    if seo_key in ("rising", "gems", "celebs"):
        page_type = "mode"
        mode_labels = {"rising": "Rising Stars", "gems": "Hidden Gems", "celebs": "Top Celebrities"}
        breadcrumbs = [
            ("HotMap", "https://hotmap.cam/"),
            (mode_labels[seo_key], canonical_url),
        ]

    dataset_jsonld = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": "HotMap — Pornhub top-500 view growth",
        "description": "Daily snapshot of cumulative video views for the top-500 Pornhub performers, broken down by gender, with day-over-day growth rates over 1d / 7d / 30d windows.",
        "url": "https://hotmap.cam/",
        "license": "https://creativecommons.org/publicdomain/zero/1.0/",
        "creator": {"@type": "Person", "name": "ansvier"},
        "distribution": [
            {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": "https://hotmap.cam/data.json"}
        ],
        "keywords": ["pornstars", "view growth", "analytics", "treemap", "rankings"],
        "isAccessibleForFree": True,
    }

    seo_head = _render_seo_head(
        page_type=page_type,
        title=meta["title"],
        description=meta["description"],
        canonical_url=canonical_url,
        og_image_url=None,                 # fall back to /og.png
        extra_jsonld=[dataset_jsonld],
        breadcrumbs=breadcrumbs,
    )
```

Then in the `_PAGE_TEMPLATE.format(...)` call, add a `seo_head=seo_head,` keyword and remove the old `seo_title=meta["title"]`, `seo_description=meta["description"]`, `seo_canonical_path=canonical_path` keywords (those template placeholders no longer exist).

- [ ] **Step 6: Update the caller in `run.py` for the mode-landing canonical_path**

Open `/Users/ansvier/ph-heatmap/run.py`. Find lines around 157–164:

```python
        render_treemap_page(
            snapshots_df,
            mode_dir / "index.html",
            default_mode=mode,
            canonical_path=f"/{mode}",
            seo_key=mode,
        )
```

Change `canonical_path=f"/{mode}"` to `canonical_path=f"/{mode}/"` (add trailing slash). The home call at line 150 already uses `canonical_path="/"` so it stays.

- [ ] **Step 7: Run the two new tests**

```bash
./venv/bin/pytest tests/test_heatmap.py -k "render_treemap_page_emits_full_seo_block or render_treemap_page_mode_landing" -v
```

Expected: 2 passed.

- [ ] **Step 8: Run the existing treemap test (regression)**

```bash
./venv/bin/pytest tests/test_heatmap.py::test_render_treemap_page_writes_html -v
```

Expected: still pass. The test checks for substrings (panel IDs, slugs, Plotly bundle, etc.) that the refactor leaves intact. If it fails on a SEO-related substring check, update the substring to match new helper output.

- [ ] **Step 9: Run full suite**

```bash
./venv/bin/pytest -q
```

Expected: 30+ tests passing.

- [ ] **Step 10: Commit**

```bash
git add heatmap.py tests/test_heatmap.py run.py
git commit -m "$(cat <<'EOF'
refactor(seo): route render_treemap_page through _render_seo_head

Home + mode landings now use the consolidated SEO head helper. Mode
landings get BreadcrumbList JSON-LD, and their canonical URLs include
the trailing slash that CF Pages actually serves (was a 307-redirect
target before, causing a canonical-vs-served-URL mismatch).

Also updates the home meta description — it still claimed "tile size =
views gained" after yesterday's switch to % growth.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Refactor `render_performer_page`

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/heatmap.py` — `render_performer_page` template + body (around lines 940–1200)
- Modify: `/Users/ansvier/ph-heatmap/tests/test_heatmap.py`

The per-performer page already has a Person JSON-LD and og:image (avatar). We're consolidating to the helper and adding BreadcrumbList.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_heatmap.py`:

```python
def test_render_performer_page_emits_full_seo_block(tmp_path):
    """Per-performer page: complete SEO + Person + BreadcrumbList JSON-LD,
    twitter:image points to avatar (not the default og.png)."""
    df = _snapshot_rows()
    out = tmp_path / "alice.html"
    render_performer_page(df, slug="alice", output_path=out)
    content = out.read_text()

    assert 'rel="canonical" href="https://hotmap.cam/p/alice"' in content
    assert 'property="og:type" content="profile"' in content
    # Avatar fallback for tests: there's no real avatar for fixture 'alice',
    # so the page should fall back to /og.png. Real production data has
    # /avatars/<slug>.jpg.
    assert ('property="og:image" content="https://hotmap.cam/og.png"' in content
            or 'property="og:image" content="https://hotmap.cam/avatars/alice' in content)
    assert 'name="twitter:image"' in content

    blocks = _extract_jsonld_blocks(content)
    types = {b.get("@type") for b in blocks}
    assert "WebSite" in types and "Person" in types and "BreadcrumbList" in types, \
        f"got types={types}"

    bc = next(b for b in blocks if b.get("@type") == "BreadcrumbList")
    names = [item["name"] for item in bc["itemListElement"]]
    assert names == ["HotMap", "Charts", "Alice"], f"got names={names}"
```

- [ ] **Step 2: Run test to confirm RED**

```bash
./venv/bin/pytest tests/test_heatmap.py::test_render_performer_page_emits_full_seo_block -v
```

Expected: failure — no BreadcrumbList, no robots meta, etc.

- [ ] **Step 3: Locate the existing `<head>` block in the performer template**

In `heatmap.py`, find `render_performer_page` (line 1203 per grep). The function builds its HTML inline (no separate `_PERFORMER_TEMPLATE` constant — it's an f-string). Find the `<head>` content and the line `og_image_tag = ...` (around line 1245–1249).

- [ ] **Step 4: Refactor to use `_render_seo_head()`**

Identify the section that builds title, meta, OG, twitter, JSON-LD inside `render_performer_page`. Replace that entire block with:

```python
    # SEO/social head — consolidated through helper.
    canonical_url = f"https://hotmap.cam/p/{slug}"
    if photo_url:
        # photo_url may be a hotmap.cam-relative path (/avatars/xxx.jpg)
        # or absolute. Normalize to absolute.
        og_image_url = (
            photo_url if photo_url.startswith("http")
            else f"https://hotmap.cam{photo_url if photo_url.startswith('/') else '/' + photo_url}"
        )
    else:
        og_image_url = None

    person_jsonld = {
        "@context": "https://schema.org",
        "@type": "Person",
        "name": display_name,
        "url": canonical_url,
        "identifier": slug,
    }
    if photo_url:
        person_jsonld["image"] = og_image_url

    breadcrumbs = [
        ("HotMap", "https://hotmap.cam/"),
        ("Charts", "https://hotmap.cam/charts/"),
        (display_name, canonical_url),
    ]

    seo_title = f"{display_name} — view statistics, growth, ranking | HotMap"
    seo_description = f"{display_name}: {latest_views:,} cumulative views as of {latest_date_str}. Daily growth: {growth_1d_str}."

    seo_head = _render_seo_head(
        page_type="performer",
        title=seo_title,
        description=seo_description,
        canonical_url=canonical_url,
        og_image_url=og_image_url,
        extra_jsonld=[person_jsonld],
        breadcrumbs=breadcrumbs,
    )
```

Then in the f-string that builds the HTML, find the `<head>` content from `<title>` through the closing `</script>` of the Person JSON-LD. Replace it all with just `{seo_head}` (literal — the f-string already substitutes).

**Important:** keep all favicon/font/preconnect `<link>` tags. Only the SEO/social/JSON-LD section is replaced.

You'll likely need to look at the existing variable names in `render_performer_page` — `display_name`, `latest_views`, `latest_date_str`, `growth_1d_str`, `photo_url`. If they have different names, use the existing ones.

- [ ] **Step 5: Run the new test**

```bash
./venv/bin/pytest tests/test_heatmap.py::test_render_performer_page_emits_full_seo_block -v
```

Expected: pass.

- [ ] **Step 6: Run the existing performer test (regression)**

```bash
./venv/bin/pytest tests/test_heatmap.py::test_render_performer_page_writes_html -v
```

Expected: pass. If a substring assertion fails (e.g., it asserts on old `og:image` format), update the assertion to match.

- [ ] **Step 7: Commit**

```bash
git add heatmap.py tests/test_heatmap.py
git commit -m "$(cat <<'EOF'
refactor(seo): route render_performer_page through _render_seo_head

Adds BreadcrumbList (HotMap > Charts > <Name>), unifies twitter:image
with og:image (was missing entirely), and centralizes the Person JSON-LD
emission through the helper. Behavior unchanged for the existing tags;
new tags now consistent with home + mode pages.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Refactor `render_stats_page`

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/heatmap.py` — `render_stats_page` (around line 1568)
- Modify: `/Users/ansvier/ph-heatmap/tests/test_heatmap.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_heatmap.py`:

```python
def test_render_stats_page_emits_full_seo_block(tmp_path):
    """Stats page: complete SEO + CollectionPage + BreadcrumbList JSON-LD,
    canonical with trailing slash, og:type=article."""
    df = _snapshot_rows()
    out = tmp_path / "stats.html"
    render_stats_page(df, out)
    content = out.read_text()

    assert 'rel="canonical" href="https://hotmap.cam/stats/"' in content, \
        "canonical must use trailing slash to match what CF serves"
    assert 'property="og:type" content="article"' in content
    assert 'name="twitter:image"' in content

    blocks = _extract_jsonld_blocks(content)
    types = {b.get("@type") for b in blocks}
    assert "WebSite" in types and "CollectionPage" in types and "BreadcrumbList" in types, \
        f"got types={types}"
```

- [ ] **Step 2: Confirm RED**

```bash
./venv/bin/pytest tests/test_heatmap.py::test_render_stats_page_emits_full_seo_block -v
```

Expected: failure — canonical is `/stats` not `/stats/`, no CollectionPage, no BreadcrumbList.

- [ ] **Step 3: Refactor `render_stats_page`**

Find the `<head>` block inside `render_stats_page`. Replace title/meta/OG/twitter/canonical with a `_render_seo_head()` call. Use the existing computed values for `n_performers`, `total_views_human`, and `hero_photo_path`.

```python
    canonical_url = "https://hotmap.cam/stats/"
    og_image_url = f"https://hotmap.cam/{hero_photo_path}" if hero_photo_path else None

    collection_jsonld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": f"HotMap Stats — {n_performers} performers, {total_views_human} cumulative views",
        "url": canonical_url,
        "description": f"Single-page summary of HotMap data — hero numbers, biggest movers, leaderboards. {n_performers} performers tracked, {total_views_human} cumulative views.",
    }
    breadcrumbs = [
        ("HotMap", "https://hotmap.cam/"),
        ("Stats", canonical_url),
    ]

    seo_head = _render_seo_head(
        page_type="stats",
        title=f"HotMap Stats — {n_performers} performers tracked, {total_views_human} cumulative views",
        description=f"HotMap tracks {n_performers} Pornhub performers across {n_days} days of view-growth history. Updated daily. Today's biggest movers, leaderboards by 1d/7d/30d growth.",
        canonical_url=canonical_url,
        og_image_url=og_image_url,
        extra_jsonld=[collection_jsonld],
        breadcrumbs=breadcrumbs,
    )
```

(If `n_days` isn't available locally in the function, compute it: `n_days = snapshots["snapshot_date"].nunique()` near the top of the function.)

Replace the existing inline `<head>` SEO/social block in the rendered f-string with `{seo_head}`.

- [ ] **Step 4: Run new + existing stats tests**

```bash
./venv/bin/pytest tests/test_heatmap.py -k render_stats_page -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add heatmap.py tests/test_heatmap.py
git commit -m "$(cat <<'EOF'
refactor(seo): route render_stats_page through _render_seo_head

Canonical now points to /stats/ (matches what CF serves directly, was
pointing to /stats which 307-redirects). Adds CollectionPage and
BreadcrumbList JSON-LD; previously /stats had zero structured data.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Refactor `render_charts_page`

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/heatmap.py` — `render_charts_page` (around line 1897)
- Modify: `/Users/ansvier/ph-heatmap/tests/test_heatmap.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_heatmap.py`:

```python
def test_render_charts_page_emits_full_seo_block(tmp_path):
    """Charts page: complete SEO + CollectionPage + BreadcrumbList JSON-LD,
    canonical /charts/, og:image falls back to /og.png (no hero photo)."""
    df = _snapshot_rows()
    out = tmp_path / "charts.html"
    render_charts_page(df, out)
    content = out.read_text()

    assert 'rel="canonical" href="https://hotmap.cam/charts/"' in content
    assert 'property="og:type" content="website"' in content
    assert 'property="og:image" content="https://hotmap.cam/og.png"' in content, \
        "charts page has no hero — must fall back to default og.png"

    blocks = _extract_jsonld_blocks(content)
    types = {b.get("@type") for b in blocks}
    assert "WebSite" in types and "CollectionPage" in types and "BreadcrumbList" in types
```

- [ ] **Step 2: Confirm RED**

```bash
./venv/bin/pytest tests/test_heatmap.py::test_render_charts_page_emits_full_seo_block -v
```

- [ ] **Step 3: Refactor `render_charts_page`**

Find the `<head>` block inside `render_charts_page`. Replace title/meta/OG/twitter/canonical with:

```python
    canonical_url = "https://hotmap.cam/charts/"
    n_performers = snapshots["slug"].nunique()

    collection_jsonld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "HotMap Charts — A-Z performer index",
        "url": canonical_url,
        "description": f"Alphabetical index of all {n_performers} Pornhub performers tracked by HotMap. Search by name, jump by letter.",
    }
    breadcrumbs = [
        ("HotMap", "https://hotmap.cam/"),
        ("Charts", canonical_url),
    ]

    seo_head = _render_seo_head(
        page_type="charts",
        title="Performer index — HotMap charts",
        description=f"Alphabetical index of all {n_performers} Pornhub performers tracked by HotMap. Search by name, jump by letter, see per-performer view-growth stats.",
        canonical_url=canonical_url,
        og_image_url=None,                 # fall back to /og.png
        extra_jsonld=[collection_jsonld],
        breadcrumbs=breadcrumbs,
    )
```

Replace existing inline head with `{seo_head}`.

- [ ] **Step 4: Run tests**

```bash
./venv/bin/pytest tests/test_heatmap.py -k render_charts_page -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add heatmap.py tests/test_heatmap.py
git commit -m "$(cat <<'EOF'
refactor(seo): route render_charts_page through _render_seo_head

Canonical now points to /charts/. Adds CollectionPage and BreadcrumbList
JSON-LD; previously /charts had zero structured data and no og:image at
all (now falls back to /og.png).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Sitemap trailing-slash + caller-side path

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/heatmap.py` — `write_sitemap_and_robots` (around line 1983)
- Modify: `/Users/ansvier/ph-heatmap/tests/test_heatmap.py`

- [ ] **Step 1: Inspect current sitemap output to find the URL builder**

```bash
./venv/bin/python -c "
import sqlite3, pandas as pd, pathlib, tempfile
from db import init_db, load_all_snapshots
from heatmap import write_sitemap_and_robots
conn = init_db('data.db')
df = load_all_snapshots(conn)
with tempfile.TemporaryDirectory() as d:
    write_sitemap_and_robots(df, public_dir=d)
    import re
    text = open(pathlib.Path(d) / 'sitemap.xml').read()
    for line in text.splitlines():
        if '<loc>' in line and ('stats' in line or 'charts' in line or 'rising' in line or 'gems' in line or 'celebs' in line or 'hotmap.cam/<' in line):
            print(line.strip())
        if '<loc>https://hotmap.cam/</loc>' in line:
            print(line.strip())
"
```

Expected: shows current entries like `<loc>https://hotmap.cam/stats</loc>` (no slash). Confirms what we're changing.

- [ ] **Step 2: Write failing test**

Append to `tests/test_heatmap.py`:

```python
def test_sitemap_uses_trailing_slash_for_directory_urls(tmp_path):
    """Directory-style URLs in sitemap match what CF serves (with slash)."""
    df = _snapshot_rows()
    write_sitemap_and_robots(df, public_dir=tmp_path)
    text = (tmp_path / "sitemap.xml").read_text()

    for path in ("/rising/", "/gems/", "/celebs/", "/stats/", "/charts/"):
        assert f"<loc>https://hotmap.cam{path}</loc>" in text, \
            f"sitemap missing trailing-slash entry for {path}"
        # And the slash-less form is NOT present:
        bare = path.rstrip("/")
        assert f"<loc>https://hotmap.cam{bare}</loc>" not in text, \
            f"sitemap still has slash-less form for {path}"
    # Per-performer URLs stay slash-less.
    assert "<loc>https://hotmap.cam/p/alice</loc>" in text
```

- [ ] **Step 3: Confirm RED**

```bash
./venv/bin/pytest tests/test_heatmap.py::test_sitemap_uses_trailing_slash_for_directory_urls -v
```

Expected: failure.

- [ ] **Step 4: Update the sitemap writer**

In `heatmap.py`, find `write_sitemap_and_robots`. Identify the static URL list (the entries for `/`, `/rising`, `/gems`, `/celebs`, `/stats`, `/charts`). Update each directory-style entry to include the trailing slash. The home (`/`) and per-performer (`/p/<slug>`) entries do NOT change.

Concretely, replace string literals:
- `"/rising"` → `"/rising/"`
- `"/gems"` → `"/gems/"`
- `"/celebs"` → `"/celebs/"`
- `"/stats"` → `"/stats/"`
- `"/charts"` → `"/charts/"`

If the function uses a list of paths, edit that list. If it builds them with f-strings, edit those.

- [ ] **Step 5: Run new + existing sitemap tests**

```bash
./venv/bin/pytest tests/test_heatmap.py -k sitemap -v
```

Expected: all pass. If `test_write_sitemap_and_robots` (the existing one) fails on a substring check expecting the old form, update its assertion.

- [ ] **Step 6: Commit**

```bash
git add heatmap.py tests/test_heatmap.py
git commit -m "$(cat <<'EOF'
fix(seo): sitemap trailing slashes match served URL form

CF Pages serves /stats/ /charts/ /rising/ /gems/ /celebs/ with trailing
slashes (bare forms 307-redirect). Aligning sitemap + canonical with
what serves 200 removes a confusing crawl signal for Google.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Submission checklist + README

**Files:**
- Create: `/Users/ansvier/ph-heatmap/docs/seo-submission-checklist.md`
- Modify: `/Users/ansvier/ph-heatmap/README.md`

- [ ] **Step 1: Write the submission checklist**

Create `/Users/ansvier/ph-heatmap/docs/seo-submission-checklist.md`:

```markdown
# Search engine submission checklist

One-time manual setup after the SEO-baseline code change deploys. Steps
in order. Take note of verification tokens; if Cloudflare changes
ownership, you'll need to re-verify.

## Google Search Console

1. Open https://search.google.com/search-console
2. "Add property" → "Domain" → enter `hotmap.cam`
3. Google shows a TXT record to add. Open Cloudflare dashboard → hotmap.cam
   → DNS → Records → Add record. Type=TXT, Name=`@`, Content=the value
   Google gave you. TTL=Auto.
4. Wait 1-2 minutes, click "Verify" in GSC. Should succeed.
5. In GSC sidebar: Sitemaps → enter `sitemap.xml` → Submit.
6. Check back in 24-48 hours: Coverage report should show URLs starting
   to be indexed. Index → Pages.

## Bing Webmaster Tools

1. Open https://www.bing.com/webmasters
2. Sign in (Microsoft account).
3. "Add a site" → enter `https://hotmap.cam/`
4. Choose "Import from Google Search Console" if available — Bing accepts
   the GSC verification automatically. Otherwise add the TXT record Bing
   provides via the same CF DNS flow as step 3 above.
5. Sitemaps → enter `https://hotmap.cam/sitemap.xml` → Submit.

## Yandex Webmaster

**Skipped.** We don't target RF traffic, and registering with Yandex
ties the domain to a Russian agency's records. See the legal-risks
discussion notes for rationale.

## Verification

After 48 hours, sanity check that indexing is happening:

```bash
# Should return some results (or "no results yet" while indexing is in progress)
curl -s "https://www.google.com/search?q=site:hotmap.cam" | grep -c "hotmap.cam"
curl -s "https://www.bing.com/search?q=site:hotmap.cam" | grep -c "hotmap.cam"
```

If 0 results after a week, check GSC Coverage report for errors —
canonical mismatches and noindex tags are the usual suspects.

## Re-submission triggers

Re-submit the sitemap (in GSC + Bing) whenever:
- URL structure changes (new page types like categories, countries)
- Many pages added or removed in one day (>20% of total URLs)
- Site moves to a new domain

For daily snapshot updates (which only change `<lastmod>` in existing
URLs), no re-submission needed. Google re-crawls based on `changefreq`.
```

- [ ] **Step 2: Update README**

Open `/Users/ansvier/ph-heatmap/README.md`. Find the section that mentions SEO or schema.org (search for "Schema.org" or "sitemap" or "SEO"). Add or update the relevant paragraph to reflect new coverage:

Replace the line(s) describing SEO with:

```markdown
**SEO:** Every rendered page emits a complete head block — title, meta
description, canonical, Open Graph quintet, Twitter Cards triple, robots
meta, and JSON-LD (`WebSite` + `BreadcrumbList` + page-specific `Dataset`
/ `Person` / `CollectionPage`). Default OG image is `/og.png` (1200×630);
per-performer and stats pages use avatar fallbacks. Sitemap submitted to
Google Search Console and Bing Webmaster Tools (Yandex skipped — not
targeting RF). See `docs/seo-submission-checklist.md` for the submission
steps.
```

Also add a note to the local-development section that running `scripts/build_og.py` regenerates `public/og.png` if branding changes.

- [ ] **Step 3: Commit**

```bash
git add docs/seo-submission-checklist.md README.md
git commit -m "$(cat <<'EOF'
docs(seo): submission checklist + README baseline note

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: E2E render against real data + verify deploy

**Files:** none (re-renders into `public/` and pushes).

- [ ] **Step 1: Re-render all pages from existing data.db**

```bash
cd /Users/ansvier/ph-heatmap
./venv/bin/python -c "
from pathlib import Path
from db import init_db, load_all_snapshots
from heatmap import dump_json, render_charts_page, render_performer_page, render_stats_page, render_treemap_page, write_sitemap_and_robots

PUBLIC_DIR = Path('public')
DB_PATH = Path('data.db')
HTML_PATH = PUBLIC_DIR / 'index.html'
JSON_PATH = PUBLIC_DIR / 'data.json'
PERFORMER_DIR = PUBLIC_DIR / 'p'

conn = init_db(DB_PATH)
snapshots_df = load_all_snapshots(conn)
print(f'loaded {len(snapshots_df)} rows from db', flush=True)

render_treemap_page(snapshots_df, HTML_PATH, default_mode='rising', canonical_path='/', seo_key='home')
print(f'wrote {HTML_PATH}', flush=True)
for mode in ('rising', 'gems', 'celebs'):
    mode_dir = PUBLIC_DIR / mode
    mode_dir.mkdir(exist_ok=True)
    render_treemap_page(snapshots_df, mode_dir / 'index.html', default_mode=mode, canonical_path=f'/{mode}/', seo_key=mode)
    print(f'wrote /{mode}/index.html', flush=True)
dump_json(snapshots_df, JSON_PATH)
print(f'wrote {JSON_PATH}', flush=True)

PERFORMER_DIR.mkdir(parents=True, exist_ok=True)
written = 0
for slug in snapshots_df['slug'].unique():
    try:
        render_performer_page(snapshots_df, slug=slug, output_path=PERFORMER_DIR / f'{slug}.html')
        written += 1
    except Exception as exc:
        print(f'  WARN: performer page failed for {slug}: {exc}')
print(f'wrote {written} performer pages')

stats_dir = PUBLIC_DIR / 'stats'
stats_dir.mkdir(exist_ok=True)
render_stats_page(snapshots_df, stats_dir / 'index.html')
print('wrote /stats/index.html')

charts_dir = PUBLIC_DIR / 'charts'
charts_dir.mkdir(exist_ok=True)
render_charts_page(snapshots_df, charts_dir / 'index.html')
print('wrote /charts/index.html')

write_sitemap_and_robots(snapshots_df, public_dir=PUBLIC_DIR)
print('wrote sitemap.xml + robots.txt')
"
```

Expected: all "wrote …" lines, no exceptions. ~14 sec.

- [ ] **Step 2: Smoke check the rendered home page**

```bash
grep -oE '<title>[^<]+</title>' public/index.html
grep -oE 'og:image[^>]+content="[^"]+"' public/index.html
grep -c 'application/ld+json' public/index.html
```

Expected:
- Title line containing "HotMap"
- og:image pointing to `https://hotmap.cam/og.png`
- JSON-LD block count: 2 (WebSite + Dataset on home; mode pages would have 3 including Breadcrumbs)

- [ ] **Step 3: Smoke check `/stats/`**

```bash
grep -oE 'canonical[^>]+href="[^"]+"' public/stats/index.html
grep -c 'application/ld+json' public/stats/index.html
```

Expected:
- canonical URL is `https://hotmap.cam/stats/` (with trailing slash)
- JSON-LD block count: 3 (WebSite + CollectionPage + BreadcrumbList)

- [ ] **Step 4: Smoke check sitemap**

```bash
grep -E '<loc>https://hotmap.cam/(rising|gems|celebs|stats|charts)/?</loc>' public/sitemap.xml
```

Expected: 5 lines, all with trailing slash, e.g. `<loc>https://hotmap.cam/stats/</loc>`.

- [ ] **Step 5: Commit re-render**

```bash
git status -s | head -5
git add public/
git commit -m "$(cat <<'EOF'
chore(render): re-render with SEO baseline applied

All pages now emit through _render_seo_head(): complete OG + Twitter +
JSON-LD coverage, trailing-slash canonicals for directory URLs.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 6: Push**

```bash
git pull --rebase origin main
git push
```

Expected: push succeeds. Cloudflare Pages auto-deploys ~30-60 sec later.

- [ ] **Step 7: Verify live (after deploy)**

Wait 60 seconds, then:

```bash
echo "=== home og:image ==="
curl -s https://hotmap.cam/ | grep -oE 'og:image[^>]+content="[^"]+"' | head -1
echo "=== /stats/ canonical ==="
curl -sL https://hotmap.cam/stats/ | grep -oE 'canonical[^>]+href="[^"]+"' | head -1
echo "=== JSON-LD count on /stats/ ==="
curl -sL https://hotmap.cam/stats/ | grep -c 'application/ld+json'
echo "=== sitemap entries ==="
curl -s https://hotmap.cam/sitemap.xml | grep -E '/(rising|gems|celebs|stats|charts)/?</loc>' | head -5
```

Expected:
- home og:image → `https://hotmap.cam/og.png`
- /stats/ canonical → `https://hotmap.cam/stats/`
- /stats/ JSON-LD count → 3
- 5 sitemap lines all with trailing slash

If any check fails, the change didn't deploy fully. Re-check `git log origin/main..` is empty (no unpushed commits) and CF Pages dashboard for deploy status.

- [ ] **Step 8: Submit to GSC + Bing (manual, off-protocol)**

Follow `docs/seo-submission-checklist.md`. This is a one-time human-side task; not part of the engineering work. Mark this step done after GSC shows the property as verified and the sitemap as submitted.

---

## Self-review checklist (filled out by plan author)

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| Static og.png (1200×630) | Task 1 |
| `_render_seo_head()` helper signature + behavior | Task 2 |
| Page-type matrix (home, mode, stats, charts, performer) | Tasks 3-6 (one each) |
| Trailing-slash canonical for directory URLs | Tasks 3, 5, 6 |
| Sitemap trailing-slash | Task 7 |
| Submission checklist (GSC + Bing, skip Yandex) | Task 8 |
| README update | Task 8 |
| All page types produce complete head block | Tasks 3-6 + new tests in each |

No gaps.

**Placeholder scan:** No TBD / TODO / "implement later". Every step has either complete code or an exact command with expected output.

**Type consistency:** `_render_seo_head` signature is identical in Task 2's tests, Task 2's implementation, and the four refactor tasks (3-6). `page_type` values match across tests and implementation. Breadcrumb tuple format (name, url) is consistent.

**Conditional risk note:** Task 3 Step 8 may require updating substring assertions in the existing `test_render_treemap_page_writes_html`. Tasks 4-6 may require similar updates in their existing per-page tests. Engineer should treat substring drift as expected (helper output is a superset of old inline blocks) and widen assertions rather than break the helper.

**One-line manual step:** Task 9 Step 8 (GSC + Bing submission) is the only step that can't be code-verified by the engineer — it's a UI flow on third-party sites. The checklist file documents exactly what to click.
