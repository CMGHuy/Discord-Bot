"""v174 bond_spike_rebound: TLT 5-day return z >= +2.0 vs its trailing 252 values."""
import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen.ideas import bond_spike_rebound
from tests.backtesting.screen.helpers import assert_prefix_stable, frame, random_walk

SPIKE = 500   # the bar where TLT steps up 12 %


def _tlt(n=600, seed=11):
    """A TLT-like walk from 2009-06-01 with one +12 % step at bar SPIKE."""
    base = random_walk(n, seed=seed, start="2009-06-01")
    closes = base["Close"].to_numpy().copy()
    closes[SPIKE:] *= 1.12
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
    assert bond_spike_rebound.CONTEXT == ("TLT",)
    assert bond_spike_rebound.CAP == 10
    assert bond_spike_rebound.RACE == "fixed"
    assert bond_spike_rebound.PARAMS == {"series": "TLT", "lookback": 5, "window": 252,
                                         "z": 2.0, "side": "long"}
    assert bond_spike_rebound.SUMMARY == "TLT 5-day return z >= +2.0 vs its trailing 252 values"
    assert bond_spike_rebound.SOURCE == (
        "Murphy (2004), Intermarket Analysis — shock proxy, "
        "see v174 § What the two shots can and cannot say")


def test_fires_exactly_where_the_reference_z_reaches_plus_two():
    tlt = _tlt()
    out = bond_spike_rebound.events(tlt, {"TLT": tlt})
    expected = np.flatnonzero(np.nan_to_num(_reference_z(tlt["Close"]), nan=-np.inf) >= 2.0)
    assert SPIKE in expected                                  # non-vacuous
    assert np.flatnonzero(out.to_numpy()).tolist() == expected.tolist()
    assert out.dtype == bool and out.name == "bond_spike_rebound"
    assert out.index.equals(tlt.index)


def test_never_fires_before_the_window_is_full():
    tlt = _tlt()
    out = bond_spike_rebound.events(tlt, {"TLT": tlt})
    assert not out.iloc[:257].any()                           # 5 + 252 bars of warm-up


def test_a_stock_date_without_a_tlt_bar_is_false_never_forward_filled():
    tlt = _tlt()
    stock = frame(np.linspace(50, 60, len(tlt)), index=tlt.index)
    thin = tlt.drop(tlt.index[SPIKE + 1])
    out = bond_spike_rebound.events(stock, {"TLT": thin})
    assert out.index.equals(stock.index)
    assert out.loc[tlt.index[SPIKE]]                          # the spike day itself still fires
    assert not out.loc[tlt.index[SPIKE + 1]]                  # no TLT bar -> False, not carried


def test_a_tlt_only_date_is_ignored():
    tlt = _tlt()
    stock = frame(np.linspace(50, 60, len(tlt) - 1), index=tlt.index.delete(SPIKE))
    out = bond_spike_rebound.events(stock, {"TLT": tlt})
    assert out.index.equals(stock.index)
    assert tlt.index[SPIKE] not in out.index


def test_reads_no_later_tlt_bar():
    tlt = _tlt()
    assert bond_spike_rebound.events(tlt, {"TLT": tlt}).any()   # non-vacuous
    assert_prefix_stable(lambda d: bond_spike_rebound.events(d, {"TLT": d}), tlt,
                         [257, 300, SPIKE - 1, SPIKE, SPIKE + 4, 599])


def test_changing_a_tlt_bar_after_t_never_changes_the_event_at_t():
    tlt = _tlt()
    before = bond_spike_rebound.events(tlt, {"TLT": tlt})
    later = tlt.copy()
    later.iloc[SPIKE + 1:, later.columns.get_loc("Close")] *= 0.5
    after = bond_spike_rebound.events(tlt, {"TLT": later})
    pd.testing.assert_series_equal(after.iloc[:SPIKE + 1], before.iloc[:SPIKE + 1])
