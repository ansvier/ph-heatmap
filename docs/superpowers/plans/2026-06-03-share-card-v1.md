# Share Card v1 — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the existing `Save image (PNG)` button's chrome-screenshot output with a 1200×630 trading-style share card on all 18 treemap-bearing pages (main mode pages, country pages, categories).

**Architecture:** Three new module-level string constants in `heatmap.py` — `_SHARE_CARD_CSS`, `_SHARE_CARD_HTML`, `_SHARE_CARD_JS` — get injected into `_PAGE_TEMPLATE`, `_COUNTRY_PAGE_TEMPLATE`, and `_CATEGORIES_PAGE_TEMPLATE` via new format placeholders. A single client-side `buildShareCard()` function reads `<body data-page-type>` and DOM data attributes to populate the card's slots, clones the currently-visible Plotly panel into the right column, picks a random background, and hands the card to the existing html2canvas → download pipeline.

**Tech Stack:** Python 3.13 string formatting, vanilla JS (no new libs), html2canvas (already on main pages, newly loaded on country/categories pages), pytest.

**Spec:** `docs/superpowers/specs/2026-06-03-share-card-v1-design.md`

---

## File map

| Path | Purpose | Tasks |
|---|---|---|
| `heatmap.py` | `_SHARE_CARD_CSS` / `_HTML` / `_JS` constants; `{share_card_*}` placeholders in 3 templates; body `data-*` wiring; `_top_category_meta` helper for categories | Tasks 1-3 |
| `tests/test_heatmap.py` | One test per page type asserting share-card wiring + a regression on the old save-flow removal | Tasks 1-3 |
| `README.md` | One-paragraph note about the upgraded Save image flow | Task 4 |
| `public/share-bg/` | Empty directory, file presence checked at deploy time | Task 4 |

No new Python modules. No new dependencies. No DB changes.

---

### Task 1: Share-card scaffolding + wire into main treemap page

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/heatmap.py`
- Modify: `/Users/ansvier/ph-heatmap/tests/test_heatmap.py`

This task introduces the three string constants AND wires them into the main treemap page (`_PAGE_TEMPLATE`, used by `render_treemap_page`). Country and categories pages get the same wiring in Tasks 2 and 3.

- [ ] **Step 1: Write the failing tests**

Append to `/Users/ansvier/ph-heatmap/tests/test_heatmap.py`:

```python
def test_main_treemap_page_has_share_card_wiring(tmp_path):
    """render_treemap_page emits the .share-card hidden div, buildShareCard JS,
    data-page-type='main' on body, and a /share-bg/ background URL reference."""
    df = _snapshot_rows()
    out = tmp_path / "out.html"
    render_treemap_page(df, out)
    content = out.read_text()

    # Hidden share card composition
    assert 'class="share-card"' in content
    assert 'class="share-card-brand-strip"' in content
    assert 'class="share-card-mode-label"' in content
    assert 'class="share-card-top-name"' in content
    assert 'class="share-card-treemap-slot"' in content
    assert 'class="share-card-footer"' in content

    # JS function + page-type wiring
    assert 'function buildShareCard' in content
    assert 'data-page-type="main"' in content
    assert 'data-updated-at=' in content
    assert "/share-bg/bg-" in content


def test_main_treemap_page_save_button_uses_build_share_card(tmp_path):
    """Save Image click handler invokes buildShareCard, not the old hero+panel
    DOM clone."""
    df = _snapshot_rows()
    out = tmp_path / "out.html"
    render_treemap_page(df, out)
    content = out.read_text()

    # Old literal-screenshot path is gone — no clone of .hero
    assert "document.querySelector('.hero').cloneNode" not in content
    # New path is in
    assert "buildShareCard()" in content
```

- [ ] **Step 2: Run tests, confirm RED**

```bash
cd /Users/ansvier/ph-heatmap
./venv/bin/pytest tests/test_heatmap.py -k "share_card_wiring or save_button_uses_build" -v
```

Expected: both tests fail — `share-card` substring absent, `buildShareCard` absent, `data-page-type` absent.

- [ ] **Step 3: Add `_SHARE_CARD_CSS` constant**

In `/Users/ansvier/ph-heatmap/heatmap.py`, add after the existing `_NAV_ITEMS` / `_top_nav` block (around line 50, before any `_PAGE_TEMPLATE` definition). Find a clean insertion point with `grep -n "^_PAGE_TEMPLATE\|^_TOP_NAV_CSS" heatmap.py` — place `_SHARE_CARD_*` constants right before the first page template that uses them.

```python
# ---- Share Card v1 ---------------------------------------------------------
# Three string constants — CSS, HTML, JS — injected into every treemap-bearing
# page template via {share_card_css}, {share_card_html}, {share_card_js}
# placeholders. The constants themselves use SINGLE braces (no .format escaping)
# because they're inserted as raw values, not formatted. The on-page Save Image
# button now invokes buildShareCard() instead of capturing .hero + .panel.active
# as a literal screenshot. See docs/superpowers/specs/2026-06-03-share-card-v1-design.md.

