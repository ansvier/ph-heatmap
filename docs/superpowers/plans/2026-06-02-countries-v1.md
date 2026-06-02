# Countries v1 — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract performer country from PH profile pages, persist on `snapshots`, render `/country/<slug>/` per-country landing pages + `/countries/` index, cross-link from `/p/<slug>`, populate via one-off backfill.

**Architecture:** New `country` column on the existing `snapshots` table (denormalized like `gender`). Scraper `parse_profile` extended to extract from `Birth Place:` infoPiece, with `Background:` nationality as fallback. Render reuses the established treemap helpers. Backfill is a one-off script (not part of daily-scrape). 

**Tech Stack:** Python 3.13, SQLite (stdlib), pandas, selectolax (existing), curl-cffi (existing), plotly (existing), pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-02-countries-v1-design.md`

---

## File map

| Path | Purpose | Tasks |
|---|---|---|
| `scraper.py` | `_NATIONALITY_TO_COUNTRY`, `_COUNTRY_ALIASES`, `_canonicalize_country`, `extract_country`; extend `ProfileData` + `parse_profile` | Task 1 |
| `db.py` | `country` field on `Snapshot`; ALTER TABLE migration; insert/load handle new column | Task 2 |
| `run.py` | `_scrape_gender` passes country from ProfileData → Snapshot; new countries render block | Tasks 3, 10 |
| `scripts/backfill_countries.py` | One-off script populating `country` for all existing slugs | Task 4 |
| `heatmap.py` | `page_type="country"`; `_COUNTRY_MIN_PERFORMERS`; `_COUNTRY_PAGE_TEMPLATE`; `render_country_page`; `render_countries_index`; cross-link in `render_performer_page`; `_NAV_ITEMS` entry; sitemap extension | Tasks 5–9 |
| `README.md` | New Countries subsection | Task 11 |
| `tests/test_scraper.py`, `tests/test_db.py`, `tests/test_heatmap.py` | New tests across all of the above | within each task |

No new packages.

---

### Task 1: `extract_country` + ProfileData extension

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/scraper.py`
- Modify: `/Users/ansvier/ph-heatmap/tests/test_scraper.py`

- [ ] **Step 1: Write the failing tests**

Append to `/Users/ansvier/ph-heatmap/tests/test_scraper.py`:

```python
from scraper import extract_country, _canonicalize_country


def test_extract_country_from_birth_place_with_full_address():
    """Birth Place like 'Chicago, Illinois, United States of America' → 'United States'."""
    html = '<html><body><div class="infoPiece">Birth Place:Chicago, Illinois, United States of America</div></body></html>'
    assert extract_country(html) == "United States"


def test_extract_country_from_birth_place_country_only():
    """Birth Place 'Russia' → 'Russia' (no comma split needed)."""
    html = '<html><body><div class="infoPiece">Birth Place:Russia</div></body></html>'
    assert extract_country(html) == "Russia"


def test_extract_country_falls_back_to_background_nationality():
    """When Birth Place missing but Background is a known nationality → mapped country."""
    html = '<html><body><div class="infoPiece">Background:Italian</div></body></html>'
    assert extract_country(html) == "Italy"


def test_extract_country_birth_place_wins_over_background():
    """If both present, Birth Place takes priority."""
    html = (
        '<html><body>'
        '<div class="infoPiece">Birth Place:Russia</div>'
        '<div class="infoPiece">Background:American</div>'
        '</body></html>'
    )
    assert extract_country(html) == "Russia"


def test_extract_country_returns_none_when_both_absent():
    """No Birth Place, no Background → None."""
    html = '<html><body><div class="infoPiece">Career Status:Active</div></body></html>'
    assert extract_country(html) is None


def test_extract_country_returns_none_when_background_unmapped():
    """Background present but nationality not in our dict → None (not raw value)."""
    html = '<html><body><div class="infoPiece">Background:Martian</div></body></html>'
    assert extract_country(html) is None


def test_canonicalize_country_collapses_usa_variants():
    assert _canonicalize_country("United States of America") == "United States"
    assert _canonicalize_country("USA") == "United States"
    assert _canonicalize_country("U.S.A.") == "United States"


def test_canonicalize_country_collapses_uk_variants():
    assert _canonicalize_country("United Kingdom") == "United Kingdom"
    assert _canonicalize_country("UK") == "United Kingdom"
    assert _canonicalize_country("Great Britain") == "United Kingdom"
    assert _canonicalize_country("England") == "United Kingdom"


def test_canonicalize_country_passes_through_unknown():
    assert _canonicalize_country("Russia") == "Russia"
    assert _canonicalize_country("Belarus") == "Belarus"


def test_parse_profile_includes_country():
    """parse_profile now returns ProfileData with the country field populated."""
    from scraper import parse_profile
    html = (
        '<html><body>'
        '<h1>Test Performer</h1>'
        '<span class="videoViews" data-title="Video views: 1,234,567"></span>'
        '<div class="infoPiece">Birth Place:Russia</div>'
        '</body></html>'
    )
    result = parse_profile(html)
    assert result.country == "Russia"
```

- [ ] **Step 2: Run tests, confirm RED**

```bash
cd /Users/ansvier/ph-heatmap
./venv/bin/pytest tests/test_scraper.py -k "extract_country or canonicalize_country or parse_profile_includes_country" -v
```

