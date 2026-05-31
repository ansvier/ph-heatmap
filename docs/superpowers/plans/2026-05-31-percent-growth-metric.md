# Percent-growth treemap metric — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Switch treemap tile-size encoding from absolute views-gained to % growth, with a 1M-views minimum-baseline filter, across all three tiers.

**Architecture:** Single function changes in `heatmap.py:_build_treemap_figure`. The percentile-rank coloring already runs on `growth_pct`, the cohort sort already runs on `growth_pct` — only the `values=` argument fed to Plotly's `Treemap` changes, plus a baseline-noise filter. Two new unit tests pin the new behavior at the figure-build level (we inspect `fig.data[0].values` and `fig.data[0].ids` directly — that's what Plotly exposes).

**Tech Stack:** Python 3.13, pandas, plotly, pytest.

**Spec:** `docs/superpowers/specs/2026-05-31-percent-growth-metric-design.md`

---

## File map

| File | Change |
|---|---|
| `heatmap.py` | Modify `_build_treemap_figure` (~5 prod lines + docstring rewrite) |
| `tests/test_heatmap.py` | Append two new tests against `_build_treemap_figure` |
| `README.md` | Update one sentence about tile-size encoding |

No new files. No DB / scraper / template / route changes.

---

### Task 1: Failing test — pct-rank wins over abs-rank for tile size

**Files:**
- Modify: `tests/test_heatmap.py` (append at end of file)

**Goal:** A performer with smaller absolute delta but higher % growth must produce a larger tile value than a performer with bigger absolute delta but lower % growth. Pins the new size metric.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_heatmap.py`:

```python
from heatmap import _build_treemap_figure


def _window_df(rows):
    """Build the per-slug DataFrame that _build_treemap_figure consumes.

    Matches compute_window_growth's output: index=slug, cols=name, total_views,
    prev_views, growth_pct, gender.
    """
    df = pd.DataFrame(rows).set_index("slug")
    df["growth_pct"] = (df["total_views"] - df["prev_views"]) / df["prev_views"] * 100
    return df


def test_build_treemap_figure_size_is_percent_growth():
    """Tile size encodes % growth, not absolute views gained.

    'big' has a larger absolute delta (+5M) but smaller % (+0.25%).
    'rising' has a smaller absolute delta (+2M) but larger % (+4%).
    Under the new metric, 'rising' must get the larger tile value.
    """
    window = _window_df([
        {"slug": "big",    "name": "Big",    "total_views": 2_005_000_000, "prev_views": 2_000_000_000, "gender": "female"},
        {"slug": "rising", "name": "Rising", "total_views":    52_000_000, "prev_views":    50_000_000, "gender": "female"},
    ])

    fig = _build_treemap_figure(window, window_days=1)

    values_by_id = dict(zip(fig.data[0].ids, fig.data[0].values))
    assert values_by_id["rising"] > values_by_id["big"], (
        f"Expected rising tile > big tile under % metric; "
        f"got rising={values_by_id['rising']}, big={values_by_id['big']}"
    )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/ansvier/ph-heatmap
./venv/bin/pytest tests/test_heatmap.py::test_build_treemap_figure_size_is_percent_growth -v
```

Expected: FAIL with `Expected rising tile > big tile` (because current code passes `growth_amount` as values; `big` gets value 5_000_000 and `rising` gets 2_000_000).

---

### Task 2: Failing test — 1M baseline filter excludes micro-accounts

**Files:**
- Modify: `tests/test_heatmap.py` (append)

**Goal:** Performers with `prev_views < 1_000_000` are dropped before rendering, regardless of how high their % growth is.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_heatmap.py`:

```python
def test_build_treemap_figure_filters_below_1m_baseline():
    """Performers with prev_views < 1M are excluded from the treemap.

    'tiny' would have +20% growth but a 500k baseline — the filter must drop
    it so micro-account noise doesn't dominate the visual.
    """
    window = _window_df([
        {"slug": "tiny",   "name": "Tiny",   "total_views":   600_000, "prev_views":   500_000, "gender": "female"},
        {"slug": "normal", "name": "Normal", "total_views": 1_500_000, "prev_views": 1_400_000, "gender": "female"},
        {"slug": "big",    "name": "Big",    "total_views":   105_000_000, "prev_views":   100_000_000, "gender": "female"},
    ])

    fig = _build_treemap_figure(window, window_days=1)

    ids = list(fig.data[0].ids)
    assert "tiny" not in ids, f"Expected 'tiny' filtered out (prev_views=500k < 1M); got ids={ids}"
    assert "normal" in ids, f"Expected 'normal' kept (prev_views=1.4M); got ids={ids}"
    assert "big" in ids, f"Expected 'big' kept; got ids={ids}"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
./venv/bin/pytest tests/test_heatmap.py::test_build_treemap_figure_filters_below_1m_baseline -v
```

