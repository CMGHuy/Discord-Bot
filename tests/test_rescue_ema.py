"""Task 107: EMA Crossover pullback-entry rescue gate.

Fixture note: the plan's illustrative fixture (30-bar downtrend + a 12-bar
recovery + a 3-bar dip) does not survive the real `ema_cross_entries` --
`compute_shared_gates`'s `bull_regime`/`trend50_bull` need ~200 bars of
history for `ma200`/`ma50` to be defined, and the plan's short, sharp
recovery either overshoots `not_extended` (price runs too far from the fast
EMA before the gates can look at it) or resolves before RSI genuinely dips
(so `rsi_dip` never triggers). This version keeps the same "cross, then a
pullback that tags the fast EMA, then continuation" mechanic the tests
care about, but (REPL-tuned, then frozen):
  1. uses a long, gentle uptrend lead-in (250 bars) so ma200/ma50 are
     defined and bullish by the time of the reversal;
  2. a short, mild down-leg forces a bearish cross, then a short, mild
     recovery leg forces the bullish cross back while price stays close
     enough to the fast EMA to pass `not_extended`;
  3. a real (not just wick) 2-bar decline after the cross drives RSI down
     through the `rsi_dip` threshold, and a bounce bar closes back above the
     fast EMA while its Low still tags it -- the actual touch-and-hold bar.
A 2.0% High/Low spread keeps ATR wide enough for `atr_floor`/`atr_calm`/
`not_extended` throughout without changing the touch mechanic itself.
"""
import numpy as np
from swingbot.core.entry_filters import ema_cross_entries
from swingbot.core.indicators import ema
from swingbot.core.strategy_types import HORIZONS
from tests.conftest import make_ohlcv

PULLBACK = {"rsi_dip": 45, "ext_atr": 1.0,
            "entry_mode": "pullback", "pullback_max_bars": 10}
# Explicit cross-mode: Task 108 adopted entry_mode="pullback" into
# DEFAULT_PARAMS, so the pre-rescue ("current") behavior must now be
# requested explicitly -- it is no longer what a no-params call returns.
CROSS = {"rsi_dip": 45, "ext_atr": 1.0,
         "entry_mode": "cross", "pullback_max_bars": 10}


def _cross_then_pullback():
    lead = [100 * 1.0008 ** i for i in range(250)]        # 200+ bars for ma200/ma50
    top = lead[-1]
    dip = [top * (1 - 0.0025) ** (i + 1) for i in range(20)]   # forces bearish cross
    bot = dip[-1]
    up = [bot * 1.005 ** (i + 1) for i in range(9)]            # forces bullish cross back
    peak = up[-1]
    decline = [peak * (1 - 0.02) ** (i + 1) for i in range(2)]  # real (not wick) 2-bar dip
    trough = decline[-1]
    bounce = trough + (peak - trough) * 0.4       # closes back above fast, Low still tags it
    cont = [bounce * 1.01 ** (i + 1) for i in range(10)]
    closes = lead + dip + up + decline + [bounce] + cont
    return make_ohlcv(closes, spread_pct=2.0)


def _runaway_no_pullback():
    lead = [100 * 1.0008 ** i for i in range(250)]
    top = lead[-1]
    dip = [top * (1 - 0.0025) ** (i + 1) for i in range(20)]
    bot = dip[-1]
    moon = [bot * 1.01 ** i for i in range(30)]        # keeps climbing, never dips back
    return make_ohlcv(lead + dip + moon, spread_pct=2.0)


def test_pullback_mode_enters_on_touch_bar_not_cross_bar():
    df = _cross_then_pullback()
    bull_cross, _ = ema_cross_entries(df, "4w", params=CROSS)
    bull_pb, _ = ema_cross_entries(df, "4w", params=PULLBACK)
    assert bull_cross.any()
    cross_i = int(np.where(bull_cross.values)[0][0])
    assert not bull_pb.iloc[cross_i]                 # not the cross bar
    pb_idx = np.where(bull_pb.values)[0]
    assert len(pb_idx) >= 1
    assert 0 < pb_idx[0] - cross_i <= 10             # inside the window
    # the entry bar really is a touch-and-hold of the fast EMA
    fast = ema(df["Close"], HORIZONS["4w"]["ema_fast"])
    i = pb_idx[0]
    assert df["Low"].iloc[i] <= fast.iloc[i] <= df["Close"].iloc[i]


def test_runaway_with_no_pullback_never_enters():
    df = _runaway_no_pullback()
    bull_pb, _ = ema_cross_entries(df, "4w", params=PULLBACK)
    assert not bull_pb.any()


def test_cross_mode_is_byte_identical():
    # Task 108 adopted entry_mode="pullback" (pullback_max_bars=15) into
    # DEFAULT_PARAMS, so the no-params default is no longer cross-mode --
    # compare two EXPLICIT cross-mode calls instead (pullback_max_bars must
    # be ignored entirely in cross mode, whatever its value).
    df = _cross_then_pullback()
    a, _ = ema_cross_entries(df, "4w", params=CROSS)
    b, _ = ema_cross_entries(df, "4w",
        params={**CROSS, "pullback_max_bars": 999})
    assert (a == b).all()


def test_default_now_matches_adopted_pullback_config():
    # Confirms DEFAULT_PARAMS["EMA Crossover"] (Task 108's train-grid
    # winner) really is entry_mode="pullback", pullback_max_bars=15 --
    # the no-params call must equal that explicit config exactly.
    df = _cross_then_pullback()
    default, _ = ema_cross_entries(df, "4w")
    explicit, _ = ema_cross_entries(df, "4w",
        params={"rsi_dip": 45, "ext_atr": 1.0, "entry_mode": "pullback",
                "pullback_max_bars": 15})
    assert (default == explicit).all()


def test_no_lookahead():
    df = _cross_then_pullback()
    full, _ = ema_cross_entries(df, "4w", params=PULLBACK)
    trunc, _ = ema_cross_entries(df.iloc[:-1], "4w", params=PULLBACK)
    assert (full.iloc[:-1] == trunc).all()