_SHARE_CARD_CSS = """
    .share-card {
      position: fixed;
      top: -99999px;
      left: 0;
      width: 1200px;
      height: 630px;
      background-color: #0a0a0a;
      background-size: cover;
      background-position: center;
      font-family: 'Inter', sans-serif;
      color: #f5f5f5;
      overflow: hidden;
    }
    .share-card-overlay {
      position: absolute;
      inset: 0;
      background: linear-gradient(135deg, rgba(10,10,10,0.85), rgba(10,10,10,0.55));
      pointer-events: none;
    }
    .share-card-content {
      position: relative;
      z-index: 1;
      width: 100%;
      height: 100%;
      display: flex;
      flex-direction: column;
      padding: 0 24px;
      box-sizing: border-box;
    }
    .share-card-brand-strip {
      flex: 0 0 56px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .share-card-path {
      font-family: ui-monospace, 'SF Mono', monospace;
      font-size: 16px;
      color: #f5f5f5;
    }
    .share-card-brand-strip svg {
      height: 36px;
    }
    .share-card-main {
      flex: 1 1 auto;
      display: flex;
      gap: 32px;
      padding-bottom: 12px;
    }
    .share-card-left {
      flex: 0 0 480px;
      display: flex;
      flex-direction: column;
      justify-content: center;
      gap: 24px;
    }
    .share-card-mode-label {
      font-size: 32px;
      font-weight: 800;
      letter-spacing: 1px;
      text-transform: uppercase;
      line-height: 1.1;
    }
    .share-card-filter {
      font-size: 16px;
      color: #9a9a9a;
      font-weight: 500;
      margin-top: -16px;
    }
    .share-card-top-mover {
      display: flex;
      gap: 16px;
      align-items: flex-start;
      background: rgba(0,0,0,0.55);
      border: 1px solid rgba(255,255,255,0.06);
      border-left: 3px solid #ff9000;
      padding: 16px 20px;
      border-radius: 10px;
    }
    .share-card-photo {
      width: 56px;
      height: 56px;
      border-radius: 50%;
      flex-shrink: 0;
      background: #222;
      overflow: hidden;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #fff;
      font-weight: 800;
      font-size: 22px;
    }
    .share-card-photo img {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }
    .share-card-mover-text {
      display: flex;
      flex-direction: column;
      gap: 4px;
      min-width: 0;
    }
    .share-card-top-name {
      font-size: 24px;
      font-weight: 700;
      line-height: 1.2;
    }
    .share-card-top-label {
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 1.5px;
      text-transform: uppercase;
      color: #ff9000;
    }
    .share-card-top-growth {
      font-size: 40px;
      font-weight: 800;
      color: #6cd36a;
      line-height: 1;
      margin-top: 4px;
    }
    .share-card-top-delta {
      font-size: 14px;
      color: #9a9a9a;
    }
    .share-card-right {
      flex: 1 1 640px;
      background: rgba(0,0,0,0.5);
      border-radius: 10px;
      padding: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
    }
    .share-card-treemap-slot {
      width: 100%;
      height: 100%;
    }
    /* Hide Plotly's colorbar/legend inside the slot — clean signature visual */
    .share-card-treemap-slot .plotly .colorbar { display: none !important; }
    .share-card-treemap-slot .modebar-container { display: none !important; }
    .share-card-footer {
      flex: 0 0 46px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 12px;
      color: #9a9a9a;
    }
    /* Save Image button used on country + categories pages (the main page
       has it inside the existing Share dropdown). */
    .save-image-btn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 12px;
      background: #161616;
      border: 1px solid #1f1f1f;
      border-radius: 6px;
      color: #f5f5f5;
      font-family: inherit;
      font-size: 13px;
      cursor: pointer;
      margin: 0 0 16px;
    }
    .save-image-btn:hover { border-color: #ff9000; color: #ff9000; }
    .save-image-btn[disabled] { opacity: 0.5; cursor: not-allowed; }
"""
```

- [ ] **Step 4: Add `_SHARE_CARD_HTML` constant**

In the same neighborhood (after `_SHARE_CARD_CSS`), add:

```python
_SHARE_CARD_HTML = """
<div class="share-card" aria-hidden="true">
  <div class="share-card-overlay"></div>
  <div class="share-card-content">
    <div class="share-card-brand-strip">
      <div class="share-card-path"></div>
      <svg width="160" height="40" viewBox="0 0 400 100" role="img" aria-label="HotMap">
        <rect width="400" height="100" fill="#000"/>
        <text x="20" y="78" font-family="'Arial Black','Helvetica Neue',Helvetica,Arial,sans-serif" font-weight="900" font-size="76" fill="#fff" letter-spacing="-3">HOT</text>
        <rect x="198" y="14" width="184" height="72" rx="14" fill="#ff9000"/>
        <text x="214" y="72" font-family="'Arial Black','Helvetica Neue',Helvetica,Arial,sans-serif" font-weight="900" font-size="60" fill="#000" letter-spacing="-3">MAP</text>
      </svg>
    </div>
    <div class="share-card-main">
      <div class="share-card-left">
        <div class="share-card-mode-label"></div>
        <div class="share-card-filter"></div>
        <div class="share-card-top-mover">
          <div class="share-card-photo"></div>
          <div class="share-card-mover-text">
            <div class="share-card-top-label">TOP MOVER TODAY</div>
            <div class="share-card-top-name"></div>
            <div class="share-card-top-growth"></div>
            <div class="share-card-top-delta"></div>
          </div>
        </div>
      </div>
      <div class="share-card-right">
        <div class="share-card-treemap-slot"></div>
      </div>
    </div>
    <div class="share-card-footer">
      <div class="share-card-footer-left"></div>
      <div class="share-card-footer-right"></div>
    </div>
  </div>
</div>
"""
```

- [ ] **Step 5: Add `_SHARE_CARD_JS` constant**

```python
_SHARE_CARD_JS = """
  // Share Card v1 — build the 1200x630 card from current page state.
  // Reads <body data-page-type=main|country|category>, finds the active
  // top-perf element and the live Plotly panel, populates the hidden
  // .share-card div, then hands it to html2canvas for download. The card
  // background rotates between three /share-bg/bg-{1,2,3}.jpg files; if
  // none are present (or load fails), the flat #0a0a0a background under
  // the gradient overlay still produces a clean card.
  var MODE_LABELS = {
    rising: 'RISING STARS',
    gems: 'HIDDEN GEMS',
    celebs: 'CELEBRITIES'
  };
  var GENDER_LABELS = {
    all: 'All performers',
    female: 'Female',
    male: 'Male'
  };

  function buildShareCard() {
    var card = document.querySelector('.share-card');
    if (!card) return null;

    var pageType = document.body.dataset.pageType || 'main';
    var updatedAt = document.body.dataset.updatedAt || '';
    var contextLabel = document.body.dataset.contextLabel || '';
    var trackedCount = document.body.dataset.trackedCount || '';
    var trackedLabel = document.body.dataset.trackedLabel || 'performers tracked';

    // Brand strip path
    card.querySelector('.share-card-path').textContent =
      window.location.host + window.location.pathname;

    // Mode label + filter chip (page-type-specific)
    var modeLabelEl = card.querySelector('.share-card-mode-label');
    var filterEl = card.querySelector('.share-card-filter');
    if (pageType === 'main' && typeof state !== 'undefined') {
      modeLabelEl.textContent = MODE_LABELS[state.mode] || 'HOTMAP';
      var windowText = state.window + ' day' + (state.window > 1 ? 's' : '');
      filterEl.textContent = (GENDER_LABELS[state.gender] || '') + ' · ' + windowText;
    } else if (pageType === 'country') {
      modeLabelEl.textContent = (contextLabel || 'COUNTRY').toUpperCase();
      filterEl.textContent = '';
    } else if (pageType === 'category') {
      modeLabelEl.textContent = 'TRENDING CATEGORIES';
      filterEl.textContent = '';
    } else {
      modeLabelEl.textContent = 'HOTMAP';
      filterEl.textContent = '';
    }

    // Top-mover mini-card
    var photoEl = card.querySelector('.share-card-photo');
    var nameEl = card.querySelector('.share-card-top-name');
    var growthEl = card.querySelector('.share-card-top-growth');
    var deltaEl = card.querySelector('.share-card-top-delta');
    var topMoverEl = card.querySelector('.share-card-top-mover');

    photoEl.innerHTML = '';
    nameEl.textContent = '';
    growthEl.textContent = '';
    deltaEl.textContent = '';

    if (pageType === 'category') {
      var catMeta = document.getElementById('share-card-top-category');
      if (catMeta && catMeta.dataset.name) {
        photoEl.style.background = '#ff9000';
        photoEl.style.color = '#000';
        photoEl.textContent = catMeta.dataset.name.charAt(0);
        nameEl.textContent = catMeta.dataset.name;
        growthEl.textContent = catMeta.dataset.deltaLabel || '';
        deltaEl.textContent = '';
      } else {
        topMoverEl.style.display = 'none';
      }
    } else {
      var activePerf = document.querySelector('.top-perf.active');
      if (activePerf) {
        var img = activePerf.querySelector('img');
        if (img && img.src) {
          var newImg = document.createElement('img');
          newImg.src = img.src;
          newImg.alt = '';
          newImg.referrerPolicy = 'no-referrer';
          photoEl.appendChild(newImg);
        } else {
          photoEl.style.background = '#ff9000';
          photoEl.style.color = '#000';
          var nm = activePerf.querySelector('.top-perf-name');
          photoEl.textContent = nm ? nm.textContent.charAt(0) : '?';
        }
        var nm2 = activePerf.querySelector('.top-perf-name');
        nameEl.textContent = nm2 ? nm2.textContent : '';
        // First .top-perf-stat-row strong = "Today: +X%"
        var firstRow = activePerf.querySelector('.top-perf-stat-row strong');
        if (firstRow) {
          growthEl.textContent = firstRow.textContent;
        } else {
          // Fallback to the .top-perf-stat aggregate when acceleration isn't available
          var agg = activePerf.querySelector('.top-perf-stat strong');
          if (agg) growthEl.textContent = agg.textContent;
        }
        // Second stat row OR the caption gives extra context
        var rows = activePerf.querySelectorAll('.top-perf-stat-row');
        if (rows.length > 1) {
          var usualText = rows[1].textContent;
          deltaEl.textContent = usualText;
        }
      } else {
        topMoverEl.style.display = 'none';
      }
    }

    // Treemap: clone the live Plotly panel into the right column.
    var slot = card.querySelector('.share-card-treemap-slot');
    slot.innerHTML = '';
    var sourcePanel = null;
    if (pageType === 'main') {
      sourcePanel = document.querySelector('.panel.active');
    } else {
      var pg = document.querySelector('.plotly-graph-div');
      if (pg) sourcePanel = pg.parentElement;
    }
    if (sourcePanel) {
      slot.appendChild(sourcePanel.cloneNode(true));
    }

    // Random background — best-effort. If the file 404s the gradient overlay
    // still renders the card cleanly on flat #0a0a0a.
    var bgIdx = 1 + Math.floor(Math.random() * 3);
    card.style.backgroundImage = "url('/share-bg/bg-" + bgIdx + ".jpg')";

    // Footer
    card.querySelector('.share-card-footer-left').textContent =
      updatedAt ? 'Updated ' + updatedAt : '';
    card.querySelector('.share-card-footer-right').textContent =
      trackedCount ? trackedCount + ' ' + trackedLabel : '';

    return card;
  }

  function saveShareCardImage(filename) {
    if (typeof html2canvas === 'undefined') {
      alert('Share library still loading — try again in a second.');
      return;
    }
    if (!document.querySelector('.plotly-graph-div')) {
      alert('Treemap still loading — try again in a moment.');
      return;
    }
    var card = buildShareCard();
    if (!card) return;
    html2canvas(card, { backgroundColor: '#0a0a0a', scale: 2, useCORS: true })
      .then(function (canvas) {
        var link = document.createElement('a');
        link.download = filename;
        link.href = canvas.toDataURL('image/png');
        link.click();
      })
      .catch(function (err) {
        console.error('Save failed:', err);
        alert('Could not generate image. See console.');
      });
  }
"""
```

- [ ] **Step 6: Wire share card into `_PAGE_TEMPLATE`**

Find `_PAGE_TEMPLATE` in heatmap.py (`grep -n "^_PAGE_TEMPLATE = " heatmap.py`). It's the main treemap page template, used by `render_treemap_page`. Apply 4 edits:

**6a.** Add the share-card CSS placeholder inside the `<style>` block. Find a clean insertion point near the end of the style block (just before `</style>`) and add a line:

```
{share_card_css}
```

**6b.** Add `data-page-type="main"` and `data-updated-at="{last_updated}"` and `data-tracked-count="{n_performers}"` and `data-tracked-label="performers tracked"` to the `<body>` tag.

Find the existing `<body>` tag in `_PAGE_TEMPLATE` and change:

```html
<body>
```

to:

```html
<body data-page-type="main" data-updated-at="{last_updated}" data-tracked-count="{n_performers}" data-tracked-label="performers tracked">
```

(`{last_updated}` and `{n_performers}` are already passed to `.format(...)` by `render_treemap_page` — verify by searching for `last_updated=` in the function.)

**6c.** Insert `{share_card_html}` just before `</body>`:

```html
{share_card_html}
</body>
```

**6d.** In the `<script>` block (the one with the existing toggle/share JS), insert `{share_card_js}` near the top, BEFORE the existing `shareSave.addEventListener` block. Then replace the entire body of the existing `shareSave.addEventListener('click', function () { ... })` callback with:

```javascript
shareSave.addEventListener('click', function () {
  var stamp = new Date().toISOString().slice(0, 10);
  var filename = 'hotmap-' + state.mode + '-' + state.gender + '-' + state.window + 'd-' + stamp + '.png';
  shareToggle.classList.add('busy');
  Promise.resolve().then(function () { saveShareCardImage(filename); })
    .finally(function () { shareToggle.classList.remove('busy'); });
});
```

(The old code that cloned `.hero` and `.panel.active` into a temporary wrap div is removed entirely.)

- [ ] **Step 7: Update `render_treemap_page` to pass the new format kwargs**

Find `render_treemap_page` (`grep -n "^def render_treemap_page" heatmap.py`). At the bottom of the function, locate the `.format(...)` call that fills the template. Add three new kwargs:

```python
        share_card_css=_SHARE_CARD_CSS,
        share_card_html=_SHARE_CARD_HTML,
        share_card_js=_SHARE_CARD_JS,
