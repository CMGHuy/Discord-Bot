# v180 — Turtle Soup entry, part 2b: diagnostics sidecar and badge check

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Spec:** [2026-10-21-v180-turtle-soup-entry-design.md](../specs/2026-10-21-v180-turtle-soup-entry-design.md)
**Index:** [2026-10-21-v180-turtle-soup-entry_0-index.md](2026-10-21-v180-turtle-soup-entry_0-index.md) — Goal, Architecture, `## Global Constraints`, `## Contracts`, `## Parallelisation` and the task ledger live there and bind every task below.
**Brief:** `.superpowers/briefs/2026-10-21-v180-turtle-soup-entry.md`

Task V180-8 (split from part 2 for the 1500-line cap; V180-5..V180-7 are part 2a). Every task runs in the worktree `.claude/worktrees/2026-10-21-v180-turtle-soup-entry` (created in V180-1) and commits on its branch. All paths below are relative to that worktree. Run every command from the worktree root.

Part 1 creates the names these tasks consume: `TURTLE_SOUP`, `turtle_soup_signal`, `sweep_frame` (V180-1), `STRUCTURAL_DROP_STRATEGIES`, `PLAN_SHAPES[TURTLE_SOUP]`, `turtle_soup_rejection_reason`, `RISK_CAP`, `NO_LEVEL_IN_BAND`, `PLAN_OTHER` (V180-4), and `population_split` already exists in `acceptance.py`. Check each with `git grep -n` before starting a task; a missing one means its part-1 task has not merged into the branch yet, so stop.

## Review Focus

1. **A counted signal that the one-position slot swallows.** It has no engine event. The report must still list it, as `position_open`, never drop it. Test: `test_a_signal_inside_an_open_trade_is_listed_as_position_open` (V180-8).
2. **The membership file is missing.** The universe block must say `None` (unknown), never 0% outside the S&P 500. Test: `test_universe_share_is_unknown_without_membership_data` (V180-8).

---

# Phase D — the research cell and its diagnostics (continued)

### Task V180-8: Diagnostics sidecar and the stage-3 badge check

**Model:** opus — it joins the engine's events, the frozen screen race and the PIT membership into the spec's descriptive blocks. It also edits the producer script, whose one-shot stages must never turn a sidecar failure into a refusal or a traceback.

**Files:**
- Create: `swingbot/core/backtesting/arms/turtle_soup_report.py`
- Create: `scripts/backtest/turtle_soup_report.py`
- Create: `tests/backtesting/test_turtle_soup_report.py`
- Create: `tests/backtest_scripts/test_measure_arms_turtle_sidecar.py`
- Modify: `scripts/backtest/measure_arms.py` (module docstring; new `TURTLE_SOUP_KNOB`, `_sp500_intervals`, `_matches_component_rows`, `turtle_soup_sidecar` after `compression_sidecar` l.214; `_write_sidecar` l.~228; `_write_sidecar_or_warn` l.~233)

**Interfaces:**
- Consumes:
  - From V180-1: `TURTLE_SOUP`; `swingbot.core.market.turtle_soup.sweep_frame(df)` (columns `prior_low`, `age`, `signal`).
  - From V180-3: `shift_permutation.additive_added(baseline, component)` and `NotAdditive`.
  - From V180-4: `turtle_soup_plan.turtle_soup_rejection_reason(df, index, horizon_key, scan_params=None, level_map=None) -> str`, returning `"risk_cap"` / `"no_level_in_band"` / `"plan_other"`.
  - From V180-7: `turtle_soup_research` (`RESEARCH_KNOB`, `HORIZON`, the event shape), `StrategyEngine(strategies=(TURTLE_SOUP,)).turtle_soup_events`, and the test world in `tests/backtesting/test_turtle_soup_engine.py` (`path`, `FULL_PATH`, `SIGNAL_POS`, `SIGNAL_DAY`, `TARGET`, `PILOT`, `pin_world`).
  - Existing: `screen.race.race(df, event_pos, cap)` (fields `event_pos`, `r`, `outcome`; raises for a position with `pos + cap > n - 1`), `screen.ideas.turtle_soup.CAP` (10), `arm_rule.pooled_stats(trades)` (`n` = decided), `arm_rule.WR_FLOOR` (50.0), `arm_rule.MAX_SCRATCH_SHARE` (0.5), `acceptance.ArmTrade`, `acceptance.CLOSED`, `pit_membership.is_member(date, spans)`, `pit_membership.load_intervals(path)` (missing file → `{}`), `knobs.apply_knobs(delta)`, `market.indicators.atr(df, 14)` (causal Wilder ewm), `strategy_types.MIN_BARS`, `universe.UNIVERSE_DIR`, `config.MARKET_REGIME_TICKER`.
- Produces (V180-10..V180-13 read these files; no later code consumes them):
  - `turtle_soup_report`: `EARLY_STOP_SESSIONS = 2`, `SCREEN_CAP = 10`, `BADGE_MIN_N = 15`, `STATUSES` (the index tuple, in that order), and the index contract's functions with the shapes below.
  - `measure_arms.TURTLE_SOUP_KNOB = "TURTLE_SOUP_RESEARCH_MODE"` and `measure_arms.turtle_soup_sidecar(blob, delta, universe, spec) -> dict | None`, written to `<out stem>.turtle_soup.json`.
  - CLI `python scripts/backtest/turtle_soup_report.py --arms FILE [--out-json F] [--min-n 15]`. It prints `BADGE: PASS|FAIL`, exits 0 on any computed verdict, and exits 2 on `refused:malformed-arms` / `refused:not-additive`.

**Shapes (pinned by the tests below).**

