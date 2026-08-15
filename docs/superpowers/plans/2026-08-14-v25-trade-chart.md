# The trade chart — Implementation Plan (v25)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-08-14-v23-trade-chart-design.md`
**Version:** ui 1.2.3 · bot 1.1.2
**Bump:** `bot` patch after Phase 1, `ui` minor after Phase 4. Two release
commits, each after its half is green.

**Goal:** Restore the trade plan's full annotation — the trendline and its swing
pivots, both sides' overlays, and a legend with the fit notes — inside one
interactive chart that serves both the trade detail and the watchlist.

**Architecture:** The trendline is fitted **once**, when the plan is created,
and persisted on the trade; both the Discord PNG and the SPA read that stored
geometry, so there is one fit and one answer. The two chart endpoints collapse
into one keyed by ticker with an optional `trade_id`, carrying epoch seconds
throughout. The two chart components collapse into one. The legend is drawn on
canvas, reversing `strategy-overlay.ts`'s "No text" rule deliberately.

**Tech Stack:** Python 3.11 (pandas, mplfinance, Flask), Angular 21 signals,
`lightweight-charts` 5.x, pytest, vitest.

## Global Constraints

- **NO-LOOKAHEAD.** Indicators are computed over the full frame and sliced
  afterwards, never computed over the visible window (`market.py:_series`). Any
  new series follows the same order.
- **One time type in the chart payload: epoch seconds.** `models.ts:709` records
  why — a payload mixing `YYYY-MM-DD` strings with epochs lands overlays a year
  from their candles.
- **`trendline_fit` is optional forever.** Absent on every record written before
  this plan. Code that requires it breaks every historical trade; that is what
  keeps this an additive change and not a major bump.
- **`chart_geometry.py` stays the one implementation.** The browser draws
  numbers off the wire and never recomputes geometry.
- **No hex outside `frontend/src/styles/tokens.css`.** The legend reads colours
  and fonts through `chart-theme.ts`'s `token()` helper.
- **The Discord alert path is live.** Phase 1 changes it. `python
  scripts/testrun.py full` is the gate for every Python task, not `fast`.

## File Structure

| File | Responsibility | Tasks |
|---|---|---|
| `swingbot/core/charts/trendline_fit.py` | **new** — the one fit, and its serialised shape | 1 |
| `swingbot/core/charts/trade_chart.py` | the PNG; consumes the stored fit | 3 |
| `swingbot/core/charts/chart_geometry.py` | a shape built from a stored fit | 4 |
| `swingbot/admin/api_v1/market.py` | the merged endpoint, backfill on read | 2, 5, 6 |
| `frontend/src/app/api/models.ts` | payload types; `Candle` retires | 5, 6 |
| `frontend/src/app/ui/chart/trade-chart.ts` | the one chart component | 7, 8 |
| `frontend/src/app/ui/price-chart.ts` | **deleted** | 8 |
| `frontend/src/app/ui/chart/primitives/legend-primitive.ts` | **new** — the legend | 9 |
| `frontend/src/app/ui/chart/chart-prefs.ts` | **new** — remembered toggles | 10 |
| `frontend/src/app/workspaces/watchlist/ticker-detail.ts` | call site | 8 |
| `frontend/src/app/workspaces/trades/trade-detail.ts` | call site | 8 |

## Parallelisation

- **Sequential: Phase 1 → 2 → 3 → 4.** A chain, and saying so is worth as much
  as a wide group. Phase 2's payload carries the geometry Phase 1 persists;
  Phase 3 consumes Phase 2's payload shape; Phase 4 draws what Phase 3 owns.
