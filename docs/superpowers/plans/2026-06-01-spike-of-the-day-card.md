# Spike of the Day card — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the static "highest growth %" selection in the "of the day" card with acceleration-based selection (today vs 7d baseline), and add a TODAY/USUAL contrast block so the displayed numbers explain the pick.

**Architecture:** Three layers — a pure `_compute_acceleration()` helper, an `acceleration` column attached by `compute_window_growth` only for `window_days=1`, and selection + contrast-rendering logic inside `_build_top_performer_card`. Treemap and all other pages are untouched. Fallback to current `growth_pct` selection when no slug in the cohort has enough history.

**Tech Stack:** Python 3.13, pandas, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-01-spike-of-the-day-card-design.md`

---

## File map

| File | Change |
|---|---|
| `heatmap.py` | Add `_compute_acceleration()`, extend `compute_window_growth`, rewrite selection + render block in `_build_top_performer_card`, add CSS for the contrast rows |
| `tests/test_heatmap.py` | 5 new tests covering: helper formula, NaN fallback, card selection, contrast rendering, fallback rendering |

No new files. No DB / route / template / sitemap changes.

---

### Task 1: `_compute_acceleration()` helper

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/heatmap.py` (add helper after `compute_window_growth`)
- Modify: `/Users/ansvier/ph-heatmap/tests/test_heatmap.py` (append tests)

Pure function. No callers yet — Task 2 wires it into `compute_window_growth`.

- [ ] **Step 1: Write the failing tests**

Append to `/Users/ansvier/ph-heatmap/tests/test_heatmap.py`:

```python
from heatmap import _compute_acceleration


def _make_history(slug_views: dict[str, list[float]], start_date: str = "2026-05-25") -> pd.DataFrame:
    """Build a snapshots DataFrame from {slug: [view_day0, view_day1, ...]}.

    Each list element is a daily total_views snapshot. All slugs same gender (female).
    """
    rows = []
    for slug, views in slug_views.items():
        for i, v in enumerate(views):
            d = pd.Timestamp(start_date) + pd.Timedelta(days=i)
            rows.append({
                "snapshot_date": d, "slug": slug, "name": slug.title(),
                "total_views": v, "rank": 1, "gender": "female",
            })
    return pd.DataFrame(rows)


def test_compute_acceleration_returns_today_vs_7d_avg():
    """Acceleration = today's daily growth % minus mean of prior 7 daily growths."""
    # 8 days. Daily growths: +1% each day for 7 days, then +5% on day 8.
    # Daily growth days 1..7: each = 1.0 (in pct). Mean of prior 7 = 1.0.
    # Today (day 8) growth = 5.0. Acceleration = 5.0 - 1.0 = 4.0.
    df = _make_history({
        "spiker": [
            1_000.0, 1_010.0, 1_020.10, 1_030.30, 1_040.60, 1_051.01, 1_061.52, 1_114.59
        ],
    })
    accel = _compute_acceleration(df)
    assert accel["spiker"] == pytest.approx(4.0, abs=0.01)


def test_compute_acceleration_nan_for_thin_history():
    """Slugs with fewer than 3 prior daily growths get NaN."""
    # Only 3 snapshots = 2 daily growths. min_priors=3 → NaN.
    df = _make_history({"newcomer": [100.0, 101.0, 102.0]})
    accel = _compute_acceleration(df)
    assert pd.isna(accel["newcomer"])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/ansvier/ph-heatmap
./venv/bin/pytest tests/test_heatmap.py -k compute_acceleration -v
```

Expected: 2 errors (`ImportError: cannot import name '_compute_acceleration'`).

- [ ] **Step 3: Implement `_compute_acceleration`**

Open `/Users/ansvier/ph-heatmap/heatmap.py`. Find `compute_window_growth` (around line 528). Add this function **immediately after** the closing of `compute_window_growth` and before `_format_views`:

