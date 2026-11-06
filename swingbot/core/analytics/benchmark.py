"""Benchmark statistics (v208): pure fractions in and out, with rf = 0.

Small-sample guards prevent unstable estimates; alpha is descriptive, never edge.
"""
from dataclasses import dataclass
import math
import statistics
from typing import Sequence

TRADING_DAYS = 252
MIN_BETA_N = 20
MIN_SHARPE_N = 20
MIN_ALPHA_N = 60
MIN_CAPTURE_SIDE_N = 10
CAPTURE_REASON = "needs ≥ 10 index-up and ≥ 10 index-down sessions"
NO_VARIANCE = "no variance"
INDEX_FLAT = "index flat"
_EPS = 1e-15


def needs(k: int) -> str:
    return f"needs ≥ {k} sessions"


@dataclass(frozen=True)
class Estimate:
    value: float | None
    se: float | None
    t: float | None
    n: int
    reason: str | None


@dataclass(frozen=True)
class Capture:
    up: float | None
    down: float | None
    ratio: float | None
    up_n: int
    down_n: int
    reason: str | None


@dataclass(frozen=True)
class BeatCount:
    up_days: int
    up_beat: int
    down_days: int
    down_beat: int


def cumulative(r: Sequence[float]) -> list[float]:
    level = 1.0
    result = []
    for daily in r:
        level *= 1 + daily
        result.append(level - 1)
    return result


def total_return(r: Sequence[float]) -> float | None:
    values = cumulative(r)
    return values[-1] if values else None


def max_drawdown(r: Sequence[float]) -> float | None:
    if not r:
        return None
    peak, worst = 1.0, 0.0
    for value in cumulative(r):
        level = value + 1
        peak = max(peak, level)
        worst = min(worst, level / peak - 1)
    return worst


def money_drawdown(closes: Sequence[float]) -> float | None:
    if not closes:
        return None
    peak, worst = closes[0], 0.0
    for close in closes:
        peak = max(peak, close)
        worst = min(worst, close - peak)
    return worst


def losing_streak(r: Sequence[float]) -> int:
    run, longest = 0, 0
    for daily in r:
        run = run + 1 if daily < 0 else 0
        longest = max(longest, run)
    return longest


def _guard(n: int, minimum: int) -> Estimate | None:
    return Estimate(None, None, None, n, needs(minimum)) if n < minimum else None


def sharpe(r: Sequence[float]) -> Estimate:
    n = len(r)
    guard = _guard(n, MIN_SHARPE_N)
    if guard:
        return guard
    sd = statistics.stdev(r)
    if sd == 0:
        return Estimate(None, None, None, n, NO_VARIANCE)
    return Estimate(statistics.mean(r) / sd * math.sqrt(TRADING_DAYS), None, None, n, None)


def _paired(bot: Sequence[float], idx: Sequence[float]) -> None:
    if len(bot) != len(idx):
        raise ValueError("bot and idx differ in length")


def _ols(y: Sequence[float], x: Sequence[float]) -> tuple[float, float, float, float] | None:
    """Slope, intercept and their standard errors; None when x is flat."""
    n = len(x)
    mx, my = math.fsum(x) / n, math.fsum(y) / n
    sxx = math.fsum((a - mx) ** 2 for a in x)
    if sxx <= _EPS:
        return None
    slope = math.fsum((a - mx) * (b - my) for a, b in zip(x, y)) / sxx
    intercept = my - slope * mx
    s2 = math.fsum((b - intercept - slope * a) ** 2 for a, b in zip(x, y)) / (n - 2)
    return slope, intercept, math.sqrt(s2 / sxx), math.sqrt(s2 * (1 / n + mx * mx / sxx))


def _t(value: float, se: float) -> float | None:
    return value / se if se > _EPS else None


def beta(bot: Sequence[float], idx: Sequence[float]) -> Estimate:
    _paired(bot, idx)
    n = len(bot)
    guard = _guard(n, MIN_BETA_N)
    if guard:
        return guard
    fit = _ols(bot, idx)
    if fit is None:
        return Estimate(None, None, None, n, INDEX_FLAT)
    slope, _, se, _ = fit
    return Estimate(slope, se, _t(slope, se), n, None)


def alpha(bot: Sequence[float], idx: Sequence[float]) -> Estimate:
    _paired(bot, idx)
    n = len(bot)
    guard = _guard(n, MIN_ALPHA_N)
    if guard:
        return guard
    fit = _ols(bot, idx)
    if fit is None:
        return Estimate(None, None, None, n, INDEX_FLAT)
    _, intercept, _, intercept_se = fit
    value, se = intercept * TRADING_DAYS, intercept_se * TRADING_DAYS
    return Estimate(value, se, _t(value, se), n, None)


def _sides(bot: Sequence[float], idx: Sequence[float]) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    up, down = [], []
    for b, i in zip(bot, idx):
        if i > 0:
            up.append((b, i))
        elif i < 0:
            down.append((b, i))
    return up, down


def _capture_side(pairs: list[tuple[float, float]]) -> float:
    return math.fsum(b for b, _ in pairs) / math.fsum(i for _, i in pairs)


def capture(bot: Sequence[float], idx: Sequence[float]) -> Capture:
    _paired(bot, idx)
    up, down = _sides(bot, idx)
    up_n, down_n = len(up), len(down)
    if min(up_n, down_n) < MIN_CAPTURE_SIDE_N:
        return Capture(None, None, None, up_n, down_n, CAPTURE_REASON)
    up_value, down_value = _capture_side(up), _capture_side(down)
    return Capture(up_value, down_value, up_value / down_value if down_value != 0 else None,
                   up_n, down_n, None)


def beat_count(bot: Sequence[float], idx: Sequence[float]) -> BeatCount:
    _paired(bot, idx)
    up, down = _sides(bot, idx)
    return BeatCount(len(up), sum(b > i for b, i in up), len(down), sum(b > i for b, i in down))
