from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go


_PROFILE_URL_BASE = "https://www.pornhub.com/pornstar/"

_PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>HotMap — who's growing fastest on Pornhub</title>
  <meta name="description" content="Live heatmap of view growth: tile size = views gained in the window, color = growth pace relative to the median.">
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
      max-width: 1400px;
      margin: 0 auto;
      padding: 32px 16px 56px;
      color: var(--fg);
      background: var(--bg);
      line-height: 1.5;
      font-feature-settings: 'cv11', 'ss01';
    }}
    .hero {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 24px;
      margin-bottom: 24px;
      flex-wrap: wrap;
    }}
    .hero-left {{
      display: flex;
      flex-direction: column;
      gap: 8px;
      flex: 1 1 420px;
      min-width: 280px;
    }}
    .top-perf-wrap {{
      flex: 0 0 auto;
      align-self: flex-start;
      margin-right: 180px;
    }}
    @media (max-width: 1200px) {{ .top-perf-wrap {{ margin-right: 80px; }} }}
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
      font-size: 22px;
      font-weight: 700;
      letter-spacing: -0.02em;
      margin: 4px 0 0;
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
  <header class="hero">
    <div class="hero-left">
      <svg class="logo" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 100" role="img" aria-label="HotMap">
        <rect width="400" height="100" fill="#000"/>
        <text x="20" y="78"
              font-family="'Arial Black','Helvetica Neue',Helvetica,Arial,sans-serif"
              font-weight="900" font-size="76" fill="#fff"
              letter-spacing="-3">HOT</text>
        <rect x="198" y="14" width="184" height="72" rx="14" fill="#ff9000"/>
        <text x="214" y="72"
              font-family="'Arial Black','Helvetica Neue',Helvetica,Arial,sans-serif"
              font-weight="900" font-size="60" fill="#000"
              letter-spacing="-3">MAP</text>
      </svg>
      <p class="tagline">Today's hottest performers. <span class="hint">Click a tile to open the profile.</span></p>
    </div>
    {top_perf_card}
  </header>

  <div class="controls">
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
      var state = {{ gender: 'female', window: '1' }};
      var panels = document.querySelectorAll('.panel');

      var topPerfCards = document.querySelectorAll('.top-perf');
      function refresh() {{
        var activeId = 'panel-' + state.gender + '-' + state.window;
        panels.forEach(function (p) {{
          p.classList.toggle('active', p.id === activeId);
        }});
        topPerfCards.forEach(function (c) {{
          c.classList.toggle('active', c.getAttribute('data-gender') === state.gender);
        }});
        window.dispatchEvent(new Event('resize'));
      }}

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

      bind('.gender', 'gender');
      bind('.window', 'window');

      // Click any tile to open the performer profile in a new tab.
      var PROFILE_URL_BASE = '{profile_url_base}';
      function attachClickHandlers() {{
        document.querySelectorAll('.plotly-graph-div').forEach(function (div) {{
          if (div._hotmapBound) return;
          div._hotmapBound = true;
          div.on('plotly_treemapclick', function (evt) {{
            if (!evt || !evt.points || !evt.points.length) return;
            var slug = evt.points[0].customdata && evt.points[0].customdata[3];
            if (slug) {{
              window.open(PROFILE_URL_BASE + slug, '_blank', 'noopener');
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
    # Floor at 0; in theory views are monotonic, but data hiccups happen.
    rows["growth_amount"] = rows["growth_amount"].clip(lower=0)

    finite = rows["growth_pct"]
    median_growth = float(finite.median()) if len(finite) else 0.0
    rows["relative_growth"] = rows["growth_pct"] - median_growth

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

    cmax = float(rows["relative_growth"].abs().max()) if len(rows) else 1.0
    if cmax < 1e-9:
        cmax = 1.0

    figure = go.Figure(
        go.Treemap(
            labels=rows["tile_text"],
            ids=rows["slug"],
            parents=[""] * len(rows),
            values=rows["growth_amount"],
            marker=dict(
                colors=rows["relative_growth"],
                colorscale="RdYlGn",
                cmid=0,
                cmin=-cmax,
                cmax=cmax,
                showscale=True,
                colorbar=dict(
                    title=f"Δ vs median ({window_days}d)",
                    tickformat="+.2f",
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


_TOP_PERF_LABELS = {
    "all": "Top performer of the day",
    "female": "Top female of the day",
    "male": "Top male of the day",
}


_TOP_PERF_MIN_VIEWS = 100_000_000  # filter out micro-accounts with noisy % growth


def _build_top_performer_card(
    snapshots: pd.DataFrame,
    gender_key: str,
    gender_filter: str | None,
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
    qualified = window_df[window_df["total_views"] >= _TOP_PERF_MIN_VIEWS]
    if qualified.empty:
        # Fallback: if nobody clears the bar (unlikely with a top-50 scrape),
        # use the highest-growth among whatever we have.
        qualified = window_df
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

    profile_url = f"{_PROFILE_URL_BASE}{slug}"
    img_tag = (
        f'<img src="{photo_url}" alt="{name}" loading="lazy" referrerpolicy="no-referrer">'
        if photo_url else '<div style="width:56px;height:56px;border-radius:50%;background:#222;flex-shrink:0"></div>'
    )
    label = _TOP_PERF_LABELS.get(gender_key, "Top performer of the day")
    active = " active" if is_default else ""

    return (
        f'<a class="top-perf{active}" data-gender="{gender_key}" href="{profile_url}" target="_blank" rel="noopener">'
        f'{img_tag}'
        f'<div class="top-perf-text">'
        f'<span class="top-perf-label">{label}</span>'
        f'<span class="top-perf-name">{name}</span>'
        f'<span class="top-perf-stat"><strong>+{pct:.2f}%</strong> · +{gain:,} views (24h)</span>'
        f'</div>'
        f'</a>'
    )


def _build_all_top_performer_cards(snapshots: pd.DataFrame, default_gender: str) -> str:
    cards: list[str] = []
    for gender_key, gender_filter in _GENDER_FILTERS:
        card = _build_top_performer_card(
            snapshots, gender_key, gender_filter, is_default=(gender_key == default_gender)
        )
        if card:
            cards.append(card)
    if not cards:
        return ""
    return f'<div class="top-perf-wrap">{"".join(cards)}</div>'


def render_treemap_page(snapshots: pd.DataFrame, output_path: Path | str) -> None:
    """Render the HotMap treemap page (3 windows x 3 gender filters)."""
    if snapshots.empty:
        raise ValueError("No snapshots to render")

    panels_html_parts: list[str] = []
    default_gender, default_window = "female", 1
    for gender_key, gender_filter in _GENDER_FILTERS:
        for window in _WINDOWS:
            window_df = compute_window_growth(snapshots, window_days=window, gender=gender_filter)
            if window_df.empty:
                # Show an empty grey panel for missing data (e.g., no male rows yet).
                placeholder = (
                    f'<div class="empty-panel" style="height:700px;display:flex;'
                    f'align-items:center;justify-content:center;color:#666;'
                    f'border:1px dashed #2a2a2a;border-radius:4px;">'
                    f'No data for {gender_key} performers yet</div>'
                )
                inner = placeholder
            else:
                figure = _build_treemap_figure(window_df, window_days=window)
                inner = figure.to_html(include_plotlyjs="cdn", full_html=False)

            active = " active" if (gender_key == default_gender and window == default_window) else ""
            panels_html_parts.append(
                f'<div id="panel-{gender_key}-{window}" class="panel{active}">{inner}</div>'
            )

    snapshots = snapshots.copy()
    snapshots["snapshot_date"] = pd.to_datetime(snapshots["snapshot_date"])
    n_days = snapshots["snapshot_date"].nunique()
    latest_date = snapshots["snapshot_date"].max()
    n_performers = snapshots[snapshots["snapshot_date"] == latest_date]["slug"].nunique()
    last_updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    top_perf_card = _build_all_top_performer_cards(snapshots, default_gender=default_gender)

    page = _PAGE_TEMPLATE.format(
        panels="\n    ".join(panels_html_parts),
        last_updated=last_updated,
        n_days=n_days,
        n_performers=n_performers,
        profile_url_base=_PROFILE_URL_BASE,
        top_perf_card=top_perf_card,
    )

    Path(output_path).write_text(page)


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
