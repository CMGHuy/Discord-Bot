"""V118-5: the direction/source/mode funnel and the extra lane's existing-trade routing."""
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.scanning import analyze, dedup, short_candidates, short_funnel, short_run
from swingbot.core.scanning.short_funnel import STAGES, ShortFunnel
from tests.scanning.test_engine_v2_plans import _structured_df, isolate_data_dir  # noqa: F401
from tests.scanning.test_short_lane_scan import (  # noqa: F401
    CANDIDATE, _FakeLog, _lane_dict, _ready_item, alert_env, both_directions, context, frame, lane,
    merge_env)


def req(key, passed):
    return SimpleNamespace(key=key, passed=passed, label=key, detail="")


# --- the counter --------------------------------------------------------------

def test_stable_stage_names_and_serialisable_keys():
    assert STAGES == ("candidate", "aligned", "scenario", "geometry", "confidence",
                      "rs", "plan", "trade_decision", "dedup", "send")
    funnel = ShortFunnel()
    funnel.record("bearish", "short_universe", "broad", "candidate")
    funnel.record("bullish", "base", None, "send")
    assert funnel.snapshot() == {"bearish/short_universe/broad/candidate/ok": 1,
                                 "bullish/base/base/send/ok": 1}


def test_unknown_stage_is_refused():
    with pytest.raises(ValueError):
        ShortFunnel().record("bearish", "base", None, "nonsense")


def test_existing_trade_suppression_is_a_trade_decision_rejection_not_a_send():
    funnel = ShortFunnel()
    funnel.record("bearish", "short_universe", "broad", "trade_decision", reason="existing_trade")
    snap = funnel.snapshot()
    assert snap["bearish/short_universe/broad/trade_decision/existing_trade"] == 1
    assert snap.get("bearish/short_universe/broad/send", 0) == 0


@pytest.mark.parametrize("direction,source,mode", [
    ("bullish", "base", None), ("bearish", "base", None),
    ("bearish", "short_universe", "broad"), ("bearish", "short_universe", "isolated")])
def test_ordered_stage_counts_per_direction_source_mode(direction, source, mode):
    funnel = ShortFunnel()
    funnel.merge(short_funnel.scenario_events(direction, source, mode, [req("min_confluence", True)]))
    label = f"{direction}/{source}/{mode or 'base'}"
    assert funnel.snapshot() == {f"{label}/scenario/ok": 1, f"{label}/geometry/ok": 1,
                                 f"{label}/confidence/ok": 1}


def test_a_geometry_failure_is_counted_once_and_never_reaches_later_stages():
    events = short_funnel.scenario_events(
        "bearish", "short_universe", "broad",
        [req("min_risk_reward", False), req("min_confidence", False)])
    funnel = ShortFunnel()
    funnel.merge(events)
    assert funnel.snapshot() == {
        "bearish/short_universe/broad/scenario/ok": 1,
        "bearish/short_universe/broad/geometry/min_risk_reward": 1}


def test_a_confidence_failure_names_its_requirement():
    funnel = ShortFunnel()
    funnel.merge(short_funnel.scenario_events("bullish", "base", None, [req("min_confluence", False)]))
    assert funnel.snapshot()["bullish/base/base/confidence/min_confluence"] == 1
    assert funnel.snapshot()["bullish/base/base/geometry/ok"] == 1


# --- worker results carry immutable events; items carry their candidate context ----

def test_base_scan_returns_events_for_both_directions_and_never_mutates_shared_state(both_directions):
    stats = analyze._scan_one("AAA", frame(), ["2w"], None, None, 1, 1, rs_cache=None, spy_df=None)
    funnel = ShortFunnel()
    funnel.merge(stats["funnel_events"])
    snap = funnel.snapshot()
    assert snap["bullish/base/base/scenario/ok"] == 1
    assert snap["bearish/base/base/scenario/ok"] == 1
    assert all(item.candidate_context is None for item in stats["items"])


