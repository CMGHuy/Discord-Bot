"""v141: market forms, buckets and per-bucket tables. Pure arithmetic."""
from __future__ import annotations

import pandas as pd
import pytest

from swingbot.core.analytics import market_day as md


def _close(values, start="2021-03-01"):
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)), dtype=float)


@pytest.mark.parametrize("ret,bucket", [
    (-1.5, "< -1%"), (-1.0, "-1% .. 0"), (-0.01, "-1% .. 0"),
    (0.0, "0 .. +1%"), (1.0, "0 .. +1%"), (1.01, "> +1%"),
])
def test_bucket_edges(ret, bucket):
    assert md.bucket_of(ret) == bucket


def test_bucket_of_missing_is_none():
    assert md.bucket_of(None) is None
    assert md.bucket_of(float("nan")) is None


def test_forms_are_percent_returns_and_prior_day_is_yesterdays_same_day():
    days = md.market_days(_close([100, 102, 101, 103, 104, 105, 106, 110]))
    keys = list(days)
    assert days[keys[0]]["same_day"] is None                 # no prior close
    assert days[keys[1]]["same_day"] == pytest.approx(2.0)
    assert days[keys[2]]["prior_day"] == pytest.approx(2.0)   # day 1's own return
    # trailing_5d on day 7: close[6] / close[1] - 1 = 106/102 - 1
    assert days[keys[7]]["trailing_5d"] == pytest.approx((106 / 102 - 1) * 100)
    assert days[keys[5]]["trailing_5d"] is None               # needs close[t-6]


def test_lagged_forms_do_not_move_when_later_bars_are_added():
    """prior_day and trailing_5d of day t use closes up to t-1 only, so
    appending or changing day t's own close cannot change them."""
    base = [100, 102, 101, 103, 104, 105, 106, 110]
    full = md.market_days(_close(base))
    bumped = md.market_days(_close(base[:-1] + [50]))
    last = list(full)[-1]
    assert full[last]["prior_day"] == bumped[last]["prior_day"]
    assert full[last]["trailing_5d"] == bumped[last]["trailing_5d"]
    assert full[last]["same_day"] != bumped[last]["same_day"]


def test_regime_is_the_prior_days_trend_word():
    close = _close([100, 101, 102])
    regimes = pd.Series(["bull_quiet", "bear_volatile", "bull_quiet"], index=close.index)
    days = md.market_days(close, regimes)
    keys = list(days)
    assert days[keys[0]]["regime"] is None
    assert days[keys[1]]["regime"] == "bull"
    assert days[keys[2]]["regime"] == "bear"


def test_days_in_filters_by_bucket_and_regime():
    days = {"2021-03-01": {"same_day": 1.5, "prior_day": None, "trailing_5d": None, "regime": "bull"},
            "2021-03-02": {"same_day": 1.2, "prior_day": 1.5, "trailing_5d": None, "regime": "bear"},
            "2021-03-03": {"same_day": -0.5, "prior_day": 1.2, "trailing_5d": None, "regime": "bear"}}
    assert md.days_in(days, "same_day", "> +1%") == ["2021-03-01", "2021-03-02"]
    assert md.days_in(days, "same_day", "> +1%", regime="bear") == ["2021-03-02"]
    assert md.days_in(days, "prior_day", "> +1%") == ["2021-03-02", "2021-03-03"]


def _days(returns, form="same_day", start="2021-03-01"):
    """One market day per return, all in the bull regime."""
    idx = pd.bdate_range(start, periods=len(returns))
    return {str(ts.date()): {"same_day": None, "prior_day": None, "trailing_5d": None,
                             "regime": "bull", form: ret}
            for ts, ret in zip(idx, returns)}


def _row(day, outcome="win", r=1.0, direction="bullish"):
    return {"day": day, "direction": direction, "outcome": outcome, "r": r}


def test_trade_table_counts_trades_and_distinct_days_per_bucket():
    days = _days([1.5] * 12 + [-1.5] * 12)
    keys = list(days)
    rows = [_row(d) for d in keys[:12]] + [_row(keys[0])]            # 13 trades, 12 green days
    rows += [_row(d, "loss", -1.0) for d in keys[12:]]               # 12 trades, 12 red days
    table = {r["bucket"]: r for r in md.trade_table(rows, days, "same_day")}
    assert (table["> +1%"]["n"], table["> +1%"]["days"]) == (13, 12)
    assert table["> +1%"]["win_rate"] == 100.0
    assert table["> +1%"]["exp_r"] == 1.0
    assert table["< -1%"]["win_rate"] == 0.0
    assert table["< -1%"]["exp_r"] == -1.0
    assert table["0 .. +1%"] == {"bucket": "0 .. +1%", "n": 0, "days": 0, "win_rate": None,
                                 "exp_r": None, "win_rate_ci": None, "exp_r_ci": None}


def test_a_bucket_below_the_day_floor_shows_counts_and_no_rate():
    days = _days([1.5] * 9)
    rows = [_row(d) for d in days] * 3            # 27 trades but only 9 days
    row = md.trade_table(rows, days, "same_day")[3]
    assert (row["n"], row["days"]) == (27, 9)
    assert row["win_rate"] is None and row["exp_r"] is None and row["win_rate_ci"] is None


