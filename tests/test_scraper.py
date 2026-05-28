import pytest

from scraper import parse_profile, parse_top_list


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
