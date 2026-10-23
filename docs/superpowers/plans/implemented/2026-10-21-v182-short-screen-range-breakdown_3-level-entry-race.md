# v182 — Part 3: the level-entry race, the depth-copy null, level threading, the level A/A

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Spec:** [2026-10-21-v182-short-screen-range-breakdown-design.md](../specs/2026-10-21-v182-short-screen-range-breakdown-design.md) — Part B (the level-entry race mode, calibration items 3 and 4).
**Index:** [2026-10-21-v182-short-screen-range-breakdown_0-index.md](2026-10-21-v182-short-screen-range-breakdown_0-index.md) — Goal, Global Constraints, Review Focus, Parallelisation and the task ledger live there and bind every task below.
**Worktree:** `.claude/worktrees/2026-10-21-v182-short-screen-range-breakdown` (created in V182-1). Every command below runs from that worktree's root.

**Tasks:** V182-9..V182-12, sequential (index § Parallelisation: V182-8 → V182-9 → V182-10 → V182-11 → V182-12). V182-13 (Part 4) may run beside any of them: it shares no file with this part.

**Long byte-identity, every task:** after each task's own narrow run, also run both golden regression files from V182-1 and expect them green:

```bash
python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_calibration_long_golden.py
```

Never edit the golden files to make a test pass. Level mode is a new branch every next-open caller skips: a golden failure means a next-open call path changed (a keyword passed where none was before, a reordered rng call, an extra float operation). Revert it.

**Contracts from Parts 1 and 2 this part consumes** (index ledger):

- `sides.oriented(o, h, l, c, direction)`, `sides.holding_days(index, entry_pos, exit_pos)`, `sides.net_r(entry, price, risk, *, direction, days, slippage_bps=None, entry_bps=None, commission=None)` — real (un-negated) prices; `entry_bps=None` means the entry fill uses `slippage_bps` (V182-4).
- `race.race(df, event_pos, cap, *, atr=None, slippage_bps=None, commission=None, direction="long")`: `RaceResult.entry` is the real entry price; `race.run_book(..., shape="fixed", direction="long")` passes `direction=` to the race function only when it is not `"long"` (V182-4).
- `null.matched_null(..., shape="fixed", direction="long")` passes `direction=direction` to the race function on every call (V182-6).
- `Idea.entry in ("next_open", "level")`, `Idea.levels` (a level idea must have one, fixed shape only) (V182-3).
- `screen_idea._books` passes `direction=idea.direction` to `run_book` and `matched_null`; `_short_trade_line(idea, costs)` and `_short_hypothesis(idea)` exist, and `_short_hypothesis` already has the level wording through `_SHORT_ENTRY_TEXT["level"]` (V182-6).
- `screen_trail_calibration`: `SHORT_CAP`, `CAL_IDEA_NAMES`, `ENABLED_ENTRIES = ("next_open",)`, `_idea(events, *, direction, entry, levels)`, `replicate(..., direction, entry)`, `calibrate(..., direction, entry)`, `doc_name`, `_render_head_short`, `_mode_refusal`; `--entry level` is refused until V182-12 (V182-7).
- The short next-open A/A doc is committed and within the limit (V182-8): Part B starts only then.

---

# Phase B — the level-entry race mode

### Task V182-9: Level-mode race: fill on bar t, entry-bar stop rule, 2 × entry slippage

**Model:** opus — a second entry path through the shared race under the byte-identity rule; off-by-one bar reads (ATR[t−1], warm-up at t−1, exit on t) and the oriented stop check decide whether the result is honest.

**Files:**
- Modify: `swingbot/core/backtesting/screen/race.py` (docstring, imports, constants after `REWARD_RISK`, `race`, `_drop_reason`, `candidate_events`, `run_book`; new `level_fills`, `_base_bps`, `_race_level`, `_level_kwargs`)
- Create: `tests/backtesting/screen/test_race_level.py`

**Interfaces:**
- Consumes: `sides.oriented`, `sides.holding_days`, `sides.net_r(..., entry_bps=)` (V182-4); `_first_exit` (`race.py:79`, unchanged); `config.SLIPPAGE_BPS` (the base `apply_frictions` reads when `slippage_bps` is `None`).
- Produces:
  - `LEVEL_SLIPPAGE_FACTOR = 2.0`, `REPRICE_SLIPPAGE_FACTOR = 3.0`.
  - `level_fills(df, event_pos, levels, atr, direction) -> tuple[np.ndarray, np.ndarray]` — per event bar t: short fill `min(Open[t], levels[t])`, depth `(Open[t] − fill) / ATR14[t−1]`; long mirror fill `max(Open[t], levels[t])`, depth `(fill − Open[t]) / ATR14[t−1]`. Raises `ValueError` (message contains `fill`) when an event's level is not finite or the bar did not trade through it (short `Low[t] < level`, long `High[t] > level`, strict, the event inequality), and `ValueError` (message contains `ATR14[t-1]`) for an event on bar 0. `levels` is a float array aligned with `df`; `atr` a Series or array aligned with `df`.
  - `race(df, event_pos, cap, *, atr=None, slippage_bps=None, commission=None, direction="long", fill=None, level_factor=LEVEL_SLIPPAGE_FACTOR) -> RaceResult` — `fill=None` is the next-open race of V182-4, untouched. With `fill` (real prices, one per event): entry on bar t at `fill`, risk `STOP_ATR × ATR14[t−1]`, on bar t only the stop counts (exit at the stop, outcome `stop`, `exit_pos = t`), bars t+1..t+cap race through `_first_exit`; entry slippage `level_factor × base` where base is `slippage_bps`, or `config.SLIPPAGE_BPS` when `None`; holding days from bar t.
  - `candidate_events(events, member, warm, cap, *, entry="next_open")` — `entry="level"` reads warm-up at t−1 (bar 0 is `dropped_warmup`); member and window checks unchanged.
  - `run_book(df, events, cap, *, member, warm, atr, slippage_bps=None, commission=None, shape="fixed", direction="long", levels: np.ndarray | None = None, level_factor=LEVEL_SLIPPAGE_FACTOR)` — `levels=None` is today's call exactly (no `entry=`, `fill=` or `level_factor=` keyword reaches `candidate_events` or the race function). With `levels`: `shape` must be `"fixed"` (`ValueError` naming `fixed` otherwise), candidates use `entry="level"`, the race gets `fill=level_fills(...)[0]` for the candidates and `level_factor=`.
- Consumed by: V182-10 (`race(fill=, level_factor=)`, `LEVEL_SLIPPAGE_FACTOR`), V182-11 (`run_book(levels=, level_factor=)`, `level_fills`, `REPRICE_SLIPPAGE_FACTOR`), V182-16 (`candidate_events(entry=)`).

**How level mode works:** the race still runs in oriented space (`sides.oriented`), so the long mirror comes free and a short is the long machinery on negated prices. The oriented entry is `fill` (negated for a short). On the fill bar the oriented low `l[t]` (for a short, the real high negated) is checked against the stop; a hit replaces whatever `_first_exit` found on bars t+1..t+cap. The window rule is unchanged: bars t+1..t+cap must exist, so `pos + cap > n − 1` still drops as `dropped_window`.

- [ ] **Step 1: Confirm Part A's A/A passed**

```bash
ls docs/superpowers/results/*-short-race-calibration.md
head -1 docs/superpowers/results/*-short-race-calibration.md
git status --short
```

Expected: one doc, its title says `-> within the 5% false-pass limit`, and the worktree is clean. A missing doc or an `**over**` title means V182-8 has not passed: stop (index § Parallelisation, spec gate).

- [ ] **Step 2: Write the failing `tests/backtesting/screen/test_race_level.py`**