def test_scratches_leave_the_win_rate_denominator_but_stay_in_exp_r():
    days = _days([1.5] * 10)
    keys = list(days)
    rows = [_row(d, "win", 2.0) for d in keys[:5]] + [_row(d, "scratch", 0.0) for d in keys[5:]]
    row = md.trade_table(rows, days, "same_day")[3]
    assert row["win_rate"] == 100.0          # 5 wins / 5 decided
    assert row["exp_r"] == 1.0               # (5*2 + 5*0) / 10


def test_direction_filter_and_regime_filter():
    days = _days([1.5] * 10)
    rows = [_row(d) for d in days] + [_row(d, direction="bearish") for d in days]
    assert md.trade_table(rows, days, "same_day")[3]["n"] == 10
    assert md.trade_table(rows, days, "same_day", direction="bearish")[3]["n"] == 10
    assert md.trade_table(rows, days, "same_day", regime="bear")[3]["n"] == 0


def test_interval_is_over_days_reproducible_and_brackets_the_point():
    days = _days([1.5] * 20)
    keys = list(days)
    rows = [_row(d, "win", 1.0) for d in keys[:10]] + [_row(d, "loss", -1.0) for d in keys[10:]]
    first = md.trade_table(rows, days, "same_day")[3]
    again = md.trade_table(rows, days, "same_day")[3]
    assert first["win_rate_ci"] == again["win_rate_ci"]            # fixed seed
    lo, hi = first["win_rate_ci"]
    assert lo < first["win_rate"] < hi
    assert md.trade_table(rows, days, "same_day", intervals=False)[3]["win_rate_ci"] is None


def test_many_trades_on_one_day_do_not_narrow_the_interval():
    """Ten trades on each of 20 days is still 20 observations."""
    days = _days([1.5] * 20)
    keys = list(days)
    one = [_row(d, "win", 1.0) for d in keys[:10]] + [_row(d, "loss", -1.0) for d in keys[10:]]
    ten = one * 10
    assert (md.trade_table(one, days, "same_day")[3]["win_rate_ci"]
            == md.trade_table(ten, days, "same_day")[3]["win_rate_ci"])


def test_rank_correlation_sign_and_floor():
    returns = [float(i) for i in range(-6, 6)]                       # 12 days
    days = _days(returns)
    keys = list(days)
    rising = [_row(d, "win", float(i)) for i, d in enumerate(keys)]
    falling = [_row(d, "win", float(-i)) for i, d in enumerate(keys)]
    assert md.day_rank_correlation(rising, days, "same_day") == 1.0
    assert md.day_rank_correlation(falling, days, "same_day") == -1.0
    assert md.day_rank_correlation(rising[:9], days, "same_day") is None   # < MIN_DAYS


def test_volume_counts_silent_days_in_the_denominator():
    days = _days([-1.5] * 10)
    keys = list(days)
    counts = {keys[0]: 4, keys[1]: 2}                 # eight days never appear
    row = md.volume_table(counts, days, "same_day")[0]
    assert row == {"bucket": "< -1%", "days": 10, "mean": 0.6, "median": 0.0, "zero_share": 80.0}


def test_volume_observed_restricts_the_denominator():
    """A day with no scan is an outage, not a silent day."""
    days = _days([-1.5] * 12)
    keys = list(days)
    counts = {keys[0]: 3}
    row = md.volume_table(counts, days, "same_day", observed=set(keys[:10]))[0]
    assert row["days"] == 10 and row["zero_share"] == 90.0


def test_volume_below_the_day_floor_shows_days_only():
    days = _days([-1.5] * 9)
    row = md.volume_table({}, days, "same_day")[0]
    assert row == {"bucket": "< -1%", "days": 9, "mean": None, "median": None, "zero_share": None}


def test_sum_by_bucket_adds_keys_over_present_days_only():
    days = _days([1.5, 1.5, -1.5])
    keys = list(days)
    values = {keys[0]: {"signals": 10, "taken": 4}, keys[2]: {"signals": 6, "taken": 1}}
    table = {r["bucket"]: r for r in md.sum_by_bucket(values, days, "same_day")}
    assert table["> +1%"] == {"bucket": "> +1%", "days": 1, "totals": {"signals": 10, "taken": 4}}
    assert table["< -1%"]["totals"] == {"signals": 6, "taken": 1}
    assert table["0 .. +1%"] == {"bucket": "0 .. +1%", "days": 0, "totals": {}}


def test_funnel_stage_counts_reads_one_direction_and_folds_reasons():
    snapshot = {
        "bullish/base/base/confidence/ok": 7,
        "bullish/base/base/confidence/min_confidence": 3,
        "bullish/base/base/confidence/min_confluence": 2,
        "bullish/base/base/send/ok": 4,
        "bearish/short_universe/weak/confidence/ok": 9,
        "malformed": 1,
    }
    assert md.funnel_stage_counts(snapshot) == {
        "confidence:ok": 7, "confidence:rejected": 5, "send:ok": 4}
    assert md.funnel_stage_counts(snapshot, "bearish") == {"confidence:ok": 9}