- A **signal row** exists for each bar where `sweep_frame(df)["signal"]` is True and `window[0] <= signal_date <= window[1]`. It holds:
  - `ticker`, `signal_date` (ISO), `signal_index`, `prior_low` (L), `low` (Low[t]), `atr14` (`indicators.atr(df, 14)[t]`), and `sweep_depth_atr` = `(L − Low[t]) / ATR14[t]`;
  - `status`, one of `STATUSES`;
  - `screen_outcome` and `screen_r`: the screen race for that bar, or `None` when the race would read past the frame;
  - for a `trade`, every trade-event key from V180-7 (`entry_date` … `tp1`).
- **Status resolution** uses the engine's events, keyed by `(ticker, signal_date)`:
  - no event → `"position_open"` (a counted signal that the one-position slot swallowed);
  - `plan_none` → `turtle_soup_rejection_reason(df.iloc[:t + 1], t, horizon_key, scan_params=params)`, on the same bars the engine handed the constructor;
  - anything else → the event's own status.
  - A frame shorter than `MIN_BARS[horizon_key] + 10` returns no rows, because the engine never reads it.
- **Excluded-population race.** `screen_outcomes(df, positions)` races every position with `pos + SCREEN_CAP <= len(df) - 1` through the screen's own `race()`: screen ATR, the 1.5/3 bracket, screen costs. It returns `{pos: {"screen_outcome": str, "screen_r": float}}`. There is no overlap thinning: an excluded population was never traded, so each signal is raced on its own. Screen wins are `target` / `gap_target`, screen losses are `stop` / `gap_stop`, and `timeout` is neither.
- **Blocks.**
  - `drop_shares` → `{"signals": N, "by_status": {status: {"count", "share", "screen": {"raced", "expectancy_r", "win_rate", "outcomes"}}}}`, with every `STATUSES` key present. `share` is `count / N`, or None when N is 0.
  - `sweep_depth_summary` → `{"all", "kept", "dropped"}`, each `{"n", "mean", "p25", "median", "p75", "max"}`, with None values when empty. Kept = `trade`; dropped = the five `DROPPED_STATUSES`.
  - `exit_mix` → `{"n", "shares": {"target", "stop", "gap", "time_cap", "other"}, "win_rate"}` over trades.
  - `regime_split` → `{"above", "below", "unknown"}`, each `{"n", "expectancy_r", "win_rate"}` over trades, booked at `r_net`.
  - `clustering` → `{"days", "max", "p95"}` over all signal rows.
  - `universe_share` → `{"n", "outside_sp500", "share"}` over trades.
- Every share is a fraction in [0, 1]. Every win rate is a percent over decided trades, as in `acceptance.win_rate`.

- [ ] **Step 1: Write the failing report tests**

Create `tests/backtesting/test_turtle_soup_report.py`:

```python
"""V180-8: the Turtle Soup diagnostics. Signal rows join the engine's events (V180-7) with the sweep
geometry and the screen's own race; the blocks are descriptive and never gate. The world is V180-7's."""
import json

import numpy as np
import pytest

from swingbot.core.backtesting.acceptance import ArmTrade
from swingbot.core.backtesting.arms import turtle_soup_report as rep
from swingbot.core.backtesting.screen import race as screen_race
from swingbot.core.backtesting.screen.ideas import turtle_soup as screen_idea
from swingbot.core.market.indicators import atr
from swingbot.core.market.strategy_types import TURTLE_SOUP
from swingbot.scan_params import ScanParams
from tests.backtesting.test_turtle_soup_engine import (FULL_PATH, PILOT, SIGNAL_DAY, SIGNAL_POS, TARGET,
                                                        path, pin_world)
from tests.helpers import make_ohlcv

ALWAYS = {"TS1": [("2000-01-01", "9999-12-31")]}


@pytest.fixture(autouse=True)
def pins(monkeypatch):
    pin_world(monkeypatch)


def _params():
    return ScanParams.from_config()


def _measure(frame=FULL_PATH, intervals=ALWAYS, spy=None):
    return rep.measure({"TS1": frame}, PILOT, _params(), spy=spy, intervals=intervals)


def test_constants():
    assert (rep.EARLY_STOP_SESSIONS, rep.SCREEN_CAP, rep.BADGE_MIN_N) == (2, 10, 15)
    assert rep.SCREEN_CAP == screen_idea.CAP
    assert rep.STATUSES == ("trade", "risk_cap", "no_level_in_band", "plan_other",
                            "cancelled_open_through_stop", "cancelled_risk_cap_fill",
                            "not_triggered", "position_open")


def test_a_trade_row_carries_geometry_event_and_screen_race():
    measured = _measure()
    (row,) = measured["rows"]
    atr_t = float(atr(FULL_PATH.iloc[:SIGNAL_POS + 1], 14).iloc[-1])
    assert (row["ticker"], row["signal_date"], row["signal_index"], row["status"]) == \
        ("TS1", SIGNAL_DAY, SIGNAL_POS, "trade")
    assert (row["prior_low"], row["low"]) == (98.0, 97.6)
    assert row["atr14"] == pytest.approx(atr_t)
    assert row["sweep_depth_atr"] == pytest.approx((98.0 - 97.6) / atr_t)
    assert row["tp1"] == TARGET and row["exit_reason"] == "tp1" and row["r_net"] < row["r_gross"]
    raced = screen_race.race(FULL_PATH, [SIGNAL_POS], rep.SCREEN_CAP)
    assert row["screen_outcome"] == str(raced.outcome[0]) == "target"
    assert row["screen_r"] == pytest.approx(float(raced.r[0]))
    assert measured["signals"] == 1 and measured["trades"] == 1
    assert measured["exit_mix"] == {"n": 1, "win_rate": 100.0, "shares": {
        "target": 1.0, "stop": 0.0, "gap": 0.0, "time_cap": 0.0, "other": 0.0}}
    assert measured["early_stop_share"] == 0.0
    assert measured["universe"] == {"n": 1, "outside_sp500": 0, "share": 0.0}


def test_the_sidecar_record_is_json_serialisable():
    json.dumps(_measure())


def test_an_open_through_the_stop_is_listed_as_its_cancel():
    (row,) = _measure(frame=path(fill_open=97.0))["rows"]
    assert row["status"] == "cancelled_open_through_stop" and "entry_date" not in row


@pytest.mark.parametrize("resistances", [(), (110.0,)])
def test_a_plan_none_is_split_into_no_level_in_band(monkeypatch, resistances):
    pin_world(monkeypatch, resistances)
    (row,) = _measure()["rows"]
    assert row["status"] == "no_level_in_band"


def test_a_wide_sweep_stop_is_listed_as_risk_cap():
    frame = FULL_PATH.copy()
    frame.iloc[SIGNAL_POS, frame.columns.get_loc("Low")] = 96.0     # stop ~95.7: > 3% from the 99.9 close
    measured = _measure(frame=frame)
    (row,) = measured["rows"]
    assert row["status"] == "risk_cap"
    assert measured["drops"]["by_status"]["risk_cap"]["count"] == 1
    assert measured["drops"]["by_status"]["risk_cap"]["share"] == 1.0


def test_a_signal_inside_an_open_trade_is_listed_as_position_open():
    (row,) = rep.signal_rows("TS1", FULL_PATH, [], PILOT, params=_params())
    assert row["status"] == "position_open" and row["signal_date"] == SIGNAL_DAY


def test_signals_outside_the_window_and_short_frames_have_no_row():
    assert rep.signal_rows("TS1", FULL_PATH, [], ("2019-03-15", "2020-12-31"), params=_params()) == []
    assert rep.signal_rows("TS1", FULL_PATH.iloc[:29], [], PILOT, params=_params()) == []


def test_a_last_bar_signal_reads_no_later_bar():
    event = {"ticker": "TS1", "signal_date": SIGNAL_DAY, "status": "not_triggered"}
    (cut,) = rep.signal_rows("TS1", FULL_PATH.iloc[:SIGNAL_POS + 1], [event], PILOT, params=_params())
    (full,) = rep.signal_rows("TS1", FULL_PATH, [event], PILOT, params=_params())
    assert cut["status"] == "not_triggered"
    assert (cut["screen_outcome"], cut["screen_r"]) == (None, None)
    for key in ("prior_low", "low", "atr14", "sweep_depth_atr"):
        assert cut[key] == pytest.approx(full[key])


def test_screen_outcomes_skips_a_race_that_would_read_past_the_frame():
    assert set(rep.screen_outcomes(FULL_PATH, [SIGNAL_POS, len(FULL_PATH) - 3])) == {SIGNAL_POS}
    assert rep.screen_outcomes(FULL_PATH, []) == {}


def _row(status, depth=0.5, screen=(None, None), **extra):
    return {"ticker": extra.pop("ticker", "TS1"), "signal_date": extra.pop("signal_date", "2019-01-02"),
            "status": status, "sweep_depth_atr": depth,
            "screen_outcome": screen[0], "screen_r": screen[1], **extra}


def test_drop_shares_reports_every_status_with_its_screen_race():
    rows = [_row("trade", screen=("target", 1.9)), _row("risk_cap", screen=("stop", -1.03)),
            _row("risk_cap"), _row("no_level_in_band", screen=("timeout", 0.2))]
    drops = rep.drop_shares(rows)
    assert drops["signals"] == 4 and set(drops["by_status"]) == set(rep.STATUSES)
    assert drops["by_status"]["risk_cap"] == {"count": 2, "share": 0.5, "screen": {
        "raced": 1, "expectancy_r": pytest.approx(-1.03), "win_rate": 0.0, "outcomes": {"stop": 1}}}
    assert drops["by_status"]["no_level_in_band"]["screen"]["win_rate"] is None
    assert drops["by_status"]["plan_other"] == {"count": 0, "share": 0.0, "screen": {
        "raced": 0, "expectancy_r": None, "win_rate": None, "outcomes": {}}}
    assert rep.drop_shares([])["by_status"]["trade"]["share"] is None


def test_sweep_depth_splits_kept_and_dropped():
    rows = [_row("trade", 0.1), _row("trade", 0.3), _row("risk_cap", 1.0),
            _row("cancelled_risk_cap_fill", 2.0), _row("position_open", 9.0)]
    summary = rep.sweep_depth_summary(rows)
    assert summary["kept"]["n"] == 2 and summary["kept"]["mean"] == pytest.approx(0.2)
    assert summary["dropped"]["n"] == 2 and summary["dropped"]["max"] == 2.0
    assert summary["all"]["n"] == 5 and summary["all"]["median"] == pytest.approx(1.0)
    assert rep.sweep_depth_summary([])["kept"] == {
        "n": 0, "mean": None, "p25": None, "median": None, "p75": None, "max": None}


def _trade(reason, outcome, hold=4, r=1.0, **extra):
    return _row("trade", exit_reason=reason, outcome=outcome, hold_sessions=hold, r_net=r, **extra)


def test_early_stops_and_exit_mix():
    rows = [_trade("stop", "loss", hold=1, r=-1.0), _trade("gap_stop", "loss", hold=2, r=-1.4),
            _trade("stop", "loss", hold=3, r=-1.0), _trade("tp1", "win", r=1.8),
            _trade("time_exit", "timeout", hold=10, r=0.3), _trade("gap_target", "scratch", hold=1, r=0.0),
            _trade("acceptance_exit", "loss", hold=5, r=-0.6), _row("risk_cap")]
    assert rep.early_stop_share(rows) == pytest.approx(2 / 7)
    mix = rep.exit_mix(rows)
    assert mix["n"] == 7 and mix["win_rate"] == pytest.approx(100 * 1 / 5)
    assert mix["shares"] == pytest.approx(
        {"target": 1 / 7, "stop": 2 / 7, "gap": 2 / 7, "time_cap": 1 / 7, "other": 1 / 7})
    assert rep.early_stop_share([_row("risk_cap")]) is None
    assert rep.exit_mix([])["win_rate"] is None


def test_regime_split_reads_spy_against_its_200_day_sma_on_the_signal_day():
    spy = make_ohlcv([100.0] * 200 + [120.0] * 20 + [80.0] * 30, start="2018-01-02")

    def day(i):
        return spy.index[i].date().isoformat()

    rows = [_trade("tp1", "win", r=1.8, signal_date=day(205)),     # 120 > SMA200 100.6
            _trade("stop", "loss", r=-1.0, signal_date=day(240)),  # 80 < SMA200 99.9
            _trade("tp1", "win", r=2.0, signal_date=day(100))]     # SMA200 not warm yet
    split = rep.regime_split(rows, spy)
    assert split["above"] == {"n": 1, "expectancy_r": 1.8, "win_rate": 100.0}
    assert split["below"] == {"n": 1, "expectancy_r": -1.0, "win_rate": 0.0}
    assert split["unknown"]["n"] == 1
    assert rep.regime_split(rows, None)["unknown"]["n"] == 3


def test_clustering_counts_signals_per_day():
    rows = [_row("trade", signal_date="2019-01-02")] * 3 + [_row("risk_cap", signal_date="2019-01-03")]
    assert rep.clustering(rows) == {"days": 2, "max": 3, "p95": pytest.approx(float(np.percentile([3, 1], 95)))}
    assert rep.clustering([]) == {"days": 0, "max": 0, "p95": None}


def test_universe_share_counts_added_trades_outside_the_sp500():
    rows = [_trade("tp1", "win", ticker="TS1"), _trade("tp1", "win", ticker="ZZZ"), _row("risk_cap", ticker="ZZZ")]
    assert rep.universe_share(rows, ALWAYS) == {"n": 2, "outside_sp500": 1, "share": 0.5}


@pytest.mark.parametrize("intervals", [{}, None])
def test_universe_share_is_unknown_without_membership_data(intervals):
    rows = [_trade("tp1", "win")]
    assert rep.universe_share(rows, intervals) == {"n": 1, "outside_sp500": None, "share": None}


def _arm(outcomes):
    return [ArmTrade(f"T{i}", TURTLE_SOUP, "2w", "2024-03-01", outcome, r, 2.0, direction="bullish")
            for i, (outcome, r) in enumerate(outcomes)]


def test_badge_check_passes_on_the_floor():
    badge = rep.badge_check(_arm([("win", 1.8)] * 8 + [("loss", -1.0)] * 7))
    assert badge["verdict"] == "PASS" and badge["n"] == 15 and badge["min_n"] == 15
    assert badge["win_rate"] == pytest.approx(100 * 8 / 15)
    assert badge["clauses"] == {"win_rate": True, "expectancy_r": True, "n": True, "scratch_timeout_share": True}


@pytest.mark.parametrize("outcomes, failing", [
    ([("win", 1.8)] * 7 + [("loss", -1.0)] * 7, "n"),                              # 14 decided
    ([("win", 1.8)] * 7 + [("loss", -1.0)] * 8, "win_rate"),                       # 46.7%
    ([("win", 0.5)] * 8 + [("loss", -1.0)] * 7, "expectancy_r"),
    ([("win", 1.8)] * 8 + [("loss", -1.0)] * 7 + [("timeout", 0.1)] * 10 + [("scratch", 0.0)] * 6,
     "scratch_timeout_share"),                                                      # 16 of 31 closed
])
def test_badge_check_fails_each_clause(outcomes, failing):
    badge = rep.badge_check(_arm(outcomes))
    assert badge["verdict"] == "FAIL" and badge["clauses"][failing] is False


def test_badge_check_respects_min_n():
    assert rep.badge_check(_arm([("win", 1.8)] * 2 + [("loss", -1.0)]), min_n=3)["clauses"]["n"] is True
```

