# Spike of the Day card — design

**Status:** approved
**Date:** 2026-06-01
**Author:** ansvier + claude

## Problem

The "of the day" card on each treemap tab (RISING / HIDDEN GEM / TOP CELEBRITY) currently selects the cohort's highest 1d `growth_pct`. Because performers have stable daily-growth rates, the same handful of names dominate: Yasmina Khan owns Rising Female, Sara Retali owns Hidden Gem Female, Eva Elfie owns Top Celebrity Female, day after day. The product promises daily change; the card delivers a leaderboard that doesn't move.

A 2026-06-01 attempt to fix this by changing the treemap's tile-size metric (% growth → acceleration) produced three iterations of UX regressions: the largest tile showed a smaller % than its neighbour, color and size encoded different metrics, etc. All reverted (`d81dc886`).

This spec is the second attempt — narrower scope. The treemap stays exactly as it is now (% growth metric, % growth color). Only the card's selection logic changes, plus the card adds a "today vs usual" contrast block so the displayed numbers explain the pick.

## Goal

After this ships, the "of the day" card on each (tier × gender) tab:

1. Picks the performer with the highest **acceleration** (today's daily growth minus 7-day baseline) in that cohort, instead of highest raw % growth.
2. Surfaces a different performer on most days, by construction — acceleration is a deviation metric, so today's leader is today's mover, not a permanent fixture.
3. Displays a TODAY-vs-USUAL contrast so the reader sees why this performer was picked even when her absolute % is smaller than neighbours.
4. Falls back gracefully (current `growth_pct` selection) when acceleration can't be computed for anyone in the cohort.

The treemap, sitemap, SEO head, per-performer pages, stats, and charts pages are all untouched.

## Decision

Four components.

### 1. Acceleration metric

`acceleration(slug)` = `today_daily_growth_pct(slug) − mean(prior_7_daily_growth_pct(slug))`

Where:

- `today_daily_growth_pct` = `(today_views − yesterday_views) / yesterday_views × 100`.
- The trailing window uses up to 7 prior daily growths (excluding today), but accepts as few as 3 to allow the metric to work on early-tracking history.
- Slugs with fewer than 3 prior daily growths get `acceleration = NaN` and are excluded from selection (fallback applies).

The helper `_compute_acceleration(snapshots, gender, baseline_days=7, min_priors=3) -> pd.Series` lives in `heatmap.py` next to `compute_window_growth`. (Same function I wrote on 2026-06-01 morning — pre-existing logic, validated by manual sim against 4 days of history.)

### 2. Selection in `_build_top_performer_card`

Today's logic (post-revert):

```python
top = qualified.sort_values("growth_pct", ascending=False).iloc[0]
```

New logic:

```python
if "acceleration" in qualified.columns and qualified["acceleration"].notna().any():
    sort_col = "acceleration"
    candidates = qualified.dropna(subset=["acceleration"])
else:
    sort_col = "growth_pct"
    candidates = qualified

top = candidates.sort_values(sort_col, ascending=False).iloc[0]
```

Highest acceleration wins, **regardless of sign**. On a slow day where everyone is decelerating, the least-decelerating performer is selected (story: "holding up best in a quiet day"). On a hot day with a real spike, the spiker wins. Both produce a non-stale pick.

Acceleration column on the cohort comes from a small extension to `compute_window_growth`: when `window_days == 1`, attach an `acceleration` column built from `_compute_acceleration`. Other window sizes (7d, 30d) don't get the column — they're not used by the card anyway (card is hard-coded to 1d).

### 3. Card content — TODAY vs USUAL contrast

The card today shows:

```
RISING FEMALE OF THE DAY
[avatar]  Yasmina Khan
          +0.21% · +689,001 views (24h)
```

New layout (same DOM positions, expanded text block):

```
RISING FEMALE OF THE DAY
[avatar]  Hazel Moore
          Today: +0.046%
          Usual: −0.035%
          ↑ Sharp turnaround
```

Three text rows:

1. **Today** — today's 1d `growth_pct`, formatted `+X.XXX%`.
2. **Usual** — 7d baseline (the mean used to compute acceleration), formatted `+Y.YYY%`.
3. **Caption** — one-line auto-generated tag from the acceleration magnitude:

| Acceleration | Caption |
|---|---|
| ≥ +0.05 pp | ↑ Sharp turnaround |
| ≥ +0.01 pp | ↑ Trending up |
| ≥ −0.01 pp | → Steady pace |
| ≥ −0.05 pp | ↓ Slower than usual |
| < −0.05 pp | ↓ Cooling off |

(Caption thresholds chosen from the manual sim: 4 days of real data produced spikes in the +0.05 to +1.0 pp range and slowdowns in the −0.05 to −0.10 pp range. Threshold at ±0.01 pp keeps "steady" rare so most days get a directional caption.)

Caption uses Unicode arrows (↑ → ↓) for direction, plain English text. No emoji. Color of the caption: green for ↑, neutral gray for →, soft red for ↓.

The pre-existing `+90,720 views (24h)` line is **removed** from the card — it's redundant with `Today: +0.046%` and the card needs to stay compact alongside the three new text rows. The raw view count is still visible on hover of the treemap tile.

### 4. Fallback

When `_compute_acceleration` returns all-NaN for the cohort (early tracking days, tiny fixture, gender filter excludes everyone):

- Selection falls back to `growth_pct` (current behaviour) — picks highest grower.
- Card shows the old single-line format: `+X.XX% · +N views (24h)`. No "Today / Usual" block, no caption.

This means the fixture-driven tests don't need to know about acceleration. And the production card never empties: there's always a pick.

## Scope

### Changes

**`heatmap.py`**

- Re-introduce `_compute_acceleration()` helper (the function I wrote and committed in `d1f752f8` and removed in `d81dc886` revert — same code, no changes).
- Re-introduce the `acceleration` column on `compute_window_growth(window_days=1)`. Other window sizes unchanged.
- Update `_build_top_performer_card()`:
  - Use new selection logic.
  - Compute the three text fields (today, usual, caption).
  - Render the expanded text block when acceleration is available; render the legacy single-line format when it isn't.
- Add caption thresholds as module-level constants near other rendering thresholds.

**`tests/test_heatmap.py`**

- `test_compute_acceleration_returns_today_vs_7d_avg` — synthetic 8-day fixture with one slug, assert the returned acceleration value matches the formula.
- `test_compute_acceleration_nan_for_thin_history` — slug with only 2 days of priors → NaN.
- `test_top_performer_card_selects_by_acceleration_when_available` — fixture where slug A has higher `growth_pct` but slug B has higher acceleration → card picks B.
- `test_top_performer_card_falls_back_to_growth_pct_when_no_acceleration` — fixture with only today's snapshot (no priors) → card picks by growth_pct, no contrast block in rendered HTML.
- `test_top_performer_card_renders_today_usual_caption_block` — when acceleration is available, rendered HTML contains both `Today:` and `Usual:` labels plus a recognisable caption substring.

**No other code changes.** Treemap, sitemap, SEO, render_performer_page, render_stats_page, render_charts_page, run.py — all untouched.

### Out of scope

- Treemap tile-size or color metric. Stays % growth.
- 7d and 30d card variants. The "of the day" card is implicitly a 1d concept.
- Acceleration on per-performer page (`/p/<slug>`). Could be a follow-up if interesting, not now.
- Card aggregation across tiers (e.g. "biggest spike across all tiers"). Each tier keeps its own card.
- New label / new card title. "RISING FEMALE OF THE DAY" stays — the tier label is still accurate, only the internal selection changed.
- Visual restyling of the card box (border, padding, hover). Just text content inside.

## Edge cases

- **All-negative cohort acceleration** (e.g. all Celebs on a slow day): the least-negative is selected; caption shows ↓ direction. Story is "held up best." Honest.
- **Tie at the top of acceleration**: `sort_values` is deterministic by row order — first match wins. Acceptable.
- **Acceleration column present but the specific slug has NaN**: `dropna(subset=["acceleration"])` excludes it from selection. The cohort's `qualified` set may shrink slightly but the fallback only triggers if the *whole* cohort lacks acceleration.
- **Acceleration is ≈ 0** (within ±0.01 pp): caption shows "→ Steady pace". Not exciting but honest.
- **Baseline period contains a gap day** (scrape failed): the `pct_change` across the gap produces a multi-day growth, not a daily one. `_compute_acceleration` uses `pivot.pct_change(axis=1)` on the sparse date matrix — pandas treats consecutive present columns as adjacent, so a missing 2026-05-29 day means the 05-28→05-30 pct_change shows ~2× normal growth. This will inflate the 7d baseline. Acceptable for now — scrape outages are rare; if they become an issue, we'd interpolate or skip.
- **Caption thresholds calibrated from 4 days of data**: may need re-tuning after a month of history. The constants are module-level so a future tune is one-line change.

## Risks

- **Caption phrasing**: "Sharp turnaround" might sound trader-jargon to some readers. Alternative phrasings explored: "Big spike," "Up sharply," "Reversed today." Going with "Sharp turnaround" because it implies the contrast with prior trend — which is exactly what acceleration measures.
- **User's prior frustration**: 3 iterations failed earlier today. Mitigation: scope is narrow (single card, no treemap touched), tests cover the selection + fallback explicitly, and the contrast block makes the pick self-explanatory rather than requiring the user to mentally combine two metrics.
- **Daily-scrape interaction**: the card renders in the daily-scrape pipeline. If the new selection logic crashes on a corner case, the entire pipeline fails and the site goes stale. Mitigation: explicit fallback path + test fixtures that include the no-history case.

## Files touched

| Path | LoC est. |
|---|---|
| `heatmap.py` | +60 prod (helper + selection + card rendering), 0 removed |
| `tests/test_heatmap.py` | +80 (5 tests + helper for synthetic snapshots) |
| `README.md` | maybe 1 line if SEO section mentions card behaviour |

Net: ~140 lines code change, no new files, no DB / template / route changes.
