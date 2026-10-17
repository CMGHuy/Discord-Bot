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


def _plan(strategy="Fibonacci", direction="bullish", entry=100.0, stop=91.0):
    return SimpleNamespace(strategy=strategy, direction=direction, trigger_price=entry, stop_loss=stop)


def _sizing(mode="risk_pct", balance=10_000.0, risk_pct=1.0, risk_amount=None, entry=100.0, stop=91.0):
    if risk_amount is None:
        risk_amount = balance * risk_pct / 100
    return {"mode": mode, "balance": balance, "risk_pct": risk_pct, "risk_amount": risk_amount,
            "shares": risk_amount / abs(entry - stop)}


def test_out_of_scope_plans_are_never_blocked(monkeypatch):
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", "", raising=False)
    assert ss.risk_sizing_ok(_plan(), sizing_fn=lambda entry, stop: None)


def test_in_scope_risk_pct_sizing_passes(monkeypatch):
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", "Fibonacci:bullish", raising=False)
    assert ss.risk_sizing_ok(_plan(), sizing_fn=lambda entry, stop: _sizing())


def test_risk_sizing_fails_closed_on_account_pct(monkeypatch):
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", "Fibonacci:bullish", raising=False)
    assert not ss.risk_sizing_ok(_plan(), sizing_fn=lambda entry, stop: _sizing(mode="account_pct"))


def test_risk_sizing_fails_closed_when_sizing_is_unavailable(monkeypatch):
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", "Fibonacci:bullish", raising=False)

    def boom(entry, stop):
        raise OSError("account file unreadable")

    assert not ss.risk_sizing_ok(_plan(), sizing_fn=lambda entry, stop: None)
    assert not ss.risk_sizing_ok(_plan(), sizing_fn=boom)
    assert not ss.risk_sizing_ok(_plan(), sizing_fn=lambda entry, stop: _sizing(risk_amount=0.0))


def test_risk_sizing_fails_closed_over_budget(monkeypatch):
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", "Fibonacci:bullish", raising=False)
    assert not ss.risk_sizing_ok(_plan(), sizing_fn=lambda entry, stop: _sizing(risk_amount=450.0))


def test_risk_sizing_rejects_rounded_shares_over_budget(monkeypatch):
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", "Fibonacci:bullish", raising=False)
    plan = _plan(stop=94.0)
    sizing = {"mode": "risk_pct", "balance": 10_000.0, "risk_pct": 1.0,
              "risk_amount": 100.0, "shares": 16.67}
    assert not ss.risk_sizing_ok(plan, sizing_fn=lambda entry, stop: sizing)


def test_shorts_are_always_checked(monkeypatch):
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", "", raising=False)
    short = _plan(strategy=SHORT_STRATEGIES[0], direction="bearish", stop=109.0)
    assert not ss.risk_sizing_ok(short, sizing_fn=lambda entry, stop: _sizing(mode="account_pct"))


def test_a_stored_ceiling_wins_for_any_source():
    confluence = SimpleNamespace(source="confluence", strategy="S/R Confluence",
                                 direction="bullish", horizon_key="4w", stop_ceiling_pct=4.0)
    assert ss.plan_stop_ceiling(confluence) == 4.0


def test_no_stored_ceiling_keeps_todays_answer(monkeypatch):
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", "", raising=False)
    confluence = SimpleNamespace(source="confluence", strategy="S/R Confluence",
                                 direction="bullish", horizon_key="4w", stop_ceiling_pct=None)
    assert ss.plan_stop_ceiling(confluence) == HARD_MAX_PLANNED_LOSS_PCT


def test_a_plan_with_a_stored_ceiling_is_always_sizing_checked(monkeypatch):
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", "", raising=False)
    plan = SimpleNamespace(strategy="S/R Confluence", direction="bullish",
                           trigger_price=100.0, stop_loss=96.0, stop_ceiling_pct=4.25)
    assert not ss.risk_sizing_ok(plan, sizing_fn=lambda e, s: _sizing(mode="account_pct", stop=96.0))
    assert ss.risk_sizing_ok(plan, sizing_fn=lambda e, s: _sizing(stop=96.0))


@pytest.mark.parametrize("d", [2.5, 4.0, 4.75])
def test_risk_pct_sizing_holds_the_dollar_loss_at_risk_per_trade(d, monkeypatch):
    from swingbot.core.market import opex
    from swingbot.core.planning import account
    monkeypatch.setattr(opex, "size_mult", lambda: 1.0)
    cfg = {"balance": 1_000_000.0, "risk_pct": config.RISK_PER_TRADE_PCT, "sizing_mode": "risk_pct",
           "max_position_pct": 100.0, "max_position_value_absolute": 0,
           "max_risk_amount_absolute": 0}
    entry = 100.0
    plan = SimpleNamespace(strategy="S/R Confluence", direction="bullish", trigger_price=entry,
                           stop_loss=entry * (1 - d / 100), stop_ceiling_pct=5.0)
    sizing = account.compute_position_size(entry, plan.stop_loss, cfg)
    budget = cfg["balance"] * config.RISK_PER_TRADE_PCT / 100
    distance = entry - plan.stop_loss
    assert sizing["mode"] == "risk_pct"
    assert sizing["shares"] * distance == pytest.approx(budget, abs=0.01 * distance)
    assert ss.risk_sizing_ok(plan, sizing_fn=lambda e, s: account.compute_position_size(e, s, cfg))
