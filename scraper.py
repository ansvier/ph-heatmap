from __future__ import annotations

import json as _json
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
    country: str | None = None


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
    country = _extract_country_from_tree(tree)
    return ProfileData(name=name, total_views=total_views, photo_url=photo_url, country=country)


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


# Matches a JSON object literal containing "id", "slug", "video_count", and "status" keys.
# Uses [^{}] to disallow nested braces — category objects in PH's HTML are flat.
_CATEGORY_BLOCK_RE = re.compile(
    r'\{[^{}]*?"id"\s*:\s*\d+[^{}]*?"slug"\s*:\s*"[^"]+"[^{}]*?"video_count"\s*:\s*\d+[^{}]*?\}'
)


def parse_category_catalog(html: str) -> list[dict]:
    """Extract the embedded category catalog from PH's /categories page HTML.

    Returns [{id, slug, name, video_count, points, url}, ...] with:
      - status == "active" entries only (filters soft-deleted)
      - deduped by id (PH duplicates entries in cross-category panels)
      - points may be None when the field is absent in the source JSON
      - url is PH's per-category landing URL (heterogeneous across the
        catalog: /video/incategories/<parent>/<slug>, /video/search?search=<slug>,
        ?c=<id>, etc.). Always present in PH's JSON. May be None for malformed
        rows; downstream renderers fall back to a search URL in that case.
    """
    out: list[dict] = []
    seen_ids: set[int] = set()
    for match in _CATEGORY_BLOCK_RE.finditer(html):
        block = match.group(0)
        try:
            obj = _json.loads(block)
            if obj.get("status") != "active":
                continue
            cid = obj["id"]
            if cid in seen_ids:
                continue
            out.append({
                "id": cid,
                "slug": obj["slug"],
                # Prefer the english-language name when PH serves a localized
                # catalog (local IP geolocation can pin PH to a regional
                # language; the catalog JSON always includes the canonical
                # english label alongside the localized name).
                "name": obj.get("english") or obj["name"],
                "video_count": obj["video_count"],
                "points": obj.get("points"),
                "url": obj.get("url"),
            })
            seen_ids.add(cid)
        except (_json.JSONDecodeError, KeyError):
            # Skip malformed or partial blocks — PH HTML drift shouldn't brick the run.
            continue
    return out


_TOP_LIST_URL_TEMPLATE = "https://www.pornhub.com/pornstars?o=mv&gender={gender}"
_PROFILE_URL_TEMPLATE = "https://www.pornhub.com/pornstar/{slug}"
_IMPERSONATE = os.environ.get("PH_IMPERSONATE", "chrome120")
_REQUEST_TIMEOUT = 30  # seconds

# When the env-configured impersonate value gives an empty top-list, we cycle
# through these as fallbacks. PH/Cloudflare occasionally tightens TLS-fingerprint
# rules for one browser version while leaving others through.
_IMPERSONATE_FALLBACKS = ("chrome120", "chrome119", "chrome116", "safari17_0", "edge101")


