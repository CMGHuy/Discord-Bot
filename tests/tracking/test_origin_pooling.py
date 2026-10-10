"""v144: every pooled figure is byte-identical with and without an outlook trade."""
from swingbot.core.analytics import pnl_calendar
from swingbot.core.analytics.journal import JournalStore
from swingbot.core.analytics.scope import closed_only
from swingbot.core.tracking import ledger
from swingbot.core.tracking.ledger import split_by_ledger
from swingbot.core.tracking.performance import TradeLog


def _open(log, ticker, **kw):
    return log.log_trade(ticker=ticker, strategy="MACD", horizon_key="3m", direction="bullish",
                         confidence_level=3, confidence_label="Medium", entry=100.0,
                         stop_loss=95.0, take_profit=110.0, source="strategy", **kw)


def _close(log, trade_id, status, exit_price, pnl):
    trade = log.get_trade_by_id(trade_id)
    trade.update(status=status, exit_price=exit_price, realized_pnl_amount=pnl,
                 closed_at="2026-09-17T20:00:00+00:00")
    log._db_upsert(trade)
    JournalStore().add({"trade_id": trade_id, "ticker": trade["ticker"], "strategy": "MACD",
                        "outcome": status, "r_realized": (exit_price - 100.0) / 5.0,
                        "closed_at": trade["closed_at"], "origin": trade.get("origin")})


def _figures(log):
    trades = log.get_trades(status=None, limit=None)
    closed = closed_only(trades)
    main, weak = split_by_ledger(closed)
    return {
        "stats_main": log.get_stats(),
        "stats_weak": log.get_stats(ledger="weak"),
        "stats_level_unexpanded": log.get_stats(3, expand=False),
        "main_ids": sorted(t["id"] for t in log.get_trades(status=None, limit=None, ledger="main")),
        "split": (sorted(t["id"] for t in main), sorted(t["id"] for t in weak)),
        "journal": sorted(e["trade_id"] for e in JournalStore().entries()),
        "calendar": pnl_calendar.load_rows(trade_log=log),
    }


def test_pooled_figures_ignore_an_outlook_trade():
    log = TradeLog()
    _close(log, _open(log, "AAPL"), "win", 108.0, 80.0)
    _close(log, _open(log, "MSFT"), "loss", 95.0, -50.0)
    _close(log, _open(log, "NVDA", ledger="weak"), "win", 104.0, 40.0)
    _open(log, "AMD")                                         # a regular open trade
    before = _figures(log)

    _close(log, _open(log, "TSLA", origin="next_session"), "win", 110.0, 100.0)
    _open(log, "META", origin="next_session")                 # an open outlook trade
    _close(log, _open(log, "AMZN", ledger="weak", origin="next_session"), "loss", 95.0, -50.0)

    assert _figures(log) == before


def test_the_cohort_is_still_readable_on_request():
    log = TradeLog()
    _close(log, _open(log, "TSLA", origin="next_session"), "win", 110.0, 100.0)
    assert [e["trade_id"] for e in JournalStore().entries(cohort="next_session")]
    assert JournalStore().entries() == []
    assert len(JournalStore().entries(cohort="all")) == 1


def test_ledger_predicates():
    evening = {"origin": "next_session"}
    assert ledger.is_main(evening) is False and ledger.is_weak(evening) is False
    assert ledger.is_weak({"ledger": "weak", "origin": "next_session"}) is False
    assert ledger.is_main({}) is True and ledger.is_weak({"ledger": "weak"}) is True
