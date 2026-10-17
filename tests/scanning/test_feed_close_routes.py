"""v170 close routes: every route that emits a feed ``closed`` event renders
the trade record's settled realized_pnl_amount (spec §1 / A2).

Only plan_manager closes emit a feed close, and each settles the linked trade
(close_plan_trade -> TradeLog._settle_account_balance) before the event
exists. One test per emitting route, the _on_event fallback, and every
unsettled case, which must print R only. Reversal (close_trade_reversed),
manual close, backfill_exit_price, update_open_trades,
close_if_live_price_hit and check_near_tp_timeout settle but never emit a
feed message (the last three skip plan-linked trades), so they get no render
test here.

Every poll runs on a Saturday clock: with no live tape a stop breach fills at
the observed print (plan_manager._continuous stays off), so each route's
per-share P&L is fixed.
"""
import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from swingbot import config
from swingbot.core.market.strategy_types import COMPRESSION_SHORT
from swingbot.core.planning.plan_manager import PlanEvent, PlanManager
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.presentation import tokens
from swingbot.core.scanning import execution_embeds
from swingbot.core.tracking import performance
from swingbot.core.tracking.performance import TradeLog, settle_legs
from tests.fake_feed import FakePriceFeed
from tests.planning.test_compression_time_exit import STD_TENTH, _at, _auction, _short
from tests.planning.test_plan_manager_pending import _pending
from tests.store_seed import seed_store

SATURDAY = dt.datetime(2026, 10, 17, 12, 0, tzinfo=ZoneInfo("America/New_York"))
PNL = tokens.FEED_SYMBOLS["pnl"]


def _seed(tmp_path, monkeypatch, balance: float) -> TradeLog:
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)
    seed_store("account", {"balance": balance, "risk_pct": 1.0, "max_position_pct": 20.0,
                           "sizing_mode": "risk_pct", "balance_history": []})
    return TradeLog()


@pytest.fixture
def trade_log(tmp_path, monkeypatch):
    return _seed(tmp_path, monkeypatch, balance=10000.0)


def _placeholder(trade_log: TradeLog) -> None:
    """scan_run's scan-time placeholder for the stop-entry plan, sized at the trigger."""
    trade_log.log_trade(
        ticker="AAPL", strategy="Fibonacci", horizon_key="4w", direction="bullish",
        confidence_level=None, confidence_label=None, entry=105.0, stop_loss=104.0,
        take_profit=110.0, plan_id="p1")


def _run(trade_log, prices, *, atr_fn=None, **plan_kw):
    """Fill the stop-entry plan at 106 and walk it through ``prices``, one poll
    per print. Returns the store and the first closed event."""
    feed = FakePriceFeed([("AAPL", p) for p in prices])
    store = PlanStore()
    store.add(_pending(stop_loss=104.0, **plan_kw))
    mgr = PlanManager(store, feed.get_price, trade_log=trade_log, atr_fn=atr_fn)
    events = []
    for _ in prices:
        events += mgr.poll(now=SATURDAY)
    closed = [e for e in events if e.transition == "closed"]
    assert closed, [e.transition for e in events]
    return store, closed[0]


def _pnl_lines(store, event) -> list[str]:
    embed = execution_embeds.build_instruction_embed(store.get("p1"), event)
    return [line for line in embed.description.splitlines() if line.startswith(PNL)]


def _assert_renders_settled(store, event, record) -> None:
    amount = record["realized_pnl_amount"]
    assert amount is not None, record
    lines = _pnl_lines(store, event)
    money = tokens.fmt_money(amount, config.CURRENCY_SYMBOL)
    assert len(lines) == 1, lines
    assert lines[0].startswith(f"{PNL} {money} · ")
    assert lines[0].endswith(tokens.COST_BASIS)


ROUTES = [
    # id, prices, plan overrides, ATR(14) for the chandelier, close reason, P&L per record share
    ("pre-TP1 stop", [106, 103], {}, None, "loss", -3.0),
    ("break-even scratch", [106, 108.5, 105], {}, None, "scratch", -1.0),
    ("runner trail", [106, 116, 140, 118], {"tp2": None}, 4.0, "tp1_runner_trail", 11.0),
    ("runner TP2", [106, 111, 121], {"tp2": 120.0}, None, "tp1_runner_tp2", 10.0),
    ("runner floor", [106, 111, 106.5, 105], {"tp2": 120.0}, None, "tp1_runner_be", 2.75),
]


@pytest.mark.parametrize("prices,plan_kw,atr,reason,per_share",
                         [route[1:] for route in ROUTES], ids=[route[0] for route in ROUTES])
