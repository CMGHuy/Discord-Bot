# v34 Task 1: RS Value Path and Unknown Representation

**Status:** Documentation complete
**Date:** 2026-08-19

## Overview

This document traces how the `rs_percentile()` return value flows through the scanning and scoring pipeline, establishing the boundary contract for the v34 Relative Strength Gate. The gate must distinguish "no reading available" from "median 50th percentile" — this document captures how that distinction is currently represented and why.

## Complete Hop Trace

### Hop 1: `refresh_rs_cache` (engine.py:1133)

**Location:** `swingbot/core/scanning/engine.py:1133`

```python
rs_cache = rs_factors.refresh_rs_cache(fresh_data, spy_df)
```

**What happens:**
- Called at the scan level, once per scan session
- `fresh_data` is a dict of `{ticker: DataFrame}` for all universe symbols
- `spy_df` is the SPY benchmark DataFrame
- Wraps in try/except: if it fails, both `rs_cache` and `spy_df` are set to None

**Return contract:**
- Returns `dict` with structure `{"as_of": date_string, "rels": {ticker: float | None, ...}}`
- Each value in `rels` comes from `relative_return(df, spy_df)` → `float | None`
- If exception occurs, `rs_cache` is set to None (line 1137)

**Unknown representation at this hop:**
- `None` (when fetch/computation fails)
- The dict itself never contains None; only the outer variable can be None

---

### Hop 2: `ScanItem.rs_percentile` Assignment (engine.py:1272-1276)

**Location:** `swingbot/core/scanning/engine.py:1272-1276`

```python
if rs_cache is not None:
    item.rs_percentile = rs_factors.rs_percentile(
        fresh_data.get(item.result.ticker), spy_df,
        universe_rels=list(rs_cache["rels"].values()),
    )
```

**What happens:**
- Set per-item within the merge loop (after confirmation checks pass)
- Only executes if `rs_cache is not None`
- Calls `rs_factors.rs_percentile()` with universe relative returns
- If `rs_cache is None`, this block is skipped and `item.rs_percentile` stays None

