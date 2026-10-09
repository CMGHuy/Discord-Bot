# tests/scanning/test_outlook_run.py
"""v144: the 23:30 outlook run -- closed bars only, live gates, three routes."""
import datetime as dt
from types import SimpleNamespace

import discord
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import data_refresh, data_store
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

def _final(last):
    frame = _frame(last)
    frame["Close"] = 2.0
    return frame


def test_closed_frames_never_trusts_the_cache_even_with_a_fresh_mtime(monkeypatch):
    """A failed post-close refresh stamps a fresh mtime on a CSV that still holds the
    mid-session partial bar (data_refresh.refresh_symbol os.utime) -- mtime proves nothing."""
    monkeypatch.setattr(data_refresh, "is_stale", lambda *a, **k: pytest.fail("cache consulted"))
    monkeypatch.setattr(data_store, "load_normalized", lambda *a, **k: pytest.fail("cache read"))
    fetched = []

    def cold(symbols, progress):
        fetched.append(list(symbols))
        return [(s, _final(FRIDAY)) for s in symbols]

    monkeypatch.setattr(orun.fetch, "_fetch_cold_frames", cold)
    frames = orun.closed_frames(["AAPL", "MSFT", "AAPL"], FRIDAY, NOW)
    assert fetched == [["AAPL", "MSFT"]]                       # one batched call, deduplicated
    assert frames["AAPL"]["Close"].iloc[-1] == 2.0             # the refetched bar, not a partial one


def test_closed_frames_drops_and_logs_symbols_not_ending_on_the_bar(monkeypatch, caplog):
    monkeypatch.setattr(orun.fetch, "_fetch_cold_frames", lambda cold, progress: [
        ("OK", _final(FRIDAY)), ("OLD", _final(FRIDAY - dt.timedelta(days=1))), ("GONE", None)])
    with caplog.at_level("WARNING"):
        frames = orun.closed_frames(["OK", "OLD", "GONE"], FRIDAY, NOW)
    assert sorted(frames) == ["OK"]
    assert "OLD" in caplog.text and "GONE" in caplog.text


def test_bars_after_the_signal_session_never_reach_the_scan(monkeypatch):
    """Truncation: a frame carrying bars after bar_date comes out identical to one that stops there."""
    monkeypatch.setattr(orun.fetch, "_fetch_cold_frames", lambda cold, progress: [("AAPL", _final(FRIDAY))])
    base = orun.closed_frames(["AAPL"], FRIDAY, NOW)["AAPL"]
    monkeypatch.setattr(orun.fetch, "_fetch_cold_frames", lambda cold, progress: [("AAPL", _final(MONDAY))])
    longer = orun.closed_frames(["AAPL"], FRIDAY, NOW)["AAPL"]
    assert longer.index[-1].date() == FRIDAY
    pd.testing.assert_frame_equal(base.loc[longer.index[0]:], longer.loc[base.index[0]:])


def test_nothing_is_trusted_before_the_close(monkeypatch):
    monkeypatch.setattr(orun.fetch, "_fetch_cold_frames", lambda *a: pytest.fail("fetched"))
    mid_session = dt.datetime(2026, 10, 9, 15, 0, tzinfo=dt.timezone.utc)     # Friday 11:00 ET
    assert orun.closed_frames(["AAPL"], FRIDAY, mid_session) == {}


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
    assert result.skipped == ["TSLA"]                   # only a PREVIOUSLY open ticker; AAPL was issued here


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


# --- the scan: closed bars in, no side effects out -------------------------------------

def _universe(*symbols):
    """Frames that end on MONDAY: Friday's bar plus a later one the scan must never see."""
    return {s: _final(MONDAY) for s in symbols}


