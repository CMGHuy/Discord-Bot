"""v194 B6: sector heat that tells "no sector data" from "no exposure".

`collect_portfolio_state` over a fixed open book, with the account, trade
log, kill switch and daily bars stubbed so no database, file or network sits
behind it. The sector map is the variable under test."""
import logging

import pytest

from swingbot.commands.growth import portfolio_report
from swingbot.core.edge import heat, portfolio_state
from swingbot.core.marketdata import universe

BALANCE = 10_000.0
# Risk to stop: AAPL 2*10 = $20, MSFT 4*5 = $20, XYZ 1*20 = $20 -> 0.2% each.
OPEN = [
    {"ticker": "AAPL", "entry": 100.0, "stop_loss": 98.0, "shares": 10},
    {"ticker": "MSFT", "entry": 200.0, "stop_loss": 196.0, "shares": 5},
    {"ticker": "XYZ", "entry": 10.0, "stop_loss": 9.0, "shares": 20},
]
FULL_MAP = {"AAPL": "Technology", "MSFT": "Technology", "XYZ": "Industrials"}
LOGGER = "swingbot.core.edge.portfolio_state"


@pytest.fixture
def book(monkeypatch):
    from swingbot.core.edge import throttle
    from swingbot.core.marketdata import data as data_module
    from swingbot.core.planning import account as account_module
    from swingbot.core.tracking.performance import TradeLog

    monkeypatch.setattr(account_module, "load_account_config", lambda: {"balance": BALANCE})
    monkeypatch.setattr(account_module, "get_balance_history_points", lambda: [])
    monkeypatch.setattr(TradeLog, "get_trades", lambda self, status=None, limit=None: [dict(t) for t in OPEN])
    monkeypatch.setattr(throttle, "kill_state", lambda: {"on": False, "reason": None})

    def _no_bars(ticker):
        raise LookupError("no daily bars in this test")

    monkeypatch.setattr(data_module, "get_daily_data", _no_bars)

    def with_map(sectors):
        monkeypatch.setattr(universe, "sector_map", lambda name: dict(sectors))
        return portfolio_state.collect_portfolio_state()

    return with_map


def test_populated_map_heats_every_sector_and_leaves_none_unmapped(book):
    state = book(FULL_MAP)
    assert state["sector_heat"] == {"Technology": pytest.approx(0.4), "Industrials": pytest.approx(0.2)}
    assert state["unmapped_count"] == 0


def test_empty_map_counts_every_open_position_as_unmapped(book):
    state = book({})
    assert state["sector_heat"] == {}
    assert state["unmapped_count"] == 3


def test_map_missing_some_tickers_counts_only_those(book):
    state = book({"AAPL": "Technology"})
    assert state["sector_heat"] == {"Technology": pytest.approx(0.2)}
    assert state["unmapped_count"] == 2


def test_a_failing_sector_map_logs_a_warning_with_the_exception_text(book, monkeypatch, caplog):
    def _boom(name):
        raise ValueError("universe file is corrupt")

    monkeypatch.setattr(universe, "sector_map", _boom)
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        state = portfolio_state.collect_portfolio_state()
    assert state["sector_heat"] == {}
    assert state["unmapped_count"] == 3
    assert any(r.levelno == logging.WARNING and "universe file is corrupt" in r.getMessage()
               for r in caplog.records if r.name == LOGGER)


def test_a_failing_sector_heat_logs_a_warning_with_the_exception_text(book, monkeypatch, caplog):
    def _boom(open_trades, balance, sectors):
        raise ZeroDivisionError("heat blew up")

    monkeypatch.setattr(heat, "sector_heat", _boom)
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        state = book(FULL_MAP)
    assert state["sector_heat"] == {}
    assert any(r.levelno == logging.WARNING and "heat blew up" in r.getMessage()
               for r in caplog.records if r.name == LOGGER)


def test_unmapped_count_uses_the_same_test_as_sector_heat():
    # `sector_heat` skips a falsy sector; so does the count, so the two agree.
    sectors = {"AAPL": "Technology", "BLANK": ""}
    trades = [{"ticker": "AAPL"}, {"ticker": "BLANK"}, {"ticker": "NOPE"}, {}]
    assert portfolio_state._unmapped_count(trades, sectors) == 3
    assert portfolio_state._unmapped_count([], {}) == 0


def test_growth_portfolio_report_is_unchanged_for_a_populated_map(book):
    """`!portfolio` reads `sector_heat` as a dict and ignores the new key."""
    state = book(FULL_MAP)
    before = {k: v for k, v in state.items() if k != "unmapped_count"}
    out = portfolio_report(state)
    assert out == portfolio_report(before)
    assert "Technology" in out and "Industrials" in out
