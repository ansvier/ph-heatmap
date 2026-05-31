from datetime import date

import pandas as pd
import pytest

from heatmap import render_performer_page, render_stats_page, render_treemap_page, write_sitemap_and_robots


def _snapshot_rows():
    """Three days, three slugs with partial coverage. All female by default.

    View counts are scaled to >=1M because _build_treemap_figure drops rows
    whose prev_views fall under that threshold (the % metric noise filter).
    """
    return pd.DataFrame([
        {"snapshot_date": pd.Timestamp(date(2026, 5, 25)), "slug": "alice", "name": "Alice", "total_views": 1_000_000_000, "rank": 1, "gender": "female"},
        {"snapshot_date": pd.Timestamp(date(2026, 5, 25)), "slug": "bob",   "name": "Bob",   "total_views":   500_000_000, "rank": 2, "gender": "male"},
        {"snapshot_date": pd.Timestamp(date(2026, 5, 26)), "slug": "alice", "name": "Alice", "total_views": 1_100_000_000, "rank": 1, "gender": "female"},
        {"snapshot_date": pd.Timestamp(date(2026, 5, 26)), "slug": "bob",   "name": "Bob",   "total_views":   600_000_000, "rank": 2, "gender": "male"},
        {"snapshot_date": pd.Timestamp(date(2026, 5, 26)), "slug": "carol", "name": "Carol", "total_views":   200_000_000, "rank": 3, "gender": "female"},
        {"snapshot_date": pd.Timestamp(date(2026, 5, 27)), "slug": "alice", "name": "Alice", "total_views": 1_200_000_000, "rank": 1, "gender": "female"},
        {"snapshot_date": pd.Timestamp(date(2026, 5, 27)), "slug": "carol", "name": "Carol", "total_views":   300_000_000, "rank": 2, "gender": "female"},
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

    # 27 panels: 3 modes × 3 gender filters × 3 windows.
    for mode in ("rising", "gems", "celebs"):
        for gender in ("all", "female", "male"):
            for window in (1, 7, 30):
                assert f'id="panel-{mode}-{gender}-{window}"' in content, \
                    f"missing panel-{mode}-{gender}-{window}"

    # All three toggle dimensions present.
    assert 'data-mode="rising"' in content
    assert 'data-mode="gems"' in content
    assert 'data-mode="celebs"' in content
    assert 'data-window="1"' in content
    assert 'data-window="7"' in content
    assert 'data-window="30"' in content
    assert 'data-gender="all"' in content
    assert 'data-gender="female"' in content
    assert 'data-gender="male"' in content

    # Slug data is embedded so the click handler can build profile URLs.
    assert "alice" in content
    assert "bob" in content

    # Display names appear too.
    assert "Alice" in content
    assert "Bob" in content


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
    assert set(first.keys()) == {"snapshot_date", "slug", "name", "total_views", "rank", "gender"}

    assert all(isinstance(r["snapshot_date"], str) for r in records)
    assert all(len(r["snapshot_date"]) == 10 for r in records)


def test_dump_json_is_round_trippable(tmp_path):
    df = _snapshot_rows()
    out = tmp_path / "data.json"
    dump_json(df, out)

    records = json.loads(out.read_text())
    assert sum(r["total_views"] for r in records) == int(df["total_views"].sum())


def test_render_performer_page_writes_html(tmp_path):
    df = _snapshot_rows()
    out = tmp_path / "alice.html"
    render_performer_page(df, slug="alice", output_path=out)
    assert out.exists()
    content = out.read_text()

    # Performer-identifying content
    assert "Alice" in content
    assert "alice" in content
    assert "1,200" in content  # latest total_views formatted with commas

    # SEO basics
    assert '<link rel="canonical"' in content
    assert "https://hotmap.cam/p/alice" in content
    assert '"@type": "Person"' in content  # Schema.org JSON-LD

    # Plotly sparkline embedded
    assert "plotly" in content.lower()

    # Link back to hub
    assert 'href="/"' in content or 'href="https://hotmap.cam"' in content


def test_render_performer_page_unknown_slug_raises(tmp_path):
    df = _snapshot_rows()
    with pytest.raises(ValueError, match="No snapshots for slug"):
        render_performer_page(df, slug="nobody", output_path=tmp_path / "x.html")


def test_render_stats_page_writes_html(tmp_path):
    df = _snapshot_rows()
    out = tmp_path / "stats.html"
    render_stats_page(df, output_path=out)
    assert out.exists()
    content = out.read_text()

    # Branding + SEO
    assert "HotMap" in content
    assert "<svg" in content
    assert '<link rel="canonical"' in content
    assert "https://hotmap.cam/stats" in content

    # Hero numbers — at minimum the performer count and a total-views number
    assert "3" in content  # 3 unique slugs in fixture (alice/bob/carol)
    # Biggest mover should reference a name from the fixture
    assert "Alice" in content or "Carol" in content or "Bob" in content


def test_render_stats_page_empty_raises(tmp_path):
    with pytest.raises(ValueError, match="No snapshots"):
        render_stats_page(
            pd.DataFrame(columns=["snapshot_date", "slug", "name", "total_views", "rank", "gender"]),
            tmp_path / "stats.html",
        )


def test_write_sitemap_and_robots(tmp_path):
    df = _snapshot_rows()
    write_sitemap_and_robots(df, public_dir=tmp_path)

    sitemap = (tmp_path / "sitemap.xml").read_text()
    robots = (tmp_path / "robots.txt").read_text()

    # Sitemap lists home + each performer page
    assert "<loc>https://hotmap.cam/</loc>" in sitemap
    assert "<loc>https://hotmap.cam/p/alice</loc>" in sitemap
    assert "<loc>https://hotmap.cam/p/carol</loc>" in sitemap

    # robots.txt allows all and points to sitemap
    assert "User-agent: *" in robots
    assert "Allow: /" in robots
    assert "Sitemap: https://hotmap.cam/sitemap.xml" in robots


from heatmap import compute_window_growth


def test_window_growth_1d_matches_pct_change():
    df = _snapshot_rows()
    result = compute_window_growth(df, window_days=1)
    alice = result.loc["alice"]
    assert alice["total_views"] == 1_200_000_000
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
    assert result.loc["alice", "total_views"] == 1_200_000_000


def test_window_growth_carries_display_name():
    df = _snapshot_rows()
    result = compute_window_growth(df, window_days=1)
    assert result.loc["alice", "name"] == "Alice"


from heatmap import _build_treemap_figure


def _window_df(rows):
    """Build the per-slug DataFrame that _build_treemap_figure consumes.

    Matches compute_window_growth's output: index=slug, cols=name, total_views,
    prev_views, growth_pct, gender.
    """
    df = pd.DataFrame(rows).set_index("slug")
    df["growth_pct"] = (df["total_views"] - df["prev_views"]) / df["prev_views"] * 100
    return df


def test_build_treemap_figure_size_is_percent_growth():
    """Tile size encodes % growth, not absolute views gained.

    'big' has a larger absolute delta (+5M) but smaller % (+0.25%).
    'rising' has a smaller absolute delta (+2M) but larger % (+4%).
    Under the new metric, 'rising' must get the larger tile value.
    """
    window = _window_df([
        {"slug": "big",    "name": "Big",    "total_views": 2_005_000_000, "prev_views": 2_000_000_000, "gender": "female"},
        {"slug": "rising", "name": "Rising", "total_views":    52_000_000, "prev_views":    50_000_000, "gender": "female"},
    ])

    fig = _build_treemap_figure(window, window_days=1)

    values_by_id = dict(zip(fig.data[0].ids, fig.data[0].values))
    assert values_by_id["rising"] > values_by_id["big"], (
        f"Expected rising tile > big tile under % metric; "
        f"got rising={values_by_id['rising']}, big={values_by_id['big']}"
    )


def test_build_treemap_figure_filters_below_1m_baseline():
    """Performers with prev_views < 1M are excluded from the treemap.

    'tiny' would have +20% growth but a 500k baseline — the filter must drop
    it so micro-account noise doesn't dominate the visual.
    """
    window = _window_df([
        {"slug": "tiny",   "name": "Tiny",   "total_views":   600_000, "prev_views":   500_000, "gender": "female"},
        {"slug": "normal", "name": "Normal", "total_views": 1_500_000, "prev_views": 1_400_000, "gender": "female"},
        {"slug": "big",    "name": "Big",    "total_views":   105_000_000, "prev_views":   100_000_000, "gender": "female"},
    ])

    fig = _build_treemap_figure(window, window_days=1)

    ids = list(fig.data[0].ids)
    assert "tiny" not in ids, f"Expected 'tiny' filtered out (prev_views=500k < 1M); got ids={ids}"
    assert "normal" in ids, f"Expected 'normal' kept (prev_views=1.4M); got ids={ids}"
    assert "big" in ids, f"Expected 'big' kept; got ids={ids}"
