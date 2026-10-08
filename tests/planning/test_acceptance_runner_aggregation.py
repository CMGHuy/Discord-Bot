"""v129: "acceptance_exit" is a new runner_outcome string; the pooling code
keys runner buckets by string, so it must count it without a KeyError."""
from swingbot.core.backtesting.backtest_scenarios import _aggregate
from swingbot.core.planning.exit_sim import simulate_exit
from tests.helpers import make_ohlcv
from tests.planning.test_exit_sim_acceptance import _bull


def test_scale_out_aggregation_counts_an_acceptance_exit_runner_leg():
    df = make_ohlcv([100.0, (100.0, 111.0, 97.0, 97.5), (97.5, 120.0, 97.0, 119.0)])
    res = simulate_exit(df, 0, _bull(), scale_out=True)
    assert res.runner_outcome == "acceptance_exit"
    agg = _aggregate([res])
    assert agg["runner"] == {"acceptance_exit": 1}
    assert agg["wins"] == 1 and agg["n"] == 1