- **Within Phase 1 — Tasks 1 and 2 are parallel** (different files, neither
  consumes the other's symbols). **Tasks 3 and 4 are sequential after both**:
  each consumes the extracted fit *and* the stored field.
- **Within Phase 2 — sequential.** Every task edits `market.py` and `models.ts`.
  Do not dispatch these concurrently; two workers on one file overwrite.
- **Within Phase 3 — sequential.** Merge, then the two call sites, then the
  deletion.
- **Within Phase 4 — Tasks 9 and 10 are parallel** (`primitives/` and `ui/`,
  no shared symbol). **Task 11 is sequential after both.**
- **This whole plan is parallel with plan v24.** No shared file: v24 converts
  workspace control rows; this touches `ui/chart/` and only the chart sections
  of the two workspace files.

---

# Phase 1 — The fit

### Task 1: Extract the fit into one module

**Files:**
- Create: `swingbot/core/charts/trendline_fit.py`
- Create: `tests/test_trendline_fit.py`

**Interfaces:**
- Consumes: `strongest_trendline_pair(df, lookback, current_price) -> dict | None`
  from `swingbot.core.trendlines`, which returns
  `{"support": {...}|None, "resistance": {...}|None, "window_bars": int}` in
  **display-window** bar coordinates (bar 0 = leftmost visible bar).
- Produces:
  - `fit_trendline(df, *, lookback, current_price, is_bull) -> dict | None`
  - `TRENDLINE_FIT_KEY = "trendline_fit"`
  Tasks 2, 3 and 4 all import from here.

- [x] **Step 1: Write the failing test**

Create `tests/test_trendline_fit.py`:

```python
import pandas as pd
import pytest

from swingbot.core.charts.trendline_fit import fit_trendline


def _frame(n=140):
    """A clean descending series -- fittable, and fittable the same way twice."""
    idx = pd.date_range("2026-01-01", periods=n, freq="B")
    close = pd.Series([200.0 - 0.3 * i for i in range(n)], index=idx)
    return pd.DataFrame({
        "Open": close, "High": close + 1.0, "Low": close - 1.0,
        "Close": close, "Volume": 1_000_000.0,
    }, index=idx)


def test_returns_none_when_nothing_is_drawable():
    tiny = _frame(5)
    assert fit_trendline(tiny, lookback=120, current_price=100.0, is_bull=True) is None


def test_fit_is_serialisable_and_json_safe():
    fit = fit_trendline(_frame(), lookback=120, current_price=160.0, is_bull=True)
    assert fit is not None
    assert set(fit) >= {"slope", "intercept", "points", "side", "lookback", "fit_at"}
    for point in fit["points"]:
        assert isinstance(point["t"], int)
        assert isinstance(point["price"], float)


def test_the_same_frame_fits_the_same_line_twice():
    """The whole point of extracting this: one fit, one answer."""
    a = fit_trendline(_frame(), lookback=120, current_price=160.0, is_bull=True)
    b = fit_trendline(_frame(), lookback=120, current_price=160.0, is_bull=True)
    assert a["slope"] == b["slope"]
    assert a["points"] == b["points"]


def test_a_bull_trade_fits_support_and_a_bear_fits_resistance():
    bull = fit_trendline(_frame(), lookback=120, current_price=160.0, is_bull=True)
    bear = fit_trendline(_frame(), lookback=120, current_price=160.0, is_bull=False)
    assert bull["side"] == "support"
    assert bear["side"] == "resistance"
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_trendline_fit.py -v`
Expected: FAIL — `ModuleNotFoundError: swingbot.core.charts.trendline_fit`.

- [x] **Step 3: Implement**

Create `swingbot/core/charts/trendline_fit.py`:

```python
"""The one trendline fit, and the shape it is stored in.

`generate_trade_chart()` used to fit the trendline pair itself, immediately
before deciding its display window (the window is then widened to fit the
line's own touches). That made the chart endpoint's position untenable:
re-fitting there would have been a SECOND source of truth for the same line,
which is exactly what `chart_geometry.py` exists to prevent -- so the endpoint
left `trend_info` unset and a trendline-confirmed trade drew no overlay at all.

Both problems dissolve if the fit happens once and is written down. This module
is that once. The PNG and the API both read what it produced; neither fits.

**Points, not just slope and intercept.** `strongest_trendline_pair` returns
geometry in DISPLAY-WINDOW bar coordinates -- bar 0 is the leftmost visible
bar, which is a different origin for every window a caller chooses. Storing
slope and intercept alone would mean every reader had to reconstruct that
window to know where the line goes. The two endpoints are resolved here, once,
into absolute (epoch, price) pairs that mean the same thing to a matplotlib
axis and a lightweight-charts pane.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from ..trendlines import strongest_trendline_pair

TRENDLINE_FIT_KEY = "trendline_fit"


def fit_trendline(df: pd.DataFrame, *, lookback: int, current_price: float,
                  is_bull: bool) -> dict | None:
    """Fit the trade's trendline and return it in storable form.

    A bull trade is drawn against SUPPORT -- the line it is holding above --
    and a bear against resistance. That is the side the plan's thesis rests
    on; drawing the other one would illustrate a trade nobody took.

    Returns None when nothing is drawable: too little history, no qualifying
    pivot pair, or a non-positive price. None is a normal outcome, not an
    error -- a candlestick-pattern-only confirmation has no trendline and
    never did.
    """
    pair = strongest_trendline_pair(df, lookback, current_price)
    if not pair:
        return None

    side = "support" if is_bull else "resistance"
    line = pair.get(side)
    if not line:
        return None

    window_bars = int(pair["window_bars"])
    if window_bars < 2 or len(df) < window_bars:
        return None

    # The display window's own bars, which is the coordinate system the slope
    # and intercept are expressed in.
    visible = df.tail(window_bars)
    slope = float(line["slope"])
    intercept = float(line["intercept"])

    first_x, last_x = 0, window_bars - 1
    points = [
        {"t": _epoch(visible.index[first_x]), "price": round(intercept + slope * first_x, 4)},
        {"t": _epoch(visible.index[last_x]), "price": round(intercept + slope * last_x, 4)},
    ]

    return {
        "slope": slope,
        "intercept": intercept,
        "points": points,
        "side": side,
        "strength": int(line.get("strength", 0)),
        "window_bars": window_bars,
        "lookback": int(lookback),
        "fit_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _epoch(stamp) -> int:
    """A pandas index entry -> Unix seconds. One time type across the payload;
    see `models.ts` on what mixing representations costs."""
    return int(pd.Timestamp(stamp).tz_localize(None).timestamp())
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_trendline_fit.py -v`
Expected: PASS, 4 tests.

- [x] **Step 5: Commit**

```bash
git add swingbot/core/charts/trendline_fit.py tests/test_trendline_fit.py
git commit -m "feat(charts): one trendline fit, stored as absolute points"
```

---

### Task 2: Persist the fit when a plan is created

**Files:**
- Modify: the module that writes a new trade/plan record (locate in Step 1)
- Test: `tests/test_trendline_fit_persistence.py` (create)

**Interfaces:**
- Consumes: `fit_trendline`, `TRENDLINE_FIT_KEY` from Task 1.
- Produces: a `trendline_fit` key on newly written trade records, shaped exactly
  as Task 1 returns. Tasks 3, 4 and 6 read it.

- [x] **Step 1: Locate the writer**

Run:

```bash
git grep -n "def add\b" -- swingbot/core/plan_store.py
git grep -rn "PlanStore().add\|store.add(" -- swingbot/core swingbot/commands | head
```

`PlanStore.add(plan: TradePlanV2)` at `swingbot/core/plan_store.py:45` is the
write; its callers are where a plan first exists with a ticker, a direction and
the frame it was built from. Read the caller that has all three in scope — that
is the fit site. Record the file and line before editing.

- [x] **Step 2: Write the failing test**

Create `tests/test_trendline_fit_persistence.py`. Use the same `_frame()` helper
as Task 1 (repeat it — the two files are read independently):

```python
import pandas as pd

from swingbot.core.charts.trendline_fit import TRENDLINE_FIT_KEY, fit_trendline


def _frame(n=140):
    idx = pd.date_range("2026-01-01", periods=n, freq="B")
    close = pd.Series([200.0 - 0.3 * i for i in range(n)], index=idx)
    return pd.DataFrame({
        "Open": close, "High": close + 1.0, "Low": close - 1.0,
        "Close": close, "Volume": 1_000_000.0,
    }, index=idx)


def test_a_new_plan_carries_its_trendline_fit():
    """Written at creation, against the data the decision was made on."""
    fit = fit_trendline(_frame(), lookback=120, current_price=160.0, is_bull=True)
    record = {"ticker": "AAPL", TRENDLINE_FIT_KEY: fit}
    assert record[TRENDLINE_FIT_KEY]["points"][0]["t"] > 0


def test_a_record_without_a_fit_is_still_valid():
    """Every trade written before this change has no fit and must stay
    readable. The field is optional forever."""
    record = {"ticker": "AAPL"}
    assert record.get(TRENDLINE_FIT_KEY) is None
```

Then add, in the same file, a test that exercises the real writer found in
Step 1 — construct a plan through that path with a fittable frame and assert
the stored record has a `trendline_fit` whose `points` have integer `t`.

- [x] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_trendline_fit_persistence.py -v`
Expected: FAIL on the writer test — the stored record has no `trendline_fit`.

- [x] **Step 4: Write the fit at creation**

At the site found in Step 1, before the record is stored:

```python
from swingbot.core.charts.trendline_fit import TRENDLINE_FIT_KEY, fit_trendline

fit = fit_trendline(
    df,
    lookback=DEFAULT_TRENDLINE_LOOKBACK_DAYS,
    current_price=float(df["Close"].iloc[-1]),
    is_bull=direction == "bullish",
)
if fit:
    record[TRENDLINE_FIT_KEY] = fit
```

`if fit:` — an unfittable plan stores nothing rather than a null, so "absent"
has one meaning (no line) instead of two.

- [x] **Step 5: Run the full suite and commit**

Run: `python scripts/testrun.py full`
Expected: `0 failed, 0 xfailed`.

```bash
git add swingbot/core/ tests/test_trendline_fit_persistence.py
git commit -m "feat(plans): persist the trendline fit at plan creation"
```

---

### Task 3: The PNG reads the stored fit

**Files:**
- Modify: `swingbot/core/charts/trade_chart.py:207-228` (signature),
  and the block where it currently calls `strongest_trendline_pair`
- Test: `tests/test_trade_chart_stored_fit.py` (create)

**Interfaces:**
- Consumes: `fit_trendline`, `TRENDLINE_FIT_KEY` from Task 1.
- Produces: `generate_trade_chart(..., trendline_fit: dict | None = None)` — a
  new keyword-only-in-practice parameter appended to the existing signature.

- [x] **Step 1: Write the failing test**

Create `tests/test_trade_chart_stored_fit.py`:

```python
import pandas as pd

from swingbot.core.charts import trade_chart


def _frame(n=140):
    idx = pd.date_range("2026-01-01", periods=n, freq="B")
    close = pd.Series([200.0 - 0.3 * i for i in range(n)], index=idx)
    return pd.DataFrame({
        "Open": close, "High": close + 1.0, "Low": close - 1.0,
        "Close": close, "Volume": 1_000_000.0,
    }, index=idx)


def test_a_stored_fit_is_not_refitted(monkeypatch):
    """The whole guarantee: given a fit, the PNG must not compute one."""
    calls = []
    monkeypatch.setattr(
        trade_chart, "strongest_trendline_pair",
        lambda *a, **k: calls.append(a) or None,
    )
    stored = {
        "slope": -0.3, "intercept": 200.0,
        "points": [{"t": 1767225600, "price": 200.0},
                   {"t": 1779235200, "price": 158.3}],
        "side": "support", "strength": 4, "window_bars": 120,
        "lookback": 120, "fit_at": "2026-08-14T10:00:00Z",
    }
    trade_chart.generate_trade_chart(
        "AAPL", _frame(), entry=160.0, stop_loss=150.0, take_profit=180.0,
        direction="bullish", strategy="RSI", horizon_label="2w",
        out_dir="/tmp", trendline_fit=stored,
    )
    assert calls == []


def test_without_a_stored_fit_it_still_renders(monkeypatch):
    """Old trades and diagnostic callers must not crash."""
    path = trade_chart.generate_trade_chart(
        "AAPL", _frame(), entry=160.0, stop_loss=150.0, take_profit=180.0,
        direction="bullish", strategy="RSI", horizon_label="2w",
        out_dir="/tmp", trendline_fit=None,
    )
    assert path
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_trade_chart_stored_fit.py -v`
Expected: FAIL — `generate_trade_chart() got an unexpected keyword argument
'trendline_fit'`.

- [x] **Step 3: Implement**

Add `trendline_fit: dict = None,` to the signature after `markers: dict = None,`.
Where the function currently fits its own pair, take the stored line first:

```python
    # The fit comes from the record when there is one -- see
    # charts/trendline_fit.py on why this is stored rather than computed.
    # Falling back to a live fit is NOT a second implementation: it is the
    # same function, called here for the diagnostic callers (!strategycharts)
    # that have no record to read from.
    if trendline_fit:
        trend_info = trendline_fit
    else:
        trend_info = fit_trendline(
            df, lookback=trendline_lookback,
            current_price=float(market_price or entry), is_bull=is_bull,
        )
```

Import `fit_trendline` at the top of the module and delete the direct
`strongest_trendline_pair` import if nothing else in the file uses it.

Then convert the display-window logic to read the line's endpoints from
`trend_info["points"]` (absolute epochs) instead of window-relative bar
coordinates. The window is still widened to fit the line's touches — that
framing decision stays local to this file; only the geometry moved.

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_trade_chart_stored_fit.py -v`
Expected: PASS.
Then: `python scripts/testrun.py full`
Expected: `0 failed, 0 xfailed`. **This is the alert path — do not proceed on a
partial run.**

- [x] **Step 5: Commit**

```bash
git add swingbot/core/charts/trade_chart.py tests/test_trade_chart_stored_fit.py
git commit -m "feat(charts): the PNG draws the stored trendline fit"
```

Then the bot release marker, its own commit:

```bash
# VERSION.json: bot 1.1.2 -> 1.1.3, bot_updated to now (UTC)
git add VERSION.json
git commit -m "release(bot): 1.1.3 -- one stored trendline fit"
```

---

### Task 4: A geometry shape built from a stored fit

**Files:**
- Modify: `swingbot/core/charts/chart_geometry.py:195-253` (`_trendline_shape`)
- Test: `tests/test_chart_geometry.py` (existing — add cases)

**Interfaces:**
- Consumes: the stored fit shape from Task 1.
- Produces: `_trendline_shape` accepting a stored fit; `overlay_geometry(...)`
  gains a `trend_fit: dict | None = None` keyword. Task 5 passes it.

> **Corrected during execution.** Two errors, both caught against the real
> code rather than the plan's sketch of it.
>
> 1. **Pivots are not the endpoints.** This task asserted
>    `shape["pivots"] == stored["points"]` and called them "the same two
>    points by construction". `points` are the segment's ENDS, two
>    extrapolated positions at the window edges no candle need have visited;
>    `pivots` are the bars that actually touched the line and earned it its
>    `strength`. Drawing the ends would put two diamonds under a label
>    reading "Trendline (6x)" — the bug `trade_chart.py:752-760` records
>    being fixed once already. Task 1's module now stores a separate
>    `pivots` list, and the `pair` verbatim (a6fb782).
> 2. **The shape is `p1`/`p2`/`pivots`/`label`, not `points`/`strength`.**
>    `_trendline_shape` already existed and already emitted that shape;
>    `models.ts:852` types it and `strategy-overlay.ts:68` draws it. The
>    rewrite this task proposed would have broken the client to no purpose.
>    What was missing was never the shape — it was that a caller with no
>    live `trend_info` (which is every API caller: `market.py:316` leaves it
>    unset deliberately) got None back.
>
> **As built:** `overlay_geometry(..., trend_fit=None)` threads the stored
> fit down to `_trendline_shape`, which reads the fit's `pair` in place of
> `trend_info` and, for the fit's OWN side, copies the absolute epochs out
> of `points`/`pivots` instead of converting window-relative coordinates.
> That conversion is exactly what the API path cannot do safely: it serves
> whatever bar range the browser asked for, and converting against a
> different frame slides the line off its own pivots. The opposite side has
> no stored points — a fit is taken for the side the trade rests on — so it
> still comes from the stored pair, converted. Tests:
> `tests/test_chart_geometry.py::test_a_stored_fit_*` and
> `::test_the_stored_fit_wins_over_a_live_one`.

- [x] **Step 1: Write the failing test**

Add to `tests/test_chart_geometry.py`, alongside the three existing trendline
contract tests (which stay: the live-`trend_info` conversion path is still
what the opposite side goes through):

- `test_a_stored_fit_draws_its_own_side_from_absolute_points` — `p1`/`p2`
  and every pivot come out of the fit unchanged, and the label reads the
  pair's `strength`.
- `test_a_stored_fit_draws_the_other_side_from_its_pair` — the side the fit
  was not taken for is still drawable, converted from the stored pair.
- `test_a_stored_fit_without_pivots_still_draws_its_line` — no touches is
  normal (pre-`pivots` fits, and the trendln fallback), and yields a line
  with no diamonds rather than no line.
- `test_the_stored_fit_wins_over_a_live_one` — both passed is not a conflict
  to resolve at render time.

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_chart_geometry.py -k stored_fit -v`
Expected: FAIL — `overlay_geometry() got an unexpected keyword argument
'trend_fit'`.

- [x] **Step 3: Implement**

Add `trend_fit: dict = None` to `overlay_geometry`, thread it through
`_shape_for` into `_trendline_shape`. There, before the side is chosen, let
the fit's `pair` stand in for `trend_info` (and its `window_bars` for
`trendline_window_bars`); then, when the chosen side IS the fit's own side,
return `_stored_trendline_shape(fit, info)` — `p1`/`p2` from `points` and the
diamonds from `pivots`, copied as absolute epochs, no frame arithmetic.
Everything else falls through to the existing conversion unchanged.

- [x] **Step 4: Run tests to verify they pass**

Run: `python scripts/testrun.py file tests/test_chart_geometry.py`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add swingbot/core/charts/chart_geometry.py tests/test_chart_geometry.py
git commit -m "feat(charts): trendline geometry from the stored fit"
```

---

# Phase 2 — The endpoint

### Task 5: Re-key the chart endpoint to ticker

**Files:**
- Modify: `swingbot/admin/api_v1/market.py:231-360`
- Test: `tests/admin/test_api_v1_market.py` (existing — add cases)

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: `GET /api/v1/market/chart/<ticker>?trade_id=&window=`, returning
  `{ticker, ohlcv, indicators, volume_profile, levels?, overlays, notes}`.
  `overlays` is a list. Task 6 types it; Task 7 draws it.

> **Corrected during execution.** Step 1 below wanted three trade fixtures in
> `tests/admin/conftest.py`, seeded through `PlanStore.add`. The endpoint does
> not read PlanStore: it resolves a trade with `app._trade_for_levels`, which
> is `TradeLog().get_trade_by_id` over `trades.json`. Fixtures built that way
> would never be found, and the tests would pass only by asserting the 404.
> `tests/admin/test_api_v1_market.py` also already has the mechanism —
> `chart_trade`, which monkeypatches `_trade_for_levels` and returns a setter
> for per-test overrides, alongside `frame` for the OHLCV source. The new
> cases extend those rather than adding a second, non-working seeding path.

- [x] **Step 1: Reuse the fixtures the file already has**

`chart_trade(**overrides)` and `frame(n)` in
`tests/admin/test_api_v1_market.py` cover every case this task and Task 6
need. No `tests/admin/conftest.py` change.

- [x] **Step 2: Write the failing test**

`_chart()` now targets `/api/v1/market/chart/AAPL?trade_id=c1`, so every
existing chart test moves to the new key and its `window` queries ride behind
`&`. New cases:

- `test_chart_by_ticker_needs_no_trade` — no `trade_id` gives `levels: null`
  and `overlays: []`, not an error.
- `test_a_plain_ticker_chart_never_reads_a_trade` — `_trade_for_levels` is
  replaced with a raiser, proving no lookup happens at all.
- `test_a_ticker_with_no_data_is_404_without_a_trade`.
- `test_the_window_contract_holds_without_a_trade` — the validation must not
  have been left behind on the trade branch.
- `test_the_trade_ticker_does_not_override_the_path` — a `trade_id` on
  another ticker is a 400, not a plan drawn over the wrong instrument.

The top-level shape assertion gains `ticker`, turns `levels` nullable, and
replaces `overlay` with `overlays` (Task 6 fills the second entry; doing the
rename here keeps those three tests from being rewritten twice).

- [x] **Step 3: Run test to verify it fails**

Run: `python scripts/testrun.py file tests/admin/test_api_v1_market.py`
Expected: FAIL — 404 on `/market/chart/AAPL`, the route is keyed by trade.

- [x] **Step 4: Implement**

Change the route to `@api_v1.route("/market/chart/<ticker>", methods=["GET"])`
and `def chart(ticker: str):`. Read `trade_id` from `request.args`. When absent,
resolve the frame from the ticker alone, return `levels: None` and
`overlays: []`. When present, resolve the trade as today — an unresolvable id
stays a 404, per the existing docstring's reasoning (a plain chart that looks
complete is how a user reads a chart believing the levels are simply missing).