```python
def _compute_acceleration(
    snapshots: pd.DataFrame,
    gender: str | None = None,
    baseline_days: int = 7,
    min_priors: int = 3,
) -> pd.Series:
    """Per-slug acceleration: today's daily growth-% minus mean(prior N daily growth-%s).

    A performer who naturally drifts upward by +0.25%/day has acceleration ≈ 0
    — that's their baseline. Acceleration > 0 means "today was faster than usual"
    (something hyped them up). Acceleration < 0 means "slowing vs baseline."

    Returns a Series indexed by slug with NaN for slugs that have fewer than
    `min_priors` historical daily growths (not enough data for a stable baseline).
    """
    snapshots = snapshots.copy()
    snapshots["snapshot_date"] = pd.to_datetime(snapshots["snapshot_date"])
    if gender is not None and "gender" in snapshots.columns:
        snapshots = snapshots[snapshots["gender"] == gender]

    if snapshots.empty:
        return pd.Series(dtype=float, name="acceleration")

    # slug × date matrix of total_views, sorted oldest → newest
    pivot = snapshots.pivot_table(index="slug", columns="snapshot_date", values="total_views")
    pivot = pivot.sort_index(axis=1)
    if pivot.shape[1] < 2:
        return pd.Series(dtype=float, name="acceleration")

    # Daily % growth (pct_change between consecutive days). First column = NaN.
    daily_growth = pivot.pct_change(axis=1) * 100

    todays = daily_growth.iloc[:, -1]
    # Prior `baseline_days` growth columns (excluding today)
    trailing = daily_growth.iloc[:, -(baseline_days + 1):-1]
    trailing_mean = trailing.mean(axis=1)
    trailing_count = trailing.count(axis=1)

    accel = (todays - trailing_mean).where(trailing_count >= min_priors)
    accel.name = "acceleration"
    return accel
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
./venv/bin/pytest tests/test_heatmap.py -k compute_acceleration -v
```

Expected: 2 passed.

- [ ] **Step 5: Run full suite (regression check)**

```bash
./venv/bin/pytest -q
```

Expected: all tests pass — at this point we only added new code. (was 43, now 45 with the 2 new tests.)

- [ ] **Step 6: Commit**

```bash
git add heatmap.py tests/test_heatmap.py
git commit -m "$(cat <<'EOF'
feat(heatmap): add _compute_acceleration helper

Per-slug acceleration = today's daily growth % minus mean of prior 7
daily growths. Returns NaN for slugs with <3 prior daily growths
(insufficient baseline). Used by Task 2 to attach an acceleration
column to compute_window_growth(window_days=1) output.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Attach `acceleration` column when `window_days == 1`

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/heatmap.py` (`compute_window_growth`, around lines 528–568)
- Modify: `/Users/ansvier/ph-heatmap/tests/test_heatmap.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_heatmap.py`:

```python
def test_compute_window_growth_attaches_acceleration_for_1d():
    """When window_days=1, output has an `acceleration` column populated for
    slugs with enough history; 7d/30d windows do NOT get the column."""
    df = _make_history({
        "veteran": [1_000.0, 1_010.0, 1_020.0, 1_030.0, 1_040.0, 1_050.0, 1_060.0, 1_070.0],
    })

    # 1d window: acceleration column present
    out_1d = compute_window_growth(df, window_days=1)
    assert "acceleration" in out_1d.columns
    assert pd.notna(out_1d.loc["veteran", "acceleration"])

    # 7d window: no acceleration column
    out_7d = compute_window_growth(df, window_days=7)
    assert "acceleration" not in out_7d.columns
```

- [ ] **Step 2: Run to confirm failure**

```bash
./venv/bin/pytest tests/test_heatmap.py::test_compute_window_growth_attaches_acceleration_for_1d -v
```

Expected: `KeyError: 'acceleration'` or `assert 'acceleration' in [...]` fails.

- [ ] **Step 3: Patch `compute_window_growth`**

In `heatmap.py`, find the body of `compute_window_growth` (around line 528). The current ending is:

```python
    out = today[today_cols].join(baseline, how="left")
    out["growth_pct"] = (out["total_views"] - out["prev_views"]) / out["prev_views"] * 100
    return out
```

Replace with:

```python
    out = today[today_cols].join(baseline, how="left")
    out["growth_pct"] = (out["total_views"] - out["prev_views"]) / out["prev_views"] * 100

    # For 1d window only: attach the acceleration column used by the
    # "Spike of the Day" card selection logic. 7d / 30d windows are not
    # surfaced through that card, so the column is omitted there.
    if window_days == 1:
        out["acceleration"] = _compute_acceleration(snapshots, gender=None)

    return out
```

(`gender=None` because `snapshots` is already pre-filtered by gender earlier in the function.)

- [ ] **Step 4: Run the new test**

```bash
./venv/bin/pytest tests/test_heatmap.py::test_compute_window_growth_attaches_acceleration_for_1d -v
```

Expected: pass.

- [ ] **Step 5: Run full suite**

```bash
./venv/bin/pytest -q
```

Expected: all tests pass (46).

- [ ] **Step 6: Commit**

```bash
git add heatmap.py tests/test_heatmap.py
git commit -m "$(cat <<'EOF'
feat(heatmap): attach acceleration column on 1d window

compute_window_growth(window_days=1) now also returns an `acceleration`
column. 7d / 30d windows unchanged (no consumer for acceleration there).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Selection by acceleration in `_build_top_performer_card`

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/heatmap.py` (`_build_top_performer_card`, around line 860)
- Modify: `/Users/ansvier/ph-heatmap/tests/test_heatmap.py`

Wire the new selection. Display stays single-line for now; Task 4 swaps the rendering to the contrast block.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_heatmap.py`:

```python
def _multiday_card_fixture():
    """8 days of history, multiple female slugs with different growth/accel signatures."""
    return pd.DataFrame([
        # 'stable_high' grows +0.5%/day every day → high growth_pct, ~0 acceleration
        # 'spiker' grows +0.1%/day for 7 days, then +1.0% on day 8 → lower growth_pct
        #          but acceleration ≈ +0.9 pp
        # Both have >100M views so the cohort filter doesn't eliminate them.
        *[{
            "snapshot_date": pd.Timestamp("2026-05-25") + pd.Timedelta(days=i),
            "slug": "stable_high", "name": "Stable High",
            "total_views": int(200_000_000 * (1.005 ** i)),
            "rank": 1, "gender": "female",
        } for i in range(8)],
        *[{
            "snapshot_date": pd.Timestamp("2026-05-25") + pd.Timedelta(days=i),
            "slug": "spiker", "name": "Spiker",
            "total_views": int(150_000_000 * ((1.001 ** min(i, 7)) * (1.010 if i == 7 else 1.0))),
            "rank": 2, "gender": "female",
        } for i in range(8)],
    ])


def test_top_performer_card_picks_by_acceleration():
    """Card prefers the spiker over the steadier high-grower when acceleration data exists."""
    df = _multiday_card_fixture()
    # Mode 'celebs' → no rank-band filter, just top-50 by views. Both slugs included.
    html = _build_top_performer_card(
        df, gender_key="female", gender_filter="female", mode="celebs", is_default=True
    )
    # Spiker has higher acceleration, so the card should feature Spiker, not Stable High.
    assert "Spiker" in html, f"expected Spiker in card; got: {html[:400]}"
    assert "Stable High" not in html


def test_top_performer_card_falls_back_to_growth_pct_without_history():
    """With only 2 days of data (no acceleration possible), card falls back to growth_pct."""
    df = pd.DataFrame([
        {"snapshot_date": pd.Timestamp("2026-05-30"), "slug": "slow",
         "name": "Slow", "total_views": 200_000_000, "rank": 1, "gender": "female"},
        {"snapshot_date": pd.Timestamp("2026-05-30"), "slug": "fast",
         "name": "Fast", "total_views": 150_000_000, "rank": 2, "gender": "female"},
        {"snapshot_date": pd.Timestamp("2026-05-31"), "slug": "slow",
         "name": "Slow", "total_views": 200_100_000, "rank": 1, "gender": "female"},
        {"snapshot_date": pd.Timestamp("2026-05-31"), "slug": "fast",
         "name": "Fast", "total_views": 151_500_000, "rank": 2, "gender": "female"},
    ])
    html = _build_top_performer_card(
        df, gender_key="female", gender_filter="female", mode="celebs", is_default=True
    )
    # Fast grew 1%, Slow grew 0.05% — fallback picks Fast.
    assert "Fast" in html, f"expected Fast in card; got: {html[:400]}"
    assert "Slow" not in html
