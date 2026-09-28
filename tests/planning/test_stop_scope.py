"""v104 §2.1: which strategy x direction keep structural stops, and their ceiling."""
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.market.strategy_types import HORIZONS, SHORT_STRATEGIES
from swingbot.core.planning import stop_scope as ss
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT


def test_empty_scope_is_the_two_percent_cap_everywhere():
    for horizon in HORIZONS:
        assert ss.stop_ceiling("Fibonacci", "bullish", horizon, raw="") == (2.0, ss.CAP)


def test_scoped_pair_gets_the_horizon_ceiling_and_drop_mode():
    raw = "Fibonacci:bullish"
    assert ss.stop_ceiling("Fibonacci", "bullish", "4w", raw=raw) == (7.0, ss.DROP)
    assert ss.stop_ceiling("Fibonacci", "bearish", "4w", raw=raw) == (2.0, ss.CAP)
    assert ss.stop_ceiling("MACD", "bullish", "4w", raw=raw) == (2.0, ss.CAP)


def test_parsing_is_forgiving_and_ignores_junk():
    raw = " fibonacci : Bullish ,MACD:bullish,, nonsense ,Support/Resistance:bullish"
    assert ss.scope_pairs(raw) == frozenset({
        ("fibonacci", "bullish"), ("macd", "bullish"), ("support/resistance", "bullish")})


def test_short_strategies_are_always_in_scope():
    for name in SHORT_STRATEGIES:
        assert ss.in_scope(name, "bearish", raw="")
        assert ss.stop_ceiling(name, "bearish", "2m", raw="") == (HORIZONS["2m"]["max_risk_pct"], ss.DROP)


def test_raw_none_reads_config(monkeypatch):
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", "MACD:bullish", raising=False)
    assert ss.in_scope("MACD", "bullish")
    assert not ss.in_scope("MACD", "bearish")


def test_plan_ceiling_is_the_hard_cap_for_non_strategy_plans(monkeypatch):
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", "Fibonacci:bullish", raising=False)
    confluence = SimpleNamespace(source="confluence", strategy="Fibonacci", direction="bullish", horizon_key="4w")
    strategy = SimpleNamespace(source="strategy", strategy="Fibonacci", direction="bullish", horizon_key="4w")
    assert ss.plan_stop_ceiling(confluence) == HARD_MAX_PLANNED_LOSS_PCT
    assert ss.plan_stop_ceiling(strategy) == pytest.approx(7.0)


def test_config_default_is_empty():
    assert config.STRUCTURAL_STOP_SCOPE == ""
