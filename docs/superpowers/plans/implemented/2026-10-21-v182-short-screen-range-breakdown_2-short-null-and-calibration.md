# v182 — Part 2: short trail race, short null and drift, short calibration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Spec:** [2026-10-21-v182-short-screen-range-breakdown-design.md](../specs/2026-10-21-v182-short-screen-range-breakdown-design.md) — Part A (the short race, calibration items 1 and 2).
**Index:** [2026-10-21-v182-short-screen-range-breakdown_0-index.md](2026-10-21-v182-short-screen-range-breakdown_0-index.md) — Goal, Global Constraints, Review Focus, Parallelisation and the task ledger live there and bind every task below.
**Worktree:** `.claude/worktrees/2026-10-21-v182-short-screen-range-breakdown` (created in V182-1). Every command below runs from that worktree's root.

**Tasks:** V182-5..V182-8. All four are sequential (index § Parallelisation: V182-4 → V182-5 → V182-6 → V182-7 → V182-8).

**Long byte-identity, every task:** after each task's own narrow run, also run both golden regression files from V182-1 and expect them green:

```bash
python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_calibration_long_golden.py
```

Never edit the golden files (`tests/backtesting/screen/golden/long_v182.json`, `tests/backtest_scripts/golden/trail_calibration_v182.txt`) to make a test pass. A golden failure means a long expression changed: revert that change and find the short-only branch it should have been.

**Contracts from Part 1 this part consumes** (index ledger, V182-2..V182-4):