def test_every_persist_terminal_route_renders_the_records_settled_dollars(
        trade_log, prices, plan_kw, atr, reason, per_share):
    _placeholder(trade_log)
    atr_fn = (lambda ticker: atr) if atr is not None else None
    store, event = _run(trade_log, prices, atr_fn=atr_fn, **plan_kw)
    assert event.detail["reason"] == reason
    record = trade_log.trade_for_plan("p1")
    assert record["realized_pnl_amount"] == settle_legs(record)
    assert record["realized_pnl_amount"] == pytest.approx(
        round(record["shares"] * per_share, 2), abs=0.01)
    _assert_renders_settled(store, event, record)


def test_the_time_exit_route_renders_the_records_settled_dollars(trade_log):
    trade_log.log_trade(
        ticker="AAPL", strategy=COMPRESSION_SHORT, horizon_key="2w", direction="bearish",
        confidence_level=None, confidence_label=None, entry=100.0, stop_loss=101.0,
        take_profit=95.0, plan_id="p1")
    store = PlanStore()
    store.add(_short())
    mgr = PlanManager(store, FakePriceFeed([("AAPL", 99.5)]).get_price,
                      auction_close_fn=_auction(98.0), trade_log=trade_log)
    mgr.poll(now=_at(STD_TENTH, 15, 40))
    closed = [e for e in mgr.poll(now=_at(STD_TENTH, 16, 0, 20)) if e.transition == "closed"]
    assert [e.detail["reason"] for e in closed] == ["time_exit"]
    record = trade_log.trade_for_plan("p1")
    assert record["realized_pnl_amount"] == pytest.approx(
        round(record["shares"] * 2.0, 2), abs=0.01)           # short 100 -> 98
    _assert_renders_settled(store, closed[0], record)


def test_the_on_event_fallback_settles_before_the_close_renders(trade_log):
    """_terminal_persisted False: _on_event closes the trade itself
    (close_plan_trade with a synthesized fraction=1.0 leg) before notify."""
    _placeholder(trade_log)
    store = PlanStore()
    store.add(_pending(stop_loss=104.0))
    mgr = PlanManager(store, FakePriceFeed([("AAPL", 106.0)]).get_price, trade_log=trade_log)
    mgr.poll(now=SATURDAY)                                      # filled at 106
    event = PlanEvent("p1", "closed", {"reason": "loss", "exit_price": 103.0,
                                       "session": "regular", "_terminal_persisted": False})
    mgr._on_event(store.get("p1"), event)
    record = trade_log.trade_for_plan("p1")
    assert record["status"] == "loss"
    assert record["realized_pnl_amount"] == pytest.approx(
        round(record["shares"] * -3.0, 2), abs=0.01)
    money = tokens.fmt_money(record["realized_pnl_amount"], config.CURRENCY_SYMBOL)
    assert _pnl_lines(store, event) == [f"{PNL} {money} · −1.5R {tokens.COST_BASIS}"]


# --- unsettled closes: R only, never an estimate -----------------------------

R_ONLY = f"{PNL} −1.5R {tokens.COST_BASIS}"          # fill 106, stop 104, exit 103


def test_a_trade_with_no_share_snapshot_closes_with_r_only(tmp_path, monkeypatch):
    """Balance 0 at open: the record never gets shares, so
    _settle_account_balance (and settle_legs) settle nothing."""
    trade_log = _seed(tmp_path, monkeypatch, balance=0.0)
    _placeholder(trade_log)
    store, event = _run(trade_log, [106, 103])
    record = trade_log.trade_for_plan("p1")
    assert not record["shares"]
    assert record["realized_pnl_amount"] is None
    assert _pnl_lines(store, event) == [R_ONLY]


def test_a_failed_balance_update_closes_with_r_only(trade_log, monkeypatch):
    def refuse(*_args, **_kwargs):
        raise RuntimeError("account store down")

    monkeypatch.setattr(performance.account_module, "apply_realized_pnl", refuse)
    _placeholder(trade_log)
    store, event = _run(trade_log, [106, 103])
    record = trade_log.trade_for_plan("p1")
    assert record["status"] == "loss" and record["shares"]
    assert record["realized_pnl_amount"] is None
    assert _pnl_lines(store, event) == [R_ONLY]


def test_a_plan_with_no_linked_trade_closes_with_r_only(tmp_path, monkeypatch):
    """A plan the bot never logged (no trade log wired): no record, no $ at all."""
    _seed(tmp_path, monkeypatch, balance=10000.0)
    store = PlanStore()
    store.add(_pending(stop_loss=104.0))
    feed = FakePriceFeed([("AAPL", p) for p in (106, 103)])
    mgr = PlanManager(store, feed.get_price)
    events = [e for _ in range(2) for e in mgr.poll(now=SATURDAY)]
    closed = [e for e in events if e.transition == "closed"]
    assert TradeLog().trade_for_plan("p1") is None
    assert _pnl_lines(store, closed[0]) == [R_ONLY]
