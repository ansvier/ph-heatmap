# Trending Categories — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Daily snapshot of all ~189 Pornhub categories with their `video_count`, rendered as a treemap at `/categories/`. Tile size = video_count, color = today's growth percentile.

**Architecture:** New `category_snapshots` SQLite table parallel to existing `snapshots`. New `parse_category_catalog` + `fetch_category_catalog` helpers in scraper. New `render_categories_treemap` in heatmap reusing existing Plotly Treemap pattern. `run.py` prepends a 3-line fetch+insert block before the existing performer flow, then renders the page after the existing renders.

**Tech Stack:** Python 3.13, SQLite (stdlib), pandas, selectolax (existing), curl-cffi (existing), plotly (existing), pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-01-trending-categories-design.md`

---

## File map

| Path | Purpose | Tasks |
|---|---|---|
| `db.py` | `CategorySnapshot` dataclass + table schema + `insert_category_snapshot` + `load_all_category_snapshots` | Task 1 |
| `scraper.py` | `parse_category_catalog`, `fetch_category_catalog` | Tasks 2, 3 |
| `tests/fixtures/categories_catalog.html` | HTML fixture with embedded JSON blocks | Task 2 |
| `heatmap.py` | `_OG_TYPE_BY_PAGE_TYPE["category"]` + `Literal` update; `_CATEGORIES_PAGE_TEMPLATE`; `render_categories_treemap`; `_NAV_ITEMS` entry; sitemap extension | Tasks 4, 5, 6 |
| `run.py` | 3-line fetch+insert block + 1-line render call | Task 7 |
| `README.md` | New subsection | Task 8 |
| `tests/test_db.py`, `tests/test_scraper.py`, `tests/test_heatmap.py` | Tests across tasks | within each task |

No new packages.

---

### Task 1: `category_snapshots` table + DB helpers

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/db.py`
- Modify: `/Users/ansvier/ph-heatmap/tests/test_db.py`

- [ ] **Step 1: Write failing tests**

Append to `/Users/ansvier/ph-heatmap/tests/test_db.py`:

```python
from db import insert_category_snapshot, load_all_category_snapshots, CategorySnapshot


def test_init_db_creates_category_snapshots_table(tmp_path):
    """init_db creates category_snapshots with the expected schema."""
    db_path = tmp_path / "test.db"
    conn = init_db(db_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(category_snapshots)")}
    assert cols == {"snapshot_date", "category_id", "slug", "name", "video_count", "points"}, \
        f"got cols={cols}"
    pk = [row[1] for row in conn.execute("PRAGMA table_info(category_snapshots)") if row[5] > 0]
    assert set(pk) == {"snapshot_date", "category_id"}, f"got pk cols={pk}"


def test_insert_and_load_category_snapshots_round_trip(tmp_path):
    """insert_category_snapshot + load_all_category_snapshots round-trips correctly."""
    from datetime import date
    conn = init_db(tmp_path / "test.db")
    today = date(2026, 6, 1)
    rows = [
        CategorySnapshot(snapshot_date=today, category_id=37, slug="18-25", name="18-25",
                         video_count=289620, points=65005),
        CategorySnapshot(snapshot_date=today, category_id=29, slug="milf", name="MILF",
                         video_count=199835, points=12500),
        CategorySnapshot(snapshot_date=today, category_id=1, slug="anal", name="Anal",
                         video_count=142217, points=None),  # points may be missing
    ]
    insert_category_snapshot(conn, rows)
    df = load_all_category_snapshots(conn)
    assert len(df) == 3
    assert set(df["category_id"]) == {37, 29, 1}
    milf_row = df[df["category_id"] == 29].iloc[0]
    assert milf_row["name"] == "MILF"
    assert int(milf_row["video_count"]) == 199835
    # Anal had points=None
    anal_row = df[df["category_id"] == 1].iloc[0]
    assert pd.isna(anal_row["points"])


def test_insert_category_snapshot_replaces_on_conflict(tmp_path):
    """Inserting the same (date, id) overwrites — upsert semantics."""
    from datetime import date
    conn = init_db(tmp_path / "test.db")
    today = date(2026, 6, 1)
    v1 = CategorySnapshot(snapshot_date=today, category_id=37, slug="18-25", name="18-25",
                          video_count=100, points=10)
    v2 = CategorySnapshot(snapshot_date=today, category_id=37, slug="18-25", name="18-25",
                          video_count=999, points=99)
    insert_category_snapshot(conn, [v1])
    insert_category_snapshot(conn, [v2])
    df = load_all_category_snapshots(conn)
    assert len(df) == 1
    assert int(df.iloc[0]["video_count"]) == 999
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/ansvier/ph-heatmap
./venv/bin/pytest tests/test_db.py -k "category_snapshots or round_trip or replaces_on_conflict" -v
```

Expected: `ImportError` — `insert_category_snapshot`, `load_all_category_snapshots`, `CategorySnapshot` don't exist.

- [ ] **Step 3: Add `CategorySnapshot` dataclass and schema**

Open `/Users/ansvier/ph-heatmap/db.py`. After the existing `Snapshot` dataclass (around line 19), add:

```python
@dataclass(frozen=True)
class CategorySnapshot:
    snapshot_date: date
    category_id: int
    slug: str
    name: str
    video_count: int
    points: int | None = None
```

After the existing `_SCHEMA` constant, add:

```python
_CATEGORY_SNAPSHOTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS category_snapshots (
    snapshot_date  TEXT    NOT NULL,
    category_id    INTEGER NOT NULL,
    slug           TEXT    NOT NULL,
    name           TEXT    NOT NULL,
    video_count    INTEGER NOT NULL,
    points         INTEGER,
    PRIMARY KEY (snapshot_date, category_id)
);
CREATE INDEX IF NOT EXISTS idx_cs_date     ON category_snapshots(snapshot_date);
CREATE INDEX IF NOT EXISTS idx_cs_category ON category_snapshots(category_id);
"""
```

