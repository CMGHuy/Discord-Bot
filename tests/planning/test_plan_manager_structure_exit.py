from datetime import datetime, timezone

import pytest

from swingbot import config
from swingbot.core.planning.plan_engine import PlanStatus, record_transition, runner_floor
from swingbot.core.planning.plan_manager import PlanManager, entry_bar_position
from swingbot.core.planning.plan_store import PlanStore
from tests.fake_feed import FakePriceFeed
from tests.planning.structure_fixtures import WARMUP, sawtooth, stall_frame
from tests.planning.test_plan_engine_model import _plan


def at(day, hour):
    return datetime(day.year, day.month, day.day, hour, 0, tzinfo=timezone.utc)


def partial_plan(df, entered_at=None):
    p = _plan(entry_type="market", horizon_key="2m", trigger_price=100.0, entry_price=100.0,
              stop_loss=95.0, tp1=101.0, tp2=None, trail_atr_mult=50.0)
    entry_day, tp1_day = df.index[WARMUP - 1].date(), df.index[WARMUP].date()
    record_transition(p, PlanStatus.ACTIVE, reason="market_entry",
                      at=entered_at or at(entry_day, 20).isoformat())
    record_transition(p, PlanStatus.PARTIAL, reason="tp1_partial", at=at(tp1_day, 15).isoformat())
    p.legs_realized = [{"fraction": 0.5, "exit_price": 101.0, "r": 0.2, "reason": "tp1"}]
    p.working_stop, p.runner_floor_session = runner_floor(100.0, 101.0), str(tp1_day)
    return p


def manager(df, plan, view):
    store = PlanStore()
    store.add(plan)
    return store, PlanManager(store, FakePriceFeed().get_price,
                              daily_frame_fn=lambda t: df.iloc[:view[0]])


def step(store, mgr, price, now):
    return mgr._step_partial(store.get("p1"), price, now)


def test_entry_bar_position_maps_fill_session():
    df = sawtooth(1)
    assert entry_bar_position(df, at(df.index[59].date(), 20).isoformat()) == 59
    assert entry_bar_position(df, "t0") is None and entry_bar_position(df, None) is None


def test_off_mode_never_fetches(monkeypatch):
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "off")
    df = sawtooth(4)
    store = PlanStore()
    store.add(partial_plan(df))
    mgr = PlanManager(store, FakePriceFeed().get_price,
                      daily_frame_fn=lambda t: pytest.fail("fetched in off mode"))
    assert step(store, mgr, 120.0, at(df.index[-1].date(), 15)) == []


def test_hl_trail_raises_working_stop_once_per_completed_bar(monkeypatch):
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "hl_trail")
    monkeypatch.setattr(config, "RUNNER_HL_TRAIL_ATR_BUFFER", 0.0)
    df = sawtooth(4)
    confirm = WARMUP + 9
    view = [confirm + 2]                 # bar confirm+1 is forming during its session
    store, mgr = manager(df, partial_plan(df), view)
    step(store, mgr, float(df["Open"].iloc[confirm + 1]), at(df.index[confirm + 1].date(), 15))
    assert store.get("p1").working_stop == pytest.approx(float(df["Low"].iloc[WARMUP + 6]))


def test_tp1_session_bar_is_not_evaluated(monkeypatch):
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "hl_trail")
    df = sawtooth(4)
    view = [WARMUP + 2]                  # completed through the TP1 bar only
    store, mgr = manager(df, partial_plan(df), view)
    step(store, mgr, 102.0, at(df.index[WARMUP + 1].date(), 15))
    assert store.get("p1").working_stop == pytest.approx(runner_floor(100.0, 101.0))


def _stall_bar(df):
    from tests.planning.test_exit_sim_runner_structure import _stall_j
    return _stall_j(df)


def test_stall_waits_for_the_next_regular_session(monkeypatch):
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "progress_stall")
    monkeypatch.setattr(config, "RUNNER_STALL_RANGE_MAX", 0.70)
    df = stall_frame()
    j = _stall_bar(df)
    view = [j + 1]                                   # bar j completed (after its close)
    store, mgr = manager(df, partial_plan(df), view)
    assert step(store, mgr, 121.0, at(df.index[j].date(), 22)) == []          # after-hours j
    assert step(store, mgr, 121.0, at(df.index[j + 1].date(), 12)) == []      # premarket j+1
    view[0] = j + 2                                  # session j+1 forming, dropped by completed_frame
    events = step(store, mgr, float(df["Open"].iloc[j + 1]), at(df.index[j + 1].date(), 15))
    assert [e.detail["reason"] for e in events] == ["tp1_runner_progress_stall"]
    assert store.get("p1").status == PlanStatus.CLOSED


def test_restart_rederives_the_stall_without_state(monkeypatch):
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "progress_stall")
    df = stall_frame()
    j = _stall_bar(df)
    view = [j + 2]
    store, mgr = manager(df, partial_plan(df), view)
    fresh = PlanManager(store, FakePriceFeed().get_price, daily_frame_fn=lambda t: df.iloc[:view[0]])
    events = fresh._step_partial(store.get("p1"), 120.0, at(df.index[j + 1].date(), 15))
    assert [e.detail["reason"] for e in events] == ["tp1_runner_progress_stall"]


@pytest.mark.parametrize("entered", ["t0", None])
def test_legacy_or_failing_inputs_are_skipped(monkeypatch, entered):
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "hl_trail")
    df = sawtooth(4)
    plan = partial_plan(df, entered_at="t0") if entered else partial_plan(df)
    store = PlanStore()
    store.add(plan)

    def frames(ticker):                  # t0: a good frame, unparseable fill time
        if entered is None:              # None: a normal plan whose fetch fails
            raise RuntimeError("yf down")
        return df
    mgr = PlanManager(store, FakePriceFeed().get_price, daily_frame_fn=frames)
    assert step(store, mgr, 120.0, at(df.index[-1].date(), 15)) == []
    assert store.get("p1").working_stop == pytest.approx(runner_floor(100.0, 101.0))
