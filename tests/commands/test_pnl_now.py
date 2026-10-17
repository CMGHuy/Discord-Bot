"""v170 §3 / A4-A6: the 💵 P&L now reply.

render_reply is pure: every status is pinned here by exact text. reply_for
is the only function with I/O; its three seams (_load_plan, _linked_trade,
_quote) are monkeypatched, and it must never raise. No pytest-asyncio.
"""
import datetime as dt
import types

import pytest

from swingbot import config
from swingbot.commands import pnl_now
from swingbot.core.planning.account import compute_unrealized_pnl
from swingbot.core.planning.plan_types import PlanStatus
from swingbot.core.scanning import scan_run
from tests.planning.test_plan_engine_model import _plan
from tests.store_seed import seed_store

PID = "0f8fad5b-d9cb-469f-a165-70867728950e"
WED = dt.datetime(2026, 10, 7, 14, 30, tzinfo=dt.timezone.utc)   # 10:30 ET, Wednesday
SAT = dt.datetime(2026, 10, 10, 14, 30, tzinfo=dt.timezone.utc)  # Saturday
TP1_LEG = {"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"}
RUNNER_LEG = {"fraction": 0.5, "exit_price": 120.0, "r": 4.0, "reason": "tp1_runner_tp2"}


@pytest.fixture(autouse=True)
def _dollars(monkeypatch):
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")


def _long(status=PlanStatus.ACTIVE, **kw):
    base = dict(plan_id=PID, status=status, entry_type="stop_entry", trigger_price=100.0,
                entry_price=100.0, stop_loss=95.0, tp1=110.0, tp2=120.0, tp1_fraction=0.5)
    base.update(kw)
    return _plan(**base)


def _short(status=PlanStatus.ACTIVE, **kw):
    base = dict(plan_id=PID, status=status, direction="bearish", entry_type="stop_entry",
                trigger_price=100.0, entry_price=100.0, stop_loss=105.0, tp1=90.0, tp2=80.0,
                tp1_fraction=0.5)
    base.update(kw)
    return _plan(**base)


def _trade(direction="bullish", stop_loss=95.0, take_profit=110.0, **kw):
    record = {"id": "t1", "plan_id": PID, "ticker": "AAPL", "direction": direction,
              "entry": 100.0, "stop_loss": stop_loss, "take_profit": take_profit,
              "shares": 20.5, "legs": [], "status": "open", "realized_pnl_amount": None,
              "exit_price": None}
    record.update(kw)
    return record


def _quote(price, daily_close=None):
    return types.SimpleNamespace(price=price, daily_close=daily_close)


def _pnl(price, direction="bullish", stop_loss=95.0, take_profit=110.0):
    return compute_unrealized_pnl(entry=100.0, stop_loss=stop_loss, take_profit=take_profit,
                                  direction=direction, current_price=price)


def _render(plan, trade, quote=None, pnl=None, *, clock=WED, market_open=True):
    return pnl_now.render_reply(plan, trade, quote, pnl, clock=clock, market_open=market_open)


# ---------------------------------------------------------------- open plans

def test_an_active_long_shows_price_open_move_and_total_with_its_basis():
    assert _render(_long(), _trade(), _quote(104.0), _pnl(104.0)).splitlines() == [
        "AAPL long · ACTIVE",
        "last 104.00 · as of 10:30 ET",
        "open 100%: +4.0% · +$82.00 · +0.8R",
        "🧾 total +$82.00 · +0.8R (paper, gross)",
    ]


def test_an_active_long_under_water_signs_both_figures():
    lines = _render(_long(), _trade(), _quote(97.0), _pnl(97.0)).splitlines()
    assert lines[2] == "open 100%: \u22123.0% · -$61.50 · \u22120.6R"
    assert lines[3] == "🧾 total -$61.50 · \u22120.6R (paper, gross)"


def test_an_active_short_measures_the_move_the_short_way():
    trade = _trade(direction="bearish", stop_loss=105.0, take_profit=90.0)
    pnl = _pnl(96.0, direction="bearish", stop_loss=105.0, take_profit=90.0)
    assert _render(_short(), trade, _quote(96.0), pnl).splitlines() == [
        "AAPL short · ACTIVE",
        "last 96.00 · as of 10:30 ET",
        "open 100%: +4.0% · +$82.00 · +0.8R",
        "🧾 total +$82.00 · +0.8R (paper, gross)",
    ]


