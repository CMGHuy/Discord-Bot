# v173 Execution fidelity, part 3: replay statuses, the summary and the frozen verdict

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task with `grep -n "^### Task V173-9:" -A 700 <this file>`; never read the file whole.

**Spec:** [`docs/superpowers/specs/2026-10-18-v173-execution-fidelity-overrides-design.md`](../specs/2026-10-18-v173-execution-fidelity-overrides-design.md) §3 (rows and statuses, the session table, helped/hurt/neutral, `summarise`) and §4 (verdict rule)
**Bump:** bot minor; ui minor (applied once, in V173-17)
**Edge:** none (integrity)
**Index:** [`2026-10-18-v173-execution-fidelity-overrides_0-index.md`](2026-10-18-v173-execution-fidelity-overrides_0-index.md) carries the Goal, `## Global Constraints`, `## Parallelisation`, `## Where to work` (`$WT`, `$R`) and the task ledger. Every task below implicitly includes those Global Constraints, in particular **Status precedence**, **One cost basis**, **Counted rows**, **Verdict** and **Report payload**.

Tasks: V173-9..V173-10, in order (both edit `swingbot/core/analytics/override_fidelity.py`). V173-9 needs V173-6 (`fill_bar_exit`, `ExitResult.tp1_index`), V173-7 and V173-8 committed on the branch first.

**What earlier tasks created, per the index ledger** (check each with `git -C $WT grep -n "<name>" swingbot/core/analytics/override_fidelity.py` before starting; a missing one means an earlier task is not merged into the branch yet: stop and report, never re-create it here):

- V173-7: constants `MANUAL_REASONS`, `STATUSES`, `EXCLUDED_STATUSES`, `TIMEOUT_REASONS`, `DEAD_BAND`, `VERDICT_FLOOR`, `WEEK_FLOOR`, `EXCLUDED_CAP`, `SPLIT_TOLERANCE`, `LEDGER_ID`; `SessionHit(session: date, price_kind: str)`; `assign_session(at_iso)`; `latest_completed_session(now)`; `session_index(df, day) -> int | None`; `transition_at(plan, status) -> str | None`; `override_entry(plan) -> dict | None`; `is_override(plan) -> bool`; `state_at_close(plan) -> "PARTIAL" | "ACTIVE"`; the frozen dataclass `OverrideRow` (the 19 row fields, property `entry_date`, `to_dict()`); `outcome_of(delta_r) -> "helped" | "hurt" | "neutral" | None`.
- V173-8: `INSTRUMENT`, `hold_cap_bars(plan)`, `engine_frame(df, ov_idx)`, `engine_path(plan, df, fill_idx) -> ExitResult` (fill-bar check first, then `walk_v2`), `leg_kind(reason)`, `live_tp1_leg(plan)`, `actual_r(plan, exit_price, state)`, `engine_r(plan, result, state)`, `dollar_risk(plan, trade)`, `to_usd(r, risk)`.

**Tests never touch a database** (Global Constraints): plain `TradePlanV2` objects, synthetic frames on real NYSE session dates, `tmp_path` ledgers. No `seed_store`, no `db_conn`, never the production replica.

# Phase: Statuses, summary, verdict (V173-9..V173-10)

### Task V173-9: `replay_override`: actual exit price and the seven statuses

**Model:** opus — no-lookahead replay, status precedence feeds the verdict