- `swingbot.core.edge.frictions.borrow_r(entry, risk, days)` and `BORROW_RATE_ANNUAL = 0.005`.
- `Idea(direction="short", entry="next_open" | "level", levels=None, control=None, family=())`.
- `swingbot.core.backtesting.screen.sides`: `oriented(o, h, l, c, direction)` (long: the same objects; short: `(-o, -l, -h, -c)`), `holding_days(index, entry_pos, exit_pos) -> np.ndarray` (calendar days), `net_r(entry, price, risk, *, direction, days, slippage_bps=None, entry_bps=None, commission=None) -> np.ndarray` (real, un-negated prices; long is today's expression with its operand order kept; short swaps the sides and subtracts `borrow_r`).
- `race.race(df, event_pos, cap, *, atr=None, slippage_bps=None, commission=None, direction="long")` and `race.run_book(..., direction="long")`, which hands `direction=` to the race function `race_for(shape)` returns.

---

# Phase A2 — the short trail race, the short null and drift, the short A/A

### Task V182-5: Short trail race

**Model:** opus — float-exact mirror of a vectorised race with a byte-identity constraint on the long path; a wrong sign or operand order is silent.

**Files:**
- Modify: `swingbot/core/backtesting/screen/trail.py` (module docstring, `race_trail` at :64-84)
- Create: `tests/backtesting/screen/test_trail_short.py`

**Interfaces:**
- Consumes: `sides.oriented`, `sides.holding_days`, `sides.net_r` (V182-4); `frictions.borrow_r` (V182-2); `race.run_book(..., shape="trail", direction=...)` (V182-4) hands `direction=` to `trail.race_trail`.
- Produces: `trail.race_trail(df, event_pos, cap, *, atr=None, slippage_bps=None, commission=None, direction="long") -> race.RaceResult`. `RaceResult.entry` holds the real (un-negated) fill price for both directions; `gross_r` is `(entry − exit) / risk` for a short.

The short trail is the long trail run on `sides.oriented` prices (`-O, -L, -H, -C`). The chandelier then sits 3 × ATR14[t] **above the lowest low** of bars t+1..j−1 and is never raised; a gap is an open at or above the stop. `trail_stops` and `_first_exit_trail` do not change at all.

- [ ] **Step 1: Write the failing tests** in `tests/backtesting/screen/test_trail_short.py`

```python
"""v182 short trail race: the exact mirror of the v163 long trail (spec § Part A)."""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import indicators
from swingbot.core.backtesting.screen import race as race_mod
from swingbot.core.backtesting.screen import sides, trail
from swingbot.core.edge import frictions
from tests.backtesting.screen.helpers import frame, random_walk

QUIET = (100.0, 101.0, 99.0, 100.0)     # bar 0 = signal bar; entry = bar 1's open = 100
DN1 = (100.0, 100.5, 96.0, 97.0)        # the stop on the next bar: 96 + 6 = 102
DN2 = (97.0, 97.5, 92.0, 93.0)          # next: 92 + 6 = 98
DN3 = (93.0, 93.5, 90.0, 91.0)          # next: 90 + 6 = 96
MIRROR_C = 256.0                        # dyadic prices and a power of two: reflection is exact


def _frame(bars):
    rows = [QUIET] + list(bars)
    o, h, l, c = (np.array(col, dtype=float) for col in zip(*rows))
    return frame(c, opens=o, highs=h, lows=l)


def _atr(df, value=2.0):
    return pd.Series(value, index=df.index)   # 1R = 3.0: initial short stop 103


def _reflect(df, c=MIRROR_C):
    """P' = c - P; High' = c - Low, Low' = c - High (spec § Part A, item 1)."""
    return pd.DataFrame({"Open": c - df["Open"], "High": c - df["Low"],
                         "Low": c - df["High"], "Close": c - df["Close"],
                         "Volume": df["Volume"]}, index=df.index)


def _race(df, pos, cap, atr, direction, **costs):
    costs.setdefault("slippage_bps", 0.0)
    costs.setdefault("commission", 0.0)
    return trail.race_trail(df, pos, cap, atr=atr, direction=direction, **costs)


def _short(bars, cap, **costs):
    df = _frame(bars)
    return _race(df, [0], cap, _atr(df), "short", **costs)


CASES = {
    "trail": ([DN1, DN2, DN3, (92.0, 96.5, 91.5, 95.0)], 4),
    "gap_trail": ([DN1, DN2, (99.0, 99.5, 97.0, 98.0)], 3),
    "gap_stop": ([QUIET, (104.0, 105.0, 103.5, 104.5)], 2),
    "stop": ([QUIET, (100.0, 103.5, 99.5, 101.0)], 2),
    "timeout": ([QUIET, QUIET, QUIET], 3),
}


def test_the_short_stop_sits_three_atr_over_the_lowest_prior_low_never_raised():
    lows = np.array([[96.0, 92.0, 95.0, 90.0]])
    entry, risk = np.array([100.0]), np.array([3.0])
    real = -trail.trail_stops(-lows, -entry, risk)[0]     # the short race's own call, un-negated
    assert real.tolist() == [103.0, 102.0, 98.0, 98.0]
    assert (np.diff(real) <= 0).all()


def test_a_short_rides_the_trail_down_and_exits_on_the_trail():
    out = _short(*CASES["trail"])
    assert out.outcome.tolist() == ["trail"]
    assert out.exit_pos.tolist() == [4]
    assert out.entry.tolist() == [100.0]                    # the real fill, not -100
    assert out.gross_r[0] == pytest.approx(4.0 / 3.0)       # (100 - 96) / 3


def test_a_short_gap_up_through_a_lowered_stop_is_gap_trail_at_the_open():
    out = _short(*CASES["gap_trail"])
    assert out.outcome.tolist() == ["gap_trail"]
    assert out.gross_r[0] == pytest.approx(1.0 / 3.0)       # (100 - 99) / 3, a gain


def test_a_short_gap_up_through_the_initial_stop_is_a_gap_loss_beyond_one_r():
    out = _short(*CASES["gap_stop"])
    assert out.outcome.tolist() == ["gap_stop"]
    assert out.gross_r[0] == pytest.approx(-4.0 / 3.0)
    assert out.gross_r[0] < -1.0


def test_a_short_high_touching_the_initial_stop_exits_at_minus_one_r():
    out = _short(*CASES["stop"])
    assert out.outcome.tolist() == ["stop"]
    assert out.gross_r[0] == pytest.approx(-1.0)


def test_a_short_with_no_exit_times_out_at_the_last_close():
    out = _short(*CASES["timeout"])
    assert out.outcome.tolist() == ["timeout"]
    assert out.exit_pos.tolist() == [3]
    assert out.gross_r[0] == 0.0


@pytest.mark.parametrize("name", sorted(CASES))
def test_short_on_p_is_long_on_the_reflected_frame_exactly(name):
    bars, cap = CASES[name]
    df = _frame(bars)
    short = _race(df, [0], cap, _atr(df), "short")
    long_ = _race(_reflect(df), [0], cap, _atr(df), "long")
    assert short.outcome.tolist() == long_.outcome.tolist() == [name]
    assert short.exit_pos.tolist() == long_.exit_pos.tolist()
    assert short.gross_r.tolist() == long_.gross_r.tolist()      # exact: dyadic prices


def _near_tie(df, pos, cap, atr, tol=1e-9):
    """Rows where a reflected open or low lies within tol of the trail stop:
    their outcome code may legitimately differ by rounding."""
    o, h, l = (df[col].to_numpy(dtype=float) for col in ("Open", "High", "Low"))
    bars = pos[:, None] + 1 + np.arange(cap)[None, :]
    entry = o[pos + 1]
    risk = race_mod.STOP_ATR * atr.to_numpy(dtype=float)[pos]
    stops = trail.trail_stops(h[bars], entry, risk)
    near = (np.abs(o[bars] - stops) < tol) | (np.abs(l[bars] - stops) < tol)
    return near.any(axis=1)


@pytest.mark.parametrize("seed", [3, 5, 8])
def test_random_frames_mirror_within_tolerance(seed):
    df = random_walk(400, seed=seed)
    atr = indicators.atr(df)
    pos = np.arange(20, 330, 7)
    short = _race(df, pos, 60, atr, "short")
    mirrored = _reflect(df, 512.0)
    long_ = _race(mirrored, pos, 60, atr, "long")
    np.testing.assert_allclose(short.gross_r, long_.gross_r, rtol=0.0, atol=1e-9)
    clear = ~_near_tie(mirrored, pos, 60, atr)
    assert clear.sum() > 30                                    # non-vacuous
    assert (short.outcome[clear] == long_.outcome[clear]).all()
    assert (short.exit_pos[clear] == long_.exit_pos[clear]).all()


def test_short_net_r_charges_sell_entry_buy_exit_and_borrow():
    days = 3                                                   # Tue 2010-01-05 -> Fri 2010-01-08
    borrow = 100.0 * frictions.BORROW_RATE_ANNUAL / 365.0 * days / 3.0
    out = _short(*CASES["trail"])
    assert out.r[0] == pytest.approx(4.0 / 3.0 - borrow)
    slipped = _short(*CASES["trail"], slippage_bps=10.0, commission=0.02)
    sell_in, buy_out = 100.0 * (1 - 0.001), 96.0 * (1 + 0.001)
    assert slipped.r[0] == pytest.approx((sell_in - buy_out) / 3.0 - 0.02 - borrow)


def _count_borrow(monkeypatch):
    """Counts trades charged: patched where sides may look the name up."""
    seen = []
    real = frictions.borrow_r

    def spy(entry, risk, days):
        seen.append(int(np.size(days)))
        return real(entry, risk, days)

    monkeypatch.setattr(frictions, "borrow_r", spy)
    monkeypatch.setattr(sides, "borrow_r", spy, raising=False)
    return seen


def test_borrow_is_charged_once_per_short_trade_and_never_for_a_long(monkeypatch):
    seen = _count_borrow(monkeypatch)
    df = random_walk(400, seed=5)
    pos = np.arange(20, 330, 7)
    _race(df, pos, 60, indicators.atr(df), "long")
    assert seen == []
    _race(df, pos, 60, indicators.atr(df), "short")
    assert seen == [len(pos)]


def test_the_default_direction_is_long_and_its_arrays_are_unchanged():
    df = random_walk(400, seed=8)
    atr = indicators.atr(df)
    pos = np.arange(20, 330, 7)
    default = trail.race_trail(df, pos, 60, atr=atr)
    explicit = trail.race_trail(df, pos, 60, atr=atr, direction="long")
    for name in ("event_pos", "exit_pos", "entry", "risk", "gross_r", "r", "outcome"):
        assert np.array_equal(getattr(default, name), getattr(explicit, name)), name


def test_run_book_races_a_short_trail_book():
    df = random_walk(400, seed=3)
    atr = indicators.atr(df)
    events = np.zeros(len(df), dtype=bool)
    events[[20, 100, 180]] = True                     # further apart than the cap: no overlap
    ones = np.ones(len(df), dtype=bool)
    booked, counts = race_mod.run_book(df, events, 60, member=ones, warm=ones, atr=atr,
                                       shape="trail", direction="short",
                                       slippage_bps=0.0, commission=0.0)
    direct = _race(df, np.array([20, 100, 180]), 60, atr, "short")
    assert counts["skipped_overlap"] == 0
    assert booked.gross_r.tolist() == direct.gross_r.tolist()
    assert booked.r.tolist() == direct.r.tolist()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_trail_short.py`
Expected: FAIL — `TypeError: race_trail() got an unexpected keyword argument 'direction'`. Only `test_the_short_stop_sits_three_atr_over_the_lowest_prior_low_never_raised` passes already, because it calls existing code alone.

- [ ] **Step 3: Implement the direction in `swingbot/core/backtesting/screen/trail.py`**

- Import `sides` beside `indicators` and `race_mod`. Drop the `apply_frictions, commission_r` import only if nothing else in the module still uses it.
- `race_trail(df, event_pos, cap, *, atr=None, slippage_bps=None, commission=None, direction="long")`:
  - read the four columns exactly as today, then pass them through `sides.oriented(o, h, l, c, direction)`;
  - everything from `bars = ...` through `_first_exit_trail(...)` is unchanged and runs on the oriented arrays;
  - `exit_pos = event_pos + 1 + offset`; `gross = (price - entry) / risk` (oriented space; for a long this is today's expression on today's objects);
  - un-orient the two prices for costs and for `RaceResult.entry` exactly as V182-4 does in `race.race`: `if direction == "short": entry, price = -entry, -price` (negation is exact; a long runs no negation, never `1.0 * x`);
  - `net = sides.net_r(entry, price, risk, direction=direction, days=sides.holding_days(df.index, event_pos + 1, exit_pos), slippage_bps=slippage_bps, commission=commission)`;
  - return `race_mod.RaceResult(event_pos, exit_pos, entry, risk, gross, net, np.asarray(race_mod.OUTCOMES)[code])`.
- `race.run_book` (V182-4) hands `direction=` to the race function only when it is not `"long"`; leave that guard as it is.
- Module docstring: replace "Long only." with one paragraph on the short mirror. It covers entry at open t+1 and the initial stop at entry + 1R. The stop on bar j is `min(entry + 1R, min(Low[t+1 .. j-1]) + 3 x ATR14[t])`, never raised. An open at or above the stop exits at the open. Costs are entry "sell", exit "buy", plus `frictions.borrow_r` on calendar days held (v182).
- `race_trail` stays well under complexity 15 (one conditional added).

- [ ] **Step 4: Run the tests to verify they pass, then the long goldens and the gate**

```bash
python scripts/dev/testrun.py file tests/backtesting/screen/test_trail_short.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_trail.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_calibration_long_golden.py
python scripts/dev/complexity_gate.py
```

Expected: every file `0 failed`; the complexity gate exits 0. A golden failure means the long expression in `race_trail` moved or was reordered: restore it.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/screen/trail.py tests/backtesting/screen/test_trail_short.py
git commit -m "feat(v182): short trail race -- mirror of the chandelier, borrow on calendar days

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V182-6: Null raced in the idea's direction, drift flipped once, short threading in `screen_idea`

**Model:** opus — threads direction through the one call site every book, null and drift shares; the sign flip must happen exactly once and long output must stay byte-identical.

**Files:**
- Modify: `swingbot/core/backtesting/screen/null.py` (`matched_null` at :75-97)
- Modify: `swingbot/core/backtesting/screen/forward.py` (module docstring, `forward_atr` at :17-25)
- Modify: `scripts/backtest/screen_idea.py` (import at :46, `_books` :128-145, `screen_ticker` :203-226, `_render_trade` :515-529, `hypothesis` :698-710)
- Modify: `tests/backtesting/screen/test_null.py`
- Modify: `tests/backtesting/screen/test_forward.py`
- Modify: `tests/backtest_scripts/test_screen_idea.py`

**Interfaces:**
- Consumes: `race.run_book(..., direction=)` and `race.race(..., direction=)` (V182-4); `trail.race_trail(..., direction=)` (V182-5); `frictions.BORROW_RATE_ANNUAL` (V182-2); `Idea.direction`, `Idea.entry` (V182-3).
- Produces:
  - `null.matched_null(df, event_pos, eligible, k, seed, *, cap, atr, trend, slippage_bps=None, commission=None, shape="fixed", direction="long") -> NullDraw`. The draw (rng, pools, groups) does not depend on `direction`; only the race does.
  - `forward.forward_atr(df, atr, h, direction="long") -> np.ndarray`: a short returns the negated long array (the only sign flip in the screen).
  - `screen_idea._short_trade_line(idea, costs: str) -> str` and `screen_idea._short_hypothesis(idea) -> str`, reached from `_render_trade` / `hypothesis` only when `idea.direction == "short"`.
  - `screen_idea._books` passes `direction=idea.direction` to `race.run_book` and `null.matched_null`; `screen_ticker` passes it to `forward.forward_atr`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/backtesting/screen/test_null.py` (it already has `_walk_null`, `_atr`, `_all`, `trail`):

```python
def _walk_null_dir(direction=None, shape="fixed"):
    df = random_walk(400, start="2019-01-01")
    eligible = null.eligible_mask(np.zeros(len(df), dtype=bool), _all(df), _all(df), cap=60)
    kw = {} if direction is None else {"direction": direction}
    draw = null.matched_null(df, [5, 30], eligible, 20, 3, cap=60, atr=_atr(df),
                             trend=_all(df), slippage_bps=0.0, commission=0.0,
                             shape=shape, **kw)
    return df, draw


@pytest.mark.parametrize("shape", ["fixed", "trail"])
def test_a_short_null_races_the_same_draw_short(shape):
    _, long_ = _walk_null_dir("long", shape)
    df, short = _walk_null_dir("short", shape)
    assert [g.tolist() for g in short.groups] == [g.tolist() for g in long_.groups]
    race_fn = race_mod.race_for(shape)
    for k, group in enumerate(short.groups):
        expected = race_fn(df, group, 60, atr=_atr(df), slippage_bps=0.0,
                           commission=0.0, direction="short")
        assert short.null_mean_r[k] == pytest.approx(expected.r.mean())
    assert short.null_race.r.tolist() != long_.null_race.r.tolist()


def test_matched_null_without_a_direction_is_the_long_null():
    _, default = _walk_null_dir(None)
    _, long_ = _walk_null_dir("long")
    assert default.null_mean_r.tolist() == long_.null_mean_r.tolist()
    assert default.null_race.r.tolist() == long_.null_race.r.tolist()
    assert default.null_race.outcome.tolist() == long_.null_race.outcome.tolist()
```

Append to `tests/backtesting/screen/test_forward.py`:

```python
def _dyadic(n=780, seed=4):
    """Closes on a 1/8 grid: reflection about 256 is exact in floats."""
    rng = np.random.default_rng(seed)
    return frame(rng.integers(400, 1200, n) / 8.0)


def test_short_forward_is_the_negated_long_forward():
    df = _dyadic()
    atr = pd.Series(2.0, index=df.index)
    for h in forward.HORIZONS:
        long_ = forward.forward_atr(df, atr, h)
        short = forward.forward_atr(df, atr, h, direction="short")
        assert np.array_equal(short, -long_, equal_nan=True)
        assert np.array_equal(forward.forward_atr(df, atr, h, direction="long"), long_,
                              equal_nan=True)


def test_a_mirrored_frame_raced_short_gives_the_original_long_drift_and_rank():
    """Spec § Part A: the flip is applied once, so short on P == long on c - P."""
    df = _dyadic()
    mirrored = frame(256.0 - df["Close"].to_numpy(), index=df.index)
    atr = pd.Series(2.0, index=df.index)
    rng = np.random.default_rng(9)
    indicator = (rng.random(len(df)) < 0.1).astype(int)
    event_pos = np.flatnonzero(indicator)[:20]
    groups = tuple(np.sort(rng.choice(len(df) - 60, 5, replace=False)) for _ in event_pos)
    years = np.asarray(df.index.year)
    for h in forward.HORIZONS:
        short = forward.forward_atr(df, atr, h, direction="short")
        long_ = forward.forward_atr(mirrored, atr, h)
        assert np.array_equal(short, long_, equal_nan=True)
        assert (forward.excess_drift(short, event_pos, groups)
                == forward.excess_drift(long_, event_pos, groups))
        assert (forward.yearly_rank_corr(years, indicator, short)
                == forward.yearly_rank_corr(years, indicator, long_))


def test_diagnostics_never_flips_a_sign_again():
    from pathlib import Path
    source = (Path(forward.__file__).with_name("diagnostics.py")).read_text(encoding="utf-8")
    assert "direction" not in source
```

Append to `tests/backtest_scripts/test_screen_idea.py` (after the existing `RUN_INFO` and `_trail_probe` definitions):

```python
from swingbot.core.backtesting.screen import sides as sides_mod  # noqa: E402
from swingbot.core.edge import frictions as frictions_mod  # noqa: E402


def _short_probe(cap=20, shape="fixed"):
    """turn_of_month's trigger raced short; never registered."""
    return Idea(name="short_probe", events=IDEAS["turn_of_month"].events,
                time_cap_bars=cap, direction="short", race_shape=shape,
                summary="probe", source="test")


def test_screen_ticker_passes_the_idea_direction_to_book_and_null(monkeypatch):
    seen = {"book": [], "null": []}
    real_book, real_null = race_mod.run_book, null.matched_null

    def book_spy(*args, **kwargs):
        seen["book"].append(kwargs.get("direction"))
        return real_book(*args, **kwargs)

    def null_spy(*args, **kwargs):
        seen["null"].append(kwargs.get("direction"))
        return real_null(*args, **kwargs)

    monkeypatch.setattr(race_mod, "run_book", book_spy)
    monkeypatch.setattr(null, "matched_null", null_spy)
    df = random_walk(2600)
    screen_idea.screen_ticker(IDEAS["turn_of_month"], "AAA", df, ALWAYS)
    assert seen == {"book": ["long"], "null": ["long"]}
    seen["book"].clear()
    seen["null"].clear()
    screen_idea.screen_ticker(_short_probe(), "AAA", df, ALWAYS)
    assert seen == {"book": ["short"], "null": ["short"]}


def test_a_short_screen_reads_the_flipped_forward_return_once(monkeypatch):
    draws = []
    real = null.matched_null

    def spy(*args, **kwargs):
        out = real(*args, **kwargs)
        draws.append(out)
        return out

    monkeypatch.setattr(null, "matched_null", spy)
    df = random_walk(2600)
    out = screen_idea.screen_ticker(_short_probe(), "AAA", df, ALWAYS)
    atr = screen_idea.indicators.atr(df)
    assert draws and draws[0].event_pos.size
    for h in forward.HORIZONS:
        fwd = -forward.forward_atr(df, atr, h)
        assert out.excess[h] == forward.excess_drift(fwd, draws[0].event_pos, draws[0].groups)
    long_rank = screen_idea.screen_ticker(IDEAS["turn_of_month"], "AAA", df, ALWAYS).rank
    for h in forward.HORIZONS:
        assert np.array_equal(out.rank[f"fwd_{h}"].to_numpy(),
                              -long_rank[f"fwd_{h}"].to_numpy(), equal_nan=True)


def _count_borrow(monkeypatch):
    seen = []
    real = frictions_mod.borrow_r

    def spy(entry, risk, days):
        seen.append(int(np.size(days)))
        return real(entry, risk, days)

    monkeypatch.setattr(frictions_mod, "borrow_r", spy)
    monkeypatch.setattr(sides_mod, "borrow_r", spy, raising=False)
    return seen


def test_borrow_is_charged_once_on_the_book_and_once_on_the_null_never_on_a_long(monkeypatch):
    seen = _count_borrow(monkeypatch)
    df = random_walk(2600)
    screen_idea.screen_ticker(IDEAS["turn_of_month"], "AAA", df, ALWAYS)
    assert seen == []
    out = screen_idea.screen_ticker(_short_probe(), "AAA", df, ALWAYS)
    raced = (len(out.events) + out.counters["skipped_overlap"]
             + out.counters["dropped_no_match"])
    assert seen == [raced, sum(out.null_outcomes.values())]


def test_short_fixed_trade_line_names_the_mirror_and_the_borrow():
    assert screen_idea._render_trade(_short_probe(), RUN_INFO) == (
        "**Trade:** short; entry next open (sell); stop 1.5 x ATR14 above; target 3.0 x "
        "ATR14 below; a gap through either level fills at the open; stop first on a bar "
        "touching both; borrow 0.5% a year on calendar days held; "
        "costs 5.0 bps a side + 0.0200R commission.")


def test_short_trail_trade_line_names_the_lowest_low_and_the_borrow():
    line = screen_idea._render_trade(_short_probe(60, "trail"), RUN_INFO)
    assert line.startswith("**Trade:** short; entry next open (sell); initial stop 1.5 x "
                           "ATR14[t] above (1R); no target;")
    assert "the lower of the initial stop and the lowest low of bars t+1..j-1 plus 3.0 x ATR14[t]" in line
    assert "never raised" in line and "60 bars" in line
    assert line.endswith("borrow 0.5% a year on calendar days held; "
                         "costs 5.0 bps a side + 0.0200R commission.")


def test_short_results_header_says_short_only():
    v = verdict.Verdict("SCREEN-FAIL", 412, 0.03, -0.01, 0.07, 0.2, 6, {}, {})
    head = "\n".join(screen_idea._render_head(_short_probe(), v, RUN_INFO))
    assert "time cap 20 bars; short only." in head


def test_short_hypothesis_names_the_direction_and_validates():
    idea = _short_probe()
    text = screen_idea.hypothesis(idea)
    assert text == ("short_probe: probe; SHORT, entry next open, fixed 1.5/3.0 ATR race vs "
                    "K=20 matched null raced short, cap 20, borrow 0.5% a year, PIT S&P 500 "
                    "2010-2019, after costs (v182 short screen)")
    trail_text = screen_idea.hypothesis(_short_probe(60, "trail"))
    assert "SHORT, entry next open, chandelier 3.0 ATR trail race, initial stop 1.5 ATR" in trail_text
    v = verdict.Verdict("SCREEN-FAIL", 412, 0.03, -0.01, 0.07, 0.2, 6, {}, {})
    row = screen_idea.ledger_row(idea, v, "docs/superpowers/results/x.md", "2026-10-21")
    stats.validate_ledger_row(row)
    assert row["hypothesis"] == text
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python scripts/dev/testrun.py file tests/backtesting/screen/test_null.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_forward.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_idea.py
```

Expected: FAIL — `matched_null() got an unexpected keyword argument 'direction'`, `forward_atr() got an unexpected keyword argument 'direction'`, the spy sees `[None]` instead of `["long"]`, and the short trade line / hypothesis are still the long text. `test_diagnostics_never_flips_a_sign_again` and `test_matched_null_without_a_direction_is_the_long_null` (default call) may pass already; that is expected.

- [ ] **Step 3: Implement**

`swingbot/core/backtesting/screen/null.py`:
- `matched_null(..., shape: str = "fixed", direction: str = "long") -> NullDraw`. The rng, pools and draw loop stay as they are. The one `race_fn(...)` call gains `direction=direction`.
- Docstring: one sentence saying the null is raced in the idea's direction (v182) and the draw does not depend on it.

`swingbot/core/backtesting/screen/forward.py`:
- `forward_atr(df, atr, h, direction: str = "long") -> np.ndarray`. Compute `out` exactly as today, then return `out` for a long and `-out` for a short.
- Module docstring: the short flip happens here, once; `diagnostics.py` never flips again, so a positive drift means good for the trade in both directions.

`scripts/backtest/screen_idea.py`:
- Import: `from swingbot.core.edge.frictions import BORROW_RATE_ANNUAL, commission_r`.
- `_books`: pass `direction=idea.direction` to both `race.run_book(...)` and `null.matched_null(...)`. Everything else stays as it is, and the `**costs` splat is unchanged.
- `screen_ticker`: `fwd = {h: forward.forward_atr(df, atr, h, direction=idea.direction) for h in forward.HORIZONS}`.
- `_render_trade(idea, run)`: build `costs` as today. Its first branch is `if idea.direction == "short": return _short_trade_line(idea, costs)`. The trail and fixed long returns stay byte for byte.
- `_short_trade_line(idea, costs: str) -> str`: the exact copy is pinned by the two tests above. Build it from `race.STOP_ATR`, `race.STOP_ATR * race.REWARD_RISK`, `trail.TRAIL_ATR`, `idea.time_cap_bars` and `f"borrow {BORROW_RATE_ANNUAL:.1%} a year on calendar days held; "`, keyed on `idea.race_shape`. The trail text is: `"**Trade:** short; entry next open (sell); initial stop {STOP_ATR} x ATR14[t] above (1R); no target; chandelier trail: the stop on bar j is the lower of the initial stop and the lowest low of bars t+1..j-1 plus {TRAIL_ATR} x ATR14[t], never raised, ATR frozen at the signal bar; a gap through the stop fills at the open; no exit after {cap} bars -> out at that close; R in the initial 1R; "` + borrow + costs. The level-entry line is V182-11's.
- `hypothesis(idea)`: after the `if idea.context:` branch, add `if idea.direction == "short": return _short_hypothesis(idea)`. The trail and fixed long returns stay byte for byte.
- `_short_hypothesis(idea) -> str`: `f"{idea.name}: {idea.summary}; SHORT, {entry}, {shape} vs K={null.K} matched null raced short, cap {idea.time_cap_bars}, borrow {BORROW_RATE_ANNUAL:.1%} a year, PIT S&P 500 2010-2019, after costs (v182 short screen)"`. It uses two module-level tables:
  - `_SHORT_ENTRY_TEXT = {"next_open": "entry next open", "level": "sell-stop at the level, filled on the event bar"}`;
  - `_SHORT_RACE_TEXT`, keyed on the shape: fixed → `f"fixed {race.STOP_ATR}/{race.STOP_ATR * race.REWARD_RISK} ATR race"`, trail → `f"chandelier {trail.TRAIL_ATR} ATR trail race, initial stop {race.STOP_ATR} ATR"`.
  
  Build the race text inside the function or as lambdas, so the constants are read at call time.
- Every function touched stays < 15 complexity; `_render_trade` and `hypothesis` each gain one branch.

- [ ] **Step 4: Run the tests to verify they pass, then the long goldens and the gate**

```bash
python scripts/dev/testrun.py file tests/backtesting/screen/test_null.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_forward.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_idea.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_calibration_long_golden.py
python scripts/dev/complexity_gate.py
```

Expected: `0 failed` everywhere. The existing pins `test_fixed_trade_line_is_unchanged`, `test_fixed_hypothesis_is_unchanged`, `test_a_fixed_idea_renders_its_results_doc_byte_identical_to_v140` and `test_screen_ticker_passes_the_idea_shape_to_book_and_null` still pass untouched.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/screen/null.py swingbot/core/backtesting/screen/forward.py scripts/backtest/screen_idea.py tests/backtesting/screen/test_null.py tests/backtesting/screen/test_forward.py tests/backtest_scripts/test_screen_idea.py
git commit -m "feat(v182): race the null in the idea's direction, flip drift once, short trade line and hypothesis

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V182-7: Calibration script: `--direction`, cap-20 short idea, Wilson interval, doc name per mode

**Model:** sonnet — mechanical extension of one script behind defaults that keep the long output byte-identical; the golden test from V182-1 is the safety net.

**Files:**
- Modify: `scripts/backtest/screen_trail_calibration.py` (docstring, constants :38-53, `_idea` :82-85, `replicate` :88-100, `calibrate` :108-123, `render` :176-179, `build_parser` :189-200, `main` :207-230)
- Modify: `tests/backtest_scripts/test_screen_trail_calibration.py`

**Interfaces:**
- Consumes: `Idea(direction="short", entry=..., levels=...)` (V182-3); the short fixed race through the real `screen_idea.screen_ticker` (V182-4, V182-6); `frictions.BORROW_RATE_ANNUAL` (V182-2).
- Produces (V182-12 extends these for level mode; the names and signatures are final):
  - `SHORT_CAP = 20`
  - `CAL_IDEA_NAMES = {("long", "next_open"): "aa_trail_calibration", ("short", "next_open"): "aa_short_calibration", ("short", "level"): "aa_short_level_calibration"}`
  - `ENABLED_ENTRIES = ("next_open",)`: V182-12 appends `"level"`
  - `_idea(events, *, direction="long", entry="next_open", levels=None) -> Idea`
  - `wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]`
  - `doc_name(direction: str, entry: str, day: str) -> str`
  - `replicate(seed, *, tickers=TICKERS, bars=BARS, rate=EVENT_RATE, n_resamples=..., direction="long", entry="next_open") -> verdict.Verdict`
  - `calibrate(replicates=REPLICATES, seed=SEED, *, tickers=TICKERS, n_resamples=..., out=print, direction="long", entry="next_open") -> dict`
  - parser `--direction {long,short}` (default `long`) and `--entry {next_open,level}` (default `next_open`). `main` refuses `long` + `level` for good, and `level` while it is not in `ENABLED_ENTRIES`; either refusal exits 2 through `parser.error`.

The long path (`--direction long --entry next_open`, the defaults) prints exactly today's text: same title, paragraphs, table and doc name, and no Wilson row. The short replicate draws its frames and events from the **same rng sequence** as the long one with the same seed. Only the idea changes: fixed shape, cap 20, raced short.

- [ ] **Step 1: Write the failing tests** (append to `tests/backtest_scripts/test_screen_trail_calibration.py`)

```python
EV = pd.Series(False, index=pd.bdate_range("2010-01-04", periods=5))


