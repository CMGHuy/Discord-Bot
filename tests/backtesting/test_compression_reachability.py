"""V119-9: the compression short is reachable the same way through the live scan
(strategy pass + PlanManager) and the research replay (StrategyEngine), and the
live mask stays closed.

One synthetic stock compresses, releases bearish on the signal bar, and then:
  full path  - the resting sell-stop triggers on session 1, neither stop nor target
               prints, and the position closes on the tenth session;
  expiry     - session 1 never touches the trigger, so the stop-entry expires;
  earnings   - a report reacts inside sessions 1-10, so no plan is ever built.
Live and replay must agree on mode, trigger, stop, target, expiry and the exit bar.
The nearest lower support is pinned through the shared level builder (one fixed
support, as in tests/planning/test_compression_short_plan.py) so both paths size
from the same structure.
"""
import contextlib
import datetime as dt
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.backtesting.arms.strategy_engine import (
    CompressionContextError, CompressionResearchContext, StrategyEngine)
from swingbot.core.market import entry_filters
from swingbot.core.market import levels as levels_mod
from swingbot.core.market.events import EarningsSnapshot
from swingbot.core.market.levels import Level
from swingbot.core.market.session import nyse_calendar
from swingbot.core.market.short_entries import compression_short_frame
from swingbot.core.market.strategy_types import (COMPRESSION_SHORT, STRATEGY_GATES,
                                                 admits)
from swingbot.core.planning import plan_manager as pm
from swingbot.core.planning import time_exit as te
from swingbot.core.planning.exit_sim import simulate_exit
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.scanning import compression_context as cc
from swingbot.core.scanning import strategy_pass as sp
from tests.helpers import make_ohlcv
from tests.market.test_squeeze_release_series import _frame

ET, UTC, CAL = ZoneInfo("America/New_York"), dt.timezone.utc, nyse_calendar()
HZ, TARGET = "2w", 95.40
BEAR = {"broad": True, "isolated": False}


@pytest.fixture(autouse=True)
def pins(monkeypatch):
    for name in ("LEVEL_LIFECYCLE_STOPS_ENABLED", "STALL_EXIT_ENABLED",
                 "REGIME_GATES_ENABLED", "DATA_DRIVEN_STOPS_ENABLED"):
        monkeypatch.setattr(config, name, False, raising=False)
    monkeypatch.setattr(levels_mod, "build_level_map",
                        lambda *a, **k: ([Level(price=TARGET, sources=["Swing low", "Pivot low"])], []))


# -- synthetic world -----------------------------------------------------------------

def _release_frame():
    """~97 bars: 40 noisy bars, a 56-bar compression base, the bearish release bar last."""
    base = _frame([96])
    rng = np.random.default_rng(11)
    prefix = make_ohlcv(list(100 + rng.normal(0, 1.5, 40)), start="2025-11-03", spread=0.0005)
    prefix = prefix[prefix.index < base.index[0]]
    return pd.concat([prefix, base])


STOCK = _release_frame()
SIGNAL = STOCK.index[-1]
SIGNAL_DAY = SIGNAL.date()
SESSIONS = CAL.sessions(SIGNAL_DAY + dt.timedelta(days=1), SIGNAL_DAY + dt.timedelta(days=40))
FILL_DAY, TENTH = SESSIONS[0], te.tenth_session(SESSIONS[0], CAL)
DECISION = datetime.combine(SIGNAL_DAY, dt.time(17), tzinfo=ET)       # after the signal close


def _series(step, end_day=SIGNAL_DAY, n=260, level=300.0):
    start = (pd.Timestamp(end_day) - pd.tseries.offsets.BDay(n - 1)).date().isoformat()
    return make_ohlcv([level + step * i for i in range(n)], start=start)


FALLING_SPY, RISING_SPY, SECTOR = _series(-0.5), _series(0.5), _series(1.0, level=100.0)

FILL_BAR = (95.97, 96.00, 95.90, 95.95)        # touches the 95.94 trigger, no stop, no target
DRIFT_BAR = (95.90, 96.00, 95.80, 95.90)       # misses stop (~96.15) and target (95.40)
NO_TOUCH_BAR = (96.05, 96.12, 96.00, 96.10)    # never reaches the trigger, never invalidates