def _run_with(monkeypatch, captured, *, scan_tickers=("AAPL",), sector_etf="XLK"):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(config, "MARKET_REGIME_TICKER", "SPY")
    monkeypatch.setattr(orun.scan_run, "_scan_tickers", lambda: list(scan_tickers))
    everything = _universe(*scan_tickers, "SPY", "QQQ", sector_etf)
    monkeypatch.setattr(orun.fetch, "_fetch_cold_frames",
                        lambda cold, progress: [(s, everything[s]) for s in cold if s in everything])
    monkeypatch.setattr(orun.fetch, "_etf_symbol_of_sector", lambda: {"Tech": sector_etf})
    monkeypatch.setattr(orun.fetch, "_sector_etfs_for_tickers",
                        lambda tickers: ({t: "Tech" for t in tickers}, [sector_etf]))
    monkeypatch.setattr(orun.fetch, "_fetch_frames", lambda *a: pytest.fail("cache-first sector fetch"))
    monkeypatch.setattr(orun.short_run, "_stamp_context", lambda frames, spy: frames)
    monkeypatch.setattr(orun.scan_run, "get_regime", lambda spy: "regime")
    monkeypatch.setattr(orun.rs_factors, "refresh_rs_cache", lambda *a: pytest.fail("shared rs cache written"))
    monkeypatch.setattr(orun.rs_factors, "atomic_write_json", lambda *a: pytest.fail("file written"))
    monkeypatch.setattr(TradeLog, "update_open_trades", lambda *a, **k: pytest.fail("monitored open trades"))

    def scan_one(ticker, df, horizons, progress, regime, min_confluence, min_level, **kwargs):
        captured["scan"].append((ticker, df, kwargs))
        return {"items": [_item(ticker)]}

    monkeypatch.setattr(orun.analyze, "_scan_one", scan_one)
    monkeypatch.setattr(orun.dedup, "dedup_scan_items", list)

    def verdict(candidate, item, context):
        captured["contexts"].append(context)
        return qualify.Accepted(item)

    monkeypatch.setattr(orun.qualify, "qualify_short_item", verdict)
    monkeypatch.setattr(orun, "_issue", lambda item, plan, result, frames, spy: captured["issued"].append(
        (item.result.ticker, frames, spy)))


def _captured():
    return {"scan": [], "contexts": [], "issued": []}


def test_the_run_scans_closed_bars_only_with_no_monitoring_and_no_file_writes(monkeypatch):
    captured = _captured()
    _run_with(monkeypatch, captured)
    result = orun.run_outlook(SUNDAY, now=NOW)
    assert result.unavailable is None
    ticker, df, kwargs = captured["scan"][0]
    assert ticker == "AAPL" and kwargs["io"] is orun.OUTLOOK_IO and kwargs["live_prices"] == {}
    assert df.index[-1].date() == FRIDAY and kwargs["spy_df"].index[-1].date() == FRIDAY
    context = captured["contexts"][0]
    assert context.confirmations is None                       # no scan-to-scan debounce
    for frame in [*context.frames.values(), context.spy, *context.sector_frames.values()]:
        assert frame.index[-1].date() == FRIDAY                # sector ETFs too, never a Monday bar
    assert set(context.sector_frames) == {"XLK"}
    assert [t for t, _, _ in captured["issued"]] == ["AAPL"]


def test_the_outlook_io_never_monitors_open_trades():
    assert orun.OUTLOOK_IO.monitor_scan("AAPL", None, 1.0) == ([], [])
    assert orun.OUTLOOK_IO.monitor_open("AAPL", None, 1.0) == ([], [])


def test_the_scan_prices_the_target_session_opex_tier(monkeypatch):
    captured = _captured()
    _run_with(monkeypatch, captured)
    monkeypatch.setattr(config, "OPEX_CAUTION_ENABLED", True)
    orun._scored_items({"AAPL": _final(FRIDAY)}, _final(FRIDAY), orun._target_tier(dt.date(2026, 10, 16)))
    assert captured["scan"][0][2]["opex_tier_today"] == orun.opex.MONTHLY      # Fri 2026-10-16 is the monthly expiry


def test_target_tier_follows_the_target_session_not_the_clock(monkeypatch):
    monkeypatch.setattr(config, "OPEX_CAUTION_ENABLED", True)
    assert orun._target_tier(dt.date(2026, 10, 16)) == orun.opex.MONTHLY
    assert orun._target_tier(MONDAY) is None
    monkeypatch.setattr(config, "OPEX_CAUTION_ENABLED", False)
    assert orun._target_tier(dt.date(2026, 10, 16)) is None


