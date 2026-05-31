import json
import re
from datetime import date

import pandas as pd
import pytest

from heatmap import (
    _render_seo_head,
    render_performer_page,
    render_stats_page,
    render_treemap_page,
    write_sitemap_and_robots,
)


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


def _extract_jsonld_blocks(html: str) -> list[dict]:
    """Parse all <script type="application/ld+json"> blocks from rendered HTML."""
    pattern = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\']>(.*?)</script>',
        re.DOTALL,
    )
    out = []
    for raw in pattern.findall(html):
        out.append(json.loads(raw.strip()))
    return out


def test_render_seo_head_home_emits_all_required_tags():
    """Home page gets the full SEO/social/JSON-LD block."""
    head = _render_seo_head(
        page_type="home",
        title="HotMap — who's growing fastest on Pornhub",
        description="Live heatmap of view growth across the top-500 performers.",
        canonical_url="https://hotmap.cam/",
    )

    # Core meta. Apostrophe may render as literal, &#39;, or &#x27; — all valid HTML.
    assert ("<title>HotMap — who&#39;s growing fastest on Pornhub</title>" in head
            or "<title>HotMap — who&#x27;s growing fastest on Pornhub</title>" in head
            or "<title>HotMap — who's growing fastest on Pornhub</title>" in head)
    assert 'name="description"' in head
    assert 'rel="canonical"' in head and 'href="https://hotmap.cam/"' in head
    assert 'name="robots"' in head and 'index, follow' in head

    # OG quintet
    assert 'property="og:type" content="website"' in head
    assert 'property="og:title"' in head
    assert 'property="og:description"' in head
    assert 'property="og:url" content="https://hotmap.cam/"' in head
    assert 'property="og:image" content="https://hotmap.cam/og.png"' in head, \
        "home should fall back to /og.png when no og_image_url provided"

    # Twitter triple
    assert 'name="twitter:card" content="summary_large_image"' in head
    assert 'name="twitter:title"' in head
    assert 'name="twitter:image" content="https://hotmap.cam/og.png"' in head

    # JSON-LD: WebSite always, plus no extras for bare home call
    blocks = _extract_jsonld_blocks(head)
    types = {b.get("@type") for b in blocks}
    assert "WebSite" in types, f"expected WebSite JSON-LD; got types={types}"


def test_render_seo_head_uses_explicit_og_image_when_given():
    """When og_image_url is explicit (e.g. an avatar), helper uses it."""
    head = _render_seo_head(
        page_type="performer",
        title="Lana Rhoades — HotMap",
        description="Lana Rhoades stats.",
        canonical_url="https://hotmap.cam/p/lana-rhoades",
        og_image_url="https://hotmap.cam/avatars/lana-rhoades.jpg",
    )
    assert 'property="og:image" content="https://hotmap.cam/avatars/lana-rhoades.jpg"' in head
    assert 'name="twitter:image" content="https://hotmap.cam/avatars/lana-rhoades.jpg"' in head
    assert 'property="og:image" content="https://hotmap.cam/og.png"' not in head


def test_render_seo_head_og_type_per_page_type():
    """og:type matches the page_type matrix in the spec."""
    expected = {
        "home": "website",
        "mode": "website",
        "stats": "article",
        "charts": "website",
        "performer": "profile",
    }
    for page_type, og_type in expected.items():
        head = _render_seo_head(
            page_type=page_type,
            title="T",
            description="D",
            canonical_url="https://hotmap.cam/x",
        )
        assert f'property="og:type" content="{og_type}"' in head, \
            f"page_type={page_type}: expected og:type={og_type}"


def test_render_seo_head_emits_breadcrumbs_when_given():
    """BreadcrumbList JSON-LD is emitted when breadcrumbs param is non-empty."""
    head = _render_seo_head(
        page_type="performer",
        title="Lana Rhoades — HotMap",
        description="Lana Rhoades stats.",
        canonical_url="https://hotmap.cam/p/lana-rhoades",
        breadcrumbs=[
            ("HotMap", "https://hotmap.cam/"),
            ("Charts", "https://hotmap.cam/charts/"),
            ("Lana Rhoades", "https://hotmap.cam/p/lana-rhoades"),
        ],
    )
    blocks = _extract_jsonld_blocks(head)
    bc = next((b for b in blocks if b.get("@type") == "BreadcrumbList"), None)
    assert bc is not None, "expected BreadcrumbList JSON-LD"
    items = bc["itemListElement"]
    assert len(items) == 3
    assert items[0]["position"] == 1
    assert items[0]["name"] == "HotMap"
    assert items[0]["item"] == "https://hotmap.cam/"
    assert items[2]["name"] == "Lana Rhoades"


