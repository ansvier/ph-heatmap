from __future__ import annotations

import html as _html
import json as _json
import re as _re
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import pandas as pd
import plotly.graph_objects as go


_PROFILE_URL_BASE = "https://www.pornhub.com/pornstar/"  # canonical PH URL (Schema.org sameAs)
_REDIRECT_URL_BASE = "/r/"  # outbound clicks go through CF Worker (click tracking + future affiliate)


_LOGO_SVG = (
    '<svg class="logo" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 100" role="img" aria-label="HotMap">'
    '<rect width="400" height="100" fill="#000"/>'
    '<text x="20" y="78" font-family="\'Arial Black\',\'Helvetica Neue\',Helvetica,Arial,sans-serif" font-weight="900" font-size="76" fill="#fff" letter-spacing="-3">HOT</text>'
    '<rect x="198" y="14" width="184" height="72" rx="14" fill="#ff9000"/>'
    '<text x="214" y="72" font-family="\'Arial Black\',\'Helvetica Neue\',Helvetica,Arial,sans-serif" font-weight="900" font-size="60" fill="#000" letter-spacing="-3">MAP</text>'
    '</svg>'
)

_NAV_ITEMS = [
    ("map",        "/",            "Map"),
    ("stats",      "/stats/",      "Stats"),
    ("categories", "/categories/", "Categories"),
    ("countries",  "/countries/",  "Countries"),
    ("charts",     "/charts/",     "Charts"),
]


def _top_nav(active: str) -> str:
    """Return the site-wide top nav HTML. `active` ∈ {'map','stats','charts',''}."""
    links = "".join(
        f'<a href="{href}" class="navlink{" active" if key == active else ""}">{label}</a>'
        for key, href, label in _NAV_ITEMS
    )
    return f'<nav class="topnav"><a class="brand" href="/">{_LOGO_SVG}</a><div class="navlinks">{links}</div></nav>'


