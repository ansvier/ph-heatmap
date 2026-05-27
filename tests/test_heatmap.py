from datetime import date

import numpy as np
import pandas as pd
import pytest

from heatmap import compute_growth_matrix, render_heatmap


def _snapshot_rows():
    """Three days, three slugs with partial coverage."""
    return pd.DataFrame([
        # day 1
        {"snapshot_date": pd.Timestamp(date(2026, 5, 25)), "slug": "alice", "name": "Alice", "total_views": 1000, "rank": 1},
        {"snapshot_date": pd.Timestamp(date(2026, 5, 25)), "slug": "bob",   "name": "Bob",   "total_views":  500, "rank": 2},
        # day 2 — alice grows 10%, bob grows 20%, carol new (no delta)
        {"snapshot_date": pd.Timestamp(date(2026, 5, 26)), "slug": "alice", "name": "Alice", "total_views": 1100, "rank": 1},
        {"snapshot_date": pd.Timestamp(date(2026, 5, 26)), "slug": "bob",   "name": "Bob",   "total_views":  600, "rank": 2},
        {"snapshot_date": pd.Timestamp(date(2026, 5, 26)), "slug": "carol", "name": "Carol", "total_views":  200, "rank": 3},
        # day 3 — alice grows another ~9.09%, bob disappears, carol +50%
        {"snapshot_date": pd.Timestamp(date(2026, 5, 27)), "slug": "alice", "name": "Alice", "total_views": 1200, "rank": 1},
        {"snapshot_date": pd.Timestamp(date(2026, 5, 27)), "slug": "carol", "name": "Carol", "total_views":  300, "rank": 2},
    ])


def test_growth_matrix_shape_and_index():
    matrix = compute_growth_matrix(_snapshot_rows())
    assert set(matrix.index) == {"alice", "bob", "carol"}
    assert list(matrix.columns) == [
        pd.Timestamp(date(2026, 5, 25)),
        pd.Timestamp(date(2026, 5, 26)),
        pd.Timestamp(date(2026, 5, 27)),
    ]


def test_growth_matrix_first_day_is_nan():
    matrix = compute_growth_matrix(_snapshot_rows())
    first_col = matrix[pd.Timestamp(date(2026, 5, 25))]
    assert first_col.isna().all()


def test_growth_matrix_values():
    matrix = compute_growth_matrix(_snapshot_rows())
    day2 = pd.Timestamp(date(2026, 5, 26))
    assert matrix.loc["alice", day2] == pytest.approx(10.0)
    assert matrix.loc["bob",   day2] == pytest.approx(20.0)
    # Carol appeared on day 2 with no day-1 baseline.
    assert np.isnan(matrix.loc["carol", day2])


def test_growth_matrix_missing_slug_yields_nan():
    matrix = compute_growth_matrix(_snapshot_rows())
    day3 = pd.Timestamp(date(2026, 5, 27))
    # Bob disappeared on day 3.
    assert np.isnan(matrix.loc["bob", day3])


def test_render_heatmap_writes_html(tmp_path):
    df = _snapshot_rows()
    out = tmp_path / "out.html"
    render_heatmap(df, out)
    assert out.exists()
    content = out.read_text()
    assert "<html" in content.lower()
    assert "plotly" in content.lower()
    assert "Alice" in content
    assert "Carol" in content


import json

from heatmap import dump_json


def test_dump_json_writes_records(tmp_path):
    df = _snapshot_rows()
    out = tmp_path / "data.json"
    dump_json(df, out)

    assert out.exists()
    records = json.loads(out.read_text())
    assert isinstance(records, list)
    assert len(records) == len(df)

    first = records[0]
    assert set(first.keys()) == {"snapshot_date", "slug", "name", "total_views", "rank"}

    assert all(isinstance(r["snapshot_date"], str) for r in records)
    assert all(len(r["snapshot_date"]) == 10 for r in records)


def test_dump_json_is_round_trippable(tmp_path):
    df = _snapshot_rows()
    out = tmp_path / "data.json"
    dump_json(df, out)

    records = json.loads(out.read_text())
    assert sum(r["total_views"] for r in records) == int(df["total_views"].sum())