```python
"""v182 level-mode race (spec Part B): a resting stop order filled on the
event bar, risk from ATR14[t-1], only the stop counts on the fill bar,
entry slippage LEVEL_SLIPPAGE_FACTOR x base."""
import numpy as np
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.backtesting.screen import indicators, race as race_mod, sides
from tests.backtesting.screen.helpers import frame, random_walk

QUIET = (100.0, 101.0, 99.0, 100.0)   # bar 0: ATR14[t-1] is read here
C_HAND = 256.0                         # a power of two: reflection is exact on 1/8 prices


def _frame(bars):
    rows = [QUIET] + list(bars)
    o, h, l, c = (np.array(col, dtype=float) for col in zip(*rows))
    return frame(c, opens=o, highs=h, lows=l)


def _mirror(df, c):
    out = df.copy()
    out["Open"], out["Close"] = c - df["Open"], c - df["Close"]
    out["High"], out["Low"] = c - df["Low"], c - df["High"]
    return out


def _atr(df, value=2.0):
    return pd.Series(value, index=df.index)          # risk 1.5 x 2 = 3


def _level(df, level, direction="short", **kw):
    """Race the event on bar 1 with order level ``level``, to the last bar."""
    kw.setdefault("slippage_bps", 0.0)
    kw.setdefault("commission", 0.0)
    atr = kw.pop("atr", _atr(df))
    fill, _ = race_mod.level_fills(df, np.array([1]), np.full(len(df), level), atr, direction)
    return race_mod.race(df, [1], len(df) - 2, atr=atr, fill=fill, direction=direction, **kw)


HAND = {   # name: (bars from the event bar on, short level, outcome, entry, gross R, exit bar)
    "inside": ([(100.0, 100.5, 98.0, 98.5), QUIET], 99.0, "timeout", 99.0, -1.0 / 3.0, 2),
    "gap_fill": ([(98.0, 98.5, 97.0, 97.5), (97.5, 98.0, 97.0, 97.5)], 99.0,
                 "timeout", 98.0, 0.5 / 3.0, 2),
    "fill_bar_stop": ([(100.0, 102.5, 98.0, 100.0), QUIET], 99.5, "stop", 99.5, -1.0, 1),
    "fill_bar_target_ignored": ([(100.0, 100.5, 92.0, 93.0), (93.5, 94.0, 92.5, 93.0)], 99.0,
                                "target", 99.0, 2.0, 2),
    "gap_stop_next_bar": ([(100.0, 100.5, 98.0, 98.5), (103.0, 104.0, 102.5, 103.5)], 99.0,
                          "gap_stop", 99.0, -4.0 / 3.0, 2),
}


def test_level_constants_are_the_spec_values():
    assert race_mod.LEVEL_SLIPPAGE_FACTOR == 2.0
    assert race_mod.REPRICE_SLIPPAGE_FACTOR == 3.0


@pytest.mark.parametrize("name", sorted(HAND))
def test_short_level_race_on_hand_built_frames(name):
    bars, level, outcome, entry, gross, exit_bar = HAND[name]
    out = _level(_frame(bars), level)
    assert out.outcome.tolist() == [outcome]
    assert out.entry.tolist() == [entry]                 # the real fill price
    assert out.risk.tolist() == [3.0]
    assert out.gross_r.tolist() == [pytest.approx(gross, rel=1e-12)]
    assert out.exit_pos.tolist() == [exit_bar]


@pytest.mark.parametrize("name", sorted(HAND))
def test_short_level_on_p_is_long_level_on_the_reflected_frame_exactly(name):
    bars, level, *_ = HAND[name]
    df = _frame(bars)
    short = _level(df, level)
    long = _level(_mirror(df, C_HAND), C_HAND - level, direction="long")
    assert short.outcome.tolist() == long.outcome.tolist()
    assert short.exit_pos.tolist() == long.exit_pos.tolist()
    assert short.gross_r.tolist() == long.gross_r.tolist()


def test_risk_reads_the_atr_known_when_the_order_was_placed():
    df = _frame([(100.0, 100.5, 98.0, 98.5), QUIET])
    atr = pd.Series([2.0, 4.0, 8.0], index=df.index)
    out = _level(df, 99.0, atr=atr)
    assert out.risk.tolist() == [3.0]                    # 1.5 x ATR14[0], not ATR14[1]


@pytest.mark.parametrize("direction", ["short", "long"])
def test_level_at_the_open_is_the_next_open_race_shifted_one_bar(direction):
    """Spec Part B item 3: level = open and no fill-bar touch reproduces the
    next-open race of the bar before, one bar longer."""
    df = random_walk(600, seed=21)
    atr = indicators.atr(df)
    cap = 20
    o, h, l = (df[k].to_numpy(dtype=float) for k in ("Open", "High", "Low"))
    a = atr.to_numpy(dtype=float)
    p = np.arange(20, len(df) - 1 - cap)
    risk = race_mod.STOP_ATR * a[p - 1]
    sign = -1.0 if direction == "short" else 1.0
    stop, target = o[p] - sign * risk, o[p] + sign * race_mod.REWARD_RISK * risk
    quiet = (h[p] < np.maximum(stop, target)) & (l[p] > np.minimum(stop, target))
    p = p[quiet]
    assert p.size > 100                                            # non-vacuous
    zero = {"slippage_bps": 0.0, "commission": 0.0, "direction": direction, "atr": atr}
    level = race_mod.race(df, p, cap, fill=o[p], **zero)
    shifted = race_mod.race(df, p - 1, cap + 1, **zero)
    assert level.outcome.tolist() == shifted.outcome.tolist()
    assert level.exit_pos.tolist() == shifted.exit_pos.tolist()
    assert level.gross_r.tolist() == shifted.gross_r.tolist()
    assert level.r.tolist() == shifted.r.tolist()                  # 2 x 0 bps = 0
    assert level.entry.tolist() == o[p].tolist()


def test_level_entry_pays_the_factor_on_the_entry_fill_only():
    df = _frame([(100.0, 100.5, 98.0, 98.5), QUIET])
    fill, _ = race_mod.level_fills(df, np.array([1]), np.full(len(df), 99.0), _atr(df), "short")
    for factor, entry_bps in ((race_mod.LEVEL_SLIPPAGE_FACTOR, 10.0),
                              (race_mod.REPRICE_SLIPPAGE_FACTOR, 15.0)):
        out = race_mod.race(df, [1], 1, atr=_atr(df), fill=fill, direction="short",
                            slippage_bps=5.0, commission=0.02, level_factor=factor)
        days = sides.holding_days(df.index, np.array([1]), out.exit_pos)
        expected = sides.net_r(np.array([99.0]), np.array([100.0]), np.array([3.0]),
                               direction="short", days=days, slippage_bps=5.0,
                               entry_bps=entry_bps, commission=0.02)
        assert out.r.tolist() == expected.tolist()


def test_level_factor_multiplies_the_configured_base(monkeypatch):
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 7.0)
    df = _frame([(100.0, 100.5, 98.0, 98.5), QUIET])
    fill, _ = race_mod.level_fills(df, np.array([1]), np.full(len(df), 99.0), _atr(df), "short")
    out = race_mod.race(df, [1], 1, atr=_atr(df), fill=fill, direction="short", commission=0.0)
    days = sides.holding_days(df.index, np.array([1]), out.exit_pos)
    expected = sides.net_r(np.array([99.0]), np.array([100.0]), np.array([3.0]),
                           direction="short", days=days, slippage_bps=None,
                           entry_bps=14.0, commission=0.0)
    assert out.r.tolist() == expected.tolist()


def test_level_fills_short_take_the_lower_of_open_and_level():
    df = _frame([(100.0, 100.5, 98.0, 98.5), (98.0, 98.5, 97.0, 97.5)])
    atr = pd.Series([2.0, 4.0, 8.0], index=df.index)
    fill, depth = race_mod.level_fills(df, np.array([1, 2]), np.array([np.nan, 99.0, 99.0]),
                                       atr, "short")
    assert fill.tolist() == [99.0, 98.0]
    assert depth.tolist() == [0.5, 0.0]          # (100 - 99) / ATR14[0]; a gap fill is 0


def test_level_fills_long_mirror_take_the_higher_of_open_and_level():
    df = _frame([(100.0, 102.0, 99.5, 101.5), (102.0, 103.0, 101.5, 102.5)])
    atr = pd.Series([2.0, 4.0, 8.0], index=df.index)
    fill, depth = race_mod.level_fills(df, np.array([1, 2]), np.array([np.nan, 101.0, 101.0]),
                                       atr, "long")
    assert fill.tolist() == [101.0, 102.0]
    assert depth.tolist() == [0.5, 0.0]


@pytest.mark.parametrize("level", [np.nan, 97.0, 98.0])   # 98.0: a touch is not a fill
def test_level_fills_refuse_an_order_that_did_not_fill(level):
    df = _frame([(100.0, 100.5, 98.0, 98.5)])
    with pytest.raises(ValueError, match="fill"):
        race_mod.level_fills(df, np.array([1]), np.full(len(df), level), _atr(df), "short")


def test_a_level_event_on_bar_zero_is_refused():
    df = _frame([QUIET, QUIET])
    with pytest.raises(ValueError, match=r"ATR14\[t-1\]"):
        race_mod.level_fills(df, np.array([0]), np.full(len(df), 100.5), _atr(df), "short")
    with pytest.raises(ValueError, match=r"ATR14\[t-1\]"):
        race_mod.race(df, [0], 1, atr=_atr(df), fill=np.array([100.0]), direction="short")


def test_level_candidates_read_warm_up_at_the_bar_before():
    events = np.array([True, True, True, True, False, False, False, False])
    member = np.ones(8, dtype=bool)
    warm = np.array([False, False, True, False, True, True, True, True])
    cand, counts = race_mod.candidate_events(events, member, warm, 2, entry="level")
    assert cand.tolist() == [3] and counts["dropped_warmup"] == 3
    cand, counts = race_mod.candidate_events(events, member, warm, 2)
    assert cand.tolist() == [2] and counts["dropped_warmup"] == 3


def _book(df, events, levels, cap, *, atr=None, warm=None, **kw):
    n = len(df)
    atr = _atr(df) if atr is None else atr
    warm = np.ones(n, dtype=bool) if warm is None else warm
    return race_mod.run_book(df, events, cap, member=np.ones(n, dtype=bool), warm=warm,
                             atr=atr, direction="short", levels=levels, **kw)


def test_level_event_with_nan_prior_atr_is_dropped_as_warmup():
    df = random_walk(120, seed=3)
    atr = indicators.atr(df).copy()
    atr.iloc[59] = np.nan
    warm = race_mod.warm_mask(atr, pd.Series(1.0, index=df.index))
    events = np.zeros(len(df), dtype=bool)
    events[[60, 90]] = True
    levels = (df["Low"] + 0.25).to_numpy()
    booked, counts = _book(df, events, levels, 10, atr=atr, warm=warm)
    assert counts["dropped_warmup"] == 1
    assert booked.event_pos.tolist() == [90]
    assert np.isfinite(booked.r).all() and np.isfinite(booked.risk).all()


def test_level_event_near_the_end_drops_as_window():
    df = random_walk(120, seed=3)
    events = np.zeros(len(df), dtype=bool)
    events[[60, 115]] = True
    booked, counts = _book(df, events, (df["Low"] + 0.25).to_numpy(), 10)
    assert counts["dropped_window"] == 1
    assert booked.event_pos.tolist() == [60]


def test_entry_bar_stop_lets_the_next_bar_trade():
    df = _frame([(100.0, 102.5, 98.0, 100.0), (100.0, 100.5, 98.0, 98.5), QUIET, QUIET])
    events = np.array([False, True, True, False, False])
    levels = np.array([np.nan, 99.5, 99.0, np.nan, np.nan])
    booked, counts = _book(df, events, levels, 2, slippage_bps=0.0, commission=0.0)
    assert booked.event_pos.tolist() == [1, 2]
    assert booked.exit_pos.tolist() == [1, 4]
    assert booked.outcome.tolist() == ["stop", "timeout"]
    assert counts["skipped_overlap"] == 0


def test_run_book_level_needs_the_fixed_shape():
    df = _frame([(100.0, 100.5, 98.0, 98.5), QUIET, QUIET])
    with pytest.raises(ValueError, match="fixed"):
        _book(df, np.array([False, True, False, False]), np.full(4, 99.0), 1, shape="trail")


def _spy_race(monkeypatch):
    seen = []

    def fake(df, cand, cap, **kwargs):
        seen.append(kwargs)
        return race_mod.RaceResult.empty()

    monkeypatch.setattr(race_mod, "race_for", lambda shape: fake)
    return seen


def test_run_book_without_levels_passes_no_level_keyword(monkeypatch):
    seen = _spy_race(monkeypatch)
    df = random_walk(100, seed=1)
    for direction in ("long", "short"):
        race_mod.run_book(df, np.zeros(100, dtype=bool), 5, member=np.ones(100, bool),
                          warm=np.ones(100, bool), atr=indicators.atr(df), direction=direction)
    assert len(seen) == 2
    assert all(not ({"fill", "level_factor"} & set(kw)) for kw in seen)


def test_run_book_threads_the_fills_and_the_factor(monkeypatch):
    seen = _spy_race(monkeypatch)
    df = _frame([(100.0, 100.5, 98.0, 98.5), (100.0, 100.5, 98.0, 98.5), QUIET, QUIET])
    events = np.array([False, True, True, False, False])
    levels = np.array([np.nan, 99.0, 99.25, np.nan, np.nan])
    _book(df, events, levels, 2, level_factor=race_mod.REPRICE_SLIPPAGE_FACTOR)
    assert seen[0]["fill"].tolist() == [99.0, 99.25]
    assert seen[0]["level_factor"] == 3.0 and seen[0]["direction"] == "short"
```