def test_wilson_interval_known_values():
    assert cal.wilson_interval(10, 200) == pytest.approx((0.027382, 0.089579), abs=1e-6)
    assert cal.wilson_interval(6, 200) == pytest.approx((0.013820, 0.063895), abs=1e-6)
    assert cal.wilson_interval(1, 4) == pytest.approx((0.045586, 0.699364), abs=1e-6)
    low, high = cal.wilson_interval(0, 200)
    assert low == 0.0 and high == pytest.approx(0.018846, abs=1e-6)


def test_wilson_interval_refuses_no_trials():
    with pytest.raises(ValueError):
        cal.wilson_interval(0, 0)


def test_doc_name_per_mode():
    assert cal.doc_name("long", "next_open", "2026-10-21") == "2026-10-21-trail-race-calibration.md"
    assert cal.doc_name("short", "next_open", "2026-10-21") == "2026-10-21-short-race-calibration.md"
    assert (cal.doc_name("short", "level", "2026-10-21")
            == "2026-10-21-short-level-race-calibration.md")
    with pytest.raises(ValueError):
        cal.doc_name("long", "level", "2026-10-21")


def test_the_long_idea_is_still_the_v163_trail_idea():
    idea = cal._idea(EV)
    assert (idea.name, idea.time_cap_bars, idea.race_shape, idea.direction, idea.entry) == (
        "aa_trail_calibration", 60, "trail", "long", "next_open")


