"""v141: trades and alert volume against the market's daily move.

Pure arithmetic -- no I/O, no network, no cache reads. The report script
(scripts/reports/market_day_report.py) owns loading; a later admin panel
re-uses these functions unchanged.

THE LAG RULE. A trade opened on day t may only be explained by `prior_day`
and `trailing_5d`, both built from closes up to t-1. `same_day` uses day t's
own close, which no scan knew: it describes, it can never gate.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from swingbot.core.analytics import metrics

FORMS: tuple[str, ...] = ("same_day", "prior_day", "trailing_5d")
# Fixed before any number was read. Redrawing these after seeing a table is
# the exact move the one-shot discipline exists to prevent.
BUCKETS: tuple[str, ...] = ("< -1%", "-1% .. 0", "0 .. +1%", "> +1%")
MIN_DAYS = 10            # below this a bucket shows counts and no rate
BOOTSTRAP_N = 2000
BOOTSTRAP_SEED = 42


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


def _by_day(rows: list[dict], direction: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for row in rows:
        if row.get("direction") == direction and row.get("day"):
            out.setdefault(row["day"], []).append(row)
    return out


def _day_arrays(by_day: dict, day_list: list[str]):
    """Per-day (wins, decided, r_sum, r_count) -- what a day resample re-sums."""
    wins, decided, r_sum, r_count = [], [], [], []
    for day in day_list:
        rows = by_day[day]
        rs = [row["r"] for row in rows if row.get("r") is not None]
        wins.append(sum(1 for row in rows if row["outcome"] == "win"))
        decided.append(sum(1 for row in rows if row["outcome"] in ("win", "loss")))
        r_sum.append(sum(rs))
        r_count.append(len(rs))
    return tuple(np.array(a, dtype=float) for a in (wins, decided, r_sum, r_count))


def _interval(numer: np.ndarray, denom: np.ndarray, scale: float, rng) -> list[float] | None:
    """95% percentile interval of sum(numer)/sum(denom) over resampled DAYS.

    Trades opened on one day share that day's market, so the day is the unit
    that is exchangeable -- resampling trades would count one green day ten
    times and call it ten confirmations.
    """
    n_days = len(numer)
    idx = rng.integers(0, n_days, size=(BOOTSTRAP_N, n_days))
    dens = denom[idx].sum(axis=1)
    nums = numer[idx].sum(axis=1)
    values = nums[dens > 0] / dens[dens > 0] * scale
    if not len(values):
        return None
    lo, hi = np.percentile(values, [2.5, 97.5])
    return [round(float(lo), 2), round(float(hi), 2)]


def _bucket_row(bucket: str, by_day: dict, day_list: list[str], intervals: bool, rng) -> dict:
    rows = [row for day in day_list for row in by_day[day]]
    out = {"bucket": bucket, "n": len(rows), "days": len(day_list), "win_rate": None,
           "exp_r": None, "win_rate_ci": None, "exp_r_ci": None}
    if len(day_list) < MIN_DAYS:
        return out
    rs = [row["r"] for row in rows if row.get("r") is not None]
    win_rate = metrics.win_rate([{"status": row["outcome"]} for row in rows])
    out["win_rate"] = None if win_rate is None else round(win_rate, 2)
    out["exp_r"] = round(sum(rs) / len(rs), 4) if rs else None
    if intervals:
        wins, decided, r_sum, r_count = _day_arrays(by_day, day_list)
        out["win_rate_ci"] = _interval(wins, decided, 100.0, rng)
        out["exp_r_ci"] = _interval(r_sum, r_count, 1.0, rng)
    return out


def trade_table(rows: list[dict], days: dict, form: str, *, direction: str = "bullish",
                regime: str | None = None, intervals: bool = True) -> list[dict]:
    """One row per bucket for trades OPENED on days in that bucket."""
    by_day = _by_day(rows, direction)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    return [_bucket_row(bucket, by_day,
                        [day for day in days_in(days, form, bucket, regime) if day in by_day],
                        intervals, rng)
            for bucket in BUCKETS]


def day_rank_correlation(rows: list[dict], days: dict, form: str, *,
                         direction: str = "bullish") -> float | None:
    """Spearman rho between a day's market return and its mean trade R."""
    pairs = []
    for day, day_rows in _by_day(rows, direction).items():
        rs = [row["r"] for row in day_rows if row.get("r") is not None]
        market = days.get(day, {}).get(form)
        if rs and market is not None:
            pairs.append((market, sum(rs) / len(rs)))
    if len(pairs) < MIN_DAYS:
        return None
    x = pd.Series([p[0] for p in pairs]).rank()
    y = pd.Series([p[1] for p in pairs]).rank()
    rho = x.corr(y)
    return None if rho != rho else round(float(rho), 3)


def volume_table(counts: dict[str, int], days: dict, form: str, *,
                 observed: set[str] | None = None, regime: str | None = None) -> list[dict]:
    """Alerts (or trades) per day, per bucket, over EVERY day in the bucket.

    A day absent from `counts` is a zero, not a gap: the silent day is the
    thing being measured. `observed` narrows the denominator to days the
    source actually covered (live: days with at least one scan).
    """
    out = []
    for bucket in BUCKETS:
        day_list = [day for day in days_in(days, form, bucket, regime)
                    if observed is None or day in observed]
        row = {"bucket": bucket, "days": len(day_list), "mean": None, "median": None,
               "zero_share": None}
        if len(day_list) >= MIN_DAYS:
            values = np.array([counts.get(day, 0) for day in day_list], dtype=float)
            row["mean"] = round(float(values.mean()), 2)
            row["median"] = round(float(np.median(values)), 2)
            row["zero_share"] = round(float((values == 0).mean() * 100.0), 1)
        out.append(row)
    return out


def sum_by_bucket(day_values: dict[str, dict[str, float]], days: dict, form: str, *,
                  regime: str | None = None) -> list[dict]:
    """Per bucket, the key-wise sum of `day_values` over the days it holds."""
    out = []
    for bucket in BUCKETS:
        day_list = [day for day in days_in(days, form, bucket, regime) if day in day_values]
        totals: dict[str, float] = {}
        for day in day_list:
            for key, value in day_values[day].items():
                totals[key] = totals.get(key, 0) + value
        out.append({"bucket": bucket, "days": len(day_list), "totals": totals})
    return out


def funnel_stage_counts(snapshot: dict[str, int], direction: str = "bullish") -> dict[str, int]:
    """{"<stage>:ok"|"<stage>:rejected": n} for one direction.

    Keys are ShortFunnel.snapshot()'s "direction/source/mode/stage/reason";
    every reason other than "ok" is a rejection at that stage.
    """
    out: dict[str, int] = {}
    for key, count in snapshot.items():
        parts = key.split("/")
        if len(parts) != 5 or parts[0] != direction:
            continue
        name = f"{parts[3]}:{'ok' if parts[4] == 'ok' else 'rejected'}"
        out[name] = out.get(name, 0) + count
    return out