Check the `HAND` values by hand before running (short, ATR14[0] = 2, risk 3):

| case | fill | stop / target | bar 1 (fill bar) | bar 2 | outcome, gross |
|---|---|---|---|---|---|
| inside | min(100, 99) = 99 | 102 / 93 | high 100.5 < 102 | QUIET, no touch, close 100 | timeout, (99 − 100)/3 |
| gap_fill | open 98 < 99 → 98 | 101 / 92 | high 98.5 < 101 | close 97.5 | timeout, (98 − 97.5)/3 |
| fill_bar_stop | 99.5 | 102.5 / 93.5 | high 102.5 ≥ 102.5 → stop on bar 1 | — | stop, −1 |
| fill_bar_target_ignored | 99 | 102 / 93 | low 92 ≤ 93 ignored | low 92.5 ≤ 93 → target | target, +2 |
| gap_stop_next_bar | 99 | 102 / 93 | high 100.5 | open 103 ≥ 102 | gap_stop, (99 − 103)/3 |

Every price is a multiple of 1/8 and `C_HAND = 256`, so the reflected frame (and level `256 − level`) is exact. In `test_entry_bar_stop_lets_the_next_bar_trade` the first event exits on its own bar (`exit_pos = 1`), so the event on bar 2 starts after it and is kept (Review Focus 4).

- [ ] **Step 3: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_race_level.py`
Expected: FAIL — `AttributeError: module ... race has no attribute 'LEVEL_SLIPPAGE_FACTOR'` / `'level_fills'`, `TypeError: race() got an unexpected keyword argument 'fill'`, `candidate_events() got an unexpected keyword argument 'entry'`.

- [ ] **Step 4: Implement level mode in `swingbot/core/backtesting/screen/race.py`**

- Imports: add `from swingbot import config` and keep `from swingbot.core.backtesting.screen import indicators, sides` (V182-4).
- Constants after `REWARD_RISK`: `LEVEL_SLIPPAGE_FACTOR = 2.0   # v182: a level entry is a stop-market order through a broken level` and `REPRICE_SLIPPAGE_FACTOR = 3.0   # v182: the level book repriced at 3 x base; printed, never gating`.
- `_base_bps(slippage_bps) -> float`: `getattr(config, "SLIPPAGE_BPS", 5.0)` when `None`, else the value (the same base `apply_frictions` reads).
- `level_fills(df, event_pos, levels, atr, direction)` with the semantics under **Interfaces**:
  - check bar 0 first (`"a level entry reads ATR14[t-1]; an event on bar 0 is dropped_warmup"`);
  - read `o`, `lvl = levels[t]`, `a = atr[t − 1]`;
  - short: `fill = np.minimum(o, lvl)`, `reached = low < lvl`; long: `fill = np.maximum(o, lvl)`, `reached = high > lvl`; any other direction raises `ValueError` naming it;
  - refuse unless `np.isfinite(lvl) & reached` holds for every event: `ValueError(f"a level order must fill on its own bar; {k} event(s) did not")`.
- `race(...)`: add `fill=None, level_factor: float = LEVEL_SLIPPAGE_FACTOR` to the keyword list. After `_check_positions(...)`, the empty return and `atr_v = ...`, add `if fill is not None: return _race_level(df, event_pos, cap, atr_v, np.asarray(fill, dtype=float), slippage_bps=slippage_bps, commission=commission, direction=direction, level_factor=level_factor)`. The next-open body after it does not change.
- `_race_level(df, event_pos, cap, atr_v, fill, *, slippage_bps, commission, direction, level_factor) -> RaceResult` — this algorithm:

```python
    if event_pos.min() < 1:
        raise ValueError("a level entry reads ATR14[t-1]; an event on bar 0 is dropped_warmup")
    o, h, l, c = sides.oriented(*(df[col].to_numpy(dtype=float)
                                  for col in ("Open", "High", "Low", "Close")), direction)
    entry = -fill if direction == "short" else fill          # oriented space
    risk = STOP_ATR * atr_v[event_pos - 1]
    stop, target = entry - risk, entry + REWARD_RISK * risk
    bars = event_pos[:, None] + 1 + np.arange(cap)[None, :]
    price, code, offset = _first_exit(o[bars], h[bars], l[bars], c[bars], stop, target)
    exit_pos = event_pos + 1 + offset
    on_fill_bar = l[event_pos] <= stop                       # short: High[t] >= stop
    price = np.where(on_fill_bar, stop, price)
    code = np.where(on_fill_bar, OUTCOMES.index("stop"), code)
    exit_pos = np.where(on_fill_bar, event_pos, exit_pos)
    gross = (price - entry) / risk
    if direction == "short":
        entry, price = -entry, -price
    net = sides.net_r(entry, price, risk, direction=direction,
                      days=sides.holding_days(df.index, event_pos, exit_pos),
                      slippage_bps=slippage_bps,
                      entry_bps=level_factor * _base_bps(slippage_bps),
                      commission=commission)
    return RaceResult(event_pos, exit_pos, entry, risk, gross, net, np.asarray(OUTCOMES)[code])
```

- `_drop_reason(pos, member, warm, cap, n, lag: int = 0)`: the warm-up line becomes `if pos - lag < 0 or not warm[pos - lag]: return "dropped_warmup"`. With `lag = 0` it is today's check (`pos` is never negative).
- `candidate_events(events, member, warm, cap: int, *, entry: str = "next_open")`: `lag = _WARM_LAG[entry]` with module constant `_WARM_LAG = {"next_open": 0, "level": 1}` (an unknown entry raises `ValueError` naming it); pass `lag` to `_drop_reason`.
- `_level_kwargs(df, cand, levels, atr, direction, level_factor) -> dict`: `{"fill": level_fills(df, cand, levels, atr, direction)[0], "level_factor": level_factor}`; for an empty `cand` the fill is `np.array([], dtype=float)` and `level_fills` is not called.
- `run_book(..., direction: str = "long", levels=None, level_factor: float = LEVEL_SLIPPAGE_FACTOR)`:
  - `levels is None`: the V182-4 body exactly (`candidate_events(events, member, warm, cap)` with no `entry=`, the `extra` direction dict, the same race call).
  - `levels is not None`: refuse `shape != "fixed"` with `ValueError("level entry races the fixed shape only")` before anything runs; `candidate_events(..., entry="level")`; `extra.update(_level_kwargs(df, cand, np.asarray(levels, dtype=float), atr, direction, level_factor))`. The V182-4 direction rule is unchanged (a short passes `direction=`). Overlap and counts as today.
  - Keep `run_book` under complexity 15: the level branch is one `if` plus the helper.
- Docstring: add a paragraph — `v182 level mode (fill=...): a resting stop order placed before bar t opens from levels known at <= t-1, living one bar. Entry on bar t at fill (short: min(Open[t], level); long mirror: max); risk = 1.5 x ATR14[t-1]; on bar t only the stop counts (exit at the stop, exit_pos = t); bars t+1..t+cap race as above; entry slippage LEVEL_SLIPPAGE_FACTOR x base; warm-up read at t-1. Fixed shape only.`

- [ ] **Step 5: Run the tests to verify they pass, then the neighbours, the long goldens and the gate**

```bash
python scripts/dev/testrun.py file tests/backtesting/screen/test_race_level.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_race.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_race_short.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_null.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_calibration_long_golden.py
python scripts/dev/complexity_gate.py
```

Expected: `0 failed` everywhere and no complexity regression. If the equivalence test fails only on `r`, check that `entry_bps` is `level_factor * 0.0 = 0.0` there and that `holding_days` starts at bar t (not t+1) in level mode.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/screen/race.py tests/backtesting/screen/test_race_level.py
git commit -m "feat(v182): level-mode race -- fill on the event bar, ATR14[t-1] risk, fill-bar stop only, 2 x entry slippage

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V182-10: Level null: depth copy, replacement on the child stream, `null_unfilled`

**Model:** opus — random-stream discipline (the next-open draw must stay bit-identical) plus a fairness-critical fill rule; a wrong stream or a silently empty group biases every level verdict.

**Files:**
- Modify: `swingbot/core/backtesting/screen/null.py` (docstring, `NullDraw`, `_empty`, `matched_null`; new `LEVEL_STREAM`, `child_seed`, `NullGroups`, `_null_fills`, `_level_group`, `draw_groups`)
- Create: `tests/backtesting/screen/test_null_level.py`