**Files:**
- Modify: `swingbot/core/analytics/override_fidelity.py` (append a V173-9 section after V173-8's arms; created by V173-7, extended by V173-8)
- Create: `tests/analytics/test_override_fidelity_replay.py`

**Interfaces:**
- Consumes (V173-7): `SessionHit`, `assign_session`, `session_index`, `transition_at`, `override_entry`, `state_at_close`, `OverrideRow`, `outcome_of`, `TIMEOUT_REASONS`, `SPLIT_TOLERANCE`. (V173-8): `INSTRUMENT`, `hold_cap_bars`, `engine_frame`, `engine_path`, `leg_kind`, `actual_r`, `engine_r`, `dollar_risk`, `to_usd`. (V173-6): `ExitResult.tp1_index`.
- Produces: `actual_exit(plan, df: pd.DataFrame | None, hit: SessionHit | None) -> tuple[float | None, str, bool]`, i.e. `(price, price_source, approx)`; `replay_override(plan, bars: pd.DataFrame | None, asof: date, trade: dict | None = None) -> OverrideRow`. V173-10's `build_report` calls `replay_override` once per override plan; nothing else in this section is public.

**Decisions this task makes inside the index's status precedence** (each has a test below; none changes a shared contract):

1. **`unreplayable` before the bars are judged** covers: not a manual close, an unreadable `at`, no `entry_price`/`stop_loss`, no or empty bars, no fill session in the bars, no actual exit price (an unstamped row whose override session is missing from the bars), and `costs.book` refusing the actual arm. A *stamped* row whose override session is missing from the bars is judged after `stale` (a cache that ends early is stale, not unreplayable), then `unreplayable`.
2. **Ambiguous on any TP1 at the override session**, ACTIVE or PARTIAL. The index names the ACTIVE case. For a PARTIAL plan whose live TP1 and manual close fall on the same session, the engine frame would clamp the TP1 bar's high and lose the very TP1 the live plan took, so that row is also `ambiguous`.
3. **Non-resolved rows carry no engine figures:** `engine_r`, `delta_r`, `engine_usd`, `delta_usd`, `engine_exit_reason` and `outcome` are `None` unless `status == "resolved"`. `actual_r`/`actual_usd` are filled whenever the actual arm could be booked (shown in the table, summed only for counted rows).
4. **`close_date`** is the override session (`assign_session(<CLOSED at>).session`), so a weekend close dates to Friday; `None` only when `at` is unreadable.

- [ ] **Step 1: Write the failing test**

Create `$WT/tests/analytics/test_override_fidelity_replay.py`:

```python
"""v173 §3: replay_override -- the actual exit price and the seven statuses.

Frames sit on real NYSE sessions from 2026-09-14: 15 warm-up bars, the fill
bar at index 15 (Mon 2026-10-05), the override session at index 17 (Wed
2026-10-07). Bullish plans enter at 100 with the stop at 95 and TP1 at 110;
the hold cap is 8 bars, so a full 26-bar frame (last bar Mon 2026-10-19)
times out at index 23. Expected R figures are booked here through the same
costs.book call, so the tests pin the wiring, not the engine's arithmetic
(V173-8's arms tests pin that).
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
LAST_DAY = date(2026, 10, 19)              # index 25 of a full frame
WARM = (100.0, 100.5, 99.5, 100.0)
FILL_BAR = (100.0, 101.0, 99.0, 100.0)
FLAT = (101.0, 102.0, 100.0, 101.0)        # below the 105 breakeven trigger
TP1_BAR = (104.0, 111.0, 103.0, 108.0)
RUNNER_HOLD = (108.0, 108.5, 107.0, 107.5)  # above the runner floor
STOP_BAR = (101.0, 102.0, 94.0, 95.0)
FLOOR = runner_floor(100.0, 110.0)           # 106.667
_STAMPED = object()
UNSTAMPED = object()


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    """Code defaults, with the exit flags that would add paths held off."""
    pin_code_defaults(monkeypatch)
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", False)
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "off")
    monkeypatch.setattr(config, "ADAPTIVE_RUNNER_TRAIL_ENABLED", False)


def stamp(price=102.0, source="quote"):
    return {"exit_price": price, "price_source": source,
            "quote_ts": CLOSE_AT if source == "quote" else None,
            "bars_asof": "2026-10-06"}


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


def book(*legs) -> float:
    """costs.book over (fraction, exit_price, kind) legs, the plan's entry and stop."""
    return costs.book(of.INSTRUMENT.cost_model, direction="bullish", entry_price=100.0,
                      stop_loss=95.0,
                      legs=[{"fraction": f, "exit_price": p, "reason": "x", "kind": k}
                            for f, p, k in legs])[0]


def replay(p, df, *, when=None, trade=None):
    return of.replay_override(p, df, when or df.index[-1].date(), trade)


# -- the frame itself --------------------------------------------------------

def test_the_frame_sits_on_the_sessions_the_docstring_names():
    df = frame()
    assert [df.index[i].date() for i in (FILL_IDX, 16, OV_IDX, 19, 20, 25)] == [
        date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 9),
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
    assert row.close_date == date(2026, 10, 7)


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


def test_runner_trail_is_replayed_on_the_engine_frame():
    """The real frame gives 3.035; the engine frame clamps the override bar's
    range to its body, which moves the ATR the trail reads: 3.038."""
    row = replay(plan(partial=True, trail_atr_mult=1.0, override=stamp(111.0)),
                 partial_frame(TRAIL_ROWS))
    assert (row.status, row.engine_exit_reason) == ("resolved", "runner_trail")
    assert row.engine_r == pytest.approx(3.038, abs=0.002)


# -- open, stale -------------------------------------------------------------

def test_data_ending_before_the_hold_cap_is_open():
    row = replay(plan(), frame(n=22))     # walk_v2 clips at index 21, 15 + 8 > 21
    assert row.status == "open"
    assert (row.engine_r, row.delta_r, row.engine_usd, row.delta_usd,
            row.engine_exit_reason, row.outcome) == (None,) * 6
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
    assert row.engine_r is None and row.delta_r is None


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
    assert row.engine_r is None and row.delta_r is None


# -- split_affected ----------------------------------------------------------

def test_entry_outside_the_fill_bar_is_split_affected():
    assert replay(plan(), frame({FILL_IDX: (50.0, 50.5, 49.5, 50.0)})).status == "split_affected"


def test_entry_inside_the_two_percent_tolerance_is_not_split_affected():
    # 98.1 * 1.02 = 100.062 >= 100
    assert replay(plan(), frame({FILL_IDX: (98.0, 98.1, 97.5, 98.0)})).status == "resolved"


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
                 id="unstamped-override-session-missing"),
    pytest.param(plan(), _FULL.drop(_FULL.index[OV_IDX]), id="stamped-override-session-missing"),
    pytest.param(plan(stop_loss=101.0), _FULL, id="costs-book-refuses"),
])
def test_rows_the_replay_cannot_place_are_unreplayable(p, bars):
    row = of.replay_override(p, bars, LAST_DAY)
    assert row.status == "unreplayable"
    assert (row.engine_r, row.delta_r, row.outcome) == (None, None, None)
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


@pytest.mark.parametrize("p, rows, quiet, touching", [
    pytest.param(plan(), {}, (101.0, 104.0, 96.0, 101.0), (101.0, 102.0, 94.0, 101.0),
                 id="active"),
    pytest.param(plan(partial=True, trail_atr_mult=1.0, override=stamp(111.0)), TRAIL_ROWS,
                 (109.0, 115.0, 107.0, 111.5), (109.0, 115.0, 106.0, 111.5), id="trail"),
])
def test_override_bar_range_flips_resolved_and_ambiguous_never_engine_r(p, rows, quiet, touching):
    build = partial_frame if p.tp1_fraction < 1.0 else frame
    base = replay(p, build(rows))
    other = replay(p, build({**rows, OV_IDX: quiet}))
    flipped = replay(p, build({**rows, OV_IDX: touching}))
    assert base.status == other.status == "resolved"
    assert other.engine_r == base.engine_r          # the engine frame clamps that bar
    assert flipped.status == "ambiguous"


# -- cost parity, dollars, bulk ----------------------------------------------

def test_same_exit_price_and_kind_as_the_engine_gives_zero_delta():
    """Same price, both legs of kind stop. On the override session itself the
    row would be ambiguous by design, so the engine's stop sits two sessions on."""
    row = replay(plan(override=stamp(95.0)), frame({19: STOP_BAR}))
    assert row.status == "resolved"
    assert row.delta_r == 0.0
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


# -- the actual exit price (spec §3 session table) ----------------------------

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
def test_unstamped_exit_price_follows_the_session_table(at, expected):
    p = plan(override=UNSTAMPED, close_at=at)
    assert of.actual_exit(p, _priced(), of.assign_session(at)) == (*expected, True)


def test_a_stamped_price_wins_and_is_not_approx():
    hit = of.assign_session(CLOSE_AT)
    assert of.actual_exit(plan(), _priced(), hit) == (102.0, "quote", False)
    bar = plan(override=stamp(101.5, "bar_close"))
    assert of.actual_exit(bar, _priced(), hit) == (101.5, "bar_close", False)


@pytest.mark.parametrize("override", [UNSTAMPED, None, stamp(None, "none")],
                         ids=["no-key", "stamp-failed", "stamp-without-price"])
def test_a_row_without_a_stamped_price_is_approx(override):
    row = replay(plan(override=override), frame())
    assert (row.approx, row.price_source, row.status) == (True, "session_close", "resolved")
    assert row.actual_r == pytest.approx(book((1.0, 101.0, "stop")), abs=1e-3)


def test_no_bar_for_the_override_session_gives_no_price():
    df = _priced().drop(_priced().index[OV_IDX])
    assert of.actual_exit(plan(override=UNSTAMPED), df, of.assign_session(CLOSE_AT)) == (
        None, "none", True)
```

The scenario paths (`timeout` at 23, `stop` at 19, `tp1` at 18, `runner_be`/`runner_tp2` at 18, `runner_trail` at 20, the early exits at 15/16/17) were checked against today's `walk_v2`/`_fill_bar_v2` with these frames when this plan was written.

- [ ] **Step 2: Run it to verify it fails**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_fidelity_replay.py
```

Expected: FAIL with `AttributeError: module 'swingbot.core.analytics.override_fidelity' has no attribute 'replay_override'` (and `actual_exit`). `test_the_frame_sits_on_the_sessions_the_docstring_names` passes.

If an import fails instead, a V173-6..8 symbol is missing: stop and report. Do not re-create it.

- [ ] **Step 3: Implement**

At the top of `$WT/swingbot/core/analytics/override_fidelity.py`, make sure these imports exist (add only the missing ones; V173-7/8 already import most):

```python
import logging
from dataclasses import dataclass
from datetime import date

import pandas as pd

from swingbot.core.planning.exit_sim import ExitResult
```

Append at the end of the module:

```python
# --------------------------------------------------------------------------
# V173-9: the actual exit price and replay_override's seven statuses
# (spec §3). Precedence, first match wins: unreplayable -> stale ->
# split_affected -> parity_mismatch -> ambiguous -> open -> resolved.
# --------------------------------------------------------------------------

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
    price_source: str
    approx: bool
    actual_r: float


def _stamp(entry: dict | None) -> dict:
    """The CLOSED entry's `override` stamp; {} when the key is absent or the
    stamp failed (`override: null`). Never inferred (schema-evolution.md)."""
    stamp = (entry or {}).get("override")
    return stamp if isinstance(stamp, dict) else {}


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

    The stamp's exit_price when it has one (`quote` or `bar_close`, not
    approx); otherwise the override session bar's open or close, approx."""
    stamp = _stamp(override_entry(plan))
    if stamp.get("exit_price") is not None:
        return float(stamp["exit_price"]), str(stamp.get("price_source") or "quote"), False
    price, source = _bar_price(df, hit)
    return price, source, True


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
                   state=state, price_source=source, approx=approx,
                   actual_r=_booked_actual(plan, price, state))


