"""v171 D2: a trade stores the quote stamp of the plan it was opened from."""
import inspect

from swingbot.core.tracking import performance
from swingbot.core.tracking.performance import TradeLog, format_quote_age

QUOTE = {"at": "2026-10-16T14:30:01+00:00", "kind": "trade", "age_s": 2.3,
         "session": "regular", "confirmed": True}


def _open(log, **kw):
    return log.log_trade(ticker="AAPL", strategy="S/R Confluence", horizon_key="4w",
                         direction="bullish", confidence_level=3, confidence_label="Medium",
                         entry=100.0, stop_loss=98.0, take_profit=106.0, **kw)


def test_log_trade_stores_the_quote_stamp():
    log = TradeLog()
    trade = log.get_trade_by_id(_open(log, quote=QUOTE))
    assert trade["quote"] == QUOTE


def test_log_trade_copies_the_quote_dict():
    log = TradeLog()
    quote = dict(QUOTE)
    trade_id = _open(log, quote=quote)
    quote["age_s"] = 99.0
    assert log.get_trade_by_id(trade_id)["quote"]["age_s"] == 2.3


def test_log_trade_without_a_quote_writes_no_key():
    log = TradeLog()
    assert "quote" not in log.get_trade_by_id(_open(log))


def test_quote_is_the_last_keyword_and_defaults_to_none():
    params = inspect.signature(TradeLog.log_trade).parameters
    assert list(params)[-1] == "quote" and params["quote"].default is None


def test_quote_field_helper():
    assert performance._quote_field(None) == {}
    assert performance._quote_field(QUOTE) == {"quote": QUOTE}


def test_format_quote_age():
    assert format_quote_age(None) == "n/a"
    assert format_quote_age({"age_s": None}) == "n/a"
    assert format_quote_age({}) == "n/a"
    assert format_quote_age(QUOTE) == "2.3 s"
    assert format_quote_age({"age_s": 0}) == "0.0 s"
