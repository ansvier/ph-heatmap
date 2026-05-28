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
    photo_url: str | None = None


_SLUG_RE = re.compile(r"^/pornstar/([^/?#]+)")


def parse_top_list(html: str, limit: int = 50) -> list[str]:
    """Return up to `limit` unique pornstar slugs from the main top-list grid.

    Scopes to `<ul id="popularPornstars">` so the gender filter on the URL is
    actually respected — the page also contains a dropdown nav with cross-gender
    recommendations that would leak into a naive scrape.
    """
    tree = HTMLParser(html)
    container = tree.css_first("ul#popularPornstars")
    if container is None:
        return []

    seen: set[str] = set()
    slugs: list[str] = []
    for a in container.css("a[href]"):
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
    """Extract display name, Video Views count, and avatar URL from a profile page."""
    tree = HTMLParser(html)

    name_node = tree.css_first("h1")
    name = name_node.text(strip=True) if name_node else ""

    total_views = _extract_video_views(tree)
    photo_url = _extract_photo_url(tree)
    return ProfileData(name=name, total_views=total_views, photo_url=photo_url)


def _extract_photo_url(tree: HTMLParser) -> str | None:
    """Return the performer's avatar image URL, or None if not found.

    Pornhub puts the canonical profile photo on `<img id="getAvatar">` inside
    the schema.org/Person block. Some layouts use a hashed URL (no `/avatar`
    path), others use `/avatar<id>/<size>.jpg` — both end up on the same ID.
    """
    avatar = tree.css_first("#getAvatar")
    if avatar is not None:
        src = avatar.attributes.get("src") or avatar.attributes.get("data-src")
        if src:
            return src
    # Last-resort fallback for any future layout change.
    header = tree.css_first(".topProfileHeader")
    if header is not None:
        for img in header.css("img"):
            src = img.attributes.get("src") or img.attributes.get("data-src")
            if src and "/avatar" in src:
                return src
    return None


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
    """Fetch up to `limit` slugs from the top-list, paginating as needed.

    Each PH list page returns ~50 slugs from `ul#popularPornstars`. Pages are
    requested with `&page=N`. We stop when we either hit the limit or get a page
    that returns no new slugs (end of list).
    """
    if gender not in {"female", "male"}:
        raise ValueError(f"gender must be 'female' or 'male', got {gender!r}")

    base_url = _TOP_LIST_URL_TEMPLATE.format(gender=gender)
    seen: set[str] = set()
    slugs: list[str] = []
    page = 1
    while len(slugs) < limit:
        url = base_url if page == 1 else f"{base_url}&page={page}"
        page_slugs = parse_top_list(_fetch(url), limit=limit)
        new_count = 0
        for s in page_slugs:
            if s in seen:
                continue
            seen.add(s)
            slugs.append(s)
            new_count += 1
            if len(slugs) >= limit:
                break
        if new_count == 0:
            break  # end of list, no point requesting more pages
        page += 1
        if page > 20:  # safety net — shouldn't happen at sensible limits
            break
        polite_sleep()  # between page requests
    return slugs


def fetch_profile(slug: str) -> ProfileData:
    return parse_profile(_fetch(_PROFILE_URL_TEMPLATE.format(slug=slug)))


def polite_sleep(base: float = 1.5, jitter: float = 0.5) -> None:
    """Sleep between requests, jittered to avoid uniform timing."""
    time.sleep(base + random.uniform(-jitter, jitter))
