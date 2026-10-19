# v173 Execution fidelity, part 3: replay statuses and data admission

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task with `grep -n "^### Task V173-9:" -A 800 <this file>`; never read the file whole.

**Spec:** [`docs/superpowers/specs/2026-10-18-v173-execution-fidelity-overrides-design.md`](../specs/2026-10-18-v173-execution-fidelity-overrides-design.md) §3 (rows and statuses, the session table) and `## Plan panel review` (unstamped rows, stale `bar_close` stamps, the before-costs delta, trimming to `asof`, calendar gaps, the adjustment basis)
**Bump:** bot minor; ui minor (applied once, in V173-17)
**Edge:** none (integrity)
**Index:** [`2026-10-18-v173-execution-fidelity-overrides_0-index.md`](2026-10-18-v173-execution-fidelity-overrides_0-index.md) carries the Goal, `## Global Constraints`, `## Parallelisation`, `## Where to work` (`$WT`, `$R`), the task ledger, `## Handoff` and `## Revision 2026-10-19`. Every task below implicitly includes those Global Constraints, in particular **Stamp kinds**, **Data admission**, **Actual exit price**, **Replay, two frames, no lookahead**, **Status precedence** and **One cost basis**.

Tasks: V173-9, then V173-22 (both edit `swingbot/core/analytics/override_fidelity.py`). V173-9 needs V173-6 (`fill_bar_exit`, `ExitResult.tp1_index`), V173-21 (`walk_v2(..., indicator_df=)`), V173-7 and V173-8 committed on the branch first. Part 3b (`_3b-verdict.md`) continues with V173-23 and V173-10.

**What earlier tasks created, per the index ledger** (check each with `git -C $WT grep -n "<name>" swingbot/core/analytics/override_fidelity.py` before starting; a missing one means an earlier task is not merged into the branch yet: stop and report, never re-create it here):

- V173-7: constants `MANUAL_REASONS`, `STATUSES` (eight, with `unstamped`), `EXCLUDED_STATUSES` (six, with `unstamped`), `TIMEOUT_REASONS`, `DEAD_BAND`, `VERDICT_FLOOR`, `WEEK_FLOOR`, `EXCLUDED_CAP`, `SPLIT_TOLERANCE`, `LEDGER_ID`; `SessionHit(session: date, price_kind: str)`; `assign_session(at_iso)`; `latest_completed_session(now)`; `session_index(df, day) -> int | None`; `transition_at(plan, status) -> str | None`; `override_entry(plan) -> dict | None`; `is_override(plan) -> bool`; `state_at_close(plan) -> "PARTIAL" | "ACTIVE"`; `stamp_kind(entry) -> "missing" | "failed" | "stamped"`; the frozen dataclass `OverrideRow` (the 20 row fields, `delta_r_gross` after `delta_r`; property `entry_date`; `to_dict()`); `ROW_FIELDS`; `outcome_of(delta_r) -> "helped" | "hurt" | "neutral" | None`. The module imports `datetime as dt`, `pandas as pd`, `PlanStatus`, and has `from __future__ import annotations`.
- V173-8: `INSTRUMENT`, `GROSS_COST_MODEL`, `hold_cap_bars(plan)`, `engine_frame(df, ov_idx)`, `engine_path(plan, df, fill_idx, *, indicator_df=None) -> ExitResult` (fill-bar check first, then `walk_v2`), `leg_kind(reason)`, `live_tp1_leg(plan)`, `actual_r(plan, exit_price, state, *, cost_model=None)`, `engine_r(plan, result, state, *, cost_model=None)`, `dollar_risk(plan, trade)`, `to_usd(r, risk)`; the module imports `ExitResult`.

**Tests never touch a database** (Global Constraints): plain `TradePlanV2` objects and synthetic frames on real NYSE session dates. No `seed_store`, no `db_conn`, never the production replica.

# Phase: Statuses and data admission (V173-9, V173-22)

### Task V173-9: `replay_override`: actual exit price and the eight statuses

**Model:** opus — no-lookahead replay, status precedence feeds the verdict