def _split_affected(plan, df: pd.DataFrame, fill_idx: int) -> bool:
    """The raw fill price outside the cached fill bar (± SPLIT_TOLERANCE):
    the adjusted cache no longer shares the plan's price basis."""
    low = float(df["Low"].iloc[fill_idx]) * (1.0 - SPLIT_TOLERANCE)
    high = float(df["High"].iloc[fill_idx]) * (1.0 + SPLIT_TOLERANCE)
    return not low <= float(plan.entry_price) <= high


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


def _still_open(plan, eng: ExitResult, rp: _Replay) -> bool:
    """walk_v2 labels a data-end clip `timeout` too; only the hold cap resolves."""
    last = len(rp.df) - 1
    return (eng.legs[-1]["reason"] in TIMEOUT_REASONS and eng.exit_index == last
            and rp.fill_idx + hold_cap_bars(plan) > last)


def _status(plan, rp: _Replay, asof: date) -> tuple[str, ExitResult | None]:
    """The row's status after _prepare, and the engine-frame result when resolved.

    The real frame decides parity and ambiguity only; the engine arm is the
    engine frame (override bar clamped to its body), so the engine never
    sees the override session's range as a later path."""
    df = rp.df
    if df.index[-1].date() < asof:
        return "stale", None
    if _split_affected(plan, df, rp.fill_idx):
        return "split_affected", None
    if rp.ov_idx is None or rp.ov_idx < rp.fill_idx:
        return "unreplayable", None
    real = engine_path(plan, df, rp.fill_idx)
    if not real.legs:
        return "unreplayable", None
    if _parity_broken(plan, real, rp):
        return "parity_mismatch", None
    if _ambiguous(real, rp.ov_idx):
        return "ambiguous", None
    eng = engine_path(plan, engine_frame(df, rp.ov_idx), rp.fill_idx)
    if _still_open(plan, eng, rp):
        return "open", None
    return "resolved", eng


def _row(plan, entry: dict | None, hit: SessionHit | None, status: str,
         trade: dict | None, *, rp: _Replay | None = None, eng_r: float | None = None,
         exit_reason: str | None = None) -> OverrideRow:
    a_r = rp.actual_r if rp is not None else None
    d_r = round(a_r - eng_r, 3) if a_r is not None and eng_r is not None else None
    risk = dollar_risk(plan, trade) if rp is not None else None
    stamp = _stamp(entry)
    return OverrideRow(
        plan_id=plan.plan_id, ticker=plan.ticker, horizon=plan.horizon_key,
        direction=plan.direction, state_at_close=state_at_close(plan),
        close_date=hit.session if hit is not None else None,
        bulk=(entry or {}).get("reason") == "manual_bulk",
        approx=rp.approx if rp is not None else stamp.get("exit_price") is None,
        price_source=rp.price_source if rp is not None
        else str(stamp.get("price_source") or "none"),
        status=status, actual_r=a_r, engine_r=eng_r, delta_r=d_r,
        actual_usd=to_usd(a_r, risk), engine_usd=to_usd(eng_r, risk),
        delta_usd=to_usd(d_r, risk), engine_exit_reason=exit_reason,
        outcome=outcome_of(d_r), source="manual")


def replay_override(plan, bars: pd.DataFrame | None, asof: date,
                    trade: dict | None = None) -> OverrideRow:
    """One manual close against the engine left alone (spec §3).

    Pure: `bars` is the live scan's cache frame (never fetched here), `asof`
    the latest completed NYSE session, `trade` the linked paper trade (for
    dollars). A row it cannot place is `unreplayable`; it never raises."""
    entry = override_entry(plan)
    hit = assign_session((entry or {}).get("at"))
    try:
        rp = _prepare(plan, bars, hit)
    except _Unreplayable as exc:
        logging.getLogger(__name__).info("override_fidelity: %s unreplayable: %s",
                                         plan.plan_id, exc)
        return _row(plan, entry, hit, "unreplayable", trade)
    status, eng = _status(plan, rp, asof)
    if eng is None:
        return _row(plan, entry, hit, status, trade, rp=rp)
    return _row(plan, entry, hit, status, trade, rp=rp, eng_r=engine_r(plan, eng, rp.state),
                exit_reason=eng.legs[-1]["reason"])
```

If V173-7 already defines a module logger (`log = logging.getLogger(__name__)`), use `log.info(...)` instead of the inline `logging.getLogger(__name__)`.

- [ ] **Step 4: Run the new test and the earlier override tests**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_fidelity_replay.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_fidelity_sessions.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_fidelity_arms.py
```

Expected: all PASS, `0 failed`, `0 xfailed`.

If `test_runner_trail_is_replayed_on_the_engine_frame` lands away from 3.038, do not loosen it. Check that `engine_frame` replaces the override bar's `High`/`Low` with `max(Open, Close)`/`min(Open, Close)` and changes nothing else; the value was measured on that clamp, with code defaults pinned and the three flags above held off. If `test_the_frame_sits_on_the_sessions_the_docstring_names` fails, the calendar changed: fix the docstring dates and the `*_AT` constants together.

- [ ] **Step 5: Complexity**

```bash
python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/analytics/override_fidelity.py
```

Expected: no output (every function below grade C, i.e. CC < 11; `_status` is about 9, `_row` about 10).

- [ ] **Step 6: Commit on the branch**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides add swingbot/core/analytics/override_fidelity.py tests/analytics/test_override_fidelity_replay.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "feat(v173): replay_override -- actual exit price and the seven replay statuses"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

The last command checks the main tree stayed clean of branch edits.

### Task V173-10: `summarise`, the frozen verdict, ledger enums and `build_report`

**Model:** opus — statistical code feeding a frozen pre-registration

