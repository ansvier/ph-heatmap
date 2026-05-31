# Treemap size metric: switch from absolute to % growth

**Status:** approved
**Date:** 2026-05-31
**Author:** ansvier + claude

## Problem

Current treemap encodes **tile size = absolute views gained over the window**.
Result: the same top performers dominate every day regardless of who actually
"rose" today, because high-volume performers naturally accrue more raw views
per day than smaller ones at any growth rate.

Example: today's top-10 1d-gainers (female, Rising Stars) overlap 8/10 with
yesterday's, just with proportionally larger numbers. The product promises
"momentum" but visually shows "consistent dominance within tier."

## Goal

Make the treemap reflect **rate of growth**, so a mid-tier performer who
suddenly accelerates appears as a large tile even when their raw delta is
smaller than a celebrity's. Move "Rising Stars" closer to its label.

## Decision

**Replace absolute growth with % growth as the size-encoding metric, in all
three tiers, with a 1M-views minimum-baseline filter to suppress micro-account
noise.**

Toggle UI was rejected (would double precomputed page count 27 → 54, require
JS, complicate share links). Hybrid `sqrt(abs × pct)` was rejected (harder to
explain).

## Scope

### Changes

**`heatmap.py:_build_treemap_figure`**

- Add filter: drop rows where `prev_views < 1_000_000` after the dropna step.
- Compute `tile_size = growth_pct.clip(lower=0)` (clipped because Plotly
  Treemap requires non-negative `values=`).
- Pass `values=rows["tile_size"]` instead of `rows["growth_amount"]`.
- Update the docstring (currently says "tile size encodes absolute views
  gained" — incorrect after this change).

**`tests/test_heatmap.py`**

- New test: with mixed-baseline cohort, performer with 5% growth on 50M base
  ranks larger than performer with 0.05% growth on 2B base (even though the
  latter has larger absolute delta).
- New test: row with `prev_views < 1M` is excluded from the rendered tiles.

**`README.md`**

- Update the "What the treemap shows" paragraph: "Tile size encodes
  percentage view growth over the window (min 1M baseline)" instead of
  "absolute views gained."

### No changes

- Color metric (already percentile rank of `growth_pct`).
- "Top Performer of the Day" card (already sorts by `growth_pct`).
- `compute_window_growth` signature and outputs.
- Tier definitions (Celebrities 1-50, Rising 51-250, Gems 251-500).
- Stats / charts / per-performer pages — already leaderboard by `growth_pct`.
- Per-performer pages — the 1M-baseline filter applies ONLY to the treemap
  aggregate view. An individual performer's page shows their own growth
  regardless of baseline size.
- Schema, `data.json` payload, DB schema.
- Number of rendered pages (27 = 3 modes × 3 genders × 3 windows).

## Edge cases

- **Plotly requires positive `values`**: handled by `.clip(lower=0)`.
  `total_views` is monotonic so `growth_pct ≥ 0` in normal data, but a missing
  baseline backfill could produce NaN — the existing `dropna` covers that.
- **<2 rows after filter**: existing `len(rows) > 1` guard remains; color
  collapses to neutral.
- **Celebrities tier compression**: all top-50 have huge baselines, so their
  % growths cluster in 0.01–0.06%. Tile sizes will be visually similar.
  Percentile-rank color still differentiates. Acceptable tradeoff for
  consistency across tiers.

## Non-goals

- Acceleration metric (today's growth vs 7d-avg) — interesting follow-up but
  out of scope here.
- Z-score normalization — same.
- UI toggle between abs and pct — explicitly rejected for scope reasons.

## Risks

- **Visual identity shift**: returning users will see noticeably different
  tile layouts. Mitigation: hover tooltip still shows both absolute gain and
  % so the absolute number is one hover away.
- **Celebrity tile uniformity**: documented above. If it looks too flat in
  practice we can revisit (e.g., per-tier metric choice), but ship the
  consistent version first.

## Files touched

| Path | LoC est. |
|---|---|
| `heatmap.py` | ~5 prod, +docstring |
| `tests/test_heatmap.py` | ~2 new tests |
| `README.md` | 1 line |

Total: ~20 lines of code change, ~15 lines of test, 1 README line.