def _extend(frame, bars):
    rows = pd.DataFrame(list(bars), columns=["Open", "High", "Low", "Close"],
                        index=pd.DatetimeIndex([pd.Timestamp(d) for d in SESSIONS[:len(bars)]]))
    rows["Volume"] = 1_000_000.0
    return pd.concat([frame, rows])


FULL_PATH = _extend(STOCK, [FILL_BAR] + [DRIFT_BAR] * 11)
EXPIRES = _extend(STOCK, [NO_TOUCH_BAR] + [DRIFT_BAR] * 11)


def _at(day, hour, minute=0, second=0):
    return datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=ET)


def _snapshot(*reports, observed=DECISION):
    return EarningsSnapshot(observed_at=observed, reports=tuple(reports), query_ok=True, source="test")


CLEAR = _snapshot()
IN_WINDOW = _snapshot(_at(SESSIONS[4], 7))      # before-open report on session 5


def _context(*, spy=FALLING_SPY, snapshot=CLEAR, sector=SECTOR):
    return CompressionResearchContext(
        spy=spy, sector_of=lambda ticker: sector,
        snapshot_of=lambda ticker, decided_at: snapshot)


def _replay(frame, context, ticker="ABC"):
    engine = StrategyEngine([COMPRESSION_SHORT], compression_context=context)
    trades = list(engine.iter_trades(ticker, frame, COMPRESSION_SHORT, HZ,
                                     (str(STOCK.index[0].date()), str(SIGNAL_DAY)), None))
    return engine, trades


# -- live harness --------------------------------------------------------------------

class _Store:
    def __init__(self):
        self.rows = []

    def all(self):
        return list(self.rows)

    def add(self, plan):
        self.rows.append(plan)


class _Log:
    def __init__(self):
        self.opened = []

    def open_trade_for_ticker(self, ticker):
        return None

    def log_trade(self, **row):
        self.opened.append(row)


def _live_pass(frame=STOCK, *, mode="shadow", live_allow=(), spy=FALLING_SPY, snapshot=CLEAR,
               hooks=True, open_cell=False):
    store, log = _Store(), _Log()
    kwargs = {}
    if hooks:
        kwargs = dict(compression_of=lambda t, f: cc.compression_mode_for(f, spy, SECTOR, now=DECISION),
                      earnings_of=lambda t: snapshot)
    ctx = (entry_filters.gate_override(COMPRESSION_SHORT, {"cells": {("bearish", HZ)}})
           if open_cell else contextlib.nullcontext())
    with ctx:
        result = sp.run_strategy_pass(
            ["ABC"], {"ABC": frame}, now=DECISION, horizons=[HZ], spy_df=spy, regimes=None,
            rs_combined_of=lambda t: None, mode=mode, live_allow=set(live_allow),
            trade_log=log, plan_store=store, **kwargs)
    return result, store, log


def _live_lifecycle(monkeypatch, plan, *, fill_price, hold_price, auction=95.90, fills=True):
    """Drive the plan through PlanManager on the synthetic sessions; returns (events, plan)."""
    clock = {"now": _at(SESSIONS[0], 10)}
    monkeypatch.setattr(PlanManager, "_now",
                        lambda self: clock["now"].astimezone(UTC).isoformat())
    store = PlanStore()
    store.add(plan)
    manager = PlanManager(store, lambda ticker: clock["price"], auction_close_fn=lambda t, d: (
        auction, "official_auction", _at(d, 16, 0, 5).astimezone(UTC).isoformat()))
    events = []
    clock["price"] = fill_price if fills else 96.10
    for number, day in enumerate(SESSIONS[:10], start=1):
        clock["now"], clock["price"] = _at(day, 10), (fill_price if number == 1 and fills else hold_price)
        events += manager.poll(now=clock["now"])
    clock["now"] = _at(TENTH, 15, 35)
    events += manager.poll(now=clock["now"])
    clock["now"] = _at(TENTH, 16, 0, 20)
    events += manager.poll(now=clock["now"])
    return events, store.get(plan.plan_id)


def _only(events, name):
    return [e for e in events if e.transition == name]


# -- the mask ------------------------------------------------------------------------

def test_live_mask_and_global_alert_mode_stay_closed():
    assert STRATEGY_GATES[COMPRESSION_SHORT] == {"directions": ()}
    assert config.STRATEGY_ALERTS_MODE == "off"
    for direction in ("bullish", "bearish"):
        for horizon in ("1w", "2w", "4w", "2m"):
            assert not admits(COMPRESSION_SHORT, direction, horizon)


