# tests/scanning/test_outlook_run.py
"""v144: the 23:30 outlook run -- closed bars only, live gates, three routes."""
import datetime as dt
from types import SimpleNamespace

import discord
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.scanning import outlook_run as orun
from swingbot.core.scanning import qualify, short_run
from swingbot.core.scanning.outlook_types import OutlookResult
from swingbot.core.tracking.performance import TradeLog
from tests.planning.test_plan_engine_model import _plan

FRIDAY, SUNDAY, MONDAY = dt.date(2026, 10, 9), dt.date(2026, 10, 11), dt.date(2026, 10, 12)
NOW = dt.datetime(2026, 10, 11, 21, 30, tzinfo=dt.timezone.utc)      # Sunday 23:30 Berlin


def _frame(last):
    days = pd.bdate_range(end=pd.Timestamp(last), periods=5)
    return pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0, "Volume": 1.0}, index=days)


# --- closed bars ----------------------------------------------------------------

def test_closed_frames_trusts_only_a_cache_written_after_the_close(monkeypatch):
    windows = {}

    def is_stale(symbol, timeframe, max_age_hours):
        windows[symbol] = max_age_hours
        return symbol != "WARM"

    monkeypatch.setattr(orun.data_refresh, "is_stale", is_stale)
    monkeypatch.setattr(orun.data_store, "load_normalized", lambda s, tf: _frame(FRIDAY))
    monkeypatch.setattr(orun.fetch, "_fetch_cold_frames",
                        lambda cold, progress: [(s, _frame(FRIDAY if s == "COLD" else FRIDAY - dt.timedelta(days=1)))
                                                for s in cold])
    frames = orun.closed_frames(["WARM", "COLD", "OLD", "WARM"], FRIDAY, NOW)
    assert sorted(frames) == ["COLD", "WARM"]          # OLD's last bar is Thursday: dropped
    assert windows["WARM"] == pytest.approx(49.5)      # Fri 16:00 ET -> Sun 21:30 UTC


def test_before_the_close_the_cache_is_never_read(monkeypatch):
    monkeypatch.setattr(orun.data_refresh, "is_stale", lambda *a, **k: pytest.fail("cache consulted"))
    assert orun._cached_after_close("AAPL", -1.0) is None


# --- the short-circuits ----------------------------------------------------------

def test_no_session_tomorrow_scans_nothing(monkeypatch):
    monkeypatch.setattr(orun, "closed_frames", lambda *a: pytest.fail("scanned"))
    result = orun.run_outlook(dt.date(2027, 3, 25), now=NOW)
    assert result.target is None and result.unavailable is None and result.plans == []


def test_the_v2_engine_must_be_on(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "shadow")
    monkeypatch.setattr(orun, "closed_frames", lambda *a: pytest.fail("scanned"))
    result = orun.run_outlook(SUNDAY, now=NOW)
    assert (result.target, result.bar_date) == (MONDAY, FRIDAY)
    assert result.unavailable == "PLAN_ENGINE_V2 is not 'on', so no plan can be built"