```

- [ ] **Step 2: Run new tests — confirm RED**

```bash
./venv/bin/pytest tests/test_heatmap.py -k top_performer_card_picks_by_acceleration -v
```

Expected: failure — currently picks "Stable High" (highest growth_pct), not "Spiker".

- [ ] **Step 3: Update selection block in `_build_top_performer_card`**

In `heatmap.py`, find this block inside `_build_top_performer_card` (around line 891):

```python
    top = qualified.sort_values("growth_pct", ascending=False).iloc[0]
    slug = top.name
    name = top["name"]
    pct = float(top["growth_pct"])
    gain = int(top["growth_amount"]) if pd.notna(top["growth_amount"]) else 0
```

Replace with:

```python
    # Selection: prefer highest acceleration (today vs 7d baseline) so the card
    # surfaces a different performer most days. Falls back to highest % growth
    # when acceleration can't be computed for anyone (early tracking days, thin
    # fixtures, etc).
    if "acceleration" in qualified.columns and qualified["acceleration"].notna().any():
        candidates = qualified.dropna(subset=["acceleration"])
        top = candidates.sort_values("acceleration", ascending=False).iloc[0]
        use_acceleration = True
    else:
        top = qualified.sort_values("growth_pct", ascending=False).iloc[0]
        use_acceleration = False

    slug = top.name
    name = top["name"]
    pct = float(top["growth_pct"])
    gain = int(top["growth_amount"]) if pd.notna(top["growth_amount"]) else 0
```

`use_acceleration` is consumed by Task 4 to decide between the contrast layout and the legacy single-line layout. For now, ignore it — output of this task still uses the legacy format.

- [ ] **Step 4: Run the new tests**

```bash
./venv/bin/pytest tests/test_heatmap.py -k "top_performer_card_picks_by_acceleration or top_performer_card_falls_back_to_growth_pct" -v
```

Expected: 2 passed.

- [ ] **Step 5: Run full suite + pre-existing top_performer_card tests**

```bash
./venv/bin/pytest -q
./venv/bin/pytest tests/test_heatmap.py -k top_performer -v
```

Expected: full suite green (48 tests). Any pre-existing top-performer-card tests still pass — selection logic is acceleration-first-with-fallback, fallback matches old behaviour on thin fixtures.

- [ ] **Step 6: Commit**

```bash
git add heatmap.py tests/test_heatmap.py
git commit -m "$(cat <<'EOF'
feat(heatmap): card selects by acceleration with growth_pct fallback

Replaces the old "highest growth_pct" selection in
_build_top_performer_card with acceleration-first picking. Falls back
to growth_pct when no slug in the cohort has enough history for an
acceleration value (fixtures, early tracking days). Card rendering
still uses the legacy single-line format — Task 4 swaps it to the
TODAY/USUAL contrast block.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: TODAY / USUAL contrast block + caption + CSS

**Files:**
- Modify: `/Users/ansvier/ph-heatmap/heatmap.py` — `_build_top_performer_card` render block (around lines 918–927), plus CSS additions in `_PAGE_TEMPLATE` style block (around lines 172–177)
- Modify: `/Users/ansvier/ph-heatmap/tests/test_heatmap.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_heatmap.py`:

