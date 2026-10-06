"""v125: confluence replay (backtest_scenarios -> stamp_entry_context) flags from plan.trigger_price."""
import numpy as np
import pytest

from swingbot import config
from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.edge.context import PROVENANCE_KEYS, plan_provenance
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


def test_replayed_confluence_plans_carry_provenance_from_the_trigger(monkeypatch):
    monkeypatch.setattr(config, "MAX_RISK_REWARD_RATIO", 2.5)
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)
    output = bs.replay_scenarios("AAPL", _structured_df(), "4w", gates=GATES)
    assert output, "fixture must yield at least one plan"
    for _, plan in output:
        expected = plan_provenance(plan.trigger_price, plan.stop_loss, plan.tp1, 2.5)
        assert {key: plan.entry_context[key] for key in PROVENANCE_KEYS} == expected
        assert plan.entry_context["stop_clamped"] in (True, False)
    # prototype: 16 plans, 13 capped, 1 clamped -- both populations exist on this fixture
    assert any(plan.entry_context["target_capped"] for _, plan in output)
    assert any(plan.entry_context["stop_clamped"] for _, plan in output)
