"""v184: PlanManager.last_poll_demand -- the open-plan tickers one poll() asked
the quote batch for and the subset it priced, with no extra fetch. Unknown or
not-demanded is None, never an empty or all-unpriced demand."""
import datetime as dt
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.planning import plan_manager as pm
from swingbot.core.planning.plan_manager import PlanManager, PollDemand, QuotePrices

SATURDAY = dt.datetime(2026, 10, 24, 12, 0, tzinfo=dt.timezone.utc)   # always quiet hours


class _Store:
    """open_plans() hands out the given plans; get() returns None, so poll()
    skips every step after the price filter. No notices to resend."""

    def __init__(self, tickers):
        self._plans = [SimpleNamespace(ticker=t, plan_id=f"p{i}") for i, t in enumerate(tickers)]

    def all(self):
        return []

    def open_plans(self):
        return list(self._plans)

    def get(self, plan_id):
        return None


def _no_serial(ticker):
    raise AssertionError("the serial price_fn must not run beside a batch fn")


def _manager(tickers, batch):
    return PlanManager(_Store(tickers), _no_serial, price_batch_fn=batch)


@pytest.fixture(autouse=True)
def _every_hour_is_a_poll_hour(monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)


def test_unpriced_is_demanded_minus_priced_in_demanded_order():
    d = PollDemand(("MSFT", "AAPL", "NVDA"), frozenset({"AAPL"}))
    assert d.unpriced == ("MSFT", "NVDA")
    assert PollDemand((), frozenset()).unpriced == ()


def test_a_new_manager_has_demanded_nothing():
    assert _manager(["AAPL"], lambda t: {}).last_poll_demand is None


def test_poll_records_unique_tickers_and_the_close_filter():
    asked = []

    def batch(tickers):
        asked.append(list(tickers))
        return {"AAPL": 190.0, "MSFT": 0.0, "NVDA": -1.0, "TSLA": None}
    mgr = _manager(["AAPL", "MSFT", "AAPL", "NVDA", "TSLA", "AMD"], batch)
    assert mgr.poll() == []
    assert asked == [["AAPL", "MSFT", "NVDA", "TSLA", "AMD"]]       # one batch call, unchanged
    assert mgr.last_poll_demand == PollDemand(
        ("AAPL", "MSFT", "NVDA", "TSLA", "AMD"), frozenset({"AAPL"}))
    assert mgr.last_poll_demand.unpriced == ("MSFT", "NVDA", "TSLA", "AMD")


def test_quote_prices_from_the_shared_batch_are_read_as_a_dict():
    mgr = _manager(["AAPL", "MSFT"], lambda t: QuotePrices({"AAPL": 190.0}, {}))
    mgr.poll()
    assert mgr.last_poll_demand == PollDemand(("AAPL", "MSFT"), frozenset({"AAPL"}))


def test_a_swallowed_plan_step_failure_is_exposed_and_cleared_next_poll(monkeypatch):
    mgr = _manager(["AAPL"], lambda t: {"AAPL": 190.0})
    plan = SimpleNamespace(plan_id="p0", ticker="AAPL", status=pm.PlanStatus.ACTIVE)
    monkeypatch.setattr(mgr.store, "get", lambda plan_id: plan)
    monkeypatch.setattr(mgr, "_warn_legacy_open_risk", lambda plan: None)

    def fail_step(plan, price, now):
        raise RuntimeError("step failed")

    monkeypatch.setattr(mgr, "_step", fail_step)
    mgr.poll()
    assert mgr.last_poll_demand == PollDemand(("AAPL",), frozenset({"AAPL"}))
    assert mgr.last_poll_check_errors == ["AAPL"]
    monkeypatch.setattr(pm, "_MANAGER", mgr)
    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", True)
    assert pm.last_poll_check_errors() == ("AAPL",)

    monkeypatch.setattr(mgr.store, "get", lambda plan_id: None)
    mgr.poll()
    assert mgr.last_poll_check_errors == []
    assert pm.last_poll_check_errors() == ()


@pytest.mark.parametrize("result", [None, {}])
def test_an_empty_or_none_batch_leaves_every_ticker_unpriced(result):
    mgr = _manager(["AAPL", "MSFT"], lambda t: result)
    mgr.poll()
    assert mgr.last_poll_demand.unpriced == ("AAPL", "MSFT")


def test_a_raising_batch_leaves_every_ticker_unpriced():
    def boom(tickers):
        raise TimeoutError("hung")
    mgr = _manager(["AAPL"], boom)
    mgr.poll()
    assert mgr.last_poll_demand == PollDemand(("AAPL",), frozenset())


def test_no_open_plans_is_a_known_empty_demand_and_fetches_nothing():
    mgr = _manager([], lambda t: pytest.fail("no fetch with no open plans"))
    mgr.poll()
    assert mgr.last_poll_demand == PollDemand((), frozenset())


def test_the_serial_seam_records_no_demand():
    mgr = PlanManager(_Store(["AAPL"]), lambda t: 190.0)        # price_batch_fn is None
    mgr.poll()
    assert mgr.last_poll_demand is None


def test_quiet_hours_clear_the_previous_demand(monkeypatch):
    mgr = _manager(["AAPL"], lambda t: {"AAPL": 190.0})
    mgr.poll()
    assert mgr.last_poll_demand is not None
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", True)
    assert mgr.poll(now=SATURDAY) == []
    assert mgr.last_poll_demand is None


def test_module_accessor_is_none_while_the_manager_is_off(monkeypatch):
    mgr = _manager(["AAPL"], lambda t: {"AAPL": 190.0})
    mgr.poll()
    monkeypatch.setattr(pm, "_MANAGER", mgr)
    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", False)
    assert pm.last_poll_demand() is None


def test_module_accessor_never_builds_the_manager(monkeypatch):
    monkeypatch.setattr(pm, "_MANAGER", None)
    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", True)
    monkeypatch.setattr(pm, "_manager", lambda: pytest.fail("must not build the manager"))
    assert pm.last_poll_demand() is None
    assert pm._MANAGER is None


def test_module_accessor_returns_the_managers_last_demand(monkeypatch):
    mgr = _manager(["AAPL", "MSFT"], lambda t: {"MSFT": 410.0})
    mgr.poll()
    monkeypatch.setattr(pm, "_MANAGER", mgr)
    monkeypatch.setattr(config, "INTRADAY_MANAGER_V2", True)
    assert pm.last_poll_demand() == PollDemand(("AAPL", "MSFT"), frozenset({"MSFT"}))
