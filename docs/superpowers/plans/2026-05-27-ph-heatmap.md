# ph-heatmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a daily-cron-driven scraper that captures the top-50 Most Viewed Pornstars from Pornhub, stores their cumulative view counts in SQLite, and regenerates an interactive Plotly heatmap of day-over-day percentage growth.

**Architecture:** Four-module Python project (`scraper`, `db`, `heatmap`, `run`). The scraper uses `curl-cffi` with Chrome TLS impersonation to bypass Cloudflare. SQLite stores one row per (date, actress slug). Plotly renders a standalone HTML file. Each module exposes a narrow interface and is testable in isolation against hand-crafted HTML fixtures and in-memory SQLite.

**Tech Stack:** Python 3.11+, `curl-cffi`, `selectolax`, `plotly`, `pandas`, `pytest` for tests, `cron` for scheduling.

**Spec:** [docs/superpowers/specs/2026-05-27-ph-heatmap-design.md](../specs/2026-05-27-ph-heatmap-design.md)

---

## File Layout

```
ph-heatmap/                       # project root (this directory)
├── run.py                        # entry point: scrape → store → render
├── scraper.py                    # HTTP + parsing for top list and profiles
├── db.py                         # SQLite schema and queries
├── heatmap.py                    # delta computation + plotly rendering
├── requirements.txt
├── README.md
├── .gitignore
├── tests/
│   ├── __init__.py
│   ├── conftest.py               # shared pytest fixtures
│   ├── fixtures/
│   │   ├── top_list.html         # hand-crafted minimal top-list snippet
│   │   └── profile.html          # hand-crafted minimal profile snippet
│   ├── test_db.py
│   ├── test_scraper.py
│   └── test_heatmap.py
├── data.db                       # created at first run, gitignored
├── heatmap.html                  # created at first run, gitignored
└── run.log                       # cron log, gitignored
```

Module responsibilities:
- **db.py** — owns the SQLite connection lifecycle, schema migration, and query primitives. No business logic.
- **scraper.py** — owns HTTP and HTML parsing. Returns plain dataclasses. No DB or rendering.
- **heatmap.py** — owns dataframe transformations and Plotly rendering. No HTTP or DB writes.
- **run.py** — orchestration only. Calls the three modules in sequence.

---

## Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Initialize git repository**

Run:
```bash
git init
git config user.email "ph-heatmap@local"
git config user.name "ph-heatmap"
```

- [ ] **Step 2: Create `requirements.txt`**

```
curl-cffi>=0.7
selectolax>=0.3.21
plotly>=5.20
pandas>=2.2
pytest>=8.0
```

- [ ] **Step 3: Create `.gitignore`**

```
__pycache__/
*.pyc
.venv/
venv/
.pytest_cache/
data.db
heatmap.html
run.log
tests/fixtures/*.live.html
```

- [ ] **Step 4: Create `tests/__init__.py` (empty file)**

```python
```

- [ ] **Step 5: Create `tests/conftest.py`**

```python
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def top_list_html() -> str:
    return (FIXTURES / "top_list.html").read_text()


@pytest.fixture
def profile_html() -> str:
    return (FIXTURES / "profile.html").read_text()
```

- [ ] **Step 6: Create and activate virtualenv, install deps**

Run:
```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```
Expected: install completes without errors.

- [ ] **Step 7: Verify pytest discovers no tests yet**

Run: `./venv/bin/pytest -q`
Expected: `no tests ran` (exit 5) — this is fine.

- [ ] **Step 8: Commit**

```bash
git add requirements.txt .gitignore tests/__init__.py tests/conftest.py
git commit -m "chore: scaffold project structure"
```

---

## Task 2: `db.py` — SQLite layer

**Files:**
- Create: `db.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: Write failing test for `init_db` + `insert_snapshot` + `load_all_snapshots`**

Create `tests/test_db.py`:

```python
from datetime import date

import pandas as pd

from db import Snapshot, init_db, insert_snapshot, load_all_snapshots


def test_insert_and_load_round_trip(tmp_path):
    db_path = tmp_path / "test.db"
    conn = init_db(db_path)

    rows = [
        Snapshot(snapshot_date=date(2026, 5, 27), slug="alice", name="Alice", total_views=1_000, rank=1),
        Snapshot(snapshot_date=date(2026, 5, 27), slug="bob",   name="Bob",   total_views=900,   rank=2),
    ]
    insert_snapshot(conn, rows)

    df = load_all_snapshots(conn)
    assert len(df) == 2
    assert set(df["slug"]) == {"alice", "bob"}
    assert df.loc[df["slug"] == "alice", "total_views"].iloc[0] == 1_000


