"""v245 V245-4: both trendline sides share one zigzag of the trimmed frame.

The shared path must return exactly what each side computing its own zigzag
returns (the pre-V245-4 algorithm), and must run zigzag_pivots once.
"""
import pandas as pd
import pytest

from swingbot.core.market import trendlines
from swingbot.core.market.indicators import zigzag_pivots

_PERIOD = 20
_AMPLITUDE = 8.0
_VOLUME_SPIKE = 2.5


def _wave(n: int, drift: float = -0.3, volume: bool = True) -> pd.DataFrame:
    """Triangle wave on spiked turn volume (pattern: tests/charts/test_trendline_fit.py).

    Swings clear PIVOT_THRESHOLD_PCT and the turns carry VOL_MIN_RATIO-passing
    volume, so the custom scanner finds pivots instead of falling to trendln.
    """
    idx = pd.date_range("2018-01-01", periods=n, freq="B")
    values, volumes = [], []
    for i in range(n):
        phase = (i % _PERIOD) / _PERIOD
        triangle = 1.0 - abs(2.0 * phase - 1.0) * 2.0
        values.append(200.0 + drift * i + _AMPLITUDE * triangle + 0.37 * (i % 7))
        at_turn = i % _PERIOD in (0, _PERIOD // 2)
        volumes.append(1_000_000.0 * (_VOLUME_SPIKE if at_turn else 1.0) if volume else 0.0)
    close = pd.Series(values, index=idx)
    return pd.DataFrame({"Open": close, "High": close + 1.0, "Low": close - 1.0,
                         "Close": close, "Volume": pd.Series(volumes, index=idx)}, index=idx)


FRAMES = {
    "short_140": lambda: _wave(140),
    "no_volume": lambda: _wave(160, volume=False),
    "long_1700": lambda: _wave(1700, drift=-0.01),      # > MAX_PIVOT_SCAN_BARS: the trim applies
    "exactly_1500": lambda: _wave(1500, drift=-0.02),
    "too_short": lambda: _wave(20),
}


def _count_zigzag(monkeypatch) -> dict:
    calls = {"n": 0}
    real = trendlines.zigzag_pivots

    def counting(df, threshold_pct):
        calls["n"] += 1
        return real(df, threshold_pct=threshold_pct)

    monkeypatch.setattr(trendlines, "zigzag_pivots", counting)
    return calls


def _unshared_levels(df: pd.DataFrame, price: float) -> list:
    """custom_scanner_levels as it was: each side runs its own zigzag."""
    if len(df) < trendlines.MIN_BARS_FOR_TRENDLINE or price <= 0:
        return []
    out = []
    for side in ("support", "resistance"):
        best = trendlines._find_best_trendline(df, price, side)
        if best:
            out.append((float(best["line_at_now"]), f"Trendline ({best['strength']}x touch)"))
    return [(p, s) for p, s in out if p and p > 0 and not pd.isna(p)]


@pytest.mark.parametrize("name", sorted(FRAMES))
@pytest.mark.parametrize("kind", ["low", "high"])
def test_given_pivots_equal_computed_pivots(name, kind):
    df = FRAMES[name]()
    given = zigzag_pivots(df, threshold_pct=trendlines.PIVOT_THRESHOLD_PCT)
    assert trendlines._volume_confirmed_pivots(df, kind, all_pivots=given) == \
        trendlines._volume_confirmed_pivots(df, kind)


@pytest.mark.parametrize("name", sorted(FRAMES))
@pytest.mark.parametrize("price_mult", [1.0, 0.9, 1.1, 0.5])   # at close, each price gate, far print
def test_custom_scanner_levels_equals_unshared(name, price_mult):
    df = FRAMES[name]()
    price = float(df["Close"].iloc[-1]) * price_mult
    assert trendlines.custom_scanner_levels(df, price) == _unshared_levels(df, price)


def test_fixture_exercises_the_custom_scanner():
    df = FRAMES["long_1700"]()
    assert _unshared_levels(df, float(df["Close"].iloc[-1])), \
        "the wave must yield custom-scanner lines, or the equality tests prove nothing"


@pytest.mark.parametrize("name", ["short_140", "long_1700"])
def test_custom_scanner_levels_runs_one_zigzag(monkeypatch, name):
    df = FRAMES[name]()
    calls = _count_zigzag(monkeypatch)
    trendlines.custom_scanner_levels(df, float(df["Close"].iloc[-1]))
    assert calls["n"] == 1


def test_strongest_pair_runs_one_zigzag_and_is_unchanged(monkeypatch):
    df = FRAMES["long_1700"]()
    price = float(df["Close"].iloc[-1])
    before = trendlines.strongest_trendline_pair(df, 120, price)
    calls = _count_zigzag(monkeypatch)
    assert trendlines.strongest_trendline_pair(df, 120, price) == before
    assert calls["n"] == 1


def test_trimmed_zigzag_is_the_zigzag_of_the_scanned_window():
    df = FRAMES["long_1700"]()
    assert trendlines._trimmed_zigzag(df) == zigzag_pivots(
        df.tail(trendlines.MAX_PIVOT_SCAN_BARS), threshold_pct=trendlines.PIVOT_THRESHOLD_PCT)


def test_zigzag_failure_still_yields_no_lines(monkeypatch):
    def boom(df, threshold_pct):
        raise ValueError("zigzag failed")

    monkeypatch.setattr(trendlines, "zigzag_pivots", boom)
    df = FRAMES["short_140"]()
    assert trendlines.custom_scanner_levels(df, float(df["Close"].iloc[-1])) == []
    assert trendlines._volume_confirmed_pivots(df, "low") == []


def test_best_line_touches_are_in_full_frame_coordinates():
    df = FRAMES["long_1700"]()
    zz = trendlines._trimmed_zigzag(df)
    price = float(df["Close"].iloc[-1])
    shared = trendlines._find_best_trendline(df, price, "support", all_pivots=zz)
    assert shared == trendlines._find_best_trendline(df, price, "support")
    if shared is not None:
        assert min(b for b, _, _ in shared["touches"]) >= len(df) - trendlines.MAX_PIVOT_SCAN_BARS