**Files:**
- Modify: `swingbot/core/analytics/override_fidelity.py` (append `summarise`; created by V173-7)
- Create: `swingbot/core/analytics/override_verdict.py`
- Modify: `swingbot/core/backtesting/instrument/stats.py:114-117` (`VERDICTS`)
- Modify: `tests/backtesting/test_instrument_stats_ledger.py:15-21` (the pinned `VERDICTS` tuple; not in the ledger row, see Step 6)
- Create: `tests/analytics/test_override_summary.py`
- Create: `tests/analytics/test_override_verdict.py`

**Interfaces:**
- Consumes: V173-7's `OverrideRow` (keyword-constructed with its 19 fields; `to_dict()` gives `close_date` as ISO), `outcome_of`, `is_override`, `STATUSES`, `EXCLUDED_STATUSES`, `VERDICT_FLOOR`, `WEEK_FLOOR`, `EXCLUDED_CAP`, `LEDGER_ID`; V173-9's `replay_override(plan, bars, asof, trade)`; `stats.week_cluster_bootstrap`, `stats.iso_week_key`, `stats.validate_ledger_row`, `stats.WEEK_BOOTSTRAP_RESAMPLES`, `stats.WEEK_BOOTSTRAP_SEED`.
- Produces:
  - `override_fidelity.summarise(rows: list[OverrideRow]) -> dict` with keys exactly `n_by_status, bulk_n, bulk_dates, approx_n, counted_n, sum_delta_r, sum_delta_usd, usd_missing_n, helped, hurt, neutral, splits`.
  - In `override_verdict.py`: `counted(rows) -> list`, `eligible(rows) -> list`, `conditions(rows) -> dict` (`n, weeks, open_n, excluded_share, evaluable`), `evaluate_verdict(rows) -> dict`, `recorded_verdict(ledger_rows: list[dict]) -> dict | None`, `verdict_payload(rows, ledger_rows) -> dict` (never evaluates), `ledger_row(verdict: dict, *, today: date) -> dict`, `build_report(plans, trades_by_plan, bars_fn, asof, ledger_rows, currency_symbol) -> dict` (keys exactly `rows, summary, verdict, engine_flags, asof, currency_symbol`); constants `SPEC_PATH`, `WAITING`, `COST`, `SAVED`, `INCONCLUSIVE`.
  - **Every verdict function accepts rows either as `OverrideRow` or as their `to_dict()` form**, so V173-11's script can pass `payload["rows"]` straight to `evaluate_verdict`.
  - `stats.VERDICTS` gains `"COST", "SAVED", "INCONCLUSIVE"` (appended, never `WAITING`).

**Shapes this task fixes** (the index names the keys but not these value types; V173-11..14 read them as written here):

- `n_by_status`: `{status: int}` over every value of `STATUSES`, counting **eligible** rows only (individual, stamped). Bulk rows are counted only in `bulk_n`, non-bulk approx rows only in `approx_n`, so `bulk_n + approx_n + sum(n_by_status.values()) == len(rows)` and no exclusion note counts a row twice.
- `bulk_dates`: `{iso_date: int}` sorted by date (one exclusion note line per key).
- `sum_delta_r` (3 dp) and `sum_delta_usd` (2 dp; rows without dollars skipped and counted in `usd_missing_n`) are over counted rows; both are `0.0` with no counted rows.
- `splits`: `{"state_at_close"|"horizon"|"direction": {value: {"n", "sum_delta_r", "sum_delta_usd"}}}` over counted rows, values sorted.
- Verdict: `excluded_share` rounded to 4 dp (the cap compares the unrounded share); `ci` is `[lo, hi]` (3 dp) or `None`; `recorded_on` is the ledger row's `date` or `None`; `needed` = `VERDICT_FLOOR`, `week_floor` = `WEEK_FLOOR`. Without a ledger row `verdict_payload` reports `WAITING` even when `evaluable` is true: only the script under `--production` evaluates.
- The ledger has no CI field (`stats.LEDGER_FIELDS` is closed), so `ledger_row` writes the interval into `hypothesis` as `95% CI [lo, hi]` and `recorded_verdict` parses it back.
- `engine_flags`: `{"stall_exit_enabled": bool, "runner_structure_exit": str}`, read live from `config`.
- `rows` are sorted newest `close_date` first, then `plan_id` descending.

- [ ] **Step 1: Write the failing summary test**

Create `$WT/tests/analytics/test_override_summary.py`:

```python
"""v173 §3: summarise -- descriptive totals over the counted rows only."""
from datetime import date

import pytest

from swingbot.core.analytics import override_fidelity as of

SUMMARY_KEYS = {"n_by_status", "bulk_n", "bulk_dates", "approx_n", "counted_n",
                "sum_delta_r", "sum_delta_usd", "usd_missing_n", "helped", "hurt",
                "neutral", "splits"}


def row(delta=0.2, day=date(2026, 8, 3), *, status="resolved", bulk=False, approx=False,
        usd=None, state="ACTIVE", horizon="2w", direction="bullish", plan_id="p"):
    resolved = status == "resolved"
    return of.OverrideRow(
        plan_id=plan_id, ticker="T", horizon=horizon, direction=direction,
        state_at_close=state, close_date=day, bulk=bulk, approx=approx,
        price_source="session_close" if approx else "quote", status=status,
        actual_r=delta, engine_r=0.0 if resolved else None,
        delta_r=delta if resolved else None, actual_usd=None, engine_usd=None,
        delta_usd=usd if resolved else None,
        engine_exit_reason="timeout" if resolved else None,
        outcome=of.outcome_of(delta if resolved else None), source="manual")


def test_keys_and_the_empty_summary():
    out = of.summarise([])
    assert set(out) == SUMMARY_KEYS
    assert out["n_by_status"] == {s: 0 for s in of.STATUSES}
    assert (out["bulk_n"], out["bulk_dates"], out["approx_n"], out["counted_n"]) == (0, {}, 0, 0)
    assert (out["sum_delta_r"], out["sum_delta_usd"], out["usd_missing_n"]) == (0.0, 0.0, 0)
    assert (out["helped"], out["hurt"], out["neutral"]) == (0, 0, 0)
    assert out["splits"] == {"state_at_close": {}, "horizon": {}, "direction": {}}


def test_rows_partition_into_counted_status_bulk_and_approx():
    rows = [row(0.2, usd=20.0), row(-0.3, usd=-30.0), row(0.05, usd=5.0),
            row(status="stale"),
            row(0.9, date(2026, 9, 30), bulk=True), row(-0.9, date(2026, 9, 30), bulk=True),
            row(1.5, approx=True)]
    out = of.summarise(rows)
    assert out["n_by_status"]["resolved"] == 3
    assert out["n_by_status"]["stale"] == 1
    assert sum(out["n_by_status"].values()) == 4
    assert (out["bulk_n"], out["bulk_dates"], out["approx_n"], out["counted_n"]) == (
        2, {"2026-09-30": 2}, 1, 3)
    assert out["bulk_n"] + out["approx_n"] + sum(out["n_by_status"].values()) == len(rows)
    assert out["sum_delta_r"] == pytest.approx(-0.05, abs=1e-9)
    assert out["sum_delta_usd"] == pytest.approx(-5.0, abs=1e-9)
    assert (out["helped"], out["hurt"], out["neutral"]) == (1, 1, 1)   # 0.05 sits on the band


def test_bulk_dates_one_key_per_day_sorted():
    rows = [row(bulk=True, day=date(2026, 9, 30)), row(bulk=True, day=date(2026, 8, 1)),
            row(bulk=True, day=date(2026, 9, 30))]
    assert list(of.summarise(rows)["bulk_dates"].items()) == [("2026-08-01", 1), ("2026-09-30", 2)]


def test_rows_without_dollars_stay_in_the_r_sum_and_are_counted_missing():
    out = of.summarise([row(0.4, usd=40.0), row(0.6, usd=None)])
    assert out["sum_delta_r"] == pytest.approx(1.0)
    assert out["sum_delta_usd"] == pytest.approx(40.0)
    assert out["usd_missing_n"] == 1


@pytest.mark.parametrize("delta, outcome", [(0.051, "helped"), (0.05, "neutral"),
                                            (-0.05, "neutral"), (-0.051, "hurt")])
def test_the_dead_band_is_frozen_at_five_hundredths(delta, outcome):
    assert of.DEAD_BAND == 0.05
    out = of.summarise([row(delta)])
    assert out[outcome] == 1


def test_splits_cover_state_horizon_and_direction_over_counted_rows():
    rows = [row(0.5, usd=50.0, state="PARTIAL", horizon="4w", direction="bearish"),
            row(-0.2, usd=-20.0, state="ACTIVE", horizon="2w"),
            row(-0.1, usd=None, state="ACTIVE", horizon="2w"),
            row(9.9, state="ACTIVE", bulk=True)]
    splits = of.summarise(rows)["splits"]
    assert splits["state_at_close"] == {
        "ACTIVE": {"n": 2, "sum_delta_r": -0.3, "sum_delta_usd": -20.0},
        "PARTIAL": {"n": 1, "sum_delta_r": 0.5, "sum_delta_usd": 50.0}}
    assert set(splits["horizon"]) == {"2w", "4w"}
    assert splits["direction"]["bearish"]["n"] == 1
    assert splits["direction"]["bullish"]["n"] == 2
```