- [ ] **Step 2: Run the report tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_turtle_soup_report.py`
Expected: FAIL at collection with `ImportError: cannot import name 'turtle_soup_report'`.

- [ ] **Step 3: Create `swingbot/core/backtesting/arms/turtle_soup_report.py`**

Module docstring: v180's descriptive Turtle Soup diagnostics (spec § The funnel, "Reported at every stage that runs"). It joins `StrategyEngine.turtle_soup_events` with the live sweep geometry and the screen's own fixed race, and it scores the stage-3 badge on the added rows. Nothing here gates a stage, and the live bot reads none of it. A signal row reads the same bars up to `t` that the engine read.

Constants and imports:

```python
from collections import Counter

import numpy as np
import pandas as pd

from swingbot.core.backtesting import arm_rule
from swingbot.core.backtesting.acceptance import CLOSED
from swingbot.core.backtesting.arms import turtle_soup_research as tsr
from swingbot.core.backtesting.arms.knobs import apply_knobs
from swingbot.core.backtesting.screen.race import race
from swingbot.core.market.indicators import atr
from swingbot.core.market.strategy_types import MIN_BARS, TURTLE_SOUP
from swingbot.core.market.turtle_soup import sweep_frame
from swingbot.core.marketdata.pit_membership import is_member
from swingbot.core.planning.turtle_soup_plan import turtle_soup_rejection_reason