def test_research_override_is_scoped_and_admits_only_the_bearish_2w_cell(monkeypatch):
    before = dict(STRATEGY_GATES[COMPRESSION_SHORT])
    seen = {}
    real = entry_filters.entries_for

    def spy_on_mask(strategy, df, horizon_key, *a, **k):
        seen["admits"] = {(d, h) for d in ("bullish", "bearish") for h in ("1w", "2w", "4w")
                          if admits(COMPRESSION_SHORT, d, h)}
        seen["closed"] = {s: any(admits(s, d, h) for d in ("bullish", "bearish") for h in ("1w", "2w"))
                          for s in ("Bull Trap", "Vol Expansion Breakdown", "Earnings Gap Drift",
                                    "Downtrend Overbought Fade")}
        return real(strategy, df, horizon_key, *a, **k)

    monkeypatch.setattr(entry_filters, "entries_for", spy_on_mask)
    _replay(FULL_PATH, _context())
    assert seen["admits"] == {("bearish", "2w")}                 # no legacy 1w, no 4w
    assert not any(seen["closed"].values())                       # closed v104/v113 cells stay closed
    assert STRATEGY_GATES[COMPRESSION_SHORT] == before            # the global mask is untouched


# -- one full path through both channels -------------------------------------------------

def test_full_path_live_and_replay_agree_on_plan_and_the_tenth_session_exit(monkeypatch):
    assert bool(compression_short_frame(STOCK, HZ)["signal"].iloc[-1])

    shadow, _, _ = _live_pass()                                  # mask closed: raw signal, audit plan only
    (record,) = shadow.compression_shadow
    live, store, log = _live_pass(open_cell=True)                # the cell opened, scoped to this scan
    assert (live.compression_rejected, live.alerts, log.opened) == (0, [], [])
    (live_plan,) = live.plans
    assert (record["plan"]["trigger_price"], record["plan"]["stop_loss"], record["plan"]["tp1"]) == \
           (live_plan.trigger_price, live_plan.stop_loss, live_plan.tp1)
    engine, trades = _replay(FULL_PATH, _context())
    ((date, replay_plan, result),) = trades

    assert live_plan.entry_context["compression_mode"] == replay_plan.entry_context["compression_mode"] == "broad"
    assert live_plan.entry_context["compression_bar_date"] == replay_plan.entry_context["compression_bar_date"] \
        == SIGNAL_DAY.isoformat() == date
    assert live_plan.trigger_price == replay_plan.trigger_price == 95.94
    assert live_plan.stop_loss == replay_plan.stop_loss > float(STOCK["High"].iloc[-1])
    assert live_plan.tp1 == replay_plan.tp1 == TARGET
    assert (live_plan.expiry_bars, live_plan.hold_cap_bars, live_plan.tp2, live_plan.tp1_fraction) == \
           (replay_plan.expiry_bars, replay_plan.hold_cap_bars, replay_plan.tp2, replay_plan.tp1_fraction) == \
           (1, 10, None, 1.0)

    # replay exit: filled on session 1, neither stop nor target, closes on the tenth session
    fill_index = FULL_PATH.index.get_loc(pd.Timestamp(FILL_DAY))
    assert result.entry_index == fill_index and result.outcome == "timeout"
    assert FULL_PATH.index[result.exit_index].date() == TENTH == te.tenth_session(FILL_DAY, CAL)
    assert result.legs[-1]["reason"] == "time_exit" and result.legs[-1]["price_basis"] == "daily_close_proxy"

    # live: the same plan through PlanManager, official-auction close at the tenth session
    events, live_after = _live_lifecycle(monkeypatch, live_plan, fill_price=95.94, hold_price=95.90)
    (filled,) = _only(events, "filled")
    assert filled.detail["entry_price"] == result.entry_price == 95.94
    (closed,) = _only(events, "closed")
    leg = closed.detail["leg"]
    assert closed.detail["reason"] == leg["reason"] == result.legs[-1]["reason"] == "time_exit"
    assert datetime.fromisoformat(leg["closed_at"]).astimezone(ET).date() == TENTH
    assert leg["price_basis"] == "official_auction"
    assert live_after.status == "CLOSED"


# -- the second: expiry --------------------------------------------------------------------------

