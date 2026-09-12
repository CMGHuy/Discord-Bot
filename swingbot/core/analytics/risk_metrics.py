"""Portfolio-level risk metrics over the open paper book (v85 D37).

Every function here returns `None` rather than a number it cannot justify --
fewer than `_MIN_BARS` overlapping days, zero variance in a denominator, an
empty book. `None` is never `0.0`: a zero beta and an unknown beta are
opposite claims. None of these functions raises -- this module is called to
render a page, and a book with one position is a normal Tuesday, not an
error."""
from __future__ import annotations

import math

import pandas as pd

#: Fewer overlapping days than this and no distributional figure is reported.
#: 20 is one trading month -- below it the 5th percentile is one observation,
#: and one observation is an anecdote with a decimal point.
_MIN_BARS = 20

#: Trading days per year, for annualising a daily standard deviation.
_TRADING_DAYS_PER_YEAR = 252


def portfolio_returns(
    weights: dict[str, float], bars: dict[str, pd.DataFrame]
) -> pd.Series:
    """Daily simple returns per symbol, weighted by each position's share of
    total notional, summed per day.

    Days where any weighted position has no bar are dropped entirely -- a
    partial day would understate the spread rather than report it honestly.
    """
    if not weights or not bars:
        return pd.Series(dtype=float)

    per_symbol: dict[str, pd.Series] = {}
    for symbol, weight in weights.items():
        frame = bars.get(symbol)
        if frame is None or frame.empty:
            return pd.Series(dtype=float)
        per_symbol[symbol] = frame["Close"].pct_change().dropna() * weight

    combined = pd.DataFrame(per_symbol).dropna(how="any")
    if combined.empty:
        return pd.Series(dtype=float)
    return combined.sum(axis=1)


def value_at_risk(returns: pd.Series, level: float = 0.95) -> float | None:
    """Historical VaR: the `(1 - level)` quantile of daily returns, reported
    as a positive loss figure. Historical, not parametric -- a normal
    assumption on twenty positions of swing equity is a worse lie than a
    thin empirical quantile."""
    if len(returns) < _MIN_BARS:
        return None
    quantile = returns.quantile(1 - level)
    return -float(quantile)


def expected_shortfall(returns: pd.Series, level: float = 0.95) -> float | None:
    """Mean of the returns at or below the VaR quantile, as a positive loss
    figure."""
    var = value_at_risk(returns, level)
    if var is None:
        return None
    threshold = -var
    tail = returns[returns <= threshold]
    if tail.empty:
        return var
    return -float(tail.mean())


def annualised_vol(returns: pd.Series) -> float | None:
    """Sample standard deviation of daily returns, scaled by sqrt(252)."""
    if len(returns) < _MIN_BARS:
        return None
    daily = returns.std(ddof=1)
    if not daily or math.isclose(daily, 0.0):
        return None
    return float(daily * math.sqrt(_TRADING_DAYS_PER_YEAR))


def beta_vs(returns: pd.Series, benchmark: pd.Series) -> float | None:
    """covariance(returns, benchmark) / variance(benchmark), over the days
    the two series overlap."""
    aligned_returns, aligned_benchmark = returns.align(benchmark, join="inner")
    if len(aligned_returns) < _MIN_BARS:
        return None
    variance = aligned_benchmark.var(ddof=1)
    if not variance or math.isclose(variance, 0.0):
        return None
    covariance = aligned_returns.cov(aligned_benchmark)
    return float(covariance / variance)


def sharpe_of(r_multiples: list[float]) -> float | None:
    """mean(R) / stdev(R) over closed trades. No risk-free rate and no
    annualisation -- an R-multiple is already excess-over-risk, and
    annualising a series with no fixed cadence invents a time axis the data
    does not have."""
    if len(r_multiples) < 2:
        return None
    series = pd.Series(r_multiples, dtype=float)
    stdev = series.std(ddof=1)
    if not stdev or math.isclose(stdev, 0.0):
        return None
    return float(series.mean() / stdev)


def max_drawdown_r(r_multiples: list[float]) -> float | None:
    """The largest peak-to-trough fall of the cumulative R curve, as a
    positive number."""
    if not r_multiples:
        return None
    cumulative = pd.Series(r_multiples, dtype=float).cumsum()
    running_peak = cumulative.cummax()
    drawdown = running_peak - cumulative
    return float(drawdown.max())