Inside `init_db`, after the existing migrations and before `return conn`, execute the new schema:

```python
    conn.executescript(_CATEGORY_SNAPSHOTS_SCHEMA)
    conn.commit()

    return conn
```

After the existing `load_all_snapshots` function, append:

```python
def insert_category_snapshot(conn: sqlite3.Connection, rows: list[CategorySnapshot]) -> None:
    """Upsert category snapshot rows. PK is (snapshot_date, category_id)."""
    conn.executemany(
        "INSERT OR REPLACE INTO category_snapshots "
        "(snapshot_date, category_id, slug, name, video_count, points) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            (r.snapshot_date.isoformat(), r.category_id, r.slug, r.name, r.video_count, r.points)
            for r in rows
        ],
    )
    conn.commit()


def load_all_category_snapshots(conn: sqlite3.Connection) -> pd.DataFrame:
    """Load the full category_snapshots table as a DataFrame."""
    df = pd.read_sql_query(
        "SELECT snapshot_date, category_id, slug, name, video_count, points "
        "FROM category_snapshots",
        conn,
    )
    if not df.empty:
        df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    return df
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
./venv/bin/pytest tests/test_db.py -k "category_snapshots or round_trip or replaces_on_conflict" -v
```

Expected: 3 passed.

- [ ] **Step 5: Full suite regression**

```bash
./venv/bin/pytest -q
```

Expected: 52 + 3 = 55 passed.

- [ ] **Step 6: Commit**

```bash
git add db.py tests/test_db.py
git commit -m "$(cat <<'EOF'
feat(db): category_snapshots table + insert/load helpers

New SQLite table parallel to snapshots — per-day capture of PH's
category catalog (id, slug, name, video_count, points). PK is
(snapshot_date, category_id); INSERT OR REPLACE semantics. Helpers
used by the upcoming category scraper and render path.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `parse_category_catalog` + HTML fixture

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/scraper.py`
- Create: `/Users/ansvier/ph-heatmap/tests/fixtures/categories_catalog.html`
- Modify: `/Users/ansvier/ph-heatmap/tests/test_scraper.py`

- [ ] **Step 1: Create HTML fixture**

Create `/Users/ansvier/ph-heatmap/tests/fixtures/categories_catalog.html` with embedded JSON blocks shaped like the real PH HTML. Use a minimal but realistic shape (one duplicate to exercise dedup; one inactive entry to exercise the status filter; one with no `points`):

```html
<!doctype html>
<html><body>
<script>
  window.CATEGORIES_DATA = [
    {"id":37,"name":"18-25","english":"18-25","slug":"18-25","segment":0,"segmented":0,"singular":0,"status":"active","video_count":289620,"video_count_whitelabel":3770,"video_count_paid":0,"points":65005,"last_updated":"2026-06-01"},
    {"id":29,"name":"MILF","english":"MILF","slug":"milf","segment":0,"segmented":0,"singular":0,"status":"active","video_count":199835,"video_count_whitelabel":2100,"video_count_paid":0,"points":12500,"last_updated":"2026-06-01"},
    {"id":1,"name":"Anal","english":"Anal","slug":"anal","segment":0,"segmented":0,"singular":0,"status":"active","video_count":142217,"video_count_whitelabel":1800,"video_count_paid":0,"last_updated":"2026-06-01"}
  ];
</script>
<div class="otherStuff">
  <!-- Duplicate of id=37 (cross-category panel) -->
  <script>{"id":37,"name":"18-25","english":"18-25","slug":"18-25","segment":0,"segmented":0,"singular":0,"status":"active","video_count":289620,"video_count_whitelabel":3770,"video_count_paid":0,"points":65005,"last_updated":"2026-06-01"}</script>
  <!-- Inactive category — must be filtered out -->
  <script>{"id":999,"name":"Deprecated","english":"Deprecated","slug":"deprecated","segment":0,"segmented":0,"singular":0,"status":"inactive","video_count":50,"video_count_whitelabel":0,"video_count_paid":0,"points":0,"last_updated":"2026-06-01"}</script>
</div>
</body></html>
```

- [ ] **Step 2: Write failing tests**

Append to `/Users/ansvier/ph-heatmap/tests/test_scraper.py`:

```python
from pathlib import Path
from scraper import parse_category_catalog


def _read_categories_fixture() -> str:
    return (Path(__file__).parent / "fixtures" / "categories_catalog.html").read_text()


def test_parse_category_catalog_extracts_required_fields():
    """parse_category_catalog returns the 3 active categories with all required fields."""
    html = _read_categories_fixture()
    result = parse_category_catalog(html)
    # 3 active distinct categories (37, 29, 1); duplicate 37 dedup'd; inactive 999 filtered
    assert len(result) == 3, f"expected 3 active categories, got {len(result)}: {result}"
    by_id = {r["id"]: r for r in result}
    assert by_id[37]["slug"] == "18-25"
    assert by_id[37]["name"] == "18-25"
    assert by_id[37]["video_count"] == 289620
    assert by_id[37]["points"] == 65005
    assert by_id[29]["slug"] == "milf"
    assert by_id[29]["video_count"] == 199835
    # Anal had no `points` field — None
    assert by_id[1]["points"] is None


def test_parse_category_catalog_filters_inactive():
    """status != 'active' rows are dropped."""
    html = _read_categories_fixture()
    result = parse_category_catalog(html)
    ids = {r["id"] for r in result}
    assert 999 not in ids, "deprecated category should be filtered"


def test_parse_category_catalog_dedupes_by_id():
    """Same id appearing multiple times produces only one output row."""
    html = _read_categories_fixture()
    result = parse_category_catalog(html)
    ids = [r["id"] for r in result]
    assert len(ids) == len(set(ids)), f"duplicates found: {ids}"


def test_parse_category_catalog_empty_when_no_blocks():
    """HTML with no category JSON returns empty list."""
    assert parse_category_catalog("<html><body><h1>nothing</h1></body></html>") == []
```

