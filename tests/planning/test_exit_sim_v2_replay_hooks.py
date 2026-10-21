"""v173 §3: the replay hooks on the v2 exit walk.

`ExitResult.tp1_index` is the TP1 bar on both TP1 paths and None everywhere
else; `fill_bar_exit` is the public fill-bar stop check. Neither changes any
existing result: `asdict`, `==` and the dataclass fields are what they were.
Expected numbers were taken from walk_v2 before the change (FREE: v2 fills,
zero costs). Entry is bar 0's price; the walk starts at bar 1.
"""
import dataclasses

import pytest

from swingbot.core.backtesting.instrument.contract import ZERO_COSTS, resolve
from swingbot.core.planning import exit_sim_v2
from swingbot.core.planning.exit_sim import ExitResult, simulate_exit
from swingbot.core.planning.exit_sim_v2 import fill_bar_exit, simulate_exit_v2, walk_v2
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults
from tests.helpers import make_ohlcv

V2 = resolve("v2")
FREE = dataclasses.replace(V2, cost_model=ZERO_COSTS)
ENTRY = (100.0, 100.5, 99.5, 100.0)
FLAT = (100.0, 100.5, 99.5, 100.0)
TP1_BAR = (105.0, 111.0, 104.0, 110.0)
TP2_BAR = (112.0, 121.0, 111.0, 120.0)

# v176 added runner_stop_source after cancel_reason; tp1_index is not a field.
_FIELDS = ("outcome", "runner_outcome", "entry_index", "exit_index", "entry_price",
           "r_total", "legs", "cancel_reason", "runner_stop_source")


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    pin_code_defaults(monkeypatch)


def _plan(**kw):
    base = dict(
        plan_id="p1", ticker="T", created_at="2024-01-02", source="strategy",
        strategy="Probe", horizon_key="4w", direction="bullish",
        entry_type="market", trigger_price=100.0, entry_price=None, expiry_bars=3,
        stop_loss=95.0, tp1=110.0, tp1_fraction=1.0, tp2=None,
        breakeven_trigger_fraction=0.5, trail_atr_mult=1.0,
        quality_score=0, quality_breakdown=[],
        badge="WEAK", badge_stats={}, status=PlanStatus.PENDING, status_history=[],
    )
    base.update(kw)
    return TradePlanV2(**base)


def _walk(bars, plan=None, *, scale_out=False, hold=10):
    df = make_ohlcv([ENTRY, *bars])
    return walk_v2(df, 0, 100.0, plan or _plan(), hold, FREE, scale_out=scale_out)


# --- ExitResult's shape is unchanged ---------------------------------------

def test_the_dataclass_fields_are_unchanged():
    assert tuple(f.name for f in dataclasses.fields(ExitResult)) == _FIELDS


def test_tp1_index_defaults_to_none_and_stays_out_of_asdict():
    res = ExitResult(outcome="no_trade", runner_outcome=None, entry_index=0, exit_index=None,
                     entry_price=100.0, r_total=0.0, legs=[])
    assert res.tp1_index is None
    assert "tp1_index" not in dataclasses.asdict(res)


def test_tp1_index_does_not_take_part_in_equality():
    a = _walk([FLAT, TP1_BAR])
    b = dataclasses.replace(a)          # a fresh instance: tp1_index back to the default
    assert b.tp1_index is None and a.tp1_index == 2
    assert a == b


# --- walk_v2 sets it on both TP1 paths --------------------------------------

def test_single_leg_tp1_exit_carries_the_tp1_bar():
    res = _walk([FLAT, TP1_BAR])
    assert (res.outcome, res.exit_index, res.r_total) == ("win", 2, 2.0)
    assert res.tp1_index == 2


def test_scale_out_runner_carries_the_tp1_bar_not_the_runner_exit():
    res = _walk([FLAT, TP1_BAR, TP2_BAR], _plan(tp1_fraction=0.5, tp2=120.0), scale_out=True)
    assert (res.outcome, res.runner_outcome, res.exit_index, res.r_total) == (
        "win", "runner_tp2", 3, 3.0)
    assert res.tp1_index == 2


def test_runner_timeout_still_carries_the_tp1_bar():
    res = _walk([FLAT, TP1_BAR, (110.0, 111.0, 109.0, 110.0)],
                _plan(tp1_fraction=0.5, tp2=130.0), scale_out=True, hold=3)
    assert (res.runner_outcome, res.exit_index) == ("runner_timeout", 3)
    assert res.tp1_index == 2


def test_a_stop_before_tp1_has_no_tp1_index():
    res = _walk([(93.0, 94.0, 92.0, 93.0)])
    assert (res.outcome, res.exit_index, res.r_total) == ("loss", 1, -1.4)
    assert res.tp1_index is None


def test_a_timeout_has_no_tp1_index():
    res = _walk([FLAT, FLAT], hold=2)
    assert (res.outcome, res.exit_index) == ("timeout", 2)
    assert res.tp1_index is None


def test_simulate_exit_v2_reaches_the_same_tp1_bar():
    """Market entry: signal bar 0, fill at bar 1's open, TP1 on bar 3."""
    df = make_ohlcv([ENTRY, FLAT, FLAT, TP1_BAR])
    res = simulate_exit_v2(df, 0, _plan(), FREE)
    assert (res.outcome, res.entry_index, res.exit_index) == ("win", 1, 3)
    assert res.tp1_index == 3


def test_v1_results_never_carry_a_tp1_index():
    df = make_ohlcv([ENTRY, FLAT, TP1_BAR, TP2_BAR])
    res = simulate_exit(df, 0, _plan(tp1_fraction=0.5, tp2=120.0), scale_out=True)
    assert res.tp1_index is None


# --- fill_bar_exit ------------------------------------------------------------

def test_fill_bar_exit_is_the_private_check_under_a_public_name():
    assert exit_sim_v2._fill_bar_v2 is fill_bar_exit


def test_fill_bar_exit_stops_out_on_the_fill_bar_at_the_stop_itself():
    df = make_ohlcv([(100.0, 101.0, 94.0, 96.0), FLAT])
    res = fill_bar_exit(df, 0, 100.0, _plan(), FREE)
    assert (res.outcome, res.entry_index, res.exit_index, res.r_total) == ("loss", 0, 0, -1.0)
    assert res.legs[0]["exit_price"] == 95.0 and res.legs[0]["reason"] == "stop"
    assert res.tp1_index is None


def test_fill_bar_exit_returns_none_when_the_fill_bar_never_reaches_the_stop():
    assert fill_bar_exit(make_ohlcv([ENTRY, FLAT]), 0, 100.0, _plan(), FREE) is None


def test_fill_bar_exit_scratches_a_fill_at_or_beyond_the_stop():
    res = fill_bar_exit(make_ohlcv([ENTRY, FLAT]), 0, 94.0, _plan(), FREE)
    assert (res.outcome, res.r_total, res.legs[0]["reason"]) == (
        "scratch", 0.0, "entry_gap_scratch")
    assert res.tp1_index is None
