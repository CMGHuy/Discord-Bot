"""v232: exit_sim_v2.simulate_exit_v2_from_fill -- the v2 walk from a given fill.

Parity: handed simulate_exit_v2's own entry bar and price, with the fill-bar
check every v2 entry applies, the wrapper returns exactly what the engine
returns, under the costed v2 instrument and a zero-cost copy. Layer 1 passes
fill_bar_check=False.
"""
import dataclasses

import pytest

from swingbot.core.backtesting.instrument.contract import ZERO_COSTS, resolve
from swingbot.core.market.strategy_types import COMPRESSION_SHORT
from swingbot.core.planning.exit_sim_v2 import (ENTRY_GAP_SCRATCH, simulate_exit_v2,
                                                simulate_exit_v2_from_fill, walk_v2)
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults
from tests.helpers import make_ohlcv

V2 = resolve("v2")
FREE = dataclasses.replace(V2, cost_model=ZERO_COSTS)
INSTRUMENTS = {"costed": V2, "free": FREE}


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    pin_code_defaults(monkeypatch)


def _plan(**kw):
    base = dict(plan_id="p1", ticker="T", created_at="2024-01-02", source="strategy",
                strategy="Fibonacci", horizon_key="2w", direction="bullish",
                entry_type="market", trigger_price=100.0, entry_price=None, expiry_bars=3,
                stop_loss=95.0, tp1=106.0, tp1_fraction=0.5, tp2=110.0,
                breakeven_trigger_fraction=0.5, trail_atr_mult=2.5,
                quality_score=0, quality_breakdown=[], badge="WEAK", badge_stats={},
                status=PlanStatus.PENDING, status_history=[])
    base.update(kw)
    return TradePlanV2(**base)


SIGNAL = (100.0, 100.5, 99.5, 100.0)
FLAT = (100.0, 100.5, 99.5, 100.0)
PATHS = {
    "win": [SIGNAL, (100.0, 101.0, 99.0, 100.5), (100.5, 103.0, 100.0, 102.5),
            (102.5, 107.0, 102.0, 106.5), (106.5, 109.0, 106.0, 108.5),
            (108.5, 111.0, 108.0, 110.5), (110.5, 111.0, 104.0, 104.5)] + [FLAT] * 8,
    "loss": [SIGNAL, (100.0, 100.5, 98.0, 99.0), (99.0, 99.5, 94.0, 94.5)] + [FLAT] * 8,
    "timeout": [SIGNAL] + [FLAT] * 14,
}


def _mirror(bars):
    """Reflect a path around 100, so a bearish plan sees what a bullish one sees."""
    return [(200.0 - o, 200.0 - l, 200.0 - h, 200.0 - c) for o, h, l, c in bars]


BEAR = dict(direction="bearish", stop_loss=105.0, tp1=94.0, tp2=90.0)
# (case id, plan overrides, mirrored path?)
CASES = [
    ("market", {}, False),
    ("market_short", BEAR, True),
    ("stop_entry", dict(entry_type="stop_entry", trigger_price=100.4), False),
    ("limit", dict(entry_type="limit", trigger_price=99.5, expiry_bars=1), False),
    ("compression_short", dict(BEAR, strategy=COMPRESSION_SHORT, entry_type="stop_entry",
                               trigger_price=99.6, stop_ceiling_pct=10.0), True),
    ("v192_waiting", dict(source="confluence", strategy="S/R Confluence", stop_loss=98.5,
                          tp1=103.0, tp2=105.0, waits_next_open=True), False),
]


def _engine_and_wrapper(bars, kw, instrument, *, scale_out, fill_bar_check=True, **extra):
    df = make_ohlcv(bars)
    engine = simulate_exit_v2(df, 0, _plan(**kw), instrument, scale_out=scale_out, **extra)
    assert engine.entry_index is not None, (engine.outcome, engine.cancel_reason)
    wrapped = simulate_exit_v2_from_fill(df, engine.entry_index, engine.entry_price,
                                         _plan(**kw), instrument, scale_out=scale_out,
                                         fill_bar_check=fill_bar_check, **extra)
    return engine, wrapped