def test_expiry_path_live_and_replay_both_expire_without_a_fill(monkeypatch):
    live, _, _ = _live_pass(open_cell=True)
    (plan,) = live.plans
    engine, trades = _replay(EXPIRES, _context())
    assert trades == []
    assert engine.compression_reasons["expired"] == 1
    assert engine.compression_reasons_by_mode["broad:expired"] == 1

    events, after = _live_lifecycle(monkeypatch, plan, fill_price=96.10, hold_price=96.10, fills=False)
    (expired,) = _only(events, "cancelled_expired")
    assert expired.detail["eligible_session"] == FILL_DAY.isoformat()
    assert after.status == "CANCELLED" and _only(events, "filled") == []


# -- the third: earnings ------------------------------------------------------------------------------

def test_earnings_inside_the_window_excludes_the_candidate_in_both_channels():
    live, _, _ = _live_pass(snapshot=IN_WINDOW)
    assert live.plans == [] and live.alerts == [] and live.compression_rejected == 1
    assert live.compression_reasons == {"earnings_within_window": 1}
    assert live.compression_reasons_by_mode == {"broad:earnings_within_window": 1}
    assert live.earnings_excluded_by_mode == {"broad": 1}

    engine, trades = _replay(FULL_PATH, _context(snapshot=IN_WINDOW))
    assert trades == []
    assert engine.compression_reasons == {"earnings_within_window": 1}
    assert engine.compression_reasons_by_mode == {"broad:earnings_within_window": 1}


def test_a_snapshot_observed_after_the_decision_is_not_known_in_replay():
    later = _snapshot(observed=DECISION + dt.timedelta(hours=1))
    engine, trades = _replay(FULL_PATH, _context(snapshot=later))
    assert trades == [] and engine.compression_reasons == {"earnings_stale": 1}


# -- mode parity, isolated arm ----------------------------------------------------------------------------

def test_live_and_replay_select_the_same_isolated_mode():
    stock = STOCK.copy()
    live_mode = cc.compression_mode_for(stock, RISING_SPY, SECTOR, now=DECISION)
    assert live_mode == ("isolated", None)
    live, _, _ = _live_pass(spy=RISING_SPY, open_cell=True)
    engine, trades = _replay(FULL_PATH, _context(spy=RISING_SPY))
    assert live.plans[0].entry_context["compression_mode"] == trades[0][1].entry_context["compression_mode"] == "isolated"


def test_the_shared_decision_rejects_a_mode_outside_the_allow_list():
    stamp, reason = cc.compression_candidate_decision(
        "ABC", STOCK, FALLING_SPY, SECTOR, CLEAR, now=DECISION, allowlist=("isolated",))
    assert reason == "mode_not_allowed" and stamp == {}
    stamp, reason = cc.compression_candidate_decision(
        "ABC", STOCK, FALLING_SPY, SECTOR, CLEAR, now=DECISION)
    assert reason is None and stamp == {"compression_mode": "broad",
                                        "compression_bar_date": SIGNAL_DAY.isoformat()}


def test_tomorrows_spy_bar_cannot_change_the_replay_mode():
    future = RISING_SPY.iloc[[-1]].copy()
    future.index = [RISING_SPY.index[-1] + pd.tseries.offsets.BDay(1)]
    future[["Open", "High", "Low", "Close"]] = 1.0                    # crash tomorrow
    assert cc.compression_candidate_decision(
        "ABC", STOCK, pd.concat([RISING_SPY, future]), SECTOR, CLEAR, now=DECISION) == \
        cc.compression_candidate_decision("ABC", STOCK, RISING_SPY, SECTOR, CLEAR, now=DECISION)


# -- failure with no context ----------------------------------------------------------------------------------

def test_replay_without_a_context_provider_fails_loudly_never_a_silent_zero():
    engine = StrategyEngine([COMPRESSION_SHORT])
    with pytest.raises(CompressionContextError):
        list(engine.iter_trades("ABC", FULL_PATH, COMPRESSION_SHORT, HZ, ("2025-01-01", "2026-12-31"), None))


def test_replay_candidate_without_an_as_of_snapshot_is_excluded_not_assumed_clear():
    context = CompressionResearchContext(spy=FALLING_SPY, sector_of=lambda t: SECTOR,
                                         snapshot_of=lambda t, at: None)
    engine, trades = _replay(FULL_PATH, context)
    assert trades == [] and engine.compression_reasons == {"earnings_unknown": 1}