```

If `n_performers` isn't already computed and passed to `.format()`, add it. It's `int(snapshots["slug"].nunique())` computed from the input dataframe.

- [ ] **Step 8: Run failing tests, confirm GREEN**

```bash
./venv/bin/pytest tests/test_heatmap.py -k "share_card_wiring or save_button_uses_build" -v
```

Expected: both new tests pass.

- [ ] **Step 9: Run full suite to catch regressions**

```bash
./venv/bin/pytest -q
```

Expected: 108 passed (106 baseline + 2 new). Existing `test_render_treemap_page_writes_html` should still pass because the share card is invisible (`top: -99999px`) and doesn't break the 27 panels logic.

- [ ] **Step 10: Commit**

```bash
git add heatmap.py tests/test_heatmap.py
git commit -m "$(cat <<'EOF'
feat(heatmap): Share Card v1 — main treemap page

Replaces the chrome-screenshot Save Image flow with a 1200x630 trading-
style share card. Two-column layout: brand+mode+top-mover mini-card on
the left, currently-active Plotly panel cloned into the right. Random
background from /share-bg/bg-{1,2,3}.jpg per click. Reflects the user's
current toggle state (mode/gender/window).

Three new module-level constants — _SHARE_CARD_CSS, _SHARE_CARD_HTML,
_SHARE_CARD_JS — injected into _PAGE_TEMPLATE via new placeholders.
buildShareCard() reads body data-attrs and DOM state to populate slots;
saveShareCardImage() wraps html2canvas + download. Old hero+panel clone
path removed.

