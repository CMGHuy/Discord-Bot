"""v171 D2/D8: the plan manager reads the monitor's shared quote and stamps exits."""
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from swingbot import config
from swingbot.core.marketdata.shared.kinds import Asker, QuoteDetail
from swingbot.core.planning import plan_manager as pm
from swingbot.core.planning.plan_manager import PlanManager, QuotePrices, quote_stamp
from swingbot.core.planning.plan_store import PlanStore
from tests.planning.test_plan_manager_active import _active

ET = ZoneInfo("America/New_York")
REG = datetime(2026, 10, 15, 11, 0, tzinfo=ET)          # Thursday, regular session


def _q(price=94.5, age=2.0, source="alpaca-iex", now=REG):
    at = now.astimezone(timezone.utc) - timedelta(seconds=age)
    return QuoteDetail(symbol="AAPL", price=price, trade_at=at if price else None,
                       bid=None, ask=None, quote_at=None, source=source)


def test_quote_stamp_live_trade_in_session(monkeypatch):
    monkeypatch.setattr(config, "REBUILD_PRICE_MAX_AGE_S", 60)
    q = _q(age=2.0)
    assert quote_stamp(q, REG) == {"at": q.trade_at.isoformat(), "kind": "trade", "age_s": 2.0,
                                   "session": "regular", "confirmed": True}


def test_quote_stamp_old_yfinance_minute_bar_is_not_confirmed(monkeypatch):
    monkeypatch.setattr(config, "REBUILD_PRICE_MAX_AGE_S", 60)
    s = quote_stamp(_q(age=90.0, source="yfinance-1m"), REG)
    assert (s["kind"], s["age_s"], s["confirmed"]) == ("yf-1m", 90.0, False)


@pytest.mark.parametrize("when, label", [
    (datetime(2026, 10, 15, 8, 0, tzinfo=ET), "pre-market"),
    (datetime(2026, 10, 15, 17, 0, tzinfo=ET), "after-hours"),
    (datetime(2026, 10, 15, 2, 0, tzinfo=ET), "closed"),
    (datetime(2026, 10, 17, 11, 0, tzinfo=ET), "closed"),          # Saturday
])
def test_quote_stamp_session_labels(when, label):
    assert quote_stamp(_q(now=when), when)["session"] == label


def test_quote_stamp_without_a_quote_or_price_is_none():
    assert quote_stamp(None, REG) is None
    assert quote_stamp(_q(price=None), REG) is None


def test_price_batch_fn_off_mode_is_unchanged(monkeypatch):
    from swingbot.core.marketdata.data import get_current_price_batch
    from swingbot.core.scanning import fetch
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "off")
    seen = []
    monkeypatch.setattr(fetch, "_run_bounded",
                        lambda fn, args, timeout, label: seen.append(fn) or {"AAPL": 1.0})
    out = pm._price_batch_fn(["AAPL"])
    assert out == {"AAPL": 1.0} and not isinstance(out, QuotePrices)
    assert seen[0].func is get_current_price_batch and seen[0].keywords == {"allow_stale": False}


def test_price_batch_fn_on_mode_returns_prices_with_details(monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    details = {"AAPL": _q(190.0), "MSFT": _q(None)}
    monkeypatch.setattr(pm, "monitor_quotes", lambda tickers: dict(details))
    out = pm._price_batch_fn(["AAPL", "MSFT"])
    assert out == {"AAPL": 190.0} and isinstance(out, QuotePrices)
    assert out.details == details


def test_monitor_quotes_runs_the_worker_and_merges_its_counts(monkeypatch):
    from swingbot.core.marketdata import data
    from swingbot.core.marketdata.shared import counters
    from swingbot.core.scanning import fetch
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    rows = [("2026-10-15T15:00:00+00:00", "alpaca", "quote", "STOP_MONITOR", "fetched", 1)]
    merged, asked = [], []
    q = _q(190.0)
    monkeypatch.setattr(fetch, "_run_bounded", lambda fn, args, timeout, label: fn(*args))
    monkeypatch.setattr(data, "get_quote_batch",
                        lambda t, *, asker, fresh_only=False, max_age_s=None:
                        asked.append((asker, fresh_only)) or {"AAPL": q})
    monkeypatch.setattr(counters, "snapshot_and_clear", lambda: list(rows))
    monkeypatch.setattr(counters, "merge", merged.extend)
    assert pm.monitor_quotes(["AAPL"]) == {"AAPL": q}
    assert asked == [(Asker.STOP_MONITOR, True)] and merged == rows


def _count_mode_monitor(monkeypatch, order, flush):
    from swingbot.core.marketdata import data
    from swingbot.core.marketdata.shared import counters
    from swingbot.core.scanning import fetch
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "count")
    q = _q(190.0)
    monkeypatch.setattr(fetch, "_run_bounded", lambda fn, args, timeout, label: fn(*args))
    monkeypatch.setattr(data, "get_quote_batch",
                        lambda t, *, asker, fresh_only=False, max_age_s=None: {"AAPL": q})
    monkeypatch.setattr(counters, "snapshot_and_clear", lambda: [("h", "p", "k", "a", "o", 1)])
    monkeypatch.setattr(counters, "merge", lambda rows: order.append("merge"))
    monkeypatch.setattr(counters, "flush", flush)
    return q


def test_monitor_quotes_flushes_the_merged_counts(monkeypatch):
    order = []
    q = _count_mode_monitor(monkeypatch, order, lambda **k: order.append("flush") or 0)
    assert pm.monitor_quotes(["AAPL"]) == {"AAPL": q}
    assert order == ["merge", "flush"]


def test_monitor_quotes_survives_a_raising_flush(monkeypatch):
    def boom(**k):
        raise RuntimeError("db down")
    q = _count_mode_monitor(monkeypatch, [], boom)
    assert pm.monitor_quotes(["AAPL"]) == {"AAPL": q}


def test_monitor_quotes_timeout_is_empty(monkeypatch):
    from swingbot.core.scanning import fetch
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    monkeypatch.setattr(fetch, "_run_bounded", lambda *a, **k: None)
    assert pm.monitor_quotes(["AAPL"]) == {}


def _mgr(batch):
    store = PlanStore()
    store.add(_active())
    return PlanManager(store, lambda t: pytest.fail("serial price seam"), price_batch_fn=batch)


def test_exit_event_carries_the_quote_stamp(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(config, "REBUILD_PRICE_MAX_AGE_S", 60)
    q = _q(94.5, age=2.0)
    mgr = _mgr(lambda tickers: QuotePrices({"AAPL": 94.5}, {"AAPL": q}))
    with caplog.at_level(logging.INFO, logger=pm.log.name):
        events = mgr.poll(now=REG)
    assert [e.transition for e in events] == ["closed"]
    assert events[0].detail["quote"] == quote_stamp(q, REG)
    assert any("quote=trade 2.0s" in r.getMessage() for r in caplog.records)


def test_non_exit_event_gets_no_stamp(tmp_path):
    mgr = _mgr(lambda tickers: QuotePrices({"AAPL": 105.0}, {"AAPL": _q(105.0)}))
    events = mgr.poll(now=REG)
    assert [e.transition for e in events] == ["be_moved"] and "quote" not in events[0].detail


def test_plain_dict_prices_add_no_stamp(tmp_path):
    events = _mgr(lambda tickers: {"AAPL": 94.5}).poll(now=REG)
    assert events[0].transition == "closed" and "quote" not in events[0].detail
