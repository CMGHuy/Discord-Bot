"""Plan v8 Task V13: the legacy (untiered) alert path is off by default.

The cohort this cut removes is defined in the live trade log by
`source=None` -- no source, no tier, no badge. n=154, WR 26.0%, -103.0%,
about 72% of all damage. In the code that cohort is exactly "an alert
posted while no live v2 plan exists", because the same expression
(`PLAN_ENGINE_V2 == "on" and item.plan_v2 is not None`) decides both
whether the alert posts and whether its trade row carries pedigree or
three Nones.

These tests drive `_sync_run_scan` rather than calling the gate directly:
a filter wired in the wrong place is a documented silent no-op in this
repo (known-traps.md), so a test that never runs the scan loop would pass
whether the cut is wired, mis-wired, or deleted.
"""
from types import SimpleNamespace

import pytest

import swingbot.config as config
from swingbot.core.performance import TradeLog
from swingbot.core.scanning import engine

from tests.test_engine_v2_plans import _structured_df


def _drive_scan(monkeypatch, tmp_path, *, mode, legacy_enabled):
    """Run one real scan pass with the network/filesystem-bound parts of the
    alert loop stubbed. Returns (alerts, trade_log)."""
    df = _structured_df()

    monkeypatch.setattr(config, "PLAN_ENGINE_V2", mode)
    monkeypatch.setattr(config, "LEGACY_ALERT_PATH_ENABLED", legacy_enabled)
    # With the engine live the loop persists every plan through PlanStore(),
    # whose default path is config.DATA_DIR -- the repo's REAL data dir. Point
    # it at tmp so the suite never writes production files.
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    # The same four hard filters plus the floor that every scan-integration
    # fixture in this repo loosens -- this df's nearest S/R sits ~1.4% out.
    monkeypatch.setattr(config, "MIN_REWARD_PCT", 0.5)
    monkeypatch.setattr(config, "MIN_STOP_DISTANCE_PCT", 0.0)
    monkeypatch.setattr(config, "MAX_STOP_LOSS_PCT", 50.0)
    monkeypatch.setattr(config, "MIN_RISK_REWARD_RATIO", 0.0)
    monkeypatch.setattr(config, "TARGET_FLOOR_ENABLED", False)
    monkeypatch.setattr(config, "MIN_ALERT_CONFIDENCE_LEVEL", 1)
    monkeypatch.setitem(engine.HORIZONS["4w"], "sr_target_min_pct", 1.0)

    trade_log = TradeLog(path=str(tmp_path / "trades.json"))
    monkeypatch.setattr(engine, "load_watchlist", lambda: ["TEST"])
    monkeypatch.setattr(engine, "get_daily_data",
                        lambda ticker, period=None: df.copy() if ticker == "TEST" else None)
    monkeypatch.setattr(engine, "get_current_price", lambda ticker: None)
    monkeypatch.setattr(engine, "trade_log", trade_log)
    monkeypatch.setattr(engine, "is_stop_requested", lambda: False)
    monkeypatch.setattr(engine, "earnings_within_window", lambda t, d: None)
    monkeypatch.setattr(engine, "get_market_events", lambda d: [])
    monkeypatch.setattr(engine, "generate_trade_chart", lambda *a, **k: str(tmp_path / "c.png"))
    monkeypatch.setattr(engine, "notify_secondary", lambda *a, **k: None)
    monkeypatch.setattr(engine, "build_embed", lambda *a, **k: SimpleNamespace(fields=[]))

    result = engine._sync_run_scan("4w", require_confirmation=False,
                                   progress=None, min_confluence=0)
    return result, trade_log


def _alerts(result):
    """_sync_run_scan's return shape varies by branch -- pull the alert list
    out of whichever container it comes back in."""
    if isinstance(result, tuple):
        for part in result:
            if isinstance(part, list):
                return part
    return result if isinstance(result, list) else []


def test_the_flag_ships_off():
    """A cut that defaults on is not a cut. Read from the Field registry,
    which is what both the env parser and the admin Settings page use."""
    field = next(f for f in config.FIELDS if f.attr == "LEGACY_ALERT_PATH_ENABLED")
    assert field.default == "false"
    assert field.type == "checkbox"


