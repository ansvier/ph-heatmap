from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go


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
        title=f"Pornhub Top-50 — Daily View Growth (latest: {latest_date.date()})",
        xaxis_title="Date",
        yaxis_title="Pornstar",
        yaxis=dict(autorange="reversed"),
        height=max(400, 18 * len(growth.index) + 200),
    )

    figure.write_html(str(output_path), include_plotlyjs="cdn", full_html=True)


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