Expected: FAIL with `Expected 'tiny' filtered out` (no filter exists yet; 'tiny' appears in `ids`).

---

### Task 3: Implement % size metric + baseline filter

**Files:**
- Modify: `heatmap.py` (`_build_treemap_figure`, around lines 599–640)

**Goal:** Make both new tests pass without breaking existing ones.

- [ ] **Step 1: Read the current function**

```bash
./venv/bin/python -c "import inspect, heatmap; print(inspect.getsource(heatmap._build_treemap_figure))" | head -50
```

Confirm the section to edit matches:

```python
rows = window.reset_index().copy()
rows["growth_amount"] = rows["total_views"] - rows["prev_views"]
rows = rows.dropna(subset=["growth_amount", "growth_pct"]).copy()
rows["growth_amount"] = rows["growth_amount"].clip(lower=0)
```

…and the `values=rows["growth_amount"],` line in the `go.Treemap(...)` call.

- [ ] **Step 2: Edit the docstring**

In `heatmap.py`, replace the docstring of `_build_treemap_figure` (lines ~599–608) with:

```python
def _build_treemap_figure(window: pd.DataFrame, window_days: int) -> go.Figure:
    """Build one Plotly Treemap figure for a single (gender, window) view.

    Tile size encodes the % view growth over the window, so a mid-tier
    performer who accelerated shows up large even when their raw delta is
    smaller than a top-tier name's daily drip.
    Tile color is percentile rank of % growth within the visible set
    (green = running ahead of the pack, red = falling behind).
    Rows without a baseline are dropped, and rows whose baseline view count
    is below 1M are filtered out as well — they're too noisy on a % metric
    (a 100k bump on a 200k base is +50% but visually meaningless next to
    real movers).
    """
```

- [ ] **Step 3: Edit the row preparation block**

Replace the four lines:

```python
rows = window.reset_index().copy()
rows["growth_amount"] = rows["total_views"] - rows["prev_views"]
rows = rows.dropna(subset=["growth_amount", "growth_pct"]).copy()
rows["growth_amount"] = rows["growth_amount"].clip(lower=0)
```

with:

```python
rows = window.reset_index().copy()
rows["growth_amount"] = rows["total_views"] - rows["prev_views"]
rows = rows.dropna(subset=["growth_amount", "growth_pct"]).copy()
rows["growth_amount"] = rows["growth_amount"].clip(lower=0)
# Drop micro-accounts: < 1M baseline views makes the % metric too noisy
# (a +100k bump on a 200k base is +50% but visually drowns out real movers).
rows = rows[rows["prev_views"] >= 1_000_000].copy()
# Size metric: % growth, clipped to ≥0 because Plotly Treemap requires
# non-negative `values`. total_views is monotonic so this clip is defensive.
rows["tile_size"] = rows["growth_pct"].clip(lower=0)
```

- [ ] **Step 4: Switch the `values=` argument**

Find the line in the `go.Treemap(...)` call:

```python
values=rows["growth_amount"],
```

Replace with:

```python
values=rows["tile_size"],
```

Leave `customdata=rows[["name", "total_views", "growth_pct", "slug", "growth_amount"]].values,` unchanged — hover tooltip still shows both absolute and % values, that's intentional.

- [ ] **Step 5: Run both new tests**

```bash
./venv/bin/pytest tests/test_heatmap.py::test_build_treemap_figure_size_is_percent_growth tests/test_heatmap.py::test_build_treemap_figure_filters_below_1m_baseline -v
```

Expected: both PASS.

- [ ] **Step 6: Run the full heatmap test file (regression check)**

```bash
./venv/bin/pytest tests/test_heatmap.py -v
```

Expected: all tests pass. Especially `test_render_treemap_page_writes_html` — that one builds a tiny fixture (alice/bob/carol with view counts 200–1200) which is entirely below the 1M baseline filter. **If it now fails because all tiles are filtered out, that means the test fixture's view counts collide with the new filter** — see "Task 3a" below.