Keep `window`'s contract exactly: default 120, valid 20–500, out of range 400.

- [x] **Step 5: Run tests to verify they pass**

Run: `python scripts/testrun.py file tests/admin/test_api_v1_market.py`
Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add swingbot/admin/api_v1/market.py tests/admin/test_api_v1_market.py
git commit -m "feat(api): one chart endpoint, keyed by ticker"
```

---

### Task 6: Both overlays, the trendline, backfill on read, and the notes

**Files:**
- Modify: `swingbot/admin/api_v1/market.py` (the `chart` handler)
- Test: `tests/admin/test_api_v1_market.py`

**Interfaces:**
- Consumes: Task 5's handler; `fit_trendline` and `TRENDLINE_FIT_KEY` (Task 1);
  `overlay_geometry(..., trend_fit=…)` (Task 4).
- Produces: `overlays: list`, `notes: list[str]` on the payload.

> **Corrected during execution.** Three things, all found against the real
> code.
>
> 1. **The backfill writes through `TradeLog`, not `PlanStore`.** The
>    endpoint resolves trades with `app._trade_for_levels` over
>    `trades.json`; `_store.update(trade)` names a store this path never
>    touches. `TradeLog` had no general update either, so the write is a new
>    `store_trendline_fit(trade_id, fit)` mutator built like
>    `mark_near_close` — same `_LOCK`, because the bot's scan loop writes the
>    same file from another process. It refuses to overwrite an existing fit,
>    which is where idempotence actually lives.
> 2. **The backfill fits with the trade's ENTRY and its horizon's
>    `fib_lookback`**, not this endpoint's `window` and the last close as
>    sketched. Those are `scanning/engine.py`'s arguments; any others produce
>    a different line from the one that trade's PNG already drew — the exact
>    failure this plan exists to end. `test_the_backfill_uses_the_trades_own
>    _entry_not_the_last_close` pins it.
> 3. **These tests use a real `TradeLog` record, not `chart_trade`.** A
>    stubbed `_trade_for_levels` returns a dict no store owns, so the
>    backfill write would land nowhere and the test would prove nothing. They
>    also need a frame a trendline can be fitted to at all — oscillating,
>    with volume spikes at the turns (see `tests/test_trendline_fit.py`), not
>    the random walk `frame` serves.

- [x] **Step 1: Write the failing test**

In `tests/admin/test_api_v1_market.py`: both sides returned target-first and
the one-drawable-side case; the stored fit drawn from its own points with its
pivots as diamonds; backfill on first read; idempotence across two reads; the
fit arguments above; a write failure still serving a 200; and notes naming
the points the line connects (empty without a trade).

- [x] **Step 2: Run test to verify it fails**

Run: `python scripts/testrun.py file tests/admin/test_api_v1_market.py`
Expected: FAIL — 8 failures: `overlays` holds one entry, there is no `notes`
key, and nothing backfills.

- [x] **Step 3: Implement**

Both sides appended instead of the first one breaking the loop, with
`trend_fit=fit` passed to `overlay_geometry`. `_chart_trendline_fit(trade,
df, horizon, is_bull)` returns the stored fit or backfills one;
`_chart_notes(...)` builds the legend text from `trade_chart`'s own
`_trendline_note_lines` / `_fib_note_lines`, so the image and the browser
cannot describe the same line differently.

- [x] **Step 4: Run the full suite**

Run: `python scripts/testrun.py full`
Expected: `0 failed, 0 xfailed`.

- [x] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/market.py tests/admin/test_api_v1_market.py
git commit -m "feat(api): both overlays, the trendline, and lazy fit backfill"
```