- [ ] **Step 3: Confirm RED**

```bash
./venv/bin/pytest tests/test_scraper.py -k "parse_category_catalog" -v
```

Expected: `ImportError` — function doesn't exist.

- [ ] **Step 4: Implement the parser**

In `/Users/ansvier/ph-heatmap/scraper.py`, near the other parse helpers, add:

```python
import json as _json

# Matches a JSON object literal containing "id", "slug", "video_count", and "status" keys.
# Uses [^{}] to disallow nested braces — category objects in PH's HTML are flat.
_CATEGORY_BLOCK_RE = re.compile(
    r'\{[^{}]*?"id"\s*:\s*\d+[^{}]*?"slug"\s*:\s*"[^"]+"[^{}]*?"video_count"\s*:\s*\d+[^{}]*?\}'
)


def parse_category_catalog(html: str) -> list[dict]:
    """Extract the embedded category catalog from PH's /categories page HTML.

    Returns [{id, slug, name, video_count, points}, ...] with:
      - status == "active" entries only (filters soft-deleted)
      - deduped by id (PH duplicates entries in cross-category panels)
      - points may be None when the field is absent in the source JSON
    """
    out: list[dict] = []
    seen_ids: set[int] = set()
    for match in _CATEGORY_BLOCK_RE.finditer(html):
        block = match.group(0)
        try:
            obj = _json.loads(block)
        except _json.JSONDecodeError:
            continue
        if obj.get("status") != "active":
            continue
        cid = obj["id"]
        if cid in seen_ids:
            continue
        seen_ids.add(cid)
        out.append({
            "id": cid,
            "slug": obj["slug"],
            "name": obj["name"],
            "video_count": obj["video_count"],
            "points": obj.get("points"),
        })
    return out
```

- [ ] **Step 5: Confirm GREEN**

```bash
./venv/bin/pytest tests/test_scraper.py -k "parse_category_catalog" -v
```

Expected: 4 passed.

- [ ] **Step 6: Full suite**

```bash
./venv/bin/pytest -q
```

Expected: 55 + 4 = 59 passed.

- [ ] **Step 7: Commit**

```bash
git add scraper.py tests/test_scraper.py tests/fixtures/categories_catalog.html
git commit -m "$(cat <<'EOF'
feat(scraper): parse_category_catalog from /categories embedded JSON

PH's /categories page embeds the full category catalog as JSON objects
inline in the HTML. Regex-extracts each {id, slug, name, video_count,
points} block, dedupes by id (PH duplicates in cross-category panels),
filters to status='active'. Verified ~189 active categories per page.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `fetch_category_catalog`

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/scraper.py`
- Modify: `/Users/ansvier/ph-heatmap/tests/test_scraper.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_scraper.py`:

```python
def test_fetch_category_catalog_hits_categories_url(monkeypatch):
    """fetch_category_catalog calls /categories once and returns parsed entries."""
    captured = {}

    def fake_fetch(url, impersonate=None):
        captured["url"] = url
        return (_read_categories_fixture(), 200)

    import scraper
    monkeypatch.setattr(scraper, "_fetch", fake_fetch)

    result = scraper.fetch_category_catalog()
    assert captured["url"] == "https://www.pornhub.com/categories"
    assert len(result) == 3
    assert {r["id"] for r in result} == {37, 29, 1}
```

- [ ] **Step 2: Confirm RED**

```bash
./venv/bin/pytest tests/test_scraper.py::test_fetch_category_catalog_hits_categories_url -v
```

Expected: `AttributeError: module 'scraper' has no attribute 'fetch_category_catalog'`.

- [ ] **Step 3: Implement**

In `/Users/ansvier/ph-heatmap/scraper.py`, after `fetch_profile` (or near other `fetch_*` helpers), add:

```python
_CATEGORIES_CATALOG_URL = "https://www.pornhub.com/categories"


def fetch_category_catalog() -> list[dict]:
    """Fetch PH's /categories page once and parse the embedded catalog.

    Returns [{id, slug, name, video_count, points}, ...] for all active
    categories. ~5 seconds per call. Exceptions from _fetch propagate;
    callers (run.py) wrap in try/except.
    """
    body, _status = _fetch(_CATEGORIES_CATALOG_URL)
    return parse_category_catalog(body)
```

- [ ] **Step 4: Confirm GREEN + full suite**

```bash
./venv/bin/pytest tests/test_scraper.py -k fetch_category_catalog -v
./venv/bin/pytest -q
```

Expected: targeted test passes; full suite 60.

- [ ] **Step 5: Commit**

```bash
git add scraper.py tests/test_scraper.py
git commit -m "$(cat <<'EOF'
feat(scraper): fetch_category_catalog wraps _fetch + parse

One GET to PH's /categories URL, returning the parsed active catalog.
~5 seconds per call. Used by run.py daily-scrape integration.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Extend `_OG_TYPE_BY_PAGE_TYPE` and `Literal`

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/heatmap.py`
- Modify: `/Users/ansvier/ph-heatmap/tests/test_heatmap.py`

Tiny task — 2 lines of code + 1 test.

- [ ] **Step 1: Write failing test**

Append to `tests/test_heatmap.py`:

```python
def test_render_seo_head_supports_category_page_type():
    """page_type='category' maps to og:type='website' and emits without error."""
    head = _render_seo_head(
        page_type="category",
        title="Trending Pornhub Categories",
        description="…",
        canonical_url="https://hotmap.cam/categories/",
    )
    assert 'property="og:type" content="website"' in head
```

- [ ] **Step 2: Confirm RED**

```bash
./venv/bin/pytest tests/test_heatmap.py::test_render_seo_head_supports_category_page_type -v
```

Expected: `KeyError: 'category'`.

- [ ] **Step 3: Add the entry**

In `heatmap.py`, find `_OG_TYPE_BY_PAGE_TYPE` (around line 652). It currently looks like:

```python
_OG_TYPE_BY_PAGE_TYPE = {
    "home": "website",
    "mode": "website",
    "stats": "article",
    "charts": "website",
    "performer": "profile",
}
```

Add the `"category"` entry:

```python
_OG_TYPE_BY_PAGE_TYPE = {
    "home": "website",
    "mode": "website",
    "stats": "article",
    "charts": "website",
    "performer": "profile",
    "category": "website",
}
```

Update the `Literal` annotation on `_render_seo_head`:

```python
def _render_seo_head(
    *,
    page_type: Literal["home", "mode", "stats", "charts", "performer", "category"],
    ...
```

- [ ] **Step 4: Confirm GREEN + full suite**

```bash
./venv/bin/pytest -q
```

Expected: 61 passed.

- [ ] **Step 5: Commit**

```bash
git add heatmap.py tests/test_heatmap.py
git commit -m "$(cat <<'EOF'
feat(seo): page_type='category' for /categories/

og:type='website'; downstream JSON-LD is CollectionPage when callers
pass it via extra_jsonld.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: `render_categories_treemap`

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/heatmap.py`
- Modify: `/Users/ansvier/ph-heatmap/tests/test_heatmap.py`

The largest task. New page-template constant + render function reusing Plotly Treemap pattern.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_heatmap.py`:

```python
def _category_snapshots_fixture(with_baseline: bool = True) -> pd.DataFrame:
    """Two-day fixture: 3 categories today, baseline yesterday for delta math.

    When with_baseline=False, only today's rows are returned (simulates
    first-deploy state with no growth data available yet).
    """
    today = pd.Timestamp("2026-06-02")
    yesterday = pd.Timestamp("2026-06-01")
    today_rows = [
        {"snapshot_date": today, "category_id": 37, "slug": "18-25",
         "name": "18-25", "video_count": 289700, "points": 65005},
        {"snapshot_date": today, "category_id": 29, "slug": "milf",
         "name": "MILF", "video_count": 199900, "points": 12500},
        {"snapshot_date": today, "category_id": 1, "slug": "anal",
         "name": "Anal", "video_count": 142250, "points": None},
    ]
    if not with_baseline:
        return pd.DataFrame(today_rows)
    baseline_rows = [
        {"snapshot_date": yesterday, "category_id": 37, "slug": "18-25",
         "name": "18-25", "video_count": 289620, "points": 65000},
        {"snapshot_date": yesterday, "category_id": 29, "slug": "milf",
         "name": "MILF", "video_count": 199835, "points": 12490},
        {"snapshot_date": yesterday, "category_id": 1, "slug": "anal",
         "name": "Anal", "video_count": 142217, "points": None},
    ]
    return pd.DataFrame(baseline_rows + today_rows)


def test_render_categories_treemap_writes_html(tmp_path):
    """Full happy path: 2 days of data, page renders with names/counts/canonical/SEO."""
    df = _category_snapshots_fixture(with_baseline=True)
    out = tmp_path / "categories.html"
    render_categories_treemap(df, out)
    assert out.exists()
    content = out.read_text()

    # Page chrome
    assert "<html" in content.lower()
    assert "Trending" in content                              # title pattern
    assert 'rel="canonical" href="https://hotmap.cam/categories/"' in content
    assert 'property="og:type" content="website"' in content

    # Category names appear on the page
    assert "MILF" in content
    assert "18-25" in content
    assert "Anal" in content

    # Treemap (Plotly) is embedded
    assert "plotly" in content.lower()

    # JSON-LD includes CollectionPage + BreadcrumbList
    blocks = _extract_jsonld_blocks(content)
    types = {b.get("@type") for b in blocks}
    assert "CollectionPage" in types and "BreadcrumbList" in types, f"got types={types}"


def test_render_categories_treemap_no_baseline(tmp_path):
    """First deploy state — only today's snapshot, no baseline. Page still renders,
    delta labels show '—' (no growth data yet). No error."""
    df = _category_snapshots_fixture(with_baseline=False)
    out = tmp_path / "categories.html"
    render_categories_treemap(df, out)
    content = out.read_text()
    # Names still present
    assert "MILF" in content
    # Page rendered successfully (we don't pin the exact "—" position because
    # Plotly may embed it inside JSON-encoded label data)
    assert "plotly" in content.lower()


def test_render_categories_treemap_raises_on_empty(tmp_path):
    """Empty DataFrame → ValueError, caller in run.py handles."""
    with pytest.raises(ValueError, match="No category snapshots"):
        render_categories_treemap(pd.DataFrame(columns=[
            "snapshot_date", "category_id", "slug", "name", "video_count", "points"
        ]), tmp_path / "out.html")