Country pages and /categories/ get the same wiring in Tasks 2 and 3.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Wire share card into country pages

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/heatmap.py` (`_COUNTRY_PAGE_TEMPLATE`, `render_country_page`)
- Modify: `/Users/ansvier/ph-heatmap/tests/test_heatmap.py`

- [ ] **Step 1: Write the failing test**

Append to `/Users/ansvier/ph-heatmap/tests/test_heatmap.py`:

```python
def test_country_page_has_share_card_wiring(tmp_path):
    """render_country_page emits .share-card, save button, html2canvas script,
    data-page-type='country', and data-context-label with the country name."""
    df = _country_snapshots_fixture()
    out = tmp_path / "russia.html"
    render_country_page(df, "Russia", out)
    content = out.read_text()

    assert 'class="share-card"' in content
    assert 'function buildShareCard' in content
    assert 'data-page-type="country"' in content
    assert 'data-context-label="Russia"' in content
    assert 'data-updated-at=' in content
    assert 'class="save-image-btn"' in content
    assert "/share-bg/bg-" in content
    # html2canvas needs to be loaded — country page didn't have it before
    assert "html2canvas" in content
```

- [ ] **Step 2: Run test, confirm RED**

```bash
./venv/bin/pytest tests/test_heatmap.py::test_country_page_has_share_card_wiring -v
```

Expected: assertion failures for all the missing substrings.

- [ ] **Step 3: Add html2canvas script tag to `_COUNTRY_PAGE_TEMPLATE`**

In heatmap.py, find `_COUNTRY_PAGE_TEMPLATE` (`grep -n "^_COUNTRY_PAGE_TEMPLATE = " heatmap.py`). In the `<head>` section (around the existing `<link rel="preconnect"...>` lines), add:

```html
  <script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js" defer></script>