Expected: ImportError (`extract_country`, `_canonicalize_country` don't exist) and `AttributeError: 'ProfileData' object has no attribute 'country'`.

- [ ] **Step 3: Add the constants + helpers**

In `/Users/ansvier/ph-heatmap/scraper.py`, near other module constants (after the existing `_TOP_LIST_URL_TEMPLATE`), add:

```python
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


def extract_country(html: str) -> str | None:
    """Extract performer country from a PH profile page.

    Strategy:
      1. Birth Place infoPiece → take last comma-segment → canonicalize.
      2. Background infoPiece → map nationality via _NATIONALITY_TO_COUNTRY.
      3. Return None if neither produces a value.
    """
    tree = HTMLParser(html)
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
```

- [ ] **Step 4: Extend `ProfileData` and `parse_profile`**

In `/Users/ansvier/ph-heatmap/scraper.py`, find the `ProfileData` dataclass (line 14–18):

```python
@dataclass(frozen=True)
class ProfileData:
    name: str
    total_views: int
    photo_url: str | None = None
```

Add the `country` field:

```python
@dataclass(frozen=True)
class ProfileData:
    name: str
    total_views: int
    photo_url: str | None = None
    country: str | None = None
```

Find `parse_profile` (line 52). Add a `country = extract_country(html)` call and pass it to the `ProfileData(...)` constructor at the end. The exact patch:

```python
def parse_profile(html: str) -> ProfileData:
    """Extract display name, Video Views count, and avatar URL from a profile page."""
    tree = HTMLParser(html)

    name_node = tree.css_first("h1")
    name = name_node.text(strip=True) if name_node else ""

    total_views = _extract_video_views(tree)
    photo_url = _extract_photo_url(tree)
    country = extract_country(html)
    return ProfileData(name=name, total_views=total_views, photo_url=photo_url, country=country)
```

- [ ] **Step 5: Confirm GREEN**

```bash
./venv/bin/pytest tests/test_scraper.py -k "extract_country or canonicalize_country or parse_profile_includes_country" -v
```

Expected: 10 passed.

- [ ] **Step 6: Full suite (regression check)**

```bash
./venv/bin/pytest -q
```

Expected: 70 + 10 = 80 passed. No regressions in existing parse_profile tests.

- [ ] **Step 7: Commit**

```bash
git add scraper.py tests/test_scraper.py
git commit -m "$(cat <<'EOF'
feat(scraper): extract_country + ProfileData.country field

Birth Place infoPiece (primary) + Background nationality (fallback)
populate a canonical country name. _NATIONALITY_TO_COUNTRY covers ~40
common nationalities; _COUNTRY_ALIASES collapses USA/UK variants.
Unmapped values resolve to None. ProfileData and parse_profile now
return the country alongside name/views/photo.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `country` column on `snapshots`

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/db.py`
- Modify: `/Users/ansvier/ph-heatmap/tests/test_db.py`

- [ ] **Step 1: Write the failing tests**

Append to `/Users/ansvier/ph-heatmap/tests/test_db.py`:

```python
def test_init_db_adds_country_column_migration(tmp_path):
    """init_db creates snapshots with a country column (TEXT, nullable)."""
    db_path = tmp_path / "test.db"
    conn = init_db(db_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(snapshots)")}
    assert "country" in cols, f"expected 'country' in columns; got {cols}"


def test_insert_and_load_snapshot_with_country(tmp_path):
    """Snapshot.country round-trips through the DB."""
    from datetime import date
    conn = init_db(tmp_path / "test.db")
    insert_snapshot(conn, [
        Snapshot(
            snapshot_date=date(2026, 6, 2), slug="lana-rhoades", name="Lana Rhoades",
            total_views=2_080_000_000, rank=2, gender="female",
            photo_url=None, country="United States",
        ),
        Snapshot(
            snapshot_date=date(2026, 6, 2), slug="eva-elfie", name="Eva Elfie",
            total_views=1_100_000_000, rank=8, gender="female",
            photo_url=None, country=None,  # missing country path
        ),
    ])
    df = load_all_snapshots(conn)
    assert len(df) == 2
    lana = df[df["slug"] == "lana-rhoades"].iloc[0]
    assert lana["country"] == "United States"
    eva = df[df["slug"] == "eva-elfie"].iloc[0]
    assert pd.isna(eva["country"])
```

- [ ] **Step 2: Confirm RED**

```bash
./venv/bin/pytest tests/test_db.py -k "country" -v
```

Expected: `AttributeError: type object 'Snapshot' has no field 'country'` or similar.

- [ ] **Step 3: Extend `Snapshot` dataclass**

In `/Users/ansvier/ph-heatmap/db.py`, find the `Snapshot` dataclass (lines 11–19) and add the `country` field:

```python
@dataclass(frozen=True)
class Snapshot:
    snapshot_date: date
    slug: str
    name: str
    total_views: int
    rank: int
    gender: str  # 'female' | 'male'
    photo_url: str | None = None
    country: str | None = None
```

- [ ] **Step 4: Add the migration in `init_db`**

In `init_db`, after the existing `Migration 1b: photo_url column` block, add:

```python
    # Migration 1c: country column.
    if "country" not in cols:
        conn.execute("ALTER TABLE snapshots ADD COLUMN country TEXT")
        conn.commit()
        cols.add("country")
```

- [ ] **Step 5: Update `insert_snapshot`**

Find `insert_snapshot` (line 106). Update the SQL and the row tuple builder:

```python
def insert_snapshot(conn: sqlite3.Connection, rows: list[Snapshot]) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO snapshots "
        "(snapshot_date, slug, name, total_views, rank, gender, photo_url, country) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (r.snapshot_date.isoformat(), r.slug, r.name, r.total_views, r.rank,
             r.gender, r.photo_url, r.country)
            for r in rows
        ],
    )
    conn.commit()
```

- [ ] **Step 6: Update `load_all_snapshots`**

Find `load_all_snapshots` (line 119). Update the SELECT:

```python
def load_all_snapshots(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query(
        "SELECT snapshot_date, slug, name, total_views, rank, gender, photo_url, country FROM snapshots",
        conn,
    )
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    return df
```

- [ ] **Step 7: Confirm GREEN + full suite**

```bash
./venv/bin/pytest tests/test_db.py -k "country" -v
./venv/bin/pytest -q
```

Expected: targeted tests pass; full suite at 82 (80 + 2 new).

- [ ] **Step 8: Commit**

```bash
git add db.py tests/test_db.py
git commit -m "$(cat <<'EOF'
feat(db): country column on snapshots + Snapshot.country field

Adds 'country TEXT' column via ALTER TABLE migration (idempotent —
checks PRAGMA table_info before adding). Snapshot dataclass gains a
country field defaulting to None. insert_snapshot/load_all_snapshots
handle the new column transparently.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `run.py` wiring — pass country from `ProfileData` to `Snapshot`

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/run.py`

- [ ] **Step 1: Find the `_scrape_gender` function**

Open `/Users/ansvier/ph-heatmap/run.py` and grep for `_scrape_gender`. It's the function that fetches each performer's profile and builds `Snapshot` instances. Look for the line where it constructs `Snapshot(...)` — the keyword args should currently include `name`, `total_views`, `photo_url`, etc. but NOT `country`.

- [ ] **Step 2: Add `country=profile.country` to the Snapshot constructor call**

The exact change: in `_scrape_gender` (or wherever `Snapshot(...)` is built from a `ProfileData` instance), add `country=profile.country` as a keyword argument. For example, if the existing line reads:

```python
            Snapshot(
                snapshot_date=today,
                slug=slug,
                name=profile.name,
                total_views=profile.total_views,
                rank=rank,
                gender=gender,
                photo_url=profile.photo_url,
            )
```

Change to:

```python
            Snapshot(
                snapshot_date=today,
                slug=slug,
                name=profile.name,
                total_views=profile.total_views,
                rank=rank,
                gender=gender,
                photo_url=profile.photo_url,
                country=profile.country,
            )
```

- [ ] **Step 3: Smoke check (no PH hits — just import)**

```bash
cd /Users/ansvier/ph-heatmap
./venv/bin/python -c "import run; print('run.py imports cleanly')"
```

Expected: prints "run.py imports cleanly" with no errors.

- [ ] **Step 4: Commit**

```bash
git add run.py
git commit -m "$(cat <<'EOF'
feat(run): pass country from ProfileData into Snapshot

Daily-scrape now persists the country extracted by parse_profile.
Snapshots written from today forward include country; existing rows
will be populated by the backfill script (Task 4).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: `scripts/backfill_countries.py`

**Files:**
- Create: `/Users/ansvier/ph-heatmap/scripts/backfill_countries.py`

Operational one-off script. Smoke against 3 slugs before the full run.

- [ ] **Step 1: Create the script**

Create `/Users/ansvier/ph-heatmap/scripts/backfill_countries.py`:

```python
"""One-off backfill: extract country from each performer's profile + UPDATE snapshots.

Reads unique slugs from snapshots. For each: fetch_profile(slug), extract country,
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

from db import init_db
from scraper import _NATIONALITY_TO_COUNTRY, fetch_profile, polite_sleep
from selectolax.parser import HTMLParser


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
            from scraper import _fetch, _PROFILE_URL_TEMPLATE, extract_country
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
```

- [ ] **Step 2: Verify help works**

```bash
cd /Users/ansvier/ph-heatmap
./venv/bin/python scripts/backfill_countries.py --help
```

Expected: argparse usage output, no import errors.

- [ ] **Step 3: Smoke run on a single known slug**

```bash
./venv/bin/python scripts/backfill_countries.py --slug lana-rhoades --rescrape
```

Expected: prints `1/1 lana-rhoades: ...` (no FAIL), then `DONE  set=1  none=0  failed=0`. Then verify the DB:

```bash
./venv/bin/python -c "
import sqlite3
conn = sqlite3.connect('data.db')
row = conn.execute(\"SELECT DISTINCT country FROM snapshots WHERE slug = 'lana-rhoades'\").fetchone()
print('lana-rhoades country:', row)
"
```

Expected: `('United States',)` or similar non-None value.

- [ ] **Step 4: Smoke run with --limit 5**

```bash
./venv/bin/python scripts/backfill_countries.py --limit 5 --rescrape
```

Expected: 5 slugs processed in ~7 seconds (1.5s × 5 polite-sleep + small fetch overhead). Most should show set=K none=0 failed=0.

If FAIL appears for most slugs → STOP and report. PH may be blocking or our parsing has a bug.

- [ ] **Step 5: Commit the script**

```bash
git add scripts/backfill_countries.py
git commit -m "$(cat <<'EOF'
feat(scripts): backfill_countries.py — one-off country population

Iterates unique slugs from snapshots, fetches each profile, extracts
country via extract_country(), UPDATEs snapshots SET country=? WHERE
slug=?. Skip-recent semantics by default (--rescrape for full re-run).
Diagnostics summary logs unmapped Background nationalities at the end.

Not added to run.py — daily-scrape going forward will populate country
via Task 3 wiring. This script is the one-time backfill for the ~870
existing slugs.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 6: Full pytest still passes**

```bash
./venv/bin/pytest -q
```

Expected: still 82 (no test changes; just confirming no regressions from the import-time side-effects of running the script).

---

### Task 5: Extend `_OG_TYPE_BY_PAGE_TYPE` for `"country"`

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/heatmap.py`
- Modify: `/Users/ansvier/ph-heatmap/tests/test_heatmap.py`

Tiny task. One dict entry + Literal update + 1 test.

- [ ] **Step 1: Write failing test**

Append to `tests/test_heatmap.py`:

```python
def test_render_seo_head_supports_country_page_type():
    """page_type='country' maps to og:type='website'."""
    head = _render_seo_head(
        page_type="country",
        title="Top Russian Performers — HotMap",
        description="…",
        canonical_url="https://hotmap.cam/country/russia/",
    )
    assert 'property="og:type" content="website"' in head
```

- [ ] **Step 2: Confirm RED**

```bash
./venv/bin/pytest tests/test_heatmap.py::test_render_seo_head_supports_country_page_type -v
```

Expected: `KeyError: 'country'`.

- [ ] **Step 3: Add the entry**

In `heatmap.py`, find `_OG_TYPE_BY_PAGE_TYPE`. It currently has 6 entries (home/mode/stats/charts/performer/category). Add the seventh:

```python
_OG_TYPE_BY_PAGE_TYPE = {
    "home": "website",
    "mode": "website",
    "stats": "article",
    "charts": "website",
    "performer": "profile",
    "category": "website",
    "country": "website",
}
```

Update the `Literal` annotation on `_render_seo_head`:

```python
def _render_seo_head(
    *,
    page_type: Literal["home", "mode", "stats", "charts", "performer", "category", "country"],
    ...
```

- [ ] **Step 4: Confirm GREEN + full suite**

```bash
./venv/bin/pytest -q
```

Expected: 83 passed (82 + 1 new).

- [ ] **Step 5: Commit**

```bash
git add heatmap.py tests/test_heatmap.py
git commit -m "$(cat <<'EOF'
feat(seo): page_type='country' for /country/<slug>/ and /countries/

og:type='website'; downstream JSON-LD is CollectionPage via callers'
extra_jsonld.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: `render_country_page` + `_COUNTRY_PAGE_TEMPLATE` + threshold

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/heatmap.py`
- Modify: `/Users/ansvier/ph-heatmap/tests/test_heatmap.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_heatmap.py`:

```python
def _country_snapshots_fixture() -> pd.DataFrame:
    """Three days of history; 3 performers with country='Russia', 1 with 'Italy'."""
    rows = []
    for d in (date(2026, 5, 26), date(2026, 5, 27), date(2026, 5, 28)):
        # Russia: 3 performers
        for slug, base_views in [("ru1", 100_000_000), ("ru2", 80_000_000), ("ru3", 60_000_000)]:
            rows.append({
                "snapshot_date": pd.Timestamp(d), "slug": slug, "name": slug.upper(),
                "total_views": base_views + (d.toordinal() - date(2026, 5, 26).toordinal()) * 10_000,
                "rank": 1, "gender": "female", "country": "Russia",
            })
        # Italy: 1 performer
        rows.append({
            "snapshot_date": pd.Timestamp(d), "slug": "it1", "name": "IT1",
            "total_views": 50_000_000 + (d.toordinal() - date(2026, 5, 26).toordinal()) * 5_000,
            "rank": 4, "gender": "female", "country": "Italy",
        })
    return pd.DataFrame(rows)


def test_render_country_page_writes_html(tmp_path):
    """render_country_page emits a single-treemap page filtered to one country."""
    df = _country_snapshots_fixture()
    out = tmp_path / "russia.html"
    render_country_page(df, "Russia", out)
    assert out.exists()
    content = out.read_text()

    assert "<html" in content.lower()
    assert "Russia" in content
    assert "Top Russian" in content or "Top Russia" in content  # title pattern
    assert 'rel="canonical" href="https://hotmap.cam/country/russia/"' in content
    assert 'property="og:type" content="website"' in content
    # Plotly bundle embedded
    assert "plotly" in content.lower()
    # JSON-LD
    blocks = _extract_jsonld_blocks(content)
    types = {b.get("@type") for b in blocks}
    assert "CollectionPage" in types and "BreadcrumbList" in types


def test_render_country_page_raises_when_no_performers(tmp_path):
    df = _country_snapshots_fixture()
    with pytest.raises(ValueError, match="No performers for country"):
        render_country_page(df, "Nonexistentland", tmp_path / "out.html")


def test_country_min_performers_constant_is_5():
    from heatmap import _COUNTRY_MIN_PERFORMERS
    assert _COUNTRY_MIN_PERFORMERS == 5
```

- [ ] **Step 2: Confirm RED**

```bash
./venv/bin/pytest tests/test_heatmap.py -k "render_country_page or country_min_performers" -v
```

Expected: 3 failures — symbols don't exist.

- [ ] **Step 3: Add the constant, template, and render function**

In `heatmap.py`, add near other `render_*` helpers (look for `render_categories_treemap` as the closest neighbor). Add:

```python
_COUNTRY_MIN_PERFORMERS = 5  # countries below this don't get a /country/<slug>/ page


_COUNTRY_PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
{seo_head}
  <link rel="icon" type="image/svg+xml" href="/favicon.svg">
  <link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png">
  <link rel="icon" type="image/png" sizes="16x16" href="/favicon-16.png">
  <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
  <link rel="shortcut icon" href="/favicon.ico">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <style>
    :root {{
      --brand-orange: #ff9000;
      --bg: #0a0a0a;
      --fg: #f5f5f5;
      --muted: #9a9a9a;
      --rule: #1f1f1f;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ font-family: 'Inter', sans-serif; }}
    body {{ max-width: 1200px; margin: 0 auto; padding: 32px 16px 56px; color: var(--fg); background: var(--bg); line-height: 1.5; }}
{nav_css}
    h1 {{ font-size: 28px; font-weight: 800; margin: 0 0 8px; }}
    .subtitle {{ color: var(--muted); margin: 0 0 24px; }}
    .empty-state {{ padding: 80px 0; text-align: center; color: var(--muted); }}
    footer {{ margin-top: 48px; padding-top: 24px; border-top: 1px solid var(--rule); color: var(--muted); font-size: 13px; }}
    footer a {{ color: var(--muted); text-decoration: underline; }}
  </style>
</head>
<body>
{top_nav}
<h1>Top {country_name} performers</h1>
<p class="subtitle">{n_performers} performers tracked · Updated {last_updated} UTC</p>
{top_perf_card}
{treemap}
<footer>
  <p>HotMap is an independent project. <a href="/">Back to homepage</a>.</p>
</footer>
</body>
</html>
"""


def render_country_page(
    snapshots: pd.DataFrame,
    country_name: str,
    output_path: Path | str,
) -> None:
    """Render /country/<slug>/index.html — top performers from one country.

    Tile size = % growth (same metric as homepage), color = acceleration percentile.
    Spike of the Day card surfaces the biggest-momentum performer in the country.
    Raises ValueError when no performers match the country (caller in run.py
    should treat as 'skip render').
    """
    in_country = snapshots[snapshots["country"] == country_name].copy()
    if in_country.empty:
        raise ValueError(f"No performers for country {country_name!r}")

    in_country["snapshot_date"] = pd.to_datetime(in_country["snapshot_date"])
    latest_date = in_country["snapshot_date"].max()
    n_performers = int(in_country[in_country["snapshot_date"] == latest_date]["slug"].nunique())

    slug = _normalize_category_slug(country_name)
    canonical_url = f"https://hotmap.cam/country/{slug}/"
    title = f"Top {country_name} Performers — HotMap"
    description = (
        f"Top {country_name} pornstars ranked by view-growth momentum. "
        f"{n_performers} performers tracked. Daily heatmap, updated automatically."
    )
    collection_jsonld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": title,
        "url": canonical_url,
        "description": description,
    }
    breadcrumbs = [
        ("HotMap", "https://hotmap.cam/"),
        ("Countries", "https://hotmap.cam/countries/"),
        (country_name, canonical_url),
    ]
    seo_head = _render_seo_head(
        page_type="country",
        title=title,
        description=description,
        canonical_url=canonical_url,
        og_image_url=None,
        extra_jsonld=[collection_jsonld],
        breadcrumbs=breadcrumbs,
    )

    # Build treemap from this country's window-growth cohort.
    window = compute_window_growth(in_country, window_days=1)
    cohort = window.dropna(subset=["growth_pct"]).sort_values("total_views", ascending=False).head(50)

    has_visible_tiles = not cohort.empty and (cohort["prev_views"] >= 1_000_000).any()
    if not has_visible_tiles:
        treemap_html = '<div class="empty-state">Not enough history yet — check back tomorrow.</div>'
    else:
        treemap_html = _build_treemap_figure(cohort, window_days=1).to_html(include_plotlyjs="cdn", full_html=False)

    top_perf_card = _build_top_performer_card(
        in_country, gender_key="all", gender_filter=None, mode="celebs", is_default=True,
        label_override=f"Top from {country_name}",
    )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_COUNTRY_PAGE_TEMPLATE.format(
        seo_head=seo_head,
        nav_css=_TOP_NAV_CSS,
        top_nav=_top_nav("countries"),
        country_name=_html.escape(country_name),
        n_performers=n_performers,
        top_perf_card=top_perf_card,
        treemap=treemap_html,
        last_updated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
    ), encoding="utf-8")
