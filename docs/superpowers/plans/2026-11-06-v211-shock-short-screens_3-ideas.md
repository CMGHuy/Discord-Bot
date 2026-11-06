# v211 — Shock-conditioned short screens, Part 3: the two ideas (V211-7..V211-9)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Spec:** [v209 — Market-shock detector (shadow) and shock-conditioned short screens](../specs/2026-11-05-v209-market-shock-detector-design.md), § Track 2 → "The shared daily inputs" (the daily shock state), "Idea 1", "Idea 2", "Printed alongside each verdict" (the unconditional control).
**Index:** [`2026-11-06-v211-shock-short-screens_0-index.md`](2026-11-06-v211-shock-short-screens_0-index.md) — Goal, Global Constraints (the frozen definitions, copied there verbatim), Review Focus, Parallelisation and the task ledger live there and bind every task below.

This part writes the frozen definitions as code: the shared family module
with the daily SHOCK state and its episodes (V211-7), then one idea module per
pre-registered idea, each with its unconditional control and its registry pins
(V211-8, V211-9). **Nothing here is tuned**: every number is the spec's, and a
test pins each one. All three tasks run in the worktree
`.claude/worktrees/2026-11-06-v211-shock-short-screens`. V211-7 may run beside
part 2 (disjoint files); V211-8 needs V211-4..6 merged into the worktree branch
(it reads `CONTEXT_KIND`, the level load path and V211-5's `_overlap`), and
V211-9 follows V211-8.

# Phase C — ideas

### Task V211-7: `_shock_breakdown.py`: frozen constants, daily SHOCK state with episodes

**Model:** opus — the state machine is the frozen definition both one-shot screens read; an off-by-one in release or re-entry, or a forward-filled date, silently changes both verdicts.

**Files:**
- Create: `swingbot/core/backtesting/screen/ideas/_shock_breakdown.py`
- Create: `tests/backtesting/screen/test_shock_breakdown_state.py`
- Modify: `tests/backtesting/screen/helpers.py` (append `shock_context`, `episodes_covering`; existing helpers untouched — test-only, used by V211-8/V211-9)

**Interfaces:**
- Consumes: `swingbot.core.backtesting.screen.indicators.atr(df, n=14)`, `indicators.rolling_min(values, n)` (exist).
- Produces (index ledger, final):
  - constants `BREADTH = "BREADTH_ATR1"`, `VIX = "^VIX"`, `CONTEXT = (BREADTH, VIX)`, `ENTER_BREADTH = 0.40`, `RELEASE_BREADTH = 0.10`, `LOW_WINDOW = 20`, `SHOCK_PARAMS = {"breadth": "BREADTH_ATR1", "vix": "^VIX", "enter": 0.40, "release": 0.10}`, `FAMILY = ("shock_support_break_short", "shock_failed_bounce_short")`, `SOURCE` (the string in Step 4).
  - `shock_state(breadth: pd.Series, vix: pd.Series) -> pd.DataFrame` — index = `breadth.index`; columns `shock` (bool), `episode` (int64: 0 when NORMAL, then 1, 2, … per episode in calendar order).
  - `ticker_state(df: pd.DataFrame, context: Mapping[str, pd.DataFrame]) -> pd.DataFrame` — the same two columns on `df.index`; a date the context lacks is `False`/`0` (never forward-filled); a context-only date is dropped.
  - `prior_low(df: pd.DataFrame, n: int = LOW_WINDOW) -> pd.Series` = `min(Low[t−n .. t−1])` (NaN until `n` prior bars).
  - `prior_atr(df: pd.DataFrame) -> pd.Series` = `indicators.atr(df).shift(1)`.
  - test helpers in `tests/backtesting/screen/helpers.py`: `shock_context(index, episodes) -> dict[str, pd.DataFrame]` and `episodes_covering(positions, n, *, length=6) -> list[tuple[int, int]]`.

**The reading pinned here (spec § The shared daily inputs, frozen):** NORMAL → SHOCK on any date with `d_breadth[t] ≥ 0.40` (a new episode id). While SHOCK, the first date with `d_breadth[t] ≤ 0.10` **and** `^VIX Close[t] < Close[t−1]` releases; that date is still SHOCK (same episode). The next date is NORMAL unless `d_breadth ≥ 0.40` again, which starts a **new** episode. A SHOCK date with breadth ≥ 0.40 never starts a new episode. A NaN breadth neither enters nor releases; a `^VIX` close missing on `t` or `t−1` is "not down". `t−1` is the previous row of the `^VIX` series itself (the loader has already checked that both calendars equal SPY's sessions).

- [ ] **Step 1: Append the two test helpers to `tests/backtesting/screen/helpers.py`**

```python
def shock_context(index, episodes) -> dict:
    """BREADTH_ATR1 and ^VIX frames on ``index`` for the v211 shock tests.
    Each (enter_pos, release_pos) pair, enter_pos < release_pos: breadth 0.45
    on enter_pos, 0.20 strictly between, 0.05 on release_pos with ^VIX one
    point down that day. Elsewhere breadth 0.05 and ^VIX flat at 20, so
    nothing else enters or releases."""
    index = pd.DatetimeIndex(index)
    n = len(index)
    breadth, vix = np.full(n, 0.05), np.full(n, 20.0)
    for enter_pos, release_pos in episodes:
        breadth[enter_pos] = 0.45
        breadth[enter_pos + 1:release_pos] = 0.20
        vix[release_pos] = 19.0
    return {"BREADTH_ATR1": frame(breadth, index=index, opens=breadth, highs=breadth,
                                  lows=breadth, volumes=np.full(n, 400.0)),
            "^VIX": frame(vix, index=index, opens=vix, highs=vix, lows=vix,
                          volumes=np.zeros(n))}


def episodes_covering(positions, n, *, length=6) -> list:
    """Non-overlapping (enter, release) pairs: each enters one bar before a
    position and releases ``length`` bars after entering; a position inside
    (or the bar after) the previous episode, or too close to the end, is skipped."""
    out, last = [], -10
    for p in (int(p) for p in positions):
        enter, release = p - 1, p - 1 + length
        if enter > last + 1 and enter >= 0 and release < n:
            out.append((enter, release))
            last = release
    return out
```

- [ ] **Step 2: Write the failing tests** — `tests/backtesting/screen/test_shock_breakdown_state.py`:

```python
"""v211 (spec v209 § Track 2): the frozen daily SHOCK state both shock ideas read."""
import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen import ideas, indicators
from swingbot.core.backtesting.screen.ideas import _shock_breakdown as sb
from tests.backtesting.screen.helpers import frame, random_walk, shock_context

IDX = pd.bdate_range("2009-06-01", periods=11)
#:           0     1     2     3     4     5     6     7     8     9     10
BREADTH = [0.05, 0.45, 0.20, 0.08, 0.08, 0.30, 0.42, 0.09, 0.41, 0.05, 0.02]
VIX =     [20.0, 21.0, 22.0, 23.0, 22.0, 21.0, 25.0, 24.0, 26.0, 25.0, 24.0]


def _series(values, index=IDX):
    return pd.Series(np.asarray(values, dtype=float), index=index)


def test_the_constants_are_the_frozen_spec_values():
    assert (sb.BREADTH, sb.VIX, sb.CONTEXT) == ("BREADTH_ATR1", "^VIX", ("BREADTH_ATR1", "^VIX"))
    assert (sb.ENTER_BREADTH, sb.RELEASE_BREADTH, sb.LOW_WINDOW) == (0.40, 0.10, 20)
    assert sb.SHOCK_PARAMS == {"breadth": "BREADTH_ATR1", "vix": "^VIX",
                               "enter": 0.40, "release": 0.10}
    assert sb.FAMILY == ("shock_support_break_short", "shock_failed_bounce_short")
    assert sb.SOURCE.startswith("v209 spec § Track 2")


def test_the_family_module_is_not_a_registered_idea():
    assert "_shock_breakdown" not in ideas.IDEA_MODULES
    assert not hasattr(sb, "CAP") and not hasattr(sb, "events")


def test_the_spec_reading_release_day_is_shock_and_re_entry_is_a_new_episode():
    """Bar 3: breadth 0.08 but ^VIX up -> stays SHOCK. Bar 4: 0.08 and ^VIX
    down -> released, still SHOCK. Bar 6 enters episode 2; bar 7 releases it;
    bar 8 (the day after the release) re-enters as episode 3; bar 9 releases;
    bar 10 is NORMAL although ^VIX is down."""
    out = sb.shock_state(_series(BREADTH), _series(VIX))
    assert out["shock"].tolist() == [False, True, True, True, True, False,
                                     True, True, True, True, False]
    assert out["episode"].tolist() == [0, 1, 1, 1, 1, 0, 2, 2, 3, 3, 0]
    assert out.index.equals(IDX)
    assert out["shock"].dtype == bool and out["episode"].dtype == np.int64


def test_the_thresholds_are_inclusive_and_vix_must_strictly_fall():
    idx = IDX[:5]
    out = sb.shock_state(_series([0.40, 0.10, 0.10, 0.39, 0.0], idx),
                         _series([20.0, 20.0, 19.0, 18.0, 17.0], idx))
    # 0.40 enters; 0.10 with ^VIX flat holds; 0.10 with ^VIX down releases
    # (still SHOCK); 0.39 the next day does not re-enter.
    assert out["shock"].tolist() == [True, True, True, False, False]
    assert out["episode"].tolist() == [1, 1, 1, 0, 0]


def test_a_second_spike_inside_an_episode_keeps_the_episode_id():
    idx = IDX[:4]
    out = sb.shock_state(_series([0.50, 0.20, 0.60, 0.20], idx),
                         _series([20.0, 19.0, 18.0, 17.0], idx))
    assert out["shock"].all() and out["episode"].tolist() == [1, 1, 1, 1]


def test_nan_breadth_neither_enters_nor_releases_and_a_missing_vix_is_not_down():
    idx = IDX[:5]
    out = sb.shock_state(_series([np.nan, 0.45, np.nan, 0.05, 0.05], idx),
                         _series([20.0, 21.0, 20.0, np.nan, 19.0], idx))
    # bar 2: NaN breadth holds SHOCK; bar 3: ^VIX[t] missing; bar 4: ^VIX[t-1] missing.
    assert out["shock"].tolist() == [False, True, True, True, True]


def test_the_state_on_t_reads_no_later_bar():
    rng = np.random.default_rng(11)
    breadth = _series(rng.uniform(0.0, 0.6, 400), pd.bdate_range("2009-06-01", periods=400))
    vix = random_walk(400, seed=12, start="2009-06-01")["Close"]
    full = sb.shock_state(breadth, vix)
    assert full["episode"].max() >= 5                         # non-vacuous
    for t in (30, 99, 100, 250, 399):
        part = sb.shock_state(breadth.iloc[: t + 1], vix.iloc[: t + 1])
        pd.testing.assert_frame_equal(part, full.iloc[: t + 1])


def test_ticker_state_never_forward_fills_a_date_the_context_lacks():
    stock_idx = pd.bdate_range("2010-01-04", periods=30)
    ctx = shock_context(stock_idx, [(5, 15)])
    gap = stock_idx[10]
    thin = {k: v.drop(gap) for k, v in ctx.items()}
    out = sb.ticker_state(frame(np.full(30, 50.0), index=stock_idx), thin)
    assert out.index.equals(stock_idx)
    assert not out.loc[gap, "shock"] and out.loc[gap, "episode"] == 0
    assert out["shock"].iloc[5:16].sum() == 10 and out["shock"].iloc[15]
    assert out["shock"].dtype == bool and out["episode"].dtype == np.int64


def test_ticker_state_drops_context_only_dates():
    ctx_idx = pd.bdate_range("2010-01-04", periods=30)
    ctx = shock_context(ctx_idx, [(2, 8)])
    stock = frame(np.full(20, 50.0), index=ctx_idx[5:25])
    out = sb.ticker_state(stock, ctx)
    assert out.index.equals(stock.index)
    assert out["shock"].tolist()[:5] == [True, True, True, True, False]


def test_prior_low_is_the_twenty_bars_before_t_and_prior_atr_is_dated_t_minus_1():
    df = random_walk(120, seed=5)
    low = df["Low"].to_numpy()
    got = sb.prior_low(df).to_numpy()
    assert np.isnan(got[:20]).all()
    assert all(got[t] == low[t - 20:t].min() for t in range(20, 120))
    pd.testing.assert_series_equal(sb.prior_atr(df), indicators.atr(df).shift(1))
```

(Episode `(5, 15)` with bar 10 dropped from the context: bars 5..15 are SHOCK except the dropped date, so 10 of the 11; the stock frame `ctx_idx[5:25]` of episode `(2, 8)` starts at bar 5, so its first four dates 5..8 are SHOCK.)

- [ ] **Step 3: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_shock_breakdown_state.py`
Expected: FAIL — `ImportError: cannot import name '_shock_breakdown'`.

- [ ] **Step 4: Implement `swingbot/core/backtesting/screen/ideas/_shock_breakdown.py`**

Follow the `_range_breakdown.py` pattern (module docstring stating the frozen reading, constants, helpers, no `CAP`/`events`).

- Docstring: *"v211 shock breakdown family (spec v209 § Track 2, frozen 2026-11-05): the daily shock state SHOCK_D both shock ideas read. Enter SHOCK on BREADTH_ATR1 >= 0.40; while SHOCK, release on the first date with BREADTH_ATR1 <= 0.10 and the ^VIX close below the previous ^VIX close, the release date itself still SHOCK; the next date is NORMAL unless BREADTH_ATR1 >= 0.40 again (a new episode). No RECOVERY tier: daily bars cannot see the intraday repair. The state on t reads context bars dated <= t only; a stock date the context lacks is NORMAL, never forward-filled. Not the live market-shock detector (no sector clause, no fast path, no VIX relief); a pass does not license its labels. Not an idea module (no CAP, no events): the leading underscore keeps it out of IDEA_MODULES."*
- Constants exactly as the Interfaces block; `SOURCE = ("v209 spec § Track 2 (frozen 2026-11-05): breadth-shock-conditioned breakdown shorts, after the 2026-11-05 session the long book lost 13.9R")`.
- `_vix_down(vix: pd.Series, index: pd.DatetimeIndex) -> np.ndarray` — `(vix < vix.shift(1))` on the `^VIX` series' own index, then `.reindex(index, fill_value=False)`, as a bool array (NaN compares False).
- `_step(shock: bool, episode: int, breadth: float, down: bool) -> tuple[bool, int, bool]` — returns `(shock_today, episode_today, shock_tomorrow)`: if not `shock` and `breadth >= ENTER_BREADTH`, enter with `episode + 1`; `shock_tomorrow = shock_today and not (breadth <= RELEASE_BREADTH and down)`. A NaN breadth compares False on both tests. This keeps `shock_state`'s loop body to one call.
- `shock_state(breadth, vix)` — one pass over `breadth.to_numpy(dtype=float)` carrying `(shock, last_episode)`; record `shock_today` and `episode_today if shock_today else 0`; build the frame with `shock` as `bool` and `episode` as `np.int64` on `breadth.index`.
- `ticker_state(df, context)` — `state = shock_state(context[BREADTH]["Close"], context[VIX]["Close"])`; return `pd.DataFrame({"shock": state["shock"].reindex(df.index, fill_value=False).astype(bool), "episode": state["episode"].reindex(df.index, fill_value=0).astype(np.int64)}, index=df.index)`.
- `prior_low(df, n=LOW_WINDOW)` = `indicators.rolling_min(df["Low"].shift(1), n)`; `prior_atr(df)` = `indicators.atr(df).shift(1)` (one-line docstrings naming the bars read).

- [ ] **Step 5: Run the tests to verify they pass, then the neighbours**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_shock_breakdown_state.py`
Expected: PASS (10 tests).

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_ideas_registry.py`
Expected: PASS, unchanged (the family module is not registered).

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_import_guard.py`
Expected: PASS.

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0, no new function at CC ≥ 15.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/screen/ideas/_shock_breakdown.py tests/backtesting/screen/test_shock_breakdown_state.py tests/backtesting/screen/helpers.py
git commit -m "feat(v211): shock breakdown family -- frozen daily SHOCK state with episodes (V211-7)"
```

### Task V211-8: Idea 1 `shock_support_break_short` + registry

**Model:** opus — the first registered level-context short; "first break per episode" and the control's "fresh break" are frozen readings a one-shot screen spends, and the registry pins are exact.

**Files:**
- Create: `swingbot/core/backtesting/screen/ideas/shock_support_break_short.py`
- Modify: `swingbot/core/backtesting/screen/ideas/__init__.py` (`IDEA_MODULES` only)
- Modify: `tests/backtesting/screen/test_ideas_registry.py` (the exact pins, same commit as `IDEA_MODULES`)
- Create: `tests/backtesting/screen/test_idea_shock_support_break_short.py`
- Modify: `tests/backtest_scripts/test_screen_context_runner.py` (`_ctx_cache` default `context`; one runner test appended)
- Modify: `tests/backtest_scripts/test_screen_level_context.py` (one line of V211-4's `test_context_kinds_and_the_default`, see Step 5 — its "every registered idea is `z`" pin stops being true the moment a level idea registers)

**Interfaces:**
- Consumes (V211-7): `sb.CONTEXT`, `sb.FAMILY`, `sb.SHOCK_PARAMS`, `sb.LOW_WINDOW`, `sb.SOURCE`, `sb.ticker_state(df, context)`, `sb.prior_low(df)`; test helpers `shock_context`, `episodes_covering`. (V211-4): module attr `CONTEXT_KIND` read by `ideas._load` into `Idea.context_kind`; level loads skip the z-coverage floor. (V211-5): `_restricted` returns `None` for a level idea, `_overlap` passes the real context.
- Produces (index ledger, final): module attrs `CAP = 10`, `RACE = "fixed"`, `DIRECTION = "short"`, `CONTEXT = sb.CONTEXT`, `CONTEXT_KIND = "level"`, `FAMILY = sb.FAMILY`, `PARAMS = {**sb.SHOCK_PARAMS, "low_window": 20, "side": "short"}`, `SUMMARY`, `SOURCE = sb.SOURCE`; `low_break(df) -> pd.Series` (bool, `Close[t] < min(Low[t−20 .. t−1])`); `events(df, context) -> pd.Series` (bool, name `shock_support_break_short`, on `df.index`); `control_events(df) -> pd.Series` (bool, name `shock_support_break_short_control`).

**The frozen trigger (spec § Idea 1):** SHOCK on `t`; `Close[t] < min(Low[t−20 .. t−1])`; and no earlier bar of the **same** SHOCK episode closed below its own prior 20-day low (first break only). A new episode — including one entered the day after a release — resets the clause. **Control** (index OPEN, the spec's "same trigger with the shock state ignored"): a *fresh* 20-day-low close, `low_break[t]` and not `low_break[t−1]`, because "first in the episode" has no episode once the shock state is ignored.

- [ ] **Step 1: Write the failing idea tests** — `tests/backtesting/screen/test_idea_shock_support_break_short.py`:

```python
"""v211 Idea 1 (spec v209 § Track 2): the first close below the prior 20-day low
inside a SHOCK episode, short at the next open."""
import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen.ideas import _shock_breakdown as sb
from swingbot.core.backtesting.screen.ideas import shock_support_break_short as idea
from tests.backtesting.screen.helpers import (assert_prefix_stable, episodes_covering,
                                              frame, random_walk, shock_context)

#: Breaks (Close < prior 20-day low, Low = Close - 1): bars 50, 51, 60, 75.
CLOSES = [100.0] * 50 + [97.0, 95.0] + [95.0] * 8 + [92.0] * 15 + [89.0] * 5
#: Episode 1 = bars 48..58 (released on 58); episode 2 re-enters on 59, the
#: day after the release, and releases on 70; bar 75 is NORMAL.
EPISODES = [(48, 58), (59, 70)]


def _stock():
    return frame(CLOSES, start="2010-01-04")


def _hits(series):
    return np.flatnonzero(series.to_numpy()).tolist()


def test_the_constants_are_the_frozen_spec_values():
    assert (idea.CAP, idea.RACE, idea.DIRECTION) == (10, "fixed", "short")
    assert idea.CONTEXT == ("BREADTH_ATR1", "^VIX") and idea.CONTEXT_KIND == "level"
    assert idea.FAMILY == ("shock_support_break_short", "shock_failed_bounce_short")
    assert idea.PARAMS == {"breadth": "BREADTH_ATR1", "vix": "^VIX", "enter": 0.40,
                           "release": 0.10, "low_window": 20, "side": "short"}
    assert idea.SOURCE == sb.SOURCE and idea.SUMMARY.strip()
    assert not hasattr(idea, "ENTRY") and not hasattr(idea, "levels")


def test_the_fixture_breaks_where_the_comment_says():
    assert _hits(idea.low_break(_stock())) == [50, 51, 60, 75]


def test_fires_on_the_first_break_of_each_episode_only():
    """51 is the second break of episode 1; 60 is the first break of episode
    2, entered the day after episode 1's release; 75 breaks while NORMAL."""
    df = _stock()
    out = idea.events(df, shock_context(df.index, EPISODES))
    assert _hits(out) == [50, 60]
    assert out.dtype == bool and out.name == "shock_support_break_short"
    assert out.index.equals(df.index)


def test_without_any_episode_nothing_fires():
    df = _stock()
    assert not idea.events(df, shock_context(df.index, [])).any()


def test_one_long_episode_fires_once():
    df = _stock()
    assert _hits(idea.events(df, shock_context(df.index, [(40, 79)]))) == [50]


def test_a_stock_date_the_context_lacks_is_never_an_event():
    df = _stock()
    thin = {k: v.drop(df.index[50]) for k, v in shock_context(df.index, EPISODES).items()}
    assert not idea.events(df, thin).iloc[50]


def test_the_control_is_every_fresh_break_with_the_shock_state_ignored():
    out = idea.control_events(_stock())
    assert _hits(out) == [50, 60, 75]
    assert out.dtype == bool and out.name == "shock_support_break_short_control"


def test_events_on_t_read_no_later_stock_or_context_bar():
    df = random_walk(700, seed=21)
    ctx = shock_context(df.index, episodes_covering(_hits(idea.low_break(df)), len(df)))

    def fn(d):
        return idea.events(d, {k: v.loc[: d.index[-1]] for k, v in ctx.items()})

    assert fn(df).sum() >= 3                                  # non-vacuous
    assert_prefix_stable(fn, df, [100, 250, 400, 699])
    assert_prefix_stable(idea.control_events, df, [100, 250, 400, 699])
```

- [ ] **Step 2: Write the failing registry and runner tests**

`tests/backtesting/screen/test_ideas_registry.py` — edit the exact pins (each existing assertion keeps its entries; add these):
- `test_registry_holds_the_first_batch_in_spec_order_then_later_ideas`: the tuple ends `"range_breakdown_stop", "shock_support_break_short")`.
- `test_time_caps_are_the_spec_values`: add `"shock_support_break_short": 10`.
- `test_frozen_parameter_sets`: add `assert dict(IDEAS["shock_support_break_short"].params) == {"breadth": "BREADTH_ATR1", "vix": "^VIX", "enter": 0.40, "release": 0.10, "low_window": 20, "side": "short"}`.
- `test_every_registered_idea_pins_its_direction_and_entry`: add `"shock_support_break_short": "short"` to the direction dict and `"shock_support_break_short": "next_open"` to the entry dict; change the `older` filter to `special = ("range_breakdown_close", "range_breakdown_stop", "shock_support_break_short")` / `older = {n: i for n, i in IDEAS.items() if n not in special}` (the `breakdown` name stays for the two v182 assertions below it).
- `test_every_registered_idea_is_raced_under_one_pinned_shape`: add `"shock_support_break_short": "fixed"`.
- rename `test_only_the_two_intermarket_ideas_read_context_series` to `test_only_the_intermarket_and_shock_ideas_read_context_series` and add `"shock_support_break_short": ("BREADTH_ATR1", "^VIX")` to its dict.
- import `shock_support_break_short` beside the two v182 modules, and append:

```python
def test_the_shock_support_idea_pins_level_context_control_and_family():
    idea = IDEAS["shock_support_break_short"]
    assert idea.context_kind == "level"
    assert idea.control is shock_support_break_short.control_events
    assert idea.family == ("shock_support_break_short", "shock_failed_bounce_short")
    assert idea.levels is None and idea.entry == "next_open"
    assert {n for n, i in IDEAS.items() if i.context_kind != "z"} == {"shock_support_break_short"}
```

`tests/backtest_scripts/test_screen_context_runner.py`:
- `_ctx_cache(tmp_path, *, tickers=("AAA", "BBB"), context=("TLT", "UUP", "BREADTH_ATR1", "^VIX"))` — `_hash_records` spans the registered union (`context_tickers()`), which now holds both new stems; the docstring gains *"(v211: BREADTH_ATR1 and ^VIX too, as random walks — only their bytes are hashed here)"*. No other line of the file changes; `PARITY_DIGESTS` stays untouched.
- append (the file already imports `np`, `random_walk`, `ALWAYS`, `IDEAS` and `screen_idea`):

```python
def test_the_shock_support_idea_screens_short_with_its_context_and_control():
    """v211: a level-context short on the real call path -- events read the
    context, the control book runs, the v174 restricted null does not."""
    from swingbot.core.backtesting.screen.ideas import shock_support_break_short as idea_mod
    from tests.backtesting.screen.helpers import episodes_covering, shock_context
    df = random_walk(2600)
    hits = np.flatnonzero(idea_mod.low_break(df).to_numpy())
    ctx = shock_context(df.index, episodes_covering(hits, len(df)))
    out = screen_idea.screen_ticker(IDEAS["shock_support_break_short"], "AAA", df,
                                    ALWAYS, context=ctx)
    assert out.events                                         # non-vacuous
    assert out.control                                        # the control book ran
    assert out.restricted is None and out.depths is None and out.repriced is None
```

- [ ] **Step 3: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_idea_shock_support_break_short.py`
Expected: FAIL — `ImportError: cannot import name 'shock_support_break_short'`.

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_ideas_registry.py`
Expected: FAIL — the import and the new pins.

- [ ] **Step 4: Implement `swingbot/core/backtesting/screen/ideas/shock_support_break_short.py` and register it**

- Module docstring: *"Shock support break, short (v211, frozen 2026-11-05 in spec v209 § Track 2). On a SHOCK_D date (_shock_breakdown.py) the stock closes below the lowest Low of the 20 bars before it, and it is the first such close in this SHOCK episode; the screen's race shorts the next open (fixed 1.5/3 ATR, 10-bar cap). The control is every fresh 20-day-low close with the shock state ignored (printed, never gating). One family with shock_failed_bounce_short; a fail closes exactly this definition."*
- Constants exactly as the Interfaces block (`PARAMS` built from `sb.SHOCK_PARAMS` and `sb.LOW_WINDOW`); `SUMMARY = ("SHOCK_D on t (BREADTH_ATR1 >= 0.40 enters; <= 0.10 with ^VIX down releases) and close[t] < min(Low[t-20..t-1]), the first such close in the episode (short, next open)")`.
- `low_break(df)` — `(df["Close"] < sb.prior_low(df))` as bool (NaN compares False, so the 20 warm-up bars are False).
- `_first_per_episode(hits: pd.Series, episode: pd.Series) -> pd.Series` — `hits & (hits.astype(int).groupby(episode).cumsum() - hits.astype(int) == 0)`; `hits` is already False outside SHOCK, so episode 0 never fires.
- `events(df, context)` — `state = sb.ticker_state(df, context)`; `_first_per_episode(low_break(df) & state["shock"], state["episode"])`, renamed `shock_support_break_short`.
- `control_events(df)` — `brk = low_break(df)`; `(brk & ~brk.shift(1, fill_value=False))`, renamed `shock_support_break_short_control`.

`swingbot/core/backtesting/screen/ideas/__init__.py`: append `"shock_support_break_short"` to `IDEA_MODULES` (last). Nothing else in the file changes (V211-4 already reads `CONTEXT_KIND`).

- [ ] **Step 5: Update V211-4's registry-wide kind pin** in `tests/backtest_scripts/test_screen_level_context.py`

In `test_context_kinds_and_the_default`, replace `assert {idea.context_kind for idea in IDEAS.values()} == {"z"}` with:

```python
    assert {n for n, i in IDEAS.items() if i.context_kind != "z"} <= {
        "shock_support_break_short", "shock_failed_bounce_short"}
```

(every idea registered before v211 stays `z`; the two shock ideas are the only level ones.)

- [ ] **Step 6: Run the tests to verify they pass, then the byte-identical pins**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_idea_shock_support_break_short.py`
Expected: PASS (8 tests).

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_ideas_registry.py`
Expected: PASS.

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_context_runner.py`
Expected: PASS, `PARITY_DIGESTS` untouched (a digest failure is a stop, never an update).

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_level_context.py`
Expected: PASS, including `test_every_pre_v211_hypothesis_is_byte_identical` with its golden untouched.

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py`
Expected: PASS, untouched.

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

Run: `git diff --stat main...HEAD -- swingbot/ | grep -v "backtesting/screen"`
Expected: only `swingbot/core/marketdata/training_data.py` (V211-1) may appear; any other `swingbot/` file outside the screen is a review stop (index Global Constraints).

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/backtesting/screen/ideas/shock_support_break_short.py swingbot/core/backtesting/screen/ideas/__init__.py tests/backtesting/screen/test_idea_shock_support_break_short.py tests/backtesting/screen/test_ideas_registry.py tests/backtest_scripts/test_screen_context_runner.py tests/backtest_scripts/test_screen_level_context.py
git commit -m "feat(v211): idea shock_support_break_short -- first 20-day-low close per SHOCK episode, short (V211-8)"
```

### Task V211-9: Idea 2 `shock_failed_bounce_short` + registry

**Model:** opus — five frozen conditions with three different bar offsets (`b−10..b−2`, `b−2`, `b+1..t−1`) and a "latest `b`" rule; the vectorised form must equal the literal reading on every bar of a one-shot screen.

**Files:**
- Create: `swingbot/core/backtesting/screen/ideas/shock_failed_bounce_short.py`
- Modify: `swingbot/core/backtesting/screen/ideas/__init__.py` (`IDEA_MODULES` only)
- Modify: `tests/backtesting/screen/test_ideas_registry.py` (the exact pins, same commit)
- Create: `tests/backtesting/screen/test_idea_shock_failed_bounce_short.py`
- Modify: `tests/backtest_scripts/test_screen_context_runner.py` (one family-overlap test appended; nothing else changes)

**Interfaces:**
- Consumes (V211-7): `sb.CONTEXT`, `sb.FAMILY`, `sb.SHOCK_PARAMS`, `sb.SOURCE`, `sb.ticker_state(df, context)`; test helpers `shock_context`, `episodes_covering`. (V211-8): the registry pins it extended, `_ctx_cache` with the new stems. (V211-5): `_overlap` passes the real context to the family partner.
- Produces (index ledger, final): module attrs as V211-8 (`CAP = 10`, `RACE = "fixed"`, `DIRECTION = "short"`, `CONTEXT = sb.CONTEXT`, `CONTEXT_KIND = "level"`, `FAMILY = sb.FAMILY`, `SOURCE = sb.SOURCE`) with `PARAMS = {**sb.SHOCK_PARAMS, "decline_atr": 1.0, "high_from": 10, "high_to": 2, "bounce_from": 5, "bounce_to": 1, "side": "short"}`; constants `DECLINE_ATR = 1.0`, `HIGH_FROM = 10`, `HIGH_TO = 2`, `BOUNCE_FROM = 5`, `BOUNCE_TO = 1`; `bounce_setup(df) -> pd.Series` (bool at `b`: conditions 1–3 with `b` as the bounce bar); `bounce_bar(df) -> pd.Series` (float position of the latest `b` in `t−5 .. t−1` with `bounce_setup[b]`, NaN when none — conditions 1–3 and 5); `failure(df, bounce: pd.Series) -> pd.Series` (bool, condition 4); `events(df, context)` (name `shock_failed_bounce_short`); `control_events(df)` (conditions 1–5, shock ignored; name `shock_failed_bounce_short_control`).

**The frozen trigger (spec § Idea 2, verbatim):** SHOCK on `t`, and (1) some `b` in `t−5 .. t−1` with `Close[b−1] ≤ max(High[b−10 .. b−2]) − 1.0 × ATR14[b−2]`; (2) `Close[b] > Close[b−1]`; (3) `High[b] < max(High[b−10 .. b−2])`; (4) `Close[t] < Low[b]`, and no bar in `b+1 .. t−1` closed below `Low[b]`; (5) if several bars qualify as `b`, the latest counts — "qualify" is conditions 1–3 (index ledger), so condition 4 is tested against the latest such `b` only. Short at the next open, the standard 1.5 × ATR14 race stop; the live follow-on's resting buy-stop above `High[b]` is recorded in the docstring and is **not** part of the race. `max(High[b−10 .. b−2])` is 9 bars: `indicators.rolling_max(High, 9).shift(2)`.

- [ ] **Step 1: Write the failing idea tests** — `tests/backtesting/screen/test_idea_shock_failed_bounce_short.py`:

```python
"""v211 Idea 2 (spec v209 § Track 2): a failed bounce after a >= 1 ATR decline
inside a SHOCK episode, short at the next open."""
import numpy as np

from swingbot.core.backtesting.screen import indicators
from swingbot.core.backtesting.screen.ideas import _shock_breakdown as sb
from swingbot.core.backtesting.screen.ideas import shock_failed_bounce_short as idea
from tests.backtesting.screen.helpers import (assert_prefix_stable, episodes_covering,
                                              frame, random_walk, shock_context)

FLAT = [100.0] * 33                       # High 101, Low 99, ATR14 = 2.0
#: decline 33..35, bounce bar b = 36 (Low 95), 37 holds above 95, 38 fails.
A = FLAT + [98.0, 96.0, 94.0, 96.0, 95.5, 94.0, 93.0] + [93.0] * 10
#: two bounce bars, 36 (Low 95) and 38 (Low 94.6): 39 is below 95 only, 40 below 94.6.
B = FLAT + [98.0, 96.0, 94.0, 96.0, 95.2, 95.6, 94.8, 94.0] + [94.0] * 8
#: b = 36, then five closes at 95.5; 42 closes below 95 with b six bars back.
C = FLAT + [98.0, 96.0, 94.0, 96.0] + [95.5] * 5 + [94.0] * 6
#: a decline of less than 1 ATR: Close[b-1] = 99.2 > 101 - 2.0.
D = FLAT + [99.5, 99.2, 99.6, 98.0] + [98.0] * 6


def _hits(series):
    return np.flatnonzero(series.to_numpy()).tolist()


def _reference(df) -> list:
    """The spec's five conditions read literally, one bar at a time."""
    atr = indicators.atr(df).to_numpy()
    high, low, close = (df[c].to_numpy() for c in ("High", "Low", "Close"))
    out = []
    for t in range(len(close)):
        latest = None
        for b in range(t - 1, t - 6, -1):                      # latest b first
            if b - 10 < 0 or not np.isfinite(atr[b - 2]):
                continue
            hh = high[b - 10:b - 1].max()                      # High[b-10 .. b-2]
            if close[b - 1] <= hh - 1.0 * atr[b - 2] and close[b] > close[b - 1] and high[b] < hh:
                latest = b
                break
        if latest is not None and close[t] < low[latest] and all(
                close[j] >= low[latest] for j in range(latest + 1, t)):
            out.append(t)
    return out


def test_the_constants_are_the_frozen_spec_values():
    assert (idea.CAP, idea.RACE, idea.DIRECTION) == (10, "fixed", "short")
    assert idea.CONTEXT == ("BREADTH_ATR1", "^VIX") and idea.CONTEXT_KIND == "level"
    assert idea.FAMILY == sb.FAMILY and idea.SOURCE == sb.SOURCE
    assert (idea.DECLINE_ATR, idea.HIGH_FROM, idea.HIGH_TO,
            idea.BOUNCE_FROM, idea.BOUNCE_TO) == (1.0, 10, 2, 5, 1)
    assert idea.PARAMS == {"breadth": "BREADTH_ATR1", "vix": "^VIX", "enter": 0.40,
                           "release": 0.10, "decline_atr": 1.0, "high_from": 10,
                           "high_to": 2, "bounce_from": 5, "bounce_to": 1, "side": "short"}
    assert idea.SUMMARY.strip() and not hasattr(idea, "levels")


def test_the_bounce_bar_is_seen_from_the_next_five_bars_only():
    b = idea.bounce_bar(frame(A)).to_numpy()
    assert np.flatnonzero(np.isfinite(b)).tolist() == [37, 38, 39, 40, 41]
    assert set(b[37:42]) == {36.0}


def test_fires_on_the_first_failure_below_the_bounce_low_inside_shock():
    df = frame(A)
    out = idea.events(df, shock_context(df.index, [(35, 45)]))
    assert _hits(out) == [38]
    assert out.dtype == bool and out.name == "shock_failed_bounce_short"
    assert out.index.equals(df.index)


def test_shock_must_be_on_at_t():
    df = frame(A)
    assert not idea.events(df, shock_context(df.index, [(30, 37)])).any()  # released on 37
    assert _hits(idea.control_events(df)) == [38]


def test_the_latest_bounce_bar_counts():
    df = frame(B)
    assert _hits(idea.events(df, shock_context(df.index, [(35, 45)]))) == [40]
    assert _hits(idea.control_events(df)) == [40]


def test_a_bounce_bar_six_bars_back_is_out_of_the_window():
    assert _hits(idea.control_events(frame(C))) == []


def test_a_decline_under_one_atr_is_no_setup():
    assert _hits(idea.control_events(frame(D))) == []


def test_a_bounce_high_at_the_recent_high_is_no_lower_high():
    highs = np.asarray(A) + 1.0
    highs[36] = 101.0                                          # == max(High[26..34])
    assert _hits(idea.control_events(frame(A, highs=highs))) == []


def test_the_control_equals_the_literal_reading_on_random_walks():
    for seed in (21, 31, 41):
        df = random_walk(800, seed=seed)
        expected = _reference(df)
        assert len(expected) >= 20                             # non-vacuous
        assert _hits(idea.control_events(df)) == expected
        assert idea.control_events(df).name == "shock_failed_bounce_short_control"


def test_events_on_t_read_no_later_stock_or_context_bar():
    df = random_walk(700, seed=21)
    ctx = shock_context(df.index, episodes_covering(_hits(idea.control_events(df)), len(df)))

    def fn(d):
        return idea.events(d, {k: v.loc[: d.index[-1]] for k, v in ctx.items()})

    assert fn(df).sum() >= 3                                   # non-vacuous
    for f in (fn, idea.control_events, idea.bounce_bar):
        assert_prefix_stable(f, df, [100, 250, 400, 699])
```

- [ ] **Step 2: Write the failing registry and runner tests**

`tests/backtesting/screen/test_ideas_registry.py` — extend V211-8's pins:
- the `IDEA_MODULES` tuple ends `"shock_support_break_short", "shock_failed_bounce_short")`.
- caps: add `"shock_failed_bounce_short": 10`.
- params: add `assert dict(IDEAS["shock_failed_bounce_short"].params) == {"breadth": "BREADTH_ATR1", "vix": "^VIX", "enter": 0.40, "release": 0.10, "decline_atr": 1.0, "high_from": 10, "high_to": 2, "bounce_from": 5, "bounce_to": 1, "side": "short"}`.
- direction `"short"`, entry `"next_open"`, race shape `"fixed"`, context `("BREADTH_ATR1", "^VIX")` for `"shock_failed_bounce_short"`; add it to `special`.
- in `test_the_shock_support_idea_pins_level_context_control_and_family`, the last line becomes `== {"shock_support_break_short", "shock_failed_bounce_short"}`.
- import `shock_failed_bounce_short` beside the others, and append:

```python
def test_the_shock_failed_bounce_idea_pins_level_context_control_and_family():
    idea = IDEAS["shock_failed_bounce_short"]
    assert idea.context_kind == "level" and idea.context == ("BREADTH_ATR1", "^VIX")
    assert idea.control is shock_failed_bounce_short.control_events
    assert idea.family == IDEAS["shock_support_break_short"].family
    assert idea.levels is None and idea.entry == "next_open"