@pytest.mark.parametrize("instrument", sorted(INSTRUMENTS))
@pytest.mark.parametrize("scale_out", [False, True])
@pytest.mark.parametrize("path", sorted(PATHS))
@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_parity_with_simulate_exit_v2_for_every_entry_type(case, path, scale_out, instrument):
    _, kw, mirrored = case
    bars = _mirror(PATHS[path]) if mirrored else PATHS[path]
    engine, wrapped = _engine_and_wrapper(bars, kw, INSTRUMENTS[instrument],
                                          scale_out=scale_out)
    assert vars(wrapped) == vars(engine)


@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_parity_holds_under_a_plan_hold_cap(case):
    _, kw, mirrored = case
    bars = _mirror(PATHS["timeout"]) if mirrored else PATHS["timeout"]
    engine, wrapped = _engine_and_wrapper(bars, dict(kw, hold_cap_bars=3), V2,
                                          scale_out=False)
    assert engine.outcome == "timeout"
    assert vars(wrapped) == vars(engine)


def test_parity_with_an_explicit_max_holding_days():
    engine, wrapped = _engine_and_wrapper(PATHS["timeout"], {}, FREE, scale_out=True,
                                          max_holding_days=2)
    assert (engine.entry_index, engine.exit_index) == (1, 3)
    assert vars(wrapped) == vars(engine)


STOPPED_FILL_BAR = [SIGNAL, (100.0, 100.5, 94.0, 96.0)] + PATHS["win"][2:]


def test_checked_fill_bar_stop_matches_the_engine():
    engine, wrapped = _engine_and_wrapper(STOPPED_FILL_BAR, {}, FREE, scale_out=False)
    assert (engine.outcome, engine.exit_index) == ("loss", 1)
    assert vars(wrapped) == vars(engine)


def test_unchecked_fill_bar_is_never_read():
    df = make_ohlcv(STOPPED_FILL_BAR)
    res = simulate_exit_v2_from_fill(df, 1, 100.0, _plan(), FREE, scale_out=False)
    assert res.entry_index == 1 and res.exit_index != 1


def test_a_checked_fill_at_the_stop_is_the_entry_gap_scratch():
    df = make_ohlcv(PATHS["win"])
    res = simulate_exit_v2_from_fill(df, 1, 95.0, _plan(), V2, scale_out=False,
                                     fill_bar_check=True)
    assert (res.outcome, res.r_total, res.legs[0]["reason"]) == ("scratch", 0.0,
                                                                ENTRY_GAP_SCRATCH)


def test_unchecked_equals_walk_v2_with_the_resolved_cap_and_indicator_frame():
    df = make_ohlcv(PATHS["win"])
    indicators = df.copy()
    res = simulate_exit_v2_from_fill(df, 1, 100.0, _plan(), V2, scale_out=True,
                                     indicator_df=indicators)
    direct = walk_v2(df, 1, 100.0, _plan(), 14, V2, scale_out=True, indicator_df=indicators)
    assert vars(res) == vars(direct)                 # 2w horizon: max_holding_days 14


def test_the_indicator_frame_reaches_walk_v2():
    df = make_ohlcv(PATHS["win"])
    with pytest.raises(ValueError, match="same index and length"):
        simulate_exit_v2_from_fill(df, 1, 100.0, _plan(), V2, scale_out=True,
                                   indicator_df=df.iloc[:-1])


def test_an_unsupported_fill_model_is_refused_like_the_engine():
    v1_fills = resolve("v1").fill_model
    bad = dataclasses.replace(V2, fill_model=v1_fills)
    with pytest.raises(ValueError, match="next_open"):
        simulate_exit_v2_from_fill(make_ohlcv(PATHS["win"]), 1, 100.0, _plan(), bad,
                                   scale_out=False)
