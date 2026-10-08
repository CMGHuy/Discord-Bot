"""v141: trades and alert volume against the market's daily move.

Pure arithmetic -- no I/O, no network, no cache reads. The report script
(scripts/reports/market_day_report.py) owns loading; a later admin panel
re-uses these functions unchanged.

THE LAG RULE. A trade opened on day t may only be explained by `prior_day`
and `trailing_5d`, both built from closes up to t-1. `same_day` uses day t's
own close, which no scan knew: it describes, it can never gate.
"""
from __future__ import annotations

import pandas as pd

FORMS: tuple[str, ...] = ("same_day", "prior_day", "trailing_5d")
# Fixed before any number was read. Redrawing these after seeing a table is
# the exact move the one-shot discipline exists to prevent.
BUCKETS: tuple[str, ...] = ("< -1%", "-1% .. 0", "0 .. +1%", "> +1%")
MIN_DAYS = 10            # below this a bucket shows counts and no rate


def bucket_of(ret: float | None) -> str | None:
    """The bucket of a percent return; None for a missing one."""
    if ret is None or ret != ret:
        return None
    if ret < -1.0:
        return BUCKETS[0]
    if ret < 0.0:
        return BUCKETS[1]
    if ret <= 1.0:
        return BUCKETS[2]
    return BUCKETS[3]


def _number(value) -> float | None:
    return None if value != value else float(value)


def market_days(spy_close: pd.Series, regimes: pd.Series | None = None) -> dict[str, dict]:
    """{day: {same_day, prior_day, trailing_5d, regime}} for every bar.

    `regimes` is regime2.regime_series' label per bar ("bull_quiet", ...);
    the stored regime is the trend word of day t-1, so it is known at t.
    """
    ret = spy_close.pct_change() * 100.0
    frame = pd.DataFrame({
        "same_day": ret,
        "prior_day": ret.shift(1),
        "trailing_5d": (spy_close.shift(1) / spy_close.shift(6) - 1.0) * 100.0,
    })
    trend = regimes.shift(1) if regimes is not None else None
    out: dict[str, dict] = {}
    for ts, row in frame.iterrows():
        label = trend.get(ts) if trend is not None else None
        out[str(ts.date())] = {
            **{form: _number(row[form]) for form in FORMS},
            "regime": label.split("_")[0] if isinstance(label, str) else None,
        }
    return out


def days_in(days: dict, form: str, bucket: str, regime: str | None = None) -> list[str]:
    """Days whose `form` return falls in `bucket` (and in `regime`, if given)."""
    return [day for day, market in days.items()
            if bucket_of(market[form]) == bucket
            and (regime is None or market["regime"] == regime)]
