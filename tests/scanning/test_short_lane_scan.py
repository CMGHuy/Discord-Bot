"""V118-4: bounded fetch and bearish-only scenario analysis for the SHORT lane."""
import numpy as np
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.market.levels import Scenario
from swingbot.core.marketdata import universe
from swingbot.core.scanning import analyze, fetch
from swingbot.core.scanning.short_candidates import ShortCandidate

CANDIDATE = ShortCandidate("AAA", "broad", "short_universe", "2026-09-18",
                           "2026-09-01", "ref-1")


def frame(volume=1e6, n=260):
    idx = pd.bdate_range(end=pd.Timestamp("2026-09-18"), periods=n)
    close = np.full(n, 100.0)
    return pd.DataFrame({"Close": close, "Open": close, "High": close + 1,
                         "Low": close - 1, "Volume": volume}, index=idx)


def scenario(direction):
    bull = direction == "bullish"
    return Scenario(
        direction=direction, entry=100.0, market_price=100.0,
        stop_loss=98.0 if bull else 102.0, stop_sources=["S"], stop_distance_pct=2.0,
        tight_stop=False, atr_floor_pct=1.0, take_profit=106.0 if bull else 94.0,
        target_distance_pct=6.0, target_sources=["T"], target2_price=None,
        target2_distance_pct=None, target2_sources=None,
        constraints={"min_reward": True})


def context(**over):
    base = dict(regime=None, min_confluence=1, min_confidence=1,
                rs_cache={"rels": {"0": -0.1, "1": 0.1}}, spy_df=frame(),
                live_prices={}, hard_filters=None, opex_tier=None)
    base.update(over)
    return analyze.ExtraScanContext(**base)


@pytest.fixture
def both_directions(monkeypatch):
    monkeypatch.setattr(analyze.levels, "build_scenarios",
                        lambda *a, **k: [scenario("bullish"), scenario("bearish")])
    monkeypatch.setattr(analyze.trade_log, "update_open_trades", lambda *a, **k: [])
    monkeypatch.setattr(analyze, "_check_near_close", lambda *a, **k: [])
    monkeypatch.setattr(analyze.universe, "data_quality_issues", lambda *a: [])


def test_scenarios_for_direction_filters_and_passes_none_through():
    scenarios = [scenario("bullish"), scenario("bearish")]
    assert analyze.scenarios_for_direction(scenarios, None) is scenarios
    assert [s.direction for s in analyze.scenarios_for_direction(scenarios, ("bearish",))] == ["bearish"]


def test_extra_candidate_continues_only_with_its_bearish_scenario(both_directions, monkeypatch):
    scored = []
    real = analyze.levels.count_confirming_strategies
    monkeypatch.setattr(analyze.levels, "count_confirming_strategies",
                        lambda df, h, price, level, **k: scored.append(level) or real(df, h, price, level, **k))
    items = analyze.scan_extra_candidate(CANDIDATE, frame(), context(), ["2w"])
    assert [item.result.trend for item in items] == ["bearish"]
    assert set(scored) == {94.0, 102.0}          # the bullish 106/98 pair was never scored


def test_base_scan_still_processes_both_directions(both_directions):
    stats = analyze._scan_one("AAA", frame(), ["2w"], None, None, 1, 1,
                              rs_cache=None, spy_df=None)
    assert sorted(item.result.trend for item in stats["items"]) == ["bearish", "bullish"]


def test_illiquid_extra_symbol_is_rejected_by_the_current_screen(both_directions):
    assert analyze.scan_extra_candidate(CANDIDATE, frame(volume=1.0), context(), ["2w"]) == []


def test_data_quality_failure_rejects_the_extra_symbol(both_directions, monkeypatch):
    monkeypatch.setattr(analyze.universe, "data_quality_issues", lambda *a: ["gap"])
    assert analyze.scan_extra_candidate(CANDIDATE, frame(), context(), ["2w"]) == []


def test_missing_frame_is_an_empty_scan_not_an_error(both_directions):
    assert analyze.scan_extra_candidate(CANDIDATE, None, context(), ["2w"]) == []


# --- bounded fetch ---------------------------------------------------------------

class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def _crawler(clock, cost, calls, missing=()):
    def crawl(chunk, progress=None):
        calls.append(list(chunk))
        clock.now += cost
        return {s: frame() for s in chunk if s not in missing}
    return crawl


def _bounded(monkeypatch, symbols, *, budget=120, cost=100.0, max_symbols=50, chunk=2, missing=()):
    clock, calls = Clock(), []
    monkeypatch.setattr(fetch, "_crawl_latest_data", _crawler(clock, cost, calls, missing))
    frames, reason = fetch._crawl_bounded(
        symbols, max_symbols=max_symbols, budget_s=budget, chunk=chunk, clock=clock)
    return frames, reason, calls