def test_insert_is_idempotent_per_date_and_slug(tmp_path):
    db_path = tmp_path / "test.db"
    conn = init_db(db_path)

    row = Snapshot(snapshot_date=date(2026, 5, 27), slug="alice", name="Alice", total_views=1_000, rank=1)
    insert_snapshot(conn, [row])
    # Re-inserting the same (date, slug) replaces the row instead of erroring.
    updated = Snapshot(snapshot_date=date(2026, 5, 27), slug="alice", name="Alice", total_views=1_500, rank=1)
    insert_snapshot(conn, [updated])

    df = load_all_snapshots(conn)
    assert len(df) == 1
    assert df["total_views"].iloc[0] == 1_500


def test_load_returns_dataframe_with_parsed_dates(tmp_path):
    db_path = tmp_path / "test.db"
    conn = init_db(db_path)

    insert_snapshot(conn, [
        Snapshot(snapshot_date=date(2026, 5, 26), slug="a", name="A", total_views=10, rank=1),
        Snapshot(snapshot_date=date(2026, 5, 27), slug="a", name="A", total_views=20, rank=1),
    ])

    df = load_all_snapshots(conn)
    assert pd.api.types.is_datetime64_any_dtype(df["snapshot_date"])
    assert df["snapshot_date"].min().date() == date(2026, 5, 26)
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `./venv/bin/pytest tests/test_db.py -v`
Expected: `ImportError` / `ModuleNotFoundError: db`.

- [ ] **Step 3: Implement `db.py`**

```python
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class Snapshot:
    snapshot_date: date
    slug: str
    name: str
    total_views: int
    rank: int


_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_date TEXT NOT NULL,
    slug          TEXT NOT NULL,
    name          TEXT NOT NULL,
    total_views   INTEGER NOT NULL,
    rank          INTEGER NOT NULL,
    PRIMARY KEY (snapshot_date, slug)
);
"""


def init_db(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.execute(_SCHEMA)
    conn.commit()
    return conn


def insert_snapshot(conn: sqlite3.Connection, rows: list[Snapshot]) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO snapshots "
        "(snapshot_date, slug, name, total_views, rank) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            (r.snapshot_date.isoformat(), r.slug, r.name, r.total_views, r.rank)
            for r in rows
        ],
    )
    conn.commit()


def load_all_snapshots(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query(
        "SELECT snapshot_date, slug, name, total_views, rank FROM snapshots",
        conn,
    )
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    return df
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `./venv/bin/pytest tests/test_db.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_db.py
git commit -m "feat: add SQLite snapshot storage"
```

---

## Task 3: `scraper.py` — HTML parsers (against fixtures)

This task implements pure-parsing functions tested against hand-crafted HTML. HTTP is added in Task 4.

**Files:**
- Create: `tests/fixtures/top_list.html`
- Create: `tests/fixtures/profile.html`
- Create: `scraper.py`
- Create: `tests/test_scraper.py`

- [ ] **Step 1: Create `tests/fixtures/top_list.html`**

A minimal snippet mirroring the structure we rely on — a container with `<a href="/pornstar/<slug>">` links. Real pages have far more markup; the parser only needs the links in document order.

```html
<!doctype html>
<html>
<body>
<ul class="pornstarsWrapper">
  <li><a href="/pornstar/alice-example">Alice Example</a></li>
  <li><a href="/pornstar/bob-sample">Bob Sample</a></li>
  <li><a href="/pornstar/alice-example">Alice Example duplicate</a></li>
  <li><a href="/pornstar/carol-third">Carol Third</a></li>
  <li><a href="/videos/something-else">unrelated</a></li>
</ul>
</body>
</html>
```

- [ ] **Step 2: Create `tests/fixtures/profile.html`**

Two known shapes for the Video Views figure are supported. Include both so the parser is exercised against either layout we have seen:

```html
<!doctype html>
<html>
<body>
<section class="infoPiece">
  <span>Video Views</span>
  <span>123,456,789</span>
