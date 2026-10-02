"""Hand-built OHLCV frames with known swing structure (v121)."""
import numpy as np

from tests.conftest import make_ohlcv

UP = [100, 110, 105, 115, 110, 120, 115, 125, 120, 130, 124, 127]   # HH/HL, ends mid-leg up
MIXED = UP + [125, 126]          # last SH 127 < 130 but last SL 125 > 124
BROKEN = UP + [118]              # close falls through the last confirmed SL (124)


def zigzag(points, leg=8):
    """Linear legs between turning points; each turning point is a unique extreme."""
    closes = [float(points[0])]
    for a, b in zip(points, points[1:]):
        closes.extend(np.linspace(a, b, leg + 1)[1:].tolist())
    return np.array(closes)


def frame(points, *, mirror=False):
    pts = [250 - p for p in points] if mirror else points
    return make_ohlcv(zigzag(pts), spread_pct=1.0)


def pullback_frame():
    """Swing low at bar 48, impulse to a swing high at bar 58 on 2M volume,
    then a 3-bar pullback (the minimum: the SH is confirmed at t-3) on 1M."""
    pre = zigzag([100, 112, 100, 110, 100], leg=12)      # 49 bars, low at 48
    impulse = np.linspace(100, 120, 11)[1:]             # bars 49..58
    pullback = np.array([118.0, 116.0, 114.0])          # bars 59..61
    closes = np.concatenate([pre, impulse, pullback])
    volumes = np.full(len(closes), 1_000_000.0)
    volumes[48:59] = 2_000_000.0                        # impulse leg SL0..SH inclusive
    return make_ohlcv(closes, spread_pct=1.0, volumes=volumes)


def wavy_frame(n=300):
    i = np.arange(n)
    closes = 100 + 0.05 * i + 6 * np.sin(i / 7.0) + 2 * np.sin(i / 2.3)
    volumes = 1_000_000 + 300_000 * np.sin(i / 3.1) + 5_000 * i
    return make_ohlcv(closes, spread_pct=1.5, volumes=volumes)


def _leg_frame(impulse_steps, pre_leg=12):
    """A swing low (bar 48 at pre_leg=12), an impulse built from `impulse_steps`
    close-to-close rises, then the same 3-bar pullback as `pullback_frame`."""
    pre = zigzag([100, 112, 100, 110, 100], leg=pre_leg)  # 4*pre_leg + 1 bars, low last
    impulse = 100 + np.cumsum(impulse_steps)
    pullback = impulse[-1] - np.array([2.0, 4.0, 6.0])
    return make_ohlcv(np.concatenate([pre, impulse, pullback]), spread_pct=1.0)


def slowing_pullback_frame():
    """Ten-bar impulse whose steps shrink 4 -> 0.5: momentum fading into the high."""
    return _leg_frame([4.0, 4.0, 3.5, 3.0, 2.5, 2.0, 1.5, 1.0, 0.5, 0.5])


def short_impulse_frame():
    """Four-bar impulse (base at 56, high at 60): a 5-bar leg is too short for a
    range decay (< 2 bars per third). pre_leg=14 keeps the frame >= 60 bars."""
    return _leg_frame([5.0, 5.0, 5.0, 5.0], pre_leg=14)
