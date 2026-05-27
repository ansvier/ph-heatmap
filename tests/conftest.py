from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def top_list_html() -> str:
    return (FIXTURES / "top_list.html").read_text()


@pytest.fixture
def profile_html() -> str:
    return (FIXTURES / "profile.html").read_text()