# Background (PH nationality field) → canonical country name. Used as a fallback
# when Birth Place is missing. Entries cover the nationalities observed across
# sample profiles; unmapped values resolve to None (performer just won't be
# attributed to any country).
_NATIONALITY_TO_COUNTRY = {
    "American": "United States",
    "British": "United Kingdom",
    "Russian": "Russia",
    "Italian": "Italy",
    "French": "France",
    "German": "Germany",
    "Spanish": "Spain",
    "Brazilian": "Brazil",
    "Mexican": "Mexico",
    "Japanese": "Japan",
    "Korean": "South Korea",
    "Chinese": "China",
    "Australian": "Australia",
    "Canadian": "Canada",
    "Czech": "Czech Republic",
    "Polish": "Poland",
    "Ukrainian": "Ukraine",
    "Hungarian": "Hungary",
    "Romanian": "Romania",
    "Argentine": "Argentina",
    "Argentinian": "Argentina",
    "Colombian": "Colombia",
    "Dutch": "Netherlands",
    "Swedish": "Sweden",
    "Norwegian": "Norway",
    "Finnish": "Finland",
    "Danish": "Denmark",
    "Turkish": "Turkey",
    "Greek": "Greece",
    "Portuguese": "Portugal",
    "Indian": "India",
    "Filipino": "Philippines",
    "Thai": "Thailand",
    "Vietnamese": "Vietnam",
    "Indonesian": "Indonesia",
    "Bulgarian": "Bulgaria",
    "Serbian": "Serbia",
    "Croatian": "Croatia",
    "Slovakian": "Slovakia",
    "Slovenian": "Slovenia",
    "English": "United Kingdom",
    "Irish": "Ireland",
    "Belgian": "Belgium",
    "Austrian": "Austria",
    "Cuban": "Cuba",
    "Dominican": "Dominican Republic",
    "Puerto Rican": "Puerto Rico",
    "Egyptian": "Egypt",
    "Nigerian": "Nigeria",
    "Armenian": "Armenia",
    "Peruvian": "Peru",
    "Venezuelan": "Venezuela",
    "Uruguayan": "Uruguay",
    "New Zealander": "New Zealand",
}

# Birth Place country variants → canonical name.
_COUNTRY_ALIASES = {
    "United States of America": "United States",
    "USA": "United States",
    "U.S.A.": "United States",
    "U.S.": "United States",
    "UK": "United Kingdom",
    "U.K.": "United Kingdom",
    "Great Britain": "United Kingdom",
    "England": "United Kingdom",
    "Scotland": "United Kingdom",
}


def _canonicalize_country(name: str) -> str:
    """Map common Birth Place variants ('USA', 'England', etc.) to canonical names.
    Unknown names pass through unchanged."""
    name = name.strip()
    return _COUNTRY_ALIASES.get(name, name)


def _extract_country_from_tree(tree: HTMLParser) -> str | None:
    """Tree-based country extractor — used by parse_profile (which already has a tree).

    Strategy:
      1. Birth Place infoPiece → take last comma-segment → canonicalize.
      2. Background infoPiece → map nationality via _NATIONALITY_TO_COUNTRY.
      3. Return None if neither produces a value.
    """
    birth_place = None
    background = None
    for piece in tree.css(".infoPiece"):
        text = piece.text(strip=True)
        if text.startswith("Birth Place:"):
            birth_place = text[len("Birth Place:"):].strip()
        elif text.startswith("Background:"):
            background = text[len("Background:"):].strip()

    if birth_place:
        country = birth_place.split(",")[-1].strip()
        if country:
            return _canonicalize_country(country)

    if background:
        mapped = _NATIONALITY_TO_COUNTRY.get(background)
        if mapped:
            return mapped

    return None


def extract_country(html: str) -> str | None:
    """HTML-based country extractor — public API used by the backfill script."""
    return _extract_country_from_tree(HTMLParser(html))


def _fetch(url: str, impersonate: str | None = None) -> tuple[str, int]:
    """Return (body, status). Raises only on connection errors, not HTTP errors —
    callers want to inspect 403/empty responses themselves for diagnostics."""
    response = cffi_requests.get(url, impersonate=impersonate or _IMPERSONATE, timeout=_REQUEST_TIMEOUT)
    return response.text, response.status_code


def _diagnose_empty(body: str, status: int) -> str:
    """Return a short hint about why the top-list page parsed as empty."""
    if status != 200:
        return f"HTTP {status}"
    if not body:
        return "empty body"
    needles = [
        ("Cloudflare challenge", "challenge-platform"),
        ("Cloudflare interstitial", "cf-browser-verification"),
        ("captcha", "captcha"),
        ("blocked", "Access denied"),
        ("rate limit", "rate limited"),
    ]
    low = body.lower()
    for label, needle in needles:
        if needle.lower() in low:
            return f"{label} (len={len(body)})"
    if "popularPornstars" not in body:
        return f"missing #popularPornstars in HTML (len={len(body)}) — markup may have changed"
    return f"#popularPornstars present but empty (len={len(body)})"