</section>
<h1>Alice Example</h1>
</body>
</html>
```

- [ ] **Step 3: Write failing tests for parsers**

Create `tests/test_scraper.py`:

```python
import pytest

from scraper import parse_profile, parse_top_list


def test_parse_top_list_returns_unique_slugs_in_order(top_list_html):
    slugs = parse_top_list(top_list_html, limit=10)
    assert slugs == ["alice-example", "bob-sample", "carol-third"]


def test_parse_top_list_respects_limit(top_list_html):
    slugs = parse_top_list(top_list_html, limit=2)
    assert slugs == ["alice-example", "bob-sample"]


def test_parse_top_list_ignores_non_pornstar_links(top_list_html):
    slugs = parse_top_list(top_list_html, limit=50)
    assert "something-else" not in slugs


def test_parse_profile_extracts_views_and_name(profile_html):
    result = parse_profile(profile_html)
    assert result.total_views == 123_456_789
    assert result.name == "Alice Example"


def test_parse_profile_raises_when_views_missing():
    html = "<html><body><h1>No Stats Person</h1></body></html>"
    with pytest.raises(ValueError, match="Video Views"):
        parse_profile(html)
```

- [ ] **Step 4: Run tests, verify they fail**

Run: `./venv/bin/pytest tests/test_scraper.py -v`
Expected: `ImportError: scraper`.

- [ ] **Step 5: Implement parsing in `scraper.py`**

```python
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
    """Find a 'Video Views' label and return the adjacent integer.

    Strategy: walk every element whose text contains 'Video Views', then look
    at its next sibling or parent's other children for a digit-bearing string.
    """
    for label in tree.css("*"):
        text = label.text(strip=True)
        if text != "Video Views":
            continue
        # Try the next sibling.
        sibling = label.next
        candidates: list[str] = []
        if sibling is not None:
            candidates.append(sibling.text(strip=True))
        # Try other children of the parent.
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
```

- [ ] **Step 6: Run tests, verify they pass**

Run: `./venv/bin/pytest tests/test_scraper.py -v`
Expected: 5 passed.

- [ ] **Step 7: Commit**

```bash
git add scraper.py tests/test_scraper.py tests/fixtures/
git commit -m "feat: add top-list and profile HTML parsers"
```

---

## Task 4: `scraper.py` — HTTP layer

Add the live-fetch functions using `curl-cffi`. These are hard to unit-test deterministically (network + Cloudflare), so we add a small smoke check executed manually rather than under pytest.

**Files:**
- Modify: `scraper.py` (append `fetch_top_pornstars` and `fetch_profile`)

- [ ] **Step 1: Append HTTP helpers to `scraper.py`**

```python
import time
import random

from curl_cffi import requests as cffi_requests

_TOP_LIST_URL = "https://www.pornhub.com/pornstars?o=mv"
_PROFILE_URL_TEMPLATE = "https://www.pornhub.com/pornstar/{slug}"
_IMPERSONATE = "chrome120"
_REQUEST_TIMEOUT = 30  # seconds


