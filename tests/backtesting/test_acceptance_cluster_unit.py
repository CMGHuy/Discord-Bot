"""v136 §4: every v2 verdict resamples ISO entry weeks; v1 keeps tickers.
The unit is a plain parameter; phase 6 maps --instrument v2 to it."""
import numpy as np
import pytest

from swingbot.core.backtesting import acceptance
from swingbot.core.backtesting.instrument import stats
from tests.backtesting._cluster_fixture import FAST, pinned_arms


def test_cluster_units_are_ticker_and_week():
    assert acceptance.CLUSTER_UNITS == ("ticker", "week")


def test_week_unit_delegates_to_the_instrument_stats_bootstrap():
    b, c = pinned_arms()
    via_gate = acceptance.cluster_bootstrap(
        b, c, acceptance.delta_standardised_win_rate, cluster="week", **FAST)
    direct = stats.week_cluster_bootstrap(
        b, c, acceptance.delta_standardised_win_rate, **FAST)
    assert np.array_equal(via_gate, direct)


def test_week_and_ticker_units_draw_differently():
    b, c = pinned_arms()
    by_ticker = acceptance.cluster_bootstrap(b, c, acceptance.delta_expectancy_r, **FAST)
    by_week = acceptance.cluster_bootstrap(b, c, acceptance.delta_expectancy_r,
                                           cluster="week", **FAST)
    assert not np.array_equal(by_ticker, by_week)


@pytest.mark.parametrize("bad", ["Ticker", "day", ""])
def test_an_unknown_unit_is_refused(bad):
    b, c = pinned_arms()
    with pytest.raises(ValueError, match="cluster"):
        acceptance.cluster_bootstrap(b, c, acceptance.delta_expectancy_r,
                                     cluster=bad, **FAST)


def test_bootstrap_delta_threads_the_unit():
    b, c = pinned_arms()
    by_ticker = acceptance.bootstrap_delta(b, c, acceptance.delta_expectancy_r, **FAST)
    by_week = acceptance.bootstrap_delta(b, c, acceptance.delta_expectancy_r,
                                         cluster="week", **FAST)
    assert by_ticker.point == by_week.point   # the point estimate is unit-free
    assert (by_ticker.lo, by_ticker.hi) != (by_week.lo, by_week.hi)


def test_mde_paired_threads_the_unit():
    b, c = pinned_arms()
    kw = dict(observed_n=len(c), target_n=1000, **FAST)
    by_ticker = acceptance.mde_paired(b, c, acceptance.delta_expectancy_r, **kw)
    by_week = acceptance.mde_paired(b, c, acceptance.delta_expectancy_r,
                                    cluster="week", **kw)
    assert by_ticker != by_week


def test_evaluate_records_and_renders_the_week_unit():
    b, c = pinned_arms()
    result = acceptance.evaluate(b, c, stage="walkforward", cluster="week", **FAST)
    assert result.cluster == "week"
    assert acceptance.render_json(result)["cluster"] == "week"
    text = acceptance.render_markdown(result, title="t", window="w")
    assert "bootstrap seed 42, clustered by ISO week of entry date." in text


def test_evaluate_refuses_an_unknown_unit_before_scoring():
    b, c = pinned_arms()
    with pytest.raises(ValueError, match="cluster"):
        acceptance.evaluate(b, c, stage="walkforward", cluster="weekly", **FAST)


def test_ticker_default_keeps_the_v1_rendering():
    b, c = pinned_arms()
    result = acceptance.evaluate(b, c, stage="walkforward", **FAST)
    assert result.cluster == "ticker"
    assert "cluster" not in acceptance.render_json(result)
    text = acceptance.render_markdown(result, title="t", window="w")
    assert "bootstrap seed 42." in text
    assert "clustered by" not in text