def test_extra_candidate_stamps_context_and_funnels_only_bearish(both_directions):
    ctx = context()
    items = analyze.scan_extra_candidate(CANDIDATE, frame(), ctx, ["2w"])
    assert [i.candidate_context for i in items] == [
        {"source": "short_universe", "mode": "broad", "reference_id": "ref-1",
         "decision_bar_date": "2026-09-18"}]
    funnel = ShortFunnel()
    funnel.merge(ctx.funnel_events)
    snap = funnel.snapshot()
    assert snap["bearish/short_universe/broad/candidate/ok"] == 1
    assert snap["bearish/short_universe/broad/aligned/ok"] == 1
    assert snap["bearish/short_universe/broad/scenario/ok"] == 1
    assert not any(k.startswith("bullish") for k in snap)


def test_unalignable_frame_is_funnelled_and_still_monitors_an_open_trade(both_directions, monkeypatch):
    monitored = []
    monkeypatch.setattr(analyze, "monitor_open_only",
                        lambda t, df, live=None: monitored.append((t, live)) or (["closed"], ["near"]))
    ctx = context(live_prices={"AAA": 97.0})
    assert analyze.scan_extra_candidate(CANDIDATE, frame().iloc[:5], ctx, ["2w"]) == []
    assert monitored == [("AAA", 97.0)]
    assert ctx.newly_closed == ["closed"] and ctx.near_close == ["near"]
    funnel = ShortFunnel()
    funnel.merge(ctx.funnel_events)
    assert funnel.snapshot()["bearish/short_universe/broad/aligned/unaligned"] == 1


def test_dedup_keeps_the_representative_candidate_context(both_directions):
    first = analyze.scan_extra_candidate(CANDIDATE, frame(), context(), ["2w"])[0]
    twin = analyze.scan_extra_candidate(CANDIDATE, frame(), context(), ["2w"])[0]
    first.conf.score, twin.conf.score = 80, 50
    kept = dedup.dedup_scan_items([twin, first])
    assert [i.candidate_context["mode"] for i in kept] == ["broad"]
    funnel = ShortFunnel()
    funnel.record_dedup([twin, first], kept)
    assert funnel.snapshot() == {"bearish/short_universe/broad/dedup/merged": 1,
                                 "bearish/short_universe/broad/dedup/ok": 1}


# --- selection rejections are no longer discarded -----------------------------------

def test_candidate_rejection_reasons_are_collected(monkeypatch):
    monkeypatch.setattr(short_candidates, "select_mode", lambda *a, **k: (None, "missing_sector"))
    monkeypatch.setattr(short_candidates, "etf_for_sector", lambda s: None)
    snapshot = SimpleNamespace(symbols=("AAA",), sector_of={}, membership_asof="2026-09-01")
    reference = SimpleNamespace(frames={"AAA": None}, spy=frame(), sector_frames={}, spy_regime=object(),
                                reference_rels=(), now=None, reference_id="r")
    rejected = []
    found, reason = short_candidates.extra_candidates(("BASE",), snapshot, reference, rejected=rejected)
    assert found == [] and reason is None and rejected == [("AAA", "missing_sector")]


# --- existing-trade routing and sends on the extra lane ------------------------------

def _spy_notify(monkeypatch):
    sent = []
    monkeypatch.setattr(short_run, "notify_secondary", lambda *a, **k: sent.append(a))
    return sent


def test_existing_trade_suppresses_send_and_secondary_notification(alert_env, monkeypatch):
    monkeypatch.setattr(short_run, "trade_log", _FakeLog(open_trade={"id": 7, "direction": "bullish"}))
    sent = _spy_notify(monkeypatch)
    funnel = ShortFunnel()
    item = _ready_item(monkeypatch)
    assert short_run._build_alerts([item], True, {"AAA": frame()}, frame(), funnel=funnel) == []
    snap = funnel.snapshot()
    assert snap["bearish/short_universe/broad/trade_decision/existing_trade"] == 1
    assert not any("/send/" in k for k in snap)
    assert sent == []