```

- [ ] **Step 2: Confirm RED**

```bash
./venv/bin/pytest tests/test_heatmap.py -k render_categories_treemap -v
```

Expected: 3 failures (`ImportError: render_categories_treemap`).

- [ ] **Step 3: Add the page template constant**

In `/Users/ansvier/ph-heatmap/heatmap.py`, near the other page-template constants (search for `_CHARTS_PAGE_TEMPLATE` or `_STATS_PAGE_TEMPLATE` to find the location), add `_CATEGORIES_PAGE_TEMPLATE`. Reuse the same chrome pattern as `_STATS_PAGE_TEMPLATE` (read it first to see exact shape — `{seo_head}` placeholder, top-nav block, footer):

```python
_CATEGORIES_PAGE_TEMPLATE = """<!doctype html>
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
    footer {{ margin-top: 48px; padding-top: 24px; border-top: 1px solid var(--rule); color: var(--muted); font-size: 13px; }}
    footer a {{ color: var(--muted); text-decoration: underline; }}
  </style>
</head>
<body>
{nav_html}
<h1>Trending categories on Pornhub</h1>
<p class="subtitle">{n_categories} categories tracked · Updated {last_updated} UTC</p>
{treemap}
<footer>
  <p>HotMap is an independent project. Category data scraped from publicly visible Pornhub HTML. <a href="/">Back to homepage</a>.</p>
</footer>
</body>
</html>
"""
```

(Use the same `_TOP_NAV_CSS` and `_top_nav(active)` helpers that the existing `render_stats_page` and `render_charts_page` use. If those names differ in the actual codebase, follow whatever pattern those two functions use.)

- [ ] **Step 4: Implement `render_categories_treemap`**

In `heatmap.py`, near `render_charts_page`, add:

```python
def render_categories_treemap(
    category_snapshots: pd.DataFrame,
    output_path: Path | str,
) -> None:
    """Render /categories/index.html — treemap of PH category video counts.

    Tile size  = video_count (latest snapshot)
    Tile color = percentile rank of 1-day delta (today − yesterday). When no
                 yesterday snapshot exists for a category, that tile gets a
                 neutral color and delta label '—'.
    Tile label = '<name>\\n<count compact>\\n+<delta> today' (or '—' when no baseline).

    Raises ValueError on empty input — caller (run.py) treats as 'skip render this day'.
    """
    if category_snapshots.empty:
        raise ValueError("No category snapshots provided")

    df = category_snapshots.copy()
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    latest_date = df["snapshot_date"].max()
    today = df[df["snapshot_date"] == latest_date].set_index("category_id")

    # Find the most recent date strictly before latest — that's the 1-day baseline.
    # (Could be exactly 1 day prior, or longer if a scrape was missed.)
    prior_dates = df[df["snapshot_date"] < latest_date]["snapshot_date"]
    if not prior_dates.empty:
        baseline_date = prior_dates.max()
        baseline = (
            df[df["snapshot_date"] == baseline_date]
            .set_index("category_id")["video_count"]
            .rename("prev_count")
        )
        today = today.join(baseline, how="left")
    else:
        today["prev_count"] = pd.NA

    today["delta"] = today["video_count"] - today["prev_count"]
    today["has_delta"] = today["delta"].notna()

    # Color metric: percentile rank of delta within categories that have one.
    # Categories without a delta get color_value=0 (neutral mid-scale).
    if today["has_delta"].any() and today["has_delta"].sum() > 1:
        ranked = today.loc[today["has_delta"], "delta"].rank(method="average", pct=True) - 0.5
        today["color_value"] = 0.0
        today.loc[today["has_delta"], "color_value"] = ranked
    else:
        today["color_value"] = 0.0

    # Build display labels
    def _compact(n):
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.0f}K"
        return str(int(n))

    def _delta_label(row):
        if not row["has_delta"]:
            return "—"
        d = int(row["delta"])
        return f"+{d:,}" if d >= 0 else f"{d:,}"

    today["count_label"] = today["video_count"].apply(_compact)
    today["delta_label"] = today.apply(_delta_label, axis=1)
    today["tile_text"] = (
        "<b>" + today["name"] + "</b>"
        + "<br><span style='font-size:11px;color:rgba(0,0,0,0.55)'>"
        + today["count_label"] + "</span>"
        + "<br><span style='font-size:13px;font-weight:600'>"
        + today["delta_label"] + " today</span>"
    )

    rows = today.reset_index()

    figure = go.Figure(
        go.Treemap(
            labels=rows["tile_text"],
            ids=rows["category_id"].astype(str),
            parents=[""] * len(rows),
            values=rows["video_count"],
            marker=dict(
                colors=rows["color_value"],
                colorscale="RdYlGn",
                cmid=0,
                cmin=-0.5,
                cmax=0.5,
                showscale=True,
                colorbar=dict(
                    title="Growth (1d)",
                    tickvals=[-0.5, -0.25, 0, 0.25, 0.5],
                    ticktext=["bottom", "low", "median", "high", "top"],
                    thickness=14,
                    outlinewidth=0,
                ),
            ),
            customdata=rows[["name", "video_count", "delta", "slug"]].values,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Total videos: %{customdata[1]:,}<br>"
                "Delta (1d): %{customdata[2]:+,.0f}<br>"
                "<extra></extra>"
            ),
            textposition="middle center",
            textfont=dict(family="Inter, sans-serif", size=12, color="#000"),
            tiling=dict(packing="squarify", pad=0),
        )
    )
    figure.update_layout(
        paper_bgcolor="#0a0a0a",
        plot_bgcolor="#0a0a0a",
        margin=dict(l=0, r=130, t=0, b=0),
        height=700,
        font=dict(family="Inter, sans-serif", color="#f5f5f5"),
    )
    treemap_html = figure.to_html(include_plotlyjs="cdn", full_html=False)

    n_categories = len(rows)
    canonical_url = "https://hotmap.cam/categories/"
    title = "Trending Pornhub Categories — Daily Growth Heatmap | HotMap"
    description = (
        f"{n_categories} Pornhub categories ranked by daily video-count growth. "
        f"Real numbers, updated automatically."
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
        ("Categories", canonical_url),
    ]
    seo_head = _render_seo_head(
        page_type="category",
        title=title,
        description=description,
        canonical_url=canonical_url,
        og_image_url=None,
        extra_jsonld=[collection_jsonld],
        breadcrumbs=breadcrumbs,
    )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_CATEGORIES_PAGE_TEMPLATE.format(
        seo_head=seo_head,
        nav_css=_TOP_NAV_CSS,
        nav_html=_top_nav("categories"),
        n_categories=n_categories,
        treemap=treemap_html,
        last_updated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
    ), encoding="utf-8")