- [ ] **Step 2: Write the failing verdict and report test**

Create `$WT/tests/analytics/test_override_verdict.py`:

```python
"""v173 §4: the frozen verdict, its one ledger row, and build_report."""
from datetime import date, timedelta

import pytest

from swingbot import config
from swingbot.core.analytics import override_fidelity as of
from swingbot.core.analytics import override_verdict as ov
from swingbot.core.backtesting.instrument import stats
from tests.analytics.test_override_fidelity_replay import (LAST_DAY, STOP_BAR, frame,
                                                           plan)
from tests.analytics.test_override_summary import row
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults

W0 = date(2026, 8, 3)
VERDICT_KEYS = {"state", "n", "needed", "weeks", "week_floor", "open_n", "excluded_share",
                "evaluable", "recorded", "recorded_on", "mean_delta_r", "ci"}
ROW_KEYS = {"plan_id", "ticker", "horizon", "direction", "state_at_close", "close_date",
            "bulk", "approx", "price_source", "status", "actual_r", "engine_r", "delta_r",
            "actual_usd", "engine_usd", "delta_usd", "engine_exit_reason", "outcome",
            "source"}


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    pin_code_defaults(monkeypatch)
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", False)
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "off")
    monkeypatch.setattr(config, "ADAPTIVE_RUNNER_TRAIL_ENABLED", False)


def spread(n, weeks, delta=0.3, **kw):
    """n counted rows over `weeks` distinct ISO weeks; `delta` may be a
    function of the week number."""
    return [row(delta(i % weeks) if callable(delta) else delta,
                W0 + timedelta(weeks=i % weeks), plan_id=f"p{i}", **kw) for i in range(n)]


def _no_bootstrap(*_a, **_k):
    raise AssertionError("the bootstrap must not run here")


# -- constants and ledger vocabulary ---------------------------------------------

def test_the_rule_constants_are_the_spec_values():
    assert (of.VERDICT_FLOOR, of.WEEK_FLOOR, of.EXCLUDED_CAP, of.DEAD_BAND) == (30, 10, 0.20, 0.05)
    assert of.LEDGER_ID == "v173-override-fidelity"
    assert ov.SPEC_PATH == "docs/superpowers/specs/2026-10-18-v173-execution-fidelity-overrides-design.md"


def test_the_ledger_accepts_the_three_outcomes_and_never_waiting():
    assert stats.VERDICTS[-3:] == ("COST", "SAVED", "INCONCLUSIVE")
    assert ov.WAITING not in stats.VERDICTS


# -- conditions: WAITING until every floor holds ---------------------------------

def test_29_rows_wait():
    out = ov.evaluate_verdict(spread(29, 10))
    assert set(out) == VERDICT_KEYS
    assert (out["state"], out["n"], out["needed"], out["evaluable"]) == ("WAITING", 29, 30, False)
    assert (out["mean_delta_r"], out["ci"], out["recorded"], out["recorded_on"]) == (
        None, None, False, None)


def test_30_rows_over_9_weeks_wait():
    out = ov.evaluate_verdict(spread(30, 9))
    assert (out["state"], out["weeks"], out["week_floor"]) == ("WAITING", 9, 10)


def test_one_eligible_open_row_holds_the_verdict():
    out = ov.evaluate_verdict(spread(30, 10) + [row(status="open")])
    assert (out["state"], out["open_n"], out["evaluable"]) == ("WAITING", 1, False)


def test_open_bulk_or_approx_rows_do_not_hold_it():
    rows = spread(30, 10) + [row(status="open", bulk=True), row(status="open", approx=True)]
    assert ov.conditions(rows)["evaluable"] is True


def test_exclusions_above_20_percent_wait_and_exactly_20_percent_does_not():
    over = spread(30, 10) + [row(status="ambiguous", plan_id=f"x{i}") for i in range(8)]
    assert ov.conditions(over)["excluded_share"] == pytest.approx(0.2105, abs=1e-4)
    assert ov.evaluate_verdict(over)["state"] == "WAITING"
    at_cap = spread(40, 10) + [row(status="stale", plan_id=f"x{i}") for i in range(10)]
    assert ov.conditions(at_cap)["excluded_share"] == 0.2
    assert ov.conditions(at_cap)["evaluable"] is True


def test_bulk_and_approx_rows_never_count_toward_n():
    rows = spread(29, 10) + [row(bulk=True)] * 5 + [row(approx=True)] * 5
    assert ov.conditions(rows)["n"] == 29
    assert [r.plan_id for r in ov.counted(rows)] == [f"p{i}" for i in range(29)]
    assert len(ov.eligible(rows)) == 29


# -- one evaluation ----------------------------------------------------------------

@pytest.mark.parametrize("delta, state", [
    (lambda w: -0.5 + 0.02 * w, "COST"),
    (lambda w: 0.5 - 0.02 * w, "SAVED"),
    (lambda w: 0.6 if w % 2 == 0 else -0.6, "INCONCLUSIVE"),
])
def test_seeded_delta_sets_give_each_outcome(delta, state):
    rows = spread(30, 10, delta)
    out = ov.evaluate_verdict(rows)
    assert (out["state"], out["evaluable"], out["recorded"]) == (state, True, False)
    lo, hi = out["ci"]
    assert lo <= out["mean_delta_r"] <= hi
    assert ov.evaluate_verdict(rows) == out          # seeded: the same draw every time


def test_dict_rows_evaluate_like_override_rows():
    rows = spread(30, 10, lambda w: -0.5 + 0.02 * w)
    assert ov.evaluate_verdict([r.to_dict() for r in rows]) == ov.evaluate_verdict(rows)


# -- the frozen ledger row ---------------------------------------------------------

def test_ledger_row_is_valid_and_round_trips_through_the_ledger(tmp_path):
    verdict = ov.evaluate_verdict(spread(30, 10, lambda w: -0.5 + 0.02 * w))
    entry = ov.ledger_row(verdict, today=date(2027, 3, 1))
    assert (entry["id"], entry["date"], entry["instrument"], entry["verdict"]) == (
        "v173-override-fidelity", "2027-03-01", "v2", "COST")
    assert (entry["n"], entry["exp_r"], entry["p"], entry["record"]) == (
        30, verdict["mean_delta_r"], None, ov.SPEC_PATH)
    path = tmp_path / "ledger.jsonl"
    stats.append_ledger_row(entry, path=path)
    recorded = ov.recorded_verdict(stats.load_ledger(path))
    assert recorded == {"state": "COST", "n": 30, "recorded_on": "2027-03-01",
                        "mean_delta_r": verdict["mean_delta_r"], "ci": verdict["ci"]}
    with pytest.raises(ValueError):
        stats.append_ledger_row(entry, path=path)      # written once


@pytest.mark.parametrize("verdict", [
    {"state": "WAITING", "evaluable": False, "recorded": False},
    {"state": "COST", "evaluable": True, "recorded": True, "n": 30, "mean_delta_r": -0.4,
     "ci": [-0.5, -0.3]},
])
def test_ledger_row_refuses_anything_but_a_fresh_evaluation(verdict):
    with pytest.raises(ValueError):
        ov.ledger_row(verdict, today=date(2027, 3, 1))


def test_a_recorded_verdict_is_shown_and_never_recomputed(monkeypatch):
    cost = ov.evaluate_verdict(spread(30, 10, lambda w: -0.5 + 0.02 * w))
    ledger = [{"id": "v139-arm-d", "verdict": "NO-LIFT"},
              ov.ledger_row(cost, today=date(2027, 3, 1))]
    monkeypatch.setattr(stats, "week_cluster_bootstrap", _no_bootstrap)
    shown = ov.verdict_payload(spread(40, 12, 0.5), ledger)   # live rows now look SAVED
    assert (shown["state"], shown["recorded"], shown["recorded_on"]) == ("COST", True, "2027-03-01")
    assert (shown["mean_delta_r"], shown["ci"]) == (cost["mean_delta_r"], cost["ci"])
    assert (shown["n"], shown["weeks"]) == (40, 12)          # descriptive figures stay live


def test_without_a_ledger_row_the_payload_waits_even_when_evaluable(monkeypatch):
    monkeypatch.setattr(stats, "week_cluster_bootstrap", _no_bootstrap)
    out = ov.verdict_payload(spread(30, 10, 0.5), [])
    assert (out["state"], out["evaluable"], out["recorded"], out["ci"]) == (
        "WAITING", True, False, None)


# -- build_report ------------------------------------------------------------------

def _book():
    return [plan(plan_id="a", ticker="AAA"),
            plan(plan_id="b", ticker="BBB", reason="manual_bulk",
                 close_at="2026-10-08T18:00:00+00:00"),
            plan(plan_id="c", ticker="AAA", reason="tp1_runner_trail"),   # not an override
            plan(plan_id="d", ticker="BAD")]


def test_report_payload_shape(monkeypatch):
    monkeypatch.setattr(stats, "week_cluster_bootstrap", _no_bootstrap)
    calls = []

    def bars_fn(ticker):
        calls.append(ticker)
        if ticker == "BAD":
            raise OSError("corrupt cache file")
        return frame({19: STOP_BAR})

    out = ov.build_report(_book(), {"a": {"id": "t", "shares": 10}}, bars_fn, LAST_DAY, [], "$")
    assert set(out) == {"rows", "summary", "verdict", "engine_flags", "asof", "currency_symbol"}
    assert (out["asof"], out["currency_symbol"]) == ("2026-10-19", "$")
    assert out["engine_flags"] == {"stall_exit_enabled": False, "runner_structure_exit": "off"}
    assert sorted(calls) == ["AAA", "BAD", "BBB"]               # once per ticker
    assert [r["plan_id"] for r in out["rows"]] == ["b", "d", "a"]   # newest close first
    assert set(of.ROW_FIELDS) == ROW_KEYS                       # V173-7's row contract
    assert all(set(r) == ROW_KEYS for r in out["rows"])
    by_id = {r["plan_id"]: r for r in out["rows"]}
    assert by_id["d"]["status"] == "unreplayable"
    assert by_id["b"]["bulk"] is True
    assert by_id["a"]["delta_usd"] is not None and by_id["b"]["delta_usd"] is None
    assert out["summary"]["bulk_dates"] == {"2026-10-08": 1}
    assert set(out["verdict"]) == VERDICT_KEYS
    assert out["verdict"]["state"] == "WAITING"


def test_report_with_no_overrides_is_empty_not_an_error():
    out = ov.build_report([plan(reason="tp1_runner_trail")], {}, lambda t: None, LAST_DAY, [], "$")
    assert out["rows"] == []
    assert out["summary"]["counted_n"] == 0
    assert out["verdict"]["state"] == "WAITING"
```