def test_live_pass_without_wired_hooks_rejects_closed_and_stores_nothing():
    live, store, log = _live_pass(hooks=False, open_cell=True, mode="live", live_allow={COMPRESSION_SHORT})
    assert live.plans == [] and live.alerts == [] and log.opened == []
    assert live.compression_reasons == {"no_context": 1}


# -- the shadow path: raw signal, zero live alerts ---------------------------------------------------------------

def test_shadow_raw_signal_builds_an_audit_plan_and_writes_a_record_with_zero_alerts():
    live, store, log = _live_pass(mode="live", live_allow={COMPRESSION_SHORT})   # mask closed
    assert live.alerts == [] and live.plans == [] and live.opened == 0
    assert store.rows == [] and log.opened == []
    (record,) = live.compression_shadow
    assert record["ticker"] == "ABC" and record["bar_date"] == SIGNAL_DAY.isoformat()
    assert record["mode"] == "broad" and record["reason"] is None and record["alert"] is False
    assert record["plan"]["trigger_price"] == 95.94 and record["plan"]["tp1"] == TARGET
    assert record["plan"]["hold_cap_bars"] == 10


def test_shadow_records_go_to_their_own_file_never_the_parity_log(tmp_path, monkeypatch):
    import json
    from swingbot.core.scanning import scan_run
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    live, _, _ = _live_pass(snapshot=IN_WINDOW)
    scan_run._record_compression_shadow(live)
    (line,) = (tmp_path / "compression_shadow.jsonl").read_text().splitlines()
    row = json.loads(line)
    assert row["alert"] is False and row["reason"] == "earnings_within_window" and row["mode"] == "broad"
    assert not (tmp_path / "shadow_plans.jsonl").exists()


def test_shadow_record_names_the_rejection_reason_by_mode():
    live, _, _ = _live_pass(snapshot=IN_WINDOW)
    (record,) = live.compression_shadow
    assert record["plan"] is None and record["reason"] == "earnings_within_window"
    assert record["mode"] == "broad"


def test_shadow_distinguishes_no_support_from_an_over_cap_stop(monkeypatch):
    monkeypatch.setattr(levels_mod, "build_level_map", lambda *a, **k: ([], []))
    live, _, _ = _live_pass()
    assert live.compression_shadow[0]["reason"] == "no_support"
    assert live.compression_reasons_by_mode == {"broad:no_support": 1}
    frame = STOCK.copy()
    frame.iloc[-1, frame.columns.get_loc("High")] = 100.0               # ~4.6% above the trigger
    monkeypatch.setattr(levels_mod, "build_level_map",
                        lambda *a, **k: ([Level(price=TARGET, sources=["Swing low"])], []))
    live, _, _ = _live_pass(frame=frame)
    assert live.compression_shadow[0]["reason"] == "over_cap_stop"


def test_open_cell_live_path_still_needs_global_mode_and_the_allow_list():
    live, _, log = _live_pass(mode="live", live_allow={COMPRESSION_SHORT}, open_cell=True)
    assert len(live.alerts) == 1 and live.opened == 1 and live.compression_shadow == []
    assert log.opened[0]["strategy"] == COMPRESSION_SHORT
    shadow, _, log = _live_pass(mode="shadow", live_allow={COMPRESSION_SHORT}, open_cell=True)
    assert shadow.alerts == [] and len(shadow.plans) == 1 and log.opened == []
    unnamed, _, log = _live_pass(mode="live", live_allow=set(), open_cell=True)
    assert unnamed.alerts == [] and log.opened == []


# -- confidence: the squeeze event is scored once -------------------------------------------------------------------

def test_strategy_path_never_scores_the_squeeze_a_second_time(monkeypatch):
    from swingbot.core.backtesting import backtest as bt
    from swingbot.core.scanning import confidence, factors

    def boom(*a, **k):
        raise AssertionError("the confluence squeeze factor must not score a compression-short plan")

    monkeypatch.setattr(confidence, "squeeze_breakout_confirmation", boom)
    monkeypatch.setattr(factors, "squeeze_breakout_confirmation", boom)
    assert COMPRESSION_SHORT not in bt.ALL_STRATEGIES        # the confluence engine never runs it
    live, _, _ = _live_pass(mode="live", live_allow={COMPRESSION_SHORT}, open_cell=True)
    _replay(FULL_PATH, _context())
    assert live.plans[0].confidence_level is None