- [ ] **Step 7: Run the full test suite**

```bash
./venv/bin/pytest -q
```

Expected: all 26 tests pass (or 28 with the two new ones = 28).

---

### Task 3a: Adjust existing fixture if it collides with the 1M filter

**Files:**
- Modify: `tests/test_heatmap.py` — `_snapshot_rows()` (top of file, around lines 9–19)

**Goal:** Only execute this task if Task 3 / Step 6 reported failures in pre-existing tests caused by the new 1M filter. If pre-existing tests pass as-is, skip this task entirely.

- [ ] **Step 1: Confirm the collision**

If `test_render_treemap_page_writes_html` failed with an empty-figure or all-dropped-rows error from `_build_treemap_figure`, that's the collision.

- [ ] **Step 2: Scale the fixture view counts above 1M**

Replace the `_snapshot_rows()` function (lines ~9–19) with the same data but multiplied by 1,000,000 so baselines clear the filter:

```python
def _snapshot_rows():
    """Three days, three slugs with partial coverage. All female by default.

    View counts are scaled to >=1M because _build_treemap_figure drops rows
    whose prev_views fall under that threshold (the % metric noise filter).
    """
    return pd.DataFrame([
        {"snapshot_date": pd.Timestamp(date(2026, 5, 25)), "slug": "alice", "name": "Alice", "total_views": 1_000_000_000, "rank": 1, "gender": "female"},
        {"snapshot_date": pd.Timestamp(date(2026, 5, 25)), "slug": "bob",   "name": "Bob",   "total_views":   500_000_000, "rank": 2, "gender": "male"},
        {"snapshot_date": pd.Timestamp(date(2026, 5, 26)), "slug": "alice", "name": "Alice", "total_views": 1_100_000_000, "rank": 1, "gender": "female"},
        {"snapshot_date": pd.Timestamp(date(2026, 5, 26)), "slug": "bob",   "name": "Bob",   "total_views":   600_000_000, "rank": 2, "gender": "male"},
        {"snapshot_date": pd.Timestamp(date(2026, 5, 26)), "slug": "carol", "name": "Carol", "total_views":   200_000_000, "rank": 3, "gender": "female"},
        {"snapshot_date": pd.Timestamp(date(2026, 5, 27)), "slug": "alice", "name": "Alice", "total_views": 1_200_000_000, "rank": 1, "gender": "female"},
        {"snapshot_date": pd.Timestamp(date(2026, 5, 27)), "slug": "carol", "name": "Carol", "total_views":   300_000_000, "rank": 2, "gender": "female"},
    ])
```

- [ ] **Step 3: Re-run the full suite**

```bash
./venv/bin/pytest -q
```

Expected: all tests pass (28 total).

---

### Task 4: Update README

**Files:**
- Modify: `README.md`

**Goal:** Stop lying about what tile size means.

- [ ] **Step 1: Find the section**

Open `README.md`, find the line in the "What the treemap shows" section:

> Each tier is sliced by **gender** (All / Female / Male) and **window** (1d / 7d / 30d). The treemap colors performers by percentile rank within the cohort — bright green = running ahead of the pack, red = falling behind. Tile size encodes absolute views gained in the window.

- [ ] **Step 2: Rewrite the last sentence**

Replace:

> Tile size encodes absolute views gained in the window.

with:

> Tile size encodes **% view growth** over the window (performers with under 1M baseline views are filtered out to keep the visual focused on meaningful movers). Hover any tile to see both the absolute and percent numbers.

---

### Task 5: Local smoke-render against real data

**Files:**
- No file changes — render check only.

**Goal:** Confirm the change produces a sane-looking page against the production `data.db` before committing.

- [ ] **Step 1: Render one page to a tmp location**

```bash
cd /Users/ansvier/ph-heatmap
./venv/bin/python -c "
import sqlite3, pandas as pd, pathlib
from heatmap import render_treemap_page
conn = sqlite3.connect('data.db')
df = pd.read_sql('SELECT snapshot_date, slug, name, total_views, rank, gender FROM snapshots', conn)
df['snapshot_date'] = pd.to_datetime(df['snapshot_date'])
out = pathlib.Path('/tmp/hotmap-smoke.html')
render_treemap_page(df, out, default_mode='rising', canonical_path='/', seo_key='home')
print(f'wrote {out}, size={out.stat().st_size}')
"
```