def test_the_short_idea_is_fixed_cap_20_short():
    idea = cal._idea(EV, direction="short")
    assert cal.SHORT_CAP == 20
    assert (idea.name, idea.time_cap_bars, idea.race_shape, idea.direction, idea.entry) == (
        "aa_short_calibration", 20, "fixed", "short", "next_open")
    assert idea.events(None) is EV
    assert cal.CAL_IDEA_NAMES[("short", "level")] == "aa_short_level_calibration"
    with pytest.raises(ValueError):
        cal._idea(EV, direction="long", entry="level")


def test_a_short_replicate_races_the_fixed_shape_short(monkeypatch):
    seen = []
    real = cal.screen_idea.race.run_book

    def spy(*args, **kwargs):
        seen.append((kwargs.get("shape"), kwargs.get("direction")))
        return real(*args, **kwargs)

    monkeypatch.setattr(cal.screen_idea.race, "run_book", spy)
    v = cal.replicate(5, tickers=1, n_resamples=100, direction="short")
    assert isinstance(v, verdict.Verdict)
    assert seen and set(seen) == {("fixed", "short")}


def test_a_short_replicate_sees_the_long_replicates_frames_and_events(monkeypatch):
    seen = {"long": [], "short": []}
    real = cal.screen_idea.screen_ticker

    def spy(idea, name, df, spans, **kwargs):
        seen[idea.direction].append((name, df["Close"].to_numpy().copy(),
                                     idea.events(df).to_numpy().copy()))
        return real(idea, name, df, spans, **kwargs)

    monkeypatch.setattr(cal.screen_idea, "screen_ticker", spy)
    cal.replicate(7, tickers=2, n_resamples=100)
    cal.replicate(7, tickers=2, n_resamples=100, direction="short")
    assert len(seen["long"]) == len(seen["short"]) == 2
    for (n1, c1, e1), (n2, c2, e2) in zip(seen["long"], seen["short"]):
        assert n1 == n2 and np.array_equal(c1, c2) and np.array_equal(e1, e2)


