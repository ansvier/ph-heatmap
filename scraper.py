from __future__ import annotations

import re
from dataclasses import dataclass

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


def _extract_video_views(tree: HTMLParser) -> int:
    """Find a 'Video Views' label and return the adjacent integer."""
    for label in tree.css("*"):
        text = label.text(strip=True)
        if text != "Video Views":
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