```

`tests/backtest_scripts/test_screen_context_runner.py` — append:

```python
def test_the_shock_family_partners_overlap_through_the_real_context():
    """v211: both shock ideas are level-context partners; _overlap (V211-5)
    hands each the context, so neither raises and both report an overlap."""
    from swingbot.core.backtesting.screen.ideas import shock_failed_bounce_short as fb
    from tests.backtesting.screen.helpers import episodes_covering, shock_context
    df = random_walk(2600)
    hits = np.flatnonzero(fb.control_events(df).to_numpy())
    ctx = shock_context(df.index, episodes_covering(hits, len(df)))
    outs = {name: screen_idea.screen_ticker(IDEAS[name], "AAA", df, ALWAYS, context=ctx)
            for name in ("shock_failed_bounce_short", "shock_support_break_short")}
    assert outs["shock_failed_bounce_short"].events            # non-vacuous
    for out in outs.values():
        assert out.overlap is not None and out.control and out.restricted is None
```

- [ ] **Step 3: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_idea_shock_failed_bounce_short.py`
Expected: FAIL — `ImportError: cannot import name 'shock_failed_bounce_short'`.

- [ ] **Step 4: Implement `swingbot/core/backtesting/screen/ideas/shock_failed_bounce_short.py` and register it**

- Module docstring: *"Shock failed bounce, short (v211, frozen 2026-11-05 in spec v209 § Track 2). On a SHOCK_D date (_shock_breakdown.py): a bar b in t-5..t-1 bounced (Close[b] > Close[b-1]) after a decline of at least 1 ATR14[b-2] from max(High[b-10..b-2]), with a lower high (High[b] below that max); the latest such b counts; today closes below Low[b] for the first time since b. The race shorts the next open (fixed 1.5/3 ATR, 10-bar cap). The live follow-on's placeable stop is a resting buy-stop just above High[b]; it is not part of the frozen race. The control is the same trigger with the shock state ignored (printed, never gating). One family with shock_support_break_short."*
- Constants as the Interfaces block; `PARAMS` built from `sb.SHOCK_PARAMS` and them; `SUMMARY = ("SHOCK_D on t; bounce bar b in t-5..t-1 (close[b-1] <= max(High[b-10..b-2]) - 1.0 ATR14[b-2], close[b] > close[b-1], High[b] < that max; latest b) and close[t] < Low[b], the first close below it since b (short, next open)")`.
- `_recent_high(df) -> pd.Series` — `indicators.rolling_max(df["High"], HIGH_FROM - HIGH_TO + 1).shift(HIGH_TO)`, the max over `b−10 .. b−2` seen from `b`.
- `bounce_setup(df)` — with `hh = _recent_high(df)`, `atr = indicators.atr(df).shift(2)` (ATR14[b−2]) and `prev = df["Close"].shift(1)`: `(prev <= hh - DECLINE_ATR * atr) & (df["Close"] > prev) & (df["High"] < hh)`, NaN → False, bool.
- `bounce_bar(df)` — positions of setup bars (`np.where(setup, np.arange(n), np.nan)`), `.shift(BOUNCE_TO)` then `.ffill()` (the latest setup at or before `t−1`), kept only where `t − b <= BOUNCE_FROM` (else NaN); float Series on `df.index`.
- `failure(df, bounce)` — condition 4 vectorised over the at most four bars between `b` and `t` (checked equal to the literal reading by the random-walk test):

