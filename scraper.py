from __future__ import annotations

import os
import random
import re
import time
from dataclasses import dataclass

from curl_cffi import requests as cffi_requests
from selectolax.parser import HTMLParser


@dataclass(frozen=True)
class ProfileData:
    name: str
    total_views: int


_SLUG_RE = re.compile(r"^/pornstar/([^/?#]+)")


def parse_top_list(html: str, limit: int = 50) -> list[str]:
    """Return up to `limit` unique pornstar slugs in document order."""
    tree = HTMLParser(html)
    seen: set[str] = set()
    slugs: list[str] = []
    for a in tree.css("a[href]"):
        match = _SLUG_RE.match(a.attributes.get("href", "") or "")
        if not match:
            continue
        slug = match.group(1)
        if slug in seen:
            continue
        seen.add(slug)
        slugs.append(slug)
        if len(slugs) >= limit:
            break
    return slugs


def parse_profile(html: str) -> ProfileData:
    """Extract display name and Video Views count from a profile page."""
    tree = HTMLParser(html)

    name_node = tree.css_first("h1")
    name = name_node.text(strip=True) if name_node else ""

    total_views = _extract_video_views(tree)
    return ProfileData(name=name, total_views=total_views)


_VIEWS_DATA_TITLE_RE = re.compile(r"Video views?\s*:\s*([\d,]+)", re.IGNORECASE)


def _extract_video_views(tree: HTMLParser) -> int:
    """Find the cumulative Video Views count on a profile page.

    Primary path: the `.videoViews` infoBox carries `data-title="Video views: 123,456,789"`
    which is the precise count (the visible span is abbreviated, e.g. "123M").
    Fallback path: walk any element whose text equals 'Video Views' / 'Video views'
    and read the adjacent integer.
    """
    for node in tree.css(".videoViews[data-title]"):
        title = node.attributes.get("data-title", "") or ""
        match = _VIEWS_DATA_TITLE_RE.search(title)
        if match:
            return int(match.group(1).replace(",", ""))

    for label in tree.css("*"):
        text = label.text(strip=True)
        if text.lower() != "video views":
            continue
        sibling = label.next
        candidates: list[str] = []
        if sibling is not None:
            candidates.append(sibling.text(strip=True))
        parent = label.parent
        if parent is not None:
            for child in parent.iter():
                if child is label:
                    continue
                candidates.append(child.text(strip=True))
        for cand in candidates:
            digits = re.sub(r"[^\d]", "", cand)
            if digits:
                return int(digits)
    raise ValueError("Could not find 'Video Views' on profile page")


_TOP_LIST_URL_TEMPLATE = "https://www.pornhub.com/pornstars?o=mv&gender={gender}"
_PROFILE_URL_TEMPLATE = "https://www.pornhub.com/pornstar/{slug}"
_IMPERSONATE = os.environ.get("PH_IMPERSONATE", "chrome120")
_REQUEST_TIMEOUT = 30  # seconds


def _fetch(url: str) -> str:
    response = cffi_requests.get(url, impersonate=_IMPERSONATE, timeout=_REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.text


def fetch_top_pornstars(limit: int = 50, gender: str = "female") -> list[str]:
    if gender not in {"female", "male"}:
        raise ValueError(f"gender must be 'female' or 'male', got {gender!r}")
    url = _TOP_LIST_URL_TEMPLATE.format(gender=gender)
    return parse_top_list(_fetch(url), limit=limit)


def fetch_profile(slug: str) -> ProfileData:
    return parse_profile(_fetch(_PROFILE_URL_TEMPLATE.format(slug=slug)))


def polite_sleep(base: float = 1.5, jitter: float = 0.5) -> None:
    """Sleep between requests, jittered to avoid uniform timing."""
    time.sleep(base + random.uniform(-jitter, jitter))
