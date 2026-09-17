import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.edge.context import FEATURE_KEYS
from tests.helpers import make_ohlcv

pytestmark = pytest.mark.slow

GATES = {"min_reward_pct": 1.0, "min_stop_distance_pct": 0.5,
         "max_stop_distance_pct": 15.0, "min_risk_reward": 0.0,
         "min_confluence": 1, "cooldown_bars": 5}


def _structured_df():
    rng = np.random.RandomState(7)
    trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, 120)))
    box = [trend[-1] * (1 + 0.05 * np.sin(index / 4)) for index in range(60)]
    return make_ohlcv(trend + box)


def test_replayed_plans_carry_context_from_the_window():
    df = _structured_df()
    asof = pd.DataFrame({"regime2_state": "bull_quiet", "rs_pctile": 80.0,
                         "sector_pctile": np.nan, "rs_combined": 80.0}, index=df.index)
    output = bs.replay_scenarios("AAPL", df, "4w", gates=GATES, asof=asof)
    assert output, "fixture must yield at least one plan"
    for index, plan in output:
        assert set(plan.entry_context) == set(FEATURE_KEYS)
        assert plan.entry_context["regime2_state"] == "bull_quiet"
        assert plan.entry_context["dow"] == df.index[index].dayofweek


def test_replay_without_asof_leaves_cross_sectional_none():
    output = bs.replay_scenarios("AAPL", _structured_df(), "4w", gates=GATES)
    assert all(plan.entry_context["rs_pctile"] is None for _, plan in output)