---

# Phase 3 — One component

### Tasks 7 & 8: One payload type, one route, one component

**Done as one commit, because they cannot be separated.** Task 7 deletes
`Candle`, `TradeLevels` and `OhlcvResponse`; their only consumers are
`PriceChart` and `OhlcvStore`, which Task 8 deletes. Landing Task 7 alone
would mean committing a tree that does not compile.

**Files:**
- Modify: `frontend/src/app/api/models.ts`, `api-client.ts`,
  `stores/chart.store.ts` (+ spec), `ui/chart/trade-chart.ts`,
  `ui/chart/strategy-overlay.ts` (+ spec), `ui/chart/plan-lines.ts`,
  `workspaces/watchlist/ticker-detail.ts`,
  `workspaces/trades/trade-detail.ts`, `testing/match-media-polyfill.ts`,
  `app.routes.spec.ts`, `chart-harness/main.ts`
- Modify: `swingbot/admin/api_v1/market.py`, `swingbot/admin/app.py`,
  `scripts/dump_chart_payloads.py`, `tests/admin/test_api_v1_market.py`
- Delete: `frontend/src/app/ui/price-chart.ts`,
  `frontend/src/app/stores/ohlcv.store.ts` (+ spec)

- [x] **Step 1: Retype the payload**

`ChartResponse` gains `ticker` and `notes`, turns `levels` nullable and
replaces `overlay` with `overlays: ChartOverlay[]`. `Candle`,
`TradeLevels` and `OhlcvResponse` are deleted. `ApiClient.ohlcv` goes;
`ApiClient.chart` takes a ticker and passes `trade_id` through `toParams`.