**Interfaces:**
- Consumes: `race.race(..., fill=, level_factor=)`, `race.LEVEL_SLIPPAGE_FACTOR` (V182-9); `race.race_for(shape)`; `matched_null(..., direction=)` (V182-6); `indicators.atr`.
- Produces:
  - `LEVEL_STREAM = 1`; `child_seed(seed) -> list[int]` — a list seed gains `LEVEL_STREAM` at the end (`[*seed, 1]`); an int seed is wrapped first (`[seed, 1]`).
  - `NullGroups` (frozen dataclass, `eq=False`): `event_pos: np.ndarray` (kept events), `groups: tuple` (sorted null positions per kept event), `fills: tuple | None` (real fill prices aligned with `groups`; `None` in next-open mode), `dropped_no_match: int`, `null_slots: int` (Σ min(k, pool) over events whose pool reached `MIN_CANDIDATES`), `null_unfilled: int` (slots left unfilled; 0 in next-open mode), `null_depths: tuple` (realised depth of every filled null trade, in group order; `()` in next-open mode).
  - `draw_groups(df, event_pos, eligible, k, seed, *, atr, trend, direction="long", depth=None) -> NullGroups` — `depth=None` is today's draw, call for call on `np.random.default_rng(seed)`. `depth` (one value per event, in ATR14[t−1]) switches on level mode. No race runs here; V182-16's `--count-only` reuses it.
  - `matched_null(df, event_pos, eligible, k, seed, *, cap, atr, trend, slippage_bps=None, commission=None, shape="fixed", direction="long", depth=None, level_factor=race_mod.LEVEL_SLIPPAGE_FACTOR) -> NullDraw` — `draw_groups`, then one race; level mode passes `fill=np.concatenate(g.fills)` and `level_factor=` to the race function, next-open mode passes neither.
  - `NullDraw` appended fields: `null_slots: int = 0`, `null_unfilled: int = 0`, `null_depths: tuple = ()`, copied from the `NullGroups`.
- Consumed by: V182-11 (`matched_null(depth=, level_factor=)`, `NullDraw.null_slots/null_unfilled/null_depths`), V182-16 (`draw_groups(depth=)`, `NullGroups`).

**The level draw, per event e with depth d_e (spec Part B; index Global Constraints):**

1. `pool = candidates(pos, eligible, months, trend)`; fewer than `MIN_CANDIDATES` drops the event as today (no slots counted).
2. `m = min(k, len(pool))`; `null_slots += m`. The first draw is **today's call on the main stream**: `first = rng.choice(pool, size=m, replace=False)`. So the main stream is consumed exactly as in next-open mode.
3. A null bar p fills when `p ≥ 1`, `ATR14[p−1]` is finite and > 0, and the bar trades through its own level: short level `Open[p] − d_e × ATR14[p−1]`, filled when `Low[p] ≤ level`; long mirror `Open[p] + d_e × ATR14[p−1]`, filled when `High[p] ≥ level`. The fill price is that level (it never lies beyond the open, because `d_e ≥ 0`).
4. Unfilled first draws are replaced from the rest of the pool (`np.setdiff1d(pool, first)`), in the order of `child.permutation(rest)`, taking the first fillable bars until m are filled or the rest is used up. `child = np.random.default_rng(child_seed(seed))` is created once per `draw_groups` call, in level mode only. `child.permutation` runs only for an event that has an unfilled first draw and a non-empty rest.
5. `null_unfilled += m − filled`. An event with zero filled bars counts in `dropped_no_match` and keeps no group. Otherwise its group is the filled positions sorted ascending, with `fills` and `null_depths` reordered with them. The realised depth is `(Open[p] − fill) / ATR14[p−1]` (short) or `(fill − Open[p]) / ATR14[p−1]` (long).

- [ ] **Step 1: Write the failing `tests/backtesting/screen/test_null_level.py`**

```python
"""v182 level null (spec Part B): each event's null bars copy its fill depth;
unfilled draws are replaced from the same pool on a child stream; the
next-open draw is unchanged."""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import null, race as race_mod
from tests.backtesting.screen.helpers import random_walk

CAP = 10
SEED = [42, 7, 9]
EVENTS = np.array([30, 95, 160, 230])


def _setup(n=400, seed=7, atr_value=1.0):
    df = random_walk(n, seed=seed, start="2019-01-01")
    atr = pd.Series(atr_value, index=df.index)
    all_ = np.ones(n, dtype=bool)
    events = np.zeros(n, dtype=bool)
    events[EVENTS] = True
    return df, atr, all_, null.eligible_mask(events, all_, all_, CAP)


def _groups(df, atr, all_, eligible, k, *, depth=None, direction="short", seed=SEED):
    return null.draw_groups(df, EVENTS, eligible, k, seed, atr=atr, trend=all_,
                            direction=direction, depth=depth)


def _old_groups(df, eligible, k, seed, trend):
    """The v140 draw, inlined: the order every next-open null keeps."""
    rng = np.random.default_rng(seed)
    months = null.month_key(df.index)
    out = []
    for pos in EVENTS:
        pool = null.candidates(pos, eligible, months, trend)
        if len(pool) < null.MIN_CANDIDATES:
            continue
        out.append(np.sort(rng.choice(pool, size=min(k, len(pool)), replace=False)).tolist())
    return out


def _pools(df, eligible, all_):
    months = null.month_key(df.index)
    return [null.candidates(pos, eligible, months, all_) for pos in EVENTS]


def test_child_seed_extends_the_seed_and_wraps_an_int():
    assert null.LEVEL_STREAM == 1
    assert null.child_seed([42, 7, 9]) == [42, 7, 9, 1]
    assert null.child_seed(5) == [5, 1]
    assert null.child_seed(null.null_seed("x", "AAA"))[:3] == null.null_seed("x", "AAA")


def test_next_open_groups_keep_the_v140_draw_order():
    df, atr, all_, eligible = _setup()
    g = _groups(df, atr, all_, eligible, 20, direction="long")
    assert [x.tolist() for x in g.groups] == _old_groups(df, eligible, 20, SEED, all_)
    assert g.fills is None and g.null_unfilled == 0 and g.null_depths == ()
    assert g.null_slots == sum(len(x) for x in g.groups)
    draw = null.matched_null(df, EVENTS, eligible, 20, SEED, cap=CAP, atr=atr, trend=all_,
                             slippage_bps=0.0, commission=0.0)
    assert [x.tolist() for x in draw.groups] == [x.tolist() for x in g.groups]


def test_only_level_mode_creates_the_child_stream(monkeypatch):
    df, atr, all_, eligible = _setup()
    seeds = []
    real = np.random.default_rng

    def spy(seed=None):
        seeds.append(seed)
        return real(seed)

    monkeypatch.setattr(null.np.random, "default_rng", spy)
    _groups(df, atr, all_, eligible, 5)
    assert seeds == [SEED]
    seeds.clear()
    _groups(df, atr, all_, eligible, 5, depth=np.full(len(EVENTS), 1.0))
    assert seeds == [SEED, [42, 7, 9, 1]]


def test_zero_depth_fills_every_first_draw_at_its_open():
    df, atr, all_, eligible = _setup()
    plain = _groups(df, atr, all_, eligible, 5)
    level = _groups(df, atr, all_, eligible, 5, depth=np.zeros(len(EVENTS)))
    assert [x.tolist() for x in level.groups] == [x.tolist() for x in plain.groups]
    o = df["Open"].to_numpy()
    assert [f.tolist() for f in level.fills] == [o[x].tolist() for x in level.groups]
    assert level.null_unfilled == 0 and set(level.null_depths) == {0.0}


@pytest.mark.parametrize("direction", ["short", "long"])
def test_a_null_bar_fills_at_its_open_shifted_by_the_event_depth(direction):
    df, atr, all_, eligible = _setup()
    o, h, l = (df[k].to_numpy() for k in ("Open", "High", "Low"))
    a = atr.to_numpy()
    g = _groups(df, atr, all_, eligible, 5, depth=np.full(len(EVENTS), 0.5),
                direction=direction)
    sign = -1.0 if direction == "short" else 1.0
    for group, fills in zip(g.groups, g.fills):
        assert fills.tolist() == (o[group] + sign * 0.5 * a[group - 1]).tolist()
        reached = l[group] <= fills if direction == "short" else h[group] >= fills
        assert reached.all()


def test_unfilled_first_draws_are_replaced_from_the_same_pool():
    df, atr, all_, eligible = _setup()
    plain = _groups(df, atr, all_, eligible, 5)
    level = _groups(df, atr, all_, eligible, 5, depth=np.full(len(EVENTS), 1.0))
    again = _groups(df, atr, all_, eligible, 5, depth=np.full(len(EVENTS), 1.0))
    assert [x.tolist() for x in level.groups] == [x.tolist() for x in again.groups]
    assert [x.tolist() for x in level.groups] != [x.tolist() for x in plain.groups]
    for group, pool in zip(level.groups, _pools(df, eligible, all_)):
        assert set(group.tolist()) <= set(pool.tolist())
        assert group.tolist() == sorted(set(group.tolist()))
        assert not set(group.tolist()) & set(EVENTS.tolist())


def test_null_bar_with_nan_prior_atr_never_fills():
    df, atr, all_, eligible = _setup()
    bad = np.zeros(len(df), dtype=bool)
    bad[::3] = True
    atr = atr.mask(bad, np.nan)
    atr.iloc[1::9] = 0.0
    g = _groups(df, atr, all_, eligible, 5, depth=np.zeros(len(EVENTS)))
    a = atr.to_numpy()
    filled = np.concatenate(g.groups)
    assert np.isfinite(a[filled - 1]).all() and (a[filled - 1] > 0).all()
    plain = _groups(df, pd.Series(1.0, index=df.index), all_, eligible, 5)
    first = np.concatenate(plain.groups)
    assert (~np.isfinite(a[first - 1]) | (a[first - 1] <= 0)).any()     # non-vacuous


def test_event_with_no_fillable_null_drops_as_no_match():
    df, atr, all_, eligible = _setup()
    g = _groups(df, atr, all_, eligible, 20, depth=np.full(len(EVENTS), 50.0))
    pools = _pools(df, eligible, all_)
    assert g.groups == () and g.dropped_no_match == len(EVENTS)
    assert g.null_slots == sum(min(20, len(p)) for p in pools)
    assert g.null_unfilled == g.null_slots
    draw = null.matched_null(df, EVENTS, eligible, 20, SEED, cap=CAP, atr=atr, trend=all_,
                             slippage_bps=0.0, commission=0.0, direction="short",
                             depth=np.full(len(EVENTS), 50.0))
    assert draw.event_pos.size == 0 and len(draw.null_race) == 0
    assert draw.dropped_no_match == len(EVENTS)
    assert (draw.null_slots, draw.null_unfilled) == (g.null_slots, g.null_unfilled)


def test_pool_exhaustion_keeps_fewer_null_trades():
    df, atr, all_, eligible = _setup()
    g = _groups(df, atr, all_, eligible, 20, depth=np.full(len(EVENTS), 1.0))
    pools = _pools(df, eligible, all_)
    assert g.null_slots == sum(min(20, len(p)) for p in pools)
    assert g.null_unfilled == g.null_slots - sum(len(x) for x in g.groups)
    assert 0 < g.null_unfilled < g.null_slots
    assert any(len(x) < min(20, len(p)) for x, p in zip(g.groups, pools))


def test_null_depths_are_the_realised_depths_in_group_order():
    df, atr, all_, eligible = _setup()
    depth = np.array([0.25, 0.5, 0.75, 1.0])
    g = _groups(df, atr, all_, eligible, 5, depth=depth)
    kept = {int(p): d for p, d in zip(EVENTS, depth)}
    expected = [kept[int(p)] for p, grp in zip(g.event_pos, g.groups) for _ in grp]
    assert list(g.null_depths) == pytest.approx(expected, rel=1e-12)
    assert len(g.null_depths) == sum(len(x) for x in g.groups)


def test_depth_must_align_with_the_events():
    df, atr, all_, eligible = _setup()
    with pytest.raises(ValueError, match="depth"):
        _groups(df, atr, all_, eligible, 5, depth=np.zeros(len(EVENTS) - 1))


def _spy_race(monkeypatch):
    seen = []
    real_for = race_mod.race_for

    def race_for(shape):
        fn = real_for(shape)

        def spy(*args, **kwargs):
            seen.append(kwargs)
            return fn(*args, **kwargs)
        return spy

    monkeypatch.setattr(race_mod, "race_for", race_for)
    return seen


def test_level_matched_null_races_the_fills_with_the_level_factor(monkeypatch):
    df, atr, all_, eligible = _setup()
    seen = _spy_race(monkeypatch)
    depth = np.full(len(EVENTS), 0.5)
    g = _groups(df, atr, all_, eligible, 5, depth=depth)
    draw = null.matched_null(df, EVENTS, eligible, 5, SEED, cap=CAP, atr=atr, trend=all_,
                             slippage_bps=5.0, commission=0.0, direction="short",
                             depth=depth, level_factor=race_mod.REPRICE_SLIPPAGE_FACTOR)
    assert seen[-1]["fill"].tolist() == np.concatenate(g.fills).tolist()
    assert seen[-1]["level_factor"] == 3.0 and seen[-1]["direction"] == "short"
    expected = race_mod.race(df, np.concatenate(g.groups), CAP, atr=atr, slippage_bps=5.0,
                             commission=0.0, direction="short", fill=np.concatenate(g.fills),
                             level_factor=3.0)
    assert draw.null_race.r.tolist() == expected.r.tolist()
    assert (draw.null_slots, draw.null_unfilled, draw.null_depths) == (
        g.null_slots, g.null_unfilled, g.null_depths)
    null.matched_null(df, EVENTS, eligible, 5, SEED, cap=CAP, atr=atr, trend=all_,
                      slippage_bps=5.0, commission=0.0, direction="short")
    assert not ({"fill", "level_factor"} & set(seen[-1]))
```