def fetch_top_pornstars(limit: int = 50, gender: str = "female") -> list[str]:
    """Fetch up to `limit` slugs from the top-list with impersonate fallback.

    If the first attempt returns no slugs (Cloudflare challenge, empty list,
    parser mismatch...), we retry the page-1 fetch with each value in
    _IMPERSONATE_FALLBACKS before giving up. Once a non-empty page-1 response
    is found, the rest of the pagination uses that same impersonate value.
    """
    if gender not in {"female", "male"}:
        raise ValueError(f"gender must be 'female' or 'male', got {gender!r}")

    base_url = _TOP_LIST_URL_TEMPLATE.format(gender=gender)

    # Resolve a working impersonate by probing page 1 — start with env-configured,
    # then fall back through the list.
    attempts = [_IMPERSONATE] + [i for i in _IMPERSONATE_FALLBACKS if i != _IMPERSONATE]
    chosen_impersonate: str | None = None
    first_page_slugs: list[str] = []
    for imp in attempts:
        body, status = _fetch(base_url, impersonate=imp)
        candidate = parse_top_list(body, limit=limit)
        if candidate:
            chosen_impersonate = imp
            first_page_slugs = candidate
            break
        print(
            f"  scraper: page 1 empty for {gender} with impersonate={imp} → {_diagnose_empty(body, status)}",
            flush=True,
        )

    if not chosen_impersonate:
        return []  # all impersonate values failed; caller logs the WARN

    if chosen_impersonate != _IMPERSONATE:
        print(f"  scraper: fell back to impersonate={chosen_impersonate} for {gender}", flush=True)

    seen: set[str] = set()
    slugs: list[str] = []
    for s in first_page_slugs:
        if s not in seen:
            seen.add(s)
            slugs.append(s)
            if len(slugs) >= limit:
                return slugs

    # Continue paginating with the chosen impersonate
    page = 2
    while len(slugs) < limit and page <= 20:
        polite_sleep()
        url = f"{base_url}&page={page}"
        body, _status = _fetch(url, impersonate=chosen_impersonate)
        page_slugs = parse_top_list(body, limit=limit)
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
            break
        page += 1
    return slugs


def fetch_profile(slug: str) -> ProfileData:
    """Fetch a profile page and parse it. PH selectively serves stripped
    pages without 'Video Views' to suspected automation on the residential
    runner IP; retry with each fallback TLS-fingerprint when parsing fails
    (matches the same defensive pattern fetch_top_pornstars uses for the
    page-1-empty case)."""
    url = _PROFILE_URL_TEMPLATE.format(slug=slug)
    attempts = [_IMPERSONATE] + [i for i in _IMPERSONATE_FALLBACKS if i != _IMPERSONATE]
    last_exc: Exception | None = None
    for imp in attempts:
        body, _status = _fetch(url, impersonate=imp)
        try:
            return parse_profile(body)
        except ValueError as exc:
            # Parser couldn't find 'Video Views' — likely a stripped page.
            # Try the next TLS fingerprint.
            last_exc = exc
            continue
    # Exhausted all fallbacks — bubble up the last parse error.
    assert last_exc is not None
    raise last_exc


_CATEGORIES_CATALOG_URL = "https://www.pornhub.com/categories"


def fetch_category_catalog() -> list[dict]:
    """Fetch PH's /categories page once and parse the embedded catalog.

    Returns [{id, slug, name, video_count, points}, ...] for all active
    categories. ~5 seconds per call. Exceptions from _fetch propagate;
    callers (run.py) wrap in try/except.
    """
    body, _status = _fetch(_CATEGORIES_CATALOG_URL)
    return parse_category_catalog(body)


def polite_sleep(base: float = 1.5, jitter: float = 0.5) -> None:
    """Sleep between requests, jittered to avoid uniform timing."""
    time.sleep(base + random.uniform(-jitter, jitter))