def test_the_rs_cache_is_built_in_memory(monkeypatch):
    monkeypatch.setattr(orun.rs_factors, "relative_return", lambda frame, spy: 0.25)
    cache = orun._rs_cache({"AAPL": object(), "MSFT": object()}, object())
    assert cache == {"rels": {"AAPL": 0.25, "MSFT": 0.25}}


def test_sector_etfs_resolve_on_the_closed_bar(monkeypatch):
    seen = {}
    monkeypatch.setattr(orun.fetch, "_etf_symbol_of_sector", lambda: {"Tech": "XLK"})
    monkeypatch.setattr(orun.fetch, "_sector_etfs_for_tickers", lambda tickers: ({"AAPL": "Tech"}, ["XLK"]))
    monkeypatch.setattr(orun, "closed_frames", lambda symbols, bar, now: seen.update(args=(list(symbols), bar, now))
                        or {"XLK": _frame(FRIDAY)})
    sector_of, etf_of, frames = orun._sector_inputs(["AAPL"], FRIDAY, NOW)
    assert (sector_of, etf_of, list(frames)) == ({"AAPL": "Tech"}, {"Tech": "XLK"}, ["XLK"])
    assert seen["args"] == (["XLK"], FRIDAY, NOW)


def test_sector_inputs_degrade_to_ticker_only_rs(monkeypatch):
    monkeypatch.setattr(orun.fetch, "_etf_symbol_of_sector", lambda: (_ for _ in ()).throw(RuntimeError("down")))
    assert orun._sector_inputs(["AAPL"], FRIDAY, NOW) == ({}, {}, {})


def test_context_carries_the_gate_inputs(monkeypatch):
    monkeypatch.setattr(orun, "_sector_inputs", lambda tickers, bar, now: ({"A": "S"}, {"S": "XLK"}, {"XLK": 1}))
    monkeypatch.setattr(orun, "_regimes", lambda spy: "series")
    context = orun._context({"A": 1}, "spy", "regime", 55.0, FRIDAY, NOW)
    assert (context.sector_of, context.sector_frames, context.regimes) == ({"A": "S"}, {"XLK": 1}, "series")
    assert (context.spy, context.regime, context.breadth, context.confirmations) == ("spy", "regime", 55.0, None)


def test_risk_dollars_sizes_the_stop_distance(monkeypatch):
    plan = _plan(entry_type="stop_entry", trigger_price=102.0, stop_loss=100.0)
    monkeypatch.setattr(orun.account_module, "compute_position_size", lambda entry, stop: {"shares": 10})
    assert orun._risk_dollars(plan) == 20.0
    monkeypatch.setattr(orun.account_module, "compute_position_size", lambda entry, stop: {"shares": 0})
    assert orun._risk_dollars(plan) is None

    def boom(entry, stop):
        raise ValueError("no account")

    monkeypatch.setattr(orun.account_module, "compute_position_size", boom)
    assert orun._risk_dollars(plan) is None


def test_the_card_stamps_the_risk_flags_before_it_is_built(monkeypatch):
    order = []
    monkeypatch.setattr(orun.short_run, "_render_chart", lambda *a: (None, None))
    monkeypatch.setattr(orun.short_run, "_stamp_risk_flags", lambda item, frames, cfg: order.append("flags"))
    monkeypatch.setattr(orun.account_module, "load_account_config", lambda: {"balance": 1000.0})
    monkeypatch.setattr(orun, "build_embed", lambda *a, **k: order.append("embed") or discord.Embed(description="x"))
    monkeypatch.setattr(orun, "build_simple_alert", lambda item: None)
    monkeypatch.setattr(orun, "_hourly", lambda ticker: None)
    item = _item("AAPL")
    item.conf.level, item.htf_info = 3, None
    orun._card(item, _plan(entry_type="stop_entry"), MONDAY, "why", {}, None, {}, None, "T1", None)
    assert order == ["flags", "embed"]
