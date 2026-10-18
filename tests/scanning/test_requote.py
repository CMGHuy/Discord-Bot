"""v171 D5: one batched re-quote, a per-symbol re-quote once, the 5 s clock."""
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.marketdata.shared.kinds import Asker, QuoteDetail
from swingbot.core.planning.rebuild import RebuildOutcome
from swingbot.core.scanning import requote as requote_mod
from swingbot.core.scanning.requote import Requote

NOW = datetime(2026, 10, 15, 15, 0, tzinfo=timezone.utc)      # 11:00 ET, in session


class Clock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t


def _item(ticker, ok=True, scan_price=100.0, horizon="4w"):
    return SimpleNamespace(result=SimpleNamespace(ticker=ticker, close=scan_price,
                                                  horizon_key=horizon, trend="bullish"),
                           all_requirements_met=ok, scan_price=scan_price)


def _quote(ticker, price=101.0, age=1.0):
    return QuoteDetail(symbol=ticker, price=price, trade_at=NOW - timedelta(seconds=age),
                       bid=None, ask=None, quote_at=None, source="alpaca-iex")


class Quotes:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def __call__(self, tickers):
        self.calls.append(list(tickers))
        if self.fail:
            raise TimeoutError("alpaca")
        return {t: _quote(t) for t in tickers}


def _keep(seen):
    def rebuild(item, price):
        seen.append((item.result.ticker, price))
        return RebuildOutcome(True, None, price)
    return rebuild


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setattr(config, "PLAN_REBUILD_ENABLED", True)
    monkeypatch.setattr(config, "QUOTE_MAX_AGE_REQUOTE_S", 5)
    monkeypatch.setattr(config, "REBUILD_PRICE_MAX_AGE_S", 60)


def test_flag_off_yields_everything_untouched_with_no_fetch(monkeypatch):
    monkeypatch.setattr(config, "PLAN_REBUILD_ENABLED", False)
    items, quotes, seen = [_item("AAPL"), _item("MSFT", ok=False)], Quotes(), []
    rq = Requote(items, quote_fn=quotes)
    assert list(rq.iter_fresh(items, rebuild=_keep(seen))) == items
    assert quotes.calls == [] and seen == []
    assert rq.age_at_persist("AAPL") is None and rq.price_for("AAPL") is None


def test_one_batched_fetch_for_the_alerting_symbols_only(on):
    items = [_item("AAPL"), _item("MSFT", ok=False), _item("NVDA"), _item("AAPL", horizon="2w")]
    quotes, seen = Quotes(), []
    rq = Requote(items, quote_fn=quotes, clock=Clock(), now_fn=lambda: NOW)
    out = list(rq.iter_fresh(items, rebuild=_keep(seen)))
    assert out == items                               # the unmet item passes through untouched
    assert quotes.calls == [["AAPL", "NVDA"]]
    assert [t for t, _ in seen] == ["AAPL", "NVDA", "AAPL"]
    assert seen[0][1].kind == "trade" and seen[0][1].price == 101.0
    assert seen[0][1].fetched_at == 1000.0


def test_a_symbol_whose_quote_aged_past_5s_is_requoted_once(on):
    items = [_item("AAPL"), _item("NVDA"), _item("NVDA", horizon="2w")]
    clock, quotes, seen = Clock(), Quotes(), []
    rq = Requote(items, quote_fn=quotes, clock=clock, now_fn=lambda: NOW)
    it = rq.iter_fresh(items, rebuild=_keep(seen))
    next(it)
    clock.t += 6.0                                    # the first alert took 6 s
    next(it)
    clock.t += 6.0
    next(it)
    assert quotes.calls == [["AAPL", "NVDA"], ["NVDA"]]
    assert seen[1][1].fetched_at == 1006.0


def test_age_at_persist_freezes_and_counts_a_miss(on):
    items = [_item("AAPL"), _item("NVDA")]
    clock = Clock()
    rq = Requote(items, quote_fn=Quotes(), clock=clock, now_fn=lambda: NOW)
    it = rq.iter_fresh(items, rebuild=_keep([]))
    next(it)
    clock.t += 1.25
    assert rq.age_at_persist("AAPL") == 1.25
    clock.t += 10.0
    assert rq.age_at_persist("AAPL") == 1.25          # frozen at the first (persist) call
    next(it)                                          # NVDA aged 11.25 s: re-quoted at 1011.25
    clock.t += 6.0                                    # ...and persisted 6 s after that re-quote
    assert rq.age_at_persist("NVDA") == 6.0 and rq.misses == 1
    assert rq.stats() == {"kept": 2, "dropped": 0, "misses": 1}


def test_a_dropped_item_is_skipped_and_logged(on, caplog):
    items = [_item("AAPL"), _item("NVDA")]
    rq = Requote(items, quote_fn=Quotes(), clock=Clock(), now_fn=lambda: NOW)

    def rebuild(item, price):
        kept = item.result.ticker != "AAPL"
        return RebuildOutcome(kept, None if kept else "rebuild:risk_cap", price)

    with caplog.at_level(logging.INFO, logger=requote_mod.log.name):
        out = list(rq.iter_fresh(items, rebuild=rebuild))
    assert [i.result.ticker for i in out] == ["NVDA"]
    assert rq.stats() == {"kept": 1, "dropped": 1, "misses": 0}
    assert "AAPL (4w, bullish): not posted -- rebuild:risk_cap" in caplog.text
    assert rq.price_for("AAPL") is None and rq.price_for("NVDA").kind == "trade"


def test_a_failed_fetch_keeps_the_scan_price_unconfirmed(on):
    items = [_item("AAPL", scan_price=99.0)]
    seen = []
    rq = Requote(items, quote_fn=Quotes(fail=True), clock=Clock(), now_fn=lambda: NOW)
    assert list(rq.iter_fresh(items, rebuild=_keep(seen))) == items
    price = seen[0][1]
    assert (price.kind, price.price, price.confirmed) == ("scan", 99.0, False)
    assert price.fetched_at == 1000.0


def test_scan_price_falls_back_to_the_result_close(on):
    item = _item("AAPL")
    item.scan_price = None
    item.result.close = 98.0
    seen = []
    rq = Requote([item], quote_fn=lambda t: {}, clock=Clock(), now_fn=lambda: NOW)
    list(rq.iter_fresh([item], rebuild=_keep(seen)))
    assert seen[0][1].price == 98.0


def test_default_quote_fn_fetches_fresh_at_tier_2(monkeypatch):
    from swingbot.core.marketdata import data
    calls = []
    monkeypatch.setattr(data, "get_quote_batch",
                        lambda tickers, **kw: calls.append((list(tickers), kw)) or {})
    requote_mod._default_quote_fn(["AAPL"])
    assert calls == [(["AAPL"], {"asker": Asker.REQUOTE, "max_age_s": 0.0})]
