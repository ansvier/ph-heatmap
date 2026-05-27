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
  <title>HotMap — Daily Pornhub view-growth treemap</title>
  <meta name="description" content="Treemap of the top Pornhub performers: tile size = cumulative views, color = growth relative to the median.">
  <style>
    :root {{
      --brand-orange: #ff9000;
      --bg: #0f0f0f;
      --fg: #f5f5f5;
      --muted: #999;
      --rule: #2a2a2a;
      --btn-bg: #1a1a1a;
      --btn-bg-active: #ff9000;
      --btn-fg: #f5f5f5;
      --btn-fg-active: #000;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
      max-width: 1400px;
      margin: 0 auto;
      padding: 24px 16px 48px;
      color: var(--fg);
      background: var(--bg);
      line-height: 1.5;
    }}
    header {{ margin-bottom: 16px; }}
    .logo {{
      display: block;
      width: 280px;
      max-width: 100%;
      height: auto;
      margin-bottom: 12px;
    }}
    header p {{ color: var(--muted); margin: 0; }}
    .controls {{
      display: flex;
      flex-wrap: wrap;
      gap: 16px;
      margin: 16px 0;
    }}
    .toggle {{
      display: flex;
      gap: 8px;
      align-items: center;
    }}
    .toggle-label {{
      color: var(--muted);
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: 1px;
      margin-right: 4px;
    }}
    .toggle button {{
      background: var(--btn-bg);
      color: var(--btn-fg);
      border: 1px solid var(--rule);
      padding: 8px 14px;
      font: inherit;
      font-weight: 600;
      cursor: pointer;
      border-radius: 4px;
      transition: background 0.12s, color 0.12s, border-color 0.12s;
    }}
    .toggle button:hover {{ border-color: var(--brand-orange); }}
    .toggle button.active {{
      background: var(--btn-bg-active);
      color: var(--btn-fg-active);
      border-color: var(--brand-orange);
    }}
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
  <header>
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
    <p>Top Pornhub performers by cumulative video views. Tile size = total views. Color = growth relative to the median of the visible set. Click a tile to open the profile.</p>
  </header>

  <div class="controls">
    <div class="toggle" role="tablist" aria-label="Gender filter">
      <span class="toggle-label">Gender</span>
      <button type="button" class="active gender" data-gender="all">All</button>
      <button type="button" class="gender" data-gender="female">Female</button>
      <button type="button" class="gender" data-gender="male">Male</button>
    </div>
    <div class="toggle" role="tablist" aria-label="Window">
      <span class="toggle-label">Window</span>
      <button type="button" class="active window" data-window="1">1d</button>
      <button type="button" class="window" data-window="7">7d</button>
      <button type="button" class="window" data-window="30">30d</button>
    </div>
  </div>

  <main>
    {panels}
  </main>

  <footer>
    <p class="stats">Updated {last_updated} UTC · {n_days} days of history · {n_performers} performers tracked · <a href="https://github.com/ansvier/ph-heatmap">source on GitHub</a> · <a href="data.json">raw data (JSON)</a></p>
    <p class="disclaimer">HotMap is an independent project. Data is collected from publicly visible Pornhub profile pages; no video content is hosted here.</p>
  </footer>

  <script>
    (function () {{
      var state = {{ gender: 'all', window: '1' }};
      var panels = document.querySelectorAll('.panel');

      function refresh() {{
        var activeId = 'panel-' + state.gender + '-' + state.window;
        panels.forEach(function (p) {{
          p.classList.toggle('active', p.id === activeId);
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

    Color encodes growth relative to the median of the visible set so the user
    sees who's running hotter/colder than the pack regardless of overall growth
    magnitude. Tile labels display the absolute growth percentage.
    """
    rows = window.reset_index().copy()
    finite = rows["growth_pct"].dropna()
    median_growth = float(finite.median()) if len(finite) else 0.0
    rows["relative_growth"] = rows["growth_pct"] - median_growth

    rows["views_label"] = rows["total_views"].apply(_format_views)
    rows["pct_label"] = rows["growth_pct"].apply(
        lambda v: "n/a" if pd.isna(v) else f"{v:+.2f}%"
    )
    rows["tile_text"] = (
        rows["name"] + "<br>" + rows["views_label"] + "<br>" + rows["pct_label"]
    )

    rel_finite = rows["relative_growth"].dropna()
    cmax = float(rel_finite.abs().max()) if len(rel_finite) else 1.0
    if cmax < 1e-9:
        cmax = 1.0

    figure = go.Figure(
        go.Treemap(
            labels=rows["tile_text"],
            ids=rows["slug"],  # unique per tile
            parents=[""] * len(rows),
            values=rows["total_views"],
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
                ),
            ),
            customdata=rows[["name", "total_views", "growth_pct", "slug"]].values,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Total views: %{customdata[1]:,}<br>"
                "Growth (" + str(window_days) + "d): %{customdata[2]:+.3f}%<br>"
                "<i>click to open profile</i>"
                "<extra></extra>"
            ),
            textposition="middle center",
            textfont=dict(size=14, color="#000"),
            tiling=dict(packing="squarify", pad=2),
        )
    )
    figure.update_layout(
        paper_bgcolor="#0f0f0f",
        plot_bgcolor="#0f0f0f",
        margin=dict(l=0, r=0, t=0, b=0),
        height=700,
        font=dict(color="#f5f5f5"),
    )
    return figure


_WINDOWS = (1, 7, 30)
_GENDER_FILTERS = (("all", None), ("female", "female"), ("male", "male"))


def render_treemap_page(snapshots: pd.DataFrame, output_path: Path | str) -> None:
    """Render the HotMap treemap page (3 windows x 3 gender filters)."""
    if snapshots.empty:
        raise ValueError("No snapshots to render")

    panels_html_parts: list[str] = []
    default_gender, default_window = "all", 1
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

    page = _PAGE_TEMPLATE.format(
        panels="\n    ".join(panels_html_parts),
        last_updated=last_updated,
        n_days=n_days,
        n_performers=n_performers,
        profile_url_base=_PROFILE_URL_BASE,
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