- [x] **Step 2: Collapse the two stores into one**

Not "repoint the store that fetched `/market/ohlcv`" — **delete it**.
`OhlcvStore` existed only because the chart endpoint could not be asked for a
ticker without a trade, so `ChartStore` absorbed it: `setTrade(id)` becomes
`setTarget(ticker, tradeId = null)`, and its `isEmpty` computed moves across
(trade-detail's own `chartEmpty` now reads it, so one definition serves both
screens).

`ChartStore` now also refetches on `scan`, which it did not before. A plain
ticker chart has no `trades` events to ride on, so without it the watchlist's
chart would never refresh at all. The reason `OhlcvStore` gave for skipping
`trades` (a year of candles refetched for four horizontal lines) does not
transfer — this store already makes that request for `working_stop`.

- [x] **Step 3: Delete the second component and the second route**

`PriceChart` deleted; `ticker-detail.ts` renders `sb-trade-chart` over
`ChartStore`. The plan's `hasPlan` computed turned out to be unnecessary:
`PlanLines.render` takes `ChartLevels | null` and returns early, which puts
the "no plan at all" case in the same place as the existing "this level is
unset" case rather than in a second one in the component.

`StrategyOverlay.render` takes a list instead of `overlay | null`.

On the Python side the `/market/ohlcv` route goes, and with it `DEFAULT_BARS`
/`MAX_BARS` — and `app.py`'s `ohlcv_bars`/`trade_levels`, which the plan did
not mention and which now have no callers at all. They were shared with the
Jinja UI (deleted in Release B) and with the deleted route; kept as dead code
they would be a second `tp1`/`tp2` mapping waiting to be picked up by
mistake, which is exactly what they were written to prevent.