def test_a_replicate_refuses_level_until_level_mode_lands():
    with pytest.raises(ValueError):
        cal.replicate(1, tickers=1, n_resamples=100, direction="short", entry="level")


def test_calibrate_hands_the_mode_to_every_replicate(monkeypatch):
    seen = []
    feed = iter(FAKE)

    def fake(seed, **kwargs):
        seen.append((seed, kwargs["direction"], kwargs["entry"]))
        return next(feed)

    monkeypatch.setattr(cal, "replicate", fake)
    cal.calibrate(4, seed=0, direction="short", **QUIET)
    assert seen == [(0, "short", "next_open"), (1, "short", "next_open"),
                    (2, "short", "next_open"), (3, "short", "next_open")]


def test_render_short_states_direction_rule_wilson_and_seeds(monkeypatch):
    _fake_replicates(monkeypatch, FAKE)
    result = cal.calibrate(4, seed=0, direction="short", **QUIET)
    params = {"replicates": 4, "seed": 0, "tickers": 2, "resamples": 200,
              "direction": "short", "entry": "next_open"}
    text = cal.render(result, params, "2026-10-21")
    assert text.startswith("# v182 short race A/A calibration (next-open entry) -> **over** "
                           "the 5% false-pass limit")
    for needle in ("1 of 4 = 25.0%", "≤ 5% (gating)",
                   "| Wilson 95% interval of the false-pass rate | 4.6% .. 69.9% | reported, not gated |",
                   "--direction short --entry next_open", "seed 0", "cap 20 bars",
                   "borrow 0.5% a year", "10 of 200", "df = 3", "| 3 |",
                   "no cached price file"):
        assert needle in text, needle