**Return contract of `rs_percentile()`:**
- **Never returns None** (code path ends at factor.py:38)
- Always returns `float`: either 50.0 (default/unknown), or a calculated percentile (0.0-100.0)
- Returns 50.0 when:
  - `rel is None` (ticker doesn't have enough history) [factors.py:33-34]
  - `not universe_rels` (no universe passed) [factors.py:33-34]
  - `not rels` (all universe values are None) [factors.py:36-37]

**Unknown representation at this hop:**
- `None` (if rs_cache never computed; stored on ScanItem)
- `50.0` (if rs_cache exists but item is unknown within it — a float sentinel, not a None flag)

**Critical distinction:**
- `item.rs_percentile = None` means "no RS cache available for this scan"
- `item.rs_percentile = 50.0` means "this item's RS was computed and it equals the median"
- These are conflated if only raw floats are visible downstream; distinguishing them requires knowing context

---

### Hop 3: `_build_quality_inputs` (engine.py:475-519)

**Location:** `swingbot/core/scanning/engine.py:512`

```python
def _build_quality_inputs(item, scenario, df, horizon_key, *, regime=None,
                          rs_percentile=None, breadth=None) -> dict:
    ...
    return {
        ...
        "rs_percentile": rs_percentile,
        "breadth": breadth,
        ...
    }
```

**What happens:**
- Called by `attach_plan_v2()` during the same merge loop (line 533-535)
- Receives `rs_percentile` parameter (either None or float from item)
- Passes it through unchanged to the returned dict

**Return contract:**
- Returns dict with key `"rs_percentile"` containing either:
  - `None` (if item.rs_percentile was None)
  - `float` (0.0-100.0, including the 50.0 sentinel)

**Unknown representation at this hop:**
- `None` (if rs cache unavailable)
- `50.0` (if rs cache available but ticker is unknown)
- **Preservation:** the None/float distinction is maintained here

---

### Hop 4: `attach_plan_v2` → `build_confluence_plan` → `_apply_quality` → `score_plan` (quality.py:127-156)

**Location chain:**
1. `engine.py:536-539` calls `build_confluence_plan(..., quality_inputs=quality_inputs)`
2. plan_engine (not traced in detail; in `swingbot/core/planning/`) calls `_apply_quality(quality_inputs)`
3. `_apply_quality()` pops `confidence_level` and forwards the rest to `score_plan()`

**What happens at `score_plan()`:**
- Accepts `rs_percentile=None` as keyword-only argument (quality.py:129)
- Builds breakdown list (line 138-145)
- Conditional loop (line 147-151):
  ```python
  for name, value, fn in (("rs", rs_percentile, rs_points),
                          ("breadth", breadth, breadth_points),
                          ("candle", candle_quality, candle_points)):
      if value is not None:
          breakdown.append((name, fn(value)))
  ```
- Only calls `rs_points(rs_percentile)` if `rs_percentile is not None`

**`rs_points()` function (quality.py:105-108):**
```python
def rs_points(rs_pctile: float | None) -> int:
    if rs_pctile is None:
        return 0
    return int(round(max(0.0, min(rs_pctile - 50.0, 50.0)) / 5.0))
```
- Returns 0 if `rs_pctile is None`
- Never called when rs_percentile is None (guarded by outer `if value is not None`)

**Return contract (QualityResult):**
- `score: int` — the summed points (0-100)
- `breakdown: list` — `[(component_name, points), ...]` — only includes "rs" if rs_percentile was not None

**Unknown representation at this hop:**
- `None` (if passed in; factor omitted from breakdown)
- `50.0` (if passed in; scores 0 points: `(50.0 - 50.0) / 5.0 = 0`)
- **Observable difference:** unknown RS doesn't appear in the breakdown at all; computed RS=50 appears and scores 0

---

## Current Behavior Summary

### The Unknowns Table

| Situation | `rs_cache` | `ScanItem.rs_percentile` | In Quality Breakdown? | Points |
|-----------|:----------:|:------------------------:|:--------------------:|:------:|
| SPY fetch fails | `None` | `None` | No | N/A |
| Ticker has short history | Not None | `50.0` (computed) | Yes | 0 |
| Ticker normal RS=60% | Not None | `60.0` | Yes | 2 |
| Empty universe (edge case) | Not None | `50.0` | Yes | 0 |

### Current Unknown Representation

The codebase uses **two independent signals** to represent "unknown RS":

1. **At the scan level:** `rs_cache = None` (entire RS benchmark fetch failed)
2. **At the item level:** `ScanItem.rs_percentile = None` (rs_cache unavailable, so no computation was attempted)

The **median sentinel (50.0) is never None:**
- If `rs_cache` is available, every item gets a computed `rs_percentile` (either real or 50.0 if the item is unknown within the universe)
- This conflates "unknown within a known universe" (50.0) with "median is truly 50.0" (also 50.0)

**Why this matters for the gate:**
The gate must accept three states:
1. `None` — no RS benchmark available, gate should be lenient or skip
2. `50.0` from computation — item is median rank, gate can apply thresholds normally
3. `50.0` from unknownness — item couldn't be ranked, gate should treat as unknown

Without additional metadata (e.g., a separate `rs_available: bool` flag), a `50.0` value alone cannot tell the gate which of state 2 or 3 it is.

---

## Decision: Unknown Representation for the Gate

**Chosen approach:** Introduce `RS_UNKNOWN = None` at the gate boundary and have the gate accept an explicit `rs_available: bool` parameter.

**Rationale:**
1. **Minimal blast radius:** `rs_percentile()` callers in other modules (factors.py, quality.py) rely on a float return type. Changing it to `float | None` would require updating every call site.

2. **Gate-specific concern:** The gate is a new consumer of RS data; it is the only place that needs to distinguish "unknown" from "median." Encoding this distinction at the gate boundary (not at the function return type) keeps the change local to the gate's own logic.

3. **Clarity:** An explicit `rs_available: bool` passed alongside `rs_percentile` makes the gate's assumptions visible and testable.

4. **Backward compatibility:** Existing scoring (quality.py) treats `None` as "omit from breakdown"; the gate can do the same while using the bool flag to apply logic.

**Gate boundary contract:**
- Gate receives: `rs_percentile: float | None` and `rs_available: bool`
- If `rs_available = False`: treat `rs_percentile` as a placeholder (likely 50.0)
- If `rs_available = True`: treat `rs_percentile` as a real computation
- Gate's decision logic uses both to avoid false positives on unknown RS

**Where this is set up:**
- Input to gate: pass `rs_available = (rs_cache is not None)` when building gate inputs
- This makes the site-wide truth (rs_cache availability) explicit to the gate

---

## Characterization Tests

Location: `tests/edge/test_rs_value_path.py`

These tests document today's behavior at the source (`rs_percentile()` function):

```python
def test_rs_percentile_returns_fifty_not_none_on_empty_universe():
    """Characterization: rs_percentile always returns 50.0, never None."""
    assert rs_percentile(_frame_120(), _frame_120(), universe_rels=[]) == 50.0

def test_rs_percentile_returns_fifty_on_short_history():
    """Characterization: short history is handled gracefully."""
    assert rs_percentile(_frame_3(), _frame_120(), universe_rels=[0.1]) == 50.0
```

**Why these tests matter:**
- They capture that `rs_percentile()` is a function that **never returns None**
- If this ever changes (e.g., to return `None` on unknown), the tests will fail loudly
- The gate's design depends on this contract; a breaking change is a breaking change to the gate

---

## Implementation Checklist

- [x] Trace complete data flow from `refresh_rs_cache` through `score_plan`
- [x] Document unknown representation at each hop
- [x] Write characterization tests capturing today's behavior
- [x] Decide unknown representation for the gate (RS_UNKNOWN = None at boundary)
- [x] Record decision rationale

**Next steps (v34 Tasks 2+):**
- Add `rs_available: bool` to gate input builder
- Implement gate decision logic using both `rs_percentile` and `rs_available`
- Write gate tests exercising both known and unknown RS cases
