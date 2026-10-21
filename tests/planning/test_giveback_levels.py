"""v178 V178-1: adaptive give-back levels (range multiple, profit share) in the v1 walk.

Frames: 15 flat warm-up bars (open 100, high 101.5, low 98.5, close 100; true
range 3.0) so ATR(14) exists from bar 13; the market entry fills at bar 14's
close (100). Stop 95, TP1 110 (tp1_fraction 0.5), runner floor 106.6667;
trail_atr_mult=50 parks the chandelier, so only the floor and the give-back
can bind. ATR(14) (Wilder) after bar 16 is 4.1352, after bar 17 4.3755.

REVERSE
  bar 15 (100, 111, 99.5, 110.5)   TP1 touched
  bar 16 (110.5, 121, 110, 120)    best close 120; sets the level for bar 17
                                   from ATR after bar 16
  bar 17 (120, 120.5, 113, 113.5)  low 113: R k 0.75/1.0/1.25 (116.90 / 115.86 /
                                   114.83), S 0.25 (115.0), S 0.33 (113.4) exit here
  bar 18 (113.5, 114, 106, 106.5)  S 0.50 (110.0) exits here; the floor too
JUMP: bars 15-16 as REVERSE, then
  bar 17 (120, 124, 116.5, 119)    no new best close; true range 7.5 lifts ATR,
                                   so the k = 1.0 level recomputed after bar 17
                                   (115.62) is looser and the stop stays 115.865
  bar 18 (119, 119.5, 112, 112.5)  low 112: out at the bar-16 level, "giveback"
  bar 19 (112.5, 113, 106, 106.5)
Bar 16's own low (110) is below every level its close sets: exit_index 17, not
16, is the no-lookahead check. The bearish frames mirror every bar around 100.
"""
import math
import pathlib

import pytest

from swingbot import config
from swingbot.core.market.indicators import atr as atr_indicator
from swingbot.core.planning import exit_sim
from swingbot.core.planning.exit_sim import (GIVEBACK_F_BOUNDS, GIVEBACK_K_BOUNDS,
                                             GIVEBACK_MODES, _carried_level,
                                             _scale_out_exit_walk, giveback_allowance,
                                             giveback_level, giveback_term)
from swingbot.core.planning.plan_engine import simulate_exit
from tests.helpers import make_ohlcv
from tests.planning.test_exit_sim_single import _plan

FLOOR = 100.0 + (2.0 / 3.0) * 10.0
ENTRY = 14
WARM = [(100.0, 101.5, 98.5, 100.0)] * 15
RUN = [(100.0, 111.0, 99.5, 110.5), (110.5, 121.0, 110.0, 120.0)]
REVERSE = WARM + RUN + [(120.0, 120.5, 113.0, 113.5), (113.5, 114.0, 106.0, 106.5)]
JUMP = WARM + RUN + [(120.0, 124.0, 116.5, 119.0), (119.0, 119.5, 112.0, 112.5),
                     (112.5, 113.0, 106.0, 106.5)]
# test_exit_sim_giveback.BULL_BARS: five bars, so ATR(14) is NaN on every bar.
NAN_ATR_BARS = [100.0, (100.0, 111.0, 99.5, 110.5), (110.5, 121.0, 110.0, 120.0),
                (120.0, 120.5, 113.0, 113.5), (113.5, 114.0, 106.0, 106.5)]