def test_the_long_render_ignores_the_new_params_and_has_no_wilson_row(monkeypatch):
    _fake_replicates(monkeypatch, FAKE)
    result = cal.calibrate(4, seed=100, **QUIET)
    base = {"replicates": 4, "seed": 100, "tickers": 2, "resamples": 200}
    plain = cal.render(result, base, "2026-10-15")
    assert cal.render(result, {**base, "direction": "long", "entry": "next_open"},
                      "2026-10-15") == plain
    assert "Wilson" not in plain


def test_a_short_run_writes_the_short_doc(tmp_path, monkeypatch):
    out_dir = tmp_path / "out"
    _fake_replicates(monkeypatch, [FAKE[1], FAKE[3]])
    argv = ["--direction", "short", "--replicates", "2", "--seed", "0",
            "--date", "2026-10-21", "--out-dir", str(out_dir)]
    assert cal.main(argv) == 0
    assert (out_dir / "2026-10-21-short-race-calibration.md").exists()
    assert not (out_dir / "2026-10-21-trail-race-calibration.md").exists()


def test_long_level_is_refused_for_good():
    with pytest.raises(SystemExit) as exc:
        cal.main(["--entry", "level", "--replicates", "1", "--dry-run"])
    assert exc.value.code == 2


def test_short_level_is_refused_until_level_mode_lands():
    """V182-12 enables level mode and replaces this test."""
    with pytest.raises(SystemExit) as exc:
        cal.main(["--direction", "short", "--entry", "level", "--replicates", "1", "--dry-run"])
    assert exc.value.code == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_trail_calibration.py`
Expected: FAIL — `AttributeError: module 'screen_trail_calibration' has no attribute 'wilson_interval'` (and `doc_name`, `SHORT_CAP`), `_idea() got an unexpected keyword argument 'direction'`, and argparse rejects `--direction`.

- [ ] **Step 3: Implement in `scripts/backtest/screen_trail_calibration.py`**

- Import `BORROW_RATE_ANNUAL` from `swingbot.core.edge.frictions`.
- Constants after `IDEA_NAME`: `SHORT_CAP`, `CAL_IDEA_NAMES`, `ENABLED_ENTRIES` (values in Interfaces), plus
  - `_DOC_SLUGS = {("long", "next_open"): "trail-race-calibration", ("short", "next_open"): "short-race-calibration", ("short", "level"): "short-level-race-calibration"}`;
  - `_ENTRY_LABELS = {"next_open": "next-open entry", "level": "level entry"}`.
- `doc_name(direction, entry, day)`: `f"{day}-{_DOC_SLUGS[(direction, entry)]}.md"`; an unknown pair raises `ValueError`.
- `_idea(events, *, direction="long", entry="next_open", levels=None)`:
  - an unknown `(direction, entry)` pair raises `ValueError`;
  - the long pair returns today's `Idea(...)` call unchanged;
  - a short pair returns `Idea(name=CAL_IDEA_NAMES[(direction, entry)], events=lambda df: events, time_cap_bars=SHORT_CAP, direction="short", entry=entry, levels=None if levels is None else (lambda df: levels), summary="random events, no planted effect, raced short", source="v182 short A/A calibration")`. Shape: `fixed`, the default.
- `replicate(..., direction="long", entry="next_open")`: raise `ValueError` when `entry not in ENABLED_ENTRIES`, before the rng is created. Otherwise use the same rng calls in the same order and pass `_idea(random_events(df.index, rng, rate), direction=direction, entry=entry)`.
- `calibrate(..., out=print, direction="long", entry="next_open")`: pass `direction=direction, entry=entry` to every `replicate(...)` call. Nothing else changes.
- `wilson_interval(k, n, z=1.96)`. For `n < 1`, raise `ValueError`. Otherwise:
  - `p = k / n`, `d = 1 + z * z / n`;
  - `centre = (p + z * z / (2 * n)) / d`;
  - `half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d`;
  - return `(max(0.0, centre - half), min(1.0, centre + half))`.
- Rendering, long text untouched:
  - Extract the long head's **Generator** paragraph into `_generator_paragraph() -> str`, returning the identical string. `_render_head` calls it, and the long golden proves the identity.
  - `render(result, params, day)`: when `params.get("direction", "long") == "long"`, run today's three sections unchanged. Otherwise run `[_render_head_short(result, params, day), _render_result_short(result), _render_replicates(result, params["seed"])]`, joined the same way.
  - `_render_head_short(result, params, day) -> list` copies the long head's shape. Title: `f"# v182 short race A/A calibration ({_ENTRY_LABELS[params['entry']]}) -> {'within' if holds else '**over**'} the {FALSE_PASS_MAX:.0%} false-pass limit"`. Paragraphs:
    - **Spec:** `` `docs/superpowers/specs/2026-10-21-v182-short-screen-range-breakdown-design.md` § Part A (calibration item 2) ``.
    - **Run:** the long sentence, with the command extended by `--direction short --entry {entry}`.
    - **Generator:** `_generator_paragraph()`.
    - **Race:** ``f"**Race:** the real `screen_ticker` with a fixed short idea (cap {SHORT_CAP} bars; entry next open, sold; stop {race.STOP_ATR} x ATR14[t] above, target {race.STOP_ATR * race.REWARD_RISK} x ATR14[t] below; borrow {BORROW_RATE_ANNUAL:.1%} a year on calendar days held) against a short matched null (K = {null.K}), pooled through the real `verdict.decide` (pass rule unchanged). Decision rule: false-pass rate ≤ {FALSE_PASS_MAX:.0%} (10 of 200 at the registered run); the Wilson 95% interval is printed, never gating."``. V182-12 adds the level wording.
  - `_render_result_short(result) -> list`: `_render_result(result)` with one row inserted right after the false-pass row (index 5): `f"| Wilson 95% interval of the false-pass rate | {low:.1%} .. {high:.1%} | reported, not gated |"`.
- Parser: add `--direction` (`choices=("long", "short")`, default `"long"`) and `--entry` (`choices=("next_open", "level")`, default `"next_open"`).
- `main`:
  - right after parsing, call `_mode_refusal(args.direction, args.entry) -> str | None` and, when it returns a message, `parser.error(...)` (exit 2). The messages: `"the level-mode long mirror is defined but unused (v182)"` for long + level; `"--entry level is not enabled yet (V182-12)"` while level is missing from `ENABLED_ENTRIES`;
  - pass `direction=` and `entry=` to `calibrate`;
  - add `"direction"` and `"entry"` to `params`;
  - write to `Path(args.out_dir) / doc_name(args.direction, args.entry, args.date)`.

  Keep a handle on the parser (`parser = build_parser()`) so `parser.error` is reachable.
- Docstring: add the usage line `python scripts/backtest/screen_trail_calibration.py --direction short --seed 0` and one sentence: v182 adds the short A/A, a fixed cap-20 idea raced short on the same frames and events, with the Wilson interval printed.
- Every function stays < 15 complexity.

- [ ] **Step 4: Run the tests to verify they pass, then the long goldens and the gate**

```bash
python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_trail_calibration.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_calibration_long_golden.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py
python scripts/dev/complexity_gate.py
```

Expected: `0 failed` everywhere; the existing v163 tests (`test_render_states_the_rate_the_rule_the_generator_and_every_seed`, `test_a_run_writes_the_dated_doc_and_the_exit_code_follows_the_rate`, `test_the_script_never_names_a_price_cache`) still pass untouched.

Smoke the short path once, small and printed only:

```bash
python scripts/backtest/screen_trail_calibration.py --direction short --replicates 2 --seed 0 --tickers 2 --resamples 200 --date 2026-10-21 --dry-run
```

Expected: a doc starting `# v182 short race A/A calibration (next-open entry) -> ...`, a Wilson row, seeds 0 and 1 in the per-replicate table; nothing written.

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/screen_trail_calibration.py tests/backtest_scripts/test_screen_trail_calibration.py
git commit -m "feat(v182): calibration --direction short -- cap-20 fixed short A/A, Wilson interval, doc per mode

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V182-8: Run the short next-open A/A (backtest-runner) and commit its doc