```python
def test_card_renders_today_usual_contrast_when_acceleration_available():
    """When acceleration drove selection, the card shows Today / Usual / caption."""
    df = _multiday_card_fixture()
    html = _build_top_performer_card(
        df, gender_key="female", gender_filter="female", mode="celebs", is_default=True
    )
    assert "Today:" in html, "expected Today: row in contrast block"
    assert "Usual:" in html, "expected Usual: row in contrast block"
    # One of the auto-captions must appear:
    captions = ("Sharp turnaround", "Trending up", "Steady pace", "Slower than usual", "Cooling off")
    assert any(c in html for c in captions), f"expected one of {captions} in card; html: {html[:600]}"


def test_card_renders_legacy_single_line_on_fallback():
    """When fallback was used, card renders the old `+X.XX% · +N views (24h)` line, no contrast."""
    df = pd.DataFrame([
        {"snapshot_date": pd.Timestamp("2026-05-30"), "slug": "fast",
         "name": "Fast", "total_views": 150_000_000, "rank": 2, "gender": "female"},
        {"snapshot_date": pd.Timestamp("2026-05-31"), "slug": "fast",
         "name": "Fast", "total_views": 151_500_000, "rank": 1, "gender": "female"},
    ])
    html = _build_top_performer_card(
        df, gender_key="female", gender_filter="female", mode="celebs", is_default=True
    )
    assert "Today:" not in html, "fallback render should not show Today: row"
    assert "views (24h)" in html, "fallback render should keep legacy '+N views (24h)' format"
```

- [ ] **Step 2: Run new tests — confirm RED**

```bash
./venv/bin/pytest tests/test_heatmap.py -k "today_usual_contrast or legacy_single_line" -v
```

Expected: failures — current render emits `+X.XX% · +N views (24h)` always; no `Today:` / `Usual:` rows.

- [ ] **Step 3: Add caption helper + thresholds**

In `heatmap.py`, add **immediately before** `_build_top_performer_card` (just before the line `def _build_top_performer_card`):

```python
# Spike of the Day caption thresholds — calibrated from the first week of
# acceleration data (range observed: -0.10 pp to +1.06 pp across all tiers).
# pp = "percentage points" (acceleration is a difference of two percentages).
_CAPTION_THRESHOLDS = (
    (0.05, "↑ Sharp turnaround"),
    (0.01, "↑ Trending up"),
    (-0.01, "→ Steady pace"),
    (-0.05, "↓ Slower than usual"),
    (float("-inf"), "↓ Cooling off"),
)


def _caption_for_acceleration(accel_pp: float) -> str:
    """Map an acceleration value (percentage points) to a one-line caption."""
    for threshold, caption in _CAPTION_THRESHOLDS:
        if accel_pp >= threshold:
            return caption
    return _CAPTION_THRESHOLDS[-1][1]  # unreachable; -inf catches all
```

- [ ] **Step 4: Update the render block in `_build_top_performer_card`**

Find the current return statement (around lines 918–927):

```python
    return (
        f'<a class="top-perf{active}" data-mode="{mode}" data-gender="{gender_key}" href="{profile_url}" target="_blank" rel="noopener">'
        f'{img_tag}'
        f'<div class="top-perf-text">'
        f'<span class="top-perf-label">{label}</span>'
        f'<span class="top-perf-name">{name}</span>'
        f'<span class="top-perf-stat"><strong>+{pct:.2f}%</strong> · +{gain:,} views (24h)</span>'
        f'</div>'
        f'</a>'
    )
```

Replace with:

```python
    if use_acceleration:
        accel = float(top["acceleration"])
        usual_pct = pct - accel  # by definition of acceleration
        caption = _caption_for_acceleration(accel)
        stat_html = (
            f'<span class="top-perf-stat-row">Today: <strong>{pct:+.3f}%</strong></span>'
            f'<span class="top-perf-stat-row">Usual: <strong>{usual_pct:+.3f}%</strong></span>'
            f'<span class="top-perf-caption">{caption}</span>'
        )
    else:
        stat_html = f'<span class="top-perf-stat"><strong>+{pct:.2f}%</strong> · +{gain:,} views (24h)</span>'

    return (
        f'<a class="top-perf{active}" data-mode="{mode}" data-gender="{gender_key}" href="{profile_url}" target="_blank" rel="noopener">'
        f'{img_tag}'
        f'<div class="top-perf-text">'
        f'<span class="top-perf-label">{label}</span>'
        f'<span class="top-perf-name">{name}</span>'
        f'{stat_html}'
        f'</div>'
        f'</a>'
    )
```

- [ ] **Step 5: Add CSS for the new classes**

