from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

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
    ("map",    "/",       "Map"),
    ("stats",  "/stats",  "Stats"),
    ("charts", "/charts", "Charts"),
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
    .navlinks { display: flex; gap: 2px; flex-wrap: wrap; }
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
    @media (max-width: 520px) {
      .topnav { flex-wrap: wrap; }
      .topnav .logo { width: 160px; }
    }
"""

_PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{seo_title}</title>
  <meta name="description" content="{seo_description}">
  <link rel="canonical" href="https://hotmap.cam{seo_canonical_path}">
  <meta property="og:title" content="{seo_title}">
  <meta property="og:description" content="{seo_description}">
  <meta property="og:url" content="https://hotmap.cam{seo_canonical_path}">
  <meta name="twitter:card" content="summary_large_image">
  <link rel="icon" type="image/svg+xml" href="/favicon.svg">
  <link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png">
  <link rel="icon" type="image/png" sizes="16x16" href="/favicon-16.png">
  <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
  <link rel="shortcut icon" href="/favicon.ico">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <script type="application/ld+json">{{
    "@context": "https://schema.org",
    "@type": "Dataset",
    "name": "HotMap — Pornhub top-500 view growth",
    "description": "Daily snapshot of cumulative video views for the top-500 Pornhub performers, broken down by gender, with day-over-day growth rates over 1d / 7d / 30d windows.",
    "url": "https://hotmap.cam/",
    "license": "https://creativecommons.org/publicdomain/zero/1.0/",
    "creator": {{ "@type": "Person", "name": "ansvier" }},
    "distribution": [
      {{ "@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": "https://hotmap.cam/data.json" }}
    ],
    "keywords": ["pornstars", "view growth", "analytics", "treemap", "rankings"],
    "isAccessibleForFree": true
  }}</script>
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
      max-width: 1400px;
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
      /* Align the card's right edge with where the treemap tiles end —
         Plotly's colorbar eats ~100px on the right of the figure, so we
         pull the card in by the same amount on wide viewports. */
      margin-right: 110px;
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
      color: var(--muted);
      font-size: 14px;
      font-weight: 400;
      letter-spacing: 0;
      margin-left: 8px;
    }}
    .controls {{
      display: flex;
      flex-wrap: wrap;
      gap: 24px;
      margin: 16px 0 20px;
    }}
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
  </style>
</head>
<body>
  {top_nav}
  <header class="hero">
    <p class="tagline">Today's hottest performers. <span class="hint">Click a tile to open the profile.</span></p>
    {top_perf_card}
  </header>

  <div class="controls">
    <div class="toggle" role="tablist" aria-label="Mode">
      <span class="toggle-label">Mode</span>
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
    <div class="toggle">
      <button type="button" id="share-btn" class="share-btn" aria-label="Save image">
        <span class="share-icon" aria-hidden="true">⤓</span> Share image
      </button>
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
      var MODE_PATHS = {{ rising: '/rising', gems: '/gems', celebs: '/celebs' }};

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

      // Share: capture the hero + active treemap to PNG and download.
      var shareBtn = document.getElementById('share-btn');
      if (shareBtn) {{
        shareBtn.addEventListener('click', function () {{
          if (typeof html2canvas === 'undefined') {{
            alert('Share library still loading — try again in a second.');
            return;
          }}
          shareBtn.classList.add('busy');
          var stamp = new Date().toISOString().slice(0, 10);
          var activePanel = document.querySelector('.panel.active');
          // Create a temporary capture wrapper containing logo + top-perf + active panel.
          var wrap = document.createElement('div');
          wrap.style.background = '#0a0a0a';
          wrap.style.padding = '24px';
          wrap.style.position = 'fixed';
          wrap.style.top = '-99999px';
          wrap.style.left = '0';
          wrap.style.width = '1280px';
          wrap.appendChild(document.querySelector('.hero').cloneNode(true));
          if (activePanel) wrap.appendChild(activePanel.cloneNode(true));
          document.body.appendChild(wrap);
          html2canvas(wrap, {{ backgroundColor: '#0a0a0a', scale: 2, useCORS: true }})
            .then(function (canvas) {{
              var link = document.createElement('a');
              link.download = 'hotmap-' + state.gender + '-' + state.window + 'd-' + stamp + '.png';
              link.href = canvas.toDataURL('image/png');
              link.click();
            }})
            .catch(function (err) {{
              console.error('Share failed:', err);
              alert('Could not generate image. See console.');
            }})
            .finally(function () {{
              document.body.removeChild(wrap);
              shareBtn.classList.remove('busy');
            }});
        }});
      }}
    }})();
  </script>
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
    return out


def _format_views(n: int) -> str:
    """Compact: 464_114_451 -> '464M', 1_234_567 -> '1.2M', 950 -> '950'."""
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.0f}M" if n >= 100_000_000 else f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _build_treemap_figure(window: pd.DataFrame, window_days: int) -> go.Figure:
    """Build one Plotly Treemap figure for a single (gender, window) view.

    Tile size encodes the absolute number of views gained over the window so
    high-volume performers and rising stars both show up in relative scale.
    Tile color is growth-rate relative to the median of the visible set
    (green = running ahead of the pack, red = falling behind).
    Rows without a baseline (no row N days ago) are dropped — they wouldn't
    have a meaningful size or color value anyway.
    """
    rows = window.reset_index().copy()
    rows["growth_amount"] = rows["total_views"] - rows["prev_views"]
    rows = rows.dropna(subset=["growth_amount", "growth_pct"]).copy()
    rows["growth_amount"] = rows["growth_amount"].clip(lower=0)

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
            values=rows["growth_amount"],
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
        margin=dict(l=0, r=0, t=0, b=0),
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


def _build_top_performer_card(
    snapshots: pd.DataFrame,
    gender_key: str,
    gender_filter: str | None,
    mode: str,
    *,
    is_default: bool,
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

    top = qualified.sort_values("growth_pct", ascending=False).iloc[0]
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
    label = _TOP_PERF_LABELS.get(mode, {}).get(gender_key, "Top performer of the day")
    active = " active" if is_default else ""

    return (
        f'<a class="top-perf{active}" data-mode="{mode}" data-gender="{gender_key}" href="{profile_url}" target="_blank" rel="noopener">'
        f'{img_tag}'
        f'<div class="top-perf-text">'
        f'<span class="top-perf-label">{label}</span>'
        f'<span class="top-perf-name">{name}</span>'
        f'<span class="top-perf-stat"><strong>+{pct:.2f}%</strong> · +{gain:,} views (24h)</span>'
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
        "description": "Live heatmap of view growth: tile size = views gained in the window, color = growth pace relative to the median.",
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
    page = _PAGE_TEMPLATE.format(
        panels="\n    ".join(panels_html_parts),
        last_updated=last_updated,
        n_days=n_days,
        n_performers=n_performers,
        profile_url_base=_PROFILE_URL_BASE,
        redirect_url_base=_REDIRECT_URL_BASE,
        top_perf_card=top_perf_card,
        default_mode=default_mode,
        seo_title=meta["title"],
        seo_description=meta["description"],
        seo_canonical_path=canonical_path,
        mode_btn_active_rising=" active" if default_mode == "rising" else "",
        mode_btn_active_gems=" active" if default_mode == "gems" else "",
        mode_btn_active_celebs=" active" if default_mode == "celebs" else "",
        top_nav=_top_nav("map"),
        nav_css=_TOP_NAV_CSS,
    )

    Path(output_path).write_text(page)


_SITE_BASE_URL = "https://hotmap.cam"


_PERFORMER_PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{name} — view statistics, growth, ranking | HotMap</title>
  <meta name="description" content="{name} has {views_label} cumulative video views as of {last_date}. Daily growth: {growth_label}. Ranked #{rank} on HotMap's top-500 tracker. Updated daily.">
  <link rel="canonical" href="{site}/p/{slug}">
  <meta property="og:type" content="profile">
  <meta property="og:title" content="{name} — HotMap statistics">
  <meta property="og:description" content="{name}: {views_label} cumulative views. Ranked #{rank}. Daily growth: {growth_label}.">
  <meta property="og:url" content="{site}/p/{slug}">
  {og_image_tag}
  <meta name="twitter:card" content="summary">
  <link rel="icon" type="image/svg+xml" href="/favicon.svg">
  <link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png">
  <link rel="icon" type="image/png" sizes="16x16" href="/favicon-16.png">
  <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
  <link rel="shortcut icon" href="/favicon.ico">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <script type="application/ld+json">{json_ld}</script>
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
      max-width: 900px;
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

    # Photo and og:image
    if photo_url:
        photo_tag = f'<img src="/{photo_url}" alt="{name}" loading="lazy">' if not photo_url.startswith("http") else f'<img src="{photo_url}" alt="{name}" loading="lazy">'
        og_image_url = f"{_SITE_BASE_URL}/{photo_url}" if not photo_url.startswith("http") else photo_url
        og_image_tag = f'<meta property="og:image" content="{og_image_url}">'
    else:
        photo_tag = '<div style="width:96px;height:96px;border-radius:50%;background:#222;flex-shrink:0"></div>'
        og_image_tag = ""

    # Schema.org Person JSON-LD
    import json as _json
    json_ld = _json.dumps({
        "@context": "https://schema.org",
        "@type": "Person",
        "name": name,
        "url": f"{_SITE_BASE_URL}/p/{slug}",
        "sameAs": [f"{_PROFILE_URL_BASE}{slug}"],
        "interactionStatistic": {
            "@type": "InteractionCounter",
            "interactionType": {"@type": "WatchAction"},
            "userInteractionCount": total_views,
        },
    })

    sparkline = _build_sparkline_html(rows)
    gender_label = {"female": "Female", "male": "Male"}.get(gender, "")

    # URL-encode share text + url for href attributes
    from urllib.parse import quote
    share_url_raw = f"{_SITE_BASE_URL}/p/{slug}"
    share_text_raw = f"{name} — {total_views:,} views, ranked #{rank} on HotMap"
    share_url = quote(share_url_raw, safe="")
    share_text = quote(share_text_raw, safe="")

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
        og_image_tag=og_image_tag,
        profile_url=f"{_REDIRECT_URL_BASE}{slug}",  # tracked outbound
        sparkline=sparkline,
        json_ld=json_ld,
        share_url=share_url,
        share_text=share_text,
        top_nav=_top_nav(""),  # no nav item highlighted on individual performer
        nav_css=_TOP_NAV_CSS,
    )

    Path(output_path).write_text(page)


_STATS_PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>HotMap Stats — {n_performers} performers tracked, {total_views_human} cumulative views</title>
  <meta name="description" content="HotMap tracks {n_performers} Pornhub performers across {n_days} days of view-growth history. Updated daily. Today's biggest mover: {hero_name} (+{hero_pct:.2f}%, +{hero_gain_human} views).">
  <link rel="canonical" href="https://hotmap.cam/stats">
  <meta property="og:title" content="HotMap Stats — {n_performers} performers, {total_views_human} cumulative views">
  <meta property="og:description" content="Today's biggest mover: {hero_name} (+{hero_pct:.2f}%, +{hero_gain_human} views). Live view-growth tracker.">
  <meta property="og:url" content="https://hotmap.cam/stats">
  <meta property="og:image" content="https://hotmap.cam/{hero_photo_path}">
  <meta name="twitter:card" content="summary_large_image">
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
      max-width: 900px;
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
      <button class="share-btn" type="button" onclick="navigator.clipboard.writeText('https://hotmap.cam/stats').then(()=>{{this.textContent='✓ Copied!';setTimeout(()=>this.textContent='🔗 Copy link',1500);}});">🔗 Copy link</button>
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
    """Render a public summary page at /stats — hero numbers + leaderboards.

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
    share_url = quote("https://hotmap.cam/stats", safe="")

    page = _STATS_PAGE_TEMPLATE.format(
        n_performers=n_performers,
        n_days=n_days,
        total_views_raw=total_views_raw,
        total_views_human=_human_views(total_views_raw),
        daily_gain_human=_human_views(daily_gain_total),
        avg_growth=avg_growth,
        hero_slug=hero_slug,
        hero_name=hero_name,
        hero_pct=hero_pct,
        hero_gain_human=_human_views(hero_gain),
        hero_photo_path=hero_photo,
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
  <title>Performer index — HotMap charts</title>
  <meta name="description" content="Alphabetical index of all {n} Pornhub performers tracked by HotMap. Search by name, jump by letter, click through to per-performer stats.">
  <link rel="canonical" href="https://hotmap.cam/charts">
  <meta property="og:title" content="HotMap Charts — A-Z performer index">
  <meta property="og:description" content="All {n} tracked performers. Search, browse, see per-performer view-growth stats.">
  <meta property="og:url" content="https://hotmap.cam/charts">
  <meta name="twitter:card" content="summary_large_image">
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
      max-width: 1100px;
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
    Updated {last_updated} UTC · <a href="/">explore the treemap</a> · <a href="/stats">view stats</a> · <a href="/data.json">raw data</a>
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
    """Render an alphabetical performer index at /charts.

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

    page = _CHARTS_PAGE_TEMPLATE.format(
        n=len(latest_per_slug),
        alphabet_links=alphabet_links,
        letter_sections=letter_sections_html,
        last_updated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        top_nav=_top_nav("charts"),
        nav_css=_TOP_NAV_CSS,
    )
    Path(output_path).write_text(page)


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

    urls = [
        f"{_SITE_BASE_URL}/",
        f"{_SITE_BASE_URL}/rising",
        f"{_SITE_BASE_URL}/gems",
        f"{_SITE_BASE_URL}/celebs",
        f"{_SITE_BASE_URL}/stats",
        f"{_SITE_BASE_URL}/charts",
    ] + [f"{_SITE_BASE_URL}/p/{s}" for s in slugs]
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
