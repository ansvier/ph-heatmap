"""One-off backfill: extract country from each performer's profile + UPDATE snapshots.

Reads unique slugs from snapshots. For each: fetch profile HTML, extract country,
UPDATE snapshots SET country = ? WHERE slug = ?.

By default, skips slugs whose country is already non-null. Pass --rescrape to
re-fetch everyone.

At the end, logs every Background nationality that was NOT in our dict — useful
for growing _NATIONALITY_TO_COUNTRY between runs.

Usage:
    ./venv/bin/python scripts/backfill_countries.py
    ./venv/bin/python scripts/backfill_countries.py --limit 3
    ./venv/bin/python scripts/backfill_countries.py --rescrape
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make project root importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from selectolax.parser import HTMLParser

from db import init_db
# Hoisted imports (the plan suggested these could be inline in the loop; Python
# caches imports so it's effectively free either way, but hoisting is cleaner).
from scraper import (
    _NATIONALITY_TO_COUNTRY,
    _PROFILE_URL_TEMPLATE,
    _fetch,
    extract_country,
    polite_sleep,
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=None, help="stop after N slugs (smoke test)")
    p.add_argument("--slug", type=str, default=None, help="backfill one specific slug")
    p.add_argument("--rescrape", action="store_true", help="re-fetch even if country already set")
    p.add_argument("--db", type=str, default="data.db")
    return p.parse_args()


def _slugs_to_backfill(conn, rescrape: bool, only_slug: str | None) -> list[str]:
    if only_slug:
        return [only_slug]
    if rescrape:
        rows = conn.execute("SELECT DISTINCT slug FROM snapshots").fetchall()
    else:
        rows = conn.execute(
            "SELECT DISTINCT slug FROM snapshots WHERE country IS NULL"
        ).fetchall()
    return sorted({r[0] for r in rows})


def main() -> int:
    args = _parse_args()
    conn = init_db(args.db)
    slugs = _slugs_to_backfill(conn, args.rescrape, args.slug)
    if args.limit is not None:
        slugs = slugs[: args.limit]
    print(f"backfilling country for {len(slugs)} slugs", flush=True)

    n_set = 0
    n_none = 0
    n_failed = 0
    unmapped_backgrounds: set[str] = set()

    for i, slug in enumerate(slugs, 1):
        try:
            # We need the raw HTML to also surface unmapped backgrounds —
            # fetch_profile returns parsed ProfileData (which has country
            # already), so we go one level lower here for diagnostics.
            body, _status = _fetch(_PROFILE_URL_TEMPLATE.format(slug=slug))
            country = extract_country(body)
            # Also log unmapped backgrounds for the diagnostics summary.
            tree = HTMLParser(body)
            for piece in tree.css(".infoPiece"):
                text = piece.text(strip=True)
                if text.startswith("Background:"):
                    raw = text[len("Background:"):].strip()
                    if raw and raw not in _NATIONALITY_TO_COUNTRY:
                        unmapped_backgrounds.add(raw)
        except Exception as exc:
            print(f"  {i}/{len(slugs)} {slug}: FAIL {exc}", flush=True)
            n_failed += 1
            polite_sleep()
            continue

        if country is None:
            n_none += 1
        else:
            conn.execute("UPDATE snapshots SET country = ? WHERE slug = ?", (country, slug))
            conn.commit()
            n_set += 1
        print(f"  {i}/{len(slugs)} {slug}: {country}", flush=True)

        if i % 50 == 0:
            print(f"  progress {i}/{len(slugs)}  set={n_set}  none={n_none}  failed={n_failed}", flush=True)
        polite_sleep()

    print(f"DONE  set={n_set}  none={n_none}  failed={n_failed}", flush=True)
    if unmapped_backgrounds:
        print(f"Unmapped Background nationalities encountered ({len(unmapped_backgrounds)}):", flush=True)
        for bg in sorted(unmapped_backgrounds):
            print(f"  - {bg}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
