from types import SimpleNamespace

from swingbot.core.plan_engine import primary_strategy_for
from swingbot.core.performance import primary_strategy_label


def _scenario(target_sources, stop_sources=()):
    return SimpleNamespace(direction="bullish", entry=100.0, stop_loss=95.0,
                           take_profit=110.0, target_sources=list(target_sources),
                           stop_sources=list(stop_sources))


def test_fibonacci_dominated_scenario_attributes_fibonacci():
    label = primary_strategy_for(_scenario(["Fib 61.8%", "Fib 50.0%", "EMA21"]))
    assert "Fib" in label or label == "Fibonacci"


def test_agrees_with_performance_label_ranking():
    # The scenario helper and the trade-dict helper must rank identically --
    # one METHOD_PRIORITY, two entry points.
    sources = ["Volume Profile HVN", "EMA21", "Bollinger upper"]
    assert primary_strategy_for(_scenario(sources)) == \
           primary_strategy_label({"target_sources": sources, "stop_sources": []})


def test_empty_sources_fall_back_to_confluence_literal():
    assert primary_strategy_for(_scenario([])) == "S/R Confluence"


def test_old_records_still_group():
    # grouping code must tolerate the legacy literal
    assert primary_strategy_label({"strategy": "S/R Confluence"}) == "S/R Confluence"