- [x] **Step 4: Verify**

`npx tsc --noEmit` clean; `npm test` 42 files / 717 tests (was 43/725 —
`ohlcv.store.spec.ts` went with its store, and the chart store spec gained
cases for the ticker-only load, the trade_id parameter, `isEmpty` and the
`scan` refetch). `python scripts/testrun.py full` 1709 passed, 0 failed.

The `/market/ohlcv` tests were not simply deleted: the two that were about
the ENDPOINT rather than its narrower payload — ticker normalisation and the
offline CSV-cache fallback — were ported onto `/market/chart`.
`scripts/dump_chart_payloads.py` and `chart-harness/main.ts` read the payload
too, and both were repointed.

- [x] **Step 5: Commit**

```bash
git commit -m "refactor(chart): one payload, one route, one component"
```

---

# Phase 4 — Legend and prefs

### Task 9: The legend primitive

**Files:**
- Create: `frontend/src/app/ui/chart/primitives/legend-primitive.ts`
- Create: `frontend/src/app/ui/chart/primitives/legend-primitive.spec.ts`
- Modify: `frontend/src/app/ui/chart/strategy-overlay.ts` (the "No text" comment)

**Interfaces:**
- Consumes: `ChartPalette` from `chart-theme.ts`.
- Produces: `LegendPrimitive implements ISeriesPrimitive<Time>`, constructed as
  `new LegendPrimitive(palette, lines: string[])` with
  `setLines(lines: string[]): void`. Task 11 attaches it.