def test_budget_exhaustion_stops_only_the_extra_queue(monkeypatch):
    frames, reason, calls = _bounded(monkeypatch, list("ABCDEF"))
    assert calls == [["A", "B"], ["C", "D"]]      # 100s then 200s: deadline (120) passed before chunk 3
    assert set(frames) == set("ABCD")
    assert reason == "budget_exhausted"


def test_deadline_boundary_is_exhausted_not_one_more_chunk(monkeypatch):
    frames, reason, calls = _bounded(monkeypatch, list("ABCD"), budget=100, cost=100.0)
    assert calls == [["A", "B"]] and reason == "budget_exhausted"


def test_finishing_inside_the_budget_records_no_reason(monkeypatch):
    frames, reason, calls = _bounded(monkeypatch, list("ABCD"), budget=500, cost=10.0)
    assert set(frames) == set("ABCD") and reason is None


def test_symbol_cap_truncates_the_queue_before_any_fetch(monkeypatch):
    frames, reason, calls = _bounded(monkeypatch, list("ABCDEF"), max_symbols=3, budget=500, cost=1.0)
    assert [s for c in calls for s in c] == ["A", "B", "C"]


def test_cold_symbol_that_never_returns_is_absent_not_fatal(monkeypatch):
    frames, reason, _ = _bounded(monkeypatch, list("ABCD"), budget=500, cost=1.0, missing=("B",))
    assert set(frames) == set("ACD") and reason is None


def test_chunk_failure_keeps_earlier_chunks_and_names_the_reason(monkeypatch):
    clock, calls = Clock(), []
    good = _crawler(clock, 1.0, calls)

    def flaky(chunk, progress=None):
        if len(calls) == 1:
            raise RuntimeError("yahoo down")
        return good(chunk, progress)
    monkeypatch.setattr(fetch, "_crawl_latest_data", flaky)
    frames, reason = fetch._crawl_bounded(list("ABCD"), max_symbols=50, budget_s=500, chunk=2, clock=clock)
    assert set(frames) == {"A", "B"} and reason == "fetch_failed"


def test_defaults_are_the_documented_safeguards():
    assert config.SHORT_UNIVERSE_MAX_SYMBOLS == 50
    assert config.SHORT_UNIVERSE_FETCH_BUDGET_SECONDS == 120


# --- the extra pass --------------------------------------------------------------

import asyncio  # noqa: E402
import datetime as dt  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from swingbot.core.edge import factors as rs_factors  # noqa: E402
from swingbot.core.marketdata.universe import ShortSnapshot  # noqa: E402
from swingbot.core.scanning import scan_run, short_run  # noqa: E402

NOW = dt.datetime(2026, 9, 18, 22, 0, tzinfo=dt.timezone.utc)


@pytest.fixture
def lane(monkeypatch, both_directions):
    """The extra pass with every network/store edge stubbed; records the calls."""
    seen = {"bounded": [], "monitored": [], "built": [], "rs_refresh": 0}
    ref = SimpleNamespace(spy=frame(), sector_frames={}, reference_rels=(-0.2, 0.1, 0.2),
                          frames={})
    monkeypatch.setattr(config, "SHORT_UNIVERSE_ENABLED", True)
    monkeypatch.setattr(config, "RS_GATE", False)
    monkeypatch.setattr(scan_run, "_short_now", lambda: NOW)
    monkeypatch.setattr(scan_run, "_scan_tickers", lambda: ["BASE"])
    monkeypatch.setattr(universe, "short_snapshot",
                        lambda day, live: ShortSnapshot(("AAA", "BASE"), "2026-09-01", {}))
    monkeypatch.setattr(fetch, "_crawl_bounded",
                        lambda syms, **k: (seen["bounded"].append(list(syms)) or {"AAA": frame()}, None))
    monkeypatch.setattr(fetch, "_crawl_latest_data",
                        lambda syms, progress=None: {s: frame() for s in syms})
    monkeypatch.setattr(fetch, "_fetch_live_prices", lambda syms, p=None: {})
    monkeypatch.setattr(fetch, "_etf_symbol_of_sector", lambda: {})
    monkeypatch.setattr(scan_run, "_short_reference", lambda *a: ref)
    monkeypatch.setattr(scan_run, "build_extra_candidates", lambda *a, **k: [CANDIDATE])
    monkeypatch.setattr(scan_run, "get_regime", lambda df: None)
    monkeypatch.setattr(short_run.scan_run, "get_regime", lambda df: None)
    monkeypatch.setattr(rs_factors, "refresh_rs_cache",
                        lambda *a, **k: seen.__setitem__("rs_refresh", seen["rs_refresh"] + 1))
    monkeypatch.setattr(short_run, "_open_extra_tickers", lambda base: ["OLD"])
    monkeypatch.setattr(analyze, "monitor_open_only",
                        lambda t, df, live=None: seen["monitored"].append(t) or ([], []))
    monkeypatch.setattr(short_run, "_stamp_context", lambda frames, spy: frames)
    monkeypatch.setattr(short_run, "_build_alerts",
                        lambda deduped, rc, frames, spy: seen["built"].append(list(deduped)) or [])
    monkeypatch.setattr(short_run, "_lane_state", lambda *a: {
        "sector_of": {}, "etf_symbol_of": {}, "sector_frames": {}, "spy": None,
        "regime": None, "regimes": None})
    return seen


