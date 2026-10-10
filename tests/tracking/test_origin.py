"""v144: the origin vocabulary, the plan fields and the trade-level origin."""
from types import SimpleNamespace

import pytest

from swingbot.core.analytics.journal import build_entry
from swingbot.core.planning.plan_types import plan_from_dict, plan_to_dict
from swingbot.core.tracking import origin
from swingbot.core.tracking.performance import TradeLog
from tests.planning.test_plan_engine_model import _plan


def test_vocabulary():
    assert origin.NEXT_SESSION == "next_session"
    assert origin.ORIGINS == ("next_session",)


@pytest.mark.parametrize("record,expected", [
    ({}, None), ({"origin": None}, None), ({"origin": "next_session"}, "next_session"),
    (SimpleNamespace(origin="next_session"), "next_session"), (SimpleNamespace(), None),
])
def test_origin_of_reads_dicts_and_objects(record, expected):
    assert origin.origin_of(record) == expected
    assert origin.is_regular(record) is (expected is None)


def test_in_cohort():
    regular, evening = {"id": "r"}, {"id": "e", "origin": "next_session"}
    assert [origin.in_cohort(r, None) for r in (regular, evening)] == [True, False]
    assert [origin.in_cohort(r, "next_session") for r in (regular, evening)] == [False, True]
    assert [origin.in_cohort(r, origin.ALL) for r in (regular, evening)] == [True, True]


def test_plan_fields_default_to_none_and_round_trip():
    plan = _plan()
    assert (plan.origin, plan.valid_session, plan.cancel_reason_message) == (None, None, None)
    plan.origin, plan.valid_session = "next_session", "2026-10-12"
    plan.cancel_reason_message = "No price data for 2026-10-12; plan expired unevaluated"
    back = plan_from_dict(plan_to_dict(plan))
    assert (back.origin, back.valid_session, back.cancel_reason_message) == (
        "next_session", "2026-10-12", plan.cancel_reason_message)


def _open(log, ticker="AAPL", **kw):
    return log.log_trade(ticker=ticker, strategy="MACD", horizon_key="3m", direction="bullish",
                         confidence_level=3, confidence_label="Medium", entry=100.0,
                         stop_loss=98.0, take_profit=105.0, **kw)


def test_log_trade_records_origin_and_defaults_to_regular():
    log = TradeLog()
    regular = log.get_trade_by_id(_open(log))
    evening = log.get_trade_by_id(_open(log, ticker="MSFT", origin="next_session"))
    assert regular["origin"] is None
    assert evening["origin"] == "next_session"


def test_open_trade_for_ticker_is_scoped_to_one_lane():
    log = TradeLog()
    evening_id = _open(log, origin="next_session")
    assert log.open_trade_for_ticker("AAPL") is None            # the regular lane sees no trade
    assert log.open_trade_for_ticker("AAPL", origin="next_session")["id"] == evening_id
    regular_id = _open(log)
    assert log.open_trade_for_ticker("AAPL")["id"] == regular_id
    assert log.open_trade_for_ticker("AAPL", origin="next_session")["id"] == evening_id


def test_journal_entry_copies_origin():
    trade = {"id": "t1", "ticker": "AAPL", "status": "win", "entry": 100.0, "stop_loss": 98.0,
             "exit_price": 104.0, "direction": "bullish", "origin": "next_session"}
    assert build_entry(trade, None)["origin"] == "next_session"
    trade.pop("origin")
    assert build_entry(trade, None)["origin"] is None
