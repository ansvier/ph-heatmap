# Share Card v1 — design

**Status:** approved
**Date:** 2026-06-03
**Author:** ansvier + claude

## Problem

The existing **Save image (PNG)** button in the Share-dropdown captures `.hero + .panel.active` via html2canvas and downloads a literal screenshot of the page chrome. It looks like a debugger dump — bare toggles, system fonts where Plotly didn't load, ragged crop. Useless for actual sharing. Modern trading apps (mirrorly.xyz being the user's reference) produce **purpose-designed share cards**: branded header strip, hero metric, signature visual, clean stats footer. We need the same — a card people would actually post to Twitter or Telegram channels and recognize as HotMap content at a glance.

## Goal

After this lands:

1. **Save image (PNG)** on every treemap page produces a 1200×630 designed card, not a chrome screenshot.
2. The card visually identifies HotMap (logo, brand colors), the specific page context (mode + gender + window, or country name, or category context), the treemap itself as the signature visual, and today's top performer as the headline.
3. The card respects the user's **current view** — whichever mode/gender/window toggle they've selected gets captured (same as today's behavior).
4. Three rotating background images add visual variety so consecutive shares don't look identical.
5. Existing share infrastructure (dropdown, Twitter/Telegram/Copy-link siblings) stays untouched.

## Decision

### 1. Scope

Treemap-bearing pages only, **18 pages total**:

- `/`, `/rising/`, `/gems/`, `/celebs/` — main mode pages
- `/country/<slug>/` — 13 country pages
- `/categories/` — 1 categories page

Out of scope for v1: `/stats/` (no treemap, would need different layout), `/p/<slug>/` (~870 pages, would need sparkline-centric layout instead).

### 2. Implementation: client-side html2canvas

A hidden `.share-card` div lives in every treemap-page template (1200×630, positioned off-screen). On Save click:

1. JS reads current state (active mode/gender/window, top-performer data already on page).
2. Populates the card's left column with page label, filter chips, top-mover details.
3. Clones the **currently visible** Plotly panel div and inserts it into the card's right column.
4. Picks a random background from `public/share-bg/{bg-1,bg-2,bg-3}.jpg`.
5. Reveals the card off-screen, runs `html2canvas(card, {scale: 2, useCORS: true})`, downloads the resulting PNG.
6. Hides the card back.

We keep html2canvas (already loaded on these pages, no new dep). Tradeoff: Plotly SVG inside html2canvas occasionally renders with subtle font shifts. Accepted — quality is "good enough for share", and the trade buys us per-current-view fidelity which is the user-stated priority.

### 3. Layout (1200×630)

```
┌──────────────────────────────────────────────────────────────────┐
│ hotmap.cam/gems                                   ⬡ HOT|MAP      │  56px brand strip
├──────────────────────────────────────────────────────────────────┤
│  HIDDEN GEMS                       ┌─────────────────────────┐   │
│  Female · 1 day                    │                         │   │
│                                    │                         │   │
│  [photo]   Lana Rhoades            │       TREEMAP           │   │  528px main row
│   56×56    ──────────              │                         │   │
│            TOP MOVER TODAY         │                         │   │
│            +12.43%                 │                         │   │
│            +1.4M views             └─────────────────────────┘   │
│                                                                  │
├──────────────────────────────────────────────────────────────────┤
│ Updated 2026-06-03 04:17 UTC · 500 performers tracked            │  46px footer
└──────────────────────────────────────────────────────────────────┘
```

**Vertical breakdown:** 56 (header) + 528 (main row) + 46 (footer) = 630px exactly.

**Left column** (~480px wide):
- Mode label, uppercase, white, 32px Inter ExtraBold — `HIDDEN GEMS` / `RISING STARS` / `CELEBRITIES` / `RUSSIA` / `TRENDING CATEGORIES`
- Filter chip line, 16px Inter Medium, muted — `Female · 1 day`. Country pages: omit (female-only by current product rules). Categories: omit.
- Top-mover mini-card: 56×56 circular photo + name (24px bold) + label "TOP MOVER TODAY" (11px uppercase orange `#ff9000`) + growth % (40px ExtraBold green `#6cd36a`) + delta views (16px muted)

**Right column** (~640px wide):
- Cloned active Plotly panel div, colorbar hidden via inline CSS override (`g.colorbar { display: none }` applied to the clone), tile labels preserved.

**Header strip** (56px):
- Left: current path (`hotmap.cam/gems` or `hotmap.cam/country/russia/`) in 16px monospace white
- Right: HotMap logo SVG (existing `<svg>` used in nav, 36px tall)

**Footer strip** (46px):
- Left: `Updated YYYY-MM-DD HH:MM UTC` (12px muted)
- Right: page-specific count (`500 performers tracked` / `13 performers tracked` / `189 categories tracked`)

### 4. Background images

`public/share-bg/bg-1.jpg`, `bg-2.jpg`, `bg-3.jpg` — 1200×630 each (or 2400×1260 for retina), JPEG, dark-toned. User provides; spec just reserves the slots.

On Save click: `var bg = '/share-bg/bg-' + (1 + Math.floor(Math.random() * 3)) + '.jpg'`. Applied as `.share-card { background-image: url(...) }`.

**Overlay for readability:** the card layers a `linear-gradient(135deg, rgba(10,10,10,0.85), rgba(10,10,10,0.55))` over the background. The treemap panel and top-mover block get their own opaque dark backgrounds (`rgba(0,0,0,0.7)` with `backdrop-filter: blur(8px)`) so tile colors and text contrast remain stable regardless of which bg fired.

**Fallback:** if all 3 background files are missing (e.g., before user uploads), card renders on flat `#0a0a0a` (current background color). No broken-image icons.

### 5. Categories page treatment

`/categories/` doesn't have performer photos — the "top mover" mini-card would degrade to "category name + delta videos" in the left column without a photo:

```
[colored block 56×56]   MILF
                        ──────────
                        TRENDING TODAY
                        +12,4K videos
```

The colored block is a 56×56 square filled with the brand-orange color, with the category's first letter centered (matches our `.cat-list` styling). Visually less striking than performer photos, but consistent with the layout. Acceptable for v1.

### 6. Data flow

All data already lives in JS state or DOM on every page:

- **Main pages**: `state.mode`, `state.gender`, `state.window` — JS toggle state. Top-mover comes from the `.top-perf.active` element's data attributes.
- **Country pages**: page is static, top-mover comes from the single `.top-perf.active` already rendered.
- **Categories**: top-mover = highest `delta` in `customdata` — read from the first Plotly point.

No new server-side data, no new template variables. Just JS introspection of what's already on the page.

### 7. JS architecture

New module-level function in the main `<script>` block, shared between all 18 page types:

```js
function buildShareCard(state, topMover) {
  // Read page-type from <body data-page-type>, populate card slots, return ready node.
}

shareSave.addEventListener('click', function () {
  var card = buildShareCard(getCurrentState(), getTopMover());
  document.body.appendChild(card);
  html2canvas(card, {scale: 2, useCORS: true})
    .then(canvas => downloadCanvas(canvas, computeFilename(state)))
    .finally(() => document.body.removeChild(card));
});
```

We extract the share-card template into a function that takes (state, topMover) and returns a DOM node, so the four page categories (main / country / category / fallback) can supply slightly different data through the same composition function.

### 8. Filename

`hotmap-<context>-<date>.png` where context is:
- Main pages: `<mode>-<gender>-<window>d` (e.g., `gems-female-1d`)
- Country pages: `country-<slug>` (e.g., `country-russia`)
- Categories: `categories`

Date is `YYYY-MM-DD` from JS `new Date().toISOString().slice(0,10)`.

## Scope

### In scope

- `.share-card` template + CSS in main treemap, country, categories page templates
- JS composition logic (`buildShareCard`)
- 3 background image slots (files provided by user)
- Random-bg selection on Save
- Updated Save Image click handler
- Test that `.share-card` exists in rendered HTML and JS is wired

### Out of scope

- `/stats/` and `/p/<slug>/` cards (v1.1)
- Server-side card pre-generation
- Becoming the og:image (separate work — would require server-side)
- Custom card preview before download
- Watermark text / "shared from hotmap.cam" — implicit in the header strip already
- A/B testing different layouts
- Animated cards / GIFs
- Multiple aspect ratios (square / vertical) — v1.x if requested

## Edge cases

- **No top performer** (empty cohort, e.g., country with no qualifying photos): left-column collapses the mini-card. Mode label, filter chip, and treemap on the right remain. Card still meaningful.
- **Photo URL missing**: 56×56 div with brand-orange background + first letter of name, mirrors the existing `_build_top_performer_card` fallback.
- **Plotly not yet rendered when Save clicked**: html2canvas captures whatever's in DOM — if treemap is mid-render, it'll be missing in the card. Mitigation: Save button is disabled until first treemap rendering completes. Single-line guard: `if (!document.querySelector('.plotly-graph-div')) { alert('...'); return; }`.
- **Background image 404s**: fallback to flat `#0a0a0a`. JS preloads the chosen image and only sets it on the card if `Image.complete` after a 500ms timeout.
- **Active panel has no toggles** (country/categories pages): code uses the only treemap on the page.
- **html2canvas crashes** on some Plotly internals (rare but seen): existing catch-block already alerts user "Could not generate image" — unchanged.

## Risks

- **Plotly font in html2canvas**: SVG text inside Plotly sometimes renders with system fallback fonts. Test on Safari + Chrome + Firefox before declaring done. If unfixable, accept — fonts only matter in the treemap labels which are tiny.
- **Background image quality**: if user provides JPEG-artifacted or off-tone images, cards look amateur. We document a 1200×630 dark-toned recommendation in the spec; QA after first upload.
- **Heavy DOM clone**: Plotly panel cloning could be slow on cheap mobiles. Test on a real low-end Android. Mitigation: show a "Generating image..." spinner during ~2 sec of html2canvas work (already exists in current code).
- **Categories card weakness**: the colored-block-with-letter fallback for /categories/ looks less striking than performer photos. Accept for v1, may warrant a redesign if categories sharing takes off.

## Files touched

| Path | Change |
|---|---|
| `heatmap.py` | New `_SHARE_CARD_TEMPLATE` and `_SHARE_CARD_CSS` constants; injected into main treemap, country, categories templates; updated `Save image` JS to call `buildShareCard` |
| `tests/test_heatmap.py` | +1 test per page type: `.share-card` div present, `buildShareCard` function defined, background path referenced |
| `public/share-bg/bg-{1,2,3}.jpg` | New files (provided by user) |
| `README.md` | Brief note about the Save-image upgrade |

**Total:** ~250 lines of HTML/CSS/JS in the template constants, ~30 lines of new test assertions. No new Python dependencies, no new build steps, no server-side render changes.
