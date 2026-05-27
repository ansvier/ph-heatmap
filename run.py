from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from db import Snapshot, init_db, insert_snapshot, load_all_snapshots
from heatmap import dump_json, render_treemap_page
from scraper import fetch_profile, fetch_top_pornstars, polite_sleep

PROJECT_ROOT = Path(__file__).parent
PUBLIC_DIR = PROJECT_ROOT / "public"
DB_PATH = PROJECT_ROOT / "data.db"
HTML_PATH = PUBLIC_DIR / "index.html"
JSON_PATH = PUBLIC_DIR / "data.json"
TOP_N = 50
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

        rows.append(Snapshot(
            snapshot_date=today,
            slug=slug,
            name=profile.name or slug,
            total_views=profile.total_views,
            rank=rank,
            gender=gender,
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