Note on `_book()`: plans `a` and `d` close on 2026-10-07 and `b` on 2026-10-08, so the order is `b` first, then `d` before `a` (same date, `plan_id` descending).

- [ ] **Step 3: Run both to verify they fail**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_summary.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_verdict.py
```

Expected: the first FAILS with `AttributeError: ... has no attribute 'summarise'` (the dead-band cases that only read `DEAD_BAND` still fail on `summarise`). The second fails at collection with `ModuleNotFoundError: No module named 'swingbot.core.analytics.override_verdict'`.

- [ ] **Step 4: Add the three ledger verdicts**

In `$WT/swingbot/core/backtesting/instrument/stats.py`, replace the `VERDICTS` block (the comment line above it included):

```python
#: v140 appends the idea screen's three verdicts and its instrument; v173
#: appends the override-fidelity outcomes. WAITING is never written: a
#: verdict that is not yet evaluable has no ledger row. Existing rows are
#: untouched (a ledger row is never edited).
VERDICTS = ("PASS", "FAIL", "NO-LIFT", "UNMEASURABLE", "WITHDRAWN", "OPEN",
            "SCREEN-PASS", "SCREEN-FAIL", "SCREEN-UNDERPOWERED",
            "COST", "SAVED", "INCONCLUSIVE")
