"""Deterministic frames with known swing structure (v123 runner tests)."""
from tests.helpers import make_ohlcv

WARMUP = 60
CYCLE = (2.0, 2.0, 2.0, 2.0, -1.0, -1.0, -1.0)


def sawtooth_closes(cycles, start=100.0):
    closes = [start] * WARMUP
    for _ in range(cycles):
        for step in CYCLE:
            closes.append(closes[-1] + step)
    return closes


def sawtooth(cycles, tail=()):
    return make_ohlcv(sawtooth_closes(cycles) + [float(c) for c in tail], spread=0.001)


def stall_frame():
    closes = sawtooth_closes(4)
    sl = closes[-1]                                  # last swing-low close; prior top = sl + 3
    # A slow climb to a lower high (sl + 1) in 0.2 steps keeps true range small
    # enough that range_trend_10_50 <= 0.70 on the bar the high confirms (V123-5).
    closes += [sl + 0.2, sl + 0.4, sl + 0.6, sl + 0.8, sl + 1.0, sl + 0.8, sl + 0.6,
               sl + 0.4] + [sl + 0.4] * 3
    df = make_ohlcv(closes, spread=0.001)
    quiet = df.index[-11:]
    df.loc[quiet, "High"] = df.loc[quiet, "Close"] + 0.05
    df.loc[quiet, "Low"] = df.loc[quiet, "Close"] - 0.05
    df.loc[quiet, "Volume"] = 400_000.0
    return df