EARLY_STOP_SESSIONS = 2
SCREEN_CAP = 10            #: the screen's CAP (screen/ideas/turtle_soup.py), pinned equal by a test
BADGE_MIN_N = 15           #: backtest-methodology.md § Badge scoring, VALIDATION N
STATUSES = ("trade", "risk_cap", "no_level_in_band", "plan_other", "cancelled_open_through_stop",
            "cancelled_risk_cap_fill", "not_triggered", "position_open")
DROPPED_STATUSES = ("risk_cap", "no_level_in_band", "plan_other", "cancelled_open_through_stop",
                    "cancelled_risk_cap_fill")
#: Anything else (acceptance_exit, a data-end timeout) is "other".
EXIT_CATEGORIES = {"tp1": "target", "stop": "stop", "gap_stop": "gap", "gap_target": "gap",
                   "time_exit": "time_cap"}
SCREEN_WINS, SCREEN_LOSSES = ("target", "gap_target"), ("stop", "gap_stop")
_EVENT_BASE = ("ticker", "signal_date", "status")
```

Functions. The signatures come from the index contract. Each body is a few lines and stays far below complexity 15.

- `screen_outcomes(df, positions)`:
  - Keep the positions with `pos + SCREEN_CAP <= len(df) - 1`, and return `{}` when none are left.
  - Otherwise run `raced = race(df, kept, SCREEN_CAP)` and map each `int(raced.event_pos[i])` to `{"screen_outcome": str(raced.outcome[i]), "screen_r": float(raced.r[i])}`.
- `signal_rows(ticker, df, events, window, *, params, horizon_key=tsr.HORIZON)`:
  - return `[]` when `len(df) < MIN_BARS[horizon_key] + 10`;
  - compute `sweep = sweep_frame(df)` and `atr14 = atr(df, 14)`; the positions are the signal bars whose ISO date lies in `window`;
  - build `by_date = {e["signal_date"]: e for e in events if e["ticker"] == ticker}` and `screen = screen_outcomes(df, positions)`;
  - build one row per position with `_signal_row(ticker, df, pos, sweep, atr14, by_date, screen, params, horizon_key)`. Cast every value to a Python `int` / `float` / `str` so the record is JSON-serialisable.
- `_status(event, df, pos, horizon_key, params) -> str`: applies the status resolution above. `turtle_soup_rejection_reason` gets `df.iloc[:pos + 1]` and `pos`.
- `_signal_row(...)` returns the row shape above:
  - for a `trade`, merge in every event key that is not in `_EVENT_BASE`;
  - `screen_outcome` / `screen_r` are `None` when `pos` is not in `screen`.
- `_screen_summary(rows) -> dict` works over the rows with a non-None `screen_outcome` and returns:
  - `raced`;
  - `expectancy_r`: the mean `screen_r`, else None;
  - `win_rate`: 100 × wins / (wins + losses), counting `SCREEN_WINS` / `SCREEN_LOSSES`, or None when no race was decided;
  - `outcomes`: `dict(Counter(...))`.
- `drop_shares(rows)`: for each status in `STATUSES` (in order), give `count`, `share = count / len(rows)` (None when `rows` is empty), and `screen = _screen_summary(rows of that status)`.
- `_distribution(values) -> dict`: `n`, `mean`, `p25`, `median`, `p75` and `max`, computed with `np.percentile` / `np.mean` and cast to `float`. Every value is None when the input is empty.
- `sweep_depth_summary(rows)`: `_distribution` of `sweep_depth_atr` for all rows, for `status == "trade"`, and for `status in DROPPED_STATUSES`.
- `_trades(rows)`: the rows with `status == "trade"`.
- `_win_rate(rows) -> float | None`: the percent of `win` among rows with `outcome in ("win", "loss")`.
- `early_stop_share(rows)`: over trades, the fraction with `exit_reason in ("stop", "gap_stop")` and `hold_sessions <= EARLY_STOP_SESSIONS`. None when there is no trade.
- `exit_mix(rows)`:
  - `n`;
  - `shares` per category, from `EXIT_CATEGORIES.get(reason, "other")`. All five keys are present, 0.0 when a category is absent and 0.0 everywhere when there is no trade;
  - `win_rate = _win_rate(trades)`.
- `_cohort(rows) -> dict`: `{"n", "expectancy_r", "win_rate"}`. `expectancy_r` is the mean `r_net` over `outcome in CLOSED`, None when empty.
- `_regime_of(signal_date, close, sma) -> str`:
  - set `idx = close.index.searchsorted(pd.Timestamp(signal_date), side="right") - 1`;
  - return `"unknown"` when `idx < 0` or `sma.iloc[idx]` is NaN;
  - return `"above"` when `close.iloc[idx] > sma.iloc[idx]`, else `"below"`.
  - Only bars up to the signal day are read.
- `regime_split(rows, spy)`:
  - When `spy` is None, every trade is `"unknown"`.
  - Otherwise `close = spy["Close"]`, `sma = close.rolling(200, min_periods=200).mean()`, and `_cohort` per regime. All three keys are present.
- `clustering(rows)`: `Counter(row["signal_date"])` over all rows, returned as `{"days": len, "max": max or 0, "p95": float(np.percentile(counts, 95)) or None}`.
- `universe_share(rows, intervals)`, over trades:
  - `outside_sp500` and `share` are None when `not intervals` (a missing file gives `{}`; the caller may also pass None);
  - otherwise `outside = sum(not is_member(r["signal_date"], intervals.get(r["ticker"], [])))` and `share = outside / n` (None when there is no trade).
- `badge_check(trades, *, min_n=BADGE_MIN_N)`:
  - `stats = arm_rule.pooled_stats(trades)` (n = decided);
  - the clauses are `win_rate` (`>= arm_rule.WR_FLOOR`), `expectancy_r` (`> 0`), `n` (`>= min_n`) and `scratch_timeout_share` (`<= arm_rule.MAX_SCRATCH_SHARE`), each False on None;
  - return `{**stats, "min_n": min_n, "clauses": clauses, "verdict": "PASS" if all(clauses.values()) else "FAIL"}`.
  - Time-cap exits are `timeout` outcomes (V180-5), so they count against the scratch-and-timeout clause with no special handling.
- `measure(frames, window, params, *, spy, intervals)`:

```python
def measure(frames: dict, window, params, *, spy, intervals) -> dict:
    """Every block for one stage, through a Turtle-Soup-only engine (V180-7: the same rows as the
    component arm) under the structural knob."""
    from swingbot.core.backtesting.arms.strategy_engine import StrategyEngine
    rows: list[dict] = []
    with apply_knobs({tsr.RESEARCH_KNOB: "structural"}):
        for ticker in sorted(frames):
            engine = StrategyEngine(strategies=(TURTLE_SOUP,))
            list(engine.run_ticker(ticker, frames[ticker], (tsr.HORIZON,), window, params))
            rows += signal_rows(ticker, frames[ticker], engine.turtle_soup_events, window, params=params)
    return {"signal_window": list(window), "signals": len(rows), "trades": len(_trades(rows)),
            "drops": drop_shares(rows), "sweep_depth": sweep_depth_summary(rows),
            "early_stop_share": early_stop_share(rows), "exit_mix": exit_mix(rows),
            "regime": regime_split(rows, spy), "clustering": clustering(rows),
            "universe": universe_share(rows, intervals), "rows": rows}