**Files:**
- Modify: `swingbot/core/analytics/override_fidelity.py` (append a V173-9 section after V173-8's arms; created by V173-7, extended by V173-8)
- Create: `tests/analytics/test_override_fidelity_replay.py`

**Interfaces:**
- Consumes (V173-7): `SessionHit`, `assign_session`, `session_index`, `transition_at`, `override_entry`, `state_at_close`, `stamp_kind`, `OverrideRow`, `outcome_of`, `TIMEOUT_REASONS`, `SPLIT_TOLERANCE`. (V173-8): `INSTRUMENT`, `GROSS_COST_MODEL`, `hold_cap_bars`, `engine_frame`, `engine_path(..., *, indicator_df=None)`, `leg_kind`, `actual_r(..., *, cost_model=None)`, `engine_r(..., *, cost_model=None)`, `dollar_risk`, `to_usd`. (V173-6): `ExitResult.tp1_index`. (V173-21): `walk_v2(..., indicator_df=)`, reached through `engine_path`.
- Produces: `actual_exit(plan, df: pd.DataFrame | None, hit: SessionHit | None) -> tuple[float | None, str, bool]`, i.e. `(price, price_source, approx)`; `replay_override(plan, bars: pd.DataFrame | None, asof: date, trade: dict | None = None) -> OverrideRow`. Private helpers later tasks replace or call by name: `_Replay` (fields `df, fill_idx, ov_idx, state, price, price_source, approx, actual_r`), `_split_band(plan, df, fill_idx) -> bool`, `_admission(plan, rp, asof) -> str | None` (replaced by V173-22), `_parity_broken`, `_ambiguous`, `_engine_arm(plan, rp) -> ExitResult`, `_still_open`, `_status(plan, rp, asof) -> tuple[str, ExitResult | None]` (replaced by V173-23), `replay_override` (its first lines replaced by V173-22). V173-10's `build_report` calls `replay_override` once per override plan.

**Decisions this task makes inside the index's status precedence** (each has a test below; none changes a shared contract):

1. **`unstamped` is decided before anything else is read.** An individual close (`reason == "manual"`) whose stamp kind is `"failed"` (`override: null`, or `price_source == "none"`) is `unstamped` even with no bars or no ACTIVE entry: the row exists to be counted against the 20% cap, and a failed stamp says nothing about the replay. It carries `approx=False`, `price_source="none"` and every R and $ field `None`. A bulk close with a failed stamp is not `unstamped`: it falls through to the session-bar path (`approx=True`) like a pre-v173 close, because bulk rows are never in the verdict population anyway.
2. **`unreplayable` before the bars are judged** covers: not a manual close, an unreadable `at`, no `entry_price`/`stop_loss`, no or empty bars, no fill session in the bars, no actual exit price (a pre-v173 row whose override session is missing from the bars), and `costs.book` refusing the actual arm. A *stamped* row whose override session is missing is judged by `_admission`; after V173-22 that is `stale` (a calendar gap), which V173-22 tests.
3. **A `bar_close` stamp is approx when its `bars_asof` is before the close session date, or unknown.** The price stays the stamp's (`price_source="bar_close"`); only the flag changes, so the row is shown and never summed. A `quote` stamp is never approx, whatever its `bars_asof`.
4. **Ambiguous on any TP1 at the override session**, ACTIVE or PARTIAL. For a PARTIAL plan whose live TP1 and manual close fall on the same session, the engine frame would clamp the TP1 bar's high and lose the very TP1 the live plan took, so that row is also `ambiguous` (index § Handoff).
5. **Non-resolved rows carry no engine figures:** `engine_r`, `delta_r`, `delta_r_gross`, `engine_usd`, `delta_usd`, `engine_exit_reason` and `outcome` are `None` unless `status == "resolved"`. `actual_r`/`actual_usd` are filled whenever the actual arm could be booked (shown in the table, summed only for counted rows). `delta_r_gross` is filled on every row that has a `delta_r`: the same two `costs.book` calls with `GROSS_COST_MODEL`, descriptive only.
6. **The engine arm is walked on `engine_frame(df, ov_idx)` with `indicator_df=df`** (Global Constraints, revised 2026-10-19): ATR and structure read the real bars, the exit checks see the clamped override bar. On a runner plan the real override bar's range therefore feeds the trail's ATR on later bars, as it did live: past data at those bars, not lookahead. So "moving the override bar's high/low never moves a resolved row's `engine_r`" is pinned on a pre-TP1 single-leg path only, the same way the index § Handoff pins the pre-fill invariance on single-leg plans.
7. **`close_date`** is the override session (`assign_session(<CLOSED at>).session`), so a weekend close dates to Friday; `None` only when `at` is unreadable.

- [ ] **Step 1: Write the failing test**

Create `$WT/tests/analytics/test_override_fidelity_replay.py`:

```python
"""v173 §3: replay_override -- the actual exit price and the eight statuses.

Frames sit on real NYSE sessions from 2026-09-14: 15 warm-up bars, the fill
bar at index 15 (Mon 2026-10-05), the override session at index 17 (Wed
2026-10-07). Bullish plans enter at 100 with the stop at 95 and TP1 at 110;
the breakeven trigger is 105; the hold cap is 8 bars, so a full 26-bar frame
(last bar Mon 2026-10-19) times out at index 23. Expected R figures are booked
here through the same costs.book call, so the tests pin the wiring, not the
engine's arithmetic (V173-8's arms tests pin that).
"""
from datetime import date, timedelta

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.analytics import override_fidelity as of
from swingbot.core.backtesting.instrument import costs
from swingbot.core.market.session import nyse_calendar
from swingbot.core.planning.exit_sim import runner_floor
from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults

START = date(2026, 9, 14)
FILL_IDX, OV_IDX = 15, 17
FILL_AT = "2026-10-05T14:00:00+00:00"      # Mon 10:00 ET -> index 15
PARTIAL_AT = "2026-10-06T15:00:00+00:00"   # Tue 11:00 ET -> index 16
CLOSE_AT = "2026-10-07T18:00:00+00:00"     # Wed 14:00 ET -> index 17
CLOSE_DAY = date(2026, 10, 7)
LAST_DAY = date(2026, 10, 19)              # index 25 of a full frame
WARM = (100.0, 100.5, 99.5, 100.0)
FILL_BAR = (100.0, 101.0, 99.0, 100.0)
FLAT = (101.0, 102.0, 100.0, 101.0)        # below the 105 breakeven trigger
TP1_BAR = (104.0, 111.0, 103.0, 108.0)
RUNNER_HOLD = (108.0, 108.5, 107.0, 107.5)  # above the runner floor
STOP_BAR = (101.0, 102.0, 94.0, 95.0)
FLOOR = runner_floor(100.0, 110.0)           # 106.667
_STAMPED = object()
UNSTAMPED = object()                          # no `override` key: a pre-v173 close
NO_FIGURES = ("engine_r", "delta_r", "delta_r_gross", "engine_usd", "delta_usd",
              "engine_exit_reason", "outcome")


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    """Code defaults, with the exit flags that would add paths held off."""
    pin_code_defaults(monkeypatch)
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", False)
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "off")
    monkeypatch.setattr(config, "ADAPTIVE_RUNNER_TRAIL_ENABLED", False)


def stamp(price=102.0, source="quote", bars_asof="2026-10-06"):
    return {"exit_price": price, "price_source": source,
            "quote_ts": CLOSE_AT if source == "quote" else None, "bars_asof": bars_asof}


def plan(*, partial=False, reason="manual", override=_STAMPED, fill_at=FILL_AT,
         partial_at=PARTIAL_AT, close_at=CLOSE_AT, **kw) -> TradePlanV2:
    history = [] if fill_at is None else [
        {"status": "ACTIVE", "reason": "filled", "at": fill_at}]
    legs = []
    if partial:
        history.append({"status": "PARTIAL", "reason": "tp1_partial", "at": partial_at})
        legs = [{"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1",
                 "closed_at": partial_at}]
    closed = {"status": "CLOSED", "reason": reason, "at": close_at}
    if override is _STAMPED:
        closed["override"] = stamp(107.5 if partial else 102.0)
    elif override is not UNSTAMPED:
        closed["override"] = override
    history.append(closed)
    base = dict(plan_id="p1", ticker="T", created_at="2026-10-02", source="strategy",
                strategy="Probe", horizon_key="2w", direction="bullish",
                entry_type="market", trigger_price=100.0, entry_price=100.0,
                expiry_bars=3, stop_loss=95.0, tp1=110.0,
                tp1_fraction=0.5 if partial else 1.0, tp2=None,
                breakeven_trigger_fraction=0.5, trail_atr_mult=5.0, quality_score=0,
                quality_breakdown=[], badge="WEAK", badge_stats={},
                status=PlanStatus.CLOSED, status_history=history, legs_realized=legs,
                hold_cap_bars=8)
    base.update(kw)
    return TradePlanV2(**base)


def frame(rows: dict | None = None, *, n: int = 26) -> pd.DataFrame:
    bars = [WARM] * FILL_IDX + [FILL_BAR] + [FLAT] * (n - FILL_IDX - 1)
    for i, bar in (rows or {}).items():
        bars[i] = bar
    days = nyse_calendar().sessions(START, START + timedelta(days=3 * n))[:n]
    return pd.DataFrame([(*bar, 1_000_000.0) for bar in bars],
                        columns=["Open", "High", "Low", "Close", "Volume"],
                        index=pd.DatetimeIndex(days))


def partial_frame(rows: dict | None = None, *, n: int = 26) -> pd.DataFrame:
    return frame({16: TP1_BAR, 17: RUNNER_HOLD, **(rows or {})}, n=n)


def book(*legs, model=None) -> float:
    """costs.book over (fraction, exit_price, kind) legs, the plan's entry and stop."""
    return costs.book(model or of.INSTRUMENT.cost_model, direction="bullish",
                      entry_price=100.0, stop_loss=95.0,
                      legs=[{"fraction": f, "exit_price": p, "reason": "x", "kind": k}
                            for f, p, k in legs])[0]


def replay(p, df, *, when=None, trade=None):
    return of.replay_override(p, df, when or df.index[-1].date(), trade)


def no_figures(row) -> bool:
    return all(getattr(row, name) is None for name in NO_FIGURES)


# -- the frame itself --------------------------------------------------------

def test_the_frame_sits_on_the_sessions_the_docstring_names():
    df = frame()
    assert [df.index[i].date() for i in (FILL_IDX, 16, OV_IDX, 19, 20, 25)] == [
        date(2026, 10, 5), date(2026, 10, 6), CLOSE_DAY, date(2026, 10, 9),
        date(2026, 10, 12), LAST_DAY]


# -- resolved exit paths -----------------------------------------------------

def test_hold_cap_timeout_is_resolved_not_open():
    row = replay(plan(), frame())
    assert (row.status, row.engine_exit_reason) == ("resolved", "timeout")
    assert row.engine_r == pytest.approx(book((1.0, 101.0, "close")), abs=1e-3)
    assert row.actual_r == pytest.approx(book((1.0, 102.0, "stop")), abs=1e-3)
    assert row.delta_r == round(row.actual_r - row.engine_r, 3)
    assert row.outcome == of.outcome_of(row.delta_r)
    assert (row.approx, row.price_source, row.bulk, row.source) == (False, "quote", False, "manual")
    assert (row.state_at_close, row.horizon, row.direction, row.ticker) == (
        "ACTIVE", "2w", "bullish", "T")
    assert row.close_date == CLOSE_DAY


def test_delta_before_costs_is_the_same_two_arms_on_the_gross_model():
    """Manual 102 (stop kind) vs the engine's 101 timeout close: 1 point on a
    5-point risk is +0.2R before costs, whatever the cost model charges."""
    row = replay(plan(), frame())
    assert row.delta_r_gross == pytest.approx(0.2, abs=1e-9)
    gross = (book((1.0, 102.0, "stop"), model=of.GROSS_COST_MODEL)
             - book((1.0, 101.0, "close"), model=of.GROSS_COST_MODEL))
    assert row.delta_r_gross == round(gross, 3)
    assert row.delta_r_gross > row.delta_r       # the manual leg pays more slippage


def test_engine_stop_after_the_override_is_resolved():
    row = replay(plan(), frame({19: STOP_BAR}))
    assert (row.status, row.engine_exit_reason) == ("resolved", "stop")
    assert row.engine_r == pytest.approx(book((1.0, 95.0, "stop")), abs=1e-3)


def test_runner_stop_at_the_floor():
    row = replay(plan(partial=True), partial_frame({18: (107.0, 107.5, 106.0, 106.5)}))
    assert (row.status, row.engine_exit_reason, row.state_at_close) == (
        "resolved", "runner_be", "PARTIAL")
    assert row.engine_r == pytest.approx(
        book((0.5, 110.0, "target"), (0.5, FLOOR, "stop")), abs=1e-3)
    assert row.actual_r == pytest.approx(
        book((0.5, 110.0, "target"), (0.5, 107.5, "stop")), abs=1e-3)


def test_runner_tp2():
    row = replay(plan(partial=True, tp2=115.0),
                 partial_frame({18: (109.0, 116.0, 108.5, 114.0)}))
    assert (row.status, row.engine_exit_reason) == ("resolved", "runner_tp2")
    assert row.engine_r == pytest.approx(
        book((0.5, 110.0, "target"), (0.5, 115.0, "target")), abs=1e-3)


TRAIL_ROWS = {17: (109.0, 112.0, 108.5, 111.5), 18: (112.0, 118.0, 111.5, 117.5),
              19: (118.0, 124.0, 117.5, 123.5), 20: (123.0, 123.5, 100.0, 101.0)}


def test_runner_trail_reads_the_real_frames_atr():
    """The engine frame clamps the override bar for the exit checks only;
    ATR comes from the real frame (indicator_df), so the trail equals the
    real-frame walk's: 3.035 when this plan was written (it was 3.038 while
    the clamped bar also fed the ATR)."""
    p = plan(partial=True, trail_atr_mult=1.0, override=stamp(111.0))
    df = partial_frame(TRAIL_ROWS)
    row = replay(p, df)
    assert (row.status, row.engine_exit_reason) == ("resolved", "runner_trail")
    real = of.engine_path(p, df, FILL_IDX)
    assert row.engine_r == of.engine_r(p, real, "PARTIAL")
    assert row.engine_r == pytest.approx(3.035, abs=0.002)


# -- open, stale -------------------------------------------------------------

def test_data_ending_before_the_hold_cap_is_open():
    row = replay(plan(), frame(n=22))     # walk_v2 clips at index 21, 15 + 8 > 21
    assert row.status == "open"
    assert no_figures(row)
    assert row.actual_r == pytest.approx(book((1.0, 102.0, "stop")), abs=1e-3)


def test_a_cache_ending_before_asof_is_stale():
    assert replay(plan(), frame(), when=date(2026, 10, 20)).status == "stale"
    assert replay(plan(), frame(), when=LAST_DAY).status == "resolved"


# -- ambiguous ---------------------------------------------------------------

@pytest.mark.parametrize("p, df", [
    pytest.param(plan(), frame({OV_IDX: (101.0, 102.0, 94.0, 101.0)}), id="active-stop-wick"),
    pytest.param(plan(), frame({OV_IDX: (101.0, 111.0, 100.0, 101.0)}), id="active-tp1-wick"),
    pytest.param(plan(partial=True), partial_frame({OV_IDX: (108.0, 108.5, 106.0, 107.5)}),
                 id="partial-floor-wick"),
    pytest.param(plan(partial=True, partial_at=CLOSE_AT),
                 frame({OV_IDX: TP1_BAR, 18: RUNNER_HOLD}), id="partial-tp1-same-session"),
])
def test_override_session_touching_a_level_is_ambiguous(p, df):
    row = replay(p, df)
    assert row.status == "ambiguous"
    assert no_figures(row)


# -- parity_mismatch ---------------------------------------------------------

@pytest.mark.parametrize("p, df", [
    pytest.param(plan(), frame({FILL_IDX: (100.0, 101.0, 94.0, 100.0)}), id="fill-bar-stop"),
    pytest.param(plan(), frame({16: STOP_BAR}), id="active-early-stop"),
    pytest.param(plan(tp1_fraction=0.5), frame({16: TP1_BAR, OV_IDX: RUNNER_HOLD}),
                 id="active-but-replay-took-tp1-first"),
    pytest.param(plan(partial=True, partial_at="2026-10-08T15:00:00+00:00",
                      close_at="2026-10-09T18:00:00+00:00"),
                 partial_frame({18: RUNNER_HOLD, 19: RUNNER_HOLD}),
                 id="partial-replay-tp1-earlier-than-live"),
    pytest.param(plan(partial=True), frame(), id="partial-replay-never-reaches-tp1"),
])
def test_replay_disagreeing_with_the_live_path_is_parity_mismatch(p, df):
    row = replay(p, df)
    assert row.status == "parity_mismatch"
    assert no_figures(row)


# -- split_affected (the price band; V173-22 adds the adjustment seam) --------

def test_entry_outside_the_fill_bar_is_split_affected():
    assert replay(plan(), frame({FILL_IDX: (50.0, 50.5, 49.5, 50.0)})).status == "split_affected"


def test_entry_inside_the_two_percent_tolerance_is_not_split_affected():
    # 98.1 * 1.02 = 100.062 >= 100
    assert replay(plan(), frame({FILL_IDX: (98.0, 98.1, 97.5, 98.0)})).status == "resolved"


# -- unstamped ---------------------------------------------------------------

@pytest.mark.parametrize("override", [None, stamp(None, "none", None)],
                         ids=["override-null", "price-source-none"])
def test_a_failed_stamp_on_an_individual_close_is_unstamped(override):
    row = replay(plan(override=override), frame(), trade={"id": "t1", "shares": 10})
    assert row.status == "unstamped"
    assert (row.approx, row.price_source, row.bulk) == (False, "none", False)
    assert row.actual_r is None and row.actual_usd is None
    assert no_figures(row)
    assert row.close_date == CLOSE_DAY


@pytest.mark.parametrize("p, bars", [
    pytest.param(plan(override=None), None, id="no-bars"),
    pytest.param(plan(override=None, fill_at=None), frame(), id="no-active-entry"),
    pytest.param(plan(override=None, entry_price=None), frame(), id="no-entry-price"),
])
def test_unstamped_beats_unreplayable(p, bars):
    assert of.replay_override(p, bars, LAST_DAY).status == "unstamped"


@pytest.mark.parametrize("override", [None, stamp(None, "none", None)],
                         ids=["override-null", "price-source-none"])
def test_a_failed_stamp_on_a_bulk_close_is_priced_from_the_session_bar(override):
    row = replay(plan(reason="manual_bulk", override=override), frame())
    assert (row.status, row.bulk, row.approx, row.price_source) == (
        "resolved", True, True, "session_close")
    assert row.actual_r == pytest.approx(book((1.0, 101.0, "stop")), abs=1e-3)


# -- unreplayable and precedence ---------------------------------------------

_FULL = frame()


@pytest.mark.parametrize("p, bars", [
    pytest.param(plan(fill_at=None), _FULL, id="no-active-entry"),
    pytest.param(plan(), None, id="no-bars"),
    pytest.param(plan(), _FULL.iloc[0:0], id="empty-bars"),
    pytest.param(plan(), _FULL.iloc[16:], id="fill-session-not-in-bars"),
    pytest.param(plan(entry_price=None), _FULL, id="no-entry-price"),
    pytest.param(plan(reason="tp1_runner_trail"), _FULL, id="not-a-manual-close"),
    pytest.param(plan(close_at="not-a-time"), _FULL, id="unreadable-close-time"),
    pytest.param(plan(override=UNSTAMPED), _FULL.drop(_FULL.index[OV_IDX]),
                 id="pre-v173-override-session-missing"),
    pytest.param(plan(stop_loss=101.0), _FULL, id="costs-book-refuses"),
])
def test_rows_the_replay_cannot_place_are_unreplayable(p, bars):
    row = of.replay_override(p, bars, LAST_DAY)
    assert row.status == "unreplayable"
    assert no_figures(row)
    assert row.source == "manual"


def test_unreplayable_beats_stale_and_stale_beats_split():
    assert of.replay_override(plan(fill_at=None), _FULL, date(2026, 10, 20)).status == "unreplayable"
    split = frame({FILL_IDX: (50.0, 50.5, 49.5, 50.0)})
    assert of.replay_override(plan(), split, date(2026, 10, 20)).status == "stale"


# -- no lookahead --------------------------------------------------------------

@pytest.mark.parametrize("p, rows", [
    pytest.param(plan(), {19: STOP_BAR}, id="stop-path"),
    pytest.param(plan(), {}, id="hold-cap-timeout-path"),
    pytest.param(plan(), {18: (101.0, 111.0, 100.0, 108.0)}, id="single-leg-tp1-path"),
])
def test_bars_before_the_fill_never_change_engine_r(p, rows):
    """Pinned on single-leg (tp1_fraction 1.0) plans only, as V173-8 does. A
    runner's trailing stop reads ATR(14), which looks back up to 13 sessions
    before the fill, exactly as the live trail did: past data, not lookahead,
    so a runner plan's engine_r may legitimately move here."""
    base = replay(p, frame(rows))
    moved = frame(rows)
    moved.iloc[0] = (90.0, 91.0, 89.0, 90.0, 1_000_000.0)
    moved.iloc[5] = (100.0, 130.0, 70.0, 100.0, 1_000_000.0)
    again = replay(p, moved)
    assert base.status == again.status == "resolved"
    assert again.engine_r == base.engine_r


def test_override_bar_range_never_moves_a_pre_tp1_engine_r():
    """Pre-TP1 the walk reads no indicator, so the clamped override bar is all
    the engine arm sees of that session: a quieter or wider range touching no
    level leaves engine_r alone, a range touching the stop flips the row to
    ambiguous. (A runner plan reads the real bar's range through ATR on later
    bars, as it did live: decision 6.)"""
    quiet, touching = (101.0, 104.0, 96.0, 101.0), (101.0, 102.0, 94.0, 101.0)
    base = replay(plan(), frame())
    other = replay(plan(), frame({OV_IDX: quiet}))
    flipped = replay(plan(), frame({OV_IDX: touching}))
    assert base.status == other.status == "resolved"
    assert other.engine_r == base.engine_r
    assert flipped.status == "ambiguous"


# -- cost parity, dollars, bulk ----------------------------------------------

def test_same_exit_price_and_kind_as_the_engine_gives_zero_delta():
    """Same price, both legs of kind stop. On the override session itself the
    row would be ambiguous by design, so the engine's stop sits two sessions on."""
    row = replay(plan(override=stamp(95.0)), frame({19: STOP_BAR}))
    assert row.status == "resolved"
    assert row.delta_r == 0.0
    assert row.delta_r_gross == 0.0
    assert row.outcome == "neutral"


def test_dollars_come_from_the_linked_trades_shares():
    row = replay(plan(), frame({19: STOP_BAR}), trade={"id": "t1", "shares": 10})
    risk = 10 * abs(100.0 - 95.0)
    assert row.actual_usd == round(row.actual_r * risk, 2)
    assert row.engine_usd == round(row.engine_r * risk, 2)
    assert row.delta_usd == round(row.delta_r * risk, 2)


@pytest.mark.parametrize("trade", [None, {"id": "t1"}, {"id": "t1", "shares": None}])
def test_no_linked_shares_means_no_dollars_but_r_stays(trade):
    row = replay(plan(), frame({19: STOP_BAR}), trade=trade)
    assert (row.actual_usd, row.engine_usd, row.delta_usd) == (None, None, None)
    assert row.delta_r is not None


def test_a_bulk_close_is_replayed_and_flagged():
    row = replay(plan(reason="manual_bulk"), frame())
    assert (row.bulk, row.status) == (True, "resolved")


# -- the actual exit price (spec §3 session table, stamp kinds) ---------------

def _priced() -> pd.DataFrame:
    df = frame()
    df["Open"] = [200.0 + i for i in range(len(df))]
    df["Close"] = [300.0 + i for i in range(len(df))]
    return df


@pytest.mark.parametrize("at, expected", [
    pytest.param("2026-10-07T12:00:00+00:00", (217.0, "session_open"), id="before-open"),
    pytest.param("2026-10-07T13:30:00+00:00", (317.0, "session_close"), id="at-the-open"),
    pytest.param("2026-10-07T18:00:00+00:00", (317.0, "session_close"), id="regular-hours"),
    pytest.param("2026-10-07T21:30:00+00:00", (317.0, "session_close"), id="after-close"),
    pytest.param("2026-10-08T02:00:00+00:00", (317.0, "session_close"), id="utc-next-day"),
    pytest.param("2026-10-10T15:00:00+00:00", (319.0, "session_close"), id="saturday"),
    pytest.param("2026-10-12T03:00:00+00:00", (319.0, "session_close"), id="sunday-night-et"),
])
def test_a_pre_v173_exit_price_follows_the_session_table(at, expected):
    p = plan(override=UNSTAMPED, close_at=at)
    assert of.actual_exit(p, _priced(), of.assign_session(at)) == (*expected, True)


def test_a_quote_stamp_wins_and_is_never_approx():
    hit = of.assign_session(CLOSE_AT)
    assert of.actual_exit(plan(), _priced(), hit) == (102.0, "quote", False)
    old_cache = plan(override=stamp(102.0, "quote", "2026-09-01"))
    assert of.actual_exit(old_cache, _priced(), hit) == (102.0, "quote", False)


@pytest.mark.parametrize("bars_asof, approx", [
    pytest.param("2026-10-07", False, id="cache-at-the-close-session"),
    pytest.param("2026-10-08", False, id="cache-after-the-close-session"),
    pytest.param("2026-10-06", True, id="cache-a-session-old"),
    pytest.param(None, True, id="cache-date-unknown"),
])
def test_a_bar_close_stamp_older_than_the_close_session_is_approx(bars_asof, approx):
    hit = of.assign_session(CLOSE_AT)
    p = plan(override=stamp(101.5, "bar_close", bars_asof))
    assert of.actual_exit(p, _priced(), hit) == (101.5, "bar_close", approx)


def test_an_approx_bar_close_row_keeps_the_stamp_price():
    row = replay(plan(override=stamp(101.5, "bar_close", "2026-10-06")), frame())
    assert (row.status, row.approx, row.price_source) == ("resolved", True, "bar_close")
    assert row.actual_r == pytest.approx(book((1.0, 101.5, "stop")), abs=1e-3)


def test_a_pre_v173_row_is_approx_from_the_session_bar():
    row = replay(plan(override=UNSTAMPED), frame())
    assert (row.approx, row.price_source, row.status) == (True, "session_close", "resolved")
    assert row.actual_r == pytest.approx(book((1.0, 101.0, "stop")), abs=1e-3)


def test_no_bar_for_the_override_session_gives_no_price():
    df = _priced().drop(_priced().index[OV_IDX])
    assert of.actual_exit(plan(override=UNSTAMPED), df, of.assign_session(CLOSE_AT)) == (
        None, "none", True)


def test_an_unreplayable_row_keeps_its_stamp_fields():
    stamped = of.replay_override(plan(fill_at=None), _FULL, LAST_DAY)
    assert (stamped.status, stamped.approx, stamped.price_source) == (
        "unreplayable", False, "quote")
    old = of.replay_override(plan(fill_at=None, override=UNSTAMPED), _FULL, LAST_DAY)
    assert (old.status, old.approx, old.price_source) == ("unreplayable", True, "none")
```

The scenario paths (`timeout` at 23, `stop` at 19, `tp1` at 18, `runner_be`/`runner_tp2` at 18, `runner_trail` at 20, the early exits at 15/16/17) were checked against `walk_v2`/`_fill_bar_v2` with these frames when this plan was first written. The trail figure 3.035 was the real-frame walk's then; the test also pins it against `engine_path` on the real frame, so the equality line is the contract and the number a sanity check.

- [ ] **Step 2: Run it to verify it fails**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_fidelity_replay.py
```

Expected: FAIL with `AttributeError: module 'swingbot.core.analytics.override_fidelity' has no attribute 'replay_override'` (and `actual_exit`). `test_the_frame_sits_on_the_sessions_the_docstring_names` passes.

If an import or a V173-6..8/21 name fails instead (`stamp_kind`, `GROSS_COST_MODEL`, `engine_path(..., indicator_df=)`), an earlier task is missing: stop and report. Do not re-create it.

- [ ] **Step 3: Implement**

At the top of `$WT/swingbot/core/analytics/override_fidelity.py`, add `import logging` beside the other standard-library imports if it is missing. V173-7 and V173-8 already import `datetime as dt`, `dataclass`, `pandas as pd`, `PlanStatus` and `ExitResult`.

Append at the end of the module:

```python
# --------------------------------------------------------------------------
# V173-9: the actual exit price and replay_override's eight statuses
# (spec §3, plan panel review). Precedence, first match wins: unstamped ->
# unreplayable -> stale -> split_affected -> parity_mismatch -> ambiguous ->
# open -> resolved.
# --------------------------------------------------------------------------

_log = logging.getLogger(__name__)


class _Unreplayable(Exception):
    """The replay cannot place this override: no fill, no bars, no exit
    price, or costs.book refused the plan's entry and stop."""


@dataclass(frozen=True)
class _Replay:
    """What the status walk needs, gathered once by _prepare."""
    df: pd.DataFrame
    fill_idx: int
    ov_idx: int | None
    state: str
    price: float
    price_source: str
    approx: bool
    actual_r: float


@dataclass(frozen=True)
class _Arms:
    """The engine side of a resolved row."""
    engine_r: float
    gross_delta: float
    exit_reason: str


def _iso_day(value) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def _bar_close_stale(stamp: dict, hit: SessionHit | None) -> bool:
    """A bar_close stamp read from a cache older than the close session (or
    of unknown age) is an estimate, not the price the human saw."""
    if stamp.get("price_source") != "bar_close":
        return False
    cache_day = _iso_day(stamp.get("bars_asof"))
    return cache_day is None or hit is None or cache_day < hit.session


def _stamped_price(entry: dict | None,
                   hit: SessionHit | None) -> tuple[float, str, bool] | None:
    """(price, source, approx) from a "stamped" stamp with a price; else None."""
    if entry is None or stamp_kind(entry) != "stamped":
        return None
    stamp = entry["override"]
    if stamp.get("exit_price") is None:
        return None
    return (float(stamp["exit_price"]), str(stamp["price_source"]),
            _bar_close_stale(stamp, hit))


def _bar_price(df: pd.DataFrame | None, hit: SessionHit | None) -> tuple[float | None, str]:
    """The override session's open or close, per the spec §3 table."""
    idx = session_index(df, hit.session) if df is not None and hit is not None else None
    if idx is None:
        return None, "none"
    if hit.price_kind == "open":
        return float(df["Open"].iloc[idx]), "session_open"
    return float(df["Close"].iloc[idx]), "session_close"


def actual_exit(plan, df: pd.DataFrame | None,
                hit: SessionHit | None) -> tuple[float | None, str, bool]:
    """(price, price_source, approx) of the human's exit.

    A "stamped" stamp's exit_price (quote or bar_close; a bar_close older
    than the close session is approx); otherwise the override session bar's
    open or close, approx. An individual close with a failed stamp never
    gets here: replay_override marks it unstamped first."""
    priced = _stamped_price(override_entry(plan), hit)
    if priced is not None:
        return priced
    price, source = _bar_price(df, hit)
    return price, source, True


def _is_unstamped(entry: dict | None) -> bool:
    """An individual close whose post-v173 stamp failed (Global Constraints,
    Stamp kinds). Bulk closes fall through to the session-bar path."""
    return (entry is not None and entry.get("reason") != "manual_bulk"
            and stamp_kind(entry) == "failed")


def _price_fields(entry: dict | None, hit: SessionHit | None) -> tuple[str, bool]:
    """(price_source, approx) of a row the replay never priced."""
    if _is_unstamped(entry):
        return "none", False
    priced = _stamped_price(entry, hit)
    return (priced[1], priced[2]) if priced is not None else ("none", True)


def _usable_frame(bars) -> pd.DataFrame:
    if bars is None or len(bars) == 0:
        raise _Unreplayable("no cached bars")
    return bars


def _fill_index(plan, df: pd.DataFrame) -> int:
    hit = assign_session(transition_at(plan, "ACTIVE"))
    idx = session_index(df, hit.session) if hit is not None else None
    if idx is None:
        raise _Unreplayable("no fill session in the cached bars")
    return idx


def _booked_actual(plan, price: float, state: str) -> float:
    try:
        return actual_r(plan, price, state)
    except (ValueError, KeyError, TypeError) as exc:
        raise _Unreplayable(f"costs.book refused the actual arm: {exc}") from exc


def _prepare(plan, bars, hit: SessionHit | None) -> _Replay:
    """Everything before the bars are judged; raises _Unreplayable."""
    if override_entry(plan) is None or hit is None:
        raise _Unreplayable("not a manual close with a readable time")
    if plan.entry_price is None or plan.stop_loss is None:
        raise _Unreplayable("plan has no entry price or stop")
    df = _usable_frame(bars)
    fill_idx = _fill_index(plan, df)
    price, source, approx = actual_exit(plan, df, hit)
    if price is None:
        raise _Unreplayable("no exit price derivable")
    state = state_at_close(plan)
    return _Replay(df=df, fill_idx=fill_idx, ov_idx=session_index(df, hit.session),
                   state=state, price=price, price_source=source, approx=approx,
                   actual_r=_booked_actual(plan, price, state))


def _split_band(plan, df: pd.DataFrame, fill_idx: int) -> bool:
    """The raw fill price outside the cached fill bar (± SPLIT_TOLERANCE):
    the adjusted cache no longer shares the plan's price basis."""
    low = float(df["Low"].iloc[fill_idx]) * (1.0 - SPLIT_TOLERANCE)
    high = float(df["High"].iloc[fill_idx]) * (1.0 + SPLIT_TOLERANCE)
    return not low <= float(plan.entry_price) <= high


def _admission(plan, rp: _Replay, asof: dt.date) -> str | None:
    """stale / split_affected / unreplayable from the bars alone, or None.
    V173-22 widens stale (calendar gaps) and split_affected (seams)."""
    if rp.df.index[-1].date() < asof:
        return "stale"
    if _split_band(plan, rp.df, rp.fill_idx):
        return "split_affected"
    if rp.ov_idx is None or rp.ov_idx < rp.fill_idx:
        return "unreplayable"
    return None


def _live_tp1_index(plan, df: pd.DataFrame) -> int | None:
    hit = assign_session(transition_at(plan, "PARTIAL"))
    return session_index(df, hit.session) if hit is not None else None


def _parity_broken(plan, real: ExitResult, rp: _Replay) -> bool:
    """The replay disagrees with what the live plan did before the override."""
    if real.exit_index < rp.ov_idx:
        return True
    if rp.state == "ACTIVE":
        return real.tp1_index is not None and real.tp1_index < rp.ov_idx
    live = _live_tp1_index(plan, rp.df)
    return live is None or real.tp1_index != live


def _ambiguous(real: ExitResult, ov_idx: int) -> bool:
    """The engine may have exited on the override session before the human."""
    if real.tp1_index == ov_idx:
        return True
    return (real.exit_index == ov_idx
            and leg_kind(real.legs[-1]["reason"]) in ("stop", "target"))


def _engine_arm(plan, rp: _Replay) -> ExitResult:
    """The engine left alone: exit checks on the clamped override bar,
    ATR and structure from the real bars (indicator_df).

    Guard: ExitResult.tp1_index is a plain class attribute set on the
    instance by walk_v2, not a dataclass field, so dataclasses.replace()
    and asdict() drop it (index § Handoff). Read tp1_index from the
    engine_path result itself, never from a copy."""
    return engine_path(plan, engine_frame(rp.df, rp.ov_idx), rp.fill_idx,
                       indicator_df=rp.df)


def _still_open(plan, eng: ExitResult, rp: _Replay) -> bool:
    """walk_v2 labels a data-end clip `timeout` too; only the hold cap resolves."""
    last = len(rp.df) - 1
    return (eng.legs[-1]["reason"] in TIMEOUT_REASONS and eng.exit_index == last
            and rp.fill_idx + hold_cap_bars(plan) > last)


def _status(plan, rp: _Replay, asof: dt.date) -> tuple[str, ExitResult | None]:
    """The row's status after _prepare, and the engine-frame result when resolved.

    The real frame decides parity and ambiguity only (its tp1_index is read
    straight from engine_path's result, see _engine_arm); the engine arm is
    the clamped engine frame, so the engine never sees the override
    session's range as a later path."""
    early = _admission(plan, rp, asof)
    if early is not None:
        return early, None
    real = engine_path(plan, rp.df, rp.fill_idx)
    if not real.legs:
        return "unreplayable", None
    if _parity_broken(plan, real, rp):
        return "parity_mismatch", None
    if _ambiguous(real, rp.ov_idx):
        return "ambiguous", None
    eng = _engine_arm(plan, rp)
    if _still_open(plan, eng, rp):
        return "open", None
    return "resolved", eng


def _arms(plan, rp: _Replay, eng: ExitResult) -> _Arms:
    """engine_r net of costs, and the delta before costs (descriptive only)."""
    gross_actual = actual_r(plan, rp.price, rp.state, cost_model=GROSS_COST_MODEL)
    gross_engine = engine_r(plan, eng, rp.state, cost_model=GROSS_COST_MODEL)
    return _Arms(engine_r=engine_r(plan, eng, rp.state),
                 gross_delta=round(gross_actual - gross_engine, 3),
                 exit_reason=eng.legs[-1]["reason"])


def _row(plan, entry: dict | None, hit: SessionHit | None, status: str,
         trade: dict | None, *, rp: _Replay | None = None,
         arms: _Arms | None = None) -> OverrideRow:
    a_r = rp.actual_r if rp is not None else None
    e_r = arms.engine_r if arms is not None else None
    d_r = round(a_r - e_r, 3) if arms is not None else None
    risk = dollar_risk(plan, trade) if rp is not None else None
    source, approx = ((rp.price_source, rp.approx) if rp is not None
                      else _price_fields(entry, hit))
    return OverrideRow(
        plan_id=plan.plan_id, ticker=plan.ticker, horizon=plan.horizon_key,
        direction=plan.direction, state_at_close=state_at_close(plan),
        close_date=hit.session if hit is not None else None,
        bulk=(entry or {}).get("reason") == "manual_bulk", approx=approx,
        price_source=source, status=status, actual_r=a_r, engine_r=e_r, delta_r=d_r,
        delta_r_gross=arms.gross_delta if arms is not None else None,
        actual_usd=to_usd(a_r, risk), engine_usd=to_usd(e_r, risk),
        delta_usd=to_usd(d_r, risk),
        engine_exit_reason=arms.exit_reason if arms is not None else None,
        outcome=outcome_of(d_r), source="manual")


def replay_override(plan, bars: pd.DataFrame | None, asof: dt.date,
                    trade: dict | None = None) -> OverrideRow:
    """One manual close against the engine left alone (spec §3).

    Pure: `bars` is the live scan's cache frame (never fetched here), `asof`
    the latest completed NYSE session, `trade` the linked paper trade (for
    dollars). A failed stamp on an individual close is `unstamped`; a row
    it cannot place is `unreplayable`; it never raises."""
    entry = override_entry(plan)
    hit = assign_session((entry or {}).get("at"))
    if _is_unstamped(entry):
        return _row(plan, entry, hit, "unstamped", trade)
    try:
        rp = _prepare(plan, bars, hit)
    except _Unreplayable as exc:
        _log.info("override_fidelity: %s unreplayable: %s", plan.plan_id, exc)
        return _row(plan, entry, hit, "unreplayable", trade)
    status, eng = _status(plan, rp, asof)
    arms = _arms(plan, rp, eng) if eng is not None else None
    return _row(plan, entry, hit, status, trade, rp=rp, arms=arms)
```

`stamp_kind` (V173-7) returns `"missing"` for an entry without an `override` key, `"failed"` for `override: None` or `price_source == "none"`, `"stamped"` otherwise; `_stamped_price` reads `entry["override"]` only after `stamp_kind` said `"stamped"`, so the key exists and holds a dict there.

- [ ] **Step 4: Run the new test and the earlier override tests**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_fidelity_replay.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_fidelity_sessions.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_fidelity_arms.py
```

Expected: all PASS, `0 failed`, `0 xfailed`.

If `test_runner_trail_reads_the_real_frames_atr` fails on the equality line, `_engine_arm` is not passing `indicator_df=rp.df`, or V173-21's keyword does not reach `atr_indicator`: fix that, never the test. If only the `3.035` sanity line misses while the equality holds, report the measured value in the task report and update the number; do not loosen the tolerance. If `test_the_frame_sits_on_the_sessions_the_docstring_names` fails, the calendar changed: fix the docstring dates and the `*_AT` constants together.

- [ ] **Step 5: Complexity**

```bash
python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/analytics/override_fidelity.py
```

Expected: no output (every function below grade C, i.e. CC < 11; `_status` is about 7, `_row` about 9, `_prepare` about 7). If `_row` grades C, move the four `arms is not None` ternaries into a helper returning a small dict of the engine fields; the tests stay unchanged.

- [ ] **Step 6: Commit on the branch**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides add swingbot/core/analytics/override_fidelity.py tests/analytics/test_override_fidelity_replay.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "feat(v173): replay_override -- actual exit price, unstamped rows and the eight replay statuses"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

The last command checks the main tree stayed clean of branch edits.


### Task V173-22: Data admission: trim to `asof`, NYSE calendar gaps, adjustment basis

**Model:** opus — no-lookahead (partial bars) and the split test on an adjusted cache

**Files:**
- Modify: `swingbot/core/analytics/override_fidelity.py` (append a V173-22 section; replace V173-9's `_admission` in place; one line of `replay_override`)
- Create: `tests/analytics/test_override_fidelity_admission.py`

**Interfaces:**
- Consumes (V173-7): `assign_session`, `override_entry`, `SPLIT_TOLERANCE`. (V173-8): `engine_path(plan, df, fill_idx, *, indicator_df=None)` (spied on in a test). (V173-9): `_Replay` (fields `df, fill_idx, ov_idx, ...`), `_split_band(plan, df, fill_idx) -> bool`, `_admission(plan, rp, asof) -> str | None` (replaced here), `_prepare(plan, bars, hit)`, `replay_override(plan, bars, asof, trade=None)`. Library: `swingbot.core.market.session.nyse_calendar().sessions(start, end) -> list[date]` (session.py:169); `swingbot.core.marketdata.adjustments.adjustment_seam_issue(frame, symbol, timeframe, threshold=0.20) -> str | None` (adjustments.py:71).
- Produces: `trim_to_asof(df: pd.DataFrame, asof: date) -> pd.DataFrame`; `missing_sessions(df: pd.DataFrame | None, start: date) -> list[date]`; `split_suspect(plan, df: pd.DataFrame, fill_idx: int) -> bool`; private `_close_session(plan) -> date | None`, `_stale(plan, rp, asof) -> bool`. `replay_override`'s signature is unchanged; V173-23 replaces `_status`, not `_admission`.

**Decisions this task makes inside the index's status precedence** (each has a test below):

1. **The trim happens once, in `replay_override`, before `_prepare`**, so the fill index, the override index, the actual exit price of a pre-v173 row, the real frame, the engine frame and the `open` check all see the same settled bars. Nothing after `asof` exists for the replay. An `asof` before every bar leaves an empty frame: `unreplayable` ("no or empty bars after the trim").
2. **`stale` has three triggers**, in this order: the last settled bar is before `asof` (V173-9's rule); `missing_sessions(df, <fill session>)` is non-empty (a calendar gap from the fill on would shift the hold cap and the `open` count); the close session lies after the last settled bar (a report run on the close day itself: the bars have not reached the override yet). A gap before the fill is ignored. A stamped row whose override session is missing from the bars is therefore `stale` (V173-9 decision 2 deferred it here); a pre-v173 row in the same position stays `unreplayable`, because `_prepare` has no price for it.
3. **`split_suspect` = the fill-bar band or an adjustment seam from the fill session on.** The seam detector runs on `df.iloc[fill_idx:]` only: a seam in the warm-up bars before the fill moves no price the replay compares. The frozen `SPLIT_TOLERANCE = 0.02` stays (index § Handoff trap: the cache is split **and dividend** adjusted, so a 1% dividend step stays inside the band and is not a seam).
4. **Precedence is unchanged:** `stale` before `split_affected` before the `unreplayable` index checks, as V173-9's `_admission` already orders them.

- [ ] **Step 1: Write the failing test**

Create `$WT/tests/analytics/test_override_fidelity_admission.py`:

```python
"""v173 plan panel review: data admission -- trim to asof, NYSE calendar
gaps, and the adjustment basis of the auto_adjust daily cache.

Same frames as test_override_fidelity_replay: 15 warm-up bars, the fill at
index 15 (Mon 2026-10-05), the override at index 17 (Wed 2026-10-07), the
last bar at index 25 (Mon 2026-10-19). Index 20 is Mon 2026-10-12 (an NYSE
session), index 24 is Fri 2026-10-16. Hold cap 8 unless a test says so.
"""
from datetime import date

import pytest

from swingbot import config
from swingbot.core.analytics import override_fidelity as of
from tests.analytics.test_override_fidelity_replay import (FILL_IDX, FLAT, LAST_DAY, OV_IDX,
                                                           UNSTAMPED, frame, plan, replay)
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults

FRI = date(2026, 10, 16)        # index 24
GAP_DAY = date(2026, 10, 12)    # index 20
HALVED = {i: tuple(v / 2 for v in FLAT) for i in range(20, 26)}   # a 2:1 seam at index 20


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    pin_code_defaults(monkeypatch)
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", False)
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "off")
    monkeypatch.setattr(config, "ADAPTIVE_RUNNER_TRAIL_ENABLED", False)


# -- trim_to_asof ------------------------------------------------------------

def test_trim_keeps_bars_on_or_before_asof_only():
    df = frame()
    out = of.trim_to_asof(df, FRI)
    assert out.index[-1].date() == FRI
    assert out.equals(df.iloc[:25])
    assert len(df) == 26                                   # the input is not mutated
    assert of.trim_to_asof(df, LAST_DAY).equals(df)
    assert of.trim_to_asof(df, date(2026, 9, 1)).empty


def test_a_bar_dated_after_asof_never_reaches_the_walk(monkeypatch):
    """The cache can hold a half-formed bar for today (data_refresh.py:160-170).
    Here Monday's bar runs through the stop; with asof = Friday no frame the
    replay walks (real, engine, or the indicator frame) reaches it."""
    seen = []
    walk = of.engine_path

    def spy(p, df, fill_idx, *, indicator_df=None):
        seen.append(df.index[-1].date())
        if indicator_df is not None:
            seen.append(indicator_df.index[-1].date())
        return walk(p, df, fill_idx, indicator_df=indicator_df)

    monkeypatch.setattr(of, "engine_path", spy)
    row = replay(plan(), frame({25: (101.0, 102.0, 94.0, 95.0)}), when=FRI)
    assert seen and max(seen) == FRI
    assert (row.status, row.engine_exit_reason) == ("resolved", "timeout")


def test_the_trim_decides_open_against_the_hold_cap():
    """Hold cap 10 from the fill at 15 ends at index 25. Trimmed to Friday
    (index 24) the walk clips at the data end: still open. With Monday
    settled, the same plan times out on the hold cap: resolved."""
    assert replay(plan(hold_cap_bars=10), frame(), when=FRI).status == "open"
    assert replay(plan(hold_cap_bars=10), frame(), when=LAST_DAY).status == "resolved"


def test_asof_before_every_bar_is_unreplayable():
    assert replay(plan(), frame(), when=date(2026, 9, 1)).status == "unreplayable"


# -- missing_sessions and stale ----------------------------------------------

def test_missing_sessions_lists_calendar_sessions_absent_from_the_frame():
    df = frame()
    gap = df.drop(df.index[20])
    assert of.missing_sessions(df, date(2026, 10, 5)) == []
    assert of.missing_sessions(gap, date(2026, 10, 5)) == [GAP_DAY]
    assert of.missing_sessions(gap, date(2026, 10, 13)) == []      # the gap is before start
    assert of.missing_sessions(df, date(2026, 10, 10)) == []       # a Saturday start
    assert of.missing_sessions(gap.iloc[0:0], date(2026, 10, 5)) == []
    assert of.missing_sessions(None, date(2026, 10, 5)) == []


@pytest.mark.parametrize("missing", [16, OV_IDX, 20],
                         ids=["after-fill", "override-session", "after-override"])
def test_a_missing_session_from_the_fill_on_is_stale(missing):
    df = frame()
    row = replay(plan(), df.drop(df.index[missing]), when=LAST_DAY)
    assert row.status == "stale"
    assert (row.engine_r, row.delta_r, row.outcome) == (None, None, None)


def test_a_pre_v173_row_missing_its_override_session_stays_unreplayable():
    df = frame()
    gap = df.drop(df.index[OV_IDX])
    assert replay(plan(override=UNSTAMPED), gap, when=LAST_DAY).status == "unreplayable"


def test_a_gap_before_the_fill_does_not_matter():
    df = frame()
    assert replay(plan(), df.drop(df.index[5]), when=LAST_DAY).status == "resolved"


def test_a_stamped_close_after_the_last_settled_bar_is_stale():
    """Report run on the close day itself: asof is the previous session, so
    the settled bars stop before the override session."""
    assert replay(plan(), frame(), when=date(2026, 10, 6)).status == "stale"


# -- split_suspect -----------------------------------------------------------

def test_a_two_for_one_seam_after_the_fill_is_split_affected():
    df = frame(HALVED)
    assert of._split_band(plan(), df, FILL_IDX) is False       # the fill bar itself agrees
    assert of.split_suspect(plan(), df, FILL_IDX) is True
    row = replay(plan(), df)
    assert row.status == "split_affected"
    assert (row.engine_r, row.delta_r) == (None, None)


def test_the_fill_bar_band_still_marks_split_suspect():
    assert of.split_suspect(plan(), frame({FILL_IDX: (50.0, 50.5, 49.5, 50.0)}), FILL_IDX) is True
    assert of.split_suspect(plan(), frame(), FILL_IDX) is False


def test_a_seam_before_the_fill_is_not_split_affected():
    df = frame({i: (200.0, 201.0, 199.0, 200.0) for i in range(10)})   # seam at index 10
    assert of.split_suspect(plan(), df, FILL_IDX) is False
    assert replay(plan(), df).status == "resolved"


def test_a_dividend_sized_drift_inside_two_percent_stays_resolved():
    """auto_adjust rescales history before an ex-date: a 1% dividend on
    Mon 2026-10-12 scales every earlier bar, the fill bar included, by 0.99.
    The raw entry (100) sits inside the fill bar's 2% band (99.99 x 1.02)
    and a 1% step is no seam."""
    df = frame()
    df.iloc[:20, :4] = df.iloc[:20, :4] * 0.99
    assert of.split_suspect(plan(), df, FILL_IDX) is False
    assert replay(plan(), df).status == "resolved"


def test_stale_beats_a_seam():
    assert replay(plan(), frame(HALVED), when=date(2026, 10, 20)).status == "stale"
```

The scenario arithmetic, checked against `adjustment_seam_issue` (adjustments.py:71-87) when this plan was written: in `HALVED` the close ratio at index 20 is 0.5; the five closes before it (indices 15..19: 100, 101, 101, 101, 101) and the five after it (50.5 each) both have a coefficient of variation below 0.03, so it reports a seam. In the warm-up seam the five 200 closes before index 10 and the five 100 closes after it qualify on the whole frame, but `df.iloc[FILL_IDX:]` holds no close ratio past 20%. The hold-cap test relies on V173-9's frame: cap 10 from index 15 ends at 25, so the trimmed 25-bar frame (last index 24) clips there and `15 + 10 > 24` keeps it open.

- [ ] **Step 2: Run it to verify it fails**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_fidelity_admission.py
```

Expected: FAIL with `AttributeError: module 'swingbot.core.analytics.override_fidelity' has no attribute 'trim_to_asof'` (and `missing_sessions`, `split_suspect`); the status tests fail on the wrong status (for example `test_the_trim_decides_open_against_the_hold_cap` reads `resolved`, `test_a_missing_session_from_the_fill_on_is_stale[override-session]` reads `unreplayable`). `test_a_gap_before_the_fill_does_not_matter` and `test_a_pre_v173_row_missing_its_override_session_stays_unreplayable` may already pass.

If an import from `tests.analytics.test_override_fidelity_replay` fails, V173-9 is not on the branch: stop and report.

- [ ] **Step 3: Implement**

In `$WT/swingbot/core/analytics/override_fidelity.py`, add beside the other imports (skip either if V173-7 already imports it):

```python
from swingbot.core.market.session import nyse_calendar
from swingbot.core.marketdata import adjustments
```

Append at the end of the module:

```python
# --------------------------------------------------------------------------
# V173-22: data admission (plan panel review). The cache can hold a
# half-formed bar for today, can miss a session, and is split AND dividend
# adjusted (auto_adjust=True), rescaled after later corporate actions.
# --------------------------------------------------------------------------

def trim_to_asof(df: pd.DataFrame, asof: dt.date) -> pd.DataFrame:
    """The bars dated on or before `asof`: settled sessions only. A partially
    formed bar for today (data_refresh.py:160-170) never reaches the replay."""
    return df.loc[df.index.normalize() <= pd.Timestamp(asof)]


def missing_sessions(df: pd.DataFrame | None, start: dt.date) -> list[dt.date]:
    """NYSE sessions from `start` to the frame's last bar that the frame lacks."""
    if df is None or len(df) == 0:
        return []
    present = set(df.index.date)
    return [day for day in nyse_calendar().sessions(start, df.index[-1].date())
            if day not in present]


def split_suspect(plan, df: pd.DataFrame, fill_idx: int) -> bool:
    """The cache no longer shares the plan's raw price basis: the fill price
    outside the fill bar's band, or an adjustment seam from the fill on."""
    if _split_band(plan, df, fill_idx):
        return True
    seam = adjustments.adjustment_seam_issue(df.iloc[fill_idx:], plan.ticker, "daily")
    return seam is not None


def _close_session(plan) -> dt.date | None:
    hit = assign_session((override_entry(plan) or {}).get("at"))
    return hit.session if hit is not None else None


def _stale(plan, rp: _Replay, asof: dt.date) -> bool:
    """Bars behind asof, a calendar gap from the fill on, or a close the
    settled bars have not reached yet."""
    last = rp.df.index[-1].date()
    if last < asof:
        return True
    if missing_sessions(rp.df, rp.df.index[rp.fill_idx].date()):
        return True
    close = _close_session(plan)
    return close is not None and close > last
```

Replace V173-9's `_admission` **in place** (same position in the module, so there is one definition) with:

```python
def _admission(plan, rp: _Replay, asof: dt.date) -> str | None:
    """stale / split_affected / unreplayable from the bars alone, or None."""
    if _stale(plan, rp, asof):
        return "stale"
    if split_suspect(plan, rp.df, rp.fill_idx):
        return "split_affected"
    if rp.ov_idx is None or rp.ov_idx < rp.fill_idx:
        return "unreplayable"
    return None
```

`_admission` calls helpers defined further down the module; Python resolves them at call time. In `replay_override`, replace the line `rp = _prepare(plan, bars, hit)` with:

```python
        settled = None if bars is None else trim_to_asof(bars, asof)
        rp = _prepare(plan, settled, hit)        # V173-22: nothing after asof
```

and add to its docstring: "Bars dated after `asof` are dropped before any index is taken."

- [ ] **Step 4: Run the new test and the earlier override tests**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_fidelity_admission.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_fidelity_replay.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_fidelity_arms.py
```

Expected: all PASS, `0 failed`, `0 xfailed`. V173-9's tests must stay green unchanged: every V173-9 frame closes on 2026-10-07 with bars through at least 2026-10-14 and no gap after the fill, so none changes status. If one does, the new rule is wrong, not the old test.

If `test_a_two_for_one_seam_after_the_fill_is_split_affected` fails on `split_suspect`, print `adjustments.adjustment_seam_issue(df.iloc[FILL_IDX:], "T", "daily")`; `None` there means the detector changed since this plan was written: report it, do not reshape the frame to pass.

- [ ] **Step 5: Complexity**

```bash
python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/analytics/override_fidelity.py
```

Expected: no output (`_stale` about 4, `_admission` about 6, `replay_override` about 4).

- [ ] **Step 6: Commit on the branch**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides add swingbot/core/analytics/override_fidelity.py tests/analytics/test_override_fidelity_admission.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "feat(v173): override replay admits settled bars only -- trim to asof, calendar gaps stale, adjustment seams split_affected"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

The last command checks the main tree stayed clean of branch edits.