```

(If the existing nav-builder helpers are named differently — e.g. `_render_top_nav` or inline — adapt to match. Read `render_charts_page` for the canonical pattern.)

- [ ] **Step 5: Confirm GREEN**

```bash
./venv/bin/pytest tests/test_heatmap.py -k render_categories_treemap -v
```

Expected: 3 passed.

- [ ] **Step 6: Full suite**

```bash
./venv/bin/pytest -q
```

Expected: 64 passed.

- [ ] **Step 7: Commit**

```bash
git add heatmap.py tests/test_heatmap.py
git commit -m "$(cat <<'EOF'
feat(heatmap): render_categories_treemap for /categories/

Single-treemap page of PH categories. Size = video_count, color =
percentile rank of 1-day delta (today minus yesterday). When the prior
day's snapshot is absent for a category (first deploy, missed scrape),
the tile renders with a neutral color and '—' delta label. SEO emits
CollectionPage + BreadcrumbList via page_type='category'.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: `_NAV_ITEMS` Categories entry + sitemap inclusion

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/heatmap.py`
- Modify: `/Users/ansvier/ph-heatmap/tests/test_heatmap.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_heatmap.py`:

```python
def test_nav_items_includes_categories():
    """The Categories nav link uses /categories/ (trailing slash, canonical form)."""
    from heatmap import _NAV_ITEMS
    hrefs = [item[1] for item in _NAV_ITEMS]
    assert "/categories/" in hrefs, f"got hrefs={hrefs}"


def test_sitemap_includes_categories_page(tmp_path):
    """Sitemap contains /categories/ entry."""
    df = _snapshot_rows()
    write_sitemap_and_robots(df, public_dir=tmp_path)
    text = (tmp_path / "sitemap.xml").read_text()
    assert "<loc>https://hotmap.cam/categories/</loc>" in text
```

- [ ] **Step 2: Confirm RED**

```bash
./venv/bin/pytest tests/test_heatmap.py -k "nav_items_includes_categories or sitemap_includes_categories" -v
```

Expected: 2 failures.

- [ ] **Step 3: Add nav entry**

In `heatmap.py`, find `_NAV_ITEMS` (around line 26). It's a list of 3-tuples `(key, href, label)`. Add `("categories", "/categories/", "Categories")` between Stats and Charts. Example final shape:

```python
_NAV_ITEMS = [
    ("map",        "/",            "Map"),
    ("stats",      "/stats/",      "Stats"),
    ("categories", "/categories/", "Categories"),
    ("charts",     "/charts/",     "Charts"),
]
```

(Read the actual current shape first — if order differs, just add the new entry at a sensible position.)

- [ ] **Step 4: Add sitemap entry**

In `write_sitemap_and_robots` (around line 2300), find the static URL list (entries for `/`, `/rising/`, `/gems/`, `/celebs/`, `/stats/`, `/charts/`). Add `/categories/` to the list. If the URLs are built via a list literal, add the entry there:

```python
# Find the list with paths like "/stats/" and add:
"/categories/",
```

- [ ] **Step 5: Confirm GREEN + full suite**

```bash
./venv/bin/pytest -q
```

Expected: 66 passed.

- [ ] **Step 6: Commit**

```bash
git add heatmap.py tests/test_heatmap.py
git commit -m "$(cat <<'EOF'
feat(heatmap): /categories/ in top nav + sitemap

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: `run.py` orchestration

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/run.py`

Smoke-verified, no new pytest tests.

- [ ] **Step 1: Update imports**

At the top of `run.py`, find the existing `from heatmap import ...` line and add `render_categories_treemap`:

```python
from heatmap import dump_json, render_categories_treemap, render_charts_page, render_performer_page, render_stats_page, render_treemap_page, write_sitemap_and_robots
```

Find the existing `from db import ...` line and add `CategorySnapshot`, `insert_category_snapshot`, `load_all_category_snapshots`:

```python
from db import CategorySnapshot, init_db, insert_category_snapshot, insert_snapshot, load_all_category_snapshots, load_all_snapshots
```

Find the existing `from scraper import ...` line and add `fetch_category_catalog`:

```python
from scraper import fetch_category_catalog, polite_sleep
```

(Keep the existing imports; just add these.)

- [ ] **Step 2: Add categories fetch block before performer scrape**

In `main()`, find the block that prints `[YYYY-MM-DD] starting snapshot run` and immediately follows with `for gender in GENDERS:`. **Before** that gender loop, add:

```python
    # ---- Categories snapshot (cheap, 1 GET) ----
    try:
        catalog = fetch_category_catalog()
        print(f"fetched {len(catalog)} categories", flush=True)
    except Exception as exc:
        print(f"  WARN: fetch_category_catalog failed: {exc}", file=sys.stderr)
        catalog = []