```

`StrategyEngine` is imported inside `measure`, so this module never pulls in the engine at import time.

- [ ] **Step 4: Run the report tests**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_turtle_soup_report.py`
Expected: all green, 0 failed, 0 xfailed.

- [ ] **Step 5: Write the failing sidecar and CLI tests**

Create `tests/backtest_scripts/test_measure_arms_turtle_sidecar.py`:

```python
"""V180-8: measure_arms writes the Turtle Soup diagnostics beside the stamped arms as
<out stem>.turtle_soup.json, never touches the arm rows, and a sidecar failure only warns. The badge
CLI scores the added Turtle Soup rows of a stamped pair."""
import dataclasses
import json
import sys
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.backtesting.acceptance import ArmTrade
from swingbot.core.market.strategy_types import TURTLE_SOUP
from tests.backtesting.test_turtle_soup_engine import FULL_PATH, SIGNAL_DAY, pin_world

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import measure_arms as ma  # noqa: E402
import turtle_soup_report as cli  # noqa: E402

KNOB = "TURTLE_SOUP_RESEARCH_MODE"
ALWAYS = {"TS1": [("2000-01-01", "9999-12-31")]}


@pytest.fixture(autouse=True)
def world(monkeypatch):
    from swingbot.core.marketdata import training_data
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "yfinance")   # v162: no store in tests
    training_data.reset()
    pin_world(monkeypatch)
    monkeypatch.setattr(ma, "load_frame", lambda ticker: {"TS1": FULL_PATH}.get(ticker))
    monkeypatch.setattr(ma, "cached_universe", lambda: ["TS1"])
    monkeypatch.setattr(ma, "_sp500_intervals", lambda: ALWAYS)
    yield
    training_data.reset()


def _pilot_blob():
    return ma.produce("pilot", {KNOB: "structural"}, universe=["TS1"], horizons=("2w",),
                      engines=("strategy",), workers=1)


def test_the_knob_constant():
    assert ma.TURTLE_SOUP_KNOB == KNOB


def test_no_sidecar_without_the_knob():
    spec = ma.windows.resolve("pilot")
    assert ma.turtle_soup_sidecar({}, {"MIN_REWARD_PCT": 4.0}, ["TS1"], spec) is None
    assert ma.turtle_soup_sidecar({}, {KNOB: "off"}, ["TS1"], spec) is None


def test_the_sidecar_matches_the_stamped_component_rows():
    blob = _pilot_blob()
    side = ma.turtle_soup_sidecar(blob, {KNOB: "structural"}, ["TS1"], ma.windows.resolve("pilot"))
    assert side["knob_delta"] == {KNOB: "structural"} and side["universe_count"] == 1
    assert side["signals"] == 1 and side["trades"] == 1 and side["matches_component_rows"] is True
    assert [(r["ticker"], r["signal_date"], r["status"]) for r in side["rows"]] == [("TS1", SIGNAL_DAY, "trade")]
    assert side["regime"]["unknown"]["n"] == 1                       # no SPY frame in this world
    assert side["universe"] == {"n": 1, "outside_sp500": 0, "share": 0.0}


def test_a_stamped_row_the_sidecar_does_not_see_is_a_mismatch():
    blob = _pilot_blob()
    extra = dict(next(r for r in blob["component"] if r["strategy"] == TURTLE_SOUP), entry_date="2019-06-03")
    blob["component"].append(extra)
    side = ma.turtle_soup_sidecar(blob, {KNOB: "structural"}, ["TS1"], ma.windows.resolve("pilot"))
    assert side["matches_component_rows"] is False


def test_main_writes_the_turtle_sidecar_beside_untouched_arms(tmp_path):
    out = tmp_path / "v180-pilot-arms.json"
    assert ma.main(["--knob", f"{KNOB}=structural", "--stage", "pilot", "--out", str(out), "--workers", "1"]) == 0
    side = json.loads((tmp_path / "v180-pilot-arms.turtle_soup.json").read_text(encoding="utf-8"))
    assert side["trades"] == 1 and side["matches_component_rows"] is True
    assert not (tmp_path / "v180-pilot-arms.diagnostics.json").exists()      # compression knob off
    blob = json.loads(out.read_text(encoding="utf-8"))
    stamped = {f.name for f in dataclasses.fields(ArmTrade)}
    assert all(set(row) == stamped for row in blob["component"] + blob["baseline"])


def test_a_failing_turtle_sidecar_only_warns(monkeypatch, tmp_path, capsys):
    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(ma, "turtle_soup_sidecar", boom)
    out = tmp_path / "v180-pilot-arms.json"
    assert ma.main(["--knob", f"{KNOB}=structural", "--stage", "pilot", "--out", str(out), "--workers", "1"]) == 0
    assert "warning: turtle_soup sidecar not written (OSError: disk full)" in capsys.readouterr().err
    assert out.exists() and not (tmp_path / "v180-pilot-arms.turtle_soup.json").exists()


def _row(ticker, outcome, r, strategy=TURTLE_SOUP):
    return dataclasses.asdict(ArmTrade(ticker, strategy, "2w", "2024-03-01", outcome, r, 2.0,
                                       direction="bullish"))


def _arms(tmp_path, added, baseline=None):
    baseline = baseline if baseline is not None else [_row("B0", "win", 1.0, strategy="RSI")]
    path = tmp_path / "arms.json"
    path.write_text(json.dumps({"provenance": {"stage": "validation"}, "baseline": baseline,
                                "component": baseline + added}), encoding="utf-8")
    return path


def test_the_badge_cli_scores_only_the_added_turtle_rows(tmp_path, capsys):
    added = [_row(f"W{i}", "win", 1.8) for i in range(8)] + [_row(f"L{i}", "loss", -1.0) for i in range(7)]
    out_json = tmp_path / "badge.json"
    assert cli.main(["--arms", str(_arms(tmp_path, added)), "--out-json", str(out_json)]) == 0
    assert "BADGE: PASS" in capsys.readouterr().out
    badge = json.loads(out_json.read_text(encoding="utf-8"))
    assert badge["n"] == 15 and badge["verdict"] == "PASS" and badge["stage"] == "validation"


def test_the_badge_cli_reports_a_fail_with_exit_zero(tmp_path, capsys):
    added = [_row(f"W{i}", "win", 1.8) for i in range(3)]
    assert cli.main(["--arms", str(_arms(tmp_path, added))]) == 0
    assert "BADGE: FAIL" in capsys.readouterr().out


def test_the_badge_cli_refuses_a_pair_that_is_not_additive(tmp_path, capsys):
    path = tmp_path / "arms.json"
    path.write_text(json.dumps({"provenance": {}, "baseline": [_row("B0", "win", 1.0, strategy="RSI")],
                                "component": []}), encoding="utf-8")
    assert cli.main(["--arms", str(path)]) == 2
    assert "refused:not-additive" in capsys.readouterr().err


def test_the_badge_cli_refuses_malformed_arms(tmp_path, capsys):
    path = tmp_path / "arms.json"
    path.write_text("{}", encoding="utf-8")
    assert cli.main(["--arms", str(path)]) == 2
    assert "refused:malformed-arms" in capsys.readouterr().err
```