```python
    close, low = df["Close"].to_numpy(float), df["Low"].to_numpy(float)
    b, pos = bounce.to_numpy(float), np.arange(len(df))
    ok = np.isfinite(b)
    bi = np.where(ok, b, 0).astype(int)
    low_b = np.where(ok, low[bi], np.nan)
    with np.errstate(invalid="ignore"):
        hit = ok & (close < low_b)
        for lag in range(1, BOUNCE_FROM):             # bars t-1 .. t-4, only those after b
            prev = np.r_[np.full(lag, np.nan), close[:-lag]]
            hit &= ~((pos - lag > bi) & (prev < low_b))
    return pd.Series(hit, index=df.index)
```

- `control_events(df)` — `failure(df, bounce_bar(df))` renamed `shock_failed_bounce_short_control`.
- `events(df, context)` — `(failure(df, bounce_bar(df)) & sb.ticker_state(df, context)["shock"])` renamed `shock_failed_bounce_short`. "First failure" is a price clause: a first failure on a NORMAL date is not repeated on a later SHOCK date.

`swingbot/core/backtesting/screen/ideas/__init__.py`: append `"shock_failed_bounce_short"` to `IDEA_MODULES` (last, after `"shock_support_break_short"`).

- [ ] **Step 5: Run the tests to verify they pass, then the byte-identical pins**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_idea_shock_failed_bounce_short.py`
Expected: PASS (10 tests).

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_ideas_registry.py`
Expected: PASS.

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_context_runner.py`
Expected: PASS, `PARITY_DIGESTS` untouched.

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_level_context.py`
Expected: PASS (V211-8's `<=` kind pin already admits this idea; the hypothesis golden untouched).

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py`
Expected: PASS, untouched.

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (`failure` is one loop and two masks, well under 15).

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/screen/ideas/shock_failed_bounce_short.py swingbot/core/backtesting/screen/ideas/__init__.py tests/backtesting/screen/test_idea_shock_failed_bounce_short.py tests/backtesting/screen/test_ideas_registry.py tests/backtest_scripts/test_screen_context_runner.py
git commit -m "feat(v211): idea shock_failed_bounce_short -- first failure below a lower-high bounce in SHOCK, short (V211-9)"
```