```

This runs BEFORE the existing performer scrape. The conn isn't open yet — we insert later, after `init_db`.

- [ ] **Step 3: Insert category snapshot after init_db**

Find the line `conn = init_db(DB_PATH)` (it's followed by `insert_snapshot(conn, all_rows)`). **After** `insert_snapshot(...)`, insert:

```python
    # Persist category snapshot from the fetch above.
    if catalog:
        category_rows = [
            CategorySnapshot(
                snapshot_date=today, category_id=c["id"], slug=c["slug"],
                name=c["name"], video_count=c["video_count"], points=c.get("points"),
            )
            for c in catalog
        ]
        insert_category_snapshot(conn, category_rows)
        print(f"stored {len(category_rows)} category rows", flush=True)
```

- [ ] **Step 4: Add render call before write_sitemap_and_robots**

Find the call to `render_charts_page(snapshots_df, charts_dir / "index.html")`. Right after it (before the `write_sitemap_and_robots` call), add:

```python
    # /categories/ — daily treemap of PH category video-counts
    category_snapshots = load_all_category_snapshots(conn)
    if not category_snapshots.empty:
        categories_dir = PUBLIC_DIR / "categories"
        categories_dir.mkdir(exist_ok=True)
        try:
            render_categories_treemap(category_snapshots, categories_dir / "index.html")
            print(f"wrote /categories/index.html", flush=True)
        except ValueError as exc:
            print(f"  WARN: render_categories_treemap skipped: {exc}", file=sys.stderr)
    else:
        print("no category snapshots in db yet — skipping /categories/ render", flush=True)
```

- [ ] **Step 5: Smoke run against existing data**

```bash
cd /Users/ansvier/ph-heatmap
./venv/bin/python -c "
from pathlib import Path
from db import init_db, load_all_category_snapshots
from heatmap import render_categories_treemap

PUBLIC_DIR = Path('public')
conn = init_db('data.db')
df = load_all_category_snapshots(conn)
print(f'category_snapshots rows: {len(df)}')
if df.empty:
    print('No snapshots yet — Task 9 bootstrap will populate. Skipping render smoke.')
else:
    (PUBLIC_DIR / 'categories').mkdir(exist_ok=True)
    render_categories_treemap(df, PUBLIC_DIR / 'categories' / 'index.html')
    print('wrote /categories/index.html')
"
```

Expected: prints the row count. If 0 (expected before Task 9 bootstrap), prints the "No snapshots yet" message — that's fine. If row count > 0 from any prior smoke, render runs successfully.

- [ ] **Step 6: Commit**

```bash
git add run.py
git commit -m "$(cat <<'EOF'
feat(run): integrate categories scrape + render

Three additions to the daily orchestration:
  1. fetch_category_catalog() up front (one GET, ~5s)
  2. insert_category_snapshot() after init_db
  3. render_categories_treemap() after charts, before sitemap

All gated on success: a failed fetch logs WARN and skips the insert;
an empty snapshot table skips the render. Daily-scrape stays robust
under transient PH issues.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: README subsection

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/README.md`

- [ ] **Step 1: Find a good spot and insert**

Open `/Users/ansvier/ph-heatmap/README.md`. Find the "Features" or "Pages" section (or any section describing the kinds of pages on the site). Add this paragraph:

```markdown
### Trending Categories

Daily snapshot of all ~189 PH categories (from `/categories`) into a treemap at `/categories/`. Tile size encodes total `video_count`; tile color encodes today's growth percentile within the category set. Single GET per day, ~5 seconds. After the first day of accumulated history, the page tells which categories are adding videos fastest. No per-category landing pages yet (deferred); this is one summary view of the catalog.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "$(cat <<'EOF'
docs: README subsection for Trending Categories

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Bootstrap snapshot + E2E render + push

**Files:** none (operational only).

This is the human-triggered final step. Bootstraps today's snapshot so the live site shows real counts immediately on deploy.

- [ ] **Step 1: Bootstrap snapshot (manual one-shot)**

```bash
cd /Users/ansvier/ph-heatmap
./venv/bin/python -c "
from datetime import date
from db import init_db, insert_category_snapshot, CategorySnapshot, load_all_category_snapshots
from scraper import fetch_category_catalog

conn = init_db('data.db')
catalog = fetch_category_catalog()
print(f'fetched {len(catalog)} categories')
today = date.today()
rows = [CategorySnapshot(snapshot_date=today, category_id=c['id'], slug=c['slug'],
                          name=c['name'], video_count=c['video_count'], points=c.get('points'))
        for c in catalog]
insert_category_snapshot(conn, rows)
df = load_all_category_snapshots(conn)
print(f'stored {len(rows)} rows; db now has {len(df)} total category-snapshot rows')
print('Top 5 by video_count today:')
print(df.sort_values('video_count', ascending=False).head(5)[['name', 'video_count']])
"
```

Expected: `fetched ~189 categories`. Top 5 shows the largest (`18-25` ~289K, `MILF` ~199K, etc.).

If the fetch fails or returns <50 categories, STOP — PH may have changed the embedded JSON shape; investigate before deploying.

- [ ] **Step 2: Render all pages with categories included**

