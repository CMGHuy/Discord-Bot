"""v136 §4: the harvest gate resamples ISO entry weeks under v2."""
import pytest

from swingbot.core.backtesting import acceptance
from swingbot.core.backtesting.acceptance_harvest import evaluate_harvest
from tests.backtesting._cluster_fixture import FAST, pinned_arms


def test_evaluate_harvest_records_and_uses_the_week_unit():
    b, c = pinned_arms()
    by_ticker = evaluate_harvest(b, c, stage="walkforward", **FAST)
    by_week = evaluate_harvest(b, c, stage="walkforward", cluster="week", **FAST)
    assert (by_ticker.cluster, by_week.cluster) == ("ticker", "week")
    assert (by_ticker.clause("expectancy_gain").detail
            != by_week.clause("expectancy_gain").detail)
    assert acceptance.render_json(by_week)["cluster"] == "week"
    assert "cluster" not in acceptance.render_json(by_ticker)


def test_win_rate_floor_threads_the_unit():
    b, c = pinned_arms()
    by_ticker = evaluate_harvest(b, c, stage="walkforward", **FAST)
    by_week = evaluate_harvest(b, c, stage="walkforward", cluster="week", **FAST)
    assert (by_ticker.clause("win_rate_floor").value
            != by_week.clause("win_rate_floor").value)


def test_an_unknown_unit_is_refused():
    b, c = pinned_arms()
    with pytest.raises(ValueError, match="cluster"):
        evaluate_harvest(b, c, stage="walkforward", cluster="day", **FAST)