**Model:** sonnet — a scripted run, a fixed gate read off the output, and a commit; no code changes.

**Files:**
- Create: `docs/superpowers/results/<run-date>-short-race-calibration.md` (written by the script; `<run-date>` = the Berlin date of the run, ISO)

**Interfaces:**
- Consumes: `scripts/backtest/screen_trail_calibration.py --direction short` (V182-7), which races the real short `screen_ticker` (V182-4..V182-6).
- Produces: the committed short next-open A/A doc. It is the spec's Part A calibration item 2 and gates V182-9 (index § Parallelisation: Part A's calibration must pass before Part B builds on the race) and every short ledger row.

Gate (spec § Part A, item 2): **false passes ≤ 10 of 200**, seeds 0..199. The Wilson 95 % interval and the coverage are printed and never gate. The run reads synthetic frames only, never the 2010–2019 cache, and writes no ledger row. So it is not a pre-registered shot: if it fails, the race is fixed and the calibration re-run (spec: "stop, fix the race, re-run").

- [ ] **Step 1: Check the worktree is clean and the code is committed**

```bash
git status --short
git log --oneline -8
python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_calibration_long_golden.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_trail_calibration.py
```

Expected: `git status --short` prints nothing; the log shows the V182-1..V182-7 commits; all three files `0 failed`. Anything uncommitted means stop: the doc must describe committed code.