Expected: prints something like `wrote /tmp/hotmap-smoke.html, size=2500000` (rough). No exceptions.

- [ ] **Step 2: Eyeball one cohort's top tile**

```bash
./venv/bin/python -c "
import sqlite3, pandas as pd
from heatmap import compute_window_growth, _RISING_RANK_RANGE
conn = sqlite3.connect('data.db')
df = pd.read_sql('SELECT snapshot_date, slug, name, total_views, rank, gender FROM snapshots', conn)
w = compute_window_growth(df, window_days=1, gender='female')
w = w[w['prev_views'] >= 1_000_000].dropna(subset=['growth_pct'])
# Apply Rising Stars rank filter: ranks 51-250 by today's total_views.
w = w.sort_values('total_views', ascending=False)
w['rank'] = range(1, len(w) + 1)
rising = w[(w['rank'] >= 51) & (w['rank'] <= 250)]
print('Top 5 Rising Stars (female, 1d) by % growth:')
for slug, row in rising.nlargest(5, 'growth_pct').iterrows():
    print(f\"  {row['growth_pct']:+.2f}%  +{int(row['total_views']-row['prev_views']):>10,}  rank=#{int(row['rank']):>3}  {slug}\")
"
```

Expected: top tiles show meaningfully different names from the absolute-growth top-10 we saw earlier (which was yasmina-khan, martina-smeraldi, …). Whoever they are, this confirms the metric flip changes the visual.

If the output looks degenerate (all 0%, single name 99x bigger than the rest, etc.) — STOP. Inspect before committing.

- [ ] **Step 3: Quick visual check (optional)**

```bash
open /tmp/hotmap-smoke.html
```

Eyeball: tile sizes should vary plausibly, hover shows both `+N% · +M views`, page renders without console errors.

---

### Task 6: Commit and push

**Files:**
- Commit: `heatmap.py`, `tests/test_heatmap.py`, `README.md`

- [ ] **Step 1: Check status**

```bash
git status
git diff --stat
```

Expected: 3 files modified.

- [ ] **Step 2: Commit**

```bash
git add heatmap.py tests/test_heatmap.py README.md
git commit -m "$(cat <<'EOF'
feat(heatmap): switch tile-size encoding from absolute to % growth

The treemap's "Rising Stars" tier was visually static day-to-day because
tile size encoded raw views gained — high-volume performers naturally
out-accrue mid-tier ones at any growth rate, so the same names always
dominated. Switching tile size to % growth (with a 1M-baseline noise
filter) lets accelerating mid-tier performers actually show up large.

Spec: docs/superpowers/specs/2026-05-31-percent-growth-metric-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3: Push**

```bash
git push
```

Expected: push succeeds. Cloudflare Pages will auto-deploy from `main`.

- [ ] **Step 4: Verify live**

Wait ~60 seconds, then:

```bash
curl -s "https://hotmap.cam/" | grep -oE "Updated [0-9-]+ [0-9:]+ UTC" | head -1
```

The "Updated" timestamp won't change (this is a render-logic change, not a data refresh), but the page should still serve. Hard-refresh in browser (Cmd+Shift+R) to see new tiles.

---

## Self-review checklist (filled out by plan author)

**Spec coverage:**
- ✅ Replace absolute with % growth as size metric → Task 3 Step 4
- ✅ 1M baseline filter → Task 3 Step 3
- ✅ All three tiers (no tier-specific branching) → naturally covered; `_build_treemap_figure` is tier-agnostic
- ✅ Update docstring → Task 3 Step 2
- ✅ Two new tests → Tasks 1 and 2
- ✅ README update → Task 4
- ✅ No DB / schema / page-count changes → confirmed by file map

**Placeholder scan:** No TBD / TODO / "implement later". All code blocks complete.

**Type consistency:** New column `tile_size` is introduced in Task 3 Step 3 and consumed in Step 4. `growth_amount` is preserved (still used for `customdata` and intermediate steps). `prev_views` is the column name pandas produces from `compute_window_growth` (verified by reading `heatmap.py` lines 577–581).

**Risk note:** Task 3a is conditional — only runs if existing fixtures collide with the new filter. The existing `_snapshot_rows()` fixture uses view counts 200–1200, all well below 1M, so the collision is **highly likely**; Task 3a will probably need to execute. Engineer should expect to do it.
