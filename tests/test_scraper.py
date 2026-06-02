from pathlib import Path

import pytest

from scraper import (
    _canonicalize_country,
    extract_country,
    parse_category_catalog,
    parse_profile,
    parse_top_list,
)


def test_parse_top_list_returns_unique_slugs_in_order(top_list_html):
    slugs = parse_top_list(top_list_html, limit=10)
    assert slugs == ["alice-example", "bob-sample", "carol-third"]


def test_parse_top_list_respects_limit(top_list_html):
    slugs = parse_top_list(top_list_html, limit=2)
    assert slugs == ["alice-example", "bob-sample"]


def test_parse_top_list_ignores_non_pornstar_links(top_list_html):
    slugs = parse_top_list(top_list_html, limit=50)
    assert "something-else" not in slugs


def test_parse_top_list_ignores_dropdown_nav(top_list_html):
    """Slugs outside #popularPornstars (e.g. dropdown nav recommendations)
    must be excluded — they leak cross-gender data otherwise."""
    slugs = parse_top_list(top_list_html, limit=50)
    assert "decoy-from-nav" not in slugs


def test_parse_profile_extracts_views_and_name(profile_html):
    result = parse_profile(profile_html)
    assert result.total_views == 123_456_789
    assert result.name == "Alice Example"


def test_parse_profile_extracts_avatar_url(profile_html):
    result = parse_profile(profile_html)
    assert result.photo_url is not None
    # The picked URL must be the one under #getAvatar (the canonical profile photo).
    assert "/avatar123/" in result.photo_url
    # Banner and decoy images must NOT be selected.
    assert "cover" not in result.photo_url
    assert "999" not in result.photo_url  # decoy "DecoyPerson" avatar


def test_parse_profile_photo_url_is_none_when_missing():
    html = """<html><body>
        <div class="tooltipTrig infoBox videoViews" data-title="Video views: 1">
            <span>1</span><div class="title">Video views</div>
        </div>
        <h1>NoPhoto</h1>
    </body></html>"""
    result = parse_profile(html)
    assert result.photo_url is None


def test_parse_profile_raises_when_views_missing():
    html = "<html><body><h1>No Stats Person</h1></body></html>"
    with pytest.raises(ValueError, match="Video Views"):
        parse_profile(html)


def _read_categories_fixture() -> str:
    return (Path(__file__).parent / "fixtures" / "categories_catalog.html").read_text()


def test_parse_category_catalog_extracts_required_fields():
    """parse_category_catalog returns the 3 active categories with all required fields."""
    html = _read_categories_fixture()
    result = parse_category_catalog(html)
    # 3 active distinct categories (37, 29, 1); duplicate 37 dedup'd; inactive 999 filtered
    assert len(result) == 3, f"expected 3 active categories, got {len(result)}: {result}"
    by_id = {r["id"]: r for r in result}
    assert by_id[37]["slug"] == "18-25"
    assert by_id[37]["name"] == "18-25"
    assert by_id[37]["video_count"] == 289620
    assert by_id[37]["points"] == 65005
    assert by_id[29]["slug"] == "milf"
    assert by_id[29]["video_count"] == 199835
    # Anal had no `points` field — None
    assert by_id[1]["points"] is None


def test_parse_category_catalog_filters_inactive():
    """status != 'active' rows are dropped."""
    html = _read_categories_fixture()
    result = parse_category_catalog(html)
    ids = {r["id"] for r in result}
    assert 999 not in ids, "deprecated category should be filtered"


def test_parse_category_catalog_dedupes_by_id():
    """Same id appearing multiple times produces only one output row."""
    html = _read_categories_fixture()
    result = parse_category_catalog(html)
    ids = [r["id"] for r in result]
    assert len(ids) == len(set(ids)), f"duplicates found: {ids}"


def test_parse_category_catalog_empty_when_no_blocks():
    """HTML with no category JSON returns empty list."""
    assert parse_category_catalog("<html><body><h1>nothing</h1></body></html>") == []