def test_a_missing_regime_bar_issues_nothing(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(config, "MARKET_REGIME_TICKER", "SPY")
    monkeypatch.setattr(orun.scan_run, "_scan_tickers", lambda: ["AAPL"])
    monkeypatch.setattr(orun, "closed_frames", lambda symbols, bar_date, now: {"AAPL": _frame(FRIDAY)})
    result = orun.run_outlook(SUNDAY, now=NOW)
    assert result.unavailable == "no closed SPY daily bar for 2026-10-09"
    assert result.plans == [] and result.alerts == []


# --- gates and routes ------------------------------------------------------------

def _item(ticker, *, met=True, entry_type="stop_entry", rejected=None, score=50):
    scenario = SimpleNamespace(entry=102.0, stop_loss=100.5, take_profit=106.0, stop_distance_pct=2.6,
                               target2_price=None)
    plan_v2 = None if entry_type is None else SimpleNamespace(
        entry_type=entry_type, direction="bullish", strategy="Break & Retest",
        trigger_price=102.0, stop_loss=100.5, tp1=106.0)
    return SimpleNamespace(
        all_requirements_met=met, plan_v2_rejected=rejected, plan=scenario, plan_v2=plan_v2,
        conf=SimpleNamespace(score=score),
        result=SimpleNamespace(ticker=ticker, trend="bullish", strategy="Break & Retest", horizon_key="4w"))


def test_verdicts_keep_accepted_items_and_word_plan_stage_rejections(monkeypatch):
    def verdict(candidate, item, context):
        if item.plan_v2_rejected:
            return qualify.Rejected(item, "plan", item.plan_v2_rejected)
        if item.result.ticker == "RS":
            return qualify.Rejected(item, "rs", "rs_blocked")
        return qualify.Accepted(item)

    monkeypatch.setattr(orun.qualify, "qualify_short_item", verdict)
    items = [_item("OK"), _item("CAP", rejected="risk_cap"), _item("RS"), _item("UNMET", met=False)]
    accepted, near = orun._verdicts(items, context=None)
    assert [item.result.ticker for item in accepted] == ["OK"]
    assert [(line.ticker, line.reason) for line in near] == [("CAP", "risk_cap (stop 2.6% from entry)")]


def test_route_issues_stop_entries_lists_market_entries_and_skips_open_tickers(monkeypatch):
    issued = []
    monkeypatch.setattr(orun, "_issue", lambda item, plan, result, frames, spy: issued.append(item.result.ticker))
    result = OutlookResult(run_date=SUNDAY, target=MONDAY)
    ordered = [_item("AAPL"), _item("AAPL"), _item("MSFT", entry_type="market"),
               _item("TSLA"), _item("NONE", entry_type=None)]
    orun._route(ordered, {"TSLA"}, result, frames={}, spy=None)
    assert issued == ["AAPL"]                           # once per ticker
    assert [line.ticker for line in result.watch] == ["MSFT"]
    assert result.skipped == ["AAPL", "TSLA"]


def test_issue_stamps_the_plan_and_logs_an_outlook_trade(monkeypatch):
    logged = {}
    monkeypatch.setattr(orun, "build_explanation", lambda *a, **k: "why")
    monkeypatch.setattr(orun.scan_run, "_earnings_in_window", lambda *a: None)
    monkeypatch.setattr(orun, "plan_numbers_for_display", lambda plan, legacy: dict(legacy))
    monkeypatch.setattr(orun.short_run, "_fit_trendline", lambda *a: None)
    monkeypatch.setattr(orun.short_run, "_log_trade",
                        lambda item, nums, explanation, fit, alerts, origin=None: logged.update(origin=origin) or "T1")
    monkeypatch.setattr(orun, "_card", lambda *a: ("card",))
    monkeypatch.setattr(orun, "_risk_dollars", lambda plan: 120.0)
    item = _item("AAPL")
    item.target_confluence = item.stop_confluence = None
    item.combined_from = []
    plan = _plan(entry_type="stop_entry", trigger_price=102.0, stop_loss=100.5, tp1=106.0)
    result = OutlookResult(run_date=SUNDAY, target=MONDAY)
    orun._issue(item, plan, result, frames={}, spy=None)
    assert (plan.origin, plan.valid_session) == ("next_session", "2026-10-12")
    assert logged["origin"] == "next_session" and item.paper_logged is True
    assert result.alerts == [("card",)]
    assert result.plans[0].risk_dollars == 120.0 and result.plans[0].entry == 102.0


def test_the_card_carries_the_badge(monkeypatch):
    monkeypatch.setattr(orun.short_run, "_render_chart", lambda *a: (None, None))
    monkeypatch.setattr(orun, "build_embed", lambda *a, **k: discord.Embed(description="body"))
    monkeypatch.setattr(orun, "build_simple_alert", lambda item: None)
    monkeypatch.setattr(orun, "_hourly", lambda ticker: None)
    item = _item("AAPL")
    item.conf.level, item.htf_info = 3, None
    plan = _plan(entry_type="stop_entry")
    embed, chart_path, card_plan, simple = orun._card(item, plan, MONDAY, "why", {}, None, {}, None, "T1", None)
    assert embed.description.startswith("🌙 **Outlook · valid Monday 2026-10-12 only**")
    assert card_plan is plan and chart_path is None


def test_open_tickers_count_only_the_outlook_lane():
    PlanStore().add(_plan(plan_id="o1", ticker="AAPL", origin="next_session", valid_session="2026-10-12"))
    PlanStore().add(_plan(plan_id="r1", ticker="MSFT"))
    TradeLog().log_trade(ticker="NVDA", strategy="MACD", horizon_key="3m", direction="bullish",
                         confidence_level=3, confidence_label="Medium", entry=100.0, stop_loss=98.0,
                         take_profit=105.0, origin="next_session")
    TradeLog().log_trade(ticker="AMD", strategy="MACD", horizon_key="3m", direction="bullish",
                         confidence_level=3, confidence_label="Medium", entry=100.0, stop_loss=98.0,
                         take_profit=105.0)
    assert orun.outlook_open_tickers() == {"AAPL", "NVDA"}


def test_log_trade_passes_the_origin_through(monkeypatch):
    seen = {}
    monkeypatch.setattr(short_run.scan_run, "_logged_plan_fields", lambda *a: ([], 2.0))
    monkeypatch.setattr(short_run.scan_run, "_persist_plan_v2", lambda plan, alerts: None)
    monkeypatch.setattr(short_run.trade_log, "log_trade", lambda **kw: seen.update(kw) or "T1")
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    plan_v2 = _plan(entry_type="stop_entry")
    item = SimpleNamespace(
        result=SimpleNamespace(ticker="AAPL", strategy="RSI", horizon_key="4w", trend="bullish"),
        plan=SimpleNamespace(stop_sources=[], target2_sources=[]), plan_v2=plan_v2, level_map=None,
        conf=SimpleNamespace(level=3, label="Medium", score=60, breakdown={}), combined_from=[])
    nums = {"entry": 102.0, "stop_loss": 100.5, "take_profit": 106.0, "target2": None}
    assert short_run._log_trade(item, nums, "why", None, [], origin="next_session") == "T1"
    assert seen["origin"] == "next_session"
    short_run._log_trade(item, nums, "why", None, [])
    assert seen["origin"] is None
