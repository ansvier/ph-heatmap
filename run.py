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


def main() -> int:
    today = date.today()
    print(f"[{today}] starting snapshot run", flush=True)

    try:
        slugs = fetch_top_pornstars(limit=TOP_N)
    except Exception as exc:
        print(f"FATAL: could not fetch top list: {exc}", file=sys.stderr)
        return 1

    if not slugs:
        print("FATAL: top list was empty", file=sys.stderr)
        return 1

    print(f"got {len(slugs)} slugs", flush=True)

    rows: list[Snapshot] = []
    for rank, slug in enumerate(slugs, start=1):
        try:
            profile = fetch_profile(slug)
        except Exception as exc:
            print(f"WARN: skipping {slug}: {exc}", file=sys.stderr)
            polite_sleep()
            continue

        rows.append(Snapshot(
            snapshot_date=today,
            slug=slug,
            name=profile.name or slug,
            total_views=profile.total_views,
            rank=rank,
        ))
        polite_sleep()

    if not rows:
        print("FATAL: no profiles parsed successfully", file=sys.stderr)
        return 1

    PUBLIC_DIR.mkdir(exist_ok=True)
    conn = init_db(DB_PATH)
    insert_snapshot(conn, rows)
    print(f"stored {len(rows)} rows", flush=True)

    snapshots_df = load_all_snapshots(conn)
    render_treemap_page(snapshots_df, HTML_PATH)
    print(f"wrote {HTML_PATH}", flush=True)
    dump_json(snapshots_df, JSON_PATH)
    print(f"wrote {JSON_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