def _fetch(url: str) -> str:
    response = cffi_requests.get(url, impersonate=_IMPERSONATE, timeout=_REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.text


def fetch_top_pornstars(limit: int = 50) -> list[str]:
    return parse_top_list(_fetch(_TOP_LIST_URL), limit=limit)


def fetch_profile(slug: str) -> ProfileData:
    return parse_profile(_fetch(_PROFILE_URL_TEMPLATE.format(slug=slug)))


def polite_sleep(base: float = 1.5, jitter: float = 0.5) -> None:
    """Sleep between requests, jittered to avoid uniform timing."""
    time.sleep(base + random.uniform(-jitter, jitter))
```

- [ ] **Step 2: Manual smoke check**

Run:
```bash
./venv/bin/python -c "from scraper import fetch_top_pornstars; print(fetch_top_pornstars(limit=3))"
```
Expected: a Python list of three slug strings, e.g. `['some-slug', 'another-slug', 'third-slug']`.

If the call fails with a 403 or hangs:
- Confirm `curl-cffi` is installed: `./venv/bin/pip show curl-cffi`.
- Try a different `impersonate` value (`chrome116`, `chrome119`).
- If still blocked, stop and report — fallback to Playwright is a separate plan.

- [ ] **Step 3: Manual smoke check for a profile**

Pick one slug from the previous step's output (called `<slug>` below) and run:
```bash
./venv/bin/python -c "from scraper import fetch_profile; print(fetch_profile('<slug>'))"
```
Expected: `ProfileData(name='...', total_views=<some_integer>)`.

- [ ] **Step 4: Commit**

```bash
git add scraper.py
git commit -m "feat: add HTTP layer with curl-cffi Chrome impersonation"
```

---

## Task 5: `heatmap.py` — delta computation

Pure pandas transformation. No I/O.

**Files:**
- Create: `heatmap.py` (transform half only — render added in Task 6)
- Create: `tests/test_heatmap.py`

- [ ] **Step 1: Write failing tests for `compute_growth_matrix`**

Create `tests/test_heatmap.py`:

```python
from datetime import date

import numpy as np
import pandas as pd
import pytest

from heatmap import compute_growth_matrix


def _snapshot_rows():
    """Three days, three slugs with partial coverage."""
    return pd.DataFrame([
        # day 1
        {"snapshot_date": pd.Timestamp(date(2026, 5, 25)), "slug": "alice", "name": "Alice", "total_views": 1000, "rank": 1},
        {"snapshot_date": pd.Timestamp(date(2026, 5, 25)), "slug": "bob",   "name": "Bob",   "total_views":  500, "rank": 2},
        # day 2 — alice grows 10%, bob grows 20%, carol new (no delta)
        {"snapshot_date": pd.Timestamp(date(2026, 5, 26)), "slug": "alice", "name": "Alice", "total_views": 1100, "rank": 1},
        {"snapshot_date": pd.Timestamp(date(2026, 5, 26)), "slug": "bob",   "name": "Bob",   "total_views":  600, "rank": 2},
        {"snapshot_date": pd.Timestamp(date(2026, 5, 26)), "slug": "carol", "name": "Carol", "total_views":  200, "rank": 3},
        # day 3 — alice grows another ~9.09%, bob disappears, carol +50%
        {"snapshot_date": pd.Timestamp(date(2026, 5, 27)), "slug": "alice", "name": "Alice", "total_views": 1200, "rank": 1},
        {"snapshot_date": pd.Timestamp(date(2026, 5, 27)), "slug": "carol", "name": "Carol", "total_views":  300, "rank": 2},
    ])


def test_growth_matrix_shape_and_index():
    matrix = compute_growth_matrix(_snapshot_rows())
    # Three slugs total, three dates.
    assert set(matrix.index) == {"alice", "bob", "carol"}
    assert list(matrix.columns) == [
        pd.Timestamp(date(2026, 5, 25)),
        pd.Timestamp(date(2026, 5, 26)),
        pd.Timestamp(date(2026, 5, 27)),
    ]


def test_growth_matrix_first_day_is_nan():
    matrix = compute_growth_matrix(_snapshot_rows())
    first_col = matrix[pd.Timestamp(date(2026, 5, 25))]
    assert first_col.isna().all()


def test_growth_matrix_values():
    matrix = compute_growth_matrix(_snapshot_rows())
    day2 = pd.Timestamp(date(2026, 5, 26))
    assert matrix.loc["alice", day2] == pytest.approx(10.0)
    assert matrix.loc["bob",   day2] == pytest.approx(20.0)
    # Carol appeared on day 2 with no day-1 baseline.
    assert np.isnan(matrix.loc["carol", day2])


def test_growth_matrix_missing_slug_yields_nan():
    matrix = compute_growth_matrix(_snapshot_rows())
    day3 = pd.Timestamp(date(2026, 5, 27))
    # Bob disappeared on day 3.
    assert np.isnan(matrix.loc["bob", day3])
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `./venv/bin/pytest tests/test_heatmap.py -v`
Expected: `ImportError: heatmap`.

- [ ] **Step 3: Implement `compute_growth_matrix` in `heatmap.py`**

```python
from __future__ import annotations

import pandas as pd


def compute_growth_matrix(snapshots: pd.DataFrame) -> pd.DataFrame:
    """Return a (slug × date) matrix of day-over-day % growth in total_views.

    Cells where either the current or previous day's value is missing become NaN.
    The first column is always NaN (no prior day to diff against).
    """
    pivot = snapshots.pivot_table(
        index="slug",
        columns="snapshot_date",
        values="total_views",
        aggfunc="first",
    )
    pivot = pivot.sort_index(axis=1)  # chronological columns
    pct = pivot.pct_change(axis=1) * 100
    return pct
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `./venv/bin/pytest tests/test_heatmap.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add heatmap.py tests/test_heatmap.py
git commit -m "feat: compute day-over-day growth matrix"
```

---

## Task 6: `heatmap.py` — Plotly rendering

**Files:**
- Modify: `heatmap.py` (append render function)
- Modify: `tests/test_heatmap.py` (add smoke test)

- [ ] **Step 1: Append failing smoke test for rendering**

Append to `tests/test_heatmap.py`:

```python
from heatmap import render_heatmap


def test_render_heatmap_writes_html(tmp_path):
    df = _snapshot_rows()
    out = tmp_path / "out.html"
    render_heatmap(df, out)
    assert out.exists()
    content = out.read_text()
    # Sanity: it is an HTML document containing a Plotly figure.
    assert "<html" in content.lower()
    assert "plotly" in content.lower()
    # Display names should appear on the Y axis.
    assert "Alice" in content
    assert "Carol" in content
```

- [ ] **Step 2: Run, verify failure**

Run: `./venv/bin/pytest tests/test_heatmap.py::test_render_heatmap_writes_html -v`
Expected: `ImportError: cannot import name 'render_heatmap'`.

- [ ] **Step 3: Append `render_heatmap` to `heatmap.py`**

```python
from pathlib import Path

import plotly.graph_objects as go


def render_heatmap(snapshots: pd.DataFrame, output_path: Path | str) -> None:
    """Render the growth heatmap to a standalone HTML file."""
    if snapshots.empty:
        raise ValueError("No snapshots to render")

    growth = compute_growth_matrix(snapshots)

    # Y-axis ordering: by total_views in the latest snapshot, descending.
    latest_date = snapshots["snapshot_date"].max()
    latest = (
        snapshots[snapshots["snapshot_date"] == latest_date]
        .set_index("slug")["total_views"]
    )
    ordered_slugs = (
        latest.reindex(growth.index)
        .sort_values(ascending=False, na_position="last")
        .index.tolist()
    )
    growth = growth.loc[ordered_slugs]

    # Map slug -> latest display name for the Y tick labels.
    latest_names = (
        snapshots.sort_values("snapshot_date")
        .drop_duplicates("slug", keep="last")
        .set_index("slug")["name"]
    )
    y_labels = [latest_names.get(slug, slug) for slug in growth.index]

    # Absolute total_views aligned to the growth matrix for hover.
    views_pivot = (
        snapshots.pivot_table(index="slug", columns="snapshot_date", values="total_views", aggfunc="first")
        .reindex(index=growth.index, columns=growth.columns)
    )

    figure = go.Figure(
        data=go.Heatmap(
            z=growth.values,
            x=[d.strftime("%Y-%m-%d") for d in growth.columns],
            y=y_labels,
            colorscale="YlOrRd",
            zmin=0,
            colorbar=dict(title="% growth"),
            customdata=views_pivot.values,
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Date: %{x}<br>"
                "Total views: %{customdata:,}<br>"
                "Growth: %{z:.2f}%<extra></extra>"
            ),
        )
    )
    figure.update_layout(
        title=f"Pornhub Top-50 — Daily View Growth (latest: {latest_date.date()})",
        xaxis_title="Date",
        yaxis_title="Pornstar",
        yaxis=dict(autorange="reversed"),  # top of axis = highest rank
        height=max(400, 18 * len(growth.index) + 200),
    )

    figure.write_html(str(output_path), include_plotlyjs="cdn", full_html=True)