_TOP_NAV_CSS = """
    .topnav {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 16px;
    }
    .topnav .brand { display: inline-block; line-height: 0; }
    .topnav .logo { width: 240px; max-width: 50vw; height: auto; }
    .navlinks { display: flex; gap: 2px; flex-wrap: wrap; margin-right: 130px; }
    .navlink {
      color: rgba(245,245,245,0.4);
      font-weight: 500;
      font-size: 13px;
      letter-spacing: 0.3px;
      padding: 6px 12px;
      border-radius: 6px;
      text-decoration: none;
      transition: color 0.15s, background 0.15s;
    }
    .navlink:hover { color: rgba(245,245,245,0.85); text-decoration: none; }
    .navlink.active {
      color: rgba(245,245,245,0.95);
      background: rgba(255,144,0,0.12);
    }
    @media (max-width: 900px) {
      .navlinks { margin-right: 0; }
    }
    @media (max-width: 520px) {
      .topnav { flex-wrap: wrap; }
      .topnav .logo { width: 160px; }
    }
"""


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
  <style>
    :root {{
      --brand-orange: #ff9000;
      --bg: #0a0a0a;
      --fg: #f5f5f5;
      --muted: #9a9a9a;
      --rule: #1f1f1f;
      --btn-bg: #161616;
      --btn-bg-active: #ff9000;
      --btn-fg: #e8e8e8;
      --btn-fg-active: #000;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
    body {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 32px 16px 56px;
      color: var(--fg);
      background: var(--bg);
      line-height: 1.5;
      font-feature-settings: 'cv11', 'ss01';
    }}
{nav_css}
    .hero {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      margin-bottom: 20px;
      flex-wrap: wrap;
    }}
    .top-perf-wrap {{
      flex: 0 0 auto;
      /* Align card right edge with tile right edge (Plotly reserves ~120px
         for the colorbar, so the actual tiles end ~130px from page right). */
      margin-right: 130px;
    }}
    @media (max-width: 900px) {{ .top-perf-wrap {{ margin-right: 0; }} }}
    .top-perf {{
      display: none;
      align-items: center;
      gap: 14px;
      padding: 12px 16px;
      background: var(--btn-bg);
      border: 1px solid var(--rule);
      border-left: 3px solid var(--brand-orange);
      border-radius: 8px;
      text-decoration: none;
      color: inherit;
      transition: border-color 0.12s, transform 0.12s;
      max-width: 360px;
    }}
    .top-perf.active {{ display: flex; }}
    .top-perf:hover {{ border-color: var(--brand-orange); transform: translateY(-1px); }}
    .top-perf img {{
      width: 56px;
      height: 56px;
      border-radius: 50%;
      object-fit: cover;
      flex-shrink: 0;
      background: #222;
    }}
    .top-perf-text {{ display: flex; flex-direction: column; gap: 2px; min-width: 0; }}
    .top-perf-label {{
      color: var(--brand-orange);
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 1.5px;
      text-transform: uppercase;
    }}
    .top-perf-name {{
      color: var(--fg);
      font-size: 17px;
      font-weight: 700;
      letter-spacing: -0.01em;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .top-perf-stat {{
      color: var(--muted);
      font-size: 12px;
      font-weight: 500;
    }}
    .top-perf-stat strong {{ color: #6cd36a; font-weight: 700; }}
    .top-perf-stat-row {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      font-weight: 500;
      line-height: 1.35;
    }}
    .top-perf-stat-row strong {{ color: var(--fg); font-weight: 700; font-variant-numeric: tabular-nums; }}
    .top-perf-caption {{
      display: block;
      color: #6cd36a;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.02em;
      margin-top: 2px;
    }}
    .logo {{
      display: block;
      width: 360px;
      max-width: 100%;
      height: auto;
    }}
    .tagline {{
      color: var(--fg);
      font-size: 20px;
      font-weight: 700;
      letter-spacing: -0.02em;
      margin: 0;
      flex: 1 1 320px;
      min-width: 0;
    }}
    .tagline .hint {{
      display: block;
      color: var(--muted);
      font-size: 14px;
      font-weight: 400;
      letter-spacing: 0;
      margin: 4px 0 0;
    }}
    .controls {{
      display: flex;
      flex-wrap: wrap;
      gap: 24px;
      margin: 16px 0 20px;
    }}
    .controls .toggle.spacer {{ margin-left: auto; margin-right: 130px; }}
    @media (max-width: 900px) {{ .controls .toggle.spacer {{ margin-left: 0; margin-right: 0; }} }}
    .toggle {{
      display: flex;
      gap: 6px;
      align-items: center;
    }}
    .toggle-label {{
      color: var(--muted);
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 1.5px;
      margin-right: 6px;
    }}
    .toggle button {{
      background: var(--btn-bg);
      color: var(--btn-fg);
      border: 1px solid var(--rule);
      padding: 7px 14px;
      font: inherit;
      font-weight: 600;
      font-size: 14px;
      cursor: pointer;
      border-radius: 6px;
      transition: background 0.12s, color 0.12s, border-color 0.12s;
    }}
    .toggle button:hover {{ border-color: var(--brand-orange); }}
    .toggle button.active {{
      background: var(--btn-bg-active);
      color: var(--btn-fg-active);
      border-color: var(--brand-orange);
    }}
    .share-btn {{
      background: transparent;
      border: 1px solid var(--brand-orange);
      color: var(--brand-orange);
    }}
    .share-btn:hover {{ background: var(--brand-orange); color: #000; }}
    .share-btn.busy {{ opacity: 0.6; cursor: progress; }}
    .share-icon {{ font-weight: 700; margin-right: 4px; }}
    .share-btn .caret {{ font-size: 10px; margin-left: 4px; opacity: 0.8; }}
    .share-menu {{ position: relative; }}
    .share-menu-items {{
      position: absolute;
      top: calc(100% + 6px);
      right: 0;
      min-width: 200px;
      background: var(--btn-bg);
      border: 1px solid var(--rule);
      border-radius: 8px;
      padding: 6px;
      box-shadow: 0 8px 24px rgba(0,0,0,0.4);
      display: none;
      z-index: 100;
    }}
    .share-menu.open .share-menu-items {{ display: block; }}
    .share-menu-items > * {{
      display: flex;
      align-items: center;
      gap: 8px;
      width: 100%;
      padding: 8px 12px;
      background: transparent;
      color: var(--fg);
      border: 0;
      border-radius: 5px;
      font: inherit;
      font-size: 13px;
      font-weight: 500;
      text-align: left;
      text-decoration: none;
      cursor: pointer;
      transition: background 0.12s;
    }}
    .share-menu-items > *:hover {{ background: rgba(255,144,0,0.15); }}
    .share-menu-items span[aria-hidden] {{ width: 18px; font-size: 14px; }}
    .panel {{ display: none; }}
    .panel.active {{ display: block; }}
    .panel .plotly-graph-div {{ cursor: pointer; }}
    main {{ margin: 0; }}
    footer {{
      margin-top: 32px;
      padding-top: 16px;
      border-top: 1px solid var(--rule);
      color: var(--muted);
      font-size: 13px;
    }}
    footer a {{ color: var(--muted); text-decoration: underline; }}
    footer a:hover {{ color: var(--brand-orange); }}
    .stats {{ margin: 0 0 4px; }}
    .disclaimer {{ margin: 0; font-size: 12px; }}
{share_card_css}
  </style>
</head>
<body data-page-type="main" data-updated-at="{last_updated}" data-tracked-count="{n_performers}" data-tracked-label="performers tracked">
  {top_nav}
  <header class="hero">
    <p class="tagline">Today's hottest performers. <span class="hint">Click a tile to open the profile.</span></p>
    {top_perf_card}
  </header>

  <div class="controls">
    <div class="toggle" role="tablist" aria-label="Mode">
      <button type="button" class="mode{mode_btn_active_rising}" data-mode="rising">Rising Stars</button>
      <button type="button" class="mode{mode_btn_active_gems}" data-mode="gems">Hidden Gems</button>
      <button type="button" class="mode{mode_btn_active_celebs}" data-mode="celebs">Celebrities</button>
    </div>
    <div class="toggle" role="tablist" aria-label="Gender filter">
      <span class="toggle-label">Gender</span>
      <button type="button" class="gender" data-gender="all">All</button>
      <button type="button" class="active gender" data-gender="female">Female</button>
      <button type="button" class="gender" data-gender="male">Male</button>
    </div>
    <div class="toggle" role="tablist" aria-label="Window">
      <span class="toggle-label">Window</span>
      <button type="button" class="active window" data-window="1">1d</button>
      <button type="button" class="window" data-window="7">7d</button>
      <button type="button" class="window" data-window="30">30d</button>
    </div>
    <div class="toggle spacer share-menu" id="share-menu">
      <button type="button" id="share-toggle" class="share-btn" aria-haspopup="true" aria-expanded="false">
        Share <span class="caret" aria-hidden="true">▾</span>
      </button>
      <div class="share-menu-items" role="menu">
        <button type="button" id="share-save" role="menuitem"><span aria-hidden="true">⤓</span> Save image (PNG)</button>
        <a id="share-tweet" href="#" target="_blank" rel="noopener" role="menuitem"><span aria-hidden="true">𝕏</span> Tweet</a>
        <a id="share-telegram" href="#" target="_blank" rel="noopener" role="menuitem"><span aria-hidden="true">📨</span> Telegram</a>
        <button type="button" id="share-copy" role="menuitem"><span aria-hidden="true">🔗</span> Copy link</button>
      </div>
    </div>
  </div>

  <main>
    {panels}
  </main>

  <footer>
    <p class="stats">Updated {last_updated} UTC · Refreshes daily at 04:17 UTC · {n_days} days of history · {n_performers} performers tracked · <a href="https://github.com/ansvier/ph-heatmap">source on GitHub</a> · <a href="data.json">raw data (JSON)</a></p>
    <p class="disclaimer">HotMap is an independent project. Data is collected from publicly visible Pornhub profile pages; no video content is hosted here.</p>
  </footer>

  <script>
    (function () {{
      var state = {{ mode: '{default_mode}', gender: 'female', window: '1' }};
      var panels = document.querySelectorAll('.panel');

      var topPerfCards = document.querySelectorAll('.top-perf');
      var MODE_PATHS = {{ rising: '/rising/', gems: '/gems/', celebs: '/celebs/' }};

      function syncUrl() {{
        var desired = MODE_PATHS[state.mode] || '/';
        var current = window.location.pathname.replace(/\\/$/, '') || '/';
        if (current !== desired) {{
          history.replaceState({{ mode: state.mode }}, '', desired);
        }}
      }}

      function refresh() {{
        var activeId = 'panel-' + state.mode + '-' + state.gender + '-' + state.window;
        panels.forEach(function (p) {{
          p.classList.toggle('active', p.id === activeId);
        }});
        topPerfCards.forEach(function (c) {{
          var matches = c.getAttribute('data-mode') === state.mode
                     && c.getAttribute('data-gender') === state.gender;
          c.classList.toggle('active', matches);
        }});
        syncUrl();
        window.dispatchEvent(new Event('resize'));
      }}

      // Handle browser back/forward — keep UI in sync if user uses history nav.
      window.addEventListener('popstate', function () {{
        var path = window.location.pathname.replace(/\\/$/, '') || '/';
        var found = Object.keys(MODE_PATHS).find(function (m) {{ return MODE_PATHS[m] === path; }});
        if (found && found !== state.mode) {{
          state.mode = found;
          document.querySelectorAll('.mode').forEach(function (b) {{
            b.classList.toggle('active', b.getAttribute('data-mode') === state.mode);
          }});
          refresh();
        }}
      }});

      function bind(selector, key) {{
        var buttons = document.querySelectorAll(selector);
        buttons.forEach(function (btn) {{
          btn.addEventListener('click', function () {{
            buttons.forEach(function (b) {{ b.classList.toggle('active', b === btn); }});
            state[key] = btn.getAttribute('data-' + key);
            refresh();
          }});
        }});
      }}

      bind('.mode', 'mode');
      bind('.gender', 'gender');
      bind('.window', 'window');

      // Click any tile → outbound bounce through /r/<slug>. The CF Worker
      // logs the click and 302-redirects to PH. Single point of attribution
      // for future affiliate tracking, no UX change for the user.
      var REDIRECT_BASE = '{redirect_url_base}';
      function attachClickHandlers() {{
        document.querySelectorAll('.plotly-graph-div').forEach(function (div) {{
          if (div._hotmapBound) return;
          div._hotmapBound = true;
          div.on('plotly_treemapclick', function (evt) {{
            if (!evt || !evt.points || !evt.points.length) return;
            var slug = evt.points[0].customdata && evt.points[0].customdata[3];
            if (slug) {{
              window.open(REDIRECT_BASE + slug, '_blank', 'noopener');
            }}
            // Prevent the default zoom-into-tile behavior.
            return false;
          }});
        }});
      }}
      // Plotly renders asynchronously; poll briefly until the divs are ready.
      var attempts = 0;
      var iv = setInterval(function () {{
        attachClickHandlers();
        if (++attempts > 20) clearInterval(iv);
      }}, 250);

{share_card_js}

      // Share dropdown — toggle menu, set share links live, wire Save image.
      var shareMenu = document.getElementById('share-menu');
      var shareToggle = document.getElementById('share-toggle');
      var shareTweet = document.getElementById('share-tweet');
      var shareTelegram = document.getElementById('share-telegram');
      var shareCopy = document.getElementById('share-copy');
      var shareSave = document.getElementById('share-save');

      function currentShareUrl() {{
        // Use the canonical URL of the active mode so the link opens the
        // same view the user is on (rising/gems/celebs).
        var modePath = state.mode === 'rising' ? '/' : '/' + state.mode;
        return 'https://hotmap.cam' + modePath;
      }}
      function currentShareText() {{
        var labels = {{ rising: 'Rising Stars', gems: 'Hidden Gems', celebs: 'Top Celebrities' }};
        return "Today's hottest performers on HotMap — " + (labels[state.mode] || 'Rising Stars');
      }}

      function refreshShareLinks() {{
        var url = currentShareUrl();
        var text = currentShareText();
        shareTweet.href = 'https://twitter.com/intent/tweet?text=' + encodeURIComponent(text) + '&url=' + encodeURIComponent(url);
        shareTelegram.href = 'https://t.me/share/url?url=' + encodeURIComponent(url) + '&text=' + encodeURIComponent(text);
      }}

      if (shareToggle) {{
        shareToggle.addEventListener('click', function (e) {{
          e.stopPropagation();
          refreshShareLinks();
          var willOpen = !shareMenu.classList.contains('open');
          shareMenu.classList.toggle('open', willOpen);
          shareToggle.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
        }});
        document.addEventListener('click', function () {{
          shareMenu.classList.remove('open');
          shareToggle.setAttribute('aria-expanded', 'false');
        }});
        shareMenu.addEventListener('click', function (e) {{ e.stopPropagation(); }});
      }}

      if (shareCopy) {{
        shareCopy.addEventListener('click', function () {{
          var url = currentShareUrl();
          navigator.clipboard.writeText(url).then(function () {{
            var orig = shareCopy.innerHTML;
            shareCopy.innerHTML = '<span aria-hidden="true">✓</span> Copied!';
            setTimeout(function () {{ shareCopy.innerHTML = orig; }}, 1400);
          }});
        }});
      }}

      // Save image: build the Share Card v1 and download as PNG.
      if (shareSave) {{
        shareSave.addEventListener('click', function () {{
          var stamp = new Date().toISOString().slice(0, 10);
          var filename = 'hotmap-' + state.mode + '-' + state.gender + '-' + state.window + 'd-' + stamp + '.png';
          shareToggle.classList.add('busy');
          Promise.resolve().then(function () {{ saveShareCardImage(filename); }})
            .finally(function () {{ shareToggle.classList.remove('busy'); }});
        }});
      }}
    }})();
  </script>
{share_card_html}
</body>
</html>
"""


def compute_window_growth(
    snapshots: pd.DataFrame,
    window_days: int,
    gender: str | None = None,
) -> pd.DataFrame:
    """Return a per-slug snapshot with % growth over a N-day window.

    Output columns: `name`, `total_views` (today), `prev_views` (N days ago,
    or NaN if no row exists for that date+slug), `growth_pct` (NaN if no baseline),
    `gender`.
    Index: `slug`. Only slugs present in the latest snapshot are included.
    `gender`, when provided ('female' | 'male'), pre-filters the input.
    """
    if snapshots.empty:
        return pd.DataFrame(columns=["name", "total_views", "prev_views", "growth_pct", "gender"])

    snapshots = snapshots.copy()
    snapshots["snapshot_date"] = pd.to_datetime(snapshots["snapshot_date"])

    if gender is not None and "gender" in snapshots.columns:
        snapshots = snapshots[snapshots["gender"] == gender]
        if snapshots.empty:
            return pd.DataFrame(columns=["name", "total_views", "prev_views", "growth_pct", "gender"])

    latest_date = snapshots["snapshot_date"].max()
    baseline_date = latest_date - pd.Timedelta(days=window_days)

    today_cols = ["name", "total_views"]
    if "gender" in snapshots.columns:
        today_cols.append("gender")

    today = snapshots[snapshots["snapshot_date"] == latest_date].set_index("slug")
    baseline = (
        snapshots[snapshots["snapshot_date"] == baseline_date]
        .set_index("slug")["total_views"]
        .rename("prev_views")
    )

    out = today[today_cols].join(baseline, how="left")
    out["growth_pct"] = (out["total_views"] - out["prev_views"]) / out["prev_views"] * 100

    # For 1d window only: attach the acceleration column used by the
    # "Spike of the Day" card selection logic. 7d / 30d windows are not
    # surfaced through that card, so the column is omitted there.
    if window_days == 1:
        out["acceleration"] = _compute_acceleration(snapshots, gender=None)

    return out


def _compute_acceleration(
    snapshots: pd.DataFrame,
    gender: str | None = None,
    baseline_days: int = 7,
    min_priors: int = 3,
) -> pd.Series:
    """Per-slug acceleration: today's daily growth-% minus mean(prior N daily growth-%s).

    A performer who naturally drifts upward by +0.25%/day has acceleration ≈ 0
    — that's their baseline. Acceleration > 0 means "today was faster than usual"
    (something hyped them up). Acceleration < 0 means "slowing vs baseline."

    Returns a Series indexed by slug with NaN for slugs that have fewer than
    `min_priors` historical daily growths (not enough data for a stable baseline).
    """
    snapshots = snapshots.copy()
    snapshots["snapshot_date"] = pd.to_datetime(snapshots["snapshot_date"])
    if gender is not None and "gender" in snapshots.columns:
        snapshots = snapshots[snapshots["gender"] == gender]

    if snapshots.empty:
        return pd.Series(dtype=float, name="acceleration")

    # slug × date matrix of total_views, sorted oldest → newest
    pivot = snapshots.pivot_table(index="slug", columns="snapshot_date", values="total_views")
    pivot = pivot.sort_index(axis=1)
    if pivot.shape[1] < 2:
        return pd.Series(dtype=float, name="acceleration")

    # Daily % growth (pct_change between consecutive days). First column = NaN.
    daily_growth = pivot.pct_change(axis=1) * 100

    todays = daily_growth.iloc[:, -1]
    # Prior `baseline_days` growth columns (excluding today)
    trailing = daily_growth.iloc[:, :-1].iloc[:, -baseline_days:]
    trailing_mean = trailing.mean(axis=1)
    trailing_count = trailing.count(axis=1)

    accel = (todays - trailing_mean).where(trailing_count >= min_priors)
    accel.name = "acceleration"
    return accel


def _format_views(n: int) -> str:
    """Compact: 464_114_451 -> '464M', 1_234_567 -> '1.2M', 950 -> '950'."""
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.0f}M" if n >= 100_000_000 else f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


_SITE_NAME = "HotMap"
_DEFAULT_OG_IMAGE = "https://hotmap.cam/og.png"
_TWITTER_CARD = "summary_large_image"

_OG_TYPE_BY_PAGE_TYPE = {
    "home": "website",
    "mode": "website",
    "stats": "article",
    "charts": "website",
    "performer": "profile",
    "category": "website",
    "country": "website",
}


def _website_jsonld() -> dict:
    """The WebSite block, emitted on every page. Carries identity for the
    site as a whole — Google uses this for sitelinks and entity reconciliation."""
    return {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": _SITE_NAME,
        "url": "https://hotmap.cam/",
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
    page_type: Literal["home", "mode", "stats", "charts", "performer", "category", "country"],
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
        f'  <script type="application/ld+json">'
        f'{_json.dumps(b, ensure_ascii=False).replace("</", "<\\/")}'
        f'</script>'
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


def _build_treemap_figure(window: pd.DataFrame, window_days: int) -> go.Figure:
    """Build one Plotly Treemap figure for a single (gender, window) view.

    Tile size encodes the % view growth over the window, so a mid-tier
    performer who accelerated shows up large even when their raw delta is
    smaller than a top-tier name's daily drip.
    Tile color is percentile rank of % growth within the visible set
    (green = running ahead of the pack, red = falling behind).
    Rows without a baseline are dropped, and rows whose baseline view count
    is below 1M are filtered out as well — they're too noisy on a % metric
    (a 100k bump on a 200k base is +50% but visually meaningless next to
    real movers).
    """
    rows = window.reset_index().copy()
    rows["growth_amount"] = rows["total_views"] - rows["prev_views"]
    rows = rows.dropna(subset=["growth_amount", "growth_pct"]).copy()
    rows["growth_amount"] = rows["growth_amount"].clip(lower=0)
    # Drop micro-accounts: < 1M baseline views makes the % metric too noisy
    # (a +100k bump on a 200k base is +50% but visually drowns out real movers).
    rows = rows[rows["prev_views"] >= 1_000_000].copy()

    # Size: % growth, clipped to ≥0 because Plotly Treemap requires
    # non-negative `values`. total_views is monotonic so this clip is defensive.
    rows["tile_size"] = rows["growth_pct"].clip(lower=0)

    # Color by percentile rank so the visible spread fills the palette even when
    # raw % growth values are tightly clustered (everyone +0.01..+0.07% etc).
    # `rank(pct=True)` returns [0..1]; we re-center to [-0.5..+0.5] so the diverging
    # scale's mid maps to the median performer.
    if len(rows) > 1:
        rows["color_value"] = rows["growth_pct"].rank(method="average", pct=True) - 0.5
    else:
        rows["color_value"] = 0.0

    rows["views_label"] = rows["total_views"].apply(_format_views)
    rows["pct_label"] = rows["growth_pct"].apply(lambda v: f"{v:+.2f}%")
    # Visual hierarchy: name bold, views muted-small, growth large+bold.
    rows["tile_text"] = (
        "<b>" + rows["name"] + "</b>"
        + "<br><span style='font-size:11px;color:rgba(0,0,0,0.55)'>"
        + rows["views_label"] + "</span>"
        + "<br><span style='font-size:16px;font-weight:700'>"
        + rows["pct_label"] + "</span>"
    )

    figure = go.Figure(
        go.Treemap(
            labels=rows["tile_text"],
            ids=rows["slug"],
            parents=[""] * len(rows),
            values=rows["tile_size"],
            marker=dict(
                colors=rows["color_value"],
                colorscale="RdYlGn",
                cmid=0,
                cmin=-0.5,
                cmax=0.5,
                showscale=True,
                colorbar=dict(
                    title=f"Rank ({window_days}d)",
                    tickvals=[-0.5, -0.25, 0, 0.25, 0.5],
                    ticktext=["bottom", "low", "median", "high", "top"],
                    thickness=14,
                    outlinewidth=0,
                ),
            ),
            customdata=rows[["name", "total_views", "growth_pct", "slug", "growth_amount"]].values,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Total views: %{customdata[1]:,}<br>"
                "Gained (" + str(window_days) + "d): +%{customdata[4]:,.0f} views<br>"
                "Growth: %{customdata[2]:+.3f}%<br>"
                "<i>click to open profile</i>"
                "<extra></extra>"
            ),
            textposition="middle center",
            textfont=dict(
                family="Inter, -apple-system, BlinkMacSystemFont, sans-serif",
                size=13,
                color="#000",
            ),
            tiling=dict(packing="squarify", pad=0),
        )
    )
    figure.update_layout(
        paper_bgcolor="#0a0a0a",
        plot_bgcolor="#0a0a0a",
        margin=dict(l=0, r=130, t=0, b=0),  # reserve right margin so colorbar ends at same offset as card / Share / nav (130px)
        height=700,
        font=dict(family="Inter, sans-serif", color="#f5f5f5"),
    )
    return figure


_WINDOWS = (1, 7, 30)
_GENDER_FILTERS = (("all", None), ("female", "female"), ("male", "male"))
_MODES = ("rising", "gems", "celebs")
_CELEBRITY_TOP_N = 50          # ranks 1..N = celebrities
_RISING_RANK_FLOOR = 250       # rising = ranks 51..N (= 200 performers)
# Soft safety ceilings (almost never trigger; safeguard if PH ranks a 1B-view
# performer unusually low one day).
_RISING_VIEW_CEILING = 2_000_000_000
_GEMS_VIEW_CEILING = 500_000_000
_TREEMAP_MAX_TILES = 100


_TOP_PERF_LABELS = {
    "rising": {
        "all": "Rising star of the day",
        "female": "Rising female of the day",
        "male": "Rising male of the day",
    },
    "gems": {
        "all": "Hidden gem of the day",
        "female": "Hidden female gem",
        "male": "Hidden male gem",
    },
    "celebs": {
        "all": "Top celebrity of the day",
        "female": "Top female celebrity",
        "male": "Top male celebrity",
    },
}


def _apply_mode_filter(window_df: pd.DataFrame, mode: str) -> pd.DataFrame:
    """Slice the window DataFrame into the requested mode cohort.

    Tiers are rank-based (after sorting by current total_views desc):
      - 'celebs':  ranks 1..50         (the established names)
      - 'rising':  ranks 51..250       (the 200 middle-tier performers)
      - 'gems':    ranks 251..N        (the deeper tail — genuinely smaller)
    Each non-celeb mode shows the TOP_MAX_TILES with the highest % growth.
    """
    if window_df.empty:
        return window_df
    df = window_df.copy()
    df = df.sort_values("total_views", ascending=False)
    df["_rank"] = range(1, len(df) + 1)

    if mode == "celebs":
        return df.head(_CELEBRITY_TOP_N).drop(columns="_rank")

    if mode == "rising":
        cohort = df[
            (df["_rank"] > _CELEBRITY_TOP_N)
            & (df["_rank"] <= _RISING_RANK_FLOOR)
            & (df["total_views"] < _RISING_VIEW_CEILING)
        ]
    else:  # mode == 'gems'
        cohort = df[
            (df["_rank"] > _RISING_RANK_FLOOR)
            & (df["total_views"] < _GEMS_VIEW_CEILING)
        ]

    cohort = cohort.dropna(subset=["growth_pct"])
    cohort = cohort.sort_values("growth_pct", ascending=False).head(_TREEMAP_MAX_TILES)
    return cohort.drop(columns="_rank")


_TOP_PERF_MIN_VIEWS = 100_000_000  # filter out micro-accounts with noisy % growth


# Spike of the Day caption thresholds — calibrated from the first week of
# acceleration data (range observed: -0.10 pp to +1.06 pp across all tiers).
# pp = "percentage points" (acceleration is a difference of two percentages).
_CAPTION_THRESHOLDS = (
    (0.05, "↑ Sharp turnaround"),
    (0.01, "↑ Trending up"),
    (-0.01, "→ Steady pace"),
    (-0.05, "↓ Slower than usual"),
    (float("-inf"), "↓ Cooling off"),
)


def _caption_for_acceleration(accel_pp: float) -> str:
    """Map an acceleration value (percentage points) to a one-line caption."""
    for threshold, caption in _CAPTION_THRESHOLDS:
        if accel_pp >= threshold:
            return caption
    return _CAPTION_THRESHOLDS[-1][1]  # unreachable; -inf catches all


def _build_top_performer_card(
    snapshots: pd.DataFrame,
    gender_key: str,
    gender_filter: str | None,
    mode: str,
    *,
    is_default: bool,
    label_override: str | None = None,
) -> str:
    """Return the HTML for one Top Performer card (overall / female / male).

    Top = highest 24h % growth among performers with at least 100M total views.
    The threshold avoids amplifying tiny accounts whose % growth is statistical
    noise. Returns an empty string if no qualifying performer exists.
    """
    window_df = compute_window_growth(snapshots, window_days=1, gender=gender_filter)
    if window_df.empty:
        return ""
    window_df = window_df.copy()
    window_df["growth_amount"] = window_df["total_views"] - window_df["prev_views"]
    window_df = window_df.dropna(subset=["growth_pct"])
    cohort = _apply_mode_filter(window_df, mode)
    # For celebs, still require the min-views floor so noise tiny pages don't win.
    if mode == "celebs":
        qualified = cohort[cohort["total_views"] >= _TOP_PERF_MIN_VIEWS]
        if qualified.empty:
            qualified = cohort
    else:
        qualified = cohort
    if qualified.empty:
        return ""

    # Selection: prefer highest acceleration (today vs 7d baseline) so the card
    # surfaces a different performer most days. Falls back to highest % growth
    # when acceleration can't be computed for anyone (early tracking days, thin
    # fixtures, etc).
    if "acceleration" in qualified.columns and qualified["acceleration"].notna().any():
        candidates = qualified.dropna(subset=["acceleration"])
        top = candidates.sort_values("acceleration", ascending=False).iloc[0]
        use_acceleration = True
    else:
        top = qualified.sort_values("growth_pct", ascending=False).iloc[0]
        use_acceleration = False

    slug = top.name
    name = top["name"]
    pct = float(top["growth_pct"])
    gain = int(top["growth_amount"]) if pd.notna(top["growth_amount"]) else 0

    photo_url = ""
    if "photo_url" in snapshots.columns:
        rows = snapshots[(snapshots["slug"] == slug) & snapshots["photo_url"].notna()]
        if not rows.empty:
            photo_url = rows.sort_values("snapshot_date").iloc[-1]["photo_url"] or ""

    profile_url = f"{_REDIRECT_URL_BASE}{slug}"  # tracked outbound via CF Worker
    # Force absolute path so the img resolves correctly from /, /rising/,
    # /gems/, and /celebs/ alike. Relative 'avatars/...' would break on the
    # per-mode landing pages.
    if photo_url and not photo_url.startswith(("http://", "https://", "/")):
        img_src = f"/{photo_url}"
    else:
        img_src = photo_url
    img_tag = (
        f'<img src="{img_src}" alt="{name}" loading="lazy" referrerpolicy="no-referrer">'
        if photo_url else '<div style="width:56px;height:56px;border-radius:50%;background:#222;flex-shrink:0"></div>'
    )
    label = label_override or _TOP_PERF_LABELS.get(mode, {}).get(gender_key, "Top performer of the day")
    active = " active" if is_default else ""

    if use_acceleration:
        accel = float(top["acceleration"])
        usual_pct = pct - accel  # by definition of acceleration
        caption = _caption_for_acceleration(accel)
        stat_html = (
            f'<span class="top-perf-stat-row">Today: <strong>{pct:+.3f}%</strong></span>'
            f'<span class="top-perf-stat-row">Usual: <strong>{usual_pct:+.3f}%</strong></span>'
            f'<span class="top-perf-caption">{caption}</span>'
        )
    else:
        stat_html = f'<span class="top-perf-stat"><strong>+{pct:.2f}%</strong> · +{gain:,} views (24h)</span>'

    return (
        f'<a class="top-perf{active}" data-mode="{mode}" data-gender="{gender_key}" href="{profile_url}" target="_blank" rel="noopener">'
        f'{img_tag}'
        f'<div class="top-perf-text">'
        f'<span class="top-perf-label">{label}</span>'
        f'<span class="top-perf-name">{name}</span>'
        f'{stat_html}'
        f'</div>'
        f'</a>'
    )


def _build_all_top_performer_cards(snapshots: pd.DataFrame, default_mode: str, default_gender: str) -> str:
    cards: list[str] = []
    for mode in _MODES:
        for gender_key, gender_filter in _GENDER_FILTERS:
            is_default = (mode == default_mode and gender_key == default_gender)
            card = _build_top_performer_card(
                snapshots, gender_key, gender_filter, mode, is_default=is_default
            )
            if card:
                cards.append(card)
    if not cards:
        return ""
    return f'<div class="top-perf-wrap">{"".join(cards)}</div>'


_MODE_LANDING_META = {
    "rising": {
        "title": "Rising Stars — HotMap",
        "description": "Today's fastest-growing performers in the middle tier (ranks 51-250). Treemap of view growth, updated daily. Spot the next breakout.",
    },
    "gems": {
        "title": "Hidden Gems — HotMap",
        "description": "Niche performers (ranks 251-500) gaining traction fast. The deep-cut tier — small accounts with real momentum. Daily heatmap.",
    },
    "celebs": {
        "title": "Top Celebrities — HotMap",
        "description": "The most-viewed performers on Pornhub: top-50 by cumulative views. Daily growth heatmap tracking the established names.",
    },
    "home": {
        "title": "HotMap — who's growing fastest on Pornhub",
        "description": "Live heatmap of view-growth momentum across the top-500 performers. Tile size = % growth in the window, color = rank within the cohort. Updated daily.",
    },
}


def render_treemap_page(
    snapshots: pd.DataFrame,
    output_path: Path | str,
    default_mode: str = "rising",
    canonical_path: str = "/",
    seo_key: str = "home",
) -> None:
    """Render the HotMap treemap page (3 modes x 3 genders x 3 windows = 27 panels).

    `default_mode` controls which Mode button is active on initial load and
    which panel is shown. `canonical_path` + `seo_key` drive the SEO meta tags
    so we can serve distinct landing pages at /, /rising, /gems, /celebs.
    """
    if snapshots.empty:
        raise ValueError("No snapshots to render")

    panels_html_parts: list[str] = []
    default_gender, default_window = "female", 1
    for mode in _MODES:
        for gender_key, gender_filter in _GENDER_FILTERS:
            for window in _WINDOWS:
                full_window = compute_window_growth(snapshots, window_days=window, gender=gender_filter)
                cohort = _apply_mode_filter(full_window, mode) if not full_window.empty else full_window
                if cohort.empty:
                    placeholder_msg = (
                        f'No rising stars for {gender_key} yet'
                        if mode == "rising"
                        else f'No data for {gender_key} celebrities yet'
                    )
                    inner = (
                        f'<div class="empty-panel" style="height:700px;display:flex;'
                        f'align-items:center;justify-content:center;color:#666;'
                        f'border:1px dashed #2a2a2a;border-radius:4px;">'
                        f'{placeholder_msg}</div>'
                    )
                else:
                    figure = _build_treemap_figure(cohort, window_days=window)
                    inner = figure.to_html(include_plotlyjs="cdn", full_html=False)

                active = " active" if (
                    mode == default_mode and gender_key == default_gender and window == default_window
                ) else ""
                panels_html_parts.append(
                    f'<div id="panel-{mode}-{gender_key}-{window}" class="panel{active}">{inner}</div>'
                )

    snapshots = snapshots.copy()
    snapshots["snapshot_date"] = pd.to_datetime(snapshots["snapshot_date"])
    n_days = snapshots["snapshot_date"].nunique()
    latest_date = snapshots["snapshot_date"].max()
    n_performers = snapshots[snapshots["snapshot_date"] == latest_date]["slug"].nunique()
    last_updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    top_perf_card = _build_all_top_performer_cards(snapshots, default_mode=default_mode, default_gender=default_gender)

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

    page = _PAGE_TEMPLATE.format(
        panels="\n    ".join(panels_html_parts),
        last_updated=last_updated,
        n_days=n_days,
        n_performers=n_performers,
        profile_url_base=_PROFILE_URL_BASE,
        redirect_url_base=_REDIRECT_URL_BASE,
        top_perf_card=top_perf_card,
        default_mode=default_mode,
        seo_head=seo_head,
        mode_btn_active_rising=" active" if default_mode == "rising" else "",
        mode_btn_active_gems=" active" if default_mode == "gems" else "",
        mode_btn_active_celebs=" active" if default_mode == "celebs" else "",
        top_nav=_top_nav("map"),
        nav_css=_TOP_NAV_CSS,
        share_card_css=_SHARE_CARD_CSS,
        share_card_html=_SHARE_CARD_HTML,
        share_card_js=_SHARE_CARD_JS,
    )

    Path(output_path).write_text(page)


_SITE_BASE_URL = "https://hotmap.cam"


_PERFORMER_PAGE_TEMPLATE = """<!doctype html>
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
  <style>
    :root {{
      --brand-orange: #ff9000;
      --bg: #0a0a0a;
      --fg: #f5f5f5;
      --muted: #9a9a9a;
      --rule: #1f1f1f;
      --card-bg: #161616;
      --positive: #6cd36a;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
    body {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 24px 16px 56px;
      color: var(--fg);
      background: var(--bg);
      line-height: 1.5;
    }}
    a {{ color: var(--brand-orange); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
{nav_css}
    .hero {{
      display: flex;
      gap: 20px;
      align-items: center;
      padding: 20px;
      background: var(--card-bg);
      border-radius: 10px;
      border-left: 4px solid var(--brand-orange);
      margin-bottom: 20px;
    }}
    .hero img {{
      width: 96px;
      height: 96px;
      border-radius: 50%;
      object-fit: cover;
      background: #222;
      flex-shrink: 0;
    }}
    .hero h1 {{
      margin: 0 0 6px;
      font-size: 28px;
      font-weight: 800;
      letter-spacing: -0.02em;
    }}
    .hero .meta {{
      color: var(--muted);
      font-size: 14px;
    }}
    .hero .rank-pill {{
      display: inline-block;
      background: var(--brand-orange);
      color: #000;
      font-weight: 700;
      font-size: 12px;
      padding: 2px 8px;
      border-radius: 4px;
      margin-left: 6px;
      letter-spacing: 0.5px;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-bottom: 24px;
    }}
    .stat {{
      padding: 14px 16px;
      background: var(--card-bg);
      border-radius: 8px;
      border: 1px solid var(--rule);
    }}
    .stat .label {{
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 1.2px;
      font-weight: 600;
      margin: 0 0 4px;
    }}
    .stat .value {{
      font-size: 22px;
      font-weight: 700;
      letter-spacing: -0.01em;
      margin: 0;
    }}
    .stat .value.pos {{ color: var(--positive); }}
    .stat .value.neu {{ color: var(--muted); }}
    section h2 {{
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: 1.5px;
      color: var(--muted);
      margin: 24px 0 12px;
      font-weight: 600;
    }}
    .chart {{
      background: var(--card-bg);
      border-radius: 8px;
      border: 1px solid var(--rule);
      padding: 8px;
      margin-bottom: 24px;
    }}
    .actions {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      align-items: center;
      margin-bottom: 24px;
    }}
    .external {{
      display: inline-block;
      padding: 10px 18px;
      background: var(--brand-orange);
      color: #000;
      font-weight: 700;
      border-radius: 6px;
    }}
    .external:hover {{ text-decoration: none; opacity: 0.9; }}
    .share {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    .share-btn {{
      display: inline-block;
      padding: 8px 14px;
      background: var(--card-bg);
      color: var(--fg);
      font: inherit;
      font-weight: 600;
      font-size: 13px;
      border: 1px solid var(--rule);
      border-radius: 6px;
      cursor: pointer;
      text-decoration: none;
    }}
    .share-btn:hover {{ border-color: var(--brand-orange); text-decoration: none; }}
    footer {{
      margin-top: 32px;
      padding-top: 16px;
      border-top: 1px solid var(--rule);
      color: var(--muted);
      font-size: 12px;
    }}
    footer a {{ color: var(--muted); text-decoration: underline; }}
  </style>
</head>
<body>
  {top_nav}

  <div class="hero">
    {photo_tag}
    <div>
      <h1>{name}<span class="rank-pill">#{rank}</span></h1>
      <p class="meta">{gender_label} performer · tracked by HotMap</p>
    </div>
  </div>
  {country_html}
  <div class="stats">
    <div class="stat">
      <p class="label">Cumulative views</p>
      <p class="value">{views_label}</p>
    </div>
    <div class="stat">
      <p class="label">1d growth</p>
      <p class="value {growth_class_1d}">{growth_label_1d}</p>
    </div>
    <div class="stat">
      <p class="label">7d growth</p>
      <p class="value {growth_class_7d}">{growth_label_7d}</p>
    </div>
    <div class="stat">
      <p class="label">30d growth</p>
      <p class="value {growth_class_30d}">{growth_label_30d}</p>
    </div>
  </div>

  <section>
    <h2>Views over time</h2>
    <div class="chart">{sparkline}</div>
  </section>

  <div class="actions">
    <a class="external" href="{profile_url}" target="_blank" rel="noopener">Open {name}'s profile on Pornhub →</a>
    <div class="share">
      <a class="share-btn" href="https://twitter.com/intent/tweet?text={share_text}&url={share_url}" target="_blank" rel="noopener" aria-label="Share on X">𝕏 Share</a>
      <a class="share-btn" href="https://t.me/share/url?url={share_url}&text={share_text}" target="_blank" rel="noopener" aria-label="Share on Telegram">📨 Telegram</a>
      <button class="share-btn" type="button" onclick="navigator.clipboard.writeText('{share_url}').then(()=>{{this.textContent='✓ Copied!';setTimeout(()=>this.textContent='🔗 Copy link',1500);}});">🔗 Copy link</button>
    </div>
  </div>

  <footer>
    Updated {last_date} · Part of the <a href="/">HotMap top-500 tracker</a> · Data collected from publicly visible profile pages.
  </footer>
</body>
</html>
"""


def _format_growth(pct: float | None) -> tuple[str, str]:
    """Return (label, css_class) for a % growth value."""
    if pct is None or pd.isna(pct):
        return "n/a", "neu"
    cls = "pos" if pct > 0 else ("neu" if pct == 0 else "pos")  # all positive in practice
    return f"+{pct:.3f}%", cls


def _build_sparkline_html(history: pd.DataFrame) -> str:
    """Build a minimal Plotly sparkline (line chart) for a performer's view history."""
    if history.empty:
        return '<div style="padding:40px;color:#666;text-align:center;">Not enough history to chart yet — check back in a few days.</div>'
    history = history.sort_values("snapshot_date").copy()
    fig = go.Figure(
        go.Scatter(
            x=history["snapshot_date"],
            y=history["total_views"],
            mode="lines+markers",
            line=dict(color="#ff9000", width=2.5),
            marker=dict(size=6, color="#ff9000"),
            hovertemplate="%{x|%Y-%m-%d}: %{y:,} views<extra></extra>",
        )
    )
    fig.update_layout(
        paper_bgcolor="#161616",
        plot_bgcolor="#161616",
        margin=dict(l=50, r=20, t=10, b=40),
        height=240,
        xaxis=dict(showgrid=False, color="#9a9a9a"),
        yaxis=dict(gridcolor="#222", color="#9a9a9a", tickformat=",d"),
        font=dict(family="Inter, sans-serif", color="#f5f5f5", size=11),
    )
    return fig.to_html(include_plotlyjs="cdn", full_html=False)


def render_performer_page(
    snapshots: pd.DataFrame,
    slug: str,
    output_path: Path | str,
    *,
    qualifying_countries: set[str] | None = None,
) -> None:
    """Render a per-performer landing page at `output_path`.

    The page is SEO-optimized (canonical link, Open Graph, Schema.org Person,
    long-tail title) and includes a Plotly sparkline of view history plus 1d/7d/30d
    growth stats. Designed to capture organic search traffic on performer names.
    """
    rows = snapshots[snapshots["slug"] == slug].copy()
    if rows.empty:
        raise ValueError(f"No snapshots for slug {slug!r}")

    rows["snapshot_date"] = pd.to_datetime(rows["snapshot_date"])
    rows = rows.sort_values("snapshot_date")
    latest = rows.iloc[-1]

    name = str(latest["name"])
    gender = str(latest.get("gender") or "")
    total_views = int(latest["total_views"])
    rank = int(latest["rank"])
    last_date = latest["snapshot_date"].strftime("%Y-%m-%d")
    raw_photo = latest.get("photo_url")
    photo_url = "" if (raw_photo is None or pd.isna(raw_photo)) else str(raw_photo)

    # Growth windows
    growth_labels = {}
    growth_classes = {}
    for window in (1, 7, 30):
        baseline_date = latest["snapshot_date"] - pd.Timedelta(days=window)
        baseline_rows = rows[rows["snapshot_date"] == baseline_date]
        if not baseline_rows.empty:
            prev = int(baseline_rows.iloc[0]["total_views"])
            pct = (total_views - prev) / prev * 100 if prev else None
        else:
            pct = None
        label, cls = _format_growth(pct)
        growth_labels[window] = label
        growth_classes[window] = cls

    # Photo for the visible hero block (og:image is handled by _render_seo_head below).
    if photo_url:
        photo_tag = f'<img src="/{photo_url}" alt="{name}" loading="lazy">' if not photo_url.startswith("http") else f'<img src="{photo_url}" alt="{name}" loading="lazy">'
    else:
        photo_tag = '<div style="width:96px;height:96px;border-radius:50%;background:#222;flex-shrink:0"></div>'

    # SEO/social head — consolidated through helper.
    canonical_url = f"{_SITE_BASE_URL}/p/{slug}"
    if photo_url:
        og_image_url = (
            photo_url if photo_url.startswith("http")
            else f"{_SITE_BASE_URL}{photo_url if photo_url.startswith('/') else '/' + photo_url}"
        )
    else:
        og_image_url = None

    person_jsonld = {
        "@context": "https://schema.org",
        "@type": "Person",
        "name": name,
        "url": canonical_url,
        "identifier": slug,
        "sameAs": [f"{_PROFILE_URL_BASE}{slug}"],
        "interactionStatistic": {
            "@type": "InteractionCounter",
            "interactionType": {"@type": "WatchAction"},
            "userInteractionCount": total_views,
        },
    }
    if photo_url:
        person_jsonld["image"] = og_image_url

    breadcrumbs = [
        ("HotMap", "https://hotmap.cam/"),
        ("Charts", "https://hotmap.cam/charts/"),
        (name, canonical_url),
    ]

    seo_title = f"{name} — view statistics, growth, ranking | HotMap"
    seo_description = (
        f"{name} has {total_views:,} cumulative video views as of {last_date}. "
        f"Daily growth: {growth_labels[1]}. Ranked #{rank} on HotMap's top-500 tracker. Updated daily."
    )

    seo_head = _render_seo_head(
        page_type="performer",
        title=seo_title,
        description=seo_description,
        canonical_url=canonical_url,
        og_image_url=og_image_url,
        extra_jsonld=[person_jsonld],
        breadcrumbs=breadcrumbs,
    )

    sparkline = _build_sparkline_html(rows)
    gender_label = {"female": "Female", "male": "Male"}.get(gender, "")

    # URL-encode share text + url for href attributes
    from urllib.parse import quote
    share_url_raw = f"{_SITE_BASE_URL}/p/{slug}"
    share_text_raw = f"{name} — {total_views:,} views, ranked #{rank} on HotMap"
    share_url = quote(share_url_raw, safe="")
    share_text = quote(share_text_raw, safe="")

    # Country cross-link block — only when performer has a non-null country
    # AND that country is in the qualifying set (i.e., a /country/<slug>/ page
    # actually exists).
    country_html = ""
    if qualifying_countries:
        # Look up this performer's most recent country (snapshot date desc).
        my_rows = snapshots[snapshots["slug"] == slug]
        if not my_rows.empty and "country" in my_rows.columns:
            sorted_rows = my_rows.sort_values("snapshot_date", ascending=False)
            country = sorted_rows.iloc[0]["country"]
            if country and not pd.isna(country) and country in qualifying_countries:
                country_slug = _country_slug(country)
                # Inline CSS so the class only appears when the block is emitted.
                country_html = (
                    '<style>'
                    '.performer-country { margin: 16px 0; }'
                    '.performer-country h3 { font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: var(--muted); margin: 0 0 8px; }'
                    '.performer-country a { display: inline-block; background: var(--card-bg); border: 1px solid var(--rule); border-radius: 6px; padding: 4px 10px; font-size: 13px; color: var(--fg); text-decoration: none; }'
                    '.performer-country a:hover { color: var(--brand-orange); }'
                    '</style>'
                    '<section class="performer-country">'
                    '<h3>From</h3>'
                    f'<a href="/country/{country_slug}/">{_html.escape(country)}</a>'
                    '</section>'
                )

    page = _PERFORMER_PAGE_TEMPLATE.format(
        name=name,
        slug=slug,
        rank=rank,
        gender_label=gender_label,
        last_date=last_date,
        views_label=f"{total_views:,}",
        growth_label=growth_labels[1],
        growth_label_1d=growth_labels[1],
        growth_label_7d=growth_labels[7],
        growth_label_30d=growth_labels[30],
        growth_class_1d=growth_classes[1],
        growth_class_7d=growth_classes[7],
        growth_class_30d=growth_classes[30],
        site=_SITE_BASE_URL,
        photo_tag=photo_tag,
        seo_head=seo_head,
        profile_url=f"{_REDIRECT_URL_BASE}{slug}",  # tracked outbound
        sparkline=sparkline,
        share_url=share_url,
        share_text=share_text,
        top_nav=_top_nav(""),  # no nav item highlighted on individual performer
        nav_css=_TOP_NAV_CSS,
        country_html=country_html,
    )

    Path(output_path).write_text(page)


_STATS_PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
{seo_head}
  <link rel="icon" type="image/svg+xml" href="/favicon.svg">
  <link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png">
  <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <style>
    :root {{
      --brand-orange: #ff9000;
      --bg: #0a0a0a;
      --fg: #f5f5f5;
      --muted: #9a9a9a;
      --rule: #1f1f1f;
      --card: #161616;
      --positive: #6cd36a;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }}
    body {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 32px 16px 56px;
      color: var(--fg);
      background: var(--bg);
      line-height: 1.5;
    }}
    a {{ color: var(--brand-orange); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
{nav_css}
    h1 {{
      font-size: 38px;
      font-weight: 800;
      letter-spacing: -0.025em;
      margin: 0 0 6px;
    }}
    .lede {{
      color: var(--muted);
      font-size: 16px;
      margin: 0 0 28px;
    }}
    .hero-grid {{
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 12px;
      margin-bottom: 28px;
    }}
    .hero-card {{
      padding: 18px 20px;
      background: var(--card);
      border: 1px solid var(--rule);
      border-radius: 10px;
    }}
    .hero-card .label {{
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 1.5px;
      font-weight: 600;
      margin: 0 0 6px;
    }}
    .hero-card .value {{
      font-size: 32px;
      font-weight: 800;
      letter-spacing: -0.02em;
      margin: 0;
    }}
    .hero-card .sub {{
      color: var(--muted);
      font-size: 13px;
      margin: 4px 0 0;
    }}
    section {{ margin-bottom: 32px; }}
    section h2 {{
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: 1.5px;
      color: var(--muted);
      margin: 0 0 12px;
      font-weight: 700;
    }}
    .biggest-mover {{
      display: flex;
      gap: 18px;
      padding: 20px;
      background: var(--card);
      border: 1px solid var(--rule);
      border-left: 4px solid var(--brand-orange);
      border-radius: 10px;
      align-items: center;
    }}
    .biggest-mover img {{
      width: 80px;
      height: 80px;
      border-radius: 50%;
      object-fit: cover;
      flex-shrink: 0;
      background: #222;
    }}
    .biggest-mover .name {{
      font-size: 24px;
      font-weight: 800;
      letter-spacing: -0.015em;
      margin: 0 0 4px;
    }}
    .biggest-mover .name a {{ color: var(--fg); }}
    .biggest-mover .stat {{
      font-size: 15px;
      color: var(--muted);
    }}
    .biggest-mover .stat strong {{ color: var(--positive); font-weight: 700; }}
    .leaderboard {{
      background: var(--card);
      border: 1px solid var(--rule);
      border-radius: 10px;
      overflow: hidden;
    }}
    .leaderboard .row {{
      display: grid;
      grid-template-columns: 40px 1fr auto;
      gap: 12px;
      padding: 12px 16px;
      border-top: 1px solid var(--rule);
      align-items: center;
    }}
    .leaderboard .row:first-child {{ border-top: 0; }}
    .leaderboard .rank {{
      color: var(--muted);
      font-weight: 700;
      font-size: 14px;
      text-align: center;
    }}
    .leaderboard .name {{ font-weight: 600; font-size: 15px; }}
    .leaderboard .name a {{ color: var(--fg); }}
    .leaderboard .value {{
      font-weight: 700;
      color: var(--positive);
      font-size: 15px;
      font-variant-numeric: tabular-nums;
    }}
    footer {{
      margin-top: 32px;
      padding-top: 16px;
      border-top: 1px solid var(--rule);
      color: var(--muted);
      font-size: 12px;
    }}
    footer a {{ color: var(--muted); text-decoration: underline; }}
    .share {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 8px;
    }}
    .share-btn {{
      display: inline-block;
      padding: 8px 14px;
      background: var(--card);
      color: var(--fg);
      font: inherit;
      font-weight: 600;
      font-size: 13px;
      border: 1px solid var(--rule);
      border-radius: 6px;
      cursor: pointer;
      text-decoration: none;
    }}
    .share-btn:hover {{ border-color: var(--brand-orange); text-decoration: none; }}
  </style>
</head>
<body>
  {top_nav}

  <h1>HotMap Stats</h1>
  <p class="lede">A live snapshot of Pornhub's view-growth landscape — updated daily at 04:17 UTC.</p>

  <div class="hero-grid">
    <div class="hero-card">
      <p class="label">Performers tracked</p>
      <p class="value">{n_performers:,}</p>
      <p class="sub">across {n_days} days of history</p>
    </div>
    <div class="hero-card">
      <p class="label">Cumulative views</p>
      <p class="value">{total_views_human}</p>
      <p class="sub">{total_views_raw:,} total</p>
    </div>
    <div class="hero-card">
      <p class="label">Views gained (24h)</p>
      <p class="value">+{daily_gain_human}</p>
      <p class="sub">across all tracked performers</p>
    </div>
    <div class="hero-card">
      <p class="label">Average daily growth</p>
      <p class="value">+{avg_growth:.3f}%</p>
      <p class="sub">across the full cohort</p>
    </div>
  </div>

  <section>
    <h2>🔥 Biggest mover today</h2>
    <div class="biggest-mover">
      <img src="/{hero_photo_path}" alt="{hero_name}" loading="lazy">
      <div>
        <p class="name"><a href="/r/{hero_slug}" target="_blank" rel="noopener">{hero_name}</a></p>
        <p class="stat"><strong>+{hero_pct:.2f}%</strong> · +{hero_gain_human} views in 24h</p>
      </div>
    </div>
  </section>

  <section>
    <h2>📈 Top % growth (24h)</h2>
    <div class="leaderboard">{top_pct_rows}</div>
  </section>

  <section>
    <h2>🚀 Top volume gained (24h)</h2>
    <div class="leaderboard">{top_vol_rows}</div>
  </section>

  <section>
    <h2>Share these stats</h2>
    <div class="share">
      <a class="share-btn" href="https://twitter.com/intent/tweet?text={share_text}&url={share_url}" target="_blank" rel="noopener">𝕏 Share on X</a>
      <a class="share-btn" href="https://t.me/share/url?url={share_url}&text={share_text}" target="_blank" rel="noopener">📨 Telegram</a>
      <button class="share-btn" type="button" onclick="navigator.clipboard.writeText('https://hotmap.cam/stats/').then(()=>{{this.textContent='✓ Copied!';setTimeout(()=>this.textContent='🔗 Copy link',1500);}});">🔗 Copy link</button>
    </div>
  </section>

  <footer>
    Updated {last_updated} UTC · Data collected from publicly visible Pornhub profile pages ·
    <a href="/">explore the full treemap</a> · <a href="/data.json">raw data (CC0)</a>
  </footer>
</body>
</html>
"""


def _human_views(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def render_stats_page(snapshots: pd.DataFrame, output_path: Path | str, gender: str = "female") -> None:
    """Render a public summary page at /stats/ — hero numbers + leaderboards.

    By default scoped to female performers (the main audience focus) so the
    page reads as a coherent narrative. `gender=None` to include both.
    Designed to look great as a single screenshot for social shares.
    """
    if snapshots.empty:
        raise ValueError("No snapshots to render")

    snapshots = snapshots.copy()
    snapshots["snapshot_date"] = pd.to_datetime(snapshots["snapshot_date"])

    # Scope to the requested gender slice for the entire page.
    if gender is not None and "gender" in snapshots.columns:
        snapshots = snapshots[snapshots["gender"] == gender]
        if snapshots.empty:
            raise ValueError(f"No snapshots for gender={gender!r}")

    latest_date = snapshots["snapshot_date"].max()
    today = snapshots[snapshots["snapshot_date"] == latest_date]

    n_performers = int(today["slug"].nunique())
    n_days = int(snapshots["snapshot_date"].nunique())
    total_views_raw = int(today["total_views"].sum())

    # 1d window for "biggest mover" + leaderboards — compute on the already-
    # filtered snapshot frame (no need to re-pass gender since it's pre-sliced).
    window = compute_window_growth(snapshots, window_days=1)
    window = window.copy()
    window["growth_amount"] = window["total_views"] - window["prev_views"]
    window = window.dropna(subset=["growth_pct", "growth_amount"])

    daily_gain_total = int(window["growth_amount"].clip(lower=0).sum())
    avg_growth = float(window["growth_pct"].mean()) if len(window) else 0.0

    # Hero: highest % growth among performers with at least 100M views (filter noise)
    qualified = window[window["total_views"] >= _TOP_PERF_MIN_VIEWS]
    if qualified.empty:
        qualified = window
    hero = qualified.sort_values("growth_pct", ascending=False).iloc[0]
    hero_slug = hero.name
    hero_name = hero["name"]
    hero_pct = float(hero["growth_pct"])
    hero_gain = int(hero["growth_amount"])

    # Hero photo path
    hero_photo = ""
    if "photo_url" in snapshots.columns:
        rows = snapshots[(snapshots["slug"] == hero_slug) & snapshots["photo_url"].notna()]
        if not rows.empty:
            raw = rows.sort_values("snapshot_date").iloc[-1]["photo_url"]
            if raw and not str(raw).startswith(("http://", "https://")):
                hero_photo = str(raw)
    if not hero_photo:
        hero_photo = "favicon-512.png"  # fallback if no avatar

    # Build leaderboards (top 5 each by % and absolute)
    def _leaderboard_html(df: pd.DataFrame, value_fn) -> str:
        rows = []
        for rank, (_, r) in enumerate(df.iterrows(), start=1):
            rows.append(
                f'<div class="row">'
                f'<span class="rank">#{rank}</span>'
                f'<span class="name"><a href="/p/{r.name}">{r["name"]}</a></span>'
                f'<span class="value">{value_fn(r)}</span>'
                f'</div>'
            )
        return "".join(rows) or '<div class="row" style="color:#666;justify-content:center">Not enough data yet</div>'

    top_pct_df = qualified.sort_values("growth_pct", ascending=False).head(5)
    top_vol_df = window.sort_values("growth_amount", ascending=False).head(5)
    top_pct_rows = _leaderboard_html(top_pct_df, lambda r: f"+{float(r['growth_pct']):.2f}%")
    top_vol_rows = _leaderboard_html(top_vol_df, lambda r: f"+{_human_views(int(r['growth_amount']))}")

    from urllib.parse import quote
    share_text = quote(
        f"HotMap tracks {n_performers} performers across {n_days} days. "
        f"Today's biggest mover: {hero_name} (+{hero_pct:.2f}%)."
    )
    share_url = quote("https://hotmap.cam/stats/", safe="")

    total_views_human = _human_views(total_views_raw)
    canonical_url = "https://hotmap.cam/stats/"
    og_image_url = f"https://hotmap.cam/{hero_photo}" if hero_photo else None

    collection_jsonld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": f"HotMap Stats — {n_performers} performers, {total_views_human} cumulative views",
        "url": canonical_url,
        "description": (
            f"Single-page summary of HotMap data — hero numbers, biggest movers, leaderboards. "
            f"{n_performers} performers tracked, {total_views_human} cumulative views."
        ),
    }
    breadcrumbs = [
        ("HotMap", "https://hotmap.cam/"),
        ("Stats", canonical_url),
    ]

    seo_head = _render_seo_head(
        page_type="stats",
        title=f"HotMap Stats — {n_performers} performers tracked, {total_views_human} cumulative views",
        description=(
            f"HotMap tracks {n_performers} Pornhub performers across {n_days} days of "
            f"view-growth history. Updated daily. Today's biggest movers, leaderboards by "
            f"1d/7d/30d growth."
        ),
        canonical_url=canonical_url,
        og_image_url=og_image_url,
        extra_jsonld=[collection_jsonld],
        breadcrumbs=breadcrumbs,
    )

    page = _STATS_PAGE_TEMPLATE.format(
        n_performers=n_performers,
        n_days=n_days,
        total_views_raw=total_views_raw,
        total_views_human=total_views_human,
        daily_gain_human=_human_views(daily_gain_total),
        avg_growth=avg_growth,
        hero_slug=hero_slug,
        hero_name=hero_name,
        hero_pct=hero_pct,
        hero_gain_human=_human_views(hero_gain),
        hero_photo_path=hero_photo,
        seo_head=seo_head,
        top_pct_rows=top_pct_rows,
        top_vol_rows=top_vol_rows,
        share_text=share_text,
        share_url=share_url,
        last_updated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        top_nav=_top_nav("stats"),
        nav_css=_TOP_NAV_CSS,
    )

    Path(output_path).write_text(page)


_CHARTS_PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
{seo_head}
  <link rel="icon" type="image/svg+xml" href="/favicon.svg">
  <link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png">
  <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <style>
    :root {{
      --brand-orange: #ff9000;
      --bg: #0a0a0a;
      --fg: #f5f5f5;
      --muted: #9a9a9a;
      --rule: #1f1f1f;
      --card: #161616;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }}
    body {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 32px 16px 56px;
      color: var(--fg);
      background: var(--bg);
      line-height: 1.5;
    }}
    a {{ color: var(--brand-orange); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
{nav_css}
    h1 {{
      font-size: 32px;
      font-weight: 800;
      letter-spacing: -0.025em;
      margin: 0 0 4px;
    }}
    .lede {{ color: var(--muted); margin: 0 0 20px; font-size: 14px; }}
    .controls {{
      position: sticky;
      top: 0;
      background: var(--bg);
      padding: 10px 0;
      z-index: 5;
      border-bottom: 1px solid var(--rule);
      margin-bottom: 16px;
    }}
    .search {{
      width: 100%;
      padding: 12px 14px;
      background: var(--card);
      color: var(--fg);
      border: 1px solid var(--rule);
      border-radius: 8px;
      font: inherit;
      font-size: 15px;
      outline: none;
    }}
    .search:focus {{ border-color: var(--brand-orange); }}
    .gender-tabs {{
      display: flex;
      gap: 6px;
      margin: 10px 0 0;
    }}
    .gender-tabs button {{
      background: var(--card);
      color: var(--fg);
      border: 1px solid var(--rule);
      padding: 7px 14px;
      font: inherit;
      font-weight: 600;
      font-size: 13px;
      cursor: pointer;
      border-radius: 6px;
    }}
    .gender-tabs button.active {{
      background: var(--brand-orange);
      color: #000;
      border-color: var(--brand-orange);
    }}
    .alphabet {{
      display: flex;
      flex-wrap: wrap;
      gap: 2px;
      margin-bottom: 18px;
    }}
    .alphabet a {{
      display: inline-block;
      width: 28px;
      text-align: center;
      padding: 5px 0;
      font-weight: 600;
      font-size: 13px;
      color: var(--muted);
      border-radius: 4px;
    }}
    .alphabet a:hover {{ background: var(--card); color: var(--brand-orange); text-decoration: none; }}
    .letter-section {{ margin-bottom: 32px; }}
    .letter-section h2 {{
      font-size: 22px;
      font-weight: 800;
      color: var(--brand-orange);
      margin: 0 0 8px;
      padding: 4px 0 4px 8px;
      border-left: 3px solid var(--brand-orange);
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
      gap: 8px;
    }}
    .row {{
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 8px 10px;
      background: var(--card);
      border: 1px solid var(--rule);
      border-radius: 8px;
      text-decoration: none;
      color: var(--fg);
      transition: border-color 0.12s, transform 0.12s;
    }}
    .row:hover {{ border-color: var(--brand-orange); text-decoration: none; transform: translateY(-1px); }}
    .row img {{
      width: 40px;
      height: 40px;
      border-radius: 50%;
      object-fit: cover;
      flex-shrink: 0;
      background: #222;
    }}
    .row .name {{ font-weight: 600; font-size: 14px; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .row .badge {{ color: var(--muted); font-size: 11px; flex-shrink: 0; }}
    .row[data-gender="male"] .badge::before {{ content: "♂"; color: #88aaff; margin-right: 4px; }}
    .row[data-gender="female"] .badge::before {{ content: "♀"; color: #ff88aa; margin-right: 4px; }}
    .empty-state {{ color: var(--muted); text-align: center; padding: 40px; }}
    footer {{
      margin-top: 32px;
      padding-top: 16px;
      border-top: 1px solid var(--rule);
      color: var(--muted);
      font-size: 12px;
    }}
  </style>
</head>
<body>
  {top_nav}
  <h1>Performer index</h1>
  <p class="lede">{n} performers tracked. Search by name or jump by letter — click any card for the full stats page.</p>

  <div class="controls">
    <input type="search" id="search" class="search" placeholder="Search performers..." autocomplete="off">
    <div class="gender-tabs">
      <button type="button" class="active" data-gender="all">All</button>
      <button type="button" data-gender="female">Female</button>
      <button type="button" data-gender="male">Male</button>
    </div>
  </div>

  <div class="alphabet">{alphabet_links}</div>

  <main id="list">{letter_sections}</main>

  <p id="empty" class="empty-state" style="display:none">No performers match your search.</p>

  <footer>
    Updated {last_updated} UTC · <a href="/">explore the treemap</a> · <a href="/stats/">view stats</a> · <a href="/data.json">raw data</a>
  </footer>

  <script>
    (function () {{
      var search = document.getElementById('search');
      var rows = document.querySelectorAll('.row');
      var sections = document.querySelectorAll('.letter-section');
      var empty = document.getElementById('empty');
      var genderBtns = document.querySelectorAll('.gender-tabs button');
      var state = {{ q: '', gender: 'all' }};

      function filter() {{
        var anyVisible = false;
        sections.forEach(function (sec) {{
          var sectionVisible = false;
          sec.querySelectorAll('.row').forEach(function (r) {{
            var nameMatch = !state.q || r.dataset.search.indexOf(state.q) !== -1;
            var genderMatch = state.gender === 'all' || r.dataset.gender === state.gender;
            var show = nameMatch && genderMatch;
            r.style.display = show ? '' : 'none';
            if (show) sectionVisible = true;
          }});
          sec.style.display = sectionVisible ? '' : 'none';
          if (sectionVisible) anyVisible = true;
        }});
        empty.style.display = anyVisible ? 'none' : 'block';
      }}

      search.addEventListener('input', function () {{
        state.q = search.value.trim().toLowerCase();
        filter();
      }});
      genderBtns.forEach(function (b) {{
        b.addEventListener('click', function () {{
          genderBtns.forEach(function (x) {{ x.classList.toggle('active', x === b); }});
          state.gender = b.getAttribute('data-gender');
          filter();
        }});
      }});
    }})();
  </script>
</body>
</html>
"""


def render_charts_page(snapshots: pd.DataFrame, output_path: Path | str) -> None:
    """Render an alphabetical performer index at /charts/.

    Lists every performer ever seen in the DB, grouped by first letter,
    with a search box and gender filter. Each row links to /p/<slug>.
    """
    if snapshots.empty:
        raise ValueError("No snapshots to render")

    snapshots = snapshots.copy()
    snapshots["snapshot_date"] = pd.to_datetime(snapshots["snapshot_date"])

    # For each slug pick the most-recent row (best name + most-current photo)
    latest_per_slug = (
        snapshots.sort_values("snapshot_date")
        .drop_duplicates(subset="slug", keep="last")
        .copy()
    )
    latest_per_slug = latest_per_slug.sort_values("name", key=lambda s: s.str.lower())

    # Group by first uppercase letter of the display name (or '#' for non-alpha).
    def _bucket(name: str) -> str:
        if not name:
            return "#"
        c = name.strip()[:1].upper()
        return c if c.isalpha() else "#"

    latest_per_slug["bucket"] = latest_per_slug["name"].fillna("").apply(_bucket)
    buckets_present = sorted(latest_per_slug["bucket"].unique(), key=lambda b: (b == "#", b))

    # Build alphabet bar
    alphabet_links = "".join(
        f'<a href="#letter-{b}">{b}</a>' for b in buckets_present
    )

    # Build per-letter sections
    def _photo_path(p):
        if p is None or pd.isna(p):
            return None
        s = str(p)
        if s.startswith(("http://", "https://", "/")):
            return s
        return f"/{s}"

    def _row(r):
        slug = r["slug"]
        name = str(r["name"])
        gender = str(r.get("gender") or "")
        photo = _photo_path(r.get("photo_url"))
        rank = int(r["rank"]) if pd.notna(r.get("rank")) else None
        img_tag = (
            f'<img src="{photo}" alt="" loading="lazy">'
            if photo
            else '<div style="width:40px;height:40px;border-radius:50%;background:#222;flex-shrink:0"></div>'
        )
        rank_html = f'<span class="badge">#{rank}</span>' if rank else '<span class="badge">—</span>'
        # data-search is used by JS for filtering — lowercased name
        return (
            f'<a class="row" href="/p/{slug}" data-gender="{gender}"'
            f' data-search="{name.lower()}">'
            f'{img_tag}<span class="name">{name}</span>{rank_html}</a>'
        )

    letter_sections_parts = []
    for b in buckets_present:
        rows = latest_per_slug[latest_per_slug["bucket"] == b]
        rows_html = "".join(_row(r) for _, r in rows.iterrows())
        letter_sections_parts.append(
            f'<section class="letter-section" id="letter-{b}">'
            f'<h2>{b}</h2>'
            f'<div class="grid">{rows_html}</div>'
            f'</section>'
        )
    letter_sections_html = "\n".join(letter_sections_parts)

    n_performers = int(latest_per_slug["slug"].nunique())
    canonical_url = "https://hotmap.cam/charts/"

    collection_jsonld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "HotMap Charts — A-Z performer index",
        "url": canonical_url,
        "description": (
            f"Alphabetical index of all {n_performers} Pornhub performers tracked by HotMap. "
            f"Search by name, jump by letter."
        ),
    }
    breadcrumbs = [
        ("HotMap", "https://hotmap.cam/"),
        ("Charts", canonical_url),
    ]

    seo_head = _render_seo_head(
        page_type="charts",
        title="Performer index — HotMap charts",
        description=(
            f"Alphabetical index of all {n_performers} Pornhub performers tracked by HotMap. "
            f"Search by name, jump by letter, see per-performer view-growth stats."
        ),
        canonical_url=canonical_url,
        og_image_url=None,                 # fall back to /og.png
        extra_jsonld=[collection_jsonld],
        breadcrumbs=breadcrumbs,
    )

    page = _CHARTS_PAGE_TEMPLATE.format(
        n=len(latest_per_slug),
        alphabet_links=alphabet_links,
        letter_sections=letter_sections_html,
        last_updated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        top_nav=_top_nav("charts"),
        nav_css=_TOP_NAV_CSS,
        seo_head=seo_head,
    )
    Path(output_path).write_text(page)


_CATEGORIES_PAGE_TEMPLATE = """<!doctype html>
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
  <style>
    :root {{
      --brand-orange: #ff9000;
      --bg: #0a0a0a;
      --fg: #f5f5f5;
      --muted: #9a9a9a;
      --rule: #1f1f1f;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ font-family: 'Inter', sans-serif; }}
    body {{ max-width: 1200px; margin: 0 auto; padding: 32px 16px 56px; color: var(--fg); background: var(--bg); line-height: 1.5; }}
{nav_css}
    h1 {{ font-size: 28px; font-weight: 800; margin: 0 0 8px; }}
    .subtitle {{ color: var(--muted); margin: 0 0 24px; }}
    footer {{ margin-top: 48px; padding-top: 24px; border-top: 1px solid var(--rule); color: var(--muted); font-size: 13px; }}
    footer a {{ color: var(--muted); text-decoration: underline; }}
  </style>
</head>
<body>
  {top_nav}
<h1>Trending categories on Pornhub</h1>
<p class="subtitle">{n_categories} categories tracked · Updated {last_updated} UTC</p>
{treemap}
<script>
  // Click any tile → open PH category landing page in a new tab. customdata[3]
  // is the fully-qualified PH URL provided by the catalog JSON (heterogeneous:
  // /video/incategories/<parent>/<slug>, /video/search?search=<slug>, ?c=NN —
  // PH decides per-category). No worker click-tracking here yet; categories
  // are a navigation aid, the tracked outbound layer is /r/<slug> for performers.
  (function () {{
    function attach() {{
      document.querySelectorAll('.plotly-graph-div').forEach(function (div) {{
        if (div._hotmapBound) return;
        div._hotmapBound = true;
        div.on('plotly_treemapclick', function (evt) {{
          if (!evt || !evt.points || !evt.points.length) return;
          var url = evt.points[0].customdata && evt.points[0].customdata[3];
          if (url) window.open(url, '_blank', 'noopener');
          return false;
        }});
      }});
    }}
    var n = 0;
    var iv = setInterval(function () {{
      attach();
      if (++n > 20) clearInterval(iv);
    }}, 250);
  }})();
</script>
<footer>
  <p>HotMap is an independent project. Category data scraped from publicly visible Pornhub HTML. <a href="/">Back to homepage</a>.</p>
</footer>
</body>
</html>
"""


# Categories that always dominate the catalog because they're meta/quality tags
# (HD Porn, Verified Amateurs, etc.) rather than actual content genres. We scrape
# and store them daily — they may be useful for future comparisons — but exclude
# them from the treemap so it reflects real genre distribution. IDs are PH's own,
# verified stable across multiple bootstraps.
_NON_GENRE_CATEGORY_IDS = frozenset({
    3,    # Amateur
    30,   # Pornstar
    38,   # HD Porn
    105,  # 60FPS
    115,  # Exclusive
    138,  # Verified Amateurs
    139,  # Verified Models
    482,  # Verified Couples
})


def render_categories_treemap(
    category_snapshots: pd.DataFrame,
    output_path: Path | str,
    url_by_id: dict[int, str] | None = None,
) -> None:
    """Render /categories/index.html — treemap of PH category video counts.

    Tile size  = video_count (latest snapshot)
    Tile color = percentile rank of 1-day delta (today − yesterday). When no
                 yesterday snapshot exists for a category, that tile gets a
                 neutral color and delta label '—'.
    Tile label = '<name>\\n<count compact>\\n+<delta> today' (or '—' when no baseline).

    Filters out _NON_GENRE_CATEGORY_IDS — meta-tags like HD Porn, Verified
    Amateurs, etc. that dominate by ubiquity rather than reflect genre signal.

    url_by_id: optional dict mapping category_id → PH outbound URL (from
    parse_category_catalog's 'url' field). When provided, treemap tiles open
    that URL on click — PH's catalog is heterogeneous, so some categories
    redirect to /video/incategories/<parent>/<slug>, others to
    /video/search?search=<slug>, others to ?c=<id>. PH's own JSON tells us
    which. When None or a category_id is missing, falls back to /video/search.

    Raises ValueError on empty input — caller (run.py) treats as 'skip render this day'.
    """
    if category_snapshots.empty:
        raise ValueError("No category snapshots provided")

    df = category_snapshots[
        ~category_snapshots["category_id"].isin(_NON_GENRE_CATEGORY_IDS)
    ].copy()
    if df.empty:
        raise ValueError("No genre categories remain after filtering meta-tags")

    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    latest_date = df["snapshot_date"].max()
    today = df[df["snapshot_date"] == latest_date].set_index("category_id")

    # Baseline = exactly 1 day prior. If yesterday's scrape was missed (gap > 1),
    # the displayed "today" delta would be a lie — fall back to no-baseline state
    # (neutral color, "—" label) instead of silently inflating deltas.
    prior_dates = df[df["snapshot_date"] < latest_date]["snapshot_date"]
    if not prior_dates.empty:
        baseline_date = prior_dates.max()
        gap_days = (latest_date - baseline_date).days
        if gap_days == 1:
            baseline = (
                df[df["snapshot_date"] == baseline_date]
                .set_index("category_id")["video_count"]
                .rename("prev_count")
            )
            today = today.join(baseline, how="left")
        else:
            # Gap > 1 (missed scrape) — refuse to compute a misleading "today" delta.
            today["prev_count"] = pd.NA
    else:
        today["prev_count"] = pd.NA

    today["delta"] = today["video_count"] - today["prev_count"]
    today["has_delta"] = today["delta"].notna()

    # Color metric: percentile rank of delta within categories that have one.
    # Categories without a delta get color_value=0 (neutral mid-scale).
    if today["has_delta"].any() and today["has_delta"].sum() > 1:
        ranked = today.loc[today["has_delta"], "delta"].rank(method="average", pct=True) - 0.5
        today["color_value"] = 0.0
        today.loc[today["has_delta"], "color_value"] = ranked
    else:
        today["color_value"] = 0.0

    # Build display labels
    def _compact(n):
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.0f}K"
        return str(int(n))

    def _delta_label(row):
        if not row["has_delta"]:
            return "—"
        d = int(row["delta"])
        return f"+{d:,}" if d >= 0 else f"{d:,}"

    today["count_label"] = today["video_count"].apply(_compact)
    today["delta_label"] = today.apply(_delta_label, axis=1)
    today["tile_text"] = (
        "<b>" + today["name"] + "</b>"
        + "<br><span style='font-size:11px;color:rgba(0,0,0,0.55)'>"
        + today["count_label"] + "</span>"
        + "<br><span style='font-size:13px;font-weight:600'>"
        + today["delta_label"] + " today</span>"
    )

    rows = today.reset_index()
    # PH-side outbound URL per category. PH's catalog is heterogeneous: some
    # categories live at /video/incategories/<parent>/<slug>, others at
    # /video/search?search=<slug>, others at /video?c=<id>. We embed the
    # PH-provided URL directly so the click handler can window.open() without
    # per-category guesswork. Fallback to a search URL when url_by_id is None
    # or the category id isn't in the lookup.
    #
    # We append ?o=mv&t=w (sort=most_viewed, time=week) so clicks land on
    # this-week's top videos in the category instead of PH's default
    # least-relevant ordering. Works across all three URL shapes — search-
    # backed categories (Deepthroat, AI etc.) especially benefit because PH's
    # raw search is fuzzy; the most-viewed-week sort surfaces real content.
    def _outbound_url(row) -> str:
        url = url_by_id.get(int(row["category_id"])) if url_by_id is not None else None
        if url:
            base = f"https://www.pornhub.com{url}" if url.startswith("/") else url
        else:
            base = f"https://www.pornhub.com/video/search?search={row['slug']}"
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}o=mv&t=w"
    rows["outbound_url"] = rows.apply(_outbound_url, axis=1)

    figure = go.Figure(
        go.Treemap(
            labels=rows["tile_text"],
            ids=rows["category_id"].astype(str),
            parents=[""] * len(rows),
            values=rows["video_count"],
            marker=dict(
                colors=rows["color_value"],
                colorscale="RdYlGn",
                cmid=0,
                cmin=-0.5,
                cmax=0.5,
                showscale=True,
                colorbar=dict(
                    title="Growth (1d)",
                    tickvals=[-0.5, -0.25, 0, 0.25, 0.5],
                    ticktext=["bottom", "low", "median", "high", "top"],
                    thickness=14,
                    outlinewidth=0,
                ),
            ),
            customdata=rows[["name", "video_count", "delta", "outbound_url"]].values,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Total videos: %{customdata[1]:,}<br>"
                "Delta (1d): %{customdata[2]:+,.0f}<br>"
                "<i>click to open category</i>"
                "<extra></extra>"
            ),
            textposition="middle center",
            textfont=dict(family="Inter, sans-serif", size=12, color="#000"),
            tiling=dict(packing="squarify", pad=0),
        )
    )
    figure.update_layout(
        paper_bgcolor="#0a0a0a",
        plot_bgcolor="#0a0a0a",
        margin=dict(l=0, r=130, t=0, b=0),
        height=700,
        font=dict(family="Inter, sans-serif", color="#f5f5f5"),
    )
    treemap_html = figure.to_html(include_plotlyjs="cdn", full_html=False)

    n_categories = len(rows)
    canonical_url = "https://hotmap.cam/categories/"
    title = "Trending Pornhub Categories — Daily Growth Heatmap | HotMap"
    description = (
        f"{n_categories} Pornhub categories ranked by daily video-count growth. "
        f"Real numbers, updated automatically."
    )
    collection_jsonld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": title,
        "url": canonical_url,
        "description": description,
    }
    breadcrumbs = [
        ("HotMap", "https://hotmap.cam/"),
        ("Categories", canonical_url),
    ]
    seo_head = _render_seo_head(
        page_type="category",
        title=title,
        description=description,
        canonical_url=canonical_url,
        og_image_url=None,
        extra_jsonld=[collection_jsonld],
        breadcrumbs=breadcrumbs,
    )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_CATEGORIES_PAGE_TEMPLATE.format(
        seo_head=seo_head,
        nav_css=_TOP_NAV_CSS,
        top_nav=_top_nav("categories"),
        n_categories=n_categories,
        treemap=treemap_html,
        last_updated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
    ), encoding="utf-8")


_COUNTRY_MIN_PERFORMERS = 5  # countries below this don't get a /country/<slug>/ page

# Canonical country name → ISO 3166-1 alpha-2 code, used to build flagcdn.com URLs.
# Covers every value emitted by scraper._NATIONALITY_TO_COUNTRY plus the common
# Birth Place countries we see in profiles. Unknown countries render without a flag.
_COUNTRY_ISO2 = {
    "United States": "us",
    "United Kingdom": "gb",
    "Russia": "ru",
    "Italy": "it",
    "France": "fr",
    "Germany": "de",
    "Spain": "es",
    "Brazil": "br",
    "Mexico": "mx",
    "Japan": "jp",
    "South Korea": "kr",
    "China": "cn",
    "Australia": "au",
    "Canada": "ca",
    "Czech Republic": "cz",
    "Poland": "pl",
    "Ukraine": "ua",
    "Hungary": "hu",
    "Romania": "ro",
    "Argentina": "ar",
    "Colombia": "co",
    "Netherlands": "nl",
    "Sweden": "se",
    "Norway": "no",
    "Finland": "fi",
    "Denmark": "dk",
    "Turkey": "tr",
    "Greece": "gr",
    "Portugal": "pt",
    "India": "in",
    "Philippines": "ph",
    "Thailand": "th",
    "Vietnam": "vn",
    "Indonesia": "id",
    "Bulgaria": "bg",
    "Serbia": "rs",
    "Croatia": "hr",
    "Slovakia": "sk",
    "Slovenia": "si",
    "Ireland": "ie",
    "Belgium": "be",
    "Austria": "at",
    "Cuba": "cu",
    "Dominican Republic": "do",
    "Puerto Rico": "pr",
    "Egypt": "eg",
    "Nigeria": "ng",
    "Armenia": "am",
    "Peru": "pe",
    "Venezuela": "ve",
    "Uruguay": "uy",
    "New Zealand": "nz",
}


def _country_flag_html(country_name: str) -> str:
    """Return a Unicode regional-indicator flag emoji for the country, or empty string.

    Uses inline emoji rather than a third-party flag CDN: <img src=flagcdn.com>
    failed behind ad blockers and strict CSPs, leaving broken-image icons. Emoji
    is rendered by the OS font (Apple Color Emoji, Segoe UI Emoji, Noto Color
    Emoji); older Windows falls back to two-letter glyphs but never to a broken
    icon.
    """
    iso2 = _COUNTRY_ISO2.get(country_name)
    if not iso2:
        return ""
    flag = "".join(chr(0x1F1E6 + ord(c.upper()) - ord("A")) for c in iso2)
    return f'<span class="cat-flag" aria-hidden="true">{flag}</span>'


def _country_slug(country_name: str) -> str:
    """URL slug for a country name: lowercase, ASCII-ish, hyphens for whitespace.

    'Russia' → 'russia', 'United States' → 'united-states', "Cote d'Ivoire" → 'cote-divoire'.
    """
    s = country_name.strip().lower()
    s = _re.sub(r"[^\w\s-]", "", s, flags=_re.UNICODE)
    s = _re.sub(r"[\s_]+", "-", s)
    return s.strip("-")


_COUNTRY_PAGE_TEMPLATE = """<!doctype html>
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
  <style>
    :root {{
      --brand-orange: #ff9000;
      --bg: #0a0a0a;
      --fg: #f5f5f5;
      --muted: #9a9a9a;
      --rule: #1f1f1f;
      --btn-bg: #161616;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ font-family: 'Inter', sans-serif; }}
    body {{ max-width: 1200px; margin: 0 auto; padding: 32px 16px 56px; color: var(--fg); background: var(--bg); line-height: 1.5; }}
{nav_css}
    h1 {{ font-size: 28px; font-weight: 800; margin: 0 0 8px; }}
    .subtitle {{ color: var(--muted); margin: 0 0 24px; }}
    .empty-state {{ padding: 80px 0; text-align: center; color: var(--muted); }}

    /* Spike-of-Day card — mirrors the main treemap page so country pages
       inherit the same visual identity. The treemap's colorbar reserves
       ~120px on the right; margin-right keeps the card edge aligned. */
    .top-perf-wrap {{ margin: 0 0 16px; }}
    @media (max-width: 900px) {{ .top-perf-wrap {{ margin-right: 0; }} }}
    .top-perf {{
      display: none;
      align-items: center;
      gap: 14px;
      padding: 12px 16px;
      background: var(--btn-bg);
      border: 1px solid var(--rule);
      border-left: 3px solid var(--brand-orange);
      border-radius: 8px;
      text-decoration: none;
      color: inherit;
      transition: border-color 0.12s, transform 0.12s;
      max-width: 360px;
    }}
    .top-perf.active {{ display: flex; }}
    .top-perf:hover {{ border-color: var(--brand-orange); transform: translateY(-1px); }}
    .top-perf img {{
      width: 56px; height: 56px; border-radius: 50%; object-fit: cover;
      flex-shrink: 0; background: #222;
    }}
    .top-perf-text {{ display: flex; flex-direction: column; gap: 2px; min-width: 0; }}
    .top-perf-label {{
      color: var(--brand-orange); font-size: 10px; font-weight: 700;
      letter-spacing: 1.5px; text-transform: uppercase;
    }}
    .top-perf-name {{
      color: var(--fg); font-size: 17px; font-weight: 700; letter-spacing: -0.01em;
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }}
    .top-perf-stat {{ color: var(--muted); font-size: 12px; font-weight: 500; }}
    .top-perf-stat strong {{ color: #6cd36a; font-weight: 700; }}
    .top-perf-stat-row {{ display: block; color: var(--muted); font-size: 12px; font-weight: 500; line-height: 1.35; }}
    .top-perf-stat-row strong {{ color: var(--fg); font-weight: 700; font-variant-numeric: tabular-nums; }}
    .top-perf-caption {{
      display: block; color: #6cd36a; font-size: 11px; font-weight: 600;
      letter-spacing: 0.02em; margin-top: 2px;
    }}

    footer {{ margin-top: 48px; padding-top: 24px; border-top: 1px solid var(--rule); color: var(--muted); font-size: 13px; }}
    footer a {{ color: var(--muted); text-decoration: underline; }}
  </style>
</head>
<body>
{top_nav}
<h1>Top performers from {country_name}</h1>
<p class="subtitle">{n_performers} performers tracked · Updated {last_updated} UTC</p>
{top_perf_card}
{treemap}
<script>
  // Click any tile → outbound bounce through /r/<slug> (same CF Worker
  // redirect as the homepage treemap). Plotly renders asynchronously so we
  // poll briefly until the graph div is ready.
  (function () {{
    function attach() {{
      document.querySelectorAll('.plotly-graph-div').forEach(function (div) {{
        if (div._hotmapBound) return;
        div._hotmapBound = true;
        div.on('plotly_treemapclick', function (evt) {{
          if (!evt || !evt.points || !evt.points.length) return;
          var slug = evt.points[0].customdata && evt.points[0].customdata[3];
          if (slug) window.open('/r/' + slug, '_blank', 'noopener');
          return false;
        }});
      }});
    }}
    var n = 0;
    var iv = setInterval(function () {{
      attach();
      if (++n > 20) clearInterval(iv);
    }}, 250);
  }})();
</script>
<footer>
  <p>HotMap is an independent project. <a href="/">Back to homepage</a>.</p>
</footer>
</body>
</html>
"""


def render_country_page(
    snapshots: pd.DataFrame,
    country_name: str,
    output_path: Path | str,
) -> None:
    """Render /country/<slug>/index.html — top performers from one country.

    Tile size = % growth (same metric as homepage), color = acceleration percentile.
    Spike of the Day card surfaces the biggest-momentum performer in the country.
    Raises ValueError when no performers match the country (caller in run.py
    should treat as 'skip render').
    """
    in_country = snapshots[
        (snapshots["country"] == country_name) & (snapshots["gender"] == "female")
    ].copy()
    if in_country.empty:
        raise ValueError(f"No performers for country {country_name!r}")

    in_country["snapshot_date"] = pd.to_datetime(in_country["snapshot_date"])
    latest_date = in_country["snapshot_date"].max()
    n_performers = int(in_country[in_country["snapshot_date"] == latest_date]["slug"].nunique())

    slug = _country_slug(country_name)
    canonical_url = f"https://hotmap.cam/country/{slug}/"
    title = f"Top performers from {country_name} — HotMap"
    description = (
        f"Top pornstars from {country_name} ranked by view-growth momentum. "
        f"{n_performers} performers tracked. Daily heatmap, updated automatically."
    )
    collection_jsonld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": title,
        "url": canonical_url,
        "description": description,
    }
    breadcrumbs = [
        ("HotMap", "https://hotmap.cam/"),
        ("Countries", "https://hotmap.cam/countries/"),
        (country_name, canonical_url),
    ]
    seo_head = _render_seo_head(
        page_type="country",
        title=title,
        description=description,
        canonical_url=canonical_url,
        og_image_url=None,
        extra_jsonld=[collection_jsonld],
        breadcrumbs=breadcrumbs,
    )

    # Build treemap from this country's window-growth cohort.
    window = compute_window_growth(in_country, window_days=1)
    cohort = window.dropna(subset=["growth_pct"]).sort_values("total_views", ascending=False).head(50)

    has_visible_tiles = not cohort.empty and (cohort["prev_views"] >= 1_000_000).any()
    if not has_visible_tiles:
        treemap_html = '<div class="empty-state">Not enough history yet — check back tomorrow.</div>'
    else:
        treemap_html = _build_treemap_figure(cohort, window_days=1).to_html(include_plotlyjs="cdn", full_html=False)

    top_perf_card = _build_top_performer_card(
        in_country, gender_key="all", gender_filter=None, mode="celebs", is_default=True,
        label_override=f"Top from {country_name}",
    )
    # Wrap in .top-perf-wrap so the new CSS in _COUNTRY_PAGE_TEMPLATE applies
    # the same way it does on the homepage; skip the wrapper when the card is
    # empty (no qualifying mover) so the page collapses cleanly.
    if top_perf_card:
        top_perf_card = f'<div class="top-perf-wrap">{top_perf_card}</div>'

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_COUNTRY_PAGE_TEMPLATE.format(
        seo_head=seo_head,
        nav_css=_TOP_NAV_CSS,
        top_nav=_top_nav("countries"),
        country_name=_html.escape(country_name),
        n_performers=n_performers,
        top_perf_card=top_perf_card,
        treemap=treemap_html,
        last_updated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
    ), encoding="utf-8")


_COUNTRIES_INDEX_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
{seo_head}
  <link rel="icon" type="image/svg+xml" href="/favicon.svg">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <style>
    :root {{ --brand-orange: #ff9000; --bg: #0a0a0a; --fg: #f5f5f5; --muted: #9a9a9a; --rule: #1f1f1f; }}
    * {{ box-sizing: border-box; }}
    html, body {{ font-family: 'Inter', sans-serif; }}
    body {{ max-width: 1200px; margin: 0 auto; padding: 32px 16px 56px; color: var(--fg); background: var(--bg); line-height: 1.5; }}
{nav_css}
    h1 {{ font-size: 28px; font-weight: 800; margin: 0 0 8px; }}
    .subtitle {{ color: var(--muted); margin: 0 0 24px; }}
    .cat-list {{ list-style: none; padding: 0; columns: 3; column-gap: 32px; }}
    .cat-list li {{ padding: 4px 0; break-inside: avoid; display: flex; align-items: center; gap: 8px; }}
    .cat-list a {{ color: var(--fg); text-decoration: none; font-weight: 600; }}
    .cat-list a:hover {{ color: var(--brand-orange); }}
    .cat-count {{ color: var(--muted); font-size: 13px; font-weight: 400; }}
    .cat-flag {{ flex: 0 0 auto; font-size: 18px; line-height: 1; }}
    @media (max-width: 720px) {{ .cat-list {{ columns: 2; }} }}
    @media (max-width: 480px) {{ .cat-list {{ columns: 1; }} }}
    footer {{ margin-top: 48px; padding-top: 24px; border-top: 1px solid var(--rule); color: var(--muted); font-size: 13px; }}
    footer a {{ color: var(--muted); text-decoration: underline; }}
  </style>
</head>
<body>
{top_nav}
<h1>All countries</h1>
<p class="subtitle">{n_countries} countries with 5 or more tracked actresses · Updated {last_updated} UTC</p>
<ul class="cat-list">
{rows_html}
</ul>
<footer>
  <p>HotMap is an independent project. <a href="/">Back to homepage</a>.</p>
</footer>
</body>
</html>
"""


def render_countries_index(
    snapshots: pd.DataFrame,
    output_path: Path | str,
) -> None:
    """Render /countries/index.html — alphabetical list of qualifying countries.

    Qualification gate still counts both genders (a country qualifies if it has
    ≥5 tracked performers of any gender), but the displayed performer count
    reflects only female performers — matching what the per-country page shows.
    """
    df = snapshots[snapshots["country"].notna()].copy()
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    latest_date = df["snapshot_date"].max()
    today = df[df["snapshot_date"] == latest_date]

    counts_all = today.groupby("country")["slug"].nunique()
    counts_female = (
        today[today["gender"] == "female"].groupby("country")["slug"].nunique()
    )
    qualifying_countries = sorted(counts_all[counts_all >= _COUNTRY_MIN_PERFORMERS].index)
    qualifying = pd.DataFrame({
        "country": qualifying_countries,
        "n": [int(counts_female.get(c, 0)) for c in qualifying_countries],
    })

    canonical_url = "https://hotmap.cam/countries/"
    title = "All Countries — HotMap"
    description = f"Alphabetical index of all {len(qualifying)} countries with tracked actresses on HotMap."
    collection_jsonld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": title,
        "url": canonical_url,
        "description": description,
    }
    breadcrumbs = [
        ("HotMap", "https://hotmap.cam/"),
        ("Countries", canonical_url),
    ]
    seo_head = _render_seo_head(
        page_type="country",
        title=title,
        description=description,
        canonical_url=canonical_url,
        og_image_url=None,
        extra_jsonld=[collection_jsonld],
        breadcrumbs=breadcrumbs,
    )

    rows_html = "\n".join(
        f'<li>{_country_flag_html(row.country)}'
        f'<a href="/country/{_country_slug(row.country)}/">{_html.escape(row.country)}</a> '
        f'<span class="cat-count">({int(row.n)} actresses)</span></li>'
        for row in qualifying.itertuples(index=False)
    )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_COUNTRIES_INDEX_TEMPLATE.format(
        seo_head=seo_head,
        nav_css=_TOP_NAV_CSS,
        top_nav=_top_nav("countries"),
        n_countries=len(qualifying),
        rows_html=rows_html,
        last_updated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
    ), encoding="utf-8")


def write_sitemap_and_robots(snapshots: pd.DataFrame, public_dir: Path | str) -> None:
    """Write sitemap.xml (home + per-performer pages) and robots.txt."""
    public = Path(public_dir)
    public.mkdir(parents=True, exist_ok=True)

    if snapshots.empty:
        slugs: list[str] = []
        last_mod = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    else:
        snapshots = snapshots.copy()
        snapshots["snapshot_date"] = pd.to_datetime(snapshots["snapshot_date"])
        latest_date = snapshots["snapshot_date"].max()
        # Include every slug ever seen — performers who dropped out still get
        # indexable pages, preserving SEO continuity for old search rankings.
        slugs = sorted(snapshots["slug"].unique().tolist())
        last_mod = latest_date.strftime("%Y-%m-%d")

    # Per-country landing pages — only for countries with >= _COUNTRY_MIN_PERFORMERS
    # in the latest snapshot (matches the threshold render_countries_index uses).
    country_urls: list[str] = []
    if not snapshots.empty and "country" in snapshots.columns:
        today_with_country = snapshots[
            (snapshots["snapshot_date"] == latest_date) & snapshots["country"].notna()
        ]
        counts = today_with_country.groupby("country")["slug"].nunique()
        qualifying = counts[counts >= _COUNTRY_MIN_PERFORMERS].index
        country_urls = [
            f"{_SITE_BASE_URL}/country/{_country_slug(c)}/"
            for c in sorted(qualifying)
        ]

    urls = [
        f"{_SITE_BASE_URL}/",
        f"{_SITE_BASE_URL}/rising/",
        f"{_SITE_BASE_URL}/gems/",
        f"{_SITE_BASE_URL}/celebs/",
        f"{_SITE_BASE_URL}/stats/",
        f"{_SITE_BASE_URL}/categories/",
        f"{_SITE_BASE_URL}/countries/",
        f"{_SITE_BASE_URL}/charts/",
    ] + country_urls + [f"{_SITE_BASE_URL}/p/{s}" for s in slugs]
    sitemap_lines = ['<?xml version="1.0" encoding="UTF-8"?>',
                     '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        sitemap_lines.extend([
            "  <url>",
            f"    <loc>{u}</loc>",
            f"    <lastmod>{last_mod}</lastmod>",
            "    <changefreq>daily</changefreq>",
            "  </url>",
        ])
    sitemap_lines.append("</urlset>")
    (public / "sitemap.xml").write_text("\n".join(sitemap_lines))

    robots = (
        "User-agent: *\n"
        "Allow: /\n"
        f"Sitemap: {_SITE_BASE_URL}/sitemap.xml\n"
    )
    (public / "robots.txt").write_text(robots)


def dump_json(snapshots: pd.DataFrame, output_path: Path | str) -> None:
    """Write snapshot rows to a JSON file as an array of records.

    Dates are serialized as ISO date strings (YYYY-MM-DD), not epoch millis,
    so the file is human-readable and stable across pandas versions.
    """
    if snapshots.empty:
        Path(output_path).write_text("[]")
        return

    out = snapshots.copy()
    out["snapshot_date"] = pd.to_datetime(out["snapshot_date"]).dt.strftime("%Y-%m-%d")
    cols = ["snapshot_date", "slug", "name", "total_views", "rank"]
    if "gender" in out.columns:
        cols.append("gender")
    out[cols].to_json(output_path, orient="records")
