"""v171 D5: the rebuild price order and the one rebuild entry point."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from swingbot import config
from swingbot.core.marketdata.shared.kinds import QuoteDetail
from swingbot.core.planning import rebuild
from swingbot.core.planning.rebuild import (RebuildPrice, choose_rebuild_price, quote_record,
                                            rebuild_before_post, session_label, stamp_quote)
from tests.planning.test_plan_engine_model import _plan

ET = ZoneInfo("America/New_York")
REG = datetime(2026, 10, 15, 11, 0, tzinfo=ET).astimezone(timezone.utc)   # Thursday, in session
PRE = datetime(2026, 10, 15, 8, 0, tzinfo=ET).astimezone(timezone.utc)


@pytest.fixture(autouse=True)
def _limit(monkeypatch):
    monkeypatch.setattr(config, "REBUILD_PRICE_MAX_AGE_S", 60)


def _ago(now, s):
    return now - timedelta(seconds=s)


def _q(now=REG, price=101.0, trade_age=2.0, bid=None, ask=None, quote_age=None,
       source="alpaca-iex"):
    return QuoteDetail(symbol="AAPL", trade_price=price,
                       trade_at=None if trade_age is None else _ago(now, trade_age),
                       bid=bid, ask=ask,
                       quote_at=None if quote_age is None else _ago(now, quote_age),
                       source=source)


def test_live_trade_under_60s_wins():
    q = _q(trade_age=2.0, bid=100.9, ask=101.1, quote_age=1.0)
    p = choose_rebuild_price(q, 100.0, REG)
    assert (p.price, p.kind, p.age_s, p.confirmed, p.session) == (101.0, "trade", 2.0, True, "regular")
    assert p.quote_at == q.trade_at.isoformat() and p.fetched_at is None


def test_stale_trade_falls_to_a_fresh_mid():
    q = _q(trade_age=90.0, bid=100.0, ask=100.4, quote_age=3.0)
    p = choose_rebuild_price(q, 99.0, REG)
    assert (p.price, p.kind, p.age_s, p.confirmed) == (100.2, "mid", 3.0, True)
    assert p.quote_at == q.quote_at.isoformat()


def test_iex_stale_in_session_uses_the_mid_before_the_yfinance_bar():
    """Router: stale IEX trade -> price from yfinance, bid/ask still IEX."""
    q = _q(price=101.5, trade_age=20.0, bid=101.0, ask=101.2, quote_age=4.0, source="yfinance-1m")
    assert choose_rebuild_price(q, 99.0, REG).kind == "mid"


def test_yfinance_minute_bar_under_60s_when_no_fresh_mid():
    q = _q(price=101.5, trade_age=20.0, bid=101.0, ask=101.2, quote_age=120.0, source="yfinance-1m")
    p = choose_rebuild_price(q, 99.0, REG)
    assert (p.price, p.kind, p.age_s, p.confirmed) == (101.5, "yf-1m", 20.0, True)


def test_old_yfinance_bar_keeps_the_scan_price_unconfirmed():
    q = _q(price=101.5, trade_age=90.0, source="yfinance-1m")
    p = choose_rebuild_price(q, 99.0, REG)
    assert (p.price, p.kind, p.age_s, p.quote_at, p.confirmed) == (99.0, "scan", None, None, False)


def test_pre_market_with_yesterdays_close_and_an_old_quote_is_not_confirmed():
    """Review Focus 5: last IEX trade is yesterday's close, quote 5 min old."""
    q = _q(now=PRE, trade_age=15 * 3600, bid=100.0, ask=100.2, quote_age=300.0)
    p = choose_rebuild_price(q, 99.5, PRE)
    assert (p.price, p.kind, p.confirmed, p.session) == (99.5, "scan", False, "pre-market")


def test_exactly_60s_is_too_old():
    assert choose_rebuild_price(_q(trade_age=60.0), 99.0, REG).kind == "scan"


def test_a_print_stamped_in_the_future_has_age_zero():
    p = choose_rebuild_price(_q(trade_age=-0.4), 99.0, REG)
    assert (p.kind, p.age_s) == ("trade", 0.0)


def test_crossed_or_one_sided_quote_gives_no_mid():
    assert choose_rebuild_price(_q(price=None, trade_age=None, bid=101.0, ask=100.0,
                                   quote_age=1.0), 99.0, REG).kind == "scan"
    assert choose_rebuild_price(_q(price=None, trade_age=None, bid=None, ask=100.0,
                                   quote_age=1.0), 99.0, REG).kind == "scan"


def test_no_quote_or_no_timestamps_keeps_the_scan_price():
    assert choose_rebuild_price(None, 99.0, REG).kind == "scan"
    legacy = _q(trade_age=None, source="legacy")
    assert choose_rebuild_price(legacy, 99.0, REG).kind == "scan"


def test_spot_price_counts_as_a_trade():
    assert choose_rebuild_price(_q(trade_age=5.0, source="spot"), 99.0, REG).kind == "trade"


def test_max_age_override():
    assert choose_rebuild_price(_q(trade_age=10.0), 99.0, REG, max_age_s=5).kind == "scan"