```

- [ ] **Step 4: Inject share-card CSS placeholder**

Inside `_COUNTRY_PAGE_TEMPLATE`'s `<style>` block, find a clean insertion point near the end (just before `</style>`) and add a line:

```
{share_card_css}
```

- [ ] **Step 5: Add body data attributes**

Find the `<body>` tag in `_COUNTRY_PAGE_TEMPLATE` and change:

```html
<body>
```

to:

```html
<body data-page-type="country" data-context-label="{country_name}" data-updated-at="{last_updated}" data-tracked-count="{n_performers}" data-tracked-label="performers tracked">
```

- [ ] **Step 6: Add Save Image button + share-card HTML**

In `_COUNTRY_PAGE_TEMPLATE`, find the subtitle line:

```html
<p class="subtitle">{n_performers} performers tracked · Updated {last_updated} UTC</p>
```

After it, add a Save button:

```html
<p class="subtitle">{n_performers} performers tracked · Updated {last_updated} UTC</p>
<button type="button" class="save-image-btn" id="save-image-btn"><span aria-hidden="true">⤓</span> Save image (PNG)</button>
```

Then, just before `</body>`, add the share-card HTML placeholder:

```html
{share_card_html}
</body>
```

- [ ] **Step 7: Add the share-card JS + click handler script**

In `_COUNTRY_PAGE_TEMPLATE`, right before `</body>` (after `{share_card_html}`), add a `<script>` block:

```html
<script>
{share_card_js}
  // Wire the Save Image button to saveShareCardImage.
  (function () {{
    var btn = document.getElementById('save-image-btn');
    if (!btn) return;
    btn.addEventListener('click', function () {{
      var slug = '{country_slug}';
      var stamp = new Date().toISOString().slice(0, 10);
      var filename = 'hotmap-country-' + slug + '-' + stamp + '.png';
      btn.disabled = true;
      Promise.resolve().then(function () {{ saveShareCardImage(filename); }})
        .finally(function () {{ setTimeout(function () {{ btn.disabled = false; }}, 1500); }});
    }});
  }})();