ARMS = [("pct", 1.0, 0.33), ("range", 0.75, 0.33), ("range", 1.0, 0.33),
        ("range", 1.25, 0.33), ("profit_share", 1.0, 0.25),
        ("profit_share", 1.0, 0.33), ("profit_share", 1.0, 0.50)]


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Give-back on, pct mode at 5%; every other runner rule that could bind off."""
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", True)
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_PCT", 5.0)
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "off")
    monkeypatch.setattr(config, "ADAPTIVE_RUNNER_TRAIL_ENABLED", False)
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", False)
    monkeypatch.setattr(exit_sim, "GIVEBACK_EXTREME_BASIS", "close")
    monkeypatch.setattr(exit_sim, "GIVEBACK_MODE", "pct")
    monkeypatch.setattr(exit_sim, "GIVEBACK_K", 1.0)
    monkeypatch.setattr(exit_sim, "GIVEBACK_F", 0.33)


def _arm(monkeypatch, mode, k=1.0, f=0.33):
    monkeypatch.setattr(exit_sim, "GIVEBACK_MODE", mode)
    monkeypatch.setattr(exit_sim, "GIVEBACK_K", k)
    monkeypatch.setattr(exit_sim, "GIVEBACK_F", f)


def _mirror(bars):
    return [(200.0 - o, 200.0 - lo, 200.0 - hi, 200.0 - c) for o, hi, lo, c in bars]


def _bull(**kw):
    base = dict(direction="bullish", stop_loss=95.0, tp1=110.0, tp2=None, trail_atr_mult=50.0)
    base.update(kw)
    return _plan(**base)


def _bear(**kw):
    base = dict(direction="bearish", stop_loss=105.0, tp1=90.0, tp2=None, trail_atr_mult=50.0)
    base.update(kw)
    return _plan(**base)


def _run(bars, plan, entry=ENTRY):
    return simulate_exit(make_ohlcv(bars), entry, plan, scale_out=True, max_holding_days=10)


def _trace(bars, plan):
    trace = []
    _scale_out_exit_walk(make_ohlcv(bars), ENTRY, 100.0, plan, 10, trace=trace)
    return trace


def _atr_after(bars, j):
    return float(atr_indicator(make_ohlcv(bars), 14).iloc[j])


# --- the pure level ------------------------------------------------------------

def test_module_defaults_keep_the_live_rule():
    src = pathlib.Path(exit_sim.__file__).read_text(encoding="utf-8")
    assert 'GIVEBACK_MODE: str = "pct"' in src
    assert "GIVEBACK_K: float = 1.0" in src
    assert "GIVEBACK_F: float = 0.33" in src
    assert GIVEBACK_MODES == ("pct", "range", "profit_share")
    assert exit_sim.GIVEBACK_FLOOR_ATR == 1.0
    assert GIVEBACK_K_BOUNDS == (0.25, 3.0) and GIVEBACK_F_BOUNDS == (0.05, 0.95)


@pytest.mark.parametrize("mode, k, f, expected", [
    ("range", 0.75, 0.33, 53.063),           # 49.94 + 0.75 x 4.164
    ("range", 1.0, 0.33, 54.104),
    ("range", 1.25, 0.33, 55.145),
    ("profit_share", 1.0, 0.25, 54.104),     # 0.25 x 10.73 = 2.68 < ATR: the floor binds
    ("profit_share", 1.0, 0.33, 54.104),     # 3.54 < 4.164: the floor binds
    ("profit_share", 1.0, 0.50, 55.305),     # 5.365 > ATR
])
def test_rklb_short_worked_example(monkeypatch, mode, k, f, expected):
    _arm(monkeypatch, mode, k, f)
    assert giveback_term(49.94, 60.67, 4.164, "bearish") == pytest.approx(expected, abs=1e-9)


@pytest.mark.parametrize("mode, k, f, expected", [
    ("pct", 1.0, 0.33, 106.40),
    ("range", 0.75, 0.33, 110.875),
    ("range", 1.0, 0.33, 110.50),
    ("range", 1.25, 0.33, 110.125),
    ("profit_share", 1.0, 0.25, 109.00),
    ("profit_share", 1.0, 0.33, 108.04),
    ("profit_share", 1.0, 0.50, 106.00),
])
def test_calm_long_worked_example(monkeypatch, mode, k, f, expected):
    _arm(monkeypatch, mode, k, f)
    assert giveback_term(112.0, 100.0, 1.5, "bullish") == pytest.approx(expected, abs=1e-9)


def test_pct_mode_is_the_live_level_exactly():
    for extreme, direction in ((120.0, "bullish"), (80.0, "bearish"), (49.94, "bearish")):
        assert giveback_term(extreme, 100.0, 4.0, direction) == giveback_level(extreme, direction)


def test_allowance_per_mode():
    assert giveback_allowance("pct", 112.0, 100.0, None, k=1.0, f=0.33) == pytest.approx(5.6)
    assert giveback_allowance("range", 112.0, 100.0, 1.5, k=1.0, f=0.33) == 1.5
    assert giveback_allowance("profit_share", 112.0, 100.0, 1.5, k=1.0, f=0.5) == 6.0
    # best price at entry: zero profit, so the 1.0 x ATR floor is the allowance
    assert giveback_allowance("profit_share", 100.0, 100.0, 2.0, k=1.0, f=0.5) == 2.0


@pytest.mark.parametrize("mode", ["range", "profit_share"])
@pytest.mark.parametrize("atr", [None, math.nan, 0.0, -1.0, math.inf])
def test_unusable_atr_yields_no_term_never_a_substitute(monkeypatch, mode, atr):
    _arm(monkeypatch, mode, 1.0, 0.33)
    assert giveback_allowance(mode, 120.0, 100.0, atr, k=1.0, f=0.33) is None
    assert giveback_term(120.0, 100.0, atr, "bullish") is None


@pytest.mark.parametrize("mode", list(GIVEBACK_MODES))
def test_flag_off_or_no_extreme_is_no_term(monkeypatch, mode):
    _arm(monkeypatch, mode)
    assert giveback_term(None, 100.0, 4.0, "bullish") is None
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", False)    # control B
    assert giveback_term(120.0, 100.0, 4.0, "bullish") is None


def test_parameter_bounds_are_inclusive_and_enforced():
    assert giveback_allowance("range", 120.0, 100.0, 4.0, k=0.25, f=0.33) == 1.0
    assert giveback_allowance("range", 120.0, 100.0, 4.0, k=3.0, f=0.33) == 12.0
    assert giveback_allowance("profit_share", 120.0, 100.0, 1.0, k=1.0, f=0.95) == 19.0
    for k in (0.2, 3.5):
        with pytest.raises(ValueError, match="GIVEBACK_K"):
            giveback_allowance("range", 120.0, 100.0, 4.0, k=k, f=0.33)
    for f in (0.01, 0.99):
        with pytest.raises(ValueError, match="GIVEBACK_F"):
            giveback_allowance("profit_share", 120.0, 100.0, 4.0, k=1.0, f=f)
    with pytest.raises(ValueError, match="GIVEBACK_K"):          # bounds before ATR
        giveback_allowance("range", 120.0, 100.0, math.nan, k=9.0, f=0.33)


def test_an_unknown_mode_is_rejected(monkeypatch):
    with pytest.raises(ValueError, match="GIVEBACK_MODE"):
        giveback_allowance("atr", 120.0, 100.0, 4.0, k=1.0, f=0.33)
    _arm(monkeypatch, "atr")
    with pytest.raises(ValueError, match="GIVEBACK_MODE"):
        giveback_term(120.0, 100.0, 4.0, "bullish")


def test_carried_level_tracks_the_level_that_set_the_stop():
    assert _carried_level(115.0, 115.0, None) == 115.0        # this bar's level set it
    assert _carried_level(116.0, 115.0, 114.0) == 114.0       # it did not: keep the old one
    assert _carried_level(116.0, None, 114.0) == 114.0        # no term this bar
    assert _carried_level(106.0, None, None) is None


# --- the v1 walk ---------------------------------------------------------------

def test_pct_mode_walk_is_the_v176_exit():
    res = _run(REVERSE, _bull())
    assert (res.exit_index, res.runner_stop_source) == (17, "giveback")
    assert res.legs[1]["exit_price"] == exit_sim.giveback_stop(120.0, 5.0, "bullish")


@pytest.mark.parametrize("k, hand", [(0.75, 116.899), (1.0, 115.865), (1.25, 114.831)])
def test_range_arm_exits_at_best_minus_k_atr_the_next_bar(monkeypatch, k, hand):
    _arm(monkeypatch, "range", k=k)
    res = _run(REVERSE, _bull())
    assert res.outcome == "win"
    assert res.runner_outcome == "runner_trail"
    assert res.runner_stop_source == "giveback"
    assert res.exit_index == 17                      # bar 16 sets it, bar 17 tests it
    level = 120.0 - k * _atr_after(REVERSE, 16)
    assert res.legs[1]["exit_price"] == pytest.approx(level)
    assert res.legs[1]["exit_price"] == pytest.approx(hand, abs=1e-3)
    assert set(res.legs[1]) == {"fraction", "exit_price", "r", "reason"}


@pytest.mark.parametrize("f, exit_index, price", [(0.25, 17, 115.0), (0.33, 17, 113.4),
                                                  (0.50, 18, 110.0)])
def test_profit_share_arm_exits_at_its_share_of_the_profit(monkeypatch, f, exit_index, price):
    _arm(monkeypatch, "profit_share", f=f)
    res = _run(REVERSE, _bull())
    assert res.runner_stop_source == "giveback"
    assert res.exit_index == exit_index
    assert res.legs[1]["exit_price"] == pytest.approx(price)


@pytest.mark.parametrize("mode, k, f, exit_index, price", [
    ("range", 1.0, 0.33, 17, None),                  # 80 + ATR after bar 16
    ("profit_share", 1.0, 0.50, 18, 90.0),
])
def test_bearish_mirror(monkeypatch, mode, k, f, exit_index, price):
    _arm(monkeypatch, mode, k, f)
    bars = _mirror(REVERSE)
    res = _run(bars, _bear())
    assert res.runner_stop_source == "giveback"
    assert res.exit_index == exit_index
    expected = price if price is not None else 80.0 + _atr_after(bars, 16)
    assert res.legs[1]["exit_price"] == pytest.approx(expected)


@pytest.mark.parametrize("k", [1.0, 1.25])
def test_atr_jump_leaves_the_stop_and_its_source_unchanged(monkeypatch, k):
    """Spec test (a) and stop attribution: no new extreme on bar 17 and a larger
    ATR -- the stop set on bar 16 stays, and still fires as "giveback"."""
    _arm(monkeypatch, "range", k=k)
    level = 120.0 - k * _atr_after(JUMP, 16)
    trace = _trace(JUMP, _bull())
    assert [j for j, _ in trace] == [16, 17]
    assert trace[0][1] == pytest.approx(level) and trace[1][1] == trace[0][1]
    res = _run(JUMP, _bull())
    assert res.exit_index == 18
    assert res.runner_stop_source == "giveback"      # recomputing from bar 17 would say "trail"
    assert res.legs[1]["exit_price"] == pytest.approx(level)


@pytest.mark.parametrize("mode, k, f", ARMS)
@pytest.mark.parametrize("bull", [True, False])
def test_the_runner_stop_only_moves_toward_price(monkeypatch, mode, k, f, bull):
    """Spec test (b): every arm's stop series is monotone toward price."""
    _arm(monkeypatch, mode, k, f)
    bars, plan = (JUMP, _bull()) if bull else (_mirror(JUMP), _bear())
    stops = [stop for _, stop in _trace(bars, plan)]
    assert stops, "the runner must survive at least one bar"
    pairs = list(zip(stops, stops[1:]))
    assert all((b >= a) if bull else (b <= a) for a, b in pairs)


