from __future__ import annotations

import pandas as pd


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