</script>
```

Note the `{{` / `}}` — these are escapes because the template is `.format()`-ed. The `{share_card_js}` and `{country_slug}` placeholders use single braces.

- [ ] **Step 8: Update `render_country_page` to pass the new kwargs**

Find `render_country_page` in heatmap.py. The function already computes `slug = _country_slug(country_name)`. At the `.format(...)` call near the end, add:

```python
        share_card_css=_SHARE_CARD_CSS,
        share_card_html=_SHARE_CARD_HTML,
        share_card_js=_SHARE_CARD_JS,
        country_slug=slug,
```

- [ ] **Step 9: Run failing test, confirm GREEN**

```bash
./venv/bin/pytest tests/test_heatmap.py::test_country_page_has_share_card_wiring -v
```

Expected: PASS.

- [ ] **Step 10: Full suite**

```bash
./venv/bin/pytest -q
```

Expected: 109 passed.

- [ ] **Step 11: Commit**

```bash
git add heatmap.py tests/test_heatmap.py
git commit -m "$(cat <<'EOF'
feat(heatmap): Share Card v1 — country pages

/country/<slug>/ pages get the same share-card composition. Adds a
"Save image (PNG)" button under the subtitle, the html2canvas script,
and a small inline <script> that wires the button to the shared
saveShareCardImage() helper. Body gains data-page-type="country" and
data-context-label="<Country Name>" so buildShareCard knows what to
render in the left column.

Filename: hotmap-country-<slug>-YYYY-MM-DD.png.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Wire share card into categories page

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/heatmap.py` (`_CATEGORIES_PAGE_TEMPLATE`, `render_categories_treemap`)
- Modify: `/Users/ansvier/ph-heatmap/tests/test_heatmap.py`

Categories don't have performer photos, so the left-column mini-card uses a brand-orange block + first letter of the category name instead. The top category (by 1-day delta) gets baked into a hidden `<div id="share-card-top-category">` on render.

- [ ] **Step 1: Write the failing test**

Append to `/Users/ansvier/ph-heatmap/tests/test_heatmap.py`:

```python
def test_categories_page_has_share_card_wiring_and_top_meta(tmp_path):
    """render_categories_treemap emits .share-card + the hidden #share-card-top-category
    meta div with the day's top-mover category and delta label."""
    df = _category_snapshots_fixture(with_baseline=True)
    out = tmp_path / "categories.html"
    render_categories_treemap(df, out)
    content = out.read_text()

    assert 'class="share-card"' in content
    assert 'function buildShareCard' in content
    assert 'data-page-type="category"' in content
    assert 'data-updated-at=' in content
    assert 'class="save-image-btn"' in content
    assert "/share-bg/bg-" in content
    assert "html2canvas" in content

    # Hidden meta div with top category
    assert 'id="share-card-top-category"' in content
    assert 'data-name=' in content
    assert 'data-delta-label=' in content
```

- [ ] **Step 2: Run test, confirm RED**

```bash
./venv/bin/pytest tests/test_heatmap.py::test_categories_page_has_share_card_wiring_and_top_meta -v
```

Expected: multiple assertion failures.

- [ ] **Step 3: Add html2canvas script tag to `_CATEGORIES_PAGE_TEMPLATE`**

In heatmap.py, find `_CATEGORIES_PAGE_TEMPLATE` (`grep -n "^_CATEGORIES_PAGE_TEMPLATE = " heatmap.py`). In the `<head>` section, add:

```html
  <script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js" defer></script>
```

- [ ] **Step 4: Inject share-card CSS placeholder**

Inside the `<style>` block, near the end (just before `</style>`), add:

```
{share_card_css}
```

- [ ] **Step 5: Add body data attributes**

Find the `<body>` tag in `_CATEGORIES_PAGE_TEMPLATE` and change:

```html
<body>
```

to:

```html
<body data-page-type="category" data-updated-at="{last_updated}" data-tracked-count="{n_categories}" data-tracked-label="categories tracked">
```

- [ ] **Step 6: Add Save Image button + share-card HTML + top-category meta**

In `_CATEGORIES_PAGE_TEMPLATE`, find the subtitle line:

```html
<p class="subtitle">{n_categories} categories tracked · Updated {last_updated} UTC</p>
```

Replace with:

```html
<p class="subtitle">{n_categories} categories tracked · Updated {last_updated} UTC</p>
<button type="button" class="save-image-btn" id="save-image-btn"><span aria-hidden="true">⤓</span> Save image (PNG)</button>
<div id="share-card-top-category" data-name="{top_category_name}" data-delta-label="{top_category_delta_label}" hidden></div>
```

Then, just before `</body>`, add:

```html
{share_card_html}
<script>
{share_card_js}
  (function () {{
    var btn = document.getElementById('save-image-btn');
    if (!btn) return;
    btn.addEventListener('click', function () {{
      var stamp = new Date().toISOString().slice(0, 10);
      var filename = 'hotmap-categories-' + stamp + '.png';
      btn.disabled = true;
      Promise.resolve().then(function () {{ saveShareCardImage(filename); }})
        .finally(function () {{ setTimeout(function () {{ btn.disabled = false; }}, 1500); }});
    }});
  }})();