```

- [ ] **Step 4: Confirm GREEN**

```bash
./venv/bin/pytest tests/test_heatmap.py -k "render_country_page or country_min_performers" -v
```

Expected: 3 passed.

- [ ] **Step 5: Full suite**

```bash
./venv/bin/pytest -q
```

Expected: 86 passed (83 + 3 new).

- [ ] **Step 6: Commit**

```bash
git add heatmap.py tests/test_heatmap.py
git commit -m "$(cat <<'EOF'
feat(heatmap): render_country_page for /country/<slug>/

Single-treemap per-country page reusing _build_treemap_figure (size
= % growth, color = acceleration percentile, same as homepage) and
_build_top_performer_card for the Spike of the Day. No gender/window
toggles — country itself is the filter. Empty cohort raises ValueError;
sparse-baseline cohort shows the empty-state placeholder.

Also introduces _COUNTRY_MIN_PERFORMERS = 5 (consumed by Tasks 7-9).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: `render_countries_index`

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/heatmap.py`
- Modify: `/Users/ansvier/ph-heatmap/tests/test_heatmap.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_heatmap.py`:

```python
def test_render_countries_index_lists_qualifying_countries(tmp_path):
    """Countries with >= _COUNTRY_MIN_PERFORMERS get listed; others omitted."""
    rows = []
    # Russia: 6 performers (qualifying)
    for i in range(6):
        rows.append({
            "snapshot_date": pd.Timestamp("2026-06-02"), "slug": f"ru{i}", "name": f"RU{i}",
            "total_views": 100_000_000, "rank": 1, "gender": "female", "country": "Russia",
        })
    # Italy: 5 performers (just-qualifying)
    for i in range(5):
        rows.append({
            "snapshot_date": pd.Timestamp("2026-06-02"), "slug": f"it{i}", "name": f"IT{i}",
            "total_views": 80_000_000, "rank": 1, "gender": "female", "country": "Italy",
        })
    # Estonia: 2 performers (below threshold — must be excluded)
    for i in range(2):
        rows.append({
            "snapshot_date": pd.Timestamp("2026-06-02"), "slug": f"ee{i}", "name": f"EE{i}",
            "total_views": 50_000_000, "rank": 1, "gender": "female", "country": "Estonia",
        })
    df = pd.DataFrame(rows)
    out = tmp_path / "index.html"
    render_countries_index(df, out)
    content = out.read_text()

    # Qualifying countries present
    assert '<a href="/country/russia/"' in content
    assert "Russia" in content
    assert '<a href="/country/italy/"' in content
    assert "Italy" in content
    # Counts visible
    assert "6" in content
    assert "5" in content
    # Below-threshold absent
    assert "Estonia" not in content
    assert "/country/estonia/" not in content
    # SEO + breadcrumbs
    assert 'rel="canonical" href="https://hotmap.cam/countries/"' in content
    blocks = _extract_jsonld_blocks(content)
    types = {b.get("@type") for b in blocks}
    assert "CollectionPage" in types and "BreadcrumbList" in types