Why these numbers: `random_walk` moves about 1.5 % a day on a price near 100, so with ATR fixed at 1.0 a depth of 1.0 leaves a fair share of first draws unfilled (Low not reaching Open − 1). That makes the replacement path and the short groups non-vacuous. A month holds about 21 eligible bars, so `k = 5` leaves a rest to draw replacements from, and `k = 20` exhausts the pool (`test_pool_exhaustion_keeps_fewer_null_trades`). `test_null_bar_with_nan_prior_atr_never_fills` uses depth 0 (every valid bar fills), so only the ATR rule can keep a bar out (Review Focus 1). `test_event_with_no_fillable_null_drops_as_no_match` is Review Focus 3.

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_null_level.py`
Expected: FAIL — `AttributeError: module ... null has no attribute 'LEVEL_STREAM'` / `'draw_groups'`, `matched_null() got an unexpected keyword argument 'depth'`.

- [ ] **Step 3: Implement in `swingbot/core/backtesting/screen/null.py`**

- Import `indicators` beside `race_mod` (`from swingbot.core.backtesting.screen import indicators, race as race_mod`).
- `LEVEL_STREAM = 1` after `SEED_BASE`, with the comment `# v182: the level null's replacement draws, never the position stream`.
- `child_seed(seed) -> list[int]`: `[*seed, LEVEL_STREAM]` for a list or tuple, `[int(seed), LEVEL_STREAM]` otherwise.
- `NullGroups` with the fields under **Interfaces**, in that order.
- `NullDraw`: append `null_slots: int = 0`, `null_unfilled: int = 0`, `null_depths: tuple = ()` after `dropped_no_match`. `_empty(dropped, slots=0, unfilled=0)` passes them through.
- `_null_fills(df, positions, d, atr_v, direction) -> tuple[np.ndarray, np.ndarray]`: the fill price per position and a boolean "filled" mask, by rule 3 above. Guard the `p − 1` read: positions at 0 are unfilled; `atr_v[p − 1]` not finite or ≤ 0 is unfilled (compute the level only where valid, so no NaN fill escapes). An unknown direction raises `ValueError` naming it.
- `_level_group(df, pool, m, first, d, atr_v, child, direction) -> tuple[np.ndarray, np.ndarray]`: rules 3–4 for one event; returns `(positions, fills)` sorted by position.
- `draw_groups(...)`:
  - `depth is None`: the loop of today's `matched_null` exactly (`rng = np.random.default_rng(seed)`, `months`, the `candidates` / `MIN_CANDIDATES` / `np.sort(rng.choice(...))` sequence). `null_slots` is the sum of the group sizes; `fills=None`, `null_unfilled=0`, `null_depths=()`.
  - `depth` given: `len(depth) != len(event_pos)` raises `ValueError("depth needs one value per event")`; `atr_v = (indicators.atr(df) if atr is None else pd.Series(atr)).to_numpy(dtype=float)`; the same `rng` and `months`; `child = np.random.default_rng(child_seed(seed))`; per event rules 1–5, with the first draw taken by `rng.choice(pool, size=m, replace=False)` **before** any fill check.
  - Keep `draw_groups` under complexity 15 by putting each mode in its own helper (`_draw_next_open(...)`, `_draw_level(...)`) behind one `if`.
- `matched_null(..., direction="long", depth=None, level_factor=race_mod.LEVEL_SLIPPAGE_FACTOR)`:
  - `race_fn = race_mod.race_for(shape)`;
  - `g = draw_groups(df, event_pos, eligible, k, seed, atr=atr, trend=trend, direction=direction, depth=depth)`;
  - no groups → `_empty(g.dropped_no_match, g.null_slots, g.null_unfilled)`;
  - `extra = {} if g.fills is None else {"fill": np.concatenate(g.fills), "level_factor": level_factor}`;
  - `raced = race_fn(df, np.concatenate(g.groups), cap, atr=atr, slippage_bps=slippage_bps, commission=commission, direction=direction, **extra)` (the V182-6 call plus `**extra`);
  - the means and the returned `NullDraw` as today, plus `g.null_slots`, `g.null_unfilled`, `g.null_depths`.
- Docstring: add a paragraph — `v182 level mode (depth=...): each event's null bars copy its fill depth d_e = (Open[t] - fill) / ATR14[t-1]: a null bar p fills at Open[p] - d_e x ATR14[p-1] (short; long mirror +) when its range reaches that level and ATR14[p-1] is finite and > 0. Unfilled first draws are replaced from the same pool on a child generator default_rng([*seed, LEVEL_STREAM]), so the position stream, and every next-open null, is unchanged. Slots left unfilled are counted (null_unfilled); an event with no filled null bar is dropped_no_match.`

- [ ] **Step 4: Run the tests to verify they pass, then the neighbours, the long goldens and the gate**

```bash
python scripts/dev/testrun.py file tests/backtesting/screen/test_null_level.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_null.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_race_level.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_idea.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_calibration_long_golden.py
python scripts/dev/complexity_gate.py
```

Expected: `0 failed` everywhere and no complexity regression. A red long golden here almost always means the next-open path now calls `rng` differently (for example `rng.choice` on a sorted copy, or `default_rng` created twice); `test_next_open_groups_keep_the_v140_draw_order` names the same fault in isolation.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/screen/null.py tests/backtesting/screen/test_null_level.py
git commit -m "feat(v182): level null -- copy each event's fill depth, replace on a child stream, count null_unfilled

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V182-11: Level threading in `screen_idea`: levels, entry date, depths, 3 × repricing

**Model:** opus — wires level mode through the one call site every book, null and stress run shares; the long and next-open paths must stay byte-identical while the level path gains its entry date, depths and repricing.