</script>
</body>
```

- [ ] **Step 7: Compute top category in `render_categories_treemap`**

Find `render_categories_treemap` in heatmap.py. After the existing `today` / `prior_dates` / delta computation block (look for where `today["delta"]` is populated), add:

```python
    # Top-mover category for the share card (largest 1-day delta among the
    # genre cohort). When no baseline available, falls back to highest video_count.
    if "delta" in today.columns and today["delta"].notna().any():
        top_cat_row = today.sort_values("delta", ascending=False).iloc[0]
        top_category_name = str(top_cat_row["name"])
        delta_val = top_cat_row["delta"]
        if pd.notna(delta_val) and delta_val != 0:
            sign = "+" if delta_val > 0 else ""
            top_category_delta_label = f"{sign}{int(delta_val):,} videos today"
        else:
            top_category_delta_label = "no change today"
    else:
        top_cat_row = today.sort_values("video_count", ascending=False).iloc[0]
        top_category_name = str(top_cat_row["name"])
        top_category_delta_label = f"{int(top_cat_row['video_count']):,} videos"
```

- [ ] **Step 8: Pass new kwargs into `.format()`**

In the same `render_categories_treemap` function, find the `.format(...)` call. Add:

```python
        share_card_css=_SHARE_CARD_CSS,
        share_card_html=_SHARE_CARD_HTML,
        share_card_js=_SHARE_CARD_JS,
        top_category_name=_html.escape(top_category_name),
        top_category_delta_label=_html.escape(top_category_delta_label),
```

- [ ] **Step 9: Run failing test, confirm GREEN**

```bash
./venv/bin/pytest tests/test_heatmap.py::test_categories_page_has_share_card_wiring_and_top_meta -v
```

Expected: PASS.

- [ ] **Step 10: Full suite**

```bash
./venv/bin/pytest -q
```

Expected: 110 passed.

- [ ] **Step 11: Commit**

```bash
git add heatmap.py tests/test_heatmap.py
git commit -m "$(cat <<'EOF'
feat(heatmap): Share Card v1 — categories page

/categories/ gets the same share-card composition with one variation:
the left-column mini-card uses an orange initial-letter block instead
of a performer photo (categories have no avatars). The day's top-mover
category (by 1-day delta, fallback to highest video_count) is computed
in render_categories_treemap and baked into a hidden meta div that
buildShareCard reads at click time.

Filename: hotmap-categories-YYYY-MM-DD.png.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: README + share-bg directory + smoke + push

**Files:**
- Create: `/Users/ansvier/ph-heatmap/public/share-bg/.gitkeep`
- Modify: `/Users/ansvier/ph-heatmap/README.md`

- [ ] **Step 1: Create empty `public/share-bg/` directory**

```bash
cd /Users/ansvier/ph-heatmap
mkdir -p public/share-bg
touch public/share-bg/.gitkeep
```

- [ ] **Step 2: Add README note about Save image upgrade**

Open `/Users/ansvier/ph-heatmap/README.md`. Find the Pages section (the table at the top with URLs and what they show). After the table, add a brief paragraph about the new Save image flow:

```markdown
### Share cards

Every treemap-bearing page (`/`, `/rising/`, `/gems/`, `/celebs/`, every `/country/<slug>/`, and `/categories/`) has a **Save image (PNG)** button that downloads a 1200×630 "trading card" style image of the current view: HotMap logo, page context, today's top mover, and the live treemap as the signature visual. The card respects whichever mode/gender/window toggle is selected when you click. A random background from `public/share-bg/{bg-1,bg-2,bg-3}.jpg` rotates between renders — drop your own 1200×630 dark-toned JPEGs into that directory to customize.
```

- [ ] **Step 3: Local browser smoke**

Render the current site and open in browser:

```bash
./venv/bin/python -c "
from pathlib import Path
from db import init_db, load_all_snapshots, load_all_category_snapshots
from heatmap import (
    _COUNTRY_MIN_PERFORMERS, _country_slug,
    render_categories_treemap, render_country_page,
    render_treemap_page,
)
from scraper import fetch_category_catalog
import pandas as pd

PUBLIC_DIR = Path('public')
conn = init_db('data.db')
snapshots = load_all_snapshots(conn)
cat_snaps = load_all_category_snapshots(conn)

# Main page
render_treemap_page(snapshots, PUBLIC_DIR / 'gems' / 'index.html',
                    default_mode='gems', canonical_path='/gems/', seo_key='gems')
print('rendered /gems/')

# One country page
render_country_page(snapshots, 'Russia', PUBLIC_DIR / 'country' / 'russia' / 'index.html')
print('rendered /country/russia/')

# Categories
catalog = fetch_category_catalog()
url_by_id = {r['id']: r['url'] for r in catalog if r.get('url')}
render_categories_treemap(cat_snaps, PUBLIC_DIR / 'categories' / 'index.html', url_by_id=url_by_id)
print('rendered /categories/')
"
```