def test_extra_pass_scans_bearish_only_and_never_refreshes_the_base_rs_cache(lane):
    alerts, closed, near = short_run._sync_run_short_scan(False)
    assert alerts == []
    assert [i.result.trend for i in lane["built"][0]] == ["bearish"]
    assert lane["rs_refresh"] == 0
    assert lane["bounded"] == [["AAA"]]          # BASE is the base lane's symbol, not an extra


def test_open_extra_trade_is_monitored_even_when_not_a_candidate_today(lane):
    short_run._sync_run_short_scan(False)
    assert lane["monitored"] == ["OLD"]


def test_flag_off_means_no_fetch_at_all(lane, monkeypatch):
    monkeypatch.setattr(config, "SHORT_UNIVERSE_ENABLED", False)
    assert asyncio.run(short_run.run_short_universe_scan()) == []
    assert lane["bounded"] == []


def test_missing_snapshot_still_monitors_open_extra_trades(lane, monkeypatch, caplog):
    monkeypatch.setattr(universe, "short_snapshot", lambda day, live: None)
    monkeypatch.setattr(scan_run, "build_extra_candidates", lambda *a, **k: [])
    monkeypatch.setattr(scan_run, "_short_reference", lambda *a: None)
    alerts, _closed, _near = short_run._sync_run_short_scan(False)
    assert alerts == [] and lane["monitored"] == ["OLD"] and lane["built"] == []


def test_a_lane_failure_is_logged_and_returns_no_alerts(lane, monkeypatch, caplog):
    def boom(*a, **k):
        raise RuntimeError("cold pool exploded")
    monkeypatch.setattr(fetch, "_crawl_bounded", boom)
    with caplog.at_level("WARNING"):
        assert asyncio.run(short_run.run_short_universe_scan()) == []
    assert "SHORT extra lane failed" in caplog.text


# --- sequencing at the Discord layer ------------------------------------------------

def _record_order(monkeypatch):
    from swingbot.commands.scanning import alerts as alerts_mod
    events = []

    async def fake_send(dest, alerts, route_by_confidence=False):
        events.append(("send", list(alerts)))

    async def fake_short(**kw):
        events.append(("short_fetch", kw["require_confirmation"]))
        return ["SHORT"]

    monkeypatch.setattr(alerts_mod, "_send_alerts", fake_send)
    monkeypatch.setattr(alerts_mod.scan_engine, "run_short_universe_scan", fake_short)
    return alerts_mod, events


def test_base_alerts_are_sent_before_the_first_extra_fetch(monkeypatch):
    alerts_mod, events = _record_order(monkeypatch)
    monkeypatch.setattr(config, "SHORT_UNIVERSE_ENABLED", True)
    asyncio.run(alerts_mod.send_then_short("chan", ["BASE"], require_confirmation=True))
    assert events == [("send", ["BASE"]), ("short_fetch", True), ("send", ["SHORT"])]


def test_flag_off_sends_base_only_and_never_fetches(monkeypatch):
    alerts_mod, events = _record_order(monkeypatch)
    monkeypatch.setattr(config, "SHORT_UNIVERSE_ENABLED", False)
    asyncio.run(alerts_mod.send_then_short("chan", ["BASE"]))
    assert events == [("send", ["BASE"])]


def test_the_scheduled_and_manual_callers_use_the_sequencing_helper():
    import inspect
    from swingbot.commands.scanning import commands, loops
    assert "send_then_short(channel, alerts" in inspect.getsource(loops._session_scan_tick)
    assert "send_then_short(ctx, alerts" in inspect.getsource(commands.check_cmd.callback)