In `heatmap.py`, find the existing CSS block (around line 172). After `.top-perf-stat strong` (line 177), add:

Find these lines:

```python
    .top-perf-stat {{
      color: var(--muted);
      font-size: 12px;
      font-weight: 500;
    }}
    .top-perf-stat strong {{ color: #6cd36a; font-weight: 700; }}
```

Append immediately after (still inside the same CSS block):

```python
    .top-perf-stat-row {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      font-weight: 500;
      line-height: 1.35;
    }}
    .top-perf-stat-row strong {{ color: var(--fg); font-weight: 700; font-variant-numeric: tabular-nums; }}
    .top-perf-caption {{
      display: block;
      color: #6cd36a;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.02em;
      margin-top: 2px;
    }}
```

(The caption is green by default. For the "↓ ..." captions, the green works against the dark background regardless of direction since the arrow communicates direction. If the user later wants per-direction colour we'd add inline style based on `accel` sign.)

- [ ] **Step 6: Run new tests**

```bash
./venv/bin/pytest tests/test_heatmap.py -k "today_usual_contrast or legacy_single_line" -v
```

Expected: 2 passed.

- [ ] **Step 7: Run full suite**

```bash
./venv/bin/pytest -q
```

Expected: all 50 tests pass.

- [ ] **Step 8: Commit**

```bash
git add heatmap.py tests/test_heatmap.py
git commit -m "$(cat <<'EOF'
feat(heatmap): card renders Today / Usual contrast + caption

Acceleration-driven card now shows a three-row stat block:
  Today: +X.XXX%
  Usual: +Y.YYY%
  ↑ Sharp turnaround   (or one of 5 auto-captions)

Falls back to legacy '+X.XX% · +N views (24h)' single-line format on
fixtures without enough history.

Adds two new CSS classes for the contrast rows; pre-existing
.top-perf-stat class remains for the fallback path.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Local E2E render + push

**Files:** none (re-renders into `public/`).

- [ ] **Step 1: Re-render all pages from existing data.db**

```bash
cd /Users/ansvier/ph-heatmap
./venv/bin/python -c "
from pathlib import Path
from db import init_db, load_all_snapshots
from heatmap import dump_json, render_charts_page, render_performer_page, render_stats_page, render_treemap_page, write_sitemap_and_robots

PUBLIC_DIR = Path('public')
conn = init_db('data.db')
df = load_all_snapshots(conn)
print(f'loaded {len(df)} rows', flush=True)

render_treemap_page(df, PUBLIC_DIR / 'index.html', default_mode='rising', canonical_path='/', seo_key='home')
for mode in ('rising', 'gems', 'celebs'):
    (PUBLIC_DIR / mode).mkdir(exist_ok=True)
    render_treemap_page(df, PUBLIC_DIR / mode / 'index.html', default_mode=mode, canonical_path=f'/{mode}/', seo_key=mode)
dump_json(df, PUBLIC_DIR / 'data.json')
(PUBLIC_DIR / 'p').mkdir(parents=True, exist_ok=True)
written = 0
for slug in df['slug'].unique():
    try:
        render_performer_page(df, slug=slug, output_path=PUBLIC_DIR / 'p' / f'{slug}.html')
        written += 1
    except Exception as exc:
        print(f'WARN: {slug}: {exc}')
print(f'wrote {written} performer pages')
(PUBLIC_DIR / 'stats').mkdir(exist_ok=True)
render_stats_page(df, PUBLIC_DIR / 'stats' / 'index.html')
(PUBLIC_DIR / 'charts').mkdir(exist_ok=True)
render_charts_page(df, PUBLIC_DIR / 'charts' / 'index.html')
write_sitemap_and_robots(df, public_dir=PUBLIC_DIR)
print('done')
"
```

Expected: all "wrote …" lines, no exceptions. ~12 sec.

- [ ] **Step 2: Smoke check — confirm the contrast block is in the rendered home page**

```bash
grep -oE 'top-perf-stat-row[^>]*>[^<]+' public/index.html | head -10
grep -oE 'top-perf-caption[^>]*>[^<]+' public/index.html | head -5
```

Expected:
- Several `top-perf-stat-row` matches with `Today: ...` and `Usual: ...` text
- Several `top-perf-caption` matches with arrow + caption text

If output is empty → the rendered HTML still uses the legacy format. Check whether `acceleration` column actually has values in production data. Re-run Task 4 Step 6 tests to verify locally first.

- [ ] **Step 3: Eyeball one page (optional)**

```bash
open /Users/ansvier/ph-heatmap/public/index.html
```

Toggle through the 3 mode tabs × 3 gender tabs (9 cards total). Each card should show:
- Avatar + name (unchanged)
- "Today: +X.XXX%" row
- "Usual: +Y.YYY%" row
- A caption (Sharp turnaround / Trending up / Steady pace / Slower than usual / Cooling off)
- No "+N views (24h)" line

If layout looks broken (overflow, weird spacing) — note exactly what's wrong and report before pushing. Don't push a visually broken card.

- [ ] **Step 4: Commit re-rendered HTML**

```bash
git status -s | head -5
git add public/
git commit -m "$(cat <<'EOF'
chore(render): re-render with Spike of the Day card

All 9 (mode × gender) cards now show TODAY/USUAL contrast + caption
when acceleration data is available. Selection picks the performer
with the highest acceleration in the cohort, so the surfaced name
changes day-over-day.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5: Pull-rebase + push**

```bash
git pull --rebase origin main 2>&1 | tail -3
git push 2>&1 | tail -3
```

Expected: push succeeds. (Daily-scrape bot may push between commit and push; rebase handles it.)

- [ ] **Step 6: Verify live (after ~60s for CF Pages deploy)**

```bash
curl -s https://hotmap.cam/ | grep -oE 'top-perf-stat-row[^>]*>[^<]+' | head -4
```

Expected: 4 lines showing `Today: +...` and `Usual: +...` text. If empty → CF Pages deploy is still in progress or there's a cache hit; retry in 60s or hard-refresh the live site.

---

## Self-review checklist (filled out by plan author)

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| `_compute_acceleration` helper with `min_priors=3` | Task 1 |
| `acceleration` column on `compute_window_growth(window_days=1)` | Task 2 |
| Selection by acceleration (highest, any sign) | Task 3 |
| Fallback to `growth_pct` when all-NaN | Task 3 |
| TODAY / USUAL contrast text block | Task 4 |
| Auto-caption from acceleration magnitude | Task 4 (5 thresholds match spec table) |
| Caption thresholds as module-level constants | Task 4 (`_CAPTION_THRESHOLDS`) |
| Remove `+N views (24h)` line from acceleration path | Task 4 (not emitted in `use_acceleration` branch) |
| Legacy single-line preserved on fallback | Task 4 (else branch) |
| Labels unchanged (`RISING FEMALE OF THE DAY` etc.) | Task 4 (label variable unchanged) |
| Treemap untouched | none — by construction |
| 5 tests in the spec | 5 tests across Tasks 1, 2, 3, 4 |

No gaps.

**Placeholder scan:** No TBD / TODO / vague language. Every step has either complete code or an exact command + expected output.

**Type consistency:** `_compute_acceleration` signature matches between Task 1 implementation and Task 1 tests. `use_acceleration` variable introduced in Task 3 Step 3 is consumed in Task 4 Step 4. `_CAPTION_THRESHOLDS` shape `(threshold, caption)` is consistent between definition and the `_caption_for_acceleration` consumer. `top["acceleration"]` accessed in Task 4 only inside the `use_acceleration` branch (where the column is guaranteed by Task 3's `dropna(subset=["acceleration"])`).

**Conditional / risk notes:**
- Task 3 inserts `use_acceleration` into a code path that Task 4 then consumes. If Task 4 is skipped or runs out of order, Task 3 commit leaves an unused variable but still works (legacy format still rendered for everyone). Tests pass at every step.
- The view-count removal in Task 4 changes the user-visible card. If reviewer wants to keep `+N views` as a tooltip instead of removing it entirely, that's a follow-up — spec explicitly approved removal.