def test_a_partial_adds_the_banked_leg_so_open_plus_banked_is_the_total():
    plan = _long(PlanStatus.PARTIAL, legs_realized=[dict(TP1_LEG)])
    assert _render(plan, _trade(), _quote(112.0), _pnl(112.0)).splitlines() == [
        "AAPL long · PARTIAL",
        "last 112.00 · as of 10:30 ET",
        "open 50%: +12.0% · +$123.00 · +1.2R",
        "banked: +$102.50 · +1.0R (paper, gross)",
        "🧾 total +$225.50 · +2.2R (paper, gross)",
    ]


def test_with_no_linked_record_no_dollar_figure_prints():
    lines = _render(_long(), None, _quote(104.0), _pnl(104.0)).splitlines()
    assert lines[2:] == ["open 100%: +4.0% · +0.8R", "🧾 total +0.8R (paper, gross)"]
    assert "$" not in "\n".join(lines)


def test_a_record_without_shares_prints_no_dollar_figure():
    text = _render(_long(), _trade(shares=None), _quote(104.0), _pnl(104.0))
    assert "$" not in text and "+0.8R" in text


def test_market_closed_and_a_daily_close_fallback_are_both_said():
    text = _render(_long(), _trade(), _quote(104.0, dt.date(2026, 10, 9)), _pnl(104.0),
                   clock=SAT, market_open=False)
    assert text.splitlines()[1] == (
        "last 104.00 · as of 10:30 ET · daily close 2026-10-09 · market closed")


def test_a_price_that_could_not_be_fetched_says_so_and_keeps_the_banked_leg():
    plan = _long(PlanStatus.PARTIAL, legs_realized=[dict(TP1_LEG)])
    assert _render(plan, _trade(), _quote(None), None).splitlines() == [
        "AAPL long · PARTIAL", "price unavailable",
        "banked: +$102.50 · +1.0R (paper, gross)"]
    assert _render(_long(), _trade(), None, None).splitlines() == [
        "AAPL long · ACTIVE", "price unavailable"]


# ------------------------------------------------- pending, closed, cancelled

def test_a_pending_plan_shows_the_price_against_its_trigger():
    plan = _long(PlanStatus.PENDING, entry_price=None)
    assert _render(plan, _trade(), _quote(98.5), _pnl(98.5)).splitlines() == [
        "AAPL long · PENDING",
        "last 98.50 · as of 10:30 ET",
        "▶ trigger 100.00 · not filled yet",
    ]


def test_a_closed_plan_shows_the_settled_record_and_no_live_price():
    plan = _long(PlanStatus.CLOSED, legs_realized=[dict(TP1_LEG), dict(RUNNER_LEG)])
    trade = _trade(status="win", realized_pnl_amount=307.5, exit_price=120.0)
    assert _render(plan, trade).splitlines() == [
        "AAPL long · CLOSED", "🧾 +$307.50 · +3.0R (paper, gross)"]


def test_a_closed_pre_tp1_loss_reads_its_exit_from_the_record():
    plan = _long(PlanStatus.CLOSED)
    trade = _trade(status="loss", realized_pnl_amount=-102.5, exit_price=95.0)
    assert _render(plan, trade).splitlines()[1] == "🧾 -$102.50 · \u22121.0R (paper, gross)"


def test_an_unsettled_close_shows_r_only():
    plan = _long(PlanStatus.CLOSED, legs_realized=[dict(TP1_LEG), dict(RUNNER_LEG)])
    assert _render(plan, _trade(status="win")).splitlines()[1] == "🧾 +3.0R (paper, gross)"
    assert _render(plan, None).splitlines()[1] == "🧾 +3.0R (paper, gross)"


def test_a_cancelled_plan_never_filled():
    assert _render(_long(PlanStatus.CANCELLED, entry_price=None), None).splitlines() == [
        "AAPL long · CANCELLED", "never filled"]


# ------------------------------------------------------------ reply_for seams

@pytest.fixture
def seams(monkeypatch):
    """reply_for's three seams, stubbed; `quoted` records every _quote call."""
    state = {"plan": _long(), "trade": _trade(), "quoted": []}

    def quote(plan, trade):
        state["quoted"].append(plan.status)
        return _quote(104.0), _pnl(104.0)

    monkeypatch.setattr(pnl_now, "_load_plan", lambda plan_id: state["plan"])
    monkeypatch.setattr(pnl_now, "_linked_trade", lambda plan_id: state["trade"])
    monkeypatch.setattr(pnl_now, "_quote", quote)
    return state


