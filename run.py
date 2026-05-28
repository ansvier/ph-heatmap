from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from db import Snapshot, init_db, insert_snapshot, load_all_snapshots
from heatmap import dump_json, render_performer_page, render_treemap_page, write_sitemap_and_robots
from scraper import fetch_profile, fetch_top_pornstars, polite_sleep
from curl_cffi import requests as cffi_requests
import os

_AVATAR_IMPERSONATE = os.environ.get("PH_IMPERSONATE", "chrome120")


def _download_avatar(remote_url: str, dest_dir: Path, slug: str) -> str | None:
    """Download an avatar image to dest_dir/<slug>.<ext>, return public path or None.

    Saves the file using slug as the filename so we don't accumulate stale versions
    per snapshot — each scrape overwrites the previous avatar for that performer.
    Returns the path relative to PUBLIC_DIR (e.g. 'avatars/lana-rhoades.jpg').
    """
    if not remote_url:
        return None
    try:
        r = cffi_requests.get(remote_url, impersonate=_AVATAR_IMPERSONATE, timeout=15)
        r.raise_for_status()
    except Exception as exc:
        print(f"  WARN: avatar download failed for {slug}: {exc}", file=sys.stderr)
        return None
    # Determine extension from content-type, falling back to .jpg.
    ext = ".jpg"
    ctype = r.headers.get("content-type", "").lower()
    if "png" in ctype:
        ext = ".png"
    elif "webp" in ctype:
        ext = ".webp"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{slug}{ext}"
    dest_path.write_bytes(r.content)
    return f"avatars/{slug}{ext}"

PROJECT_ROOT = Path(__file__).parent
PUBLIC_DIR = PROJECT_ROOT / "public"
AVATAR_DIR = PUBLIC_DIR / "avatars"
PERFORMER_DIR = PUBLIC_DIR / "p"
DB_PATH = PROJECT_ROOT / "data.db"
HTML_PATH = PUBLIC_DIR / "index.html"
JSON_PATH = PUBLIC_DIR / "data.json"
TOP_N = 500
GENDERS = ("female", "male")


def _scrape_gender(today: date, gender: str) -> list[Snapshot]:
    try:
        slugs = fetch_top_pornstars(limit=TOP_N, gender=gender)
    except Exception as exc:
        print(f"WARN: could not fetch {gender} top list: {exc}", file=sys.stderr)
        return []

    if not slugs:
        print(f"WARN: {gender} top list was empty", file=sys.stderr)
        return []

    print(f"got {len(slugs)} {gender} slugs", flush=True)

    rows: list[Snapshot] = []
    for rank, slug in enumerate(slugs, start=1):
        try:
            profile = fetch_profile(slug)
        except Exception as exc:
            print(f"WARN: skipping {gender}/{slug}: {exc}", file=sys.stderr)
            polite_sleep()
            continue

        local_photo = _download_avatar(profile.photo_url or "", AVATAR_DIR, slug) if profile.photo_url else None
        rows.append(Snapshot(
            snapshot_date=today,
            slug=slug,
            name=profile.name or slug,
            total_views=profile.total_views,
            rank=rank,
            gender=gender,
            photo_url=local_photo,
        ))
        polite_sleep()

    return rows


def main() -> int:
    today = date.today()
    print(f"[{today}] starting snapshot run", flush=True)

    all_rows: list[Snapshot] = []
    for gender in GENDERS:
        all_rows.extend(_scrape_gender(today, gender))

    if not all_rows:
        print("FATAL: no profiles parsed successfully for any gender", file=sys.stderr)
        return 1

    PUBLIC_DIR.mkdir(exist_ok=True)
    conn = init_db(DB_PATH)
    insert_snapshot(conn, all_rows)
    print(f"stored {len(all_rows)} rows total", flush=True)

    snapshots_df = load_all_snapshots(conn)
    render_treemap_page(snapshots_df, HTML_PATH)
    print(f"wrote {HTML_PATH}", flush=True)
    dump_json(snapshots_df, JSON_PATH)
    print(f"wrote {JSON_PATH}", flush=True)

    # Per-performer landing pages for EVERY slug ever seen — not just today's.
    # When a performer drops out of top-500, their page stays live (SEO continuity)
    # with the most recent data available for them.
    PERFORMER_DIR.mkdir(parents=True, exist_ok=True)
    all_slugs = snapshots_df["slug"].unique()
    written = 0
    for slug in all_slugs:
        try:
            render_performer_page(snapshots_df, slug=slug, output_path=PERFORMER_DIR / f"{slug}.html")
            written += 1
        except Exception as exc:
            print(f"  WARN: performer page failed for {slug}: {exc}", file=sys.stderr)
    print(f"wrote {written} performer pages under {PERFORMER_DIR}", flush=True)

    write_sitemap_and_robots(snapshots_df, public_dir=PUBLIC_DIR)
    print("wrote sitemap.xml + robots.txt", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