@pytest.mark.parametrize("when, label", [
    (datetime(2026, 10, 15, 11, 0, tzinfo=ET), "regular"),
    (datetime(2026, 10, 15, 8, 0, tzinfo=ET), "pre-market"),
    (datetime(2026, 10, 15, 17, 0, tzinfo=ET), "after-hours"),
    (datetime(2026, 10, 15, 2, 0, tzinfo=ET), "closed"),
    (datetime(2026, 10, 17, 11, 0, tzinfo=ET), "closed"),          # Saturday
])
def test_session_label(when, label):
    assert session_label(when) == label


def _price(kind="trade", price=101.0, confirmed=True, session="regular"):
    return RebuildPrice(price=price, kind=kind, age_s=2.0 if confirmed else None,
                        quote_at=REG.isoformat() if confirmed else None,
                        fetched_at=None, confirmed=confirmed, session=session)


def _item(plan_v2="old-v2"):
    old = SimpleNamespace(entry=100.0, direction="bullish")
    return SimpleNamespace(result=SimpleNamespace(ticker="AAPL", close=100.0, scenario=old),
                           plan=old, plan_v2=plan_v2, plan_v2_rejected=None,
                           plan_v2_rejected_plan=None, plan_v2_rejected_margin=None)


class _Calls:
    def __init__(self, scenario, build=True, reject=None):
        self.scenario, self.build, self.reject = scenario, build, reject
        self.rescenario_prices, self.attached = [], []

    def rescenario(self, price):
        self.rescenario_prices.append(price)
        return self.scenario

    def attach_to(self, item):
        def attach(scenario):
            assert item.plan is scenario and item.plan_v2 is None   # cleared before attach
            self.attached.append(scenario)
            if self.reject:
                item.plan_v2_rejected = self.reject
            elif self.build:
                item.plan_v2 = _plan(trigger_price=scenario.entry)
        return attach


def _run(item, calls, price):
    return rebuild_before_post(item, price, rescenario=calls.rescenario,
                               attach=calls.attach_to(item))


def test_a_confirmed_price_rebuilds_and_stamps_the_new_plan(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    item, new = _item(), SimpleNamespace(entry=101.0, direction="bullish")
    calls = _Calls(new)
    out = _run(item, calls, _price())
    assert (out.kept, out.reason) == (True, None)
    assert calls.rescenario_prices == [101.0] and calls.attached == [new]
    assert item.plan is new and item.result.scenario is new and item.result.close == 101.0
    assert item.plan_v2.trigger_price == 101.0
    assert (item.plan_v2.quote_kind, item.plan_v2.price_confirmed,
            item.plan_v2.quote_session, item.plan_v2.quote_at) == ("trade", True, "regular",
                                                                   REG.isoformat())
    assert item.plan_v2.quote_age_s is None          # set at persist time (V171-20)


def test_no_scenario_at_the_new_price_drops_the_plan(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    item = _item()
    calls = _Calls(None)
    out = _run(item, calls, _price())
    assert (out.kept, out.reason) == (False, "rebuild:no_scenario")
    assert calls.attached == []


def test_a_gate_rejection_at_the_new_price_drops_the_plan(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    item = _item()
    out = _run(item, _Calls(SimpleNamespace(entry=101.0), reject="risk_cap"), _price())
    assert (out.kept, out.reason) == (False, "rebuild:risk_cap")


def test_a_builder_failure_in_on_mode_never_posts_legacy_numbers(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    out = _run(_item(), _Calls(SimpleNamespace(entry=101.0), build=False), _price())
    assert (out.kept, out.reason) == (False, "rebuild:no_plan")


def test_legacy_mode_keeps_and_stamps_the_scenario(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "off")
    item, new = _item(plan_v2=None), SimpleNamespace(entry=101.0, direction="bullish")
    out = _run(item, _Calls(new, build=False), _price(kind="mid"))
    assert out.kept and item.plan is new
    assert (new.quote_kind, new.price_confirmed) == ("mid", True)


def test_an_unconfirmed_price_never_rebuilds(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    v2 = _plan()
    item = _item(plan_v2=v2)
    old = item.plan
    calls = _Calls(SimpleNamespace(entry=999.0))
    out = _run(item, calls, _price(kind="scan", price=100.0, confirmed=False, session="pre-market"))
    assert (out.kept, out.reason) == (True, None)
    assert calls.rescenario_prices == [] and calls.attached == []
    assert item.plan is old and item.plan_v2 is v2 and item.result.close == 100.0
    assert (v2.quote_kind, v2.price_confirmed, v2.quote_session, v2.quote_at) == (
        "scan", False, "pre-market", None)


def test_stamp_quote_and_quote_record():
    plan, price = _plan(), _price(kind="mid")
    stamp_quote(plan, price, 1.7)
    assert (plan.quote_at, plan.quote_kind, plan.quote_age_s, plan.quote_session,
            plan.price_confirmed) == (REG.isoformat(), "mid", 1.7, "regular", True)
    assert quote_record(price, 1.7) == {"at": REG.isoformat(), "kind": "mid", "age_s": 1.7,
                                        "session": "regular", "confirmed": True}


def test_rebuild_imports_nothing_from_scanning():
    import inspect
    assert "swingbot.core.scanning" not in inspect.getsource(rebuild)
