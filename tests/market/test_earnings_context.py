"""v104 §3.3/§3.4: earnings reaction sessions on the frame's own bar grid."""
import datetime as dt
from types import SimpleNamespace

import numpy as np
import pytest

from swingbot.core.market import earnings_calendar as ec
from swingbot.core.market import earnings_context as evt
from tests.helpers import make_ohlcv


def _source(*reports):
    return SimpleNamespace(reports=lambda ticker: list(reports))


def _df(n=30):
    return make_ohlcv([100.0] * n, start="2024-01-02")      # business days from Tue 2024-01-02


def test_before_open_reacts_the_same_day_after_close_the_next():
    df = _df()
    day = df.index[10].date()
    before = evt.reaction_positions(df.index, [ec.Report(day, ec.BEFORE_OPEN)])
    after = evt.reaction_positions(df.index, [ec.Report(day, ec.AFTER_CLOSE)])
    unconfirmed = evt.reaction_positions(df.index, [ec.Report(day, ec.UNCONFIRMED)])
    assert before == [10] and after == [11] and unconfirmed == [11]


def test_columns_mark_the_reaction_and_count_down_to_it():
    df = _df()
    out = evt.attach(df, "AAPL", source=_source(ec.Report(df.index[10].date(), ec.BEFORE_OPEN)))
    assert out["evt_reaction"].tolist().count(1.0) == 1 and out["evt_reaction"].iloc[10] == 1.0
    assert out["evt_bars_to_next"].iloc[7] == 3 and out["evt_bars_to_next"].iloc[10] == 0
    assert np.isnan(out["evt_bars_to_next"].iloc[11])            # no later report known


def test_a_report_after_the_last_bar_still_counts_down():
    df = _df(30)
    last = df.index[-1].date()                                   # a business day
    report_day = last + dt.timedelta(days=7)                     # one calendar week later
    out = evt.attach(df, "AAPL", source=_source(ec.Report(report_day, ec.BEFORE_OPEN)))
    assert out["evt_bars_to_next"].iloc[-1] == 5                 # 5 business days ahead
    assert out["evt_reaction"].sum() == 0


def test_no_reports_means_no_reaction_and_nan_distance():
    out = evt.attach(_df(), "SPY", source=_source())
    assert out["evt_reaction"].sum() == 0 and out["evt_bars_to_next"].isna().all()


@pytest.mark.parametrize("k", [5, 10, 20, 29])
def test_attach_is_truncation_invariant(k):
    df = _df(30)
    reports = (ec.Report(df.index[12].date(), ec.AFTER_CLOSE),
               ec.Report(df.index[-1].date() + dt.timedelta(days=14), ec.BEFORE_OPEN))
    full = evt.attach(df, "AAPL", source=_source(*reports)).iloc[k]
    cut = evt.attach(df.iloc[:k + 1], "AAPL", source=_source(*reports)).iloc[k]
    for col in evt.EVT_COLUMNS:
        assert full[col] == pytest.approx(cut[col], nan_ok=True)