def test_a_posted_alert_counts_trade_decision_and_send_once(alert_env, monkeypatch):
    monkeypatch.setattr(short_run, "trade_log", _FakeLog())
    sent = _spy_notify(monkeypatch)
    funnel = ShortFunnel()
    item = _ready_item(monkeypatch)
    assert len(short_run._build_alerts([item], True, {"AAA": frame()}, frame(), funnel=funnel)) == 1
    snap = funnel.snapshot()
    assert snap["bearish/short_universe/broad/trade_decision/ok"] == 1
    assert snap["bearish/short_universe/broad/send/ok"] == 1
    assert len(sent) == 1


def test_rs_and_plan_rejections_are_counted_under_their_own_stage(merge_env, monkeypatch):
    leader, laggard = _ready_item(monkeypatch), _ready_item(monkeypatch)
    leader.rs_percentile = 99.0

    def reject(it, *a, **k):
        it.plan_v2_rejected = "no_qualifying_target"
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(analyze, "attach_plan_v2", reject)
    lane = _lane_dict()
    lane["funnel"] = ShortFunnel()
    assert short_run._qualified_items([leader, laggard], False, {"AAA": frame()}, lane) == []
    snap = lane["funnel"].snapshot()
    assert snap["bearish/short_universe/broad/rs/rs_blocked"] == 1
    assert snap["bearish/short_universe/broad/rs/ok"] == 1
    assert snap["bearish/short_universe/broad/plan/no_qualifying_target"] == 1


def test_open_extra_trade_that_lost_its_mode_is_monitored_and_funnelled_not_selected(monkeypatch):
    monitored = []
    monkeypatch.setattr(short_run, "_open_extra_tickers", lambda base: ["OLD"])
    monkeypatch.setattr(analyze, "monitor_open_only",
                        lambda t, df, live=None: monitored.append(t) or ([], []))
    ctx = context()
    funnel = ShortFunnel()
    short_run._monitor_stranded(("BASE",), set(), {"OLD": frame()}, {}, ctx, funnel=funnel)
    assert monitored == ["OLD"]
    assert funnel.snapshot() == {"bearish/short_universe/unselected/candidate/not_selected": 1}


def test_unresolved_extra_symbols_get_named_fetch_reasons(monkeypatch):
    monkeypatch.setattr(short_run.fetch, "_crawl_bounded",
                        lambda queue, **k: ({"AAA": frame()}, "budget_exhausted"))
    snapshot = SimpleNamespace(symbols=("AAA", "BBB", "BASE"))
    funnel = ShortFunnel()
    frames = short_run._crawl_extra(snapshot, ("BASE",), funnel=funnel)
    assert set(frames) == {"AAA"}
    assert funnel.snapshot() == {"bearish/short_universe/unselected/candidate/budget_exhausted": 1}


# --- the base merge feeds the same funnel into scan telemetry --------------------------

def test_base_scan_telemetry_carries_the_direction_source_mode_funnel(
        monkeypatch, tmp_path, stub_batch_fetch, isolate_data_dir):   # noqa: F811
    from swingbot.core.scanning import engine, fetch, runstate, scan_run, telemetry
    from swingbot.core.tracking.performance import TradeLog
    df = _structured_df()
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "shadow")
    monkeypatch.setattr(config, "MIN_REWARD_PCT", 0.5)
    monkeypatch.setattr(config, "MIN_STOP_DISTANCE_PCT", 0.0)
    monkeypatch.setattr(config, "MAX_STOP_LOSS_PCT", 50.0)
    monkeypatch.setattr(config, "MIN_RISK_REWARD_RATIO", 0.01)
    monkeypatch.setitem(scan_run.HORIZONS["4w"], "sr_target_min_pct", 1.0)
    monkeypatch.setattr(scan_run, "load_watchlist", lambda: ["TEST"])
    monkeypatch.setattr(fetch, "get_daily_data",
                        lambda ticker, period=None: df.copy() if ticker == "TEST" else None)
    monkeypatch.setattr(scan_run, "trade_log", TradeLog())
    monkeypatch.setattr(runstate, "is_stop_requested", lambda: False)
    monkeypatch.setattr(dedup, "dedup_scan_items", lambda items: [])
    rows = []
    monkeypatch.setattr(telemetry, "log_scan_telemetry", lambda stats, path=None: rows.append(stats))
    engine._sync_run_scan("4w", require_confirmation=False, progress=None, min_confluence=999_999)
    funnel = rows[-1]["short_funnel"]
    scenario_keys = [k for k in funnel if "/scenario/" in k]
    assert scenario_keys and all(k.split("/")[1:3] == ["base", "base"] for k in scenario_keys)
    assert any(k.endswith("/confidence/min_confluence") for k in funnel)


