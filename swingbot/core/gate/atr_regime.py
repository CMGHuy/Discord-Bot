"""ATR-percentile regime checks. Percentile uses MIDRANK so a
constant-volatility series sits mid-band, not at 100.

Two deliberate departures from the obvious implementation, both needed to
make that true:

1. The ranking series is a FINITE-MEMORY TR mean (rolling 14), not the
   Wilder ewm that `indicators.atr` provides. Wilder's ewm approaches its
   steady state asymptotically: with alpha=1/14 the residual needs ~130
   bars to fall to 1e-6, so on a steady tape the whole 252-bar window is
   one monotonically rising transient and the newest bar is the maximum by
   construction — a flat 1%-a-day series ranks at the 100th percentile and
   the check reports "ATR spiked, stop math unreliable" on the calmest
   possible tape. A rolling mean forgets after 14 bars, so steady
   volatility gives genuinely repeated values for midrank to tie.
   `indicators.atr` stays Wilder's everywhere else — stop sizing wants the
   smooth estimator; only *ranking* needs the finite window.
2. Ties are compared within a relative tolerance, mopping up the float
   noise that would otherwise order values that are equal in every
   meaningful sense."""
from __future__ import annotations

import pandas as pd

from swingbot.core.gate.registry import CHECKS, ThresholdSpec, register
from swingbot.core.gate.types import CheckResult

_TIE_TOL = 1e-6        # relative; float noise only, orders of magnitude
                       # below any real volatility difference
_RANK_PERIOD = 14      # TR-mean window; matches indicators.atr's period


def _tr_mean(df: pd.DataFrame, period: int = _RANK_PERIOD) -> pd.Series:
    """True range averaged over a FIXED window — see module docstring for
    why ranking cannot use Wilder's ewm."""
    prev_close = df["Close"].shift(1)
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - prev_close).abs(),
        (df["Low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _atr_percentile(df_daily) -> tuple[float | None, float | None]:
    atr_pct = (_tr_mean(df_daily) / df_daily["Close"]).dropna()
    if len(atr_pct) < 60:
        return None, None
    window = atr_pct.iloc[-252:]
    last = float(atr_pct.iloc[-1])
    tol = abs(last) * _TIE_TOL
    midrank = 100.0 * (float((window < last - tol).mean())
                       + float((window <= last + tol).mean())) / 2.0
    return midrank, last * 100.0


def check_atr_normal(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    spec = CHECKS["atr_normal"]
    pctile, atr_pct = _atr_percentile(df_daily)
    if pctile is None:
        return CheckResult("atr_normal", "context", "unknown", 6.0,
                           "insufficient history for ATR percentile", {})
    evidence = {"percentile": round(pctile, 1), "atr_pct": round(atr_pct, 2)}
    if pctile > spec.threshold("pct_spike"):
        return CheckResult("atr_normal", "context", "fail", 6.0,
                           f"ATR spiked ({pctile:.0f}th pct) — stop math unreliable",
                           evidence)
    if pctile < spec.threshold("pct_low"):
        return CheckResult("atr_normal", "context", "warn", 6.0,
                           f"volatility compressed ({pctile:.0f}th pct) — "
                           f"breakout fuel but whipsaw risk", evidence)
    if pctile > spec.threshold("pct_high"):
        return CheckResult("atr_normal", "context", "warn", 6.0,
                           f"volatility elevated ({pctile:.0f}th pct)", evidence)
    return CheckResult("atr_normal", "context", "pass", 6.0,
                       f"volatility normal ({pctile:.0f}th pct)", evidence)


register(check_id="atr_normal", section="context", weight=6.0, func=check_atr_normal,
         thresholds={
             "pct_low": ThresholdSpec("pct_low", 20.0, 0.0, 40.0, 5.0,
                 "lower to accept more compression without a warn",
                 presets={"strict": 25.0, "balanced": 20.0, "relaxed": 10.0}),
             "pct_high": ThresholdSpec("pct_high", 80.0, 60.0, 100.0, 5.0,
                 "raise to accept more elevated volatility",
                 presets={"strict": 75.0, "balanced": 80.0, "relaxed": 90.0}),
             "pct_spike": ThresholdSpec("pct_spike", 95.0, 80.0, 100.0, 1.0,
                 "raise to fail only on the most extreme spikes",
                 presets={"strict": 90.0, "balanced": 95.0, "relaxed": 99.0}),
         })