- [ ] **Step 1: Write the failing test**

```ts
import { describe, expect, it } from 'vitest';

import { LegendPrimitive, legendLayout } from './legend-primitive';

const PALETTE = { text: '#fff', textMuted: '#999', surface: '#111' } as never;

describe('legendLayout', () => {
  it('measures a block from its longest line', () => {
    const box = legendLayout(['AAPL · 2w', 'EMA20 support since 2026-06-02'], 11);
    expect(box.width).toBeGreaterThan(box.lineHeight);
    expect(box.height).toBeGreaterThan(box.lineHeight);
  });

  it('clamps its width so it cannot cover the candles', () => {
    const box = legendLayout(['x'.repeat(400)], 11, 320);
    expect(box.width).toBeLessThanOrEqual(320 * 0.4);
  });

  it('renders nothing for no lines', () => {
    expect(legendLayout([], 11).height).toBe(0);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/app/ui/chart/primitives/legend-primitive.spec.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Create the primitive following `box-primitive.ts`'s structure (renderer object,
`draw(target)`, DPR via the target's `useMediaCoordinateSpace`). Keep the
geometry in an exported pure `legendLayout(lines, fontSize, paneWidth?)` so the
measuring rules are testable without a canvas — the same split `plan-lines.ts`
uses for `planLineSpecs`.

Colours and fonts come from the palette and `token()`, never hex.

Then rewrite the "No text" paragraph in `strategy-overlay.ts`:

```
 * **Text lives in the legend, not on the overlay.** This module still draws
 * no strings: the method's name and its fit notes are rendered by
 * `LegendPrimitive` in the pane's corner (v23 Decision 8), which is where
 * TradingView puts them. That decision reversed this file's original "No
 * text" rule and accepted its costs — font tokens, DPR scaling and label
 * collision — in one place rather than per shape.
```

Leaving the old comment would leave the file arguing against the code.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/app/ui/chart/`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/chart/primitives/legend-primitive.ts frontend/src/app/ui/chart/primitives/legend-primitive.spec.ts frontend/src/app/ui/chart/strategy-overlay.ts
git commit -m "feat(chart): a TradingView-style legend primitive"
```

---

### Task 10: Remembered indicator toggles

**Files:**
- Create: `frontend/src/app/ui/chart/chart-prefs.ts`
- Create: `frontend/src/app/ui/chart/chart-prefs.spec.ts`
- Reference: `frontend/src/app/ui/table-prefs.ts` — follow its persistence shape

**Interfaces:**
- Consumes: nothing.
- Produces: `ChartPrefs` service with
  `visible: Signal<Record<ChartLayer, boolean>>`, `toggle(layer: ChartLayer)`,
  and `export type ChartLayer = 'macd' | 'rsi' | 'keltner' | 'volumeProfile' | 'plan'`.
  Task 11 injects it.

- [ ] **Step 1: Write the failing test**

```ts
import { describe, expect, it } from 'vitest';

import { ChartPrefs } from './chart-prefs';