def test_reply_for_an_open_plan_prices_it_and_stamps_the_click_time(seams):
    text = pnl_now.reply_for(PID, now=WED)
    assert text.splitlines()[1] == "last 104.00 · as of 10:30 ET"
    assert seams["quoted"] == [PlanStatus.ACTIVE]


def test_reply_for_reads_market_closed_from_the_session_clock(seams):
    assert pnl_now.reply_for(PID, now=SAT).splitlines()[1].endswith("· market closed")


def test_reply_for_a_closed_or_cancelled_plan_fetches_no_price(seams):
    for status in (PlanStatus.CLOSED, PlanStatus.CANCELLED):
        seams["plan"] = _long(status)
        pnl_now.reply_for(PID, now=WED)
    assert seams["quoted"] == []


def test_reply_for_a_pruned_plan_says_it_is_gone(seams):
    seams["plan"] = None
    assert pnl_now.reply_for(PID, now=WED) == pnl_now.GONE == (
        "This plan is not tracked (never placed, or pruned).")


def test_reply_for_never_raises(seams, monkeypatch):
    def boom(plan_id):
        raise RuntimeError("store down")
    monkeypatch.setattr(pnl_now, "_load_plan", boom)
    assert pnl_now.reply_for(PID, now=WED) == pnl_now.FAILED


def test_a_failing_price_fetch_is_price_unavailable_not_an_exception(monkeypatch):
    def boom(trade):
        raise RuntimeError("yahoo down")
    monkeypatch.setattr(scan_run, "quote_trade", boom)
    assert pnl_now._quote(_long(), _trade()) == (None, None)
    monkeypatch.setattr(pnl_now, "_load_plan", lambda plan_id: _long())
    monkeypatch.setattr(pnl_now, "_linked_trade", lambda plan_id: _trade())
    assert pnl_now.reply_for(PID, now=WED).splitlines()[1] == pnl_now.UNAVAILABLE


def test_quote_prices_the_record_or_the_plan_when_there_is_none(monkeypatch):
    seen = []
    monkeypatch.setattr(scan_run, "quote_trade",
                        lambda trade: seen.append(trade) or (_quote(1.0), None))
    record = _trade()
    pnl_now._quote(_long(), record)
    pnl_now._quote(_long(PlanStatus.PENDING, entry_price=None), None)
    assert seen[0] is record
    assert seen[1] == {"ticker": "AAPL", "direction": "bullish", "entry": 100.0,
                       "stop_loss": 95.0, "take_profit": 110.0}


# ------------------------------------------------------- the real record seam

@pytest.fixture
def tlog(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    seed_store("account", {"balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
                           "sizing_mode": "risk_pct", "balance_history": []})
    from swingbot.core.tracking.performance import TradeLog
    return TradeLog()


def test_linked_trade_reads_the_record_in_any_status(tlog):
    tlog.log_trade(ticker="AAPL", strategy="Fibonacci", horizon_key="4w", direction="bullish",
                   confidence_level=4, confidence_label="High", entry=100.0, stop_loss=95.0,
                   take_profit=110.0, plan_id=PID)
    record = pnl_now._linked_trade(PID)
    assert record["plan_id"] == PID and record["ticker"] == "AAPL"
    assert pnl_now._linked_trade("00000000-0000-0000-0000-000000000000") is None


def test_linked_trade_never_raises(monkeypatch):
    from swingbot.core.tracking import performance

    def boom(self, plan_id):
        raise RuntimeError("db down")
    monkeypatch.setattr(performance.TradeLog, "trade_for_plan", boom)
    assert pnl_now._linked_trade(PID) is None


def test_a_near_flat_open_plan_never_prints_a_signed_zero():
    for price in (99.9996, 100.0004, 100.03):
        text = _render(_long(), _trade(), _quote(price), _pnl(price))
        assert "−0.0R" not in text and "-$0.00" not in text


def test_a_flat_open_plan_prints_no_signed_zero_in_any_unit():
    sym = config.CURRENCY_SYMBOL
    for price in (99.9999, 99.97, 100.0001):
        text = _render(_long(), _trade(), _quote(price), _pnl(price))
        assert f"-{sym}0.00" not in text and "+-" not in text
        assert "−0.0R" not in text and "−0.0%" not in text
    assert "open 100%: 0.0% · " in _render(_long(), _trade(), _quote(99.97), _pnl(99.97))
