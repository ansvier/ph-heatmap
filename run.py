from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from db import Snapshot, init_db, insert_snapshot, load_all_snapshots
from heatmap import dump_json, render_charts_page, render_performer_page, render_stats_page, render_treemap_page, write_sitemap_and_robots
from scraper import fetch_profile, fetch_top_pornstars, polite_sleep
from curl_cffi import requests as cffi_requests
import os
import time

_AVATAR_IMPERSONATE = os.environ.get("PH_IMPERSONATE", "chrome120")


def _download_avatar(remote_url: str, dest_dir: Path, slug: str, *, max_retries: int = 3) -> str | None:
    """Download an avatar image with retries. Returns public path or None on terminal failure."""
    if not remote_url:
        return None

    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            r = cffi_requests.get(remote_url, impersonate=_AVATAR_IMPERSONATE, timeout=15)
            r.raise_for_status()
            break
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries:
                time.sleep(0.5 * attempt)  # 0.5s, 1.0s
                continue
            print(f"  WARN: avatar failed for {slug} after {max_retries} tries: {exc}", file=sys.stderr)
            return None

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


def _backfill_missing_avatars(conn, today_str: str) -> int:
    """For performers in today's snapshot with NULL photo_url, refetch their
    profile and try to grab the avatar. Returns count of newly populated."""
    cur = conn.execute("""
        SELECT slug FROM snapshots
        WHERE snapshot_date = ? AND (photo_url IS NULL OR photo_url = '')
    """, (today_str,))
    slugs = [row[0] for row in cur]
    if not slugs:
        return 0
    print(f"backfilling avatars for {len(slugs)} performers", flush=True)

    filled = 0
    for slug in slugs:
        try:
            profile = fetch_profile(slug)
        except Exception:
            polite_sleep()
            continue
        if profile.photo_url:
            local = _download_avatar(profile.photo_url, AVATAR_DIR, slug)
            if local:
                conn.execute(
                    "UPDATE snapshots SET photo_url = ? WHERE snapshot_date = ? AND slug = ?",
                    (local, today_str, slug),
                )
                filled += 1
        polite_sleep()
    conn.commit()
    return filled

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

    # Backfill any avatars the main scrape missed (transient PH errors etc).
    filled = _backfill_missing_avatars(conn, today.isoformat())
    if filled:
        print(f"backfilled {filled} missing avatars", flush=True)

    snapshots_df = load_all_snapshots(conn)
    render_treemap_page(snapshots_df, HTML_PATH, default_mode="rising", canonical_path="/", seo_key="home")
    print(f"wrote {HTML_PATH}", flush=True)

    # Per-mode landing pages — shareable URLs that open directly on the mode.
    for mode in ("rising", "gems", "celebs"):
        mode_dir = PUBLIC_DIR / mode
        mode_dir.mkdir(exist_ok=True)
        render_treemap_page(
            snapshots_df,
            mode_dir / "index.html",
            default_mode=mode,
            canonical_path=f"/{mode}",
            seo_key=mode,
        )
        print(f"wrote /{mode}/index.html", flush=True)
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

    # /stats summary page — single-image hook for social shares (female-focused).
    stats_dir = PUBLIC_DIR / "stats"
    stats_dir.mkdir(exist_ok=True)
    render_stats_page(snapshots_df, stats_dir / "index.html")
    print(f"wrote /stats/index.html", flush=True)

    # /charts alphabetical performer index — search + gender filter.
    charts_dir = PUBLIC_DIR / "charts"
    charts_dir.mkdir(exist_ok=True)
    render_charts_page(snapshots_df, charts_dir / "index.html")
    print(f"wrote /charts/index.html", flush=True)

    write_sitemap_and_robots(snapshots_df, public_dir=PUBLIC_DIR)
    print("wrote sitemap.xml + robots.txt", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