```bash
./venv/bin/python -c "
from pathlib import Path
from db import init_db, load_all_snapshots, load_all_category_snapshots
from heatmap import dump_json, render_categories_treemap, render_charts_page, render_performer_page, render_stats_page, render_treemap_page, write_sitemap_and_robots

PUBLIC_DIR = Path('public')
conn = init_db('data.db')
snapshots = load_all_snapshots(conn)
category_snapshots = load_all_category_snapshots(conn)
print(f'snapshots: {len(snapshots)}, category_snapshots: {len(category_snapshots)}')

# Re-render existing surfaces
render_treemap_page(snapshots, PUBLIC_DIR / 'index.html', default_mode='rising', canonical_path='/', seo_key='home')
for mode in ('rising', 'gems', 'celebs'):
    (PUBLIC_DIR / mode).mkdir(exist_ok=True)
    render_treemap_page(snapshots, PUBLIC_DIR / mode / 'index.html', default_mode=mode, canonical_path=f'/{mode}/', seo_key=mode)
dump_json(snapshots, PUBLIC_DIR / 'data.json')
(PUBLIC_DIR / 'p').mkdir(parents=True, exist_ok=True)
n_perf = 0
for slug in snapshots['slug'].unique():
    try:
        render_performer_page(snapshots, slug=slug, output_path=PUBLIC_DIR / 'p' / f'{slug}.html')
        n_perf += 1
    except Exception as exc:
        print(f'WARN perf {slug}: {exc}')
print(f'wrote {n_perf} performer pages')
(PUBLIC_DIR / 'stats').mkdir(exist_ok=True)
render_stats_page(snapshots, PUBLIC_DIR / 'stats' / 'index.html')
(PUBLIC_DIR / 'charts').mkdir(exist_ok=True)
render_charts_page(snapshots, PUBLIC_DIR / 'charts' / 'index.html')

# NEW: /categories/
(PUBLIC_DIR / 'categories').mkdir(exist_ok=True)
render_categories_treemap(category_snapshots, PUBLIC_DIR / 'categories' / 'index.html')
print('wrote /categories/index.html')

write_sitemap_and_robots(snapshots, public_dir=PUBLIC_DIR)
print('done')
"
```

Expected: ~14-20 seconds. `/categories/index.html` exists.

- [ ] **Step 3: Smoke check rendered output**

```bash
echo "=== /categories/ rendered ===" 
ls -la public/categories/index.html
echo "=== Page contains categories ==="
grep -oE 'MILF|18-25|Anal|Big Tits' public/categories/index.html | sort -u | head -5
echo "=== Nav contains Categories link ==="
grep -c 'href="/categories/"' public/index.html
echo "=== Sitemap contains /categories/ ==="
grep -c 'https://hotmap.cam/categories/' public/sitemap.xml
```

Expected: file exists, several category names visible, nav and sitemap link present.

- [ ] **Step 4: Commit re-render + data.db update**

```bash
git status -s | head -10
git add data.db public/
git commit -m "$(cat <<'EOF'
chore(data+render): bootstrap Trending Categories — first snapshot live

One-off pre-deploy snapshot of PH's category catalog (~189 active
categories). Daily-scrape will write the second snapshot tomorrow
~05:00 UTC; from then on the /categories/ treemap colors by real
1-day deltas.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5: Push**

```bash
git pull --rebase origin main 2>&1 | tail -3
git push 2>&1 | tail -3
```

- [ ] **Step 6: Verify live after ~60s deploy**

```bash
sleep 60
echo "=== /categories/ HTTP status ==="
curl -sI https://hotmap.cam/categories/ | head -1
echo "=== Page mentions top category ==="
curl -s https://hotmap.cam/categories/ | grep -oE 'MILF|18-25|Anal' | head -3
echo "=== Sitemap has /categories/ entry ==="
curl -s https://hotmap.cam/sitemap.xml | grep -c 'hotmap.cam/categories/'
```

Expected: HTTP 200, category names visible, sitemap entry present.

If 404 → CF Pages deploy still in progress, retry in 60s.

---

## Self-review checklist (filled out by plan author)

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| `category_snapshots` table with PK `(snapshot_date, category_id)` | Task 1 |
| `CategorySnapshot` dataclass | Task 1 |
| `insert_category_snapshot`, `load_all_category_snapshots` | Task 1 |
| `parse_category_catalog` with dedup + status filter | Task 2 |
| HTML fixture | Task 2 |
| `fetch_category_catalog` (one GET to /categories) | Task 3 |
| `_OG_TYPE_BY_PAGE_TYPE["category"]` + Literal | Task 4 |
| `_CATEGORIES_PAGE_TEMPLATE` + `render_categories_treemap` | Task 5 |
| Size = video_count, color = 1d delta percentile | Task 5 |
| Empty/no-baseline edge cases | Task 5 |
| `_NAV_ITEMS` Categories entry | Task 6 |
| Sitemap inclusion | Task 6 |
| run.py 3-line fetch+insert + 1-line render | Task 7 |
| README subsection | Task 8 |
| Bootstrap snapshot pre-deploy | Task 9 |
| E2E render + push + live verify | Task 9 |

No gaps.

**Placeholder scan:** No TBD / TODO. Every code step has the exact code; every command step has the exact command + expected output.

**Type consistency:** `CategorySnapshot` dataclass fields match table columns and test assertions. `category: pd.DataFrame` shape (six columns) consistent across `load_all_category_snapshots`, `render_categories_treemap` test fixtures, and run.py call. `parse_category_catalog` return shape `[{id, slug, name, video_count, points}]` consistent across Task 2 (parser), Task 3 (fetch), and Task 7 (run.py loop building `CategorySnapshot` from each dict).

**Conditional / risk notes:**
- Task 5's template references `_TOP_NAV_CSS` and `_top_nav("categories")`. The implementer must verify the exact existing helper names by reading `render_stats_page` and `render_charts_page` and follow the same pattern. If those use a different signature, adapt — don't introduce new helpers.
- Task 7's bootstrap step (Task 9) is the only step that hits PH live. If the fetch fails or returns 0 categories, the implementer should STOP and surface — the parser pinning fixture in Task 2 is the canary for HTML shape changes.
- Test count expectations: 52 → 55 (Task 1) → 59 (Task 2) → 60 (Task 3) → 61 (Task 4) → 64 (Task 5) → 66 (Task 6) → 66 (Tasks 7-9, no new pytest tests).