- [ ] **Step 2: Fix the run date**

Run: `date -u +%Y-%m-%dT%H:%M` and add 2 hours (Berlin summer time; Git Bash prints UTC even with `TZ` set). `<run-date>` is that Berlin day, e.g. `2026-10-22`. Use it in every step below.

- [ ] **Step 3: Dispatch `backtest-runner` with the exact command**

Dispatch the `backtest-runner` agent (it runs long jobs and returns only the summary), naming the worktree path `.claude/worktrees/2026-10-21-v182-short-screen-range-breakdown` and this command, run from that worktree's root:

```bash
python scripts/backtest/screen_trail_calibration.py --direction short --entry next_open --replicates 200 --seed 0 --tickers 24 --date <run-date>
```

The bootstrap stays at its default of 10,000 week resamples, as in the v163 run. Progress prints to stderr every 10 replicates (`[calibration] 10/200 replicates (5%)`), so the runner can report percent on a run of 15 minutes or more. Ask the runner to return:
- the exit code;
- the final stdout line (`false-pass k/200 = x%, coverage y% -> <path>`);
- the doc's first 30 lines.

Expected: exit code 0 and the doc at `docs/superpowers/results/<run-date>-short-race-calibration.md`.

- [ ] **Step 4: Verify the doc**

```bash
head -20 docs/superpowers/results/<run-date>-short-race-calibration.md
grep -c "^| [0-9]" docs/superpowers/results/<run-date>-short-race-calibration.md
grep -n "Wilson 95% interval" docs/superpowers/results/<run-date>-short-race-calibration.md
grep -n "^| 0 |\|^| 199 |" docs/superpowers/results/<run-date>-short-race-calibration.md
```

Expected:
- the title reads `# v182 short race A/A calibration (next-open entry) -> within the 5% false-pass limit`;
- the per-replicate row count is 200, and seeds 0 and 199 are both present;
- the Wilson row is present;
- the **Run** paragraph names `--direction short --entry next_open --replicates 200 --seed 0 --tickers 24`.

- [ ] **Step 5: Read the gate**

- **k ≤ 10 (exit 0):** the gate holds. Go to Step 6, and the plan continues to V182-9.
- **k > 10 (exit 1, title says `**over**`):** the gate fails, and the plan stops here. Do not start V182-9 and write no ledger row. Commit the doc anyway (Step 6, message `-- OVER the limit`), because a failed A/A is evidence. Then tell the partner the false-pass count, the Wilson interval and the per-replicate ΔExpR spread, and diagnose the short race with `superpowers:systematic-debugging` (check first the sign of `gross_r`, the borrow charge and the null direction). A fix is a new reviewed commit with its own regression test. Then re-run Step 3 with the same seeds, overwriting the doc and committing it again. Both commits stay in history.

- [ ] **Step 6: Commit the doc**

```bash
git add docs/superpowers/results/<run-date>-short-race-calibration.md
git commit -m "docs(v182): short next-open A/A calibration -- <k> of 200 false passes (gate <= 10)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Expected: one new commit holding only the results doc; `git status --short` is empty again.
