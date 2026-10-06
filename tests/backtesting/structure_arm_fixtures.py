"""Hand-built frames with known swing structure for the v127 walk (spec §7).

Every frame is flat (100, 101, 99, 100) bars with overrides. Flat highs and
lows are never pivots (a swing high must be STRICTLY above the 3 highs
before it), so the only pivots are the ones an override creates. The arm
candidate sits at bar 25 on a support at L=98.5; with ATR pinned at 1.0
and k=0.25 a bar tests the level when its low is <= 98.75.
"""
import dataclasses

import numpy as np

from swingbot.core.backtesting import armed_replay as ar
from swingbot.core.backtesting import structure_arm as sa
from swingbot.core.market import levels, reaction as rx
from swingbot.scan_params import ScanParams
from tests.helpers import make_ohlcv

L, T1 = 98.5, 108.0
BASE = (100.0, 101.0, 99.0, 100.0)
TEST = (99.5, 100.0, 98.6, 99.5)              # bar 25: low 98.6 tests L
HOVER = (99.3, 99.6, 99.0, 99.3)              # near the level, never a test, never a release
RETEST = (99.3, 99.6, 98.6, 99.3)             # tests L again
RELEASE = (99.3, 100.4, 99.2, 100.2)          # close 100.2 > L + (0.25 + 1) * 1.0 = 99.75

# MSB: swing high 101.6 at bar 20 (confirmed at 23). Bar 27 closes 101.4
# (below it), bar 28 closes 101.7 (above it) -> the first break is bar 28.
MSB_FRAME = {20: (100.0, 101.6, 99.0, 100.0), 25: TEST,
             27: (100.0, 101.5, 99.0, 101.4), 28: (100.0, 101.9, 99.8, 101.7)}
# HL: MSB_FRAME, then a higher low 98.8 at bar 30 (confirmed at 33) and a
# close 102.1 at bar 34 above the newer swing high 101.9 (bar 28, confirmed 31).
HL_FRAME = {**MSB_FRAME, 30: (100.0, 101.0, 98.8, 100.0), 34: (101.0, 102.3, 100.5, 102.1)}
# Zone failed: bar 27 closes 98.4 < touch low 98.6 - 0.10 * 1.0.
CANCEL_FRAME = {25: TEST, 27: (99.0, 99.2, 98.0, 98.4)}
# Never-confirmed swing high: bar 27's 101.8 is beaten by bar 29's 102.2, so
# only bar 29 is a pivot (confirmed at 32). Bar 29's own close 102.0 > 101.8
# must NOT trigger; bar 33's close 102.4 > 102.2 does.
PIVOT_LAG_FRAME = {25: TEST, 27: (100.0, 101.8, 99.5, 101.0), 28: (101.0, 101.5, 100.5, 101.2),
                   29: (101.2, 102.2, 101.0, 102.0), 33: (101.0, 102.6, 100.8, 102.4)}


def mirror(row):
    """Reflect a bar through 100: the bearish twin of a bullish bar."""
    o, h, l, c = row
    return (200.0 - o, 200.0 - l, 200.0 - h, 200.0 - c)


def frame(overrides, n=40, bearish=False):
    rows = [BASE] * n
    for index, row in overrides.items():
        rows[index] = row
    if bearish:
        rows = [mirror(row) for row in rows]
    return make_ohlcv(rows)


def scenario(direction, stop, target, entry=100.0):
    return levels.Scenario(
        direction=direction, entry=entry, market_price=entry, stop_loss=stop,
        stop_sources=["Rolling S/R"], stop_distance_pct=abs(entry - stop) / entry * 100,
        tight_stop=False, atr_floor_pct=0.0, take_profit=target,
        target_distance_pct=abs(target - entry) / entry * 100,
        target_sources=["Fibonacci"], target2_price=None, target2_distance_pct=None,
        target2_sources=None)


def cand(index=25, direction="bullish", level=L, target=T1):
    return ar.ArmCandidate(index, direction, level, target, scenario(direction, level, target))


def bear_cand(index=25):
    return cand(index, direction="bearish", level=200.0 - L, target=92.0)


def walk(df, c=None, cell=sa.StructCell(sa.MSB, 5, 0.25), atr_values=None):
    atr_values = np.full(len(df), 1.0) if atr_values is None else atr_values
    return sa.walk_structure_arm(rx.Bars.from_frame(df), atr_values, sa.Pivots.from_frame(df),
                                 c or cand(), cell)


def params(**kw):
    base = dict(min_reward_pct=3.0, min_stop_distance_pct=2.0, max_stop_loss_pct=7.0,
                min_target_confluence_count=2, min_risk_reward_ratio=1.5,
                max_risk_reward_ratio=2.5)
    base.update(kw)
    return dataclasses.replace(ScanParams.from_config(), **base)


def structured_df():
    """Trend up, then a 60-bar consolidation -- tests/backtesting/
    test_armed_replay.py's fixture, copied so the files stay independent."""
    rng = np.random.RandomState(7)
    trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, 120)))
    box = [trend[-1] * (1 + 0.05 * np.sin(i / 4)) for i in range(60)]
    return make_ohlcv(trend + box)