**Files:**
- Modify: `scripts/backtest/screen_idea.py` (`TickerScreen` :99-108, `_event_rows` :111-117, `_books` :128-145, `screen_ticker` :203-226, `_short_trade_line` (V182-6); new `raw_levels`, `_ENTRY_OFFSET`, `_event_depths`, `_repriced`, `_level_report`, `_short_level_line`)
- Modify: `swingbot/core/backtesting/screen/verdict.py` (the `PairedEvent.entry_date` comment at :34 only)
- Modify: `tests/backtest_scripts/test_screen_idea.py`

**Interfaces:**
- Consumes: `race.run_book(..., levels=, level_factor=)`, `race.level_fills`, `race.LEVEL_SLIPPAGE_FACTOR`, `race.REPRICE_SLIPPAGE_FACTOR` (V182-9); `null.matched_null(..., depth=, level_factor=)`, `NullDraw.null_slots`, `.null_unfilled`, `.null_depths` (V182-10); `Idea.entry`, `Idea.levels` (V182-3); `_books(..., direction=)`, `_short_trade_line(idea, costs)`, `_short_hypothesis(idea)`, `frictions.BORROW_RATE_ANNUAL` import (V182-6).
- Produces:
  - `raw_levels(idea, df) -> np.ndarray | None` — `None` unless `idea.entry == "level"`; else `idea.levels(df)` reindexed to `df.index`, as a float array (NaN where the idea has no level).
  - `_event_rows(ticker, index, kept, null_mean_r, entry_offset: int = 1) -> list` — `entry_date = index[pos + entry_offset]`; `_ENTRY_OFFSET = {"next_open": 1, "level": 0}`.
  - `_books(idea, ticker, df, ctx, costs, exclude=None, level_factor=race.LEVEL_SLIPPAGE_FACTOR)` — reads `ctx.get("levels")`. When it is `None`, the V182-6 calls are unchanged (no `levels=`, `depth=` or `level_factor=` keyword). Otherwise `run_book` gets `levels=` and `level_factor=`, and `matched_null` gets `depth=` (the booked events' depths) and `level_factor=`.
  - `TickerScreen` appended fields, in this order after `restricted`: `null_slots: int = 0`, `null_unfilled: int = 0`, `depths: dict | None = None` (`{"event": list[float], "null": list[float]}`, level only), `repriced: list | None = None` (level only; rows `{"entry_date", "r_event", "r_null"}` at `REPRICE_SLIPPAGE_FACTOR`).
  - `_repriced(idea, ticker, df, ctx, costs) -> list | None` — level only: `_books(..., level_factor=race.REPRICE_SLIPPAGE_FACTOR)`, rows as `_stressed` builds them, with `entry_offset=0`.
  - `_short_trade_line(idea, costs)` gains the level line (exact copy pinned below).
- Consumed by: V182-12 (the calibration's level replicate runs the real `screen_ticker`), V182-16 (`raw_levels`, `ctx["levels"]`), V182-17 (`TickerScreen.depths`, `.null_slots`, `.null_unfilled`, `.repriced` rendered in the short blocks).

`summarise`, `_render_head` and `render_results` do not change here: the 3 × and unfilled blocks are rendered by V182-17. `ctx` keeps every key it has today and gains `"levels"`. `_books` reads it with `.get`, so a `ctx` built elsewhere without the key is next-open.

- [ ] **Step 1: Write the failing tests** (append to `tests/backtest_scripts/test_screen_idea.py`, after the V182-6 short tests; `Idea`, `IDEAS`, `race_mod`, `null`, `ALWAYS`, `RUN_INFO`, `random_walk`, `_short_probe` are already imported or defined there)

```python
def _level_probe():
    """A short sell-stop half an ATR under the prior close, every 7th bar; never registered."""
    def levels(df):
        atr = screen_idea.indicators.atr(df)
        return df["Close"].shift(1) - 0.5 * atr.shift(1)

    def events(df):
        every = pd.Series(np.arange(len(df)) % 7 == 0, index=df.index)
        return (every & (df["Low"] < levels(df))).fillna(False)

    return Idea(name="level_probe", events=events, time_cap_bars=20, direction="short",
                entry="level", levels=levels, summary="probe", source="test")


def test_raw_levels_only_for_a_level_idea():
    df = random_walk(400)
    assert screen_idea.raw_levels(IDEAS["turn_of_month"], df) is None
    assert screen_idea.raw_levels(_short_probe(), df) is None
    probe = _level_probe()
    assert np.array_equal(screen_idea.raw_levels(probe, df),
                          probe.levels(df).to_numpy(dtype=float), equal_nan=True)


def test_event_rows_enter_on_the_event_bar_in_level_mode():
    index = pd.bdate_range("2015-01-05", periods=8)
    kept = race_mod.RaceResult(np.array([3]), np.array([5]), np.array([99.0]),
                               np.array([3.0]), np.array([0.5]), np.array([0.4]),
                               np.array(["timeout"]))
    level = screen_idea._event_rows("AAA", index, kept, [0.1], entry_offset=0)
    plain = screen_idea._event_rows("AAA", index, kept, [0.1])
    assert level[0]["entry_date"] == "2015-01-08" and plain[0]["entry_date"] == "2015-01-09"
    assert level[0]["exit_date"] == plain[0]["exit_date"] == "2015-01-12"


def test_a_level_screen_enters_on_the_event_bar():
    df = random_walk(2600)
    probe = _level_probe()
    out = screen_idea.screen_ticker(probe, "AAA", df, ALWAYS)
    assert out.events                                                  # non-vacuous
    event_days = set(df.index[probe.events(df).to_numpy()].strftime("%Y-%m-%d"))
    assert {row["entry_date"] for row in out.events} <= event_days


def test_a_level_screen_passes_levels_to_the_book_and_depth_to_the_null(monkeypatch):
    seen = {"book": [], "null": []}
    real_book, real_null = race_mod.run_book, null.matched_null

    def book_spy(*args, **kwargs):
        seen["book"].append(kwargs)
        return real_book(*args, **kwargs)

    def null_spy(*args, **kwargs):
        seen["null"].append((len(args[1]), kwargs))
        return real_null(*args, **kwargs)

    monkeypatch.setattr(race_mod, "run_book", book_spy)
    monkeypatch.setattr(null, "matched_null", null_spy)
    df = random_walk(2600)
    for idea in (IDEAS["turn_of_month"], _short_probe()):
        screen_idea.screen_ticker(idea, "AAA", df, ALWAYS)
    assert all(not ({"levels", "level_factor"} & set(kw)) for kw in seen["book"])
    assert all(not ({"depth", "level_factor"} & set(kw)) for _, kw in seen["null"])
    seen["book"].clear()
    seen["null"].clear()
    screen_idea.screen_ticker(_level_probe(), "AAA", df, ALWAYS)
    assert [kw["level_factor"] for kw in seen["book"]] == [2.0, 3.0]     # book, repriced
    assert seen["book"][0]["levels"] is not None
    for n_events, kw in seen["null"]:
        assert len(kw["depth"]) == n_events and kw["direction"] == "short"
    assert [kw["level_factor"] for _, kw in seen["null"]] == [2.0, 3.0]


def test_level_depths_slots_and_unfilled_are_reported():
    df = random_walk(2600)
    out = screen_idea.screen_ticker(_level_probe(), "AAA", df, ALWAYS)
    assert len(out.depths["event"]) == len(out.events)
    assert min(out.depths["event"]) >= 0.0
    assert len(out.depths["null"]) == sum(out.null_outcomes.values())
    assert out.null_slots > 0 and 0 <= out.null_unfilled <= out.null_slots
    plain = screen_idea.screen_ticker(_short_probe(), "AAA", df, ALWAYS)
    assert plain.depths is None and plain.repriced is None and plain.null_unfilled == 0


def test_the_repriced_book_is_the_same_events_at_three_times_slippage():
    df = random_walk(2600)
    out = screen_idea.screen_ticker(_level_probe(), "AAA", df, ALWAYS)
    assert [r["entry_date"] for r in out.repriced] == [r["entry_date"] for r in out.events]
    for at3, at2 in zip(out.repriced, out.events):
        assert at3["r_event"] < at2["r_event"] and at3["r_null"] < at2["r_null"]


def test_short_level_trade_line():
    assert screen_idea._render_trade(_level_probe(), RUN_INFO) == (
        "**Trade:** short; sell-stop resting at the level (known from bars <= t-1), placed "
        "before bar t opens, valid one bar; fills at the lower of the open and the level, "
        "entry slippage 2.0 x base; stop 1.5 x ATR14[t-1] above; target 3.0 x ATR14[t-1] "
        "below; on the fill bar only the stop counts (a high at or above it exits at the "
        "stop); from bar t+1 a gap through either level fills at the open; stop first on a "
        "bar touching both; borrow 0.5% a year on calendar days held; "
        "costs 5.0 bps a side + 0.0200R commission.")


def test_short_level_hypothesis():
    assert screen_idea.hypothesis(_level_probe()) == (
        "level_probe: probe; SHORT, sell-stop at the level, filled on the event bar, fixed "
        "1.5/3.0 ATR race vs K=20 matched null raced short, cap 20, borrow 0.5% a year, PIT "
        "S&P 500 2010-2019, after costs (v182 short screen)")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_idea.py`
Expected: FAIL — `AttributeError: module 'screen_idea' has no attribute 'raw_levels'`, `_event_rows() got an unexpected keyword argument 'entry_offset'`, the level probe still enters at the next open (entry-date test), and `TickerScreen` has no `depths`.

- [ ] **Step 3: Implement in `scripts/backtest/screen_idea.py`**

- `TickerScreen`: append the four fields under **Interfaces**, each with a `# v182:` comment (`level only` for `depths` and `repriced`).
- `_event_rows(ticker, index, kept, null_mean_r, entry_offset: int = 1)`: `index[pos + entry_offset]`; nothing else changes. Module constant `_ENTRY_OFFSET = {"next_open": 1, "level": 0}` beside it.
- `raw_levels(idea, df)` beside `raw_events`.
- `_event_depths(df, event_pos, ctx, direction) -> np.ndarray`: `race.level_fills(df, event_pos, ctx["levels"], ctx["atr"], direction)[1]`, or an empty float array for no events (`level_fills` needs at least one).
- `_books(..., exclude=None, level_factor=race.LEVEL_SLIPPAGE_FACTOR)`:
  - `levels = ctx.get("levels")`;
  - `book_kw = {} if levels is None else {"levels": levels, "level_factor": level_factor}`, splatted into the `race.run_book(...)` call beside `**costs`;
  - after the eligible mask: `null_kw = {} if levels is None else {"depth": _event_depths(df, booked.event_pos, ctx, idea.direction), "level_factor": level_factor}`, splatted into `null.matched_null(...)`;
  - the rest as today. The docstring gains: `v182: a level idea (ctx["levels"]) books and nulls in level mode at level_factor x base entry slippage.`
- `_repriced(idea, ticker, df, ctx, costs)`: `None` unless `idea.entry == "level"`; else `kept, _, draw = _books(idea, ticker, df, ctx, costs, level_factor=race.REPRICE_SLIPPAGE_FACTOR)` and the `_stressed` row shape from `_event_rows(ticker, df.index, kept, draw.null_mean_r, entry_offset=0)`. Docstring: the same events (exits, overlap and the seeded draw do not depend on slippage), repriced; printed, never gating.
- `_level_report(idea, ticker, df, ctx, costs, kept, draw) -> dict`: `{"null_slots": draw.null_slots, "null_unfilled": draw.null_unfilled, "depths": ..., "repriced": _repriced(...)}`; `depths` is `None` for a next-open idea, else `{"event": [float(x) for x in _event_depths(df, kept.event_pos, ctx, idea.direction)], "null": [float(x) for x in draw.null_depths]}`.
- `screen_ticker`:
  - `ctx` gains `"levels": raw_levels(idea, df)`;
  - `events=_event_rows(ticker, df.index, kept, draw.null_mean_r, entry_offset=_ENTRY_OFFSET[idea.entry])`;
  - the `TickerScreen(...)` call ends with `**_level_report(idea, ticker, df, ctx, costs, kept, draw)`.
  - Nothing else changes. `_stressed` (trail only) and `_restricted` (context only) never meet a level idea (`Idea` refuses level with trail; no context idea is level), so they keep the default offset.
- `_short_trade_line(idea, costs)`: first line `if idea.entry == "level": return _short_level_line(costs)`.
- `_short_level_line(costs: str) -> str`: the exact text the test pins, built from `race.LEVEL_SLIPPAGE_FACTOR`, `race.STOP_ATR`, `race.STOP_ATR * race.REWARD_RISK` and `f"borrow {BORROW_RATE_ANNUAL:.1%} a year on calendar days held; "`, then `costs`.
- `hypothesis` / `_short_hypothesis`: no change (V182-6 already maps `entry="level"` to `"sell-stop at the level, filled on the event bar"`; the test above pins it).
- Every function stays < 15 complexity. `screen_ticker` gains no branch: the level choices live in the helpers and `_ENTRY_OFFSET`.

`swingbot/core/backtesting/screen/verdict.py:34`: the comment becomes `# entry bar t+1 (frozen reading F9); v182 level mode: the event bar t`. No code change.

- [ ] **Step 4: Run the tests to verify they pass, then the neighbours, the long goldens and the gate**

```bash
python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_idea.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_verdict.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_context_runner.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_calibration_long_golden.py
python scripts/dev/complexity_gate.py
```

Expected: `0 failed` everywhere and no complexity regression. The existing pins `test_fixed_trade_line_is_unchanged`, `test_fixed_hypothesis_is_unchanged`, `test_a_fixed_idea_renders_its_results_doc_byte_identical_to_v140` and the V182-6 direction and borrow tests still pass untouched.

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/screen_idea.py swingbot/core/backtesting/screen/verdict.py tests/backtest_scripts/test_screen_idea.py
git commit -m "feat(v182): level threading in screen_idea -- event-bar entry date, fill depths, null_unfilled, 3 x repricing

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V182-12: Calibration level mode and the level A/A run

**Model:** sonnet — extends one script along the V182-7 pattern behind defaults the long golden pins, then a scripted run read against a fixed gate; the level race itself is V182-9..V182-11's.

**Files:**
- Modify: `scripts/backtest/screen_trail_calibration.py` (docstring, imports, constants, `ENABLED_ENTRIES`, `replicate`, `_render_head_short`; new `level_events`, `_replicate_idea`, `_race_paragraph`)
- Modify: `tests/backtest_scripts/test_screen_trail_calibration.py` (append; delete the two "until level mode lands" tests)
- Create: `docs/superpowers/results/<run-date>-short-level-race-calibration.md` (written by the script; `<run-date>` = the Berlin date of the run, ISO)

**Interfaces:**
- Consumes: `_idea(events, *, direction, entry, levels)`, `CAL_IDEA_NAMES`, `ENABLED_ENTRIES`, `doc_name`, `_mode_refusal`, `_render_head_short`, `_render_result_short`, `wilson_interval` (V182-7); the level race, null and threading through the real `screen_idea.screen_ticker` (V182-9..V182-11); `indicators.atr`.
- Produces:
  - `LEVEL_OFFSET_ATR = 0.5`; `LEVEL_RATE_SCALE = 2.5` (a level replicate draws bars at `2.5 × rate` and keeps only the ones whose order fills, so its event count stays near the next-open run's).
  - `level_events(df, rng, rate) -> tuple[pd.Series, pd.Series]` — `levels = Close[t−1] − LEVEL_OFFSET_ATR × ATR14[t−1]` (reads bars ≤ t−1 only); `events = random_events(df.index, rng, rate) & (Low < levels)` (NaN levels never fire). It consumes the rng exactly as `random_events` does (one `rng.random(len(index))` call), so every later ticker's frame is the long run's.
  - `ENABLED_ENTRIES = ("next_open", "level")`; `--entry level` runs (short only; `long` + `level` stays refused for good).
  - The committed level A/A doc (spec Part B item 4; gate: false passes ≤ 10 of 200, seeds 0..199). It gates every level-mode ledger row (V182-20).
- Consumed by: V182-18 (both A/A docs must be on disk before the counts run), V182-20.

The default long run and the short next-open run print exactly what they print after V182-7: the long golden and the V182-7 render tests prove it.

- [ ] **Step 1: Write the failing tests**

In `tests/backtest_scripts/test_screen_trail_calibration.py`, **delete** `test_a_replicate_refuses_level_until_level_mode_lands` and `test_short_level_is_refused_until_level_mode_lands` (V182-7 marked both for replacement). Keep `test_long_level_is_refused_for_good`. Append:

```python
from swingbot.core.backtesting.screen import indicators  # noqa: E402
from tests.backtesting.screen.helpers import assert_prefix_stable  # noqa: E402


def _synthetic(bars=400, seed=1):
    return cal.synthetic_frame(np.random.default_rng(seed), bars=bars)


def test_level_mode_is_enabled_and_its_constants_are_pinned():
    assert cal.ENABLED_ENTRIES == ("next_open", "level")
    assert cal.LEVEL_OFFSET_ATR == 0.5 and cal.LEVEL_RATE_SCALE == 2.5


def test_level_events_are_random_bars_whose_order_fills():
    df = _synthetic()
    events, levels = cal.level_events(df, np.random.default_rng(3), 0.3)
    draw = cal.random_events(df.index, np.random.default_rng(3), 0.3)
    expected = (df["Close"].shift(1) - 0.5 * indicators.atr(df).shift(1)).to_numpy()
    assert np.array_equal(levels.to_numpy(), expected, equal_nan=True)
    assert events.tolist() == (draw & (df["Low"] < levels)).tolist()
    assert 0 < events.sum() < draw.sum()                              # non-vacuous


def test_level_events_consume_the_rng_like_random_events():
    df = _synthetic()
    a, b = np.random.default_rng(5), np.random.default_rng(5)
    cal.level_events(df, a, 0.02)
    cal.random_events(df.index, b, 0.02)
    assert a.random() == b.random()


def test_levels_read_no_later_bar():
    df = _synthetic(bars=120)
    assert_prefix_stable(lambda d: cal.level_events(d, np.random.default_rng(0), 0.0)[1],
                         df, [30, 60, 90, 119])


def test_the_short_level_idea_is_fixed_cap_20_short_level():
    lv = pd.Series(1.0, index=EV.index)
    idea = cal._idea(EV, direction="short", entry="level", levels=lv)
    assert (idea.name, idea.time_cap_bars, idea.race_shape, idea.direction, idea.entry) == (
        "aa_short_level_calibration", 20, "fixed", "short", "level")
    assert idea.levels(None) is lv


def test_a_long_level_replicate_is_refused():
    with pytest.raises(ValueError):
        cal.replicate(1, tickers=1, n_resamples=100, direction="long", entry="level")


def test_a_short_level_replicate_races_level_mode(monkeypatch):
    seen = []
    real = cal.screen_idea.race.run_book

    def spy(*args, **kwargs):
        seen.append((kwargs.get("shape"), kwargs.get("direction"),
                     kwargs.get("levels") is not None))
        return real(*args, **kwargs)

    monkeypatch.setattr(cal.screen_idea.race, "run_book", spy)
    v = cal.replicate(5, tickers=1, n_resamples=100, direction="short", entry="level")
    assert isinstance(v, verdict.Verdict)
    assert seen and set(seen) == {("fixed", "short", True)}


def test_a_level_replicate_sees_the_long_replicates_frames(monkeypatch):
    seen = {"next_open": [], "level": []}
    real = cal.screen_idea.screen_ticker

    def spy(idea, name, df, spans, **kwargs):
        seen[idea.entry].append((name, df["Close"].to_numpy().copy()))
        return real(idea, name, df, spans, **kwargs)

    monkeypatch.setattr(cal.screen_idea, "screen_ticker", spy)
    cal.replicate(7, tickers=2, n_resamples=100)
    cal.replicate(7, tickers=2, n_resamples=100, direction="short", entry="level")
    assert len(seen["next_open"]) == len(seen["level"]) == 2
    for (n1, c1), (n2, c2) in zip(seen["next_open"], seen["level"]):
        assert n1 == n2 and np.array_equal(c1, c2)


def test_render_short_level_states_the_order_the_null_and_the_limit(monkeypatch):
    _fake_replicates(monkeypatch, FAKE)
    result = cal.calibrate(4, seed=0, direction="short", entry="level", **QUIET)
    params = {"replicates": 4, "seed": 0, "tickers": 2, "resamples": 200,
              "direction": "short", "entry": "level"}
    text = cal.render(result, params, "2026-10-21")
    assert text.startswith("# v182 short race A/A calibration (level entry) -> **over** "
                           "the 5% false-pass limit")
    for needle in ("§ Part B (calibration item 4)", "--direction short --entry level",
                   "sell-stop at Close[t-1] - 0.5 x ATR14[t-1]", "entry slippage 2.0 x base",
                   "only the stop counts on the fill bar", "copies each event's fill depth",
                   "probability 0.05", "borrow 0.5% a year", "10 of 200",
                   "cannot show that the depth-copy null is fair",
                   "| Wilson 95% interval of the false-pass rate | 4.6% .. 69.9% | reported, not gated |"):
        assert needle in text, needle


def test_a_short_level_run_writes_the_level_doc(tmp_path, monkeypatch):
    out_dir = tmp_path / "out"
    _fake_replicates(monkeypatch, [FAKE[1], FAKE[3]])
    argv = ["--direction", "short", "--entry", "level", "--replicates", "2", "--seed", "0",
            "--date", "2026-10-21", "--out-dir", str(out_dir)]
    assert cal.main(argv) == 0
    assert (out_dir / "2026-10-21-short-level-race-calibration.md").exists()
    assert not (out_dir / "2026-10-21-short-race-calibration.md").exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_trail_calibration.py`
Expected: FAIL — `AttributeError: module 'screen_trail_calibration' has no attribute 'level_events'` (and `LEVEL_OFFSET_ATR`), the level replicate refused with `ValueError`, and `main` exiting 2 on `--entry level`.

- [ ] **Step 3: Implement in `scripts/backtest/screen_trail_calibration.py`**

- Imports: `from swingbot.core.backtesting.screen import indicators, null, race, trail, verdict`.
- Constants beside `SHORT_CAP`: `LEVEL_OFFSET_ATR`, `LEVEL_RATE_SCALE` (values under **Interfaces**); `ENABLED_ENTRIES = ("next_open", "level")`.
- `level_events(df, rng, rate)` beside `random_events`, with the semantics under **Interfaces** (levels as a Series on `df.index`; `events` a bool Series, `Low < NaN` is `False`).
- `_replicate_idea(df, rng, rate, direction, entry) -> Idea`: next-open → `_idea(random_events(df.index, rng, rate), direction=direction, entry=entry)` (V182-7's call, unchanged); level → `events, levels = level_events(df, rng, rate * LEVEL_RATE_SCALE)` then `_idea(events, direction=direction, entry="level", levels=levels)`. `_idea` refuses `long` + `level`.
- `replicate(...)`: the per-ticker idea comes from `_replicate_idea(df, rng, rate, direction, entry)`. The rng calls keep their order (frame, then the one event draw). The `ENABLED_ENTRIES` refusal stays as V182-7 wrote it.
- `_render_head_short(result, params, day)`:
  - the **Spec** paragraph names `§ Part A (calibration item 2)` for next-open and `§ Part B (calibration item 4)` for level (`_SPEC_ITEMS = {"next_open": "§ Part A (calibration item 2)", "level": "§ Part B (calibration item 4)"}`);
  - the **Race** paragraph comes from `_race_paragraph(entry) -> str`. Next-open returns V182-7's text unchanged. Level returns:

```python
    (f"**Race:** the real `screen_ticker` with a fixed short level idea (cap {SHORT_CAP} bars; "
     f"a sell-stop at Close[t-1] - {LEVEL_OFFSET_ATR} x ATR14[t-1], placed before bar t opens "
     "and filled on bar t at the lower of the open and the level, entry slippage "
     f"{race.LEVEL_SLIPPAGE_FACTOR} x base; stop {race.STOP_ATR} x ATR14[t-1] above, target "
     f"{race.STOP_ATR * race.REWARD_RISK} x ATR14[t-1] below, only the stop counts on the fill "
     f"bar; borrow {BORROW_RATE_ANNUAL:.1%} a year on calendar days held) against a short "
     f"matched null that copies each event's fill depth (K = {null.K}, unfilled draws replaced "
     "on the child stream), pooled through the real `verdict.decide` (pass rule unchanged). "
     f"Events: a bar is drawn with probability {EVENT_RATE * LEVEL_RATE_SCALE:g} and is an "
     "event only when the order fills (Low[t] < level). Decision rule: false-pass rate "
     f"≤ {FALSE_PASS_MAX:.0%} (10 of 200 at the registered run); the Wilson 95% interval is "
     "printed, never gating. This A/A shows only that the level-mode code adds no false "
     "passes; it cannot show that the depth-copy null is fair to real events (check 5 on the "
     "real cache does that, for range_breakdown_stop).")
```

  (exact copy: the spec's own caveat for item 4).
- Docstring: add the usage line `python scripts/backtest/screen_trail_calibration.py --direction short --entry level --seed 0` and one sentence: v182 level mode races a short sell-stop half an ATR under the prior close, filled on the event bar, against the depth-copy null.
- Every function stays < 15 complexity.

- [ ] **Step 4: Run the tests, the long goldens and the gate, then smoke the level path**

```bash
python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_trail_calibration.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_calibration_long_golden.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py
python scripts/dev/complexity_gate.py
python scripts/backtest/screen_trail_calibration.py --direction short --entry level --replicates 2 --seed 0 --tickers 2 --resamples 200 --date 2026-10-21 --dry-run
```

Expected: `0 failed` everywhere, no complexity regression; the smoke prints a doc starting `# v182 short race A/A calibration (level entry) -> ...` with the Wilson row and seeds 0 and 1, and writes nothing.

- [ ] **Step 5: Commit the code**

```bash
git add scripts/backtest/screen_trail_calibration.py tests/backtest_scripts/test_screen_trail_calibration.py
git commit -m "feat(v182): calibration --entry level -- short sell-stop A/A on the depth-copy null

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Check the worktree is clean and fix the run date**

```bash
git status --short
python scripts/dev/testrun.py file tests/backtesting/screen/test_race_level.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_null_level.py
```

Expected: `git status --short` prints nothing; both files `0 failed`. Then run `date -u +%Y-%m-%dT%H:%M` and add 2 hours (Berlin summer time; Git Bash prints UTC even with `TZ` set). `<run-date>` is that Berlin day.

- [ ] **Step 7: Dispatch `backtest-runner` with the exact command**

Dispatch the `backtest-runner` agent, naming the worktree path `.claude/worktrees/2026-10-21-v182-short-screen-range-breakdown` and this command, run from that worktree's root:

```bash
python scripts/backtest/screen_trail_calibration.py --direction short --entry level --replicates 200 --seed 0 --tickers 24 --date <run-date>
```

The bootstrap stays at its default 10,000 week resamples. Progress prints to stderr every 10 replicates, so the runner can report percent on a run of 15 minutes or more. Ask it to return the exit code, the final stdout line (`false-pass k/200 = x%, coverage y% -> <path>`) and the doc's first 30 lines.

Expected: exit code 0 and the doc at `docs/superpowers/results/<run-date>-short-level-race-calibration.md`.

- [ ] **Step 8: Verify the doc and read the gate**

```bash
head -20 docs/superpowers/results/<run-date>-short-level-race-calibration.md
grep -c "^| [0-9]" docs/superpowers/results/<run-date>-short-level-race-calibration.md
grep -n "Wilson 95% interval\|mean kept events" docs/superpowers/results/<run-date>-short-level-race-calibration.md
grep -n "^| 0 |\|^| 199 |" docs/superpowers/results/<run-date>-short-level-race-calibration.md
```

Expected: the title reads `# v182 short race A/A calibration (level entry) -> within the 5% false-pass limit`; 200 per-replicate rows with seeds 0 and 199; the Wilson row; the **Run** paragraph names `--direction short --entry level --replicates 200 --seed 0 --tickers 24`.

- **k ≤ 10 (exit 0):** the gate holds; commit (Step 9). V182-18 may run once Part 4/5's code tasks are done.
- **k > 10 (exit 1, title says `**over**`):** the gate fails and no level-mode idea runs (spec: "If (4) fails: stop, fix, re-run"). Commit the doc anyway with the message suffix `-- OVER the limit` (a failed A/A is evidence). Tell the partner the count, the Wilson interval, the mean N and the ΔExpR spread. Diagnose with `superpowers:systematic-debugging`, checking first the fill-bar stop rule, the 2 × entry slippage applied to both sides, and the child-stream replacements. A fix is a new reviewed commit with its own regression test; then re-run Step 7 with the same seeds, overwrite the doc and commit again. `range_breakdown_close` (next-open) is not blocked by this gate.
- **Mean kept events N under 300:** most replicates are `SCREEN-UNDERPOWERED`, so a low false-pass count proves little. Report it to the partner before relying on the gate. Do not change `LEVEL_RATE_SCALE` after seeing a result without the partner's call.

- [ ] **Step 9: Commit the doc**

```bash
git add docs/superpowers/results/<run-date>-short-level-race-calibration.md
git commit -m "docs(v182): short level A/A calibration -- <k> of 200 false passes (gate <= 10)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Expected: one new commit holding only the results doc; `git status --short` is empty again.

