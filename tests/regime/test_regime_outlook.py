"""v239 V239-11 (partner): the 23:30 outlook plans carry the regime stamp too; off stamps nothing."""
import datetime as dt

import pytest

from swingbot import config
from swingbot.core.market import bear_regime as br
from swingbot.core.scanning import analyze, outlook_run as orun, qualify, regime_scan
from tests.scanning.test_shock_plans_byte_identical import FRAME, _canon, _long_item, _long_plan

FRIDAY = dt.date(2026, 10, 9)
NOW = dt.datetime(2026, 10, 11, 21, 30, tzinfo=dt.timezone.utc)      # Sunday 23:30 Berlin
DAY = br.RegimeDay(session_date=dt.date(2026, 10, 12), last_bar_date=FRIDAY,
                   state=br.CORRECTION, stress=False)


@pytest.fixture(autouse=True)
def _gate_inputs(monkeypatch):
    monkeypatch.setattr(orun, "_sector_inputs", lambda tickers, bar, now: ({}, {}, {}))
    monkeypatch.setattr(orun, "_regimes", lambda spy: None)
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(analyze, "_build_quality_inputs", lambda *a, **k: {})
    monkeypatch.setattr(analyze, "build_confluence_plan", lambda *a, **k: _long_plan())
    monkeypatch.setattr(analyze, "primary_strategy_for", lambda scenario: "MACD")


def _no_io(monkeypatch):
    monkeypatch.setattr(regime_scan, "get_daily_data",
                        lambda *a, **k: pytest.fail("the outlook fetched under off"))
    monkeypatch.setattr(regime_scan, "market_regime_repo",
                        lambda: pytest.fail("the outlook opened the regime store under off"))


def _context():
    return orun._context({"AAPL": FRAME}, "spy", None, None, FRIDAY, NOW)


def _plan_from(context):
    item = _long_item()
    qualify._attach_plan(item, context)
    return item.plan_v2


def test_shadow_runs_the_pass_once_at_the_outlook_clock_and_stamps_the_plan(monkeypatch):
    calls = []
    monkeypatch.setattr(regime_scan, "regime_for_pass", lambda **k: calls.append(k) or DAY)
    context = _context()
    assert calls == [{"now": NOW}] and context.regime_day is DAY
    ctx = _plan_from(context).entry_context
    assert (ctx["bear_regime"], ctx["regime_action"]) == ("CORRECTION", "caution")


@pytest.mark.parametrize("mode", ["off", "bogus"])
def test_off_fetches_nothing_and_the_plan_differs_only_by_the_two_keys(monkeypatch, mode):
    monkeypatch.setattr(config, "BEAR_REGIME_MODE", mode)
    with monkeypatch.context() as m:
        _no_io(m)
        context = _context()
        assert context.regime_day is None
        off = _plan_from(context)
    monkeypatch.setattr(regime_scan, "regime_for_pass", lambda **k: DAY)
    shadow = _plan_from(_context())
    assert not {"bear_regime", "regime_action"} & set(off.entry_context)
    assert shadow.entry_context.pop("bear_regime") == "CORRECTION"
    assert shadow.entry_context.pop("regime_action") == "caution"
    assert _canon(off) == _canon(shadow)
