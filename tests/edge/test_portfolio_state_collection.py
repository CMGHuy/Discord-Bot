"""Characterize portfolio collection before its reporting contract changes."""
import pandas as pd
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
    monkeypatch.setattr(data, "get_daily_data", lambda ticker: pd.DataFrame({"Close": [1.0, 1.1]}))
    monkeypatch.setattr(correlation, "cluster_exposure", lambda *a, **kw: {"cluster": ["AAA", "BBB"]})
    monkeypatch.setattr(throttle, "current_throttle", lambda *a, **kw: (0.75, False))
    monkeypatch.setattr(throttle, "kill_state", lambda: {"on": False, "reason": None})
    return trades


def boom(*args, **kwargs):
    raise OSError("synthetic collection failure")


def test_characterized_success_has_original_fields(collected):
    state = ps.collect_portfolio_state()
    assert set(state) == {"open_heat", "heat_cap", "sector_heat", "unmapped_count",
                          "throttle_mult", "paused", "kill", "growth", "clusters",
                          "open_trades", "balance", "availability"}
    assert state["open_heat"] == pytest.approx(0.6)
    assert state["sector_heat"] == {"Tech": pytest.approx(0.6)}
    assert state["unmapped_count"] == 0
    assert state["clusters"] == [["AAA", "BBB"]]
    assert state["throttle_mult"] == 0.75
    assert state["paused"] is False
    assert state["growth"] == {}


def test_failed_trade_read_is_unknown(monkeypatch, collected):
    from swingbot.core.tracking.performance import TradeLog
    monkeypatch.setattr(TradeLog, "get_trades", boom)
    state = ps.collect_portfolio_state()
    assert state["open_heat"] is None
    assert state["sector_heat"] is None
    assert state["clusters"] is None
    assert state["availability"]["positions"]["state"] == "unavailable"


def test_failed_controls_are_unknown(monkeypatch, collected):
    from swingbot.core.edge import throttle
    monkeypatch.setattr(throttle, "current_throttle", boom)
    monkeypatch.setattr(throttle, "kill_state", boom)
    state = ps.collect_portfolio_state()
    assert state["throttle_mult"] is None
    assert state["paused"] is None
    assert state["kill"]["on"] is None


def test_characterized_cluster_failure_does_not_blank_heat(monkeypatch, collected):
    from swingbot.core.edge import correlation
    monkeypatch.setattr(correlation, "cluster_exposure", boom)
    state = ps.collect_portfolio_state()
    assert state["clusters"] is None
    assert state["open_heat"] == pytest.approx(0.6)


@pytest.mark.parametrize("balance", [0, -1, float("nan"), float("inf"), "bad", None])
def test_invalid_balance_retains_identities_without_heat(monkeypatch, collected, balance):
    from swingbot.core.planning import account
    monkeypatch.setattr(account, "load_account_config", lambda: {"balance": balance})
    state = ps.collect_portfolio_state()
    assert state["open_trades"] == collected
    assert state["availability"]["positions"]["state"] == "ok"
    assert state["open_heat"] is None
    assert state["sector_heat"] is None
    assert state["availability"]["heat"]["reason"] == "invalid_balance"


def test_account_failure_is_not_measured_zero(monkeypatch, collected):
    from swingbot.core.planning import account
    monkeypatch.setattr(account, "load_account_config", boom)
    state = ps.collect_portfolio_state()
    assert state["open_trades"] == collected
    assert state["balance"] is None
    assert state["open_heat"] is None
    assert state["availability"]["heat"]["reason"] == "account_unavailable"


def test_known_empty_is_ok(monkeypatch, collected):
    from swingbot.core.tracking.performance import TradeLog
    monkeypatch.setattr(TradeLog, "get_trades", lambda self, **kw: [])
    state = ps.collect_portfolio_state()
    assert state["open_trades"] == []
    assert state["open_heat"] == 0
    assert state["clusters"] == []
    assert state["availability"]["positions"]["state"] == "ok"
    assert state["availability"]["heat"]["state"] == "ok"


def test_heat_failure_preserves_positions_and_controls(monkeypatch, collected):
    from swingbot.core.edge import heat
    monkeypatch.setattr(heat, "open_heat", boom)
    state = ps.collect_portfolio_state()
    assert state["open_trades"] == collected
    assert state["open_heat"] is None
    assert state["availability"]["heat"]["reason"] == "heat_unavailable"
    assert state["kill"]["on"] is False


def test_partial_sector_map_is_distinct_from_failed_map(monkeypatch, collected):
    from swingbot.core.marketdata import universe
    monkeypatch.setattr(universe, "sector_map", lambda name: {"AAA": "Tech"})
    partial = ps.collect_portfolio_state()
    assert partial["unmapped_count"] == 1
    assert partial["availability"]["sector_heat"]["state"] == "partial"
    monkeypatch.setattr(universe, "sector_map", boom)
    failed = ps.collect_portfolio_state()
    assert failed["sector_heat"] is None
    assert failed["availability"]["sector_heat"]["reason"] == "sector_map_unavailable"


def test_missing_cluster_bars_cannot_claim_no_clusters(monkeypatch, collected):
    from swingbot.core.marketdata import data
    monkeypatch.setattr(data, "get_daily_data", boom)
    state = ps.collect_portfolio_state()
    assert state["clusters"] is None
    assert state["availability"]["clusters"]["state"] == "unavailable"


def test_statuses_have_utc_checks_and_sanitized_reasons(monkeypatch, collected):
    from datetime import datetime
    from swingbot.core.edge import throttle
    monkeypatch.setattr(throttle, "kill_state", boom)
    state = ps.collect_portfolio_state()
    for status in state["availability"].values():
        assert datetime.fromisoformat(status["checked_at"]).utcoffset().total_seconds() == 0
    assert "synthetic collection failure" not in str(state)


def test_partial_cluster_bars_preserve_coverage_warning(monkeypatch, collected):
    import pandas as pd
    from swingbot.core.marketdata import data

    def read(ticker):
        if ticker == "BBB":
            return boom()
        return pd.DataFrame({"Close": [1.0, 1.1]})

    monkeypatch.setattr(data, "get_daily_data", read)
    state = ps.collect_portfolio_state()
    assert state["availability"]["clusters"]["state"] == "partial"
    assert state["availability"]["clusters"]["reason"] == "clusters_incomplete"
    assert state["open_heat"] == pytest.approx(0.6)
