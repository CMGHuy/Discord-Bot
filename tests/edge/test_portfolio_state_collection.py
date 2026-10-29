"""Characterize portfolio collection before its reporting contract changes."""
import pytest

from swingbot.core.edge import portfolio_state as ps


@pytest.fixture
def collected(monkeypatch):
    from swingbot.core.edge import correlation, throttle
    from swingbot.core.marketdata import data, universe
    from swingbot.core.planning import account
    from swingbot.core.tracking.performance import TradeLog

    trades = [{"id": "a", "ticker": "AAA", "risk_pct": 0.4},
              {"id": "b", "ticker": "BBB", "risk_pct": 0.2}]
    monkeypatch.setattr(account, "load_account_config", lambda: {"balance": 1000})
    monkeypatch.setattr(account, "get_balance_history_points", lambda: [])
    monkeypatch.setattr(TradeLog, "get_trades", lambda self, **kw: list(trades))
    monkeypatch.setattr(universe, "sector_map", lambda name: {"AAA": "Tech", "BBB": "Tech"})
    monkeypatch.setattr(data, "get_daily_data", lambda ticker: object())
    monkeypatch.setattr(correlation, "cluster_exposure", lambda *a, **kw: {"cluster": ["AAA", "BBB"]})
    monkeypatch.setattr(throttle, "current_throttle", lambda *a, **kw: (0.75, False))
    monkeypatch.setattr(throttle, "kill_state", lambda: {"on": False, "reason": None})
    return trades


def boom(*args, **kwargs):
    raise OSError("synthetic collection failure")


def test_characterized_success_has_original_fields(collected):
    state = ps.collect_portfolio_state()
    assert set(state) == {"open_heat", "heat_cap", "sector_heat", "unmapped_count",
                          "throttle_mult", "paused", "kill", "growth", "clusters"}
    assert state["open_heat"] == pytest.approx(0.6)
    assert state["sector_heat"] == {"Tech": pytest.approx(0.6)}
    assert state["unmapped_count"] == 0
    assert state["clusters"] == [["AAA", "BBB"]]
    assert state["throttle_mult"] == 0.75
    assert state["paused"] is False
    assert state["growth"] == {}


def test_characterized_failed_trade_read_is_empty(monkeypatch, collected):
    from swingbot.core.tracking.performance import TradeLog
    monkeypatch.setattr(TradeLog, "get_trades", boom)
    state = ps.collect_portfolio_state()
    assert state["open_heat"] == 0.0
    assert state["sector_heat"] == {}
    assert state["clusters"] == []


def test_characterized_failed_controls_use_legacy_defaults(monkeypatch, collected):
    from swingbot.core.edge import throttle
    monkeypatch.setattr(throttle, "current_throttle", boom)
    monkeypatch.setattr(throttle, "kill_state", boom)
    state = ps.collect_portfolio_state()
    assert state["throttle_mult"] == 1.0
    assert state["paused"] is False
    assert state["kill"] == {"on": False, "reason": None}


def test_characterized_cluster_failure_does_not_blank_heat(monkeypatch, collected):
    from swingbot.core.edge import correlation
    monkeypatch.setattr(correlation, "cluster_exposure", boom)
    state = ps.collect_portfolio_state()
    assert state["clusters"] == []
    assert state["open_heat"] == pytest.approx(0.6)
