"""v103: build_strategy_plan's per-strategy dispatch is a table, not an elif chain."""
from swingbot.core.market.strategy_types import SHORT_STRATEGIES
from swingbot.core.planning import builders


def test_structural_strategies_have_their_own_branch():
    assert set(builders._STRUCTURAL_BRANCHES) == {
        "Fibonacci", "Support/Resistance", "Elliott Wave", "Fibonacci Continuation",
        *SHORT_STRATEGIES,
    }


def test_every_other_strategy_falls_back_to_the_atr_branch():
    assert builders._STRUCTURAL_BRANCHES.get("MACD", builders._atr_branch) is builders._atr_branch
