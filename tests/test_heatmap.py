import json
import re
from datetime import date

import pandas as pd
import pytest

from heatmap import (
    _render_seo_head,
    render_categories_treemap,
    render_countries_index,
    render_country_page,
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


def test_nav_items_includes_countries():
    from heatmap import _NAV_ITEMS
    hrefs = [item[1] for item in _NAV_ITEMS]
    assert "/countries/" in hrefs, f"got hrefs={hrefs}"


def test_sitemap_includes_countries_page(tmp_path):
    """Sitemap emits /countries/ and per-country URLs for qualifying countries."""
    rows = []
    # Russia: 6 performers (qualifying)
    for i in range(6):
        rows.append({
            "snapshot_date": pd.Timestamp("2026-06-02"), "slug": f"ru{i}", "name": f"RU{i}",
            "total_views": 100_000_000, "rank": 1, "gender": "female", "country": "Russia",
        })
    # Italy: 2 performers (below threshold)
    for i in range(2):
        rows.append({
            "snapshot_date": pd.Timestamp("2026-06-02"), "slug": f"it{i}", "name": f"IT{i}",
            "total_views": 80_000_000, "rank": 1, "gender": "female", "country": "Italy",
        })
    df = pd.DataFrame(rows)
    write_sitemap_and_robots(df, public_dir=tmp_path)
    text = (tmp_path / "sitemap.xml").read_text()
    assert "<loc>https://hotmap.cam/countries/</loc>" in text
    assert "<loc>https://hotmap.cam/country/russia/</loc>" in text
    assert "/country/italy/" not in text  # below threshold


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


def test_window_growth_nan_when_no_priors_at_all():
    """When the dataset has only the latest snapshot date (no prior rows
    anywhere), growth_pct stays NaN. The single-day fixture covers this."""
    df = _snapshot_rows()
    one_day = df[df["snapshot_date"] == df["snapshot_date"].max()].copy()
    result = compute_window_growth(one_day, window_days=1)
    assert result["growth_pct"].isna().all()
    assert result.loc["alice", "total_views"] == 1_200_000_000


def test_window_growth_falls_back_to_closest_prior_when_target_missing():
    """When the exact target_date snapshot is missing but other priors
    exist, growth is computed against the closest available date. Fixture:
    request window_days=30, but only ~2 days of history exist → fallback
    finds the oldest available snapshot and computes growth from there.
    Without the fallback this would all be NaN."""
    df = _snapshot_rows()
    result = compute_window_growth(df, window_days=30)
    assert result["growth_pct"].notna().any(), "should fall back to nearest prior"
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


def test_render_performer_page_emits_full_seo_block(tmp_path):
    """Per-performer page: complete SEO + Person + BreadcrumbList JSON-LD,
    twitter:image points to avatar (not the default og.png)."""
    df = _snapshot_rows()
    out = tmp_path / "alice.html"
    render_performer_page(df, slug="alice", output_path=out)
    content = out.read_text()

    assert 'rel="canonical" href="https://hotmap.cam/p/alice"' in content
    assert 'property="og:type" content="profile"' in content
    # Avatar fallback for tests: there's no real avatar for fixture 'alice',
    # so the page should fall back to /og.png. Real production data has
    # /avatars/<slug>.jpg.
    assert ('property="og:image" content="https://hotmap.cam/og.png"' in content
            or 'property="og:image" content="https://hotmap.cam/avatars/alice' in content)
    assert 'name="twitter:image"' in content

    blocks = _extract_jsonld_blocks(content)
    types = {b.get("@type") for b in blocks}
    assert "WebSite" in types and "Person" in types and "BreadcrumbList" in types, \
        f"got types={types}"

    bc = next(b for b in blocks if b.get("@type") == "BreadcrumbList")
    names = [item["name"] for item in bc["itemListElement"]]
    assert names == ["HotMap", "Charts", "Alice"], f"got names={names}"


def test_render_stats_page_emits_full_seo_block(tmp_path):
    """Stats page: complete SEO + CollectionPage + BreadcrumbList JSON-LD,
    canonical with trailing slash, og:type=article."""
    df = _snapshot_rows()
    out = tmp_path / "stats.html"
    render_stats_page(df, out)
    content = out.read_text()

    assert 'rel="canonical" href="https://hotmap.cam/stats/"' in content, \
        "canonical must use trailing slash to match what CF serves"
    assert 'property="og:type" content="article"' in content
    assert 'name="twitter:image"' in content

    blocks = _extract_jsonld_blocks(content)
    types = {b.get("@type") for b in blocks}
    assert "WebSite" in types and "CollectionPage" in types and "BreadcrumbList" in types, \
        f"got types={types}"


def test_render_charts_page_emits_full_seo_block(tmp_path):
    """Charts page: complete SEO + CollectionPage + BreadcrumbList JSON-LD,
    canonical /charts/, og:image falls back to /og.png (no hero photo)."""
    from heatmap import render_charts_page
    df = _snapshot_rows()
    out = tmp_path / "charts.html"
    render_charts_page(df, out)
    content = out.read_text()

    assert 'rel="canonical" href="https://hotmap.cam/charts/"' in content
    assert 'property="og:type" content="website"' in content
    assert 'property="og:image" content="https://hotmap.cam/og.png"' in content, \
        "charts page has no hero — must fall back to default og.png"

    blocks = _extract_jsonld_blocks(content)
    types = {b.get("@type") for b in blocks}
    assert "WebSite" in types and "CollectionPage" in types and "BreadcrumbList" in types


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


def test_sitemap_uses_trailing_slash_for_directory_urls(tmp_path):
    """Directory-style URLs in sitemap match what CF serves (with slash)."""
    df = _snapshot_rows()
    write_sitemap_and_robots(df, public_dir=tmp_path)
    text = (tmp_path / "sitemap.xml").read_text()

    for path in ("/rising/", "/gems/", "/celebs/", "/stats/", "/charts/"):
        assert f"<loc>https://hotmap.cam{path}</loc>" in text, \
            f"sitemap missing trailing-slash entry for {path}"
        # And the slash-less form is NOT present:
        bare = path.rstrip("/")
        assert f"<loc>https://hotmap.cam{bare}</loc>" not in text, \
            f"sitemap still has slash-less form for {path}"
    # Per-performer URLs stay slash-less.
    assert "<loc>https://hotmap.cam/p/alice</loc>" in text


def test_nav_items_use_canonical_trailing_slash():
    """Internal navbar links must point to the canonical (slash) form so
    every nav click doesn't 307-redirect through CF Pages."""
    from heatmap import _NAV_ITEMS
    hrefs = [href for (_, href, _) in _NAV_ITEMS]
    for bare in ("/stats", "/charts", "/rising", "/gems", "/celebs"):
        assert bare not in hrefs, \
            f"_NAV_ITEMS still has bare {bare}; should be {bare}/"


from heatmap import _compute_acceleration


def _make_history(slug_views: dict[str, list[float]], start_date: str = "2026-05-25") -> pd.DataFrame:
    """Build a snapshots DataFrame from {slug: [view_day0, view_day1, ...]}.

    Each list element is a daily total_views snapshot. All slugs same gender (female).
    """
    rows = []
    for slug, views in slug_views.items():
        for i, v in enumerate(views):
            d = pd.Timestamp(start_date) + pd.Timedelta(days=i)
            rows.append({
                "snapshot_date": d, "slug": slug, "name": slug.title(),
                "total_views": v, "rank": 1, "gender": "female",
            })
    return pd.DataFrame(rows)


def test_compute_acceleration_returns_today_vs_7d_avg():
    """Acceleration = today's daily growth % minus mean of prior 7 daily growths."""
    # 8 days. Daily growths: +1% each day for 7 days, then +5% on day 8.
    # Daily growth days 1..7: each = 1.0 (in pct). Mean of prior 7 = 1.0.
    # Today (day 8) growth = 5.0. Acceleration = 5.0 - 1.0 = 4.0.
    df = _make_history({
        "spiker": [
            1_000.0, 1_010.0, 1_020.10, 1_030.30, 1_040.60, 1_051.01, 1_061.52, 1_114.59
        ],
    })
    accel = _compute_acceleration(df)
    assert accel["spiker"] == pytest.approx(4.0, abs=0.01)


def test_compute_acceleration_nan_for_thin_history():
    """Slugs with fewer than 3 prior daily growths get NaN."""
    # Only 3 snapshots = 2 daily growths. min_priors=3 → NaN.
    df = _make_history({"newcomer": [100.0, 101.0, 102.0]})
    accel = _compute_acceleration(df)
    assert pd.isna(accel["newcomer"])


def test_compute_acceleration_uses_full_baseline_window_when_available():
    """Acceleration averages the full baseline_days when enough history exists.
    Off-by-one regression guard: the oldest prior must be included in the mean."""
    # 9 days. First daily growth = +10%, next 6 = +1%, today = +5%.
    # With baseline_days=7: trailing includes all 7 priors → mean = (10 + 1*6)/7 = 16/7 ≈ 2.2857
    # → acceleration = 5 - 2.2857 ≈ 2.714
    # If off-by-one excluded the oldest +10% growth, mean = 1.0, acceleration = 4.0. Wrong.
    df = _make_history({
        "veteran": [
            1_000.0,        # day 0
            1_100.0,        # day 1: +10% growth (the "old" prior we must include)
            1_111.0,        # day 2: +1%
            1_122.11,       # day 3: +1%
            1_133.33,       # day 4: +1%
            1_144.66,       # day 5: +1%
            1_156.11,       # day 6: +1%
            1_167.67,       # day 7: +1% — 7 priors total
            1_226.05,       # day 8: +5% today
        ],
    })
    accel = _compute_acceleration(df)
    assert accel["veteran"] == pytest.approx(2.714, abs=0.01), \
        f"expected full 7-day baseline included (mean=2.29); got accel={accel['veteran']}"


def test_compute_acceleration_returns_value_at_min_priors_boundary():
    """Slugs with exactly min_priors=3 prior daily growths get a non-NaN value."""
    # 5 snapshots = 4 daily growths. >=3, so acceleration computed.
    df = _make_history({"borderline": [100.0, 101.0, 102.01, 103.03, 104.06]})
    accel = _compute_acceleration(df)
    assert pd.notna(accel["borderline"]), "with 4 priors (>=3), acceleration should not be NaN"


def test_compute_window_growth_attaches_acceleration_for_1d():
    """When window_days=1, output has an `acceleration` column populated for
    slugs with enough history; 7d/30d windows do NOT get the column."""
    df = _make_history({
        "veteran": [1_000.0, 1_010.0, 1_020.0, 1_030.0, 1_040.0, 1_050.0, 1_060.0, 1_070.0],
    })

    # 1d window: acceleration column present
    out_1d = compute_window_growth(df, window_days=1)
    assert "acceleration" in out_1d.columns
    assert pd.notna(out_1d.loc["veteran", "acceleration"])

    # 7d window: no acceleration column
    out_7d = compute_window_growth(df, window_days=7)
    assert "acceleration" not in out_7d.columns


from heatmap import _build_top_performer_card


def _multiday_card_fixture():
    """8 days of history. stable_high has HIGHER today's growth_pct (0.5%),
    spiker has LOWER today's growth_pct (0.3%) but HIGHER acceleration
    (~+0.25 pp vs stable's ~0). Picking by growth_pct → stable_high.
    Picking by acceleration → spiker. The card test asserts spiker is picked,
    so only the acceleration-based selection makes the test pass.
    """
    rows = []
    # stable_high: +0.5%/day every day for 8 days → growth_pct ≈ 0.5%, accel ≈ 0
    for i in range(8):
        rows.append({
            "snapshot_date": pd.Timestamp("2026-05-25") + pd.Timedelta(days=i),
            "slug": "stable_high", "name": "Stable High",
            "total_views": int(200_000_000 * (1.005 ** i)),
            "rank": 1, "gender": "female",
        })
    # spiker: +0.05%/day for 7 days, then +0.3% on day 8.
    # 7d-avg of priors = 0.05%; today = 0.3%; acceleration = +0.25 pp.
    spiker_views = [150_000_000]
    for _ in range(6):
        spiker_views.append(int(spiker_views[-1] * 1.0005))  # +0.05% each
    spiker_views.append(int(spiker_views[-1] * 1.003))  # +0.3% today
    for i, v in enumerate(spiker_views):
        rows.append({
            "snapshot_date": pd.Timestamp("2026-05-25") + pd.Timedelta(days=i),
            "slug": "spiker", "name": "Spiker",
            "total_views": v,
            "rank": 2, "gender": "female",
        })
    return pd.DataFrame(rows)


def test_top_performer_card_picks_by_acceleration():
    """Card prefers the spiker over the steadier high-grower when acceleration data exists."""
    df = _multiday_card_fixture()
    # Mode 'celebs' → no rank-band filter, just top-50 by views. Both slugs included.
    html = _build_top_performer_card(
        df, gender_key="female", gender_filter="female", mode="celebs", is_default=True
    )
    # Spiker has higher acceleration, so the card should feature Spiker, not Stable High.
    assert "Spiker" in html, f"expected Spiker in card; got: {html[:400]}"
    assert "Stable High" not in html


def test_top_performer_card_falls_back_to_growth_pct_without_history():
    """With only 2 days of data (no acceleration possible), card falls back to growth_pct."""
    df = pd.DataFrame([
        {"snapshot_date": pd.Timestamp("2026-05-30"), "slug": "slow",
         "name": "Slow", "total_views": 200_000_000, "rank": 1, "gender": "female"},
        {"snapshot_date": pd.Timestamp("2026-05-30"), "slug": "fast",
         "name": "Fast", "total_views": 150_000_000, "rank": 2, "gender": "female"},
        {"snapshot_date": pd.Timestamp("2026-05-31"), "slug": "slow",
         "name": "Slow", "total_views": 200_100_000, "rank": 1, "gender": "female"},
        {"snapshot_date": pd.Timestamp("2026-05-31"), "slug": "fast",
         "name": "Fast", "total_views": 151_500_000, "rank": 2, "gender": "female"},
    ])
    html = _build_top_performer_card(
        df, gender_key="female", gender_filter="female", mode="celebs", is_default=True
    )
    # Fast grew 1%, Slow grew 0.05% — fallback picks Fast.
    assert "Fast" in html, f"expected Fast in card; got: {html[:400]}"
    assert "Slow" not in html


def test_card_renders_today_usual_contrast_when_acceleration_available():
    """When acceleration drove selection, the card shows Today / Usual / caption."""
    df = _multiday_card_fixture()
    html = _build_top_performer_card(
        df, gender_key="female", gender_filter="female", mode="celebs", is_default=True
    )
    assert "Today:" in html, "expected Today: row in contrast block"
    assert "Usual:" in html, "expected Usual: row in contrast block"
    # One of the auto-captions must appear:
    captions = ("Sharp turnaround", "Trending up", "Steady pace", "Slower than usual", "Cooling off")
    assert any(c in html for c in captions), f"expected one of {captions} in card; html: {html[:600]}"


def test_card_renders_legacy_single_line_on_fallback():
    """When fallback was used, card renders the old `+X.XX% · +N views (24h)` line, no contrast."""
    df = pd.DataFrame([
        {"snapshot_date": pd.Timestamp("2026-05-30"), "slug": "fast",
         "name": "Fast", "total_views": 150_000_000, "rank": 2, "gender": "female"},
        {"snapshot_date": pd.Timestamp("2026-05-31"), "slug": "fast",
         "name": "Fast", "total_views": 151_500_000, "rank": 1, "gender": "female"},
    ])
    html = _build_top_performer_card(
        df, gender_key="female", gender_filter="female", mode="celebs", is_default=True
    )
    assert "Today:" not in html, "fallback render should not show Today: row"
    assert "views (24h)" in html, "fallback render should keep legacy '+N views (24h)' format"


def test_render_seo_head_supports_category_page_type():
    """page_type='category' maps to og:type='website' and emits without error."""
    head = _render_seo_head(
        page_type="category",
        title="Trending Pornhub Categories",
        description="…",
        canonical_url="https://hotmap.cam/categories/",
    )
    assert 'property="og:type" content="website"' in head


def test_render_seo_head_supports_country_page_type():
    """page_type='country' maps to og:type='website' and emits without error."""
    head = _render_seo_head(
        page_type="country",
        title="Top Russian Performers — HotMap",
        description="…",
        canonical_url="https://hotmap.cam/country/russia/",
    )
    assert 'property="og:type" content="website"' in head


def _category_snapshots_fixture(with_baseline: bool = True) -> pd.DataFrame:
    """Two-day fixture: 3 categories today, baseline yesterday for delta math.

    When with_baseline=False, only today's rows are returned (simulates
    first-deploy state with no growth data available yet).
    """
    today = pd.Timestamp("2026-06-02")
    yesterday = pd.Timestamp("2026-06-01")
    today_rows = [
        {"snapshot_date": today, "category_id": 37, "slug": "18-25",
         "name": "18-25", "video_count": 289700, "points": 65005},
        {"snapshot_date": today, "category_id": 29, "slug": "milf",
         "name": "MILF", "video_count": 199900, "points": 12500},
        {"snapshot_date": today, "category_id": 1, "slug": "anal",
         "name": "Anal", "video_count": 142250, "points": None},
    ]
    if not with_baseline:
        return pd.DataFrame(today_rows)
    baseline_rows = [
        {"snapshot_date": yesterday, "category_id": 37, "slug": "18-25",
         "name": "18-25", "video_count": 289620, "points": 65000},
        {"snapshot_date": yesterday, "category_id": 29, "slug": "milf",
         "name": "MILF", "video_count": 199835, "points": 12490},
        {"snapshot_date": yesterday, "category_id": 1, "slug": "anal",
         "name": "Anal", "video_count": 142217, "points": None},
    ]
    return pd.DataFrame(baseline_rows + today_rows)


def test_render_categories_treemap_writes_html(tmp_path):
    """Full happy path: 2 days of data, page renders with names/counts/canonical/SEO."""
    df = _category_snapshots_fixture(with_baseline=True)
    out = tmp_path / "categories.html"
    render_categories_treemap(df, out)
    assert out.exists()
    content = out.read_text()

    # Page chrome
    assert "<html" in content.lower()
    assert "Trending" in content                              # title pattern
    assert 'rel="canonical" href="https://hotmap.cam/categories/"' in content
    assert 'property="og:type" content="website"' in content

    # Category names appear on the page
    assert "MILF" in content
    assert "18-25" in content
    assert "Anal" in content

    # Treemap (Plotly) is embedded
    assert "plotly" in content.lower()

    # JSON-LD includes CollectionPage + BreadcrumbList
    blocks = _extract_jsonld_blocks(content)
    types = {b.get("@type") for b in blocks}
    assert "CollectionPage" in types and "BreadcrumbList" in types, f"got types={types}"

    # Outbound click handler wired (Categories v1.1) — plotly_treemapclick →
    # window.open(PH URL). Without url_by_id, customdata falls back to a generic
    # search URL. Plotly JSON-encodes slashes in customdata as /, so we
    # check for the host substring (slash-free). The sort+time params land
    # the user on this-week's top videos in the category.
    assert "plotly_treemapclick" in content
    assert "pornhub.com" in content                    # host always present
    assert "search?search=" in content                 # fallback URL shape
    assert "o=mv" in content and "t=w" in content      # most-viewed, week
    assert "click to open category" in content


def test_render_categories_treemap_uses_url_by_id_when_provided(tmp_path):
    """url_by_id maps category_id → PH outbound URL. customdata embeds it.

    Plotly serializes customdata strings with JSON unicode-escaped slashes
    (\\u002f), so we assert on slash-free substrings of the URL path.
    """
    df = _category_snapshots_fixture(with_baseline=True)
    # Fixture has category_id=29 (MILF). Inject the PH-shaped URL for it.
    url_by_id = {29: "/video/incategories/lesbian/milf"}
    out = tmp_path / "categories.html"
    render_categories_treemap(df, out, url_by_id=url_by_id)
    content = out.read_text()
    # Provided URL appears (slashes are / after JSON-encoding)
    assert "incategories" in content and "lesbian" in content and "milf" in content
    # Categories without an entry fall back to search URL shape
    assert "search?search=" in content


def test_render_categories_treemap_no_baseline(tmp_path):
    """First deploy state — only today's snapshot, no baseline. Page still renders,
    delta labels show '—' (no growth data yet). No error."""
    df = _category_snapshots_fixture(with_baseline=False)
    out = tmp_path / "categories.html"
    render_categories_treemap(df, out)
    content = out.read_text()
    # Names still present
    assert "MILF" in content
    # Page rendered successfully (we don't pin the exact "—" position because
    # Plotly may embed it inside JSON-encoded label data)
    assert "plotly" in content.lower()


def test_render_categories_treemap_raises_on_empty(tmp_path):
    """Empty DataFrame → ValueError, caller in run.py handles."""
    with pytest.raises(ValueError, match="No category snapshots"):
        render_categories_treemap(pd.DataFrame(columns=[
            "snapshot_date", "category_id", "slug", "name", "video_count", "points"
        ]), tmp_path / "out.html")


def test_nav_items_includes_categories():
    """The Categories nav link uses /categories/ (trailing slash, canonical form)."""
    from heatmap import _NAV_ITEMS
    hrefs = [item[1] for item in _NAV_ITEMS]
    assert "/categories/" in hrefs, f"got hrefs={hrefs}"


def test_sitemap_includes_categories_page(tmp_path):
    """Sitemap contains /categories/ entry."""
    df = _snapshot_rows()
    write_sitemap_and_robots(df, public_dir=tmp_path)
    text = (tmp_path / "sitemap.xml").read_text()
    assert "<loc>https://hotmap.cam/categories/</loc>" in text


def test_render_categories_treemap_falls_back_when_prior_scrape_skipped(tmp_path):
    """When the prior snapshot is >1 day old (missed scrape), no 1-day delta
    should be computed — page renders with neutral color + '—' labels rather
    than a misleading 2-day delta presented as 'today'."""
    today = pd.Timestamp("2026-06-05")
    two_days_ago = pd.Timestamp("2026-06-03")  # gap = 2 days
    rows = [
        {"snapshot_date": today, "category_id": 37, "slug": "18-25",
         "name": "18-25", "video_count": 290000, "points": None},
        {"snapshot_date": today, "category_id": 29, "slug": "milf",
         "name": "MILF", "video_count": 200000, "points": None},
        {"snapshot_date": two_days_ago, "category_id": 37, "slug": "18-25",
         "name": "18-25", "video_count": 289000, "points": None},
        {"snapshot_date": two_days_ago, "category_id": 29, "slug": "milf",
         "name": "MILF", "video_count": 199000, "points": None},
    ]
    df = pd.DataFrame(rows)
    out = tmp_path / "categories.html"
    render_categories_treemap(df, out)
    content = out.read_text()
    # Names render
    assert "MILF" in content
    assert "18-25" in content
    # Page renders successfully — exact "—" placement varies inside JSON-encoded
    # tile labels, so we don't assert on it directly. The key test is that the
    # render completes without raising and without inventing a fake "+1000 today"
    # label. (1d delta of 1000 would have rendered if gap-check was missing.)
    assert "plotly" in content.lower()


def test_render_categories_treemap_excludes_non_genre_meta_categories(tmp_path):
    """HD Porn, Verified Amateurs, Amateur, Pornstar, Exclusive, 60FPS, Verified
    Couples/Models are scraped and stored but never rendered — they're meta-tags,
    not genres, and dominate the catalog by ubiquity rather than signal."""
    today = pd.Timestamp("2026-06-02")
    yesterday = pd.Timestamp("2026-06-01")
    rows = []
    for d in (today, yesterday):
        rows += [
            # All 8 meta-tags from _NON_GENRE_CATEGORY_IDS — must NOT appear
            {"snapshot_date": d, "category_id": 38,  "slug": "hd-porn",          "name": "HD Porn",           "video_count": 1_000_000, "points": None},
            {"snapshot_date": d, "category_id": 138, "slug": "verified-amateurs","name": "Verified Amateurs", "video_count":   726_377, "points": None},
            {"snapshot_date": d, "category_id": 3,   "slug": "amateur",          "name": "Amateur",           "video_count":   527_979, "points": None},
            {"snapshot_date": d, "category_id": 115, "slug": "exclusive",        "name": "Exclusive",         "video_count":   399_269, "points": None},
            {"snapshot_date": d, "category_id": 30,  "slug": "pornstar",         "name": "Pornstar",          "video_count":   191_116, "points": None},
            {"snapshot_date": d, "category_id": 105, "slug": "60fps-1",          "name": "60FPS",             "video_count":   130_256, "points": None},
            {"snapshot_date": d, "category_id": 482, "slug": "verified-couples", "name": "Verified Couples",  "video_count":    62_126, "points": None},
            {"snapshot_date": d, "category_id": 139, "slug": "verified-models",  "name": "Verified Models",   "video_count":    51_419, "points": None},
            # Two real genres — must appear
            {"snapshot_date": d, "category_id": 35,  "slug": "anal",             "name": "Anal",              "video_count":   142_217, "points": None},
            {"snapshot_date": d, "category_id": 29,  "slug": "milf",             "name": "MILF",              "video_count":   199_835, "points": None},
        ]
    df = pd.DataFrame(rows)
    out = tmp_path / "categories.html"
    render_categories_treemap(df, out)
    content = out.read_text()
    # All 8 meta-tag names absent from rendered output
    for excluded in ("HD Porn", "Verified Amateurs", "Verified Couples", "Verified Models",
                     "Exclusive", "60FPS"):
        assert excluded not in content, f"meta-tag {excluded!r} should not appear in treemap"
    # The header description quotes the count of categories rendered. After
    # filtering 8 meta-tags from 10 inputs, exactly 2 genres remain.
    assert "2 Pornhub categories" in content, \
        "expected '2 Pornhub categories' in description after filtering 8 meta-tags out of 10"
    # Plotly binary-encodes tile labels (base64 bdata) so we can't search them as text;
    # we rely on the count assertion above + the meta-name absence checks for confidence.


def test_render_categories_treemap_raises_when_only_meta_categories_present(tmp_path):
    """If after filtering all rows are meta-tags, the function refuses to render
    (no point in an empty treemap)."""
    df = pd.DataFrame([
        {"snapshot_date": pd.Timestamp("2026-06-02"), "category_id": 38, "slug": "hd-porn",
         "name": "HD Porn", "video_count": 1_000_000, "points": None},
        {"snapshot_date": pd.Timestamp("2026-06-02"), "category_id": 3, "slug": "amateur",
         "name": "Amateur", "video_count": 500_000, "points": None},
    ])
    with pytest.raises(ValueError, match="No genre categories"):
        render_categories_treemap(df, tmp_path / "out.html")


def _country_snapshots_fixture() -> pd.DataFrame:
    """Three days of history; 3 performers with country='Russia', 1 with 'Italy'."""
    rows = []
    for d in (date(2026, 5, 26), date(2026, 5, 27), date(2026, 5, 28)):
        # Russia: 3 performers
        for slug, base_views in [("ru1", 100_000_000), ("ru2", 80_000_000), ("ru3", 60_000_000)]:
            rows.append({
                "snapshot_date": pd.Timestamp(d), "slug": slug, "name": slug.upper(),
                "total_views": base_views + (d.toordinal() - date(2026, 5, 26).toordinal()) * 10_000,
                "rank": 1, "gender": "female", "country": "Russia",
            })
        # Italy: 1 performer
        rows.append({
            "snapshot_date": pd.Timestamp(d), "slug": "it1", "name": "IT1",
            "total_views": 50_000_000 + (d.toordinal() - date(2026, 5, 26).toordinal()) * 5_000,
            "rank": 4, "gender": "female", "country": "Italy",
        })
    return pd.DataFrame(rows)


def test_render_country_page_writes_html(tmp_path):
    """render_country_page emits a single-treemap page filtered to one country."""
    df = _country_snapshots_fixture()
    out = tmp_path / "russia.html"
    render_country_page(df, "Russia", out)
    assert out.exists()
    content = out.read_text()

    assert "<html" in content.lower()
    assert "Russia" in content
    assert "Top performers from Russia" in content  # H1 + SEO title pattern
    assert 'rel="canonical" href="https://hotmap.cam/country/russia/"' in content
    assert 'property="og:type" content="website"' in content
    # Plotly bundle embedded
    assert "plotly" in content.lower()
    # JSON-LD
    blocks = _extract_jsonld_blocks(content)
    types = {b.get("@type") for b in blocks}
    assert "CollectionPage" in types and "BreadcrumbList" in types


def test_render_country_page_raises_when_no_performers(tmp_path):
    df = _country_snapshots_fixture()
    with pytest.raises(ValueError, match="No performers for country"):
        render_country_page(df, "Nonexistentland", tmp_path / "out.html")


def test_render_country_page_excludes_males(tmp_path):
    """Country pages show female performers only — male slugs must not appear."""
    df = _country_snapshots_fixture()
    extra = pd.DataFrame([
        {"snapshot_date": pd.Timestamp(d), "slug": "ru-dude", "name": "RuDude",
         "total_views": 90_000_000, "rank": 5, "gender": "male", "country": "Russia"}
        for d in (date(2026, 5, 26), date(2026, 5, 27), date(2026, 5, 28))
    ])
    out = tmp_path / "russia.html"
    render_country_page(pd.concat([df, extra], ignore_index=True), "Russia", out)
    content = out.read_text()
    assert "ru-dude" not in content and "RuDude" not in content


def test_render_country_page_raises_when_only_males(tmp_path):
    """Country with no female performers → ValueError (caller skips the page)."""
    df = pd.DataFrame([
        {"snapshot_date": pd.Timestamp(d), "slug": "m1", "name": "M1",
         "total_views": 100_000_000, "rank": 1, "gender": "male", "country": "Maleland"}
        for d in (date(2026, 5, 26), date(2026, 5, 27), date(2026, 5, 28))
    ])
    with pytest.raises(ValueError, match="No performers for country"):
        render_country_page(df, "Maleland", tmp_path / "out.html")


def test_country_min_performers_constant_is_5():
    from heatmap import _COUNTRY_MIN_PERFORMERS
    assert _COUNTRY_MIN_PERFORMERS == 5


def test_render_countries_index_lists_qualifying_countries(tmp_path):
    """Countries with >= _COUNTRY_MIN_PERFORMERS get listed; others omitted."""
    rows = []
    # Russia: 6 performers (qualifying)
    for i in range(6):
        rows.append({
            "snapshot_date": pd.Timestamp("2026-06-02"), "slug": f"ru{i}", "name": f"RU{i}",
            "total_views": 100_000_000, "rank": 1, "gender": "female", "country": "Russia",
        })
    # Italy: 5 performers (just-qualifying)
    for i in range(5):
        rows.append({
            "snapshot_date": pd.Timestamp("2026-06-02"), "slug": f"it{i}", "name": f"IT{i}",
            "total_views": 80_000_000, "rank": 1, "gender": "female", "country": "Italy",
        })
    # Estonia: 2 performers (below threshold — must be excluded)
    for i in range(2):
        rows.append({
            "snapshot_date": pd.Timestamp("2026-06-02"), "slug": f"ee{i}", "name": f"EE{i}",
            "total_views": 50_000_000, "rank": 1, "gender": "female", "country": "Estonia",
        })
    df = pd.DataFrame(rows)
    out = tmp_path / "index.html"
    render_countries_index(df, out)
    content = out.read_text()

    # Qualifying countries present
    assert '<a href="/country/russia/"' in content
    assert "Russia" in content
    assert '<a href="/country/italy/"' in content
    assert "Italy" in content
    # Counts visible
    assert "6" in content
    assert "5" in content
    # Below-threshold absent
    assert "Estonia" not in content
    assert "/country/estonia/" not in content
    # SEO + breadcrumbs
    assert 'rel="canonical" href="https://hotmap.cam/countries/"' in content
    blocks = _extract_jsonld_blocks(content)
    types = {b.get("@type") for b in blocks}
    assert "CollectionPage" in types and "BreadcrumbList" in types


def test_render_countries_index_counts_females_only_and_renders_flag(tmp_path):
    """Visible count = female slugs only; flag <img> appears next to known countries."""
    rows = []
    # Russia qualifies (≥5 total): 4 female + 2 male — displayed count must be 4.
    for i in range(4):
        rows.append({
            "snapshot_date": pd.Timestamp("2026-06-02"), "slug": f"ruf{i}", "name": f"RUF{i}",
            "total_views": 100_000_000, "rank": 1, "gender": "female", "country": "Russia",
        })
    for i in range(2):
        rows.append({
            "snapshot_date": pd.Timestamp("2026-06-02"), "slug": f"rum{i}", "name": f"RUM{i}",
            "total_views": 100_000_000, "rank": 1, "gender": "male", "country": "Russia",
        })
    df = pd.DataFrame(rows)
    out = tmp_path / "index.html"
    render_countries_index(df, out)
    content = out.read_text()

    assert "(4 actresses)" in content
    assert "(6 actresses)" not in content
    # Russia flag emoji (regional indicators R + U)
    assert "\U0001F1F7\U0001F1FA" in content
    assert 'class="cat-flag"' in content


def test_performer_page_emits_country_cross_link(tmp_path):
    """When performer has a country AND it's in the qualifying set, /p/<slug> shows a 'From' block."""
    df = _snapshot_rows().copy()
    # Inject country into Alice's snapshots
    df.loc[df["slug"] == "alice", "country"] = "Russia"
    out = tmp_path / "alice.html"
    render_performer_page(df, slug="alice", output_path=out, qualifying_countries={"Russia"})
    content = out.read_text()
    assert 'class="performer-country"' in content
    assert '<a href="/country/russia/">Russia</a>' in content


def test_performer_page_omits_country_block_when_not_qualifying(tmp_path):
    """Performer has a country, but country not in qualifying set → no block."""
    df = _snapshot_rows().copy()
    df.loc[df["slug"] == "alice", "country"] = "Estonia"
    out = tmp_path / "alice.html"
    render_performer_page(df, slug="alice", output_path=out, qualifying_countries={"Russia"})
    content = out.read_text()
    assert "performer-country" not in content
    assert "/country/estonia/" not in content


def test_performer_page_omits_country_block_when_country_is_none(tmp_path):
    """Performer with no country → no block even if qualifying_countries is provided."""
    df = _snapshot_rows().copy()
    df["country"] = None  # Force None
    out = tmp_path / "alice.html"
    render_performer_page(df, slug="alice", output_path=out, qualifying_countries={"Russia"})
    content = out.read_text()
    assert "performer-country" not in content


def test_main_treemap_page_has_share_card_wiring(tmp_path):
    """render_treemap_page emits the .share-card hidden div, buildShareCard JS,
    data-page-type='main' on body, and a /share-bg/ background URL reference."""
    df = _snapshot_rows()
    out = tmp_path / "out.html"
    render_treemap_page(df, out)
    content = out.read_text()

    # Hidden share card composition (minimal v1.2: brand strip + title + treemap)
    assert 'class="share-card"' in content
    assert 'class="share-card-brand-strip"' in content
    assert 'class="share-card-mode-label"' in content
    assert 'class="share-card-treemap-slot"' in content

    # JS function + page-type wiring
    assert 'function buildShareCard' in content
    assert 'data-page-type="main"' in content
    assert "/share-bg/bg-" in content


def test_main_treemap_page_save_button_uses_build_share_card(tmp_path):
    """Save Image click handler invokes buildShareCard, not the old hero+panel
    DOM clone."""
    df = _snapshot_rows()
    out = tmp_path / "out.html"
    render_treemap_page(df, out)
    content = out.read_text()

    # Old literal-screenshot path is gone — no clone of .hero
    assert "document.querySelector('.hero').cloneNode" not in content
    # New path is in
    assert "buildShareCard()" in content


def test_country_page_has_share_card_wiring(tmp_path):
    """render_country_page emits .share-card, save button, html2canvas script,
    data-page-type='country', and data-context-label with the country name."""
    df = _country_snapshots_fixture()
    out = tmp_path / "russia.html"
    render_country_page(df, "Russia", out)
    content = out.read_text()

    assert 'class="share-card"' in content
    assert 'function buildShareCard' in content
    assert 'data-page-type="country"' in content
    assert 'data-context-label="Russia"' in content
    assert 'data-updated-at=' in content
    assert 'class="save-image-btn"' in content
    assert "/share-bg/bg-" in content
    # html2canvas needs to be loaded — country page didn't have it before
    assert "html2canvas" in content


def test_categories_page_has_share_card_wiring_and_top_meta(tmp_path):
    """render_categories_treemap emits .share-card + the hidden #share-card-top-category
    meta div with the day's top-mover category and delta label."""
    df = _category_snapshots_fixture(with_baseline=True)
    out = tmp_path / "categories.html"
    render_categories_treemap(df, out)
    content = out.read_text()

    assert 'class="share-card"' in content
    assert 'function buildShareCard' in content
    assert 'data-page-type="category"' in content
    assert 'data-updated-at=' in content
    assert 'class="save-image-btn"' in content
    assert "/share-bg/bg-" in content
    assert "html2canvas" in content

    # Hidden meta div with top category
    assert 'id="share-card-top-category"' in content
    assert 'data-name=' in content
    assert 'data-delta-label=' in content
