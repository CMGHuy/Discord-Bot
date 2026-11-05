"""V191-10: the live scan builds the band from COMPLETED bars, logs
band_no_atr when ATR14 is missing, and the requirement table shows the band."""
import logging
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.market import atr_band, levels
from swingbot.core.market.strategy import HORIZONS
from swingbot.core.scanning import analyze, requirements, scan_run
from tests.market.test_atr_band import _frame

IN_SESSION = datetime(2026, 10, 21, 15, 0, tzinfo=timezone.utc)   # Wed 11:00 ET
FILTERS = {"min_reward_pct": 3.0, "max_stop_loss_pct": 7.0, "min_stop_distance_pct": 1.75,
           "min_risk_reward_ratio": 1.5}


@pytest.fixture
def seen(monkeypatch):
    calls = []
    real = levels.build_scenarios
    monkeypatch.setattr(levels, "collect_candidate_levels", lambda *a, **k: [])
    monkeypatch.setattr(levels, "build_level_map", lambda *a, **k: (
        [levels.Level(99.0, ["Rolling S/R"])], [levels.Level(108.0, ["Rolling S/R"])]))
    monkeypatch.setattr(analyze, "veto_bullish_for", lambda df: False)
    monkeypatch.setattr(levels, "build_scenarios",
                        lambda *a, **k: calls.append(k.get("band")) or real(*a, **k))
    return calls


def _run(df, k, now=IN_SESSION, filters=FILTERS):
    hf = {**filters, "confluence_atr_stop_floor": k} if k is not None else dict(filters)
    return analyze._horizon_scenarios(df, HORIZONS["4w"], 100.0, [], hf, ticker="XYZ", now=now)


def test_floor_off_or_a_pre_v191_snapshot_passes_no_band(seen):
    _run(_frame(), 0.0)
    _run(_frame(), None)                       # hard_filters without the key
    assert seen == [None, None]


def test_the_forming_bar_is_dropped_before_the_atr_is_read(seen):
    df = _frame(n=61, end="2026-10-21")
    df.iloc[-1, df.columns.get_loc("High")] = 500.0      # today's forming bar
    build = _run(df, 1.0)
    assert seen[0] == atr_band.band_for(df.iloc[:-1], 100.0, 1.0)
    assert seen[0].atr_pct == pytest.approx(4.0)
    assert [s.direction for s in build.scenarios] == ["bullish"]   # d 1.0 admitted by the band


def test_missing_atr_logs_band_no_atr_and_keeps_todays_admission(seen, caplog):
    with caplog.at_level(logging.INFO, logger=analyze.log.name):
        build = _run(_frame(n=10), 1.0)
    assert seen == [atr_band.AtrBand(1.0, None)]
    assert build.scenarios == []                                  # d 1.0 < 1.75, as today
    assert "XYZ (4-week swing): plan rejected (band_no_atr" in caplog.text


def test_the_hard_filter_snapshots_carry_the_floor(monkeypatch):
    monkeypatch.setattr(config, "CONFLUENCE_ATR_STOP_FLOOR", 1.0)
    assert analyze._default_hard_filters()["confluence_atr_stop_floor"] == 1.0
    assert scan_run._hard_filters_snapshot()["confluence_atr_stop_floor"] == 1.0


def _checks(scenario):
    conf = SimpleNamespace(level=3, label="Medium", score=60)
    return {c.key: c for c in requirements._build_requirement_checks(scenario, (2, ["A", "B"]), conf, 2, 1)}


def test_requirement_rows_show_the_band(monkeypatch):
    monkeypatch.setattr(requirements.opex, "suppress_new_entries", lambda **k: False)
    monkeypatch.setattr(config, "CONFLUENCE_ATR_STOP_FLOOR", 1.0)
    sc = levels.build_scenarios(100.0, [levels.Level(99.0, ["S"])], [levels.Level(108.0, ["R"])],
                                3.0, min_stop_distance_pct=1.75, max_stop_distance_pct=7.0,
                                min_risk_reward=1.5, band=atr_band.AtrBand(1.0, 4.0))[0]
    checks = _checks(sc)
    assert checks["min_stop_distance"].detail == "1.0% away (ATR band 4.0\u20138.0%: 1\u00d7 to 2\u00d7 ATR14)"
    assert checks["max_stop_distance"].detail == checks["min_stop_distance"].detail


def test_requirement_rows_without_a_band_are_todays_text(monkeypatch):
    monkeypatch.setattr(requirements.opex, "suppress_new_entries", lambda **k: False)
    sc = levels.build_scenarios(100.0, [levels.Level(98.0, ["S"])], [levels.Level(108.0, ["R"])],
                                3.0, min_stop_distance_pct=1.75, max_stop_distance_pct=7.0)[0]
    detail = _checks(sc)["min_stop_distance"].detail
    assert detail == f"2.0% away (needs {config.MIN_STOP_DISTANCE_PCT:.1f}%+)"


def test_completed_band_matches_a_frame_truncated_before_the_forming_bar():
    df = _frame(n=61, end="2026-10-21")
    df.iloc[-1, df.columns.get_loc("High")] = 500.0
    full = analyze._band_live(df, 100.0, 1.0, IN_SESSION, "XYZ", "4-week swing")
    truncated = analyze._band_live(df.iloc[:-1], 100.0, 1.0, IN_SESSION, "XYZ", "4-week swing")
    assert full == truncated == atr_band.AtrBand(1.0, pytest.approx(4.0))


def test_completed_frame_error_keeps_legacy_admission(seen, monkeypatch, caplog):
    from swingbot.core.scanning import strategy_pass

    def broken_frame(*args, **kwargs):
        raise ValueError("bad frame")

    monkeypatch.setattr(strategy_pass, "completed_frame", broken_frame)
    with caplog.at_level(logging.INFO, logger=analyze.log.name):
        build = _run(_frame(), 1.0)
    assert seen == [atr_band.AtrBand(1.0, None)]
    assert build.scenarios == []
    assert "plan rejected (band_no_atr" in caplog.text
