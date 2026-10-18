"""v171 D5: the SHORT lane rebuilds through the same Requote and entry point."""
import inspect
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.planning.rebuild import RebuildOutcome, RebuildPrice
from swingbot.core.scanning import analyze, qualify, requote as requote_mod, short_run

PRICE = RebuildPrice(101.0, "trade", 1.0, "2026-10-15T15:00:00+00:00", 1000.0, True, "regular")


def _item(ticker="AAA"):
    return SimpleNamespace(result=SimpleNamespace(ticker=ticker, close=100.0, horizon_key="4w",
                                                  trend="bearish"),
                           all_requirements_met=True, scan_price=100.0, plan="old",
                           plan_v2=None, plan_v2_rejected=None)


def test_rescenario_for_uses_the_lane_frame(monkeypatch):
    calls = []
    monkeypatch.setattr(analyze, "rescenario", lambda item, df, p: calls.append((df, p)) or "s")
    item = _item()
    assert short_run._rescenario_for(item, {"AAA": "frame"})(101.0) == "s"
    assert short_run._rescenario_for(item, {})(99.0) == "s"
    assert calls == [("frame", 101.0), (None, 99.0)]


def test_attach_for_sets_the_scenario_then_uses_the_lane_attach(monkeypatch):
    seen = []
    monkeypatch.setattr(qualify, "_attach_plan", lambda item, ctx: seen.append((item.plan, ctx)))
    item, ctx = _item(), short_run._bare_context({})
    short_run._attach_for(item, ctx)("new")
    assert item.plan == "new" and seen == [("new", ctx)]


def test_a_dropped_short_revokes_through_the_lane_path(monkeypatch):
    revoked = []
    monkeypatch.setattr(short_run.rebuild, "rebuild_before_post",
                        lambda item, price, **kw: RebuildOutcome(False, "rebuild:no_scenario", price))
    monkeypatch.setattr(qualify, "_revoke", lambda item, ctx: revoked.append(item.plan_v2_rejected))
    item = _item()
    out = short_run._rebuild_fn({}, short_run._bare_context({}))(item, PRICE)
    assert not out.kept and revoked == ["rebuild:no_scenario"]


def test_a_dropped_short_representative_revokes_its_siblings(monkeypatch):
    revoked = []
    store = SimpleNamespace(revoke_confirmation=lambda k, v, p: revoked.append((k, v, p)))
    monkeypatch.setattr(short_run.rebuild, "rebuild_before_post",
                        lambda item, price, **kw: RebuildOutcome(False, "rebuild:no_scenario", price))
    monkeypatch.setattr(qualify, "_revoke", lambda item, ctx: None)
    sib = SimpleNamespace(result=SimpleNamespace(state_key="k", state_value="v"),
                          previous_confirmed=3)
    item = _item()
    item.cluster_siblings = [sib]
    ctx = qualify.QualifyContext(frames={}, spy=None, sector_of={}, etf_symbol_of={},
                                 sector_frames={}, regime=None, regimes=None, confirmations=store)
    short_run._rebuild_fn({}, ctx)(item, PRICE)
    assert revoked == [("k", "v", 3)]


@pytest.fixture
def lane(monkeypatch):
    posted = []
    monkeypatch.setattr(short_run, "load_account_config", lambda: {})
    monkeypatch.setattr(short_run.runstate, "is_stop_requested", lambda: False)
    monkeypatch.setattr(short_run, "_alert_for",
                        lambda item, frames, spy, cfg, alerts, funnel=None, requote=None:
                        posted.append((item.result.ticker, requote)))
    return posted


def test_build_alerts_rebuilds_and_posts_only_kept_items(monkeypatch, lane):
    monkeypatch.setattr(config, "PLAN_REBUILD_ENABLED", True)
    quotes = []
    monkeypatch.setattr(requote_mod, "_default_quote_fn", lambda t: quotes.append(list(t)) or {})
    monkeypatch.setattr(short_run.rebuild, "rebuild_before_post",
                        lambda item, price, **kw: RebuildOutcome(item.result.ticker == "AAA",
                                                                 None, price))
    monkeypatch.setattr(qualify, "_revoke", lambda item, ctx: None)
    short_run._build_alerts([_item("AAA"), _item("BBB")], False, {}, None)
    assert quotes == [["AAA", "BBB"]]
    assert [t for t, _ in lane] == ["AAA"] and lane[0][1] is not None


def test_build_alerts_flag_off_is_todays_loop(monkeypatch, lane):
    monkeypatch.setattr(config, "PLAN_REBUILD_ENABLED", False)
    monkeypatch.setattr(requote_mod, "_default_quote_fn",
                        lambda t: pytest.fail("no re-quote with the flag off"))
    short_run._build_alerts([_item("AAA"), _item("BBB")], False, {}, None)
    assert [t for t, _ in lane] == ["AAA", "BBB"]


def test_log_trade_carries_the_requote(monkeypatch):
    seen = {}
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(short_run.scan_run, "_persist_plan_v2",
                        lambda plan, alerts, requote=None: seen.setdefault("persist", requote))
    monkeypatch.setattr(short_run.scan_run, "_trade_quote", lambda rq, t: {"kind": "trade", "t": t})
    monkeypatch.setattr(short_run.trade_log, "log_trade",
                        lambda **kw: seen.setdefault("quote", kw["quote"]) and "tid")
    from tests.planning.test_plan_engine_model import _plan
    from tests.scanning.test_short_lane_scan import scenario
    item = SimpleNamespace(result=SimpleNamespace(ticker="AAA", strategy="S/R Confluence",
                                                  horizon_key="4w", trend="bearish"),
                           plan=scenario("bearish"), plan_v2=_plan(ticker="AAA"),
                           conf=SimpleNamespace(level=3, label="Medium", score=60, breakdown={}),
                           level_map=None, combined_from=[])
    nums = {"entry": 100.0, "stop_loss": 102.0, "take_profit": 94.0, "target2": None}
    rq = object()
    short_run._log_trade(item, nums, "why", None, [], requote=rq)
    assert seen["persist"] is rq and seen["quote"] == {"kind": "trade", "t": "AAA"}


def test_the_lane_passes_its_qualify_context():
    src = inspect.getsource(short_run._sync_run_short_scan)
    assert "qualify_context=_qualify_context(require_confirmation, frames, lane)" in src