Expected: prints 3 "rendered" lines, no errors.

Then open these in browser:

```bash
open "file://$(pwd)/public/gems/index.html"
```

In the browser dev tools or just by clicking the Share dropdown → Save image, verify a PNG downloads and contains:
- HotMap logo top-right
- "HIDDEN GEMS" mode label
- Filter line ("Female · 1 day")
- A top-mover mini-card with photo
- The current treemap as the right-side visual
- Footer with updated-at + "N performers tracked"

If the PNG looks broken (missing tiles, ragged crop, no logo), STOP and investigate before pushing.

Repeat for country and categories pages:

```bash
open "file://$(pwd)/public/country/russia/index.html"
open "file://$(pwd)/public/categories/index.html"
```

For country: click the new "Save image (PNG)" button (under the subtitle), verify download.
For categories: same.

- [ ] **Step 4: Commit + push**

```bash
git add public/share-bg/.gitkeep README.md
git commit -m "$(cat <<'EOF'
docs+chore: reserve public/share-bg/ directory + README note

Share Card v1 expects 1200x630 background images at /share-bg/bg-1.jpg,
bg-2.jpg, bg-3.jpg. Reserves the directory via .gitkeep so the path
exists; missing files fall through to flat #0a0a0a gracefully. User
will drop the three JPEGs in afterward.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push 2>&1 | tail -3
```

- [ ] **Step 5: Live verify (after CF Pages deploy)**

```bash
until curl -s https://hotmap.cam/gems/ 2>/dev/null | grep -q "buildShareCard"; do sleep 5; done
echo "DEPLOY COMPLETE"
echo "=== main page has share-card ==="
curl -s https://hotmap.cam/gems/ | grep -c 'class="share-card"\|buildShareCard\|/share-bg/'
echo "=== country page has share-card ==="
curl -s https://hotmap.cam/country/russia/ | grep -c 'class="share-card"\|class="save-image-btn"\|data-context-label="Russia"'
echo "=== categories page has share-card ==="
curl -s https://hotmap.cam/categories/ | grep -c 'class="share-card"\|id="share-card-top-category"\|class="save-image-btn"'
```

Expected: all three pages show ≥3 matches each. Then open each URL in a browser, click Save image, verify the PNG.

---

## Self-review checklist (filled out by plan author)

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| `.share-card` template + CSS in main, country, categories templates | Tasks 1, 2, 3 |
| `buildShareCard` JS function shared across all 3 page types | Task 1 |
| 3 background image slots in `public/share-bg/` | Task 4 |
| Random-bg selection on Save (Math.floor(random*3)) | Task 1 (in `_SHARE_CARD_JS`) |
| Save Image button → buildShareCard (not chrome screenshot) | Task 1 |
| Tests for `.share-card` existence + JS wiring | Tasks 1, 2, 3 |
| Two-column 1200×630 layout (480 left + 640 right) | Task 1 CSS |
| Brand strip (path left + logo right) | Task 1 HTML |
| Mode label, filter chip, top-mover mini-card | Task 1 HTML + JS |
| Footer (updated-at left, tracked count right) | Task 1 HTML + JS |
| Plotly colorbar hidden via inline CSS override | Task 1 CSS |
| Random bg fallback to `#0a0a0a` when image missing | Task 1 CSS (`background-color: #0a0a0a` base, image stacks on top) |
| Categories: colored-block + first letter (no photo) | Task 1 JS (category branch) + Task 3 meta div |
| Top performer extracted from `.top-perf.active` for main+country | Task 1 JS |
| Top category extracted from hidden meta div for categories | Task 3 |
| Save guard: alert if Plotly not loaded | Task 1 JS (`saveShareCardImage`) |
| Filenames per-page-type | Tasks 1, 2, 3 click handlers |
| README note | Task 4 |

No gaps.

**Placeholder scan:** No TBD/TODO/"similar to". Each code step contains the actual code.

**Type consistency:**
- `buildShareCard()` signature: zero args, reads from DOM. Consistent across Tasks 1-3.
- `saveShareCardImage(filename)`: 1-arg, calls buildShareCard, html2canvases it, downloads. Consistent.
- `_SHARE_CARD_CSS` / `_HTML` / `_JS` constants used identically in 3 page templates.
- `data-page-type` values: `"main"`, `"country"`, `"category"` — match the JS switch.
- `data-context-label` only on country pages (matches JS branch).
- `data-updated-at` / `data-tracked-count` / `data-tracked-label` consistent across all 3.

**Risk-aware steps:**
- Task 1 Step 9 catches regressions in existing 27-panel main page tests.
- Task 4 Step 3 manual browser smoke catches Plotly + html2canvas oddities before push.
- Task 4 Step 5 live verify confirms CF Pages deploy reflects the code.