# --- fix round 1 ---------------------------------------------------------------------

class _BaseLog:
    """scan_run's trade log: one open LONG until a reversal closes it."""

    def __init__(self):
        self.open = {"id": 9, "direction": "bullish"}
        self.logged = []

    def open_trade_for_ticker(self, ticker):
        return self.open

    def close_trade_reversed(self, trade_id, price):
        self.open = None
        return {"id": trade_id}

    def log_trade(self, **kw):
        self.logged.append(kw)
        return "T-1"

    def get_stats(self, *a, **k):
        return {"win_rate": None, "closed": 0, "open": 1, "n": 0}

    def get_trades(self, **k):
        return []


def _base_alert_scan(monkeypatch, reversal_allowed):
    """_sync_run_scan through the real alert loop with an open LONG on the only ticker."""
    from swingbot.core.scanning import engine, fetch, runstate, scan_run, telemetry
    df = _structured_df()
    for name, value in (("PLAN_ENGINE_V2", "shadow"), ("MIN_REWARD_PCT", 0.5),
                        ("MIN_STOP_DISTANCE_PCT", 0.0), ("MAX_STOP_LOSS_PCT", 50.0),
                        ("MIN_RISK_REWARD_RATIO", 0.01), ("MIN_ALERT_CONFIDENCE_LEVEL", 1),
                        ("SIGNAL_CONFIRMATION_SCANS", 1), ("RS_GATE", False)):
        monkeypatch.setattr(config, name, value)
    monkeypatch.setitem(scan_run.HORIZONS["4w"], "sr_target_min_pct", 1.0)
    monkeypatch.setattr(scan_run, "load_watchlist", lambda: ["TEST"])
    monkeypatch.setattr(fetch, "get_daily_data",
                        lambda ticker, period=None: df.copy() if ticker == "TEST" else None)
    monkeypatch.setattr(fetch, "get_current_price", lambda *a, **k: 100.0)
    monkeypatch.setattr(runstate, "is_stop_requested", lambda: False)
    fake = _BaseLog()
    monkeypatch.setattr(scan_run, "trade_log", fake)
    real_scan_one = analyze._scan_one

    def bearish_only(*a, **k):
        stats = real_scan_one(*a, **k)
        stats["items"] = [i for i in stats["items"] if i.result.trend == "bearish"]
        return stats
    monkeypatch.setattr(analyze, "_scan_one", bearish_only)
    monkeypatch.setattr(scan_run, "evaluate_reversal",
                        lambda *a, **k: SimpleNamespace(allowed=reversal_allowed, reason="test"))
    monkeypatch.setattr(scan_run, "get_market_events", lambda days: [])
    monkeypatch.setattr(scan_run, "_earnings_in_window", lambda *a: None)
    monkeypatch.setattr(scan_run, "generate_trade_chart", lambda *a, **k: None)
    monkeypatch.setattr(scan_run, "render_decision_chart", lambda *a, **k: None)
    monkeypatch.setattr(scan_run.throttle, "kill_state", lambda: {"on": False})
    sent, rows = [], []
    monkeypatch.setattr(scan_run, "notify_secondary", lambda *a, **k: sent.append(a))
    monkeypatch.setattr(telemetry, "log_scan_telemetry", lambda stats, path=None: rows.append(stats))
    alerts, _closed, _near = engine._sync_run_scan("4w", require_confirmation=True, progress=None,
                                                   min_confluence=0)
    return alerts, sent, rows[-1]["short_funnel"], fake