def test_fetch_category_catalog_hits_categories_url(monkeypatch):
    """fetch_category_catalog calls /categories once and returns parsed entries."""
    captured = {}

    def fake_fetch(url, impersonate=None):
        captured["url"] = url
        return (_read_categories_fixture(), 200)

    import scraper
    monkeypatch.setattr(scraper, "_fetch", fake_fetch)

    result = scraper.fetch_category_catalog()
    assert captured["url"] == "https://www.pornhub.com/categories"
    assert len(result) == 3
    assert {r["id"] for r in result} == {37, 29, 1}


def test_parse_category_catalog_skips_partial_blocks():
    """A JSON block missing 'name' (or any required field) is skipped, not raised on."""
    # Block 1: well-formed. Block 2: missing 'name'. Block 3: well-formed.
    html = """
    <script>{"id":1,"name":"Anal","slug":"anal","status":"active","video_count":100,"points":50}</script>
    <script>{"id":2,"slug":"badblock","status":"active","video_count":200,"points":75}</script>
    <script>{"id":3,"name":"MILF","slug":"milf","status":"active","video_count":300,"points":150}</script>
    """
    result = parse_category_catalog(html)
    ids = {r["id"] for r in result}
    assert ids == {1, 3}, f"expected only well-formed entries (1, 3), got {ids}"


@pytest.mark.parametrize("birth_place, expected", [
    ("Chicago, Illinois, United States of America", "United States"),
    ("Russia", "Russia"),
])
def test_extract_country_from_birth_place(birth_place, expected):
    """Birth Place — full address takes last segment; bare country passes through."""
    html = f'<html><body><div class="infoPiece">Birth Place:{birth_place}</div></body></html>'
    assert extract_country(html) == expected


def test_extract_country_falls_back_to_background_nationality():
    """When Birth Place missing but Background is a known nationality → mapped country."""
    html = '<html><body><div class="infoPiece">Background:Italian</div></body></html>'
    assert extract_country(html) == "Italy"


def test_extract_country_birth_place_wins_over_background():
    """If both present, Birth Place takes priority."""
    html = (
        '<html><body>'
        '<div class="infoPiece">Birth Place:Russia</div>'
        '<div class="infoPiece">Background:American</div>'
        '</body></html>'
    )
    assert extract_country(html) == "Russia"


def test_extract_country_returns_none_when_both_absent():
    """No Birth Place, no Background → None."""
    html = '<html><body><div class="infoPiece">Career Status:Active</div></body></html>'
    assert extract_country(html) is None


def test_extract_country_returns_none_when_background_unmapped():
    """Background present but nationality not in our dict → None (not raw value)."""
    html = '<html><body><div class="infoPiece">Background:Martian</div></body></html>'
    assert extract_country(html) is None


@pytest.mark.parametrize("input_, expected", [
    ("United States of America", "United States"),
    ("USA", "United States"),
    ("U.S.A.", "United States"),
])
def test_canonicalize_country_collapses_usa_variants(input_, expected):
    assert _canonicalize_country(input_) == expected


@pytest.mark.parametrize("input_, expected", [
    ("United Kingdom", "United Kingdom"),
    ("UK", "United Kingdom"),
    ("Great Britain", "United Kingdom"),
    ("England", "United Kingdom"),
])
def test_canonicalize_country_collapses_uk_variants(input_, expected):
    assert _canonicalize_country(input_) == expected


@pytest.mark.parametrize("input_, expected", [
    ("Russia", "Russia"),
    ("Belarus", "Belarus"),
])
def test_canonicalize_country_passes_through_unknown(input_, expected):
    assert _canonicalize_country(input_) == expected


def test_parse_profile_includes_country():
    """parse_profile now returns ProfileData with the country field populated."""
    html = (
        '<html><body>'
        '<h1>Test Performer</h1>'
        '<span class="videoViews" data-title="Video views: 1,234,567"></span>'
        '<div class="infoPiece">Birth Place:Russia</div>'
        '</body></html>'
    )
    result = parse_profile(html)
    assert result.country == "Russia"
