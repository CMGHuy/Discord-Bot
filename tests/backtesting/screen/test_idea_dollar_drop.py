"""v174 dollar_drop: UUP 5-day return z <= -2.0 vs its trailing 252 values."""
import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen.ideas import dollar_drop
from tests.backtesting.screen.helpers import assert_prefix_stable, frame, random_walk

DROP = 500   # the bar where UUP steps down 12 %


def _uup(n=600, seed=13):
    """A UUP-like walk from 2009-06-01 with one -12 % step at bar DROP."""
    base = random_walk(n, seed=seed, start="2009-06-01")
    closes = base["Close"].to_numpy().copy()
    closes[DROP:] *= 0.88
    return frame(closes, start="2009-06-01")


def _reference_z(close: pd.Series, lookback=5, window=252) -> np.ndarray:
    """Brute force, one bar at a time: W = r[t-252..t-1], t excluded, ddof 0."""
    r = (close / close.shift(lookback) - 1.0).to_numpy()
    out = np.full(len(r), np.nan)
    for t in range(window, len(r)):
        w = r[t - window:t]
        if np.isnan(w).any() or np.isnan(r[t]):
            continue
        sd = w.std(ddof=0)
        if sd > 1e-12:
            out[t] = (r[t] - w.mean()) / sd
    return out


def test_the_constants_are_the_frozen_spec_values():
    assert dollar_drop.CONTEXT == ("UUP",)
    assert dollar_drop.CAP == 10
    assert dollar_drop.RACE == "fixed"
    assert dollar_drop.PARAMS == {"series": "UUP", "lookback": 5, "window": 252,
                                  "z": -2.0, "side": "long"}
    assert dollar_drop.SUMMARY == "UUP 5-day return z <= -2.0 vs its trailing 252 values"
    assert dollar_drop.SOURCE == (
        "Murphy (2004), Intermarket Analysis — shock proxy, "
        "see v174 § What the two shots can and cannot say")


def test_fires_exactly_where_the_reference_z_reaches_minus_two():
    uup = _uup()
    out = dollar_drop.events(uup, {"UUP": uup})
    expected = np.flatnonzero(np.nan_to_num(_reference_z(uup["Close"]), nan=np.inf) <= -2.0)
    assert DROP in expected                                   # non-vacuous
    assert np.flatnonzero(out.to_numpy()).tolist() == expected.tolist()
    assert out.dtype == bool and out.name == "dollar_drop"
    assert out.index.equals(uup.index)


def test_a_rise_never_fires_the_drop_idea():
    base = random_walk(600, seed=13, start="2009-06-01")
    closes = base["Close"].to_numpy().copy()
    closes[DROP:] *= 1.12
    up = frame(closes, start="2009-06-01")
    assert not dollar_drop.events(up, {"UUP": up}).iloc[DROP:DROP + 5].any()


def test_a_flat_series_has_no_z_and_never_fires():
    flat = frame(np.full(600, 25.0), start="2009-06-01")      # std(W) == 0 everywhere
    assert not dollar_drop.events(flat, {"UUP": flat}).any()


def test_a_stock_date_without_a_uup_bar_is_false_never_forward_filled():
    uup = _uup()
    stock = frame(np.linspace(50, 60, len(uup)), index=uup.index)
    thin = uup.drop(uup.index[DROP + 1])
    out = dollar_drop.events(stock, {"UUP": thin})
    assert out.loc[uup.index[DROP]]
    assert not out.loc[uup.index[DROP + 1]]


def test_reads_no_later_uup_bar():
    uup = _uup()
    assert dollar_drop.events(uup, {"UUP": uup}).any()        # non-vacuous
    assert_prefix_stable(lambda d: dollar_drop.events(d, {"UUP": d}), uup,
                         [257, 300, DROP - 1, DROP, DROP + 4, 599])


def test_changing_a_uup_bar_after_t_never_changes_the_event_at_t():
    uup = _uup()
    before = dollar_drop.events(uup, {"UUP": uup})
    later = uup.copy()
    later.iloc[DROP + 1:, later.columns.get_loc("Close")] *= 2.0
    after = dollar_drop.events(uup, {"UUP": later})
    pd.testing.assert_series_equal(after.iloc[:DROP + 1], before.iloc[:DROP + 1])