def test_render_seo_head_emits_extra_jsonld():
    """extra_jsonld list is appended verbatim as additional <script> blocks."""
    person_ld = {"@context": "https://schema.org", "@type": "Person", "name": "Lana Rhoades"}
    head = _render_seo_head(
        page_type="performer",
        title="Lana Rhoades — HotMap",
        description="…",
        canonical_url="https://hotmap.cam/p/lana-rhoades",
        extra_jsonld=[person_ld],
    )
    blocks = _extract_jsonld_blocks(head)
    types = {b.get("@type") for b in blocks}
    assert "WebSite" in types  # always
    assert "Person" in types   # from extra


def test_render_seo_head_jsonld_escapes_safely():
    """Strings inside JSON-LD must survive json.loads, including apostrophes."""
    head = _render_seo_head(
        page_type="home",
        title="HotMap — who's growing fastest",
        description="Tile size = % growth; color = rank.",
        canonical_url="https://hotmap.cam/",
    )
    # Must not throw
    blocks = _extract_jsonld_blocks(head)
    assert all(isinstance(b, dict) for b in blocks)


def test_render_seo_head_always_emits_website_jsonld():
    """WebSite block is an invariant — every page type, every input shape."""
    for pt in ("home", "mode", "stats", "charts", "performer"):
        head = _render_seo_head(
            page_type=pt,
            title="T",
            description="D",
            canonical_url="https://hotmap.cam/x",
        )
        blocks = _extract_jsonld_blocks(head)
        assert any(b.get("@type") == "WebSite" for b in blocks), \
            f"WebSite JSON-LD missing for page_type={pt}"


def test_render_treemap_page_emits_full_seo_block(tmp_path):
    """Home page output contains the full SEO/social/JSON-LD set."""
    df = _snapshot_rows()
    out = tmp_path / "out.html"
    render_treemap_page(df, out, default_mode="rising", canonical_path="/", seo_key="home")
    content = out.read_text()

    # Canonical now uses the trailing-slash form (already does for home).
    assert 'rel="canonical" href="https://hotmap.cam/"' in content
    # OG image must default to /og.png
    assert 'property="og:image" content="https://hotmap.cam/og.png"' in content
    # Twitter image must match
    assert 'name="twitter:image" content="https://hotmap.cam/og.png"' in content
    # og:type=website on home
    assert 'property="og:type" content="website"' in content
    # Robots meta
    assert 'name="robots" content="index, follow' in content

    blocks = _extract_jsonld_blocks(content)
    types = {b.get("@type") for b in blocks}
    assert "WebSite" in types and "Dataset" in types, f"got types={types}"


def test_render_treemap_page_mode_landing_has_breadcrumbs_and_trailing_slash(tmp_path):
    """Mode landings (/rising/, /gems/, /celebs/) emit BreadcrumbList JSON-LD
    and canonical URLs include the trailing slash that CF Pages serves."""
    df = _snapshot_rows()
    out = tmp_path / "rising.html"
    render_treemap_page(df, out, default_mode="rising", canonical_path="/rising/", seo_key="rising")
    content = out.read_text()

    assert 'rel="canonical" href="https://hotmap.cam/rising/"' in content
    blocks = _extract_jsonld_blocks(content)
    types = {b.get("@type") for b in blocks}
    assert "BreadcrumbList" in types, f"got types={types}"

    # The breadcrumb should reflect the navigation: HotMap -> Rising Stars
    bc = next(b for b in blocks if b.get("@type") == "BreadcrumbList")
    names = [item["name"] for item in bc["itemListElement"]]
    assert names == ["HotMap", "Rising Stars"], f"got names={names}"


def test_render_seo_head_neutralizes_script_close_in_jsonld():
    """Strings inside JSON-LD that contain </script> must not break out of
    the surrounding <script> block. Standard mitigation: serialize </ as <\\/.
    """
    head = _render_seo_head(
        page_type="performer",
        title="Safe title",
        description="Safe desc",
        canonical_url="https://hotmap.cam/p/x",
        extra_jsonld=[{
            "@context": "https://schema.org",
            "@type": "Person",
            "name": "Evil </script><script>alert(1)</script>",
        }],
    )
    # The literal </script> from the payload must not appear; only the two
    # legitimate closing tags (one per emitted script block: WebSite + Person)
    # plus zero extras from the BreadcrumbList (we didn't pass breadcrumbs).
    assert head.count("</script>") == 2, \
        f"expected exactly 2 </script> (WebSite + Person); got {head.count('</script>')}"
    # The escaped form must be present somewhere in the head (showing the
    # payload was neutralized rather than dropped).
    assert "<\\/script>" in head, "escaped </script> not present — payload may have been dropped"
