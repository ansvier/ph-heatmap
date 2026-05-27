from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go


_PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>HotMap — Daily Pornhub view-growth treemap</title>
  <meta name="description" content="Treemap of the top-50 Most Viewed Pornstars on Pornhub: tile size = cumulative video views, color = view growth over the selected window.">
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
      max-width: 280px;
      width: 100%;
      height: auto;
      margin-bottom: 12px;
    }}
    header p {{ color: var(--muted); margin: 0; }}
    .toggle {{
      display: flex;
      gap: 8px;
      margin: 16px 0;
    }}
    .toggle button {{
      background: var(--btn-bg);
      color: var(--btn-fg);
      border: 1px solid var(--rule);
      padding: 8px 16px;
      font: inherit;
      font-weight: 600;
      cursor: pointer;
      border-radius: 4px;
      transition: background 0.12s, color 0.12s;
    }}
    .toggle button:hover {{ border-color: var(--brand-orange); }}
    .toggle button.active {{
      background: var(--btn-bg-active);
      color: var(--btn-fg-active);
      border-color: var(--brand-orange);
    }}
    .panel {{ display: none; }}
    .panel.active {{ display: block; }}
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
    <svg class="logo" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 120" role="img" aria-label="HotMap">
      <rect width="480" height="120" fill="#000"/>
      <text x="20" y="92" font-family="-apple-system, Helvetica, Arial, sans-serif" font-weight="900" font-size="92" fill="#fff" letter-spacing="-2">HOT</text>
      <rect x="245" y="20" width="220" height="80" rx="16" fill="#ff9000"/>
      <text x="262" y="84" font-family="-apple-system, Helvetica, Arial, sans-serif" font-weight="900" font-size="76" fill="#000" letter-spacing="-2">MAP</text>
    </svg>
    <p>Top-50 Pornhub performers by cumulative video views. Tile size = total views. Color = % growth over the selected window. Hover for details.</p>
  </header>

  <div class="toggle" role="tablist">
    <button type="button" class="active" data-window="1">1d</button>
    <button type="button" data-window="7">7d</button>
    <button type="button" data-window="30">30d</button>
  </div>

  <main>
    <div id="tm-1d" class="panel active">{plot_1d}</div>
    <div id="tm-7d" class="panel">{plot_7d}</div>
    <div id="tm-30d" class="panel">{plot_30d}</div>
  </main>

  <footer>
    <p class="stats">Updated {last_updated} UTC · {n_days} days of history · {n_performers} performers tracked · <a href="https://github.com/ansvier/ph-heatmap">source on GitHub</a> · <a href="data.json">raw data (JSON)</a></p>
    <p class="disclaimer">HotMap is an independent project. Data is collected from publicly visible Pornhub profile pages; no video content is hosted here.</p>
  </footer>

  <script>
    (function () {{
      var buttons = document.querySelectorAll('.toggle button');
      var panels = {{
        '1': document.getElementById('tm-1d'),
        '7': document.getElementById('tm-7d'),
        '30': document.getElementById('tm-30d'),
      }};
      buttons.forEach(function (btn) {{
        btn.addEventListener('click', function () {{
          var w = btn.getAttribute('data-window');
          buttons.forEach(function (b) {{ b.classList.toggle('active', b === btn); }});
          Object.keys(panels).forEach(function (k) {{
            panels[k].classList.toggle('active', k === w);
          }});
          window.dispatchEvent(new Event('resize'));
        }});
      }});
    }})();
  </script>
</body>
</html>
"""


def compute_window_growth(snapshots: pd.DataFrame, window_days: int) -> pd.DataFrame:
    """Return a per-slug snapshot with % growth over a N-day window.

    Output columns: `name`, `total_views` (today), `prev_views` (N days ago,
    or NaN if no row exists for that date+slug), `growth_pct` (NaN if no baseline).
    Index: `slug`. Only slugs present in the latest snapshot are included.
    """
    if snapshots.empty:
        return pd.DataFrame(columns=["name", "total_views", "prev_views", "growth_pct"])

    snapshots = snapshots.copy()
    snapshots["snapshot_date"] = pd.to_datetime(snapshots["snapshot_date"])

    latest_date = snapshots["snapshot_date"].max()
    baseline_date = latest_date - pd.Timedelta(days=window_days)

    today = snapshots[snapshots["snapshot_date"] == latest_date].set_index("slug")
    baseline = (
        snapshots[snapshots["snapshot_date"] == baseline_date]
        .set_index("slug")["total_views"]
        .rename("prev_views")
    )

    out = today[["name", "total_views"]].join(baseline, how="left")
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
    """Build one Plotly Treemap figure for a single window."""
    rows = window.reset_index().copy()
    rows["views_label"] = rows["total_views"].apply(_format_views)
    rows["pct_label"] = rows["growth_pct"].apply(
        lambda v: "n/a" if pd.isna(v) else f"{v:+.2f}%"
    )
    rows["tile_text"] = (
        rows["name"] + "<br>" + rows["views_label"] + "<br>" + rows["pct_label"]
    )

    finite = rows["growth_pct"].dropna()
    cmax = max(1.0, float(finite.abs().max()) if len(finite) else 1.0)

    figure = go.Figure(
        go.Treemap(
            labels=rows["tile_text"],
            parents=[""] * len(rows),
            values=rows["total_views"],
            marker=dict(
                colors=rows["growth_pct"],
                colorscale="RdYlGn",
                cmid=0,
                cmin=-cmax,
                cmax=cmax,
                showscale=True,
                colorbar=dict(
                    title=f"% growth ({window_days}d)",
                    tickformat="+.2f",
                ),
            ),
            customdata=rows[["name", "total_views", "growth_pct"]].values,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Total views: %{customdata[1]:,}<br>"
                "Growth (" + str(window_days) + "d): %{customdata[2]:+.3f}%"
                "<extra></extra>"
            ),
            textposition="middle center",
            textfont=dict(size=14, color="white"),
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


def render_treemap_page(snapshots: pd.DataFrame, output_path: Path | str) -> None:
    """Render the HotMap treemap page (3 windows + toggle) to `output_path`."""
    if snapshots.empty:
        raise ValueError("No snapshots to render")

    def _plot_div(window_days: int) -> str:
        window = compute_window_growth(snapshots, window_days=window_days)
        figure = _build_treemap_figure(window, window_days=window_days)
        return figure.to_html(include_plotlyjs="cdn", full_html=False)

    plot_1d = _plot_div(1)
    plot_7d = _plot_div(7)
    plot_30d = _plot_div(30)

    snapshots = snapshots.copy()
    snapshots["snapshot_date"] = pd.to_datetime(snapshots["snapshot_date"])
    n_days = snapshots["snapshot_date"].nunique()
    latest_date = snapshots["snapshot_date"].max()
    n_performers = snapshots[snapshots["snapshot_date"] == latest_date]["slug"].nunique()
    last_updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    page = _PAGE_TEMPLATE.format(
        plot_1d=plot_1d,
        plot_7d=plot_7d,
        plot_30d=plot_30d,
        last_updated=last_updated,
        n_days=n_days,
        n_performers=n_performers,
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
    out[["snapshot_date", "slug", "name", "total_views", "rank"]].to_json(
        output_path, orient="records"
    )
