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


def test_parse_profile_extracts_views_and_name(profile_html):
    result = parse_profile(profile_html)
    assert result.total_views == 123_456_789
    assert result.name == "Alice Example"


def test_parse_profile_raises_when_views_missing():
    html = "<html><body><h1>No Stats Person</h1></body></html>"
    with pytest.raises(ValueError, match="Video Views"):
        parse_profile(html)