def test_shadow_mode_posts_nothing_while_the_cut_is_on(monkeypatch, tmp_path):
    """In shadow mode no alert is v2-priced, so every one of them is the
    untiered cohort -- the cut must suppress all of them, and must not log
    a paper trade for any."""
    result, trade_log = _drive_scan(monkeypatch, tmp_path,
                                    mode="shadow", legacy_enabled=False)
    assert _alerts(result) == []
    assert trade_log.get_trades(status="open", limit=None) == []


def test_the_same_scenarios_do_post_when_the_flag_is_turned_back_on(monkeypatch, tmp_path):
    """The contrast that proves the suppression above is the flag's doing and
    not the fixture failing to produce a scenario at all."""
    result, trade_log = _drive_scan(monkeypatch, tmp_path,
                                    mode="shadow", legacy_enabled=True)
    assert _alerts(result), "fixture must produce alerts, or the test above proves nothing"
    trades = trade_log.get_trades(status="open", limit=None)
    assert trades, "legacy alerts still log paper trades when re-enabled"
    # ...and they are exactly the pedigree-less rows V13 is about.
    assert all(t.get("source") is None for t in trades)


def test_v2_plans_are_not_caught_by_the_cut(monkeypatch, tmp_path):
    """V13 Step 2. With the engine live, plans carry source="confluence" and
    must sail through the same gate that suppressed the shadow-mode run --
    otherwise the cut is a kill switch on the whole scanner, not a cohort cut."""
    result, trade_log = _drive_scan(monkeypatch, tmp_path,
                                    mode="on", legacy_enabled=False)
    assert _alerts(result), "v2-priced alerts must still post with the cut on"
    trades = trade_log.get_trades(status="open", limit=None)
    assert trades
    assert all(t.get("source") == "confluence" for t in trades)
    assert all(t.get("tier") is not None for t in trades)


def test_a_v2_build_failure_falls_back_to_suppression_not_to_an_untiered_alert(monkeypatch, tmp_path):
    """attach_plan_v2 swallows construction errors by design (a v2 bug must
    never break the scan). Before V13 that fallback quietly emitted an
    untiered alert -- i.e. the failure mode landed the trade in the -103%
    cohort. With the cut on, a build failure means no alert at all."""
    monkeypatch.setattr(engine, "build_confluence_plan", lambda *a, **k: 1 / 0)
    result, trade_log = _drive_scan(monkeypatch, tmp_path,
                                    mode="on", legacy_enabled=False)
    assert _alerts(result) == []
    assert trade_log.get_trades(status="open", limit=None) == []


def test_the_suppression_is_counted_for_telemetry(monkeypatch, tmp_path):
    """Silent suppression is how a starving channel gets misdiagnosed as a
    data outage. The count has to reach the funnel."""
    progress = engine.ScanProgress()
    progress.funnel = {}

    df = _structured_df()
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "shadow")
    monkeypatch.setattr(config, "LEGACY_ALERT_PATH_ENABLED", False)
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "MIN_REWARD_PCT", 0.5)
    monkeypatch.setattr(config, "MIN_STOP_DISTANCE_PCT", 0.0)
    monkeypatch.setattr(config, "MAX_STOP_LOSS_PCT", 50.0)
    monkeypatch.setattr(config, "MIN_RISK_REWARD_RATIO", 0.0)
    monkeypatch.setattr(config, "TARGET_FLOOR_ENABLED", False)
    monkeypatch.setattr(config, "MIN_ALERT_CONFIDENCE_LEVEL", 1)
    monkeypatch.setitem(engine.HORIZONS["4w"], "sr_target_min_pct", 1.0)
    monkeypatch.setattr(engine, "load_watchlist", lambda: ["TEST"])
    monkeypatch.setattr(engine, "get_daily_data",
                        lambda ticker, period=None: df.copy() if ticker == "TEST" else None)
    monkeypatch.setattr(engine, "get_current_price", lambda ticker: None)
    monkeypatch.setattr(engine, "trade_log", TradeLog(path=str(tmp_path / "trades.json")))
    monkeypatch.setattr(engine, "is_stop_requested", lambda: False)
    monkeypatch.setattr(engine, "notify_secondary", lambda *a, **k: None)

    engine._sync_run_scan("4w", require_confirmation=False,
                          progress=progress, min_confluence=0)
    assert progress.funnel["skipped_legacy_path"] > 0
