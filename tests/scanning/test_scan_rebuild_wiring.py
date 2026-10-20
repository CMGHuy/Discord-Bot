"""v171 D5: the main scan rebuilds every alerting plan from the re-quote, and the
embed, chart, plan and trade all come from the rebuilt plan."""
import dataclasses
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import swingbot.config as config
from swingbot.core.marketdata.shared.kinds import QuoteDetail
from swingbot.core.planning.rebuild import RebuildOutcome, RebuildPrice
from swingbot.core.scanning import analyze, engine, fetch, requote as requote_mod, runstate, scan_run
from swingbot.core.tracking.performance import TradeLog
from tests.planning.test_plan_engine_model import _plan
from tests.scanning.test_engine_v2_plans import _structured_df

PRICE = RebuildPrice(101.0, "trade", 1.0, "2026-10-15T15:00:00+00:00", 1000.0, True, "regular")


class _Store:
    plans: list = []
    def add(self, plan): type(self).plans.append(plan)


class _FakeRequote:
    enabled = True
    def __init__(self, age=1.5, price=PRICE): self.age, self.price = age, price
    def age_at_persist(self, ticker): return self.age
    def price_for(self, ticker): return self.price
    def stats(self): return {"kept": 1, "dropped": 0, "misses": 0}


def test_persist_stamps_the_age_only_with_a_live_requote(monkeypatch):
    monkeypatch.setattr(scan_run, "PlanStore", _Store)
    monkeypatch.setattr(scan_run, "log_plan_armed", lambda p: None)
    plan = _plan()
    scan_run._persist_plan_v2(plan, (), _FakeRequote(age=2.25))
    assert plan.quote_age_s == 2.25
    off = _FakeRequote()
    off.enabled = False
    other = _plan(plan_id="p2")
    scan_run._persist_plan_v2(other, (), off)
    scan_run._persist_plan_v2(_plan(plan_id="p3"))
    assert other.quote_age_s is None


def test_trade_quote_and_rebuild_stats():
    assert scan_run._trade_quote(None, "AAPL") is None
    assert scan_run._trade_quote(_FakeRequote(price=None), "AAPL") is None
    assert scan_run._trade_quote(_FakeRequote(age=1.5), "AAPL") == {
        "at": PRICE.quote_at, "kind": "trade", "age_s": 1.5, "session": "regular",
        "confirmed": True}
    off = _FakeRequote()
    off.enabled = False
    assert scan_run._rebuild_stats(off) == {}
    assert scan_run._rebuild_stats(_FakeRequote()) == {
        "rebuild": {"kept": 1, "dropped": 0, "misses": 0}}


def test_a_rebuild_drop_revokes_the_confirmation(monkeypatch):
    revoked = []
    monkeypatch.setattr(scan_run.state, "revoke_confirmation",
                        lambda key, value, prev: revoked.append((key, value, prev)))
    monkeypatch.setattr(scan_run.rebuild, "rebuild_before_post",
                        lambda item, price, **kw: RebuildOutcome(False, "rebuild:risk_cap", price))
    item = SimpleNamespace(result=SimpleNamespace(ticker="AAPL", horizon_key="4w", trend="bullish",
                                                  state_key="k", state_value="v"),
                           plan=SimpleNamespace(stop_distance_pct=2.5), previous_confirmed="p",
                           plan_v2_rejected=None)
    out = scan_run._rebuild_item(item, PRICE, fresh_data={}, regimes=None, regime=None,
                                 require_confirmation=True)
    assert not out.kept and item.plan_v2_rejected == "rebuild:risk_cap"
    assert revoked == [("k", "v", "p")]


def _scan_env(monkeypatch, *, rebuild_on: bool):
    df = _structured_df()
    monkeypatch.setattr(config, "PLAN_REBUILD_ENABLED", rebuild_on)
    monkeypatch.setattr(config, "QUOTE_MAX_AGE_REQUOTE_S", 5)
    monkeypatch.setattr(config, "REBUILD_PRICE_MAX_AGE_S", 60)
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(config, "DECISION_CHART_ENABLED", False)
    monkeypatch.setattr(config, "MIN_REWARD_PCT", 0.5)
    monkeypatch.setattr(config, "MIN_STOP_DISTANCE_PCT", 0.0)
    monkeypatch.setattr(config, "MAX_STOP_LOSS_PCT", 50.0)
    monkeypatch.setattr(config, "MIN_RISK_REWARD_RATIO", 0.01)
    monkeypatch.setattr(config, "MIN_ALERT_CONFIDENCE_LEVEL", 1)
    monkeypatch.setitem(scan_run.HORIZONS["4w"], "sr_target_min_pct", 1.0)
    monkeypatch.setattr(scan_run, "load_watchlist", lambda: ["T0"])
    monkeypatch.setattr(fetch, "get_daily_data",
                        lambda ticker, period=None: df.copy() if ticker == "T0" else None)
    log = TradeLog()
    monkeypatch.setattr(scan_run, "trade_log", log)
    monkeypatch.setattr(runstate, "is_stop_requested", lambda: False)
    monkeypatch.setattr(scan_run, "earnings_within_window", lambda t, d: None)
    monkeypatch.setattr(scan_run, "get_market_events", lambda d: [])
    monkeypatch.setattr(scan_run, "notify_secondary", lambda *a, **k: None)
    monkeypatch.setattr(scan_run, "log_plan_armed", lambda p: None)
    monkeypatch.setattr(scan_run, "build_simple_alert", lambda item: "simple")
    _Store.plans = []
    monkeypatch.setattr(scan_run, "PlanStore", _Store)
    seen = {"embed_plans": [], "chart_entries": [], "rebuilt": [], "quotes": []}
    monkeypatch.setattr(scan_run, "build_embed",
                        lambda item, *a, **k: seen["embed_plans"].append(item.plan) or "embed")
    monkeypatch.setattr(scan_run, "generate_trade_chart",
                        lambda ticker, df_, entry, *a, **k: seen["chart_entries"].append(entry))
    real = analyze.rescenario

    def spy(item, frame, price):
        out = real(item, frame, price)
        out = dataclasses.replace(out) if out is not None else None   # a new object
        seen["rebuilt"].append(out)
        return out

    monkeypatch.setattr(analyze, "rescenario", spy)
    close = float(df["Close"].iloc[-1])

    def quotes(tickers):
        seen["quotes"].append(list(tickers))
        now = datetime.now(timezone.utc)
        return {t: QuoteDetail(t, close, now - timedelta(seconds=1), None, None, None,
                               "alpaca-iex") for t in tickers}

    monkeypatch.setattr(requote_mod, "_default_quote_fn", quotes)
    return log, seen