```

- [ ] **Step 4: Run all heatmap tests**

Run: `./venv/bin/pytest tests/test_heatmap.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add heatmap.py tests/test_heatmap.py
git commit -m "feat: render growth matrix to standalone Plotly HTML"
```

---

## Task 7: `run.py` — orchestration

Wires the three modules together into a CLI entry point. End-to-end manual verification rather than an automated test, since the integration touches the network.

**Files:**
- Create: `run.py`

- [ ] **Step 1: Implement `run.py`**

```python
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from db import Snapshot, init_db, insert_snapshot, load_all_snapshots
from heatmap import render_heatmap
from scraper import fetch_profile, fetch_top_pornstars, polite_sleep

PROJECT_ROOT = Path(__file__).parent
DB_PATH = PROJECT_ROOT / "data.db"
HTML_PATH = PROJECT_ROOT / "heatmap.html"
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

    conn = init_db(DB_PATH)
    insert_snapshot(conn, rows)
    print(f"stored {len(rows)} rows", flush=True)

    snapshots_df = load_all_snapshots(conn)
    render_heatmap(snapshots_df, HTML_PATH)
    print(f"wrote {HTML_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: End-to-end run with reduced N**

Temporarily edit `run.py`, change `TOP_N = 50` to `TOP_N = 3`, save.

Run:
```bash
./venv/bin/python run.py
```

Expected output (slugs and counts will vary):
```
[2026-05-27] starting snapshot run
got 3 slugs
stored 3 rows
wrote /Users/ansvier/Hecto Bot 2/heatmap.html
```

Verify:
- `data.db` exists.
- `heatmap.html` exists and opens in a browser (the heatmap will be empty of color — only one snapshot exists so all deltas are NaN).
- Re-run the script a second time: hover tooltips should still show, and rerunning on the same day should INSERT OR REPLACE (still 3 rows for today).

- [ ] **Step 3: Restore `TOP_N = 50`**

Edit `run.py` and set `TOP_N = 50` again.

- [ ] **Step 4: Commit**

```bash
git add run.py
git commit -m "feat: add CLI entry point that orchestrates scrape, store, render"
```

---

## Task 8: README and cron setup

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create `README.md`**

```markdown
# ph-heatmap

Daily snapshot of the top-50 Most Viewed Pornstars on Pornhub, visualized as a heatmap of day-over-day percentage growth in cumulative `Video Views`.

## Setup

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

## Run once

```bash
./venv/bin/python run.py
```

Creates / updates `data.db` (SQLite) and `heatmap.html` (open in a browser).

## Schedule via cron

Add to `crontab -e`:

```
0 4 * * * cd /absolute/path/to/ph-heatmap && ./venv/bin/python run.py >> run.log 2>&1
```

This runs daily at 04:00 local time. The first run produces a heatmap with no colored cells (no prior day to diff against). The second run is the first useful one.

## Tests

```bash
./venv/bin/pytest -v
```

## Troubleshooting

- **403 / blank top list:** Cloudflare is rejecting the TLS fingerprint. Try a different `impersonate` value in `scraper.py` (`chrome116`, `chrome119`, `chrome120`).
- **Profile parser raises `Could not find 'Video Views'`:** the site changed its layout. Fetch one profile manually, inspect, and update `_extract_video_views` in `scraper.py`.
- **Empty heatmap after several days:** check `run.log` for `WARN: skipping ...` lines — those actresses are being filtered out before insert.

## Layout

| File | Responsibility |
|------|----------------|
| `run.py` | Orchestration |
| `scraper.py` | HTTP + parsing |
| `db.py` | SQLite read/write |
| `heatmap.py` | Delta math + Plotly render |
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with setup, run, cron, and troubleshooting"
```

- [ ] **Step 3: Final verification**

Run: `./venv/bin/pytest -v`
Expected: all tests pass (3 db + 5 scraper + 5 heatmap = 13 tests).

Run: `git log --oneline`
Expected: a clean linear history of ~8 commits.

---

## Spec Coverage Check

| Spec section | Implemented in |
|---|---|
| SQLite schema with composite PK | Task 2 |
| Slug as stable identity | Task 2 (schema), Task 3 (parser extracts slug) |
| `curl-cffi` Chrome impersonation | Task 4 |
| 1.5s ± 0.5s jittered throttle | Task 4 (`polite_sleep`) |
| Top-list URL: pornstars?o=mv | Task 4 (`_TOP_LIST_URL`) |
| Profile-level Video Views extraction | Task 3 (`_extract_video_views`) |
| Sequential warm palette, zmin=0 | Task 6 (`colorscale="YlOrRd"`, `zmin=0`) |
| Y-axis sorted by latest total_views desc | Task 6 (`ordered_slugs`) |
| Missing cells render as gaps | Task 6 (NaN → blank in Plotly) |
| Hover with name, date, views, delta | Task 6 (`hovertemplate`) |
| Per-actress error skips, top-list failure exits nonzero | Task 7 |
| Cron snippet, 04:00 daily | Task 8 (README) |
| `data.db`, `heatmap.html`, `run.log` gitignored | Task 1 |