def test_base_existing_long_with_reversal_denied_funnels_existing_trade_and_sends_nothing(
        monkeypatch, stub_batch_fetch, isolate_data_dir):   # noqa: F811
    alerts, sent, funnel, fake = _base_alert_scan(monkeypatch, reversal_allowed=False)
    assert funnel["bearish/base/base/trade_decision/existing_trade"] >= 1
    assert not any("/send/" in k or "/trade_decision/ok" in k for k in funnel)
    assert alerts == [] and sent == [] and fake.logged == []


def test_base_reversal_allowed_funnels_decision_ok_then_send(
        monkeypatch, stub_batch_fetch, isolate_data_dir):   # noqa: F811
    alerts, sent, funnel, fake = _base_alert_scan(monkeypatch, reversal_allowed=True)
    assert funnel["bearish/base/base/trade_decision/ok"] >= 1
    assert funnel["bearish/base/base/send/ok"] == len(alerts) == len(sent) >= 1
    assert "bearish/base/base/trade_decision/existing_trade" not in funnel
    assert fake.logged and fake.open is None


def test_a_not_fully_qualifying_item_is_not_counted_past_confidence(merge_env, monkeypatch):
    """`!check` lets failed items reach the merge; their rejection is already in
    scenario_events, so rs/plan/dedup/trade_decision must not count them again."""
    item = _ready_item(monkeypatch)
    item.requirements = [req("min_risk_reward", False)]
    lane = _lane_dict()
    lane["funnel"] = ShortFunnel()
    short_run._qualified_items([item], False, {"AAA": frame()}, lane)
    lane["funnel"].record_dedup([item], [item])
    lane["funnel"].record_decision(item)
    assert lane["funnel"].snapshot() == {}


def test_extra_lane_does_not_record_unmet_trade_decision(alert_env, monkeypatch):
    monkeypatch.setattr(short_run, "trade_log", _FakeLog())
    funnel = ShortFunnel()
    item = _ready_item(monkeypatch)
    item.requirements = [req("min_confluence", False)]
    assert short_run._build_alerts([item], False, {"AAA": frame()}, frame(), funnel=funnel) == []
    assert funnel.snapshot() == {}


@pytest.mark.parametrize("reason_source", ["rejected_mode", "missing_frame"])
def test_a_stranded_open_symbol_is_counted_once_at_candidate(lane, monkeypatch, reason_source):
    from swingbot.core.marketdata import universe
    from swingbot.core.marketdata.universe import ShortSnapshot
    rows = []
    monkeypatch.setattr(short_run.telemetry, "log_scan_telemetry", lambda stats, path=None: rows.append(stats))
    monkeypatch.setattr(universe, "short_snapshot",
                        lambda day, live: ShortSnapshot(("AAA", "OLD", "BASE"), "2026-09-01", {}))
    from swingbot.core.scanning import fetch, scan_run
    frames = {"AAA": frame(), "OLD": frame()} if reason_source == "rejected_mode" else {"AAA": frame()}
    monkeypatch.setattr(fetch, "_crawl_bounded", lambda syms, **k: (frames, None))

    def build(base, *, rejected=None, **k):
        if reason_source == "rejected_mode":
            rejected.append(("OLD", "not_laggard"))
        return [CANDIDATE]
    monkeypatch.setattr(scan_run, "build_extra_candidates", build)
    short_run._sync_run_short_scan(False)
    funnel = rows[-1]["short_funnel"]
    old_rows = {k: v for k, v in funnel.items()
                if "/candidate/" in k and not k.endswith("/candidate/ok")}
    assert old_rows == {"bearish/short_universe/unselected/candidate/"
                        + ("not_laggard" if reason_source == "rejected_mode" else "missing_frame"): 1}