```

- [ ] **Step 5: Implement `summarise`**

At the top of `$WT/swingbot/core/analytics/override_fidelity.py` add `from collections import Counter` if missing. Append at the end of the module:

```python
# --------------------------------------------------------------------------
# V173-10: descriptive totals (spec §3). Counted rows are individual,
# stamped and resolved; bulk and approx rows are shown, never summed.
# --------------------------------------------------------------------------

_SPLIT_KEYS = ("state_at_close", "horizon", "direction")


def _sum_r(rows) -> float:
    return round(sum(r.delta_r for r in rows), 3)


def _sum_usd(rows) -> float:
    return round(sum(r.delta_usd for r in rows if r.delta_usd is not None), 2)


def _split(rows, key: str) -> dict:
    groups: dict = {}
    for r in rows:
        groups.setdefault(getattr(r, key), []).append(r)
    return {value: {"n": len(group), "sum_delta_r": _sum_r(group),
                    "sum_delta_usd": _sum_usd(group)}
            for value, group in sorted(groups.items())}


def _bulk_dates(rows) -> dict[str, int]:
    tally = Counter(r.close_date.isoformat() if r.close_date else "unknown"
                    for r in rows if r.bulk)
    return dict(sorted(tally.items()))


def summarise(rows: list[OverrideRow]) -> dict:
    """N by status, bulk/approx counts, ΣΔR and Σ$ and helped/hurt/neutral
    over counted rows, and the splits by state, horizon and direction."""
    rows = list(rows)
    eligible = [r for r in rows if not r.bulk and not r.approx]
    counted = [r for r in eligible if r.status == "resolved"]
    by_status = Counter(r.status for r in eligible)
    outcomes = Counter(r.outcome for r in counted)
    return {
        "n_by_status": {status: by_status[status] for status in STATUSES},
        "bulk_n": sum(1 for r in rows if r.bulk),
        "bulk_dates": _bulk_dates(rows),
        "approx_n": sum(1 for r in rows if r.approx and not r.bulk),
        "counted_n": len(counted),
        "sum_delta_r": _sum_r(counted),
        "sum_delta_usd": _sum_usd(counted),
        "usd_missing_n": sum(1 for r in counted if r.delta_usd is None),
        "helped": outcomes["helped"], "hurt": outcomes["hurt"],
        "neutral": outcomes["neutral"],
        "splits": {key: _split(counted, key) for key in _SPLIT_KEYS},
    }