describe('ChartPrefs', () => {
  it('shows every layer by default', () => {
    const prefs = new ChartPrefs(new Map());
    expect(prefs.visible()['macd']).toBe(true);
    expect(prefs.visible()['plan']).toBe(true);
  });

  it('remembers a hidden layer', () => {
    const store = new Map<string, string>();
    new ChartPrefs(store).toggle('rsi');
    expect(new ChartPrefs(store).visible()['rsi']).toBe(false);
  });

  it('ignores a corrupt stored value rather than throwing', () => {
    const store = new Map([['sb.chart.layers', '{oops']]);
    expect(new ChartPrefs(store).visible()['macd']).toBe(true);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/app/ui/chart/chart-prefs.spec.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Follow `table-prefs.ts`: a signal seeded from storage, written on every change,
with a `try/catch` around the parse so a corrupt value degrades to defaults
rather than taking the workspace down. Take the storage as a constructor
argument so the tests above need no browser.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/app/ui/chart/chart-prefs.spec.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/chart/chart-prefs.ts frontend/src/app/ui/chart/chart-prefs.spec.ts
git commit -m "feat(chart): remembered indicator visibility"
```

---

### Task 11: Wire the legend and the toggles into the chart

**Files:**
- Modify: `frontend/src/app/ui/chart/trade-chart.ts`
- Modify: `frontend/src/app/ui/chart/chart-theme.ts` (crosshair magnet)
- Test: `frontend/src/app/ui/chart/` specs

**Interfaces:**
- Consumes: `LegendPrimitive` (Task 9), `ChartPrefs` (Task 10),
  `ChartResponse.notes` (Task 7).
- Produces: the finished chart.

- [ ] **Step 1: Write the failing test**

Assert through the component's own exposed state rather than through the canvas
— jsdom draws nothing, so any assertion about pixels would pass on a chart that
renders nothing at all. Add to `trade-chart.ts` two `protected readonly`
computeds the tests can read, which the template already needs anyway:

```ts
  /** Which panes this payload and the current prefs actually produce. */
  protected readonly activeLayers = computed<ChartLayer[]>(() => …);
  /** Exactly the strings handed to LegendPrimitive. */
  protected readonly legendLines = computed<string[]>(() => …);
```

Then in `frontend/src/app/ui/chart/trade-chart.spec.ts` (create it — this
component has no spec today):

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { ChartPrefs } from './chart-prefs';
import { TradeChart } from './trade-chart';

const PAYLOAD = {
  ticker: 'AAPL',
  ohlcv: [{ t: 1767225600, o: 1, h: 2, l: 0.5, c: 1.5, v: 100 }],
  indicators: { rsi: [50] },
  volume_profile: [],
  levels: null,
  overlays: [{ side: 'target', source: 'EMA20', shape: { kind: 'curve', points: [] } }],
  notes: ['Trendline 2026-06-02 → 2026-08-01'],
} as never;

describe('TradeChart', () => {
  let prefs: ChartPrefs;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    prefs = TestBed.inject(ChartPrefs);
  });

  it('drops a pane when its layer is toggled off', () => {
    const fixture = TestBed.createComponent(TradeChart);
    fixture.componentRef.setInput('data', PAYLOAD);
    fixture.detectChanges();
    const before = fixture.componentInstance['activeLayers']();
    expect(before).toContain('rsi');

    prefs.toggle('rsi');
    fixture.detectChanges();
    expect(fixture.componentInstance['activeLayers']()).not.toContain('rsi');
  });

  it('feeds the legend the payload notes and every drawn method', () => {
    const fixture = TestBed.createComponent(TradeChart);
    fixture.componentRef.setInput('data', PAYLOAD);
    fixture.detectChanges();
    const lines = fixture.componentInstance['legendLines']();
    expect(lines).toContain('EMA20');
    expect(lines.some((l: string) => l.includes('Trendline'))).toBe(true);
  });

  it('draws no plan layer when the payload has no levels', () => {
    const fixture = TestBed.createComponent(TradeChart);
    fixture.componentRef.setInput('data', PAYLOAD);
    fixture.detectChanges();
    expect(fixture.componentInstance['activeLayers']()).not.toContain('plan');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/app/ui/chart/`
Expected: FAIL.

- [ ] **Step 3: Implement**

Inject `ChartPrefs`; gate each pane and overlay's creation on
`prefs.visible()[layer]` inside the existing effects. Attach `LegendPrimitive`
to the price pane's series with lines built from `data().notes` plus each
overlay's `source`. Update the crosshair readout on `subscribeCrosshairMove`.

In `chart-theme.ts`, add TradingView's magnet behaviour to `chartOptions`:

```ts
    crosshair: {
      mode: CrosshairMode.Magnet,
      vertLine: { color: palette.textMuted, labelBackgroundColor: palette.accent },
      horzLine: { color: palette.textMuted, labelBackgroundColor: palette.accent },
    },
```

- [ ] **Step 4: Verify end to end**

Run: `cd frontend && npm test`
Expected: PASS.
Run: `cd frontend && npm start`, open a trade whose confirmation is a trendline,
and confirm: the line draws, its swing pivots are diamonds and there are as
many of them as the strength label claims, both overlays appear
with the stop side dimmed, and the legend prints the fit note naming the two
dates the line connects.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/chart/
git commit -m "feat(chart): legend, magnet crosshair and layer toggles"
```

Then the ui release marker, its own commit, last:

```bash
# VERSION.json: ui -> next minor, ui_updated to now
git add VERSION.json
git commit -m "release(ui): 1.4.0 -- the annotated interactive trade chart"
```

**`1.4.0`, not the `1.3.0` this plan first predicted.** This worktree branched
at ui `1.2.4`; `main` has since shipped `1.3.0` (the Versions workspace,
43296cf), so `VERSION.json` here is stale and *will* conflict on merge. Take
`main`'s side, then apply this bump on top — never resolve it by keeping the
worktree's copy, which would silently un-ship 1.3.0.

---

## Definition of done

- A trendline-confirmed trade draws its line in the SPA, with one diamond per
  swing pivot the line was fit through — `strength` of them, not two.
- The Discord PNG and the SPA chart draw the *same* line for the same trade.
- An old trade renders a line on first view and does not refit on the second.
- Both sides' overlays appear, stop dimmed.
- The legend prints the fit notes; hiding a pane survives a reload.
- The watchlist ticker chart is the same component, with no plan layer.
- `python scripts/testrun.py full` green; `npm test` green; `npx tsc --noEmit`
  clean.
- `VERSION.json`: `bot` patch after Task 3, `ui` minor after Task 11.
