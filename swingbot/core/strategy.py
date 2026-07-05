"""
Strategy layer: independent swing-trade signal types, each evaluated
across five swing horizons (2 weeks, 4 weeks, 2 months, 3 months,
6 months) -- capped at 6 months max; further out gets too speculative
for a mechanically-detected level to mean much.

This bot trades the underlying STOCK/ETF directly: a bullish signal is a
recommendation to go LONG (buy), a bearish signal is a recommendation to
go SHORT (sell short). No options are involved.

Horizons change which indicator settings AND risk sizing are used -- a
"2 week" swing uses fast-reacting indicators and a tight, realistic
target sized for a short hold; a "12 month" swing uses slower indicators
and a much wider target appropriate for a longer hold.

Risk framework is deliberately modeled on classic disciplined
swing/position trading practice (the approach popularized by William
O'Neil's CANSLIM and Mark Minervini's SEPA): cut losses fast and small
(3-12% depending on horizon, no exceptions), and take profit in a
15-30% zone -- the recommended take-profit scales toward the ~30%
ceiling for the strongest, highest-conviction setups (confirmed by
volume or a wide reward:risk structure) and toward the low end for
weaker ones. This is NOT applied as aggressively to the 2-week horizon:
expecting anywhere near 30% in 1-2 weeks from an ordinary swing setup
isn't disciplined trading, it's speculation, and a genuinely experienced
trader would say so rather than chase it.

Every take-profit the bot shows is a RECOMMENDATION, not a promise --
it's the level a disciplined trader would plan to take profit at, sized
by the same rules that a professional would actually use. Alerts are
additionally filtered to only surface setups whose recommended
take-profit implies at least `config.MIN_REWARD_PCT` potential gain
(default 5%) -- see scan_engine.py.

Strategies:
  1. EMA Crossover        - fast EMA crossing the slow EMA, RSI-filtered.
  2. VWAP                  - price crossing a rolling volume-weighted average.
  3. Fibonacci             - price testing a retracement level of the recent
                             swing high/low range.
  4. Support/Resistance    - price breaks above resistance (or below
                             support) established over the lookback window,
                             confirmed by above-average volume -- the
                             classic "breakout from a base" setup.

None of this is financial advice -- these are technical pattern flags,
not trade recommendations.

The individual signal-detection functions (one per strategy above, plus
RSI/MACD/Elliott Wave/MA Ribbon/Break & Retest/RSI Divergence/Volume
Profile) live in signals.py, and the SignalResult/HORIZONS/MIN_BARS
types they share live in strategy_types.py -- this module is just the
registry (STRATEGY_FUNCS) and the evaluate_all() runner that calls every
one of them for a given ticker. Both siblings are imported back here and
re-exported, so `from swingbot.core.strategy import <anything>` that
worked before this split still works identically.
"""
import pandas as pd

from .strategy_types import (
    FIB_TOLERANCE_PCT, HORIZONS, MACD_PERIODS_BY_HORIZON, MIN_BARS,
    RSI_OVERBOUGHT, RSI_OVERSOLD, SR_VOLUME_MULTIPLE, SignalResult,
)
from .signals import (
    break_retest_signal, compute_hvn_level, compute_volume_profile,
    ema_cross_signal, elliott_wave_signal, fibonacci_signal, ma_ribbon_signal,
    macd_signal, rsi_divergence_signal, rsi_signal, support_resistance_signal,
    volume_profile_signal, vwap_signal,
)


# ---------------------------------------------------------------------------
# Runner: evaluate every strategy across every horizon for one ticker
# ---------------------------------------------------------------------------
STRATEGY_FUNCS = {
    "EMA Crossover":    ema_cross_signal,
    "VWAP":             vwap_signal,
    "Fibonacci":        fibonacci_signal,
    "Support/Resistance": support_resistance_signal,
    "RSI":              rsi_signal,
    "MACD":             macd_signal,
    "Elliott Wave":     elliott_wave_signal,
    "MA Ribbon":        ma_ribbon_signal,
    "Break & Retest":   break_retest_signal,
    "RSI Divergence":   rsi_divergence_signal,
    "Volume Profile":   volume_profile_signal,
}

STRATEGY_SHORT_NAMES = {
    "EMA Crossover":    "EMA",
    "VWAP":             "VWAP",
    "Fibonacci":        "Fib",
    "Support/Resistance": "S/R",
    "RSI":              "RSI",
    "MACD":             "MACD",
    "Elliott Wave":     "Elliott",
    "MA Ribbon":        "MARib",
    "Break & Retest":   "B&R",
    "RSI Divergence":   "RSI Div",
    "Volume Profile":   "VolProf",
}


def evaluate_all(ticker: str, df: pd.DataFrame) -> list[SignalResult]:
    """Run all strategies across all horizons for which we have enough data."""
    results = []
    bars_available = len(df)

    for horizon_key in HORIZONS:
        if bars_available < MIN_BARS[horizon_key]:
            continue
        for strategy_name, func in STRATEGY_FUNCS.items():
            try:
                results.append(func(ticker, df, horizon_key))
            except Exception:
                continue

    return results