```

- [ ] **Step 6: Implement `override_verdict.py`**

Create `$WT/swingbot/core/analytics/override_verdict.py`:

```python
"""v173 §4: the frozen verdict on manual overrides, and the report payload.

The rule is frozen in the spec and evaluated once. Population: individual
(not bulk), stamped (not approx), resolved rows. It becomes evaluable when
there are >= VERDICT_FLOOR of them over >= WEEK_FLOOR ISO weeks, no
eligible row is still open, and excluded statuses are <= EXCLUDED_CAP of
the eligible rows. The first evaluating run of the report script (under
--production, on the VM) writes one ledger row; from then on every reader
shows that row and never recomputes it, because watching a live interval
until it crosses zero inflates false positives.

Pure: no store, no network. build_report takes its inputs from the caller
(the report script, the API route) and never evaluates the verdict.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Callable

import numpy as np
import pandas as pd

from swingbot import config
from swingbot.core.analytics import override_fidelity as ofi
from swingbot.core.backtesting.instrument import stats

log = logging.getLogger(__name__)

SPEC_PATH = "docs/superpowers/specs/2026-10-18-v173-execution-fidelity-overrides-design.md"
WAITING = "WAITING"
COST, SAVED, INCONCLUSIVE = "COST", "SAVED", "INCONCLUSIVE"
_EVALUATED = (COST, SAVED, INCONCLUSIVE)
_HYPOTHESIS = ("Manual overrides vs the v2 engine left alone: mean delta R over stamped "
               "individual resolved overrides, week-cluster bootstrap 95% CI [{lo:.3f}, {hi:.3f}]")
_CI_RE = re.compile(r"95% CI \[(-?\d+(?:\.\d+)?), (-?\d+(?:\.\d+)?)\]")


@dataclass(frozen=True)
class _View:
    """The fields the rule reads, from an OverrideRow or its to_dict() form.
    `entry_date` is the name stats.group_by_week reads."""
    bulk: bool
    approx: bool
    status: str
    delta_r: float | None
    entry_date: date | None


def _field(row, name: str):
    return row.get(name) if isinstance(row, dict) else getattr(row, name)


def _day(value) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _view(row) -> _View:
    return _View(bulk=bool(_field(row, "bulk")), approx=bool(_field(row, "approx")),
                 status=_field(row, "status"), delta_r=_field(row, "delta_r"),
                 entry_date=_day(_field(row, "close_date")))


def _is_eligible(view: _View) -> bool:
    return not view.bulk and not view.approx


def _is_counted(view: _View) -> bool:
    return _is_eligible(view) and view.status == "resolved"


def eligible(rows) -> list:
    """Individual, stamped rows (any status), as given."""
    return [r for r in rows if _is_eligible(_view(r))]


def counted(rows) -> list:
    """The verdict population: individual, stamped, resolved rows, as given."""
    return [r for r in rows if _is_counted(_view(r))]


def conditions(rows) -> dict:
    """The four floors of spec §4, evaluated on the rows as they are now."""
    views = [_view(r) for r in rows]
    elig = [v for v in views if _is_eligible(v)]
    population = [v for v in elig if v.status == "resolved"]
    weeks = len({stats.iso_week_key(v.entry_date) for v in population})
    open_n = sum(1 for v in elig if v.status == "open")
    excluded = sum(1 for v in elig if v.status in ofi.EXCLUDED_STATUSES)
    share = excluded / len(elig) if elig else 0.0
    evaluable = (len(population) >= ofi.VERDICT_FLOOR and weeks >= ofi.WEEK_FLOOR
                 and open_n == 0 and share <= ofi.EXCLUDED_CAP)
    return {"n": len(population), "weeks": weeks, "open_n": open_n,
            "excluded_share": share, "evaluable": evaluable}


def _payload(cond: dict, state: str, *, recorded: bool = False,
             recorded_on: str | None = None, mean: float | None = None,
             ci: list | None = None) -> dict:
    return {"state": state, "n": cond["n"], "needed": ofi.VERDICT_FLOOR,
            "weeks": cond["weeks"], "week_floor": ofi.WEEK_FLOOR,
            "open_n": cond["open_n"], "excluded_share": round(cond["excluded_share"], 4),
            "evaluable": cond["evaluable"], "recorded": recorded,
            "recorded_on": recorded_on, "mean_delta_r": mean, "ci": ci}


def _mean_delta(baseline, _component) -> float | None:
    return float(np.mean([v.delta_r for v in baseline])) if baseline else None


def _state_for(lo: float, hi: float) -> str:
    if hi < 0:
        return COST
    if lo > 0:
        return SAVED
    return INCONCLUSIVE


def evaluate_verdict(rows) -> dict:
    """The one evaluation: WAITING until conditions() holds, then the
    week-clustered bootstrap of mean ΔR (seeded) and its 95% interval.
    Called only by the report script under --production."""
    cond = conditions(rows)
    if not cond["evaluable"]:
        return _payload(cond, WAITING)
    population = [v for v in map(_view, rows) if _is_counted(v)]
    draws = stats.week_cluster_bootstrap(population, [], _mean_delta,
                                         n_resamples=stats.WEEK_BOOTSTRAP_RESAMPLES,
                                         seed=stats.WEEK_BOOTSTRAP_SEED)
    lo, hi = (float(x) for x in np.percentile(draws, [2.5, 97.5]))
    mean = round(float(np.mean([v.delta_r for v in population])), 3)
    return _payload(cond, _state_for(lo, hi), mean=mean, ci=[round(lo, 3), round(hi, 3)])


def recorded_verdict(ledger_rows) -> dict | None:
    """The frozen v173 ledger row, read back; None when not yet written."""
    for entry in ledger_rows or ():
        if entry.get("id") != ofi.LEDGER_ID:
            continue
        match = _CI_RE.search(entry.get("hypothesis") or "")
        ci = [float(match.group(1)), float(match.group(2))] if match else None
        return {"state": entry["verdict"], "n": entry["n"], "recorded_on": entry["date"],
                "mean_delta_r": entry["exp_r"], "ci": ci}
    return None


def verdict_payload(rows, ledger_rows) -> dict:
    """What the API and every non-evaluating run show. Never evaluates: the
    state is the recorded verdict, or WAITING; the counts stay live."""
    cond = conditions(rows)
    recorded = recorded_verdict(ledger_rows)
    if recorded is None:
        return _payload(cond, WAITING)
    return _payload(cond, recorded["state"], recorded=True,
                    recorded_on=recorded["recorded_on"],
                    mean=recorded["mean_delta_r"], ci=recorded["ci"])


def ledger_row(verdict: dict, *, today: date) -> dict:
    """The one pre-registration row for a fresh COST/SAVED/INCONCLUSIVE
    evaluation; anything else (WAITING, an already recorded verdict) raises."""
    if (verdict.get("recorded") or verdict.get("state") not in _EVALUATED
            or not verdict.get("evaluable")):
        raise ValueError("only a fresh COST/SAVED/INCONCLUSIVE evaluation is written")
    lo, hi = verdict["ci"]
    entry = {"id": ofi.LEDGER_ID, "date": today.isoformat(),
             "hypothesis": _HYPOTHESIS.format(lo=lo, hi=hi), "instrument": "v2",
             "n": int(verdict["n"]), "exp_r": float(verdict["mean_delta_r"]), "p": None,
             "verdict": verdict["state"], "record": SPEC_PATH}
    stats.validate_ledger_row(entry)
    return entry


def _bars_for(bars_fn: Callable[[str], pd.DataFrame | None], ticker: str,
              cache: dict) -> pd.DataFrame | None:
    """One cache read per ticker; an unreadable file is an unreplayable row."""
    if ticker not in cache:
        try:
            cache[ticker] = bars_fn(ticker)
        except Exception as exc:   # noqa: BLE001 -- one bad file never fails the report
            log.warning("override_verdict: bars for %s unreadable: %s", ticker, exc)
            cache[ticker] = None
    return cache[ticker]


def _engine_flags() -> dict:
    """The exit flags walk_v2 reads live, echoed so a reader can see what
    the replay ran under."""
    return {"stall_exit_enabled": bool(config.STALL_EXIT_ENABLED),
            "runner_structure_exit": str(config.RUNNER_STRUCTURE_EXIT)}


def build_report(plans: list, trades_by_plan: dict[str, dict],
                 bars_fn: Callable[[str], pd.DataFrame | None], asof: date,
                 ledger_rows: list[dict], currency_symbol: str) -> dict:
    """The report payload (index § Report payload). Replays every manual
    close, newest first; the verdict is the recorded one or WAITING."""
    cache: dict = {}
    trades = trades_by_plan or {}
    rows = [ofi.replay_override(p, _bars_for(bars_fn, p.ticker, cache), asof,
                                trades.get(p.plan_id))
            for p in plans if ofi.is_override(p)]
    rows.sort(key=lambda r: (r.close_date or date.min, r.plan_id), reverse=True)
    return {"rows": [r.to_dict() for r in rows], "summary": ofi.summarise(rows),
            "verdict": verdict_payload(rows, ledger_rows), "engine_flags": _engine_flags(),
            "asof": asof.isoformat(), "currency_symbol": currency_symbol}
```

Then update the pinned vocabulary in `$WT/tests/backtesting/test_instrument_stats_ledger.py` (`test_fields_and_vocabularies_are_the_plan_set`, lines 15-21). The ledger row for V173-10 does not list this file; it is the one existing test that pins `VERDICTS`, so it changes here:

```python
    assert stats.VERDICTS == ("PASS", "FAIL", "NO-LIFT", "UNMEASURABLE",
                              "WITHDRAWN", "OPEN", "SCREEN-PASS", "SCREEN-FAIL",
                              "SCREEN-UNDERPOWERED", "COST", "SAVED", "INCONCLUSIVE")
```

The research page's `VERDICT_TONE` (`frontend/src/app/workspaces/research/research.ts:32`) shows an unlisted verdict as neutral, which is right for all three. It stays unchanged.

- [ ] **Step 7: Run the new tests and the ledger tests**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_summary.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_verdict.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/backtesting/test_instrument_stats_ledger.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_fidelity_replay.py
```

Expected: all PASS, `0 failed`, `0 xfailed`. Each seeded evaluation draws 10,000 resamples over 10 weeks. If `test_override_verdict.py` takes more than about 15 s, report it; do not lower the resample count (it is the pre-registered `stats.WEEK_BOOTSTRAP_RESAMPLES`).

If the INCONCLUSIVE case comes out COST or SAVED, the bootstrap is not pooling weeks: check that `_View.entry_date` carries the row's `close_date`. Do not change the seeded deltas.

- [ ] **Step 8: Complexity**

```bash
python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/analytics/override_fidelity.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/analytics/override_verdict.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/backtesting/instrument/stats.py
```

Expected: no output (every function below grade C). If `summarise` or `conditions` grades C, move one comprehension into a named helper: the result stays identical and the tests above must stay green unchanged.

- [ ] **Step 9: Commit on the branch (two scoped commits)**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides add swingbot/core/backtesting/instrument/stats.py tests/backtesting/test_instrument_stats_ledger.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "feat(v173): ledger verdicts COST, SAVED, INCONCLUSIVE"
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides add swingbot/core/analytics/override_fidelity.py swingbot/core/analytics/override_verdict.py tests/analytics/test_override_summary.py tests/analytics/test_override_verdict.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "feat(v173): override summary, the frozen verdict and build_report"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

The last command checks the main tree stayed clean of branch edits.

