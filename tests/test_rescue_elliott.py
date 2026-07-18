import numpy as np

from swingbot.core.entry_filters import elliott_wave_entries
from tests.conftest import make_ohlcv

GATED = {"depth_min": 0.30, "depth_max": 0.80,
         "w2_min_retrace": 0.382, "w2_max_retrace": 0.786,
         "w2_max_duration_ratio": 1.0}


def _five_wave(retrace=0.5, w2_bars=5, w1_bars=60, overlap=False):
    """wave0 at 100, wave1 to 120 over w1_bars, wave2 retracing `retrace`
    of wave1 over w2_bars (below 100 when overlap=True), then wave-3 launch.

    The plan's illustrative fixture (30 flat bars + a short, steep 10/5/8-bar
    wave) does not survive `compute_shared_gates`: 30 bars is far short of
    the 200 needed for `bull_regime`'s ma200, a purely monotonic lead-in
    collapses the whole run into a single zigzag pivot at bar 0 (so "wave0"
    ends up priced at the lead-in's start, not at the actual wave-1 launch
    point), and an 8-bar/step-3 launch spikes ATR14 well past its 60-bar
    rolling mean (fails `atr_calm`). This version keeps the same wave-2
    mechanics (retrace ratio, bar counts, overlap) the gate tests care about,
    but: (1) uses a long flat lead-in (200+ bars) so ma200/ma50 are defined
    and trending correctly by breakout time, (2) inserts one extra high/low
    swing (the lead-in's flat top -> a dip to wave0) so the zigzag detector
    registers "wave0" at the real wave-1 launch price (~100), not bar 0, and
    (3) ramps wave 3's launch as a gentle geometric climb (0.5%/bar) instead
    of large fixed-point steps, so ATR stays calm through the breakout bar.
    """
    lead = [110.0] * 220
    decline = list(np.linspace(110.0, 100.0, 6)[1:])          # -> wave0 pivot
    w1 = [100 + 20 * (i + 1) / w1_bars for i in range(w1_bars)]
    w2_low = 120 - 20 * retrace if not overlap else 99.0
    w2 = [120 - (120 - w2_low) * (i + 1) / w2_bars for i in range(w2_bars)]
    launch = [w2_low * (1.005 ** (i + 1)) for i in range(40)]
    return make_ohlcv(lead + decline + w1 + w2 + launch)


def test_textbook_wave2_passes():
    df = _five_wave(retrace=0.5, w2_bars=5)
    bull_off, _ = elliott_wave_entries(df, "4w")
    bull_on, _ = elliott_wave_entries(df, "4w", params=GATED)
    assert bull_off.any(), "fixture must fire ungated (tune shape first)"
    assert bull_on.any()                      # good wave-2 survives the gate


def test_deep_retrace_suppressed():
    df = _five_wave(retrace=0.9)
    bull_on, _ = elliott_wave_entries(df, "4w", params=GATED)
    assert not bull_on.any()


def test_slow_wave2_suppressed():
    df = _five_wave(retrace=0.5, w2_bars=20, w1_bars=10)   # duration 2x wave1
    bull_on, _ = elliott_wave_entries(df, "4w", params=GATED)
    assert not bull_on.any()


def test_overlap_suppressed():
    df = _five_wave(overlap=True)
    bull_on, _ = elliott_wave_entries(df, "4w", params=GATED)
    assert not bull_on.any()


def test_gate_off_is_byte_identical():
    df = _five_wave()
    a, _ = elliott_wave_entries(df, "4w")
    b, _ = elliott_wave_entries(df, "4w",
        params={"depth_min": 0.30, "depth_max": 0.80,
                "w2_min_retrace": None, "w2_max_retrace": None,
                "w2_max_duration_ratio": None})
    assert (a == b).all()