@pytest.mark.parametrize("mode", ["range", "profit_share"])
def test_no_atr_means_no_term_so_the_runner_rides_to_the_floor(monkeypatch, mode):
    """Spec test (c) in the walk: a NaN ATR gives no term (pct still fires)."""
    _arm(monkeypatch, mode)
    res = _run(NAN_ATR_BARS, _bull(), entry=0)
    assert (res.runner_outcome, res.runner_stop_source, res.exit_index) == \
           ("runner_be", "floor", 4)
    assert res.legs[1]["exit_price"] == pytest.approx(FLOOR)
    _arm(monkeypatch, "pct")
    assert _run(NAN_ATR_BARS, _bull(), entry=0).exit_index == 3


def test_an_allowance_beyond_the_profit_exits_at_the_floor(monkeypatch):
    """Floor clamp: f = 0.95 puts the level at 120 - 19 = 101, below the floor."""
    _arm(monkeypatch, "profit_share", f=0.95)
    res = _run(REVERSE, _bull())
    assert (res.runner_outcome, res.runner_stop_source, res.exit_index) == \
           ("runner_be", "floor", 18)
    assert res.legs[1]["exit_price"] == pytest.approx(FLOOR)
    assert res.legs[1]["r"] > 0                      # never on the loss side of entry


@pytest.mark.parametrize("mode", list(GIVEBACK_MODES))
def test_control_b_is_flag_off_in_every_mode(monkeypatch, mode):
    _arm(monkeypatch, mode)
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", False)
    res = _run(REVERSE, _bull())
    assert (res.runner_outcome, res.runner_stop_source, res.exit_index) == \
           ("runner_be", "floor", 18)