```

- [ ] **Step 2: Confirm RED**

```bash
./venv/bin/pytest tests/test_heatmap.py::test_render_countries_index_lists_qualifying_countries -v
```

Expected: `ImportError: cannot import name 'render_countries_index'`.

- [ ] **Step 3: Add the index template + function**

In `heatmap.py`, near `render_country_page`, add `_COUNTRIES_INDEX_TEMPLATE` and `render_countries_index`. The template reuses the chrome from the existing `_CATEGORIES_INDEX_TEMPLATE`. To avoid copy-paste drift, prefer:

```python
_COUNTRIES_INDEX_TEMPLATE = _CATEGORIES_INDEX_TEMPLATE  # same chrome — only the rendered list content differs
```

(If the categories template uses `{rows_html}` and `{n_categories}` placeholders, the country index will substitute the same placeholder names with country values — the template doesn't care semantically.)

Wait — that's brittle. Better to define a fresh template that uses country-specific labels in the body, but the same chrome. Add a dedicated:

```python
_COUNTRIES_INDEX_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
{seo_head}
  <link rel="icon" type="image/svg+xml" href="/favicon.svg">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <style>
    :root {{ --brand-orange: #ff9000; --bg: #0a0a0a; --fg: #f5f5f5; --muted: #9a9a9a; --rule: #1f1f1f; }}
    * {{ box-sizing: border-box; }}
    html, body {{ font-family: 'Inter', sans-serif; }}
    body {{ max-width: 1200px; margin: 0 auto; padding: 32px 16px 56px; color: var(--fg); background: var(--bg); line-height: 1.5; }}
{nav_css}
    h1 {{ font-size: 28px; font-weight: 800; margin: 0 0 8px; }}
    .subtitle {{ color: var(--muted); margin: 0 0 24px; }}
    .cat-list {{ list-style: none; padding: 0; columns: 3; column-gap: 32px; }}
    .cat-list li {{ padding: 4px 0; break-inside: avoid; }}
    .cat-list a {{ color: var(--fg); text-decoration: none; font-weight: 600; }}
    .cat-list a:hover {{ color: var(--brand-orange); }}
    .cat-count {{ color: var(--muted); font-size: 13px; font-weight: 400; }}
    @media (max-width: 720px) {{ .cat-list {{ columns: 2; }} }}
    @media (max-width: 480px) {{ .cat-list {{ columns: 1; }} }}
    footer {{ margin-top: 48px; padding-top: 24px; border-top: 1px solid var(--rule); color: var(--muted); font-size: 13px; }}
    footer a {{ color: var(--muted); text-decoration: underline; }}
  </style>
</head>
<body>
{top_nav}
<h1>All countries</h1>
<p class="subtitle">{n_countries} countries with 5 or more tracked performers · Updated {last_updated} UTC</p>
<ul class="cat-list">
{rows_html}
</ul>
<footer>
  <p>HotMap is an independent project. <a href="/">Back to homepage</a>.</p>
</footer>
</body>
</html>
"""


def render_countries_index(
    snapshots: pd.DataFrame,
    output_path: Path | str,
) -> None:
    """Render /countries/index.html — alphabetical list of qualifying countries."""
    df = snapshots[snapshots["country"].notna()].copy()
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    latest_date = df["snapshot_date"].max()
    today = df[df["snapshot_date"] == latest_date]

    counts = today.groupby("country")["slug"].nunique().reset_index(name="n")
    qualifying = counts[counts["n"] >= _COUNTRY_MIN_PERFORMERS].sort_values("country")

    canonical_url = "https://hotmap.cam/countries/"
    title = "All Countries — HotMap"
    description = f"Alphabetical index of all {len(qualifying)} countries with ≥5 tracked performers on HotMap."
    collection_jsonld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": title,
        "url": canonical_url,
        "description": description,
    }
    breadcrumbs = [
        ("HotMap", "https://hotmap.cam/"),
        ("Countries", canonical_url),
    ]
    seo_head = _render_seo_head(
        page_type="country",
        title=title,
        description=description,
        canonical_url=canonical_url,
        og_image_url=None,
        extra_jsonld=[collection_jsonld],
        breadcrumbs=breadcrumbs,
    )

    rows_html = "\n".join(
        f'<li><a href="/country/{_normalize_category_slug(row.country)}/">{_html.escape(row.country)}</a> '
        f'<span class="cat-count">({int(row.n)} performers)</span></li>'
        for row in qualifying.itertuples(index=False)
    )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_COUNTRIES_INDEX_TEMPLATE.format(
        seo_head=seo_head,
        nav_css=_TOP_NAV_CSS,
        top_nav=_top_nav("countries"),
        n_countries=len(qualifying),
        rows_html=rows_html,
        last_updated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
    ), encoding="utf-8")
```

- [ ] **Step 4: Confirm GREEN + full suite**

```bash
./venv/bin/pytest tests/test_heatmap.py::test_render_countries_index_lists_qualifying_countries -v
./venv/bin/pytest -q
```

Expected: 87 passed (86 + 1 new).

- [ ] **Step 5: Commit**

```bash
git add heatmap.py tests/test_heatmap.py
git commit -m "$(cat <<'EOF'
feat(heatmap): render_countries_index for /countries/

Alphabetical list of every country with >= _COUNTRY_MIN_PERFORMERS
performers in today's snapshot. Each entry links to /country/<slug>/.
Below-threshold countries omitted. SEO via page_type='country'.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Cross-link block on `/p/<slug>`

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/heatmap.py` (`render_performer_page`)
- Modify: `/Users/ansvier/ph-heatmap/tests/test_heatmap.py`

`render_performer_page` already accepts `categories` kwarg. Add an analogous `countries: set[str] | None = None` kwarg that gates the country block to qualifying countries only.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_heatmap.py`:

```python
def test_performer_page_emits_country_cross_link(tmp_path):
    """When performer has a country AND it's in the qualifying set, /p/<slug> shows a 'From' block."""
    df = _snapshot_rows().copy()
    # Inject country into Alice's snapshots
    df.loc[df["slug"] == "alice", "country"] = "Russia"
    out = tmp_path / "alice.html"
    render_performer_page(df, slug="alice", output_path=out, qualifying_countries={"Russia"})
    content = out.read_text()
    assert 'class="performer-country"' in content
    assert '<a href="/country/russia/">Russia</a>' in content


def test_performer_page_omits_country_block_when_not_qualifying(tmp_path):
    """Performer has a country, but country not in qualifying set → no block."""
    df = _snapshot_rows().copy()
    df.loc[df["slug"] == "alice", "country"] = "Estonia"
    out = tmp_path / "alice.html"
    render_performer_page(df, slug="alice", output_path=out, qualifying_countries={"Russia"})
    content = out.read_text()
    assert "performer-country" not in content
    assert "/country/estonia/" not in content


def test_performer_page_omits_country_block_when_country_is_none(tmp_path):
    """Performer with no country → no block even if qualifying_countries is provided."""
    df = _snapshot_rows().copy()
    df["country"] = None  # Force None
    out = tmp_path / "alice.html"
    render_performer_page(df, slug="alice", output_path=out, qualifying_countries={"Russia"})
    content = out.read_text()
    assert "performer-country" not in content
```

Note: `_snapshot_rows()` is an existing helper — if it doesn't currently produce a `country` column, the `df["country"] = None` lines force the right schema.

- [ ] **Step 2: Confirm RED**

```bash
./venv/bin/pytest tests/test_heatmap.py -k "performer_page_emits_country or performer_page_omits_country" -v
```

Expected: failures (no `qualifying_countries` kwarg; no country block).

- [ ] **Step 3: Extend `render_performer_page`**

In `heatmap.py`, find `def render_performer_page`. Add `qualifying_countries: set[str] | None = None` as a keyword-only argument after existing parameters (right after the `categories` kwarg from Categories v1).

Inside the function, after the existing categories_html construction block, add:

```python
    # Country cross-link block — only when performer has a non-null country
    # AND that country is in the qualifying set (i.e., a /country/<slug>/ page
    # actually exists).
    country_html = ""
    if qualifying_countries:
        # Look up this performer's most recent country (snapshot date desc).
        my_rows = snapshots[snapshots["slug"] == slug]
        if not my_rows.empty and "country" in my_rows.columns:
            sorted_rows = my_rows.sort_values("snapshot_date", ascending=False)
            country = sorted_rows.iloc[0]["country"]
            if country and not pd.isna(country) and country in qualifying_countries:
                country_slug = _normalize_category_slug(country)
                # Inline CSS so the class only appears when the block is emitted.
                country_html = (
                    '<style>'
                    '.performer-country { margin: 16px 0; }'
                    '.performer-country h3 { font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: var(--muted); margin: 0 0 8px; }'
                    '.performer-country a { display: inline-block; background: var(--card-bg); border: 1px solid var(--rule); border-radius: 6px; padding: 4px 10px; font-size: 13px; color: var(--fg); text-decoration: none; }'
                    '.performer-country a:hover { color: var(--brand-orange); }'
                    '</style>'
                    '<section class="performer-country">'
                    '<h3>From</h3>'
                    f'<a href="/country/{country_slug}/">{_html.escape(country)}</a>'
                    '</section>'
                )
```

Then in the f-string that builds the page HTML, insert `{country_html}` immediately after `{categories_html}` (or wherever the categories block lives in the template).

- [ ] **Step 4: Confirm GREEN**

```bash
./venv/bin/pytest tests/test_heatmap.py -k "performer_page_emits_country or performer_page_omits_country" -v
```

Expected: 3 passed.

- [ ] **Step 5: Full suite (regression check on existing perf-page tests)**

```bash
./venv/bin/pytest -q
```

Expected: 90 passed (87 + 3 new). Existing perf-page tests still pass — `qualifying_countries=None` default is backwards-compatible.

- [ ] **Step 6: Commit**

```bash
git add heatmap.py tests/test_heatmap.py
git commit -m "$(cat <<'EOF'
feat(heatmap): /p/<slug> shows 'From <Country>' cross-link

render_performer_page gains a qualifying_countries: set[str] | None
kwarg. When the performer's latest snapshot has a country AND that
country is in the qualifying set (≥5 performers → has /country/<slug>/
page), a <section class="performer-country"> block renders with a
link to that country page.

Mirrors the existing performer-categories cross-link pattern. CSS is
inlined per-page only when the block is emitted, matching that pattern.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: `_NAV_ITEMS` + sitemap

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/heatmap.py`
- Modify: `/Users/ansvier/ph-heatmap/tests/test_heatmap.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_heatmap.py`:

```python
def test_nav_items_includes_countries():
    from heatmap import _NAV_ITEMS
    hrefs = [item[1] for item in _NAV_ITEMS]
    assert "/countries/" in hrefs, f"got hrefs={hrefs}"


def test_sitemap_includes_countries_page(tmp_path):
    """Sitemap emits /countries/ and per-country URLs for qualifying countries."""
    rows = []
    # Russia: 6 performers (qualifying)
    for i in range(6):
        rows.append({
            "snapshot_date": pd.Timestamp("2026-06-02"), "slug": f"ru{i}", "name": f"RU{i}",
            "total_views": 100_000_000, "rank": 1, "gender": "female", "country": "Russia",
        })
    # Italy: 2 performers (below threshold)
    for i in range(2):
        rows.append({
            "snapshot_date": pd.Timestamp("2026-06-02"), "slug": f"it{i}", "name": f"IT{i}",
            "total_views": 80_000_000, "rank": 1, "gender": "female", "country": "Italy",
        })
    df = pd.DataFrame(rows)
    write_sitemap_and_robots(df, public_dir=tmp_path)
    text = (tmp_path / "sitemap.xml").read_text()
    assert "<loc>https://hotmap.cam/countries/</loc>" in text
    assert "<loc>https://hotmap.cam/country/russia/</loc>" in text
    assert "/country/italy/" not in text  # below threshold
```

- [ ] **Step 2: Confirm RED**

```bash
./venv/bin/pytest tests/test_heatmap.py -k "nav_items_includes_countries or sitemap_includes_countries" -v
```

Expected: 2 failures.

- [ ] **Step 3: Add nav entry**

In `heatmap.py`, find `_NAV_ITEMS`. Add `("countries", "/countries/", "Countries")` between Categories and Charts:

```python
_NAV_ITEMS = [
    ("map",        "/",            "Map"),
    ("stats",      "/stats/",      "Stats"),
    ("categories", "/categories/", "Categories"),
    ("countries",  "/countries/",  "Countries"),
    ("charts",     "/charts/",     "Charts"),
]
```

(Adjust to match current shape — only the new entry matters.)

- [ ] **Step 4: Extend `write_sitemap_and_robots`**

In `write_sitemap_and_robots`, find the static URL list. Add `/countries/`. Then add a per-country emission block that mirrors the existing per-category pattern:

```python
    # Country URLs: /countries/ + per-qualifying-country
    if "country" in snapshots.columns:
        latest_date = pd.to_datetime(snapshots["snapshot_date"]).max()
        today = snapshots[(pd.to_datetime(snapshots["snapshot_date"]) == latest_date) & snapshots["country"].notna()]
        counts = today.groupby("country")["slug"].nunique()
        qualifying = counts[counts >= _COUNTRY_MIN_PERFORMERS].index
        for country in sorted(qualifying):
            urls.append((f"/country/{_normalize_category_slug(country)}/", today_str))
```

(Adapt to existing local variable names in `write_sitemap_and_robots` — read the function to find the `urls` list variable and `today_str` equivalent.)

Also add `"/countries/"` to the static URL list (the one with `/`, `/stats/`, `/charts/`, etc.).

- [ ] **Step 5: Confirm GREEN + full suite**

```bash
./venv/bin/pytest -q
```

Expected: 92 passed (90 + 2 new).

- [ ] **Step 6: Commit**

```bash
git add heatmap.py tests/test_heatmap.py
git commit -m "$(cat <<'EOF'
feat(heatmap): /countries/ in nav + sitemap

_NAV_ITEMS gains the Countries entry between Categories and Charts.
write_sitemap_and_robots emits /countries/ unconditionally and
/country/<slug>/ for each country with ≥5 performers in the latest
snapshot.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: `run.py` countries orchestration

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/run.py`

- [ ] **Step 1: Add imports**

In `run.py`, find the existing `from heatmap import ...` line. Add `render_country_page`, `render_countries_index`. Example final shape:

```python
from heatmap import dump_json, render_categories_treemap, render_charts_page, render_countries_index, render_country_page, render_performer_page, render_stats_page, render_treemap_page, write_sitemap_and_robots
```

- [ ] **Step 2: Insert countries rendering block**

Find the block that renders categories (look for `render_categories_treemap`). After that block, before `write_sitemap_and_robots`, add:

```python
    # ---- Countries — per-country + index ----
    if "country" in snapshots_df.columns:
        from heatmap import _COUNTRY_MIN_PERFORMERS, _normalize_category_slug
        latest_date_for_country = pd.to_datetime(snapshots_df["snapshot_date"]).max()
        today_df = snapshots_df[
            (pd.to_datetime(snapshots_df["snapshot_date"]) == latest_date_for_country)
            & snapshots_df["country"].notna()
        ]
        country_counts = today_df.groupby("country")["slug"].nunique()
        qualifying_countries = set(country_counts[country_counts >= _COUNTRY_MIN_PERFORMERS].index)
        if qualifying_countries:
            countries_root = PUBLIC_DIR / "country"
            countries_root.mkdir(parents=True, exist_ok=True)
            n_country_pages = 0
            for country_name in sorted(qualifying_countries):
                slug = _normalize_category_slug(country_name)
                country_dir = countries_root / slug
                country_dir.mkdir(exist_ok=True)
                try:
                    render_country_page(snapshots_df, country_name, country_dir / "index.html")
                    n_country_pages += 1
                except ValueError as exc:
                    print(f"  WARN: render_country_page skipped for {country_name}: {exc}", file=sys.stderr)
            print(f"wrote {n_country_pages} country pages under {countries_root}", flush=True)

            (PUBLIC_DIR / "countries").mkdir(exist_ok=True)
            render_countries_index(snapshots_df, PUBLIC_DIR / "countries" / "index.html")
            print(f"wrote /countries/index.html", flush=True)
        else:
            print("no qualifying countries (< 5 performers each) — skipping /countries/ renders", flush=True)
    else:
        qualifying_countries = set()
        print("no country data yet — skipping /countries/ renders", flush=True)
```

- [ ] **Step 3: Thread `qualifying_countries` into per-performer page calls**

Find the loop calling `render_performer_page(snapshots_df, slug=..., output_path=..., categories=...)`. Add `qualifying_countries=qualifying_countries` to each call:

```python
            render_performer_page(snapshots_df, slug=slug,
                output_path=PERFORMER_DIR / f"{slug}.html",
                categories=categories_df,
                qualifying_countries=qualifying_countries)
```

(If the categories kwarg is not yet present from Categories v1, just add `qualifying_countries=qualifying_countries` to the call. Match the existing pattern.)

**Important:** the `qualifying_countries` variable must be in scope at the performer-page loop. If the countries block above is positioned AFTER the performer-page loop, move the countries-computation step (just the `qualifying_countries = ...` calculation, NOT the rendering) to BEFORE the performer-page loop.

Specifically: compute `qualifying_countries` early, render countries pages later, but pass the set into performer pages whenever they're rendered. The simplest order:

1. Load `snapshots_df` (already done).
2. Compute `qualifying_countries` (new — 3 lines).
3. Render performer pages, passing `qualifying_countries=qualifying_countries`.
4. Render `/country/<slug>/` pages (the loop above).
5. Render `/countries/` index.

- [ ] **Step 4: Smoke run**

```bash
cd /Users/ansvier/ph-heatmap
./venv/bin/python -c "
from pathlib import Path
from db import init_db, load_all_snapshots
from heatmap import _COUNTRY_MIN_PERFORMERS, _normalize_category_slug, render_country_page, render_countries_index
import pandas as pd

PUBLIC_DIR = Path('public')
conn = init_db('data.db')
df = load_all_snapshots(conn)
if 'country' not in df.columns or df['country'].isna().all():
    print('No country data yet — backfill needed (Task 12).')
else:
    today_max = pd.to_datetime(df['snapshot_date']).max()
    today = df[(pd.to_datetime(df['snapshot_date']) == today_max) & df['country'].notna()]
    counts = today.groupby('country')['slug'].nunique()
    qualifying = counts[counts >= _COUNTRY_MIN_PERFORMERS].index
    print(f'qualifying countries: {len(qualifying)}: {list(qualifying)[:10]}')
    if len(qualifying) > 0:
        (PUBLIC_DIR / 'country').mkdir(parents=True, exist_ok=True)
        n = 0
        for c in qualifying:
            slug = _normalize_category_slug(c)
            d = PUBLIC_DIR / 'country' / slug
            d.mkdir(exist_ok=True)
            try:
                render_country_page(df, c, d / 'index.html')
                n += 1
            except Exception as exc:
                print(f'WARN {c}: {exc}')
        print(f'rendered {n} country pages')
        (PUBLIC_DIR / 'countries').mkdir(exist_ok=True)
        render_countries_index(df, PUBLIC_DIR / 'countries' / 'index.html')
        print('rendered /countries/index.html')
"
```

Expected: either reports "No country data yet" (if Task 12 backfill hasn't run yet — that's fine, Task 12 will populate) or reports `qualifying countries: N` and writes pages.

- [ ] **Step 5: Commit**

```bash
git add run.py
git commit -m "$(cat <<'EOF'
feat(run): render /country/<slug>/ + /countries/ index in daily orchestration

Inserts the countries rendering block after categories and threads
qualifying_countries into render_performer_page so cross-links only
appear when the target /country/<slug>/ actually exists.

Skips renders gracefully when no country data is present yet (e.g.,
fresh deploy before backfill).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 11: README

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/README.md`

- [ ] **Step 1: Add a Countries subsection**

Open `/Users/ansvier/ph-heatmap/README.md`. Find the "Features" / "Pages" section (look for where Categories or other page types are described — should be near the top). Add this paragraph:

```markdown
### Countries

Each performer's birth country (or nationality as fallback) is parsed from their Pornhub profile during the daily scrape. Countries with at least 5 tracked performers get their own landing page at `/country/<slug>/` — a single treemap showing top performers from that country, ranked the same way as the homepage (tile size = % growth, color = today's acceleration vs 7d baseline). An alphabetical index at `/countries/` lists every qualifying country with a count. Each `/p/<slug>` page shows the performer's country as a "From" cross-link.

Coverage depends on how completely each performer fills out their profile. Sample: ~85% of profiles expose either Birth Place or Background (nationality), with combined fallback. The one-off `scripts/backfill_countries.py` populates country for all existing tracked slugs; daily-scrape going forward extracts it as part of the existing profile fetch.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "$(cat <<'EOF'
docs: README subsection for Countries v1

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 12: Backfill + E2E render + push

**Files:** none (operational only).

The big operational step. Runs ~22 minutes (~870 slugs × 1.5s polite sleep).

- [ ] **Step 1: Run the full backfill**

```bash
cd /Users/ansvier/ph-heatmap
./venv/bin/python scripts/backfill_countries.py
```

Expected output:
- Progress lines every 50 slugs.
- Some `none` (no country found) — OK, ~15% expected.
- Some `FAIL` — OK if PH transiently errors (curl 28, etc.).
- Final `DONE  set=N  none=M  failed=K` with `N >= 700`.
- Followed by `Unmapped Background nationalities encountered:` list.

If most slugs fail (n_failed > n_set) → STOP and report. PH may be blocking; investigate before pushing.

- [ ] **Step 2: Sanity-check coverage**

```bash
./venv/bin/python -c "
import sqlite3, pandas as pd
conn = sqlite3.connect('data.db')
df = pd.read_sql_query('SELECT DISTINCT slug, country FROM snapshots', conn)
print(f'total unique slugs: {len(df)}')
print(f'with country: {df[\"country\"].notna().sum()} ({df[\"country\"].notna().mean()*100:.1f}%)')
print(f'without country: {df[\"country\"].isna().sum()}')
print()
counts = df[df['country'].notna()].groupby('country').size().sort_values(ascending=False)
print(f'top 15 countries by performer count:')
print(counts.head(15).to_string())
print()
print(f'countries with >=5 performers: {(counts >= 5).sum()}')
"
```

Expected: ~85% coverage, ~10-15 countries with ≥5 performers.

- [ ] **Step 3: Re-render everything**

```bash
./venv/bin/python -c "
from pathlib import Path
from db import init_db, load_all_snapshots, load_all_category_snapshots
from heatmap import (
    dump_json, render_categories_treemap, render_charts_page,
    render_countries_index, render_country_page,
    render_performer_page, render_stats_page, render_treemap_page,
    write_sitemap_and_robots,
    _COUNTRY_MIN_PERFORMERS, _normalize_category_slug,
)
import pandas as pd, sys

PUBLIC_DIR = Path('public')
conn = init_db('data.db')
snapshots = load_all_snapshots(conn)
category_snapshots = load_all_category_snapshots(conn)
print(f'snapshots={len(snapshots)}, category_snapshots={len(category_snapshots)}')

# Compute qualifying_countries (for cross-link gating)
today_max = pd.to_datetime(snapshots['snapshot_date']).max()
today = snapshots[(pd.to_datetime(snapshots['snapshot_date']) == today_max) & snapshots['country'].notna()]
country_counts = today.groupby('country')['slug'].nunique()
qualifying_countries = set(country_counts[country_counts >= _COUNTRY_MIN_PERFORMERS].index)
print(f'qualifying countries: {sorted(qualifying_countries)}')

# Main + mode landings
render_treemap_page(snapshots, PUBLIC_DIR / 'index.html', default_mode='rising', canonical_path='/', seo_key='home')
for mode in ('rising', 'gems', 'celebs'):
    (PUBLIC_DIR / mode).mkdir(exist_ok=True)
    render_treemap_page(snapshots, PUBLIC_DIR / mode / 'index.html', default_mode=mode, canonical_path=f'/{mode}/', seo_key=mode)
dump_json(snapshots, PUBLIC_DIR / 'data.json')

# Performer pages with country cross-link
(PUBLIC_DIR / 'p').mkdir(parents=True, exist_ok=True)
n_perf = 0
for slug in snapshots['slug'].unique():
    try:
        render_performer_page(snapshots, slug=slug, output_path=PUBLIC_DIR / 'p' / f'{slug}.html',
                              qualifying_countries=qualifying_countries)
        n_perf += 1
    except Exception as exc:
        print(f'WARN perf {slug}: {exc}')
print(f'wrote {n_perf} performer pages')

# Stats + charts
(PUBLIC_DIR / 'stats').mkdir(exist_ok=True)
render_stats_page(snapshots, PUBLIC_DIR / 'stats' / 'index.html')
(PUBLIC_DIR / 'charts').mkdir(exist_ok=True)
render_charts_page(snapshots, PUBLIC_DIR / 'charts' / 'index.html')

# Categories
if not category_snapshots.empty:
    (PUBLIC_DIR / 'categories').mkdir(exist_ok=True)
    render_categories_treemap(category_snapshots, PUBLIC_DIR / 'categories' / 'index.html')

# Countries
if qualifying_countries:
    countries_root = PUBLIC_DIR / 'country'
    countries_root.mkdir(parents=True, exist_ok=True)
    n_country = 0
    for country in sorted(qualifying_countries):
        slug = _normalize_category_slug(country)
        d = countries_root / slug
        d.mkdir(exist_ok=True)
        try:
            render_country_page(snapshots, country, d / 'index.html')
            n_country += 1
        except Exception as exc:
            print(f'WARN country {country}: {exc}')
    print(f'wrote {n_country} country pages')
    (PUBLIC_DIR / 'countries').mkdir(exist_ok=True)
    render_countries_index(snapshots, PUBLIC_DIR / 'countries' / 'index.html')
    print('wrote /countries/index.html')

write_sitemap_and_robots(snapshots, public_dir=PUBLIC_DIR)
print('done')
"
```

Expected: ~20-30 seconds. ~10-15 country pages written. `/countries/index.html` exists.

- [ ] **Step 4: Smoke check rendered output**

```bash
echo "=== /countries/ exists ==="
ls -la public/countries/index.html
echo "=== Sample country page ==="
ls public/country/ | head -5
echo "=== Sitemap has /countries/ + /country/ entries ==="
grep -E 'hotmap.cam/countries/|hotmap.cam/country/' public/sitemap.xml | head -5
echo "=== Lana Rhoades performer page has country block ==="
grep -c 'performer-country' public/p/lana-rhoades.html
```

Expected: index file exists, ≥5 country dirs, sitemap has ≥10 country URLs, lana-rhoades.html has the country block.

- [ ] **Step 5: Commit**

```bash
git status -s | head -10
git add data.db public/
git commit -m "$(cat <<'EOF'
chore(data+render): backfill Countries v1 and re-render

One-off PH country backfill for all tracked slugs. Re-rendered:
- /countries/index.html (alphabetical country list)
- /country/<slug>/ for each country with >=5 performers
- /p/<slug> pages updated to show 'From <Country>' cross-link
- sitemap.xml extended with all new URLs

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 6: Push**

```bash
git pull --rebase origin main 2>&1 | tail -3
git push 2>&1 | tail -3
```

- [ ] **Step 7: Live verify (after ~60s for CF Pages deploy)**

```bash
sleep 60
echo "=== /countries/ live ==="
curl -sI https://hotmap.cam/countries/ | head -1
echo "=== /country/russia/ (or another known country) live ==="
curl -sI https://hotmap.cam/country/russia/ | head -1
echo "=== /p/lana-rhoades shows country block ==="
curl -s https://hotmap.cam/p/lana-rhoades | grep -c 'performer-country'
echo "=== sitemap has /country/ entries ==="
curl -s https://hotmap.cam/sitemap.xml | grep -c 'hotmap.cam/country/'
```

Expected: HTTP 200 on both URL types; performer-country class present in /p/<slug>; sitemap has ≥10 entries.

---

## Self-review checklist (filled out by plan author)

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| `_NATIONALITY_TO_COUNTRY` + `_COUNTRY_ALIASES` | Task 1 |
| `extract_country` + `_canonicalize_country` | Task 1 |
| `ProfileData.country` + `parse_profile` extension | Task 1 |
| `country` column + migration | Task 2 |
| `Snapshot.country` field | Task 2 |
| `insert_snapshot` / `load_all_snapshots` handle country | Task 2 |
| `run.py` wires country from ProfileData → Snapshot | Task 3 |
| One-off backfill script with skip-NULL semantics + diagnostics | Task 4 |
| `_OG_TYPE_BY_PAGE_TYPE["country"]` + Literal | Task 5 |
| `_COUNTRY_MIN_PERFORMERS = 5` | Task 6 |
| `_COUNTRY_PAGE_TEMPLATE` + `render_country_page` | Task 6 |
| Spike of the Day card on country page | Task 6 |
| `render_countries_index` (alphabetical, threshold-filtered) | Task 7 |
| Cross-link block on `/p/<slug>` with qualifying-set gate | Task 8 |
| `_NAV_ITEMS` Countries entry | Task 9 |
| Sitemap includes `/countries/` + `/country/<slug>/` | Task 9 |
| `run.py` countries orchestration | Task 10 |
| README subsection | Task 11 |
| One-off backfill execution + E2E render + push | Task 12 |

No gaps.

**Placeholder scan:** No TBD/TODO/"similar to". Every code step has the actual code; every command step has the actual command + expected output.

**Type consistency:**
- `extract_country` signature stable across Tasks 1, 4.
- `Snapshot.country: str | None` matches `ProfileData.country` (Task 1 & 2).
- `qualifying_countries: set[str]` shape consistent in Tasks 8, 9 (via filter), 10 (in run.py).
- `_COUNTRY_MIN_PERFORMERS = 5` introduced in Task 6, consumed in Tasks 7, 9, 10.

**Conditional risk:** Task 8's `_snapshot_rows()` fixture may not currently have a `country` column. The tests force `df["country"] = "<value>"` to inject one, which works whether the column existed or not.