- [ ] **Step 6: Run the sidecar tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_arms_turtle_sidecar.py`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'turtle_soup_report'`.

- [ ] **Step 7: Wire `scripts/backtest/measure_arms.py`**

1. Module docstring: add the line `v180: --knob TURTLE_SOUP_RESEARCH_MODE=structural also writes <out stem>.turtle_soup.json (see turtle_soup_sidecar).`
2. After `compression_sidecar`:

```python
TURTLE_SOUP_KNOB = "TURTLE_SOUP_RESEARCH_MODE"


def _sp500_intervals() -> dict:
    """The PIT S&P 500 membership spans; {} when the file is missing (the universe block then says None)."""
    from swingbot.core.marketdata import universe as universe_mod
    from swingbot.core.marketdata.pit_membership import load_intervals
    return load_intervals(str(Path(universe_mod.UNIVERSE_DIR) / "sp500_membership.csv"))


def _matches_component_rows(rows, blob, spec) -> bool:
    """The sidecar's trades are exactly the stamped component's Turtle Soup rows, by (ticker, signal date)."""
    from swingbot.core.market.strategy_types import TURTLE_SOUP
    if "component" in blob:
        component, spans = blob["component"], [tuple(spec.signal_window)]
    else:
        component = [row for fold in blob.get(spec.fold_key) or [] for row in fold["component"]]
        spans = [(start, end) for _, start, end in spec.folds]
    stamped = sorted((r["ticker"], r["entry_date"]) for r in component if r["strategy"] == TURTLE_SOUP)
    traded = sorted((r["ticker"], r["signal_date"]) for r in rows
                    if r["status"] == "trade" and any(s <= r["signal_date"] <= e for s, e in spans))
    return stamped == traded
```

