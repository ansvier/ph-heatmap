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
  <title>HotMap — Daily Pornhub view-growth heatmap</title>
  <meta name="description" content="Day-over-day percentage growth of cumulative video views for the top-50 Most Viewed Pornstars on Pornhub. Updated daily.">
  <style>
    :root {{
      --brand-orange: #ff9000;
      --bg: #ffffff;
      --fg: #1a1a1a;
      --muted: #666;
      --rule: #eee;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
      max-width: 1100px;
      margin: 0 auto;
      padding: 24px 16px 48px;
      color: var(--fg);
      background: var(--bg);
      line-height: 1.5;
    }}
    header {{ margin-bottom: 24px; }}
    .logo {{
      display: block;
      max-width: 280px;
      width: 100%;
      height: auto;
      margin-bottom: 12px;
    }}
    header p {{ color: var(--muted); margin: 0; }}
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
    <p>Daily view-growth heatmap of Pornhub's top-50 performers. Brighter cells = faster day-over-day growth in cumulative video views.</p>
  </header>

  <main>
    {plot_div}
  </main>

  <footer>
    <p class="stats">Updated {last_updated} UTC · {n_days} days of history · {n_performers} performers tracked · <a href="https://github.com/ansvier/ph-heatmap">source on GitHub</a> · <a href="data.json">raw data (JSON)</a></p>
    <p class="disclaimer">HotMap is an independent project. Data is collected from publicly visible Pornhub profile pages; no video content is hosted here.</p>
  </footer>
</body>
</html>
"""


def compute_growth_matrix(snapshots: pd.DataFrame) -> pd.DataFrame:
    """Return a (slug x date) matrix of day-over-day % growth in total_views.

    Cells where either the current or previous day's value is missing become NaN.
    The first column is always NaN (no prior day to diff against).
    """
    pivot = snapshots.pivot_table(
        index="slug",
        columns="snapshot_date",
        values="total_views",
        aggfunc="first",
    )
    pivot = pivot.sort_index(axis=1)
    pct = pivot.pct_change(axis=1) * 100
    return pct


def render_heatmap(snapshots: pd.DataFrame, output_path: Path | str) -> None:
    """Render the growth heatmap to a standalone HTML file."""
    if snapshots.empty:
        raise ValueError("No snapshots to render")

    growth = compute_growth_matrix(snapshots)

    latest_date = snapshots["snapshot_date"].max()
    latest = (
        snapshots[snapshots["snapshot_date"] == latest_date]
        .set_index("slug")["total_views"]
    )
    ordered_slugs = (
        latest.reindex(growth.index)
        .sort_values(ascending=False, na_position="last")
        .index.tolist()
    )
    growth = growth.loc[ordered_slugs]

    latest_names = (
        snapshots.sort_values("snapshot_date")
        .drop_duplicates("slug", keep="last")
        .set_index("slug")["name"]
    )
    y_labels = [latest_names.get(slug, slug) for slug in growth.index]

    views_pivot = (
        snapshots.pivot_table(index="slug", columns="snapshot_date", values="total_views", aggfunc="first")
        .reindex(index=growth.index, columns=growth.columns)
    )

    figure = go.Figure(
        data=go.Heatmap(
            z=growth.values,
            x=[d.strftime("%Y-%m-%d") for d in growth.columns],
            y=y_labels,
            colorscale="YlOrRd",
            zmin=0,
            colorbar=dict(title="% growth"),
            customdata=views_pivot.values,
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Date: %{x}<br>"
                "Total views: %{customdata:,}<br>"
                "Growth: %{z:.2f}%<extra></extra>"
            ),
        )
    )
    figure.update_layout(
        title=None,
        xaxis_title="Date",
        yaxis_title=None,
        yaxis=dict(autorange="reversed"),
        margin=dict(l=140, r=20, t=20, b=40),
        height=max(400, 18 * len(growth.index) + 200),
    )

    plot_div = figure.to_html(include_plotlyjs="cdn", full_html=False)
    last_updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    page = _PAGE_TEMPLATE.format(
        plot_div=plot_div,
        last_updated=last_updated,
        n_days=growth.shape[1],
        n_performers=growth.shape[0],
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
