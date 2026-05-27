from datetime import date

import pandas as pd
import pytest

from heatmap import render_treemap_page


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


def test_render_treemap_page_writes_html(tmp_path):
    df = _snapshot_rows()
    out = tmp_path / "out.html"
    render_treemap_page(df, out)
    assert out.exists()
    content = out.read_text()

    # Plotly + HotMap branding.
    assert "<html" in content.lower()
    assert "plotly" in content.lower()
    assert "HotMap" in content
    assert "<svg" in content
    assert "<footer" in content.lower()

    # Three treemap containers (one per window) and the toggle buttons.
    assert 'id="tm-1d"' in content
    assert 'id="tm-7d"' in content
    assert 'id="tm-30d"' in content
    assert 'data-window="1"' in content
    assert 'data-window="7"' in content
    assert 'data-window="30"' in content

    # Display names appear in the treemap data.
    assert "Alice" in content
    assert "Carol" in content


def test_render_treemap_page_raises_on_empty(tmp_path):
    with pytest.raises(ValueError, match="No snapshots"):
        render_treemap_page(
            pd.DataFrame(columns=["snapshot_date", "slug", "name", "total_views", "rank"]),
            tmp_path / "out.html",
        )


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


from heatmap import compute_window_growth


def test_window_growth_1d_matches_pct_change():
    df = _snapshot_rows()
    result = compute_window_growth(df, window_days=1)
    alice = result.loc["alice"]
    assert alice["total_views"] == 1200
    assert alice["growth_pct"] == pytest.approx(100 * (1200 - 1100) / 1100)
    carol = result.loc["carol"]
    assert carol["growth_pct"] == pytest.approx(50.0)


def test_window_growth_only_includes_today_slugs():
    df = _snapshot_rows()
    result = compute_window_growth(df, window_days=1)
    assert "bob" not in result.index
    assert set(result.index) == {"alice", "carol"}


def test_window_growth_nan_when_no_baseline():
    df = _snapshot_rows()
    result = compute_window_growth(df, window_days=30)
    assert result["growth_pct"].isna().all()
    assert result.loc["alice", "total_views"] == 1200


def test_window_growth_carries_display_name():
    df = _snapshot_rows()
    result = compute_window_growth(df, window_days=1)
    assert result.loc["alice", "name"] == "Alice"