3. `turtle_soup_sidecar(blob, delta, universe, spec) -> dict | None`.
   - Docstring: v180's descriptive diagnostics, replayed through a Turtle-Soup-only `StrategyEngine` under the same delta. The stamped arm rows are never touched. None without the knob.
   - Body:
     - return None when `delta.get(TURTLE_SOUP_KNOB) in (None, "off")`;
     - load `frames` for `universe` with `load_frame`, skipping None;
     - `spy = load_frame(config.MARKET_REGIME_TICKER)`;
     - under `apply_knobs(delta)`, call `turtle_soup_report.measure(frames, spec.signal_window, ScanParams.from_config(), spy=spy, intervals=_sp500_intervals())`;
     - then add `knob_delta` (`dict(delta)`), `universe_count` (`len(universe)`) and `matches_component_rows` (`_matches_component_rows(measured["rows"], blob, spec)`).
   - Import `config`, `ScanParams`, `apply_knobs` and `turtle_soup_report` inside the function, as `compression_sidecar` does.
4. Replace `_write_sidecar` / `_write_sidecar_or_warn`. The compression file name and the warning text stay byte-identical, so `test_measure_compression_short.py` (which monkeypatches `_write_sidecar` and greps `warning: diagnostics sidecar not written`) passes unmodified:

```python
#: (file suffix, builder name) per sidecar; looked up by name so a test can monkeypatch the builder.
_SIDECARS = (("diagnostics", "compression_sidecar"), ("turtle_soup", "turtle_soup_sidecar"))


def _write_sidecar(out: Path, sidecar, suffix: str = "diagnostics") -> None:
    if sidecar is not None:
        out.with_name(f"{out.stem}.{suffix}.json").write_text(json.dumps(sidecar), encoding="utf-8")


def _write_sidecar_or_warn(out: Path, blob, delta, universe, spec) -> None:
    """Each sidecar is diagnostics only: a failure here warns and never pre-empts the zero-diff refusal
    (or turns a spent one-shot stage into a traceback that invites a re-run)."""
    for suffix, builder in _SIDECARS:
        try:
            sidecar = globals()[builder](blob, delta, universe, spec)
            if sidecar is not None:
                _write_sidecar(out, sidecar, suffix)
        except Exception as exc:    # noqa: BLE001
            print(f"warning: {suffix} sidecar not written ({type(exc).__name__}: {exc}); the arm file is intact.",
                  file=sys.stderr)
```

`main` is not edited: it already calls `_write_sidecar_or_warn` after writing the arms and before the zero-diff refusal.

- [ ] **Step 8: Create `scripts/backtest/turtle_soup_report.py`**

```python
#!/usr/bin/env python3
"""v180 stage-3 badge check: score the Turtle Soup rows a stamped arm pair adds on the badge floor
(backtest-methodology.md § Badge scoring): win_rate >= 50 over win+loss, expectancy_r > 0, N >= 15,
scratches + timeouts <= 50% of closed. Descriptive output for the record; the verdict is the gate's."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from swingbot.core.backtesting.acceptance import ArmTrade  # noqa: E402
from swingbot.core.backtesting.arms import turtle_soup_report as rep  # noqa: E402
from swingbot.core.backtesting.arms.shift_permutation import NotAdditive, additive_added  # noqa: E402
from swingbot.core.market.strategy_types import TURTLE_SOUP  # noqa: E402
```

Functions:

- `_parser() -> argparse.ArgumentParser`: `--arms` (required, `Path`), `--out-json` (`Path`, default None), `--min-n` (`int`, default `rep.BADGE_MIN_N`).
- `_load(path) -> tuple[dict, list, list] | None`: read the blob and build `ArmTrade(**row)` for `baseline` and `component`. On `OSError`, `ValueError`, `TypeError` or `KeyError`, print `refused:malformed-arms -- <exc>` to stderr and return None.
- `main(argv=None) -> int`:
  - parse, then `_load`; on None, return 2;
  - `added = [t for t in additive_added(baseline, component) if t.strategy == TURTLE_SOUP]`. On `NotAdditive`, print `refused:not-additive -- <exc>` to stderr and return 2;
  - `badge = {**rep.badge_check(added, min_n=args.min_n), "arms": str(args.arms), "stage": blob.get("provenance", {}).get("stage")}`;
  - print `BADGE: <verdict>`, then one line per clause (`  <clause>: ok|FAIL`), then one line `n=<n> win_rate=<..> expectancy_r=<..> scratch_timeout_share=<..>`;
  - when `--out-json` is given, create its parent and write `badge` there as JSON;
  - return 0.
- `if __name__ == "__main__": sys.exit(main())`.

- [ ] **Step 9: Run the tests**

```bash
python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_arms_turtle_sidecar.py
python scripts/dev/testrun.py file tests/backtesting/test_turtle_soup_report.py
python scripts/dev/testrun.py file tests/backtesting/test_measure_compression_short.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_arms.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_arms_record_blocked.py
python scripts/dev/testrun.py file tests/backtesting/test_turtle_soup_engine.py
python scripts/dev/complexity_gate.py
```

Expected:

- All green, 0 failed, 0 xfailed.
- The compression and measure_arms test files pass unmodified. The `.diagnostics.json` name and the `warning: diagnostics sidecar not written` text are unchanged.
- The complexity gate reports no new function at or above 15.

- [ ] **Step 10: Commit**

```bash
git add swingbot/core/backtesting/arms/turtle_soup_report.py scripts/backtest/turtle_soup_report.py scripts/backtest/measure_arms.py tests/backtesting/test_turtle_soup_report.py tests/backtest_scripts/test_measure_arms_turtle_sidecar.py
git commit -m "feat(v180): Turtle Soup diagnostics sidecar beside the stamped arms, and the stage-3 badge check CLI" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