def test_main_scan_posts_only_the_rebuilt_plan(monkeypatch, stub_batch_fetch):
    log, seen = _scan_env(monkeypatch, rebuild_on=True)
    alerts, _, _ = engine._sync_run_scan("4w", require_confirmation=False, progress=None,
                                         min_confluence=0)
    assert alerts, "the structured frame must alert"
    assert seen["quotes"] == [["T0"]]                       # one batched re-quote
    assert seen["embed_plans"] and all(any(p is r for r in seen["rebuilt"])
                                        for p in seen["embed_plans"])   # identity: the rebuilt object
    stored = _Store.plans
    assert stored and all(p.quote_kind == "trade" and p.price_confirmed for p in stored)
    assert all(p.quote_age_s is not None and p.quote_age_s < 5 for p in stored)
    trades = log.get_trades(status=None, limit=None)
    assert trades and all(t["quote"]["kind"] == "trade" for t in trades)
    # One chart per posted alert, each drawn from that alert's rebuilt plan. The
    # fixture alerts both directions on T0 (dedup keys on ticker+trend); the
    # second finds T0/4w already open, so it posts without logging a trade.
    assert len(seen["chart_entries"]) == len(alerts) == len(seen["embed_plans"])
    assert seen["chart_entries"] == [p.entry for p in seen["embed_plans"]]
    assert {t["entry"] for t in trades} <= set(seen["chart_entries"])


def test_flag_off_scan_is_todays_path(monkeypatch, stub_batch_fetch):
    log, seen = _scan_env(monkeypatch, rebuild_on=False)
    alerts, _, _ = engine._sync_run_scan("4w", require_confirmation=False, progress=None,
                                         min_confluence=0)
    assert alerts and seen["quotes"] == [] and seen["rebuilt"] == []
    assert all(p.quote_kind is None and p.quote_age_s is None for p in _Store.plans)
    assert all("quote" not in t for t in log.get_trades(status=None, limit=None))


def _cluster_item(strategy, score, key):
    plan = SimpleNamespace(entry=100.0, take_profit=110.0, stop_loss=95.0, stop_distance_pct=5.0)
    return SimpleNamespace(
        result=SimpleNamespace(ticker="AAPL", trend="bullish", strategy=strategy, horizon_key="4w",
                               state_key=key, state_value="bullish"),
        plan=plan, conf=SimpleNamespace(score=score, level=3), previous_confirmed=None,
        plan_v2_rejected=None)


def test_dedup_keeps_the_cluster_siblings_on_the_representative():
    from swingbot.core.scanning import dedup
    rep, sib = _cluster_item("RSI", 0.9, "k1"), _cluster_item("Fibonacci", 0.5, "k2")
    assert dedup.dedup_scan_items([sib, rep]) == [rep]
    assert rep.cluster_siblings == [sib]


def test_a_rebuild_drop_revokes_every_cluster_sibling(monkeypatch):
    """The merge loop confirmed every cluster member; the drop posts none of them,
    so every one must stay able to confirm and alert on a later scan."""
    from swingbot.core.scanning import dedup
    revoked = []
    monkeypatch.setattr(scan_run.state, "revoke_confirmation",
                        lambda key, value, prev: revoked.append(key))
    monkeypatch.setattr(scan_run.rebuild, "rebuild_before_post",
                        lambda item, price, **kw: RebuildOutcome(False, "rebuild:risk_cap", price))
    rep, sib = _cluster_item("RSI", 0.9, "k1"), _cluster_item("Fibonacci", 0.5, "k2")
    dedup.dedup_scan_items([rep, sib])
    scan_run._rebuild_item(rep, PRICE, fresh_data={}, regimes=None, regime=None,
                           require_confirmation=True)
    assert revoked == ["k1", "k2"]
    revoked.clear()
    scan_run._rebuild_item(rep, PRICE, fresh_data={}, regimes=None, regime=None,
                           require_confirmation=False)
    assert revoked == []
