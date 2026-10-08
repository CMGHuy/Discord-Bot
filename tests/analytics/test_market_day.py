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
